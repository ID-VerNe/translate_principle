# -*- coding: utf-8 -*- 

import json
import asyncio
import logging
from typing import List, Dict, Tuple

from .llm_client import call_llm, clean_and_extract_json
from .prompts import get_prompt_templates
from .glossary_manager import glossary_manager

logger = logging.getLogger(__name__)
PROMPT_TEMPLATES = get_prompt_templates()

def filter_relevant_glossary(text_content: str, full_glossary: Dict[str, str]) -> Dict[str, str]:
    relevant = {}
    text_lower = text_content.lower()
    for src, tgt in full_glossary.items():
        if src.lower() in text_lower:
            relevant[src] = tgt
    return relevant

async def extract_global_terms(config, blocks: List[Dict]) -> Dict[str, str]:
    """提取术语（五步循环采样版）"""
    print("=== Step 1: 构建术语表 (五步循环采样) ===")
    
    all_llm_glossary = {}
    for pass_idx in range(5):
        sampled_text = ""
        for i in range(pass_idx, len(blocks), 5):
            sampled_text += blocks[i]['content'] + "\n"
        
        MAX_SAMPLE_LEN = 4000
        text_parts = [sampled_text[i:i+MAX_SAMPLE_LEN] for i in range(0, len(sampled_text), MAX_SAMPLE_LEN)]
        
        for part_idx, part_text in enumerate(text_parts):
            messages = [{"role": "system", "content": PROMPT_TEMPLATES["TERM_EXTRACT"].format(content=part_text)}]
            result = await call_llm(config, messages, temperature=config.temp_terms)
            data = clean_and_extract_json(result)
            if isinstance(data, dict):
                all_llm_glossary.update(data)
    
    full_text = "\n".join([b['content'] for b in blocks])
    historical_glossary = glossary_manager.extract_terms(full_text)
    final_glossary = {**all_llm_glossary, **historical_glossary}
    
    if all_llm_glossary:
        glossary_manager.save_terms(all_llm_glossary)
    
    print(f"  ✅ 最终术语表包含 {len(final_glossary)} 条目")
    return final_glossary

async def _do_single_request(stage: str, sub_blocks: List[Dict], config, glossary_text: str, use_context: bool, **kwargs) -> List[Dict]:
    if stage == "literal":
        input_data = [{"id": int(b['index']), "text": b['content']} for b in sub_blocks]
        g_text = glossary_text if use_context else "{}"
        msgs = [{"role": "system", "content": PROMPT_TEMPLATES["LITERAL_TRANS"].format(
            glossary=g_text, json_input=json.dumps(input_data, ensure_ascii=False)
        )}]
        raw = await call_llm(config, msgs, temperature=config.temp_literal)
        res = clean_and_extract_json(raw)
        return res if isinstance(res, list) and len(res) == len(sub_blocks) else None
    else:
        polish_input = []
        for b in sub_blocks:
            lit_text = kwargs.get('literal_map', {}).get(str(b['index']), b['content'])
            polish_input.append({"id": int(b['index']), "original": b['content'], "literal": lit_text})
        
        ctx = kwargs.get('previous_context', "None") if use_context else "None"
        f_ctx = kwargs.get('future_context', "None") if use_context else "None"
        g_text = glossary_text if use_context else "{}"

        msgs = [{"role": "system", "content": PROMPT_TEMPLATES["REVIEW_AND_POLISH"].format(
            glossary=g_text, 
            json_input=json.dumps(polish_input, ensure_ascii=False),
            previous_context=ctx,
            future_context=f_ctx
        )}]
        raw = await call_llm(config, msgs, temperature=config.temp_polish)
        res = clean_and_extract_json(raw)
        return res if isinstance(res, list) and len(res) == len(sub_blocks) else None

async def ladder_rescue_engine(blocks: List[Dict], config, glossary_text: str, stage: str, **kwargs) -> List[Dict]:
    ladder = [8, 6, 4, 2, 1]
    results = []
    
    idx = 0
    while idx < len(blocks):
        success = False
        remaining = len(blocks) - idx
        
        for size in [s for s in ladder if s <= remaining]:
            chunk = blocks[idx:idx+size]
            # 尝试带上下文
            for _ in range(2):
                res = await _do_single_request(stage, chunk, config, glossary_text, use_context=True, **kwargs)
                if res:
                    results.extend(res)
                    idx += size
                    success = True
                    break
            if success: break
            
            # 尝试剥离上下文
            res = await _do_single_request(stage, chunk, config, glossary_text, use_context=False, **kwargs)
            if res:
                results.extend(res)
                idx += size
                success = True
                break
        
        if not success:
            bad_block = blocks[idx]
            logger.warning(f"ID {bad_block['index']} 无法翻译，将降级保留原文/直译")
            if stage == "literal":
                results.append({"id": int(bad_block['index']), "trans": bad_block['content']})
            else:
                lit = kwargs.get('literal_map', {}).get(str(bad_block['index']), bad_block['content'])
                results.append({"id": int(bad_block['index']), "polished": lit})
            idx += 1
            
    return results

async def process_literal_stage(batch_blocks: List[Dict], config, glossary: Dict[str, str]) -> Tuple[Dict[str, str], str]:
    batch_text_all = " ".join([b['content'] for b in batch_blocks])
    relevant_glossary = filter_relevant_glossary(batch_text_all, glossary)
    glossary_text = json.dumps(relevant_glossary, ensure_ascii=False)
    trans_list = await ladder_rescue_engine(batch_blocks, config, glossary_text, stage="literal")
    literal_map = {str(item['id']): item.get('trans', '') for item in trans_list if 'id' in item}
    return literal_map, glossary_text

async def process_polish_stage(batch_blocks: List[Dict], config, literal_map: Dict[str, str], glossary_text: str, previous_context: str = "", future_context: str = "") -> List[Dict]:
    polished_list = await ladder_rescue_engine(
        batch_blocks, config, glossary_text, stage="polish",
        literal_map=literal_map,
        previous_context=previous_context,
        future_context=future_context
    )
    polish_map = {str(item['id']): item.get('polished', '') for item in polished_list if 'id' in item}

    final_blocks = []
    for block in batch_blocks:
        idx = str(block['index'])
        final_text = polish_map.get(idx) or literal_map.get(idx) or block['content']
        final_blocks.append({
            "index": block['index'], "timestamp": block['timestamp'],
            "original": block['content'], "polished": final_text
        })
    return final_blocks