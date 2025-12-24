# -*- coding: utf-8 -*-
import os
import sys
import argparse
import asyncio
import hashlib
import logging
from typing import List

# 添加当前目录到路径，确保可以导入核心模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import TranslationConfig
from translate_srt_llm import run_translation

# 动态加载子模块
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# 获取子工具路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACT_TOOL_PATH = os.path.join(BASE_DIR, "pre-process", "01-extract_srt.py")
ASS_TOOL_PATH = os.path.join(BASE_DIR, "post-process", "02-post_process_ass.py")

extract_tool = load_module("extract_tool", EXTRACT_TOOL_PATH)
ass_tool = load_module("ass_tool", ASS_TOOL_PATH)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MainWorkflow")

class TranslationArgs:
    def __init__(self, input_file, output_file, bilingual, model_name=None, batch_size=None, target_lang="zh"):
        self.input_file = input_file
        self.output_file = output_file
        self.bilingual = bilingual
        self.target_lang = target_lang
        
        # 加载基础配置 (从 .env 读取)
        config = TranslationConfig()
        
        self.api_key = config.api_key
        self.api_url = config.api_url
        self.model_name = model_name if model_name else config.model_name
        self.batch_size = batch_size if batch_size else config.batch_size
        
        self.max_concurrent = config.max_concurrent_requests
        self.temp_terms = config.temp_terms
        self.temp_literal = config.temp_literal
        self.temp_polish = config.temp_polish
        self.progress_file = None
        self.glossary_cache_file = None

async def main():
    parser = argparse.ArgumentParser(description="字幕翻译一站式工具 - 从 MKV 到最终版字幕")
    
    # 输入输出控制 (CLI 的主要职责)
    parser.add_argument("-i", "--input", required=True, help="输入文件 (MKV 或 SRT)")
    parser.add_argument("-o", "--output", help="最终输出文件名 (可选)")
    parser.add_argument("-f", "--format", choices=["srt", "ass"], default="ass", help="最终输出格式 (默认 ass)")
    
    # 常用覆盖参数 (可选)
    parser.add_argument("--to-english", action="store_true", help="开启中译英模式")
    parser.add_argument("--bilingual", action="store_true", default=True, help="是否生成双语字幕 (默认开启)")
    parser.add_argument("--no-bilingual", action="store_false", dest="bilingual", help="仅保留中文字幕")
    parser.add_argument("--model", type=str, help="覆盖 .env 中的模型名称")
    parser.add_argument("--batch-size", type=int, help="覆盖 .env 中的批次大小")
    
    args = parser.parse_args()

    # 逻辑判断
    target_lang = "en" if args.to_english else "zh"

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        logger.error(f"找不到输入文件: {input_path}")
        return

    # 0. 确定最终输出格式和路径
    final_format = args.format
    if args.output:
        if args.output.lower().endswith(".srt"):
            final_format = "srt"
        elif args.output.lower().endswith(".ass"):
            final_format = "ass"
    
    final_output = args.output if args.output else os.path.splitext(input_path)[0] + f".{final_format}"

    # 1. 预处理
    working_srt = None
    if input_path.lower().endswith(".mkv"):
        logger.info(f"检测到 MKV 文件，正在提取字幕...")
        srt_files = extract_tool.extract_subtitles(input_path)
        if not srt_files:
            logger.error("未能从 MKV 中提取到有效的 SRT 字幕。")
            return
        working_srt = srt_files[0]
        logger.info(f"将处理提取出的第一个字幕轨道: {working_srt}")
    elif input_path.lower().endswith(".srt"):
        working_srt = input_path
    elif input_path.lower().endswith(".ass"):
        logger.info(f"检测到 ASS 字幕输入，正在转换为中间格式 SRT...")
        working_srt = extract_tool.convert_ass_file_to_srt(input_path)
        if not working_srt:
            logger.error("无法将 ASS 转换为 SRT 进行处理。")
            return
    else:
        logger.error("不支持的文件格式，请提供 MKV、SRT 或 ASS 文件。")
        return

    # 2. 翻译阶段
    cache_dir = os.path.join(BASE_DIR, ".cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    input_filename = os.path.basename(working_srt)
    file_hash = hashlib.md5(input_filename.encode('utf-8')).hexdigest()

    # 确定中间输出文件名（翻译后的 SRT）
    if final_format == "ass":
        # 如果最终要转 ASS，中间 SRT 丢到 cache
        translated_srt = os.path.join(cache_dir, f"translated_{file_hash}.srt")
    else:
        # 如果最终就要 SRT，直接输出到目标位置
        translated_srt = final_output
    
    trans_args = TranslationArgs(
        input_file=working_srt,
        output_file=translated_srt,
        bilingual=args.bilingual,
        model_name=args.model,
        batch_size=args.batch_size,
        target_lang=target_lang
    )

    logger.info(f"开始翻译流程: {working_srt} -> {translated_srt} (Target: {target_lang})")
    await run_translation(trans_args)

    # 3. 后处理
    if final_format == "ass":
        logger.info(f"正在将翻译后的 SRT 转换为 ASS 格式: {final_output}")
        
        head_path = os.path.join(BASE_DIR, "post-process", "asshead.txt")
        if not os.path.exists(head_path):
             head_path = "asshead.txt"
        
        ass_tool.srt_to_ass(translated_srt, head_path, final_output)
        logger.info(f"✅ 完成！最终字幕文件已生成: {os.path.abspath(final_output)}")
    else:
        logger.info(f"✅ 完成！最终字幕文件已生成: {os.path.abspath(final_output)}")

if __name__ == "__main__":
    asyncio.run(main())