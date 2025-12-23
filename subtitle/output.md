PS C:\Users\VerNe\Downloads\Documents\字幕处理> python 新版/translate_srt_llm.py
Traceback (most recent call last):
  File "C:\Users\VerNe\Downloads\Documents\字幕处理\新版\translate_srt_llm.py", line 14, in <module>
    from core.translation_pipeline import extract_global_terms, process_literal_stage, process_polish_stage
  File "C:\Users\VerNe\Downloads\Documents\字幕处理\新版\core\translation_pipeline.py", line 9, in <module>
    from .glossary_manager import glossary_manager
  File "C:\Users\VerNe\Downloads\Documents\字幕处理\新版\core\glossary_manager.py", line 10, in <module>
    from .config import GLOSSARY_DIR, GLOSSARY_DB_PATH
ImportError: cannot import name 'GLOSSARY_DIR' from 'core.config' (C:\Users\VerNe\Downloads\Documents\字幕处理\新版\core\config.py)
PS C:\Users\VerNe\Downloads\Documents\字幕处理> 
