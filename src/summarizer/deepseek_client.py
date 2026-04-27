"""
DeepSeek 客户端实现

DeepSeek 使用 OpenAI 兼容的 API
"""
import os
import logging
from typing import List
from openai import OpenAI

from .base_llm_client import BaseLLMClient


class DeepSeekClient(BaseLLMClient):
    """DeepSeek 客户端"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.logger = logging.getLogger('daily_arxiv.llm.deepseek')
        
        # 获取 API Key
        api_key = config.get('api_key') or os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise ValueError("DeepSeek API Key 未设置！请在 .env 文件中设置 DEEPSEEK_API_KEY")
        
        # 获取 Base URL
        base_url = config.get('base_url', 'https://api.deepseek.com/v1')
        
        # 创建客户端（使用 OpenAI SDK）
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        self.logger.info(f"DeepSeek 客户端初始化成功，模型: {self.model}")
    
    def generate(self, prompt: str, system_prompt: str = None, max_tokens: int = None) -> str:
        """生成文本"""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            # 使用传入的 max_tokens 或默认值
            tokens = max_tokens if max_tokens is not None else self.max_tokens
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=tokens,
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            self.logger.error(f"DeepSeek 生成失败: {str(e)}")
            raise
    
    def generate_batch(self, prompts: List[str], system_prompt: str = None) -> List[str]:
        """批量生成文本"""
        results = []
        for prompt in prompts:
            try:
                result = self.generate(prompt, system_prompt)
                results.append(result)
            except Exception as e:
                self.logger.error(f"批量生成失败: {str(e)}")
                results.append(f"Error: {str(e)}")
        return results
