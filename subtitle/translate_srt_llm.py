# -*- coding: utf-8 -*-

import os
import json
import argparse
import asyncio
import logging
import hashlib
from typing import List, Dict
from tqdm import tqdm

# 在定义和修改配置前，先导入它们
from core.config import TranslationConfig
from core.srt_utils import parse_srt, format_srt_block
from core.translation_pipeline import extract_global_terms, process_literal_stage, process_polish_stage
from core.glossary_manager import glossary_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("translation.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def save_checkpoint(srt_file: str, progress_file: str, blocks: List[Dict], progress_data: Dict, bilingual_output: bool = False, last_context: str = ""):
    """
    保存检查点，使用 srt_utils 统一格式化。
    """
    if not blocks:
        return

    output_block_index = progress_data.get('output_block_index', 1)

    with open(srt_file, 'a', encoding='utf-8') as f:
        for b in blocks:
            if bilingual_output:
                # 块分离模式
                f.write(format_srt_block(output_block_index, b['timestamp'], b['original']))
                output_block_index += 1
                f.write(format_srt_block(output_block_index, b['timestamp'], b['polished']))
                output_block_index += 1
            else:
                f.write(format_srt_block(output_block_index, b['timestamp'], b['polished']))
                output_block_index += 1
    
    progress_data['output_block_index'] = output_block_index
    progress_data['last_context'] = last_context
    last_idx = int(blocks[-1]['index'])
    progress_data["last_index"] = last_idx
    processed_set = set(progress_data.get("processed_indices", []))
    processed_set.update(b['index'] for b in blocks)
    progress_data["processed_indices"] = sorted(list(processed_set), key=int)

    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, ensure_ascii=False, indent=2)

def load_progress(progress_file: str) -> Dict:
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_index": 0, "processed_indices": []}

async def run_translation(args):
    """执行翻译流程的核心逻辑"""
    
    # --- 0. 初始化配置与语料库 ---
    config = TranslationConfig(
        api_key=args.api_key,
        api_url=args.api_url,
        model_name=args.model_name,
        temp_terms=args.temp_terms,
        temp_literal=args.temp_literal,
        temp_polish=args.temp_polish,
        max_concurrent_requests=args.max_concurrent
    )
    glossary_manager.initialize()

    # --- 0.1 动态处理缓存路径 ---
    cache_dir = ".cache"
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    
    input_filename = os.path.basename(args.input_file)
    file_hash = hashlib.md5(input_filename.encode('utf-8')).hexdigest()
    
    glossary_cache_file = getattr(args, 'glossary_cache_file', None)
    if glossary_cache_file is None:
        glossary_cache_file = os.path.join(cache_dir, f"glossary_{file_hash}.json")
        
    progress_file = getattr(args, 'progress_file', None)
    if progress_file is None:
        progress_file = os.path.join(cache_dir, f"progress_{file_hash}.json")

    # --- 1. 加载 SRT ---
    blocks = parse_srt(args.input_file)
    if not blocks:
        logger.error(f"无法从 {args.input_file} 加载任何字幕块。")
        return
    logger.info(f"成功加载原文: {len(blocks)} 块")

    # --- 2. 构建当前任务的混合术语表 ---
    current_glossary = {}
    if os.path.exists(glossary_cache_file):
        try:
            with open(glossary_cache_file, 'r', encoding='utf-8') as f:
                current_glossary = json.load(f)
            logger.info(f"加载任务缓存术语表: {len(current_glossary)} 条")
        except:
            pass
            
    if not current_glossary:
        logger.info("开始提取全局术语表...")
        current_glossary = await extract_global_terms(config, blocks)
        with open(glossary_cache_file, 'w', encoding='utf-8') as f:
            json.dump(current_glossary, f, ensure_ascii=False, indent=2)
        logger.info(f"术语表已保存至: {glossary_cache_file}")

    # --- 显眼提示用户术语表位置 ---
    print("\n" + "="*60)
    print(f"📋 【当前生效的术语表】")
    print(f"   路径: {os.path.abspath(glossary_cache_file)}")
    print(f"   提示: 若需人工修正术语，请编辑此文件后重新运行脚本。")
    print("="*60 + "\n")

    # --- 3. 恢复进度 ---
    progress = load_progress(progress_file)
    processed_indices = set(progress.get("processed_indices", []))
    remaining_blocks = [b for b in blocks if b['index'] not in processed_indices]

    if not remaining_blocks:
        logger.info("所有字幕块都已处理完毕。")
        return

    if not processed_indices:
        open(args.output_file, 'w').close()
        progress['output_block_index'] = 1 
    progress.setdefault('output_block_index', 1)

    logger.info(f"开始处理，剩余 {len(remaining_blocks)} 块...")

    # 从进度文件中恢复上下文
    previous_context_str = progress.get('last_context', "")

    # --- 4. 准备批次列表 ---
    batches = []
    for i in range(0, len(remaining_blocks), args.batch_size):
        batches.append(remaining_blocks[i: i + args.batch_size])

    # --- 5. 流水线并行处理 ---
    literal_tasks = {}
    PREFETCH_WINDOW = 3 
    total_batches = len(batches)

    # 使用 tqdm 显示总进度
    pbar = tqdm(total=total_batches, desc="翻译进度", unit="batch")

    for i, batch in enumerate(batches):
        start_id, end_id = batch[0]['index'], batch[-1]['index']

        # A. 启动预取任务
        for j in range(i, min(i + PREFETCH_WINDOW + 1, total_batches)):
            if j not in literal_tasks:
                task = asyncio.create_task(process_literal_stage(batches[j], config, current_glossary))
                literal_tasks[j] = task

        # B. 获取直译结果
        literal_map, glossary_text = await literal_tasks[i]
        del literal_tasks[i]

        # C. 准备下文 (Future Context)
        future_context_str = ""
        if i + 1 < total_batches:
            # 取下一个批次的全部原文
            future_blocks = batches[i+1]
            future_context_str = "\n".join([f"- {b['content']}" for b in future_blocks])

        # D. 执行润色阶段
        final_blocks = await process_polish_stage(
            batch, config, literal_map, glossary_text, 
            previous_context=previous_context_str,
            future_context=future_context_str
        )
        
        if final_blocks:
            # 更新上文上下文（保留当前批次的全部翻译结果供下一批次参考）
            previous_context_str = "\n".join(
                [f"- {b['original']} -> {b['polished']}" for b in final_blocks]
            )

            save_checkpoint(args.output_file, progress_file, final_blocks, progress, bilingual_output=args.bilingual, last_context=previous_context_str)
            pbar.update(1)
            # tqdm.write 可以在不破坏进度条的情况下打印信息
            tqdm.write(f"  ✅ 批次 {i+1} (ID {start_id}-{end_id}) 处理完成。")
        else:
            logger.warning(f"批次 {i+1} 未生成任何内容。")

    pbar.close()
    logger.info("翻译任务圆满完成！")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="SRT 智能翻译工具 (架构优化版)")

    # --- 文件与路径参数 ---
    parser.add_argument('-i', '--input-file', type=str, default='官方英文.srt', help='输入SRT文件')
    parser.add_argument('-o', '--output-file', type=str, default='官方英文_output.srt', help='输出SRT文件')
    parser.add_argument('--progress-file', type=str, default=None, help='进度文件')
    parser.add_argument('--glossary-cache-file', type=str, default=None, help='术语缓存')
    
    # --- 运行参数 ---
    defaults = TranslationConfig()
    parser.add_argument('--batch-size', type=int, default=defaults.batch_size, help='批次大小')
    parser.add_argument('--max-concurrent', type=int, default=defaults.max_concurrent_requests, help='最大并发请求数')

    parser.add_argument('--bilingual', dest='bilingual', action='store_true', help='开启双语')
    parser.add_argument('--no-bilingual', dest='bilingual', action='store_false', help='仅中文')
    parser.set_defaults(bilingual=True)

    # --- API 与模型参数 ---
    parser.add_argument('--api-key', type=str, default=defaults.api_key, help='API Key')
    parser.add_argument('--api-url', type=str, default=defaults.api_url, help='API URL')
    parser.add_argument('--model-name', type=str, default=defaults.model_name, help='模型名称')
    
    # --- 温度参数 ---
    parser.add_argument('--temp-terms', type=float, default=defaults.temp_terms, help='术语提取温度')
    parser.add_argument('--temp-literal', type=float, default=defaults.temp_literal, help='直译温度')
    parser.add_argument('--temp-polish', type=float, default=defaults.temp_polish, help='润色温度')

    args = parser.parse_args()

    # 启动异步主逻辑
    asyncio.run(run_translation(args))

if __name__ == "__main__":
    main()