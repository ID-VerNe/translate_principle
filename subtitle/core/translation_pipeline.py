# -*- coding: utf-8 -*- 

import json
from typing import List, Dict, Tuple

from .llm_client import call_llm, clean_and_extract_json
from .prompts import get_prompt_templates
# 引入语料库管理器
from .glossary_manager import glossary_manager

PROMPT_TEMPLATES = get_prompt_templates()

def filter_relevant_glossary(text_content: str, full_glossary: Dict[str, str]) -> Dict[str, str]:
    """
    仅保留在当前文本中出现的术语，减少 Token 消耗并聚焦注意力。
    """
    relevant = {}
    text_lower = text_content.lower()
    for src, tgt in full_glossary.items():
        if src.lower() in text_lower:
            relevant[src] = tgt
    return relevant

async def extract_global_terms(config, blocks: List[Dict]) -> Dict[str, str]:
    """
    提取术语（混合模式：历史语料库匹配 + LLM 新术语发现）
    """
    print("=== Step 1: 构建术语表 ===")
    
    # 1. 拼接全文
    full_text = "\n".join([b['content'] for b in blocks])
    
    # 2. 从历史语料库中匹配 (基于 FlashText，速度极快)
    print("  正在检索历史语料库...")
    historical_glossary = glossary_manager.extract_terms(full_text)
    print(f"  📖 匹配到 {len(historical_glossary)} 个历史固定术语")

    # 3. 使用 LLM 发现新术语 (采样处理)
    print("  正在使用 LLM 发现新术语...")
    sampled_text = ""
    # 稍微增加采样密度，每5行采一行，或者取前中后
    for i in range(0, len(blocks), 5): 
        sampled_text += blocks[i]['content'] + "\n"
    
    if len(sampled_text) > 3000:
        sampled_text = sampled_text[:3000]

    messages = [{"role": "system", "content": PROMPT_TEMPLATES["TERM_EXTRACT"].format(content=sampled_text)}]
    
    # 这里的 temperature 低一点，减少幻觉
    result = await call_llm(config, messages, temperature=config.temp_terms)
    
    llm_glossary = {}
    data = clean_and_extract_json(result)
    if isinstance(data, dict):
        llm_glossary = data
    
    print(f"  🤖 LLM 发现了 {len(llm_glossary)} 个新术语")

    # 4. 合并术语表
    # 策略：历史术语覆盖 LLM 提取的术语 (History is Truth)
    # 这样可以修正 LLM 可能产生的错误幻觉，保持系列一致性
    final_glossary = {**llm_glossary, **historical_glossary}
    
    print(f"  ✅ 最终术语表包含 {len(final_glossary)} 条目")
    return final_glossary


async def process_literal_stage(batch_blocks: List[Dict], config, glossary: Dict[str, str]) -> Tuple[Dict[str, str], str]:
    """
    阶段1：直译与术语准备（上下文无关，可并行）
    返回: (literal_map, glossary_text)
    """
    # --- 0. 动态语料库筛选 ---
    batch_text_all = " ".join([b['content'] for b in batch_blocks])
    relevant_glossary = filter_relevant_glossary(batch_text_all, glossary)
    glossary_text = json.dumps(relevant_glossary, ensure_ascii=False)

    # --- 1. 直译 (Literal) ---
    input_data = [{"id": int(b['index']), "text": b['content']} for b in batch_blocks]
    json_input = json.dumps(input_data, ensure_ascii=False, indent=2)

    msgs_trans = [{"role": "system", "content": PROMPT_TEMPLATES["LITERAL_TRANS"].format(
        glossary=glossary_text, json_input=json_input
    )}]

    trans_list = []
    # 增加结果校验重试逻辑
    for attempt in range(config.max_retries):
        raw_trans = await call_llm(config, msgs_trans, temperature=config.temp_literal)
        trans_list = clean_and_extract_json(raw_trans)
        
        # 简单校验：如果返回了非空列表，且包含基本的 id/trans 字段，则视为成功
        if trans_list and isinstance(trans_list, list) and len(trans_list) > 0:
            break
        else:
            print(f"  [Warn] 直译结果解析失败或为空 (Attempt {attempt+1}/{config.max_retries})，正在重试...")

    # 建立直译映射表 {id: text}
    literal_map = {}
    if isinstance(trans_list, list):
        for item in trans_list:
            if isinstance(item, dict) and 'id' in item and 'trans' in item:
                literal_map[str(item['id'])] = item['trans']
    
    return literal_map, glossary_text


async def process_polish_stage(batch_blocks: List[Dict], config, literal_map: Dict[str, str], glossary_text: str, previous_context: str = "") -> List[Dict]:
    """
    阶段2：润色（依赖上文，必须串行）
    """
    # --- 2. 润色 (Polish) ---
    # 构建润色输入：包含原文和直译
    polish_input_data = []
    for b in batch_blocks:
        idx = str(b['index'])
        # 即使直译失败，也把原文放进去，防止断档
        lit_text = literal_map.get(idx, b['content'])
        polish_input_data.append({
            "id": int(idx),
            "original": b['content'],
            "literal": lit_text
        })

    json_polish_input = json.dumps(polish_input_data, ensure_ascii=False, indent=2)

    # 处理空上下文的情况
    context_to_send = previous_context if previous_context else "None (Beginning of file, please establish the translation style)."

    msgs_polish = [{"role": "system", "content": PROMPT_TEMPLATES["REVIEW_AND_POLISH"].format(
        glossary=glossary_text, 
        json_input=json_polish_input,
        previous_context=context_to_send
    )}]

    polish_list = []
    # 增加结果校验重试逻辑
    for attempt in range(config.max_retries):
        raw_polish = await call_llm(config, msgs_polish, temperature=config.temp_polish)
        polish_list = clean_and_extract_json(raw_polish)
        
        if polish_list and isinstance(polish_list, list) and len(polish_list) > 0:
            break
        else:
             print(f"  [Warn] 润色结果解析失败或为空 (Attempt {attempt+1}/{config.max_retries})，正在重试...")

    # 建立润色映射表
    polish_map = {}
    if isinstance(polish_list, list):
        for item in polish_list:
            if isinstance(item, dict) and 'id' in item and 'polished' in item:
                polish_map[str(item['id'])] = item['polished']

    # --- 3. 最终组装 ---
    final_blocks = []

    for block in batch_blocks:
        idx = block['index']

        # 优先级：润色结果 > 直译结果 > 原文
        if idx in polish_map and len(polish_map[idx]) > 0:
            final_text = polish_map[idx]
        elif idx in literal_map and len(literal_map[idx]) > 0:
            final_text = literal_map[idx]
            # 只有在直译和润色双重失败后，才会打印这个 Info
            # print(f"  [Info] ID {idx} 润色丢失，回退到直译") 
        else:
            final_text = block['content']
            print(f"  [Error] ID {idx} 翻译完全失败，保留原文") # 只有真的全挂了才 Error

        final_blocks.append({
            "index": idx,
            "timestamp": block['timestamp'],
            "original": block['content'],
            "polished": final_text
        })

    return final_blocks
