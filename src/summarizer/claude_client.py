"""
Anthropic Claude 客户端实现
"""
import os
import logging
from typing import List
from anthropic import Anthropic

from .base_llm_client import BaseLLMClient


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude 客户端"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.logger = logging.getLogger('daily_arxiv.llm.claude')
        
        # 获取 API Key
        api_key = config.get('api_key') or os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        base_url = config.get('base_url')
        if not api_key:
            raise ValueError("Claude API Key 未设置！请在 .env 文件中设置 CLAUDE_API_KEY")
        
        # 创建客户端
        if base_url:
            self.client = Anthropic(api_key=api_key, base_url=base_url)
        else:
            self.client = Anthropic(api_key=api_key)
        
        self.logger.info(f"Claude 客户端初始化成功，模型: {self.model}")
    
    def generate(self, prompt: str, system_prompt: str = None, max_tokens: int = None) -> str:
        """生成文本"""
        try:
            # 使用传入的 max_tokens 或默认值
            tokens = max_tokens if max_tokens is not None else self.max_tokens
            
            # Claude 需要明确的 system 参数
            kwargs = {
                "model": self.model,
                "max_tokens": tokens,
                "temperature": self.temperature,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            if system_prompt:
                kwargs["system"] = system_prompt
            
            response = self.client.messages.create(**kwargs)
            
            if len(response.content) == 1:
                res = response.content[0].text.strip()
            else:
                res = response.content[1].text.strip()
            # Claude 的响应结构
            return res
            
        except Exception as e:
            self.logger.error(f"Claude 生成失败: {str(e)}")
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
