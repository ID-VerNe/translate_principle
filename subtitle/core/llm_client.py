# -*- coding: utf-8 -*-

import json
import re
import time
import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional, Union
from json_repair import repair_json

# 设置模块日志
logger = logging.getLogger(__name__)

# 全局信号量与限流器
_semaphore = None
_rate_limiter = None

class TokenBucket:
    """简易令牌桶，用于控制 RPM (Requests Per Minute)"""
    def __init__(self, rpm):
        self.capacity = rpm
        self.tokens = rpm
        self.fill_rate = rpm / 60.0
        self.timestamp = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            elapsed = now - self.timestamp
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            self.timestamp = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.fill_rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1

def get_semaphore(config):
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.max_concurrent_requests)
    return _semaphore

def get_rate_limiter(config):
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = TokenBucket(config.rpm_limit)
    return _rate_limiter

def clean_and_extract_json(text: Optional[str]) -> Union[Dict, List]:
    """
    更鲁棒的 JSON 提取器：优先寻找 Markdown 代码块，然后结合 json_repair 进行容错处理。
    """
    if text is None:
        return []
    
    text = text.strip()
    if not text:
        return []

    # 1. 优先尝试提取 Markdown 代码块 (这是最准确的)
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, text)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except:
            # 如果代码块里的也不合法，尝试用 repair_json 修复
            try:
                repaired = repair_json(json_str)
                data = json.loads(repaired)
                if data is not None:
                    return data
            except:
                pass

    # 2. 如果没有代码块，或者代码块解析失败，尝试直接解析全文
    try:
        return json.loads(text)
    except:
        pass

    # 3. 寻找第一个 [ 或 { 开始的位置，截取到最后并尝试修复
    # 这一步能有效去除开头的废话（如 "Here is the result:"）
    start_idx = -1
    for i, char in enumerate(text):
        if char in ['{', '[']:
            start_idx = i
            break
    
    if start_idx != -1:
        potential_json = text[start_idx:]
        try:
            repaired = repair_json(potential_json)
            data = json.loads(repaired)
            if data is not None:
                return data
        except:
            pass

    # 4. 终极保底：对原始文本直接 repair
    try:
        repaired = repair_json(text)
        data = json.loads(repaired)
        return data if data is not None else []
    except:
        return []

async def call_llm(config, messages: List[Dict], temperature: float = 0.5) -> Optional[str]:
    """异步调用 LLM API"""
    sem = get_semaphore(config)
    limiter = get_rate_limiter(config)
    
    payload = {
        "model": config.model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
        "stream": False
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    async with sem:
        await limiter.acquire()
        
        for attempt in range(config.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(config.api_url, headers=headers, json=payload, timeout=120) as response:
                        if response.status == 429:
                            await asyncio.sleep(5)
                            continue
                        
                        raw_resp = await response.text()
                        if response.status != 200:
                            logger.error(f"API 返回状态码 {response.status}: {raw_resp}")
                            response.raise_for_status()
                        
                        try:
                            data = json.loads(raw_resp)
                        except Exception:
                            raise Exception(f"Invalid JSON response: {raw_resp[:100]}")

                        if 'choices' not in data or not data['choices']:
                            raise Exception("Invalid API Response: missing choices")
                            
                        message = data['choices'][0].get('message', {})
                        content = message.get('content')
                        refusal = message.get('refusal')

                        if refusal:
                            logger.warning(f"模型拒绝回答 (Refusal): {refusal}")
                            return ""

                        if content is None or content.strip() == "":
                            # 只有在 content_filter 导致空时才记录警告
                            finish_reason = data['choices'][0].get('finish_reason')
                            if finish_reason == "content_filter":
                                logger.warning("API 因内容安全过滤 (content_filter) 返回空内容")
                            return ""
                            
                        return content.strip()
            except Exception as e:
                if attempt < config.max_retries - 1:
                    await asyncio.sleep(config.retry_delay)
                else:
                    logger.error(f"API 请求最终失败: {e}")
    return None