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
            # 补充令牌
            elapsed = now - self.timestamp
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            self.timestamp = now

            if self.tokens < 1:
                # 令牌不足，计算等待时间
                wait_time = (1 - self.tokens) / self.fill_rate
                await asyncio.sleep(wait_time)
                # 等待后重新计算（简化处理，直接扣除）
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
    # ... (原有代码保持不变) ...
    """
    鲁棒的 JSON 提取器，结合正则提取与 json_repair 容错解析
    """
    if not text:
        return []

    # 1. 提取 Markdown 代码块 ```json ... ``` 或直接提取内层 JSON 结构
    json_pattern = r'```(?:json)?\s*([\[\{].*?[\]\}])\s*```|[\[\{].*?[\]\}]'
    match = re.search(json_pattern, text, re.DOTALL)
    json_str = match.group(1) if match and match.group(1) else (match.group(0) if match else text)

    # 2. 尝试标准解析
    try:
        return json.loads(json_str)
    except:
        pass

    # 3. 终极兜底：使用 json_repair 修复并解析
    try:
        repaired = repair_json(json_str)
        return json.loads(repaired)
    except Exception as e:
        # logger.debug(f"JSON 解析彻底失败。原始文本: {text[:200]}... 错误: {e}")
        return []

async def call_llm(config, messages: List[Dict], temperature: float = 0.5) -> Optional[str]:
    """异步调用 LLM API，支持并发控制(Semaphore)、速率限制(RPM)与 Authorization"""
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

    # 1. 获取并发锁 (限制最大同时连接数)
    async with sem:
        # 2. 获取速率令牌 (限制每分钟请求数)
        await limiter.acquire()
        
        for attempt in range(config.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(config.api_url, headers=headers, json=payload, timeout=120) as response:
                        if response.status == 429:
                            # 触发了 Rate Limit，强制退避
                            logger.warning(f"触发 API Rate Limit (429)，等待 5 秒后重试...")
                            await asyncio.sleep(5)
                            raise Exception("Rate Limited")
                        
                        response.raise_for_status()
                        data = await response.json()
                        content = data['choices'][0]['message']['content'].strip()
                        return content
            except Exception as e:
                if attempt < config.max_retries - 1:
                    logger.warning(f"API请求失败 ({attempt + 1}/{config.max_retries}): {e}，将在 {config.retry_delay}s 后重试")
                    await asyncio.sleep(config.retry_delay)
                else:
                    logger.error(f"API请求最终失败: {e}")
    return None
