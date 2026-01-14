# -*- coding: utf-8 -*-
import json
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import Dict
from flashtext import KeywordProcessor

# 导入配置
from .config import GLOSSARY_DIR, GLOSSARY_DB_PATH, LLM_DISCOVERY_DB_PATH, LLM_DISCOVERY_CN_DB_PATH, TranslationConfig

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

    def initialize(self, reverse=False):
        """初始化：建表、增量更新、加载内存"""
        # [核心修改] 根据方向选择数据库路径
        if reverse:
            self.discovery_db_path = LLM_DISCOVERY_CN_DB_PATH
        else:
            self.discovery_db_path = LLM_DISCOVERY_DB_PATH

        # 1. 初始化精校库
        self._init_db(self.db_path)
        
        # 2. 如果启用，初始化发现库
        if self.enable_discovery:
            self._init_db(self.discovery_db_path)
        
        self.incremental_update()
        self._load_to_memory(reverse=reverse)
        self._initialized = True
        mode = "中->英 (反向)" if reverse else "英->中 (正向)"
        print(f"✅ 语料库初始化完毕 [{mode}]: 内存中包含 {len(self.term_mapping)} 个术语")

    def _init_db(self, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS terms (
                source_term TEXT PRIMARY KEY,
                target_term TEXT,
                category TEXT,
                description TEXT,
                instruction TEXT,
                source_file TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 增量检查列是否存在 (防止旧数据库报错)
        cursor.execute("PRAGMA table_info(terms)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'description' not in columns:
            cursor.execute("ALTER TABLE terms ADD COLUMN description TEXT")
        if 'instruction' not in columns:
            cursor.execute("ALTER TABLE terms ADD COLUMN instruction TEXT")
            
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
        # 定义需要扫描的目录
        scan_dirs = [
            self.glossary_dir,
            Path(self.glossary_dir).parent.parent / "online_db_api" / "glossary"
        ]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename, file_hash FROM file_hashes")
        processed_files = dict(cursor.fetchall())
        
        updated_count = 0
        for s_dir in scan_dirs:
            if not s_dir.exists():
                continue
                
            for file_path in s_dir.rglob("*.json"):
                # 使用绝对路径或相对于 scan_dirs 的路径作为标识，防止重名
                filename = str(file_path.absolute())
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
            description = item.get('description', '').strip()
            instruction = item.get('instruction', '').strip()
            if source and target:
                cursor.execute('''
                    INSERT OR REPLACE INTO terms (source_term, target_term, category, description, instruction, source_file, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (source, target, category, description, instruction, file_path.name))

    def _load_to_memory(self, reverse=False):
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping = {} # 存储 target_term (或更多信息)
        self.full_term_data = {} # [新增] 存储完整元数据
        if self.enable_discovery:
            self._load_from_db(self.discovery_db_path, reverse=reverse)
        self._load_from_db(self.db_path, reverse=reverse)

    def _load_from_db(self, db_path, reverse=False):
        if not Path(db_path).exists():
            return
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT source_term, target_term, category, description, instruction FROM terms")
        rows = cursor.fetchall()
        
        # 反向模式下的黑名单：习语和俚语不适合直接作为词条匹配，防止中译英时产生奇怪映射
        REVERSE_BLACKLIST = {"Idioms/Colloquialisms", "Slang"}

        for source, target, category, description, instruction in rows:
            source = source.strip() if source else ""
            target = target.strip() if target else ""
            category = category.strip() if category else ""
            description = description.strip() if description else ""
            instruction = instruction.strip() if instruction else ""
            
            if not source or not target:
                continue

            term_info = {
                "source": source,
                "target": target,
                "category": category,
                "description": description,
                "instruction": instruction
            }

            if reverse:
                # 如果是习语类，反向时跳过
                if category in REVERSE_BLACKLIST:
                    continue
                
                # 处理中文逗号分隔的情况
                clean_target = target.replace('，', ',')
                possible_keys = [t.strip() for t in clean_target.split(',')]
                
                for key in possible_keys:
                    if key:
                        self.keyword_processor.add_keyword(key, key)
                        self.term_mapping[key] = source
                        self.full_term_data[key] = term_info
            else:
                self.keyword_processor.add_keyword(source, source)
                self.term_mapping[source] = target
                self.full_term_data[source] = term_info
        conn.close()

    def extract_terms(self, text: str) -> Dict[str, dict]:
        """修改返回值为 dict 的 dict，包含完整信息"""
        found_sources = self.keyword_processor.extract_keywords(text)
        result = {}
        for source in set(found_sources):
            if source in self.full_term_data:
                result[source] = self.full_term_data[source]
        return result

    def save_terms(self, terms_dict: Dict[str, str], category: str = "LLM_Discovered"):
        if not terms_dict:
            return
        if self.enable_discovery:
            self._init_db(self.discovery_db_path) # 确保发现库结构也是最新的
            
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
                self.full_term_data[s_c] = {
                    "source": s_c,
                    "target": t_c,
                    "category": category,
                    "description": "",
                    "instruction": ""
                }

# 全局单例
glossary_manager = GlossaryManager()