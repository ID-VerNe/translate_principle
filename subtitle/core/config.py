# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()

# --- 基础路径 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 语料库路径 (供 glossary_manager 直接使用) ---
GLOSSARY_DIR = os.path.join(BASE_DIR, 'glossaries')
GLOSSARY_DB_PATH = os.path.join(BASE_DIR, 'glossary_cache.db')
LLM_DISCOVERY_DB_PATH = os.path.join(BASE_DIR, 'llm_discovery.db')
LLM_DISCOVERY_CN_DB_PATH = os.path.join(BASE_DIR, 'llm_discovery_cn.db')

@dataclass
class TranslationConfig:
    # --- API 配置 ---
    api_key: str = os.getenv("LLM_API_KEY", "")
    api_url: str = os.getenv("LLM_API_URL", "http://localhost:19183/v1/chat/completions")
    model_name: str = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-20b")
    
    # --- 并发控制 ---
    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "4"))
    rpm_limit: int = int(os.getenv("RPM_LIMIT", "60"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "8"))
    
    # --- 容错配置 ---
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    retry_delay: float = float(os.getenv("RETRY_DELAY", "2.0"))
    
    # --- 语料库配置 ---
    glossary_dir: str = GLOSSARY_DIR
    glossary_db_path: str = GLOSSARY_DB_PATH
    llm_discovery_db_path: str = LLM_DISCOVERY_DB_PATH
    enable_llm_discovery: bool = os.getenv("ENABLE_LLM_DISCOVERY", "True").lower() == "true"
    
    # [新增] 目标语言，默认中文 'zh'，可选英文 'en'
    target_lang: str = "zh" 
    
    # --- LLM 温度配置 ---
    temp_terms: float = float(os.getenv("TEMP_TERMS", "0.1"))
    temp_literal: float = float(os.getenv("TEMP_LITERAL", "0.3"))
    temp_polish: float = float(os.getenv("TEMP_POLISH", "0.5"))

    def __post_init__(self):
        # 确保目录存在
        os.makedirs(self.glossary_dir, exist_ok=True)