# -*- coding: utf-8 -*-
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict
from flashtext import KeywordProcessor

# 导入配置
from .config import GLOSSARY_DIR, GLOSSARY_DB_PATH, LLM_DISCOVERY_DB_PATH, TranslationConfig

class GlossaryManager:
    def __init__(self):
        self.glossary_dir = Path(GLOSSARY_DIR)
        self.db_path = GLOSSARY_DB_PATH
        self.discovery_db_path = LLM_DISCOVERY_DB_PATH
        
        # 预加载配置以获取开关状态
        config = TranslationConfig()
        self.enable_discovery = config.enable_llm_discovery
        
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping: Dict[str, str] = {}
        self._initialized = False

    def initialize(self):
        """初始化：建表、增量更新、加载内存"""
        print(f"初始化语料库管理器 (发现库持久化: {'开启' if self.enable_discovery else '关闭'})...")
        print(f"   扫描目录: {self.glossary_dir.absolute()}")
        
        # 1. 初始化精校库
        self._init_db(self.db_path)
        
        # 2. 如果启用，初始化发现库
        if self.enable_discovery:
            self._init_db(self.discovery_db_path)
        
        # 3. 增量更新精校库 (从 JSON 文件)
        changes = self.incremental_update()
        if changes > 0:
            print(f"   检测到 {changes} 个语料文件变化，已更新精校数据库")
        else:
            print("   精校数据库已是最新，无需更新")
        
        # 4. 加载到内存
        self._load_to_memory()
        self._initialized = True
        print(f"语料库加载完毕: 内存中包含 {len(self.term_mapping)} 个合并术语")

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
        """仅针对精校库的 JSON 文件进行增量扫描"""
        if not self.glossary_dir.exists():
            print(f"⚠️ 语料库目录不存在: {self.glossary_dir.absolute()}")
            self.glossary_dir.mkdir(parents=True, exist_ok=True)
            return 0
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT filename, file_hash FROM file_hashes")
        processed_files = dict(cursor.fetchall())
        
        updated_count = 0
        json_files = list(self.glossary_dir.glob("*.json"))
        print(f"   找到 {len(json_files)} 个 JSON 语料文件")
        
        for file_path in json_files:
            filename = file_path.name
            current_hash = self._calculate_file_hash(file_path)
            
            if filename not in processed_files or processed_files[filename] != current_hash:
                print(f"     -> 正在处理: {filename}")
                try:
                    self._process_single_file(file_path, cursor)
                    cursor.execute('''
                        INSERT OR REPLACE INTO file_hashes (filename, file_hash, processed_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    ''', (filename, current_hash))
                    updated_count += 1
                except Exception as e:
                    print(f"❌ 处理文件 {filename} 失败: {e}")
        
        conn.commit()
        conn.close()
        return updated_count

    def _process_single_file(self, file_path: Path, cursor: sqlite3.Cursor):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            print(f"⚠️ 文件 {file_path.name} 格式不正确，应为 JSON 列表")
            return
        
        inserted = 0
        for item in data:
            source = item.get('source_term', '').strip()
            target = item.get('target_term', '').strip()
            category = item.get('category', 'General')
            if source and target:
                cursor.execute('''
                    INSERT OR REPLACE INTO terms (source_term, target_term, category, source_file, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (source, target, category, file_path.name))
                inserted += 1
        print(f"        已导入 {inserted} 条术语")

    def _load_to_memory(self):
        """加载逻辑：先发现库，后精校库，确保优先级"""
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping = {}
        
        # 1. 如果启用，加载 LLM 发现库
        if self.enable_discovery:
            self._load_from_db(self.discovery_db_path)
        
        # 2. 无论如何都加载精校库 (覆盖发现库)
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
        """从文本中匹配术语"""
        found_sources = self.keyword_processor.extract_keywords(text)
        result = {}
        for source in set(found_sources):
            if source in self.term_mapping:
                result[source] = self.term_mapping[source]
        return result

    def save_terms(self, terms_dict: Dict[str, str], category: str = "LLM_Discovered"):
        """保存新发现的术语：尊重开关，且不破坏内存中的主库词条"""
        if not terms_dict:
            return
            
        # 1. 物理保存 (仅当开启时)
        if self.enable_discovery:
            # 建立一个临时的主库 key 集合用于快速过滤
            main_conn = sqlite3.connect(self.db_path)
            main_cursor = main_conn.cursor()
            main_cursor.execute("SELECT source_term FROM terms")
            main_keys = {row[0].lower() for row in main_cursor.fetchall()}
            main_conn.close()

            conn = sqlite3.connect(self.discovery_db_path)
            cursor = conn.cursor()
            
            # 获取发现库中已有的词条用于去重
            cursor.execute("SELECT source_term, target_term FROM terms")
            existing_discovery = {row[0].lower(): row[1] for row in cursor.fetchall()}

            for source, target in terms_dict.items():
                source_clean = source.strip()
                target_clean = target.strip()
                source_lower = source_clean.lower()
                
                if not source_clean or not target_clean:
                    continue
                
                # A. 过滤：如果主库已经有了，绝对不存入发现库，尊重精校数据
                if source_lower in main_keys:
                    continue
                
                # B. 去重：如果发现库已经有了且译文相同，跳过
                if source_lower in existing_discovery and existing_discovery[source_lower] == target_clean:
                    continue

                cursor.execute('''
                    INSERT OR REPLACE INTO terms (source_term, target_term, category, source_file, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (source_clean, target_clean, category, "dynamic_cache"))
            conn.commit()
            conn.close()
        
        # 2. 更新当前内存 (无论是否持久化)
        for source, target in terms_dict.items():
            source_clean = source.strip()
            target_clean = target.strip()
            if source_clean and target_clean:
                # 仅当主库不存在此词时才更新内存，确保优先级
                if source_clean not in self.term_mapping:
                    self.keyword_processor.add_keyword(source_clean, source_clean)
                    self.term_mapping[source_clean] = target_clean

# 全局单例
glossary_manager = GlossaryManager()