# -*- coding: utf-8 -*-
import json
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import Dict
from flashtext import KeywordProcessor

# 导入配置
from .config import GLOSSARY_DIR, GLOSSARY_DB_PATH, LLM_DISCOVERY_DB_PATH, TranslationConfig

logger = logging.getLogger(__name__)

class GlossaryManager:
    def __init__(self):
        self.glossary_dir = Path(GLOSSARY_DIR)
        self.db_path = GLOSSARY_DB_PATH
        self.discovery_db_path = LLM_DISCOVERY_DB_PATH
        config = TranslationConfig()
        self.enable_discovery = config.enable_llm_discovery
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping: Dict[str, str] = {}
        self._initialized = False

    def initialize(self):
        """初始化：建表、增量更新、加载内存"""
        self._init_db(self.db_path)
        if self.enable_discovery:
            self._init_db(self.discovery_db_path)
        
        self.incremental_update()
        self._load_to_memory()
        self._initialized = True
        print(f"✅ 语料库初始化完毕: 内存中包含 {len(self.term_mapping)} 个术语")

    def _init_db(self, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS terms (
                source_term TEXT PRIMARY KEY,
                target_term TEXT,
                category TEXT,
                source_file TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_hashes (
                filename TEXT PRIMARY KEY,
                file_hash TEXT,
                processed_at TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def _calculate_file_hash(self, file_path: Path) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def incremental_update(self) -> int:
        if not self.glossary_dir.exists():
            self.glossary_dir.mkdir(parents=True, exist_ok=True)
            return 0
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename, file_hash FROM file_hashes")
        processed_files = dict(cursor.fetchall())
        
        updated_count = 0
        for file_path in self.glossary_dir.glob("*.json"):
            filename = file_path.name
            current_hash = self._calculate_file_hash(file_path)
            if filename not in processed_files or processed_files[filename] != current_hash:
                try:
                    self._process_single_file(file_path, cursor)
                    cursor.execute('''
                        INSERT OR REPLACE INTO file_hashes (filename, file_hash, processed_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    ''', (filename, current_hash))
                    updated_count += 1
                except Exception as e:
                    logger.error(f"处理语料文件 {filename} 失败: {e}")
        
        conn.commit()
        conn.close()
        return updated_count

    def _process_single_file(self, file_path: Path, cursor: sqlite3.Cursor):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            return
        for item in data:
            source = item.get('source_term', '').strip()
            target = item.get('target_term', '').strip()
            category = item.get('category', 'General')
            if source and target:
                cursor.execute('''
                    INSERT OR REPLACE INTO terms (source_term, target_term, category, source_file, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (source, target, category, file_path.name))

    def _load_to_memory(self):
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping = {}
        if self.enable_discovery:
            self._load_from_db(self.discovery_db_path)
        self._load_from_db(self.db_path)

    def _load_from_db(self, db_path):
        if not Path(db_path).exists():
            return
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT source_term, target_term FROM terms")
        rows = cursor.fetchall()
        for source, target in rows:
            self.keyword_processor.add_keyword(source, source)
            self.term_mapping[source] = target
        conn.close()

    def extract_terms(self, text: str) -> Dict[str, str]:
        found_sources = self.keyword_processor.extract_keywords(text)
        result = {}
        for source in set(found_sources):
            if source in self.term_mapping:
                result[source] = self.term_mapping[source]
        return result

    def save_terms(self, terms_dict: Dict[str, str], category: str = "LLM_Discovered"):
        if not terms_dict:
            return
        if self.enable_discovery:
            main_conn = sqlite3.connect(self.db_path)
            main_cursor = main_conn.cursor()
            main_cursor.execute("SELECT source_term FROM terms")
            main_keys = {row[0].lower() for row in main_cursor.fetchall()}
            main_conn.close()

            conn = sqlite3.connect(self.discovery_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT source_term, target_term FROM terms")
            existing_discovery = {row[0].lower(): row[1] for row in cursor.fetchall()}

            for source, target in terms_dict.items():
                s_c, t_c = source.strip(), target.strip()
                s_l = s_c.lower()
                if not s_c or not t_c or s_l in main_keys:
                    continue
                if s_l in existing_discovery and existing_discovery[s_l] == t_c:
                    continue
                cursor.execute('''
                    INSERT OR REPLACE INTO terms (source_term, target_term, category, source_file, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (s_c, t_c, category, "dynamic_cache"))
            conn.commit()
            conn.close()
        
        for source, target in terms_dict.items():
            s_c, t_c = source.strip(), target.strip()
            if s_c and t_c and s_c not in self.term_mapping:
                self.keyword_processor.add_keyword(s_c, s_c)
                self.term_mapping[s_c] = t_c

# 全局单例
glossary_manager = GlossaryManager()
