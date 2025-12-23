# -*- coding: utf-8 -*-
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict
from flashtext import KeywordProcessor

# 导入配置
from .config import GLOSSARY_DIR, GLOSSARY_DB_PATH

class GlossaryManager:
    def __init__(self):
        self.glossary_dir = Path(GLOSSARY_DIR)
        self.db_path = GLOSSARY_DB_PATH
        # case_sensitive=False 通常更鲁棒，避免 "top gear" 和 "Top Gear" 匹配失败
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping: Dict[str, str] = {}
        self._initialized = False

    def initialize(self):
        """初始化：建表、增量更新、加载内存"""
        print(f"初始化语料库管理器...")
        self._init_db()
        
        changes = self.incremental_update()
        if changes > 0:
            print(f"   检测到 {changes} 个语料文件变化，已更新数据库")
        
        self._load_to_memory()
        self._initialized = True
        print(f"语料库加载完毕: 内存中包含 {len(self.term_mapping)} 个历史术语")

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
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
            print(f"⚠️ 语料库目录不存在: {self.glossary_dir}, 已自动创建")
            self.glossary_dir.mkdir(parents=True, exist_ok=True)
            return 0
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT filename, file_hash FROM file_hashes")
        processed_files = dict(cursor.fetchall())
        
        updated_count = 0
        
        # 扫描 JSON 文件
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
                    print(f"❌ 处理文件 {filename} 失败: {e}")
        
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT source_term, target_term FROM terms")
        rows = cursor.fetchall()
        
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping = {}
        
        for source, target in rows:
            # FlashText 提取时，我们希望它返回原文(source)，然后我们去查字典
            # 也可以直接替换，但为了给 LLM 展示 "原文->译文"，我们需要保留原文键
            self.keyword_processor.add_keyword(source, source)
            self.term_mapping[source] = target # 这里存的是小写还是原样取决于 FlashText 设置，建议存原样
            
        conn.close()

    def extract_terms(self, text: str) -> Dict[str, str]:
        """从文本中匹配历史术语"""
        found_sources = self.keyword_processor.extract_keywords(text)
        result = {}
        for source in set(found_sources):
            # 注意：FlashText 大小写不敏感时返回的名字可能需要去 mapping 里查标准 key
            # 这里简化处理，假设 mapping 里的 key 覆盖了这种情况
            if source in self.term_mapping:
                result[source] = self.term_mapping[source]
        return result

# 全局单例
glossary_manager = GlossaryManager()
