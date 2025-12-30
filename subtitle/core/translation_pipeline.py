# -*- coding: utf-8 -*- 

import json
import asyncio
import logging
from typing import List, Dict, Tuple
from tqdm import tqdm

from .llm_client import call_llm, clean_and_extract_json
from .prompts import get_prompt_templates
from .glossary_manager import glossary_manager

logger = logging.getLogger(__name__)

def filter_relevant_glossary(text_content: str, full_glossary: Dict[str, str]) -> Dict[str, str]:
    relevant = {}
    text_lower = text_content.lower()
    for src, tgt in full_glossary.items():
        if src.lower() in text_lower:
            relevant[src] = tgt
    return relevant

async def extract_global_terms(config, blocks: List[Dict]) -> Dict[str, str]:
    """提取术语（动态循环采样版）"""
    templates = get_prompt_templates(config.target_lang)
    
    # 动态计算采样步数：每 100 块对应 1 步，最少 5 步
    num_passes = max(5, (len(blocks) + 99) // 100)
    print(f"=== Step 1: 构建术语表 (动态 {num_passes} 步循环采样) ===")
    
    all_llm_glossary = {}
    
    # 准备所有并发任务
    tasks = []
    
    for pass_idx in range(num_passes):
        sampled_text = ""
        for i in range(pass_idx, len(blocks), num_passes):
            sampled_text += blocks[i]['content'] + "\n"
        
        MAX_SAMPLE_LEN = 4000
        text_parts = [sampled_text[i:i+MAX_SAMPLE_LEN] for i in range(0, len(sampled_text), MAX_SAMPLE_LEN)]
        
        for part_text in text_parts:
            messages = [{"role": "system", "content": templates["TERM_EXTRACT"].format(content=part_text)}]
            # 创建协程任务
            tasks.append(call_llm(config, messages, temperature=config.temp_terms))
    
    if tasks:
        print(f"  🚀 发起 {len(tasks)} 个并发采样请求...")
        # 使用 tqdm 配合 asyncio.gather 的简单封装或手动分批
        # 这里直接 gather 所有任务，并用 tqdm 展示
        results = []
        pbar = tqdm(total=len(tasks), desc="并发提取术语")
        
        # 为了能让 pbar 更新，我们需要包装一下任务
        async def watched_task(task):
            res = await task
            pbar.update(1)
            return res
            
        results = await asyncio.gather(*[watched_task(t) for t in tasks])
        pbar.close()
        
        for result in results:
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
    """执行单次 API 请求并进行严格的 ID 校验"""
    templates = get_prompt_templates(config.target_lang)
    # 提取当前批次期望的所有 ID
    expected_ids = {int(b['index']) for b in sub_blocks}

    if stage == "literal":
        input_data = [{"id": int(b['index']), "text": b['content']} for b in sub_blocks]
        # 如果剥离上下文，直译阶段则不传入术语表
        g_text = glossary_text if use_context else "{}"
        msgs = [{"role": "system", "content": templates["LITERAL_TRANS"].format(
            glossary=g_text, json_input=json.dumps(input_data, ensure_ascii=False)
        )}]
        raw = await call_llm(config, msgs, temperature=config.temp_literal)
        res = clean_and_extract_json(raw)
    else:
        # polish 阶段
        polish_input = []
        for b in sub_blocks:
            lit_text = kwargs.get('literal_map', {}).get(str(b['index']), b['content'])
            polish_input.append({"id": int(b['index']), "original": b['content'], "literal": lit_text})
        
        ctx = kwargs.get('previous_context', "None") if use_context else "None"
        f_ctx = kwargs.get('future_context', "None") if use_context else "None"
        g_text = glossary_text if use_context else "{}"

        msgs = [{"role": "system", "content": templates["REVIEW_AND_POLISH"].format(
            glossary=g_text, 
            json_input=json.dumps(polish_input, ensure_ascii=False),
            previous_context=ctx,
            future_context=f_ctx
        )}]
        raw = await call_llm(config, msgs, temperature=config.temp_polish)
        res = clean_and_extract_json(raw)

    # --- 严格 ID 校验逻辑 ---
    if not isinstance(res, list):
        return None

    # 1. 检查长度
    if len(res) != len(sub_blocks):
        logger.warning(f"[{stage.upper()}] 长度不匹配: 期望 {len(sub_blocks)}, 实际 {len(res)}。准备重试...")
        return None

    # 2. 检查 ID 是否完全匹配
    returned_ids = set()
    for item in res:
        if not isinstance(item, dict) or 'id' not in item:
            return None
        try:
            returned_ids.add(int(item['id']))
        except (ValueError, TypeError):
            return None

    if returned_ids != expected_ids:
        logger.warning(f"[{stage.upper()}] ID 不匹配: 输入 {expected_ids} vs 返回 {returned_ids}。准备重试...")
        return None

    # 将原文附带回去，方便后续 context 构建
    if stage == "polish":
        id_to_original = {int(b['index']): b['content'] for b in sub_blocks}
        for item in res:
            item['original'] = id_to_original.get(int(item['id']), "")

    return res

async def ladder_rescue_engine(blocks: List[Dict], config, glossary_text: str, stage: str, **kwargs) -> List[Dict]:
    """梯次拯救引擎：8 -> 6 -> 4 -> 2 -> 1，支持动态上下文维护"""
    ladder = [8, 6, 4, 2, 1]
    results = []
    
    # 动态维护上下文语境
    running_context = kwargs.get('previous_context', "None")
    
    idx = 0
    while idx < len(blocks):
        success = False
        remaining = len(blocks) - idx
        
        for size in [s for s in ladder if s <= remaining]:
            chunk = blocks[idx:idx+size]
            
            # 更新当前尝试的参数，确保使用最新的上下文
            current_kwargs = {**kwargs, 'previous_context': running_context}
            
            # 尝试带上下文
            for _ in range(2):
                res = await _do_single_request(stage, chunk, config, glossary_text, use_context=True, **current_kwargs)
                if res:
                    results.extend(res)
                    # 只有润色阶段需要更新 running_context
                    if stage == "polish":
                        # 将刚生成的 翻译/润色 结果追加到 context
                        new_context_lines = [f"- {item.get('original', '')} -> {item.get('polished', '')}" for item in res]
                        if running_context == "None":
                            running_context = "\n".join(new_context_lines)
                        else:
                            running_context += "\n" + "\n".join(new_context_lines)
                    
                    idx += size
                    success = True
                    break
            if success: break
            
            # 尝试剥离上下文
            res = await _do_single_request(stage, chunk, config, glossary_text, use_context=False, **current_kwargs)
            if res:
                results.extend(res)
                if stage == "polish":
                    new_context_lines = [f"- {item.get('original', '')} -> {item.get('polished', '')}" for item in res]
                    if running_context == "None":
                        running_context = "\n".join(new_context_lines)
                    else:
                        running_context += "\n" + "\n".join(new_context_lines)
                idx += size
                success = True
                break
        
        if not success:
            bad_block = blocks[idx]
            logger.warning(f"ID {bad_block['index']} 无法翻译，将降级保留原文/直译")
            if stage == "literal":
                res_item = {"id": int(bad_block['index']), "trans": bad_block['content']}
                results.append(res_item)
            else:
                lit = kwargs.get('literal_map', {}).get(str(bad_block['index']), bad_block['content'])
                res_item = {"id": int(bad_block['index']), "polished": lit}
                results.append(res_item)
                # 即使失败也把这个“原文”作为后续参考，防止断档
                new_line = f"- {bad_block['content']} -> {res_item['polished']}"
                if running_context == "None":
                    running_context = new_line
                else:
                    running_context += "\n" + new_line
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