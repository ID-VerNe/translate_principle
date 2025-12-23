# -*- coding: utf-8 -*-
import os
from typing import Dict

PROMPT_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

def load_prompt(name: str) -> str:
    """从文件加载单个 prompt 模板。"""
    try:
        with open(os.path.join(PROMPT_DIR, f"{name}.prompt"), 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"Prompt template '{name}.prompt' not found in '{PROMPT_DIR}'")

def get_prompt_templates() -> Dict[str, str]:
    """加载所有 prompt 模板。"""
    return {
        "TERM_EXTRACT": load_prompt("term_extract"),
        "LITERAL_TRANS": load_prompt("literal_trans"),
        "REVIEW_AND_POLISH": load_prompt("review_and_polish"),
    }
