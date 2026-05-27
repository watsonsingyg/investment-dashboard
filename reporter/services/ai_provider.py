"""
reporter/services/ai_provider.py — AI 多供应商抽象层。

支持 DeepSeek / OpenAI / Anthropic，统一为 stream_chat() 接口。
"""

import json
from abc import ABC, abstractmethod
from typing import Generator

import httpx
from models.base import SessionLocal
from models.ai_config import AIConfig
from reporter.services.crypto import decrypt
from config import settings


class AbstractAIChatProvider(ABC):
    """AI 聊天供应商抽象基类。"""

    @abstractmethod
    def stream_chat(
        self, system_prompt: str, user_message: str, model: str
    ) -> Generator[str, None, None]:
        """
        流式聊天，yield SSE 格式字符串：
          data: {"text": "..."}   — 增量文本
          data: {"done": True}    — 生成完成
          data: {"error": "..."}  — 错误
        """
        ...


# ═══════════════════════════════════════════════════════════════════════════
# DeepSeek Provider（OpenAI 兼容格式）
# ═══════════════════════════════════════════════════════════════════════════

class DeepSeekProvider(AbstractAIChatProvider):
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.deepseek.com"

    def stream_chat(self, system_prompt, user_message, model):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": True,
            "max_tokens": 2500,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        return self._stream_openai_format(url, payload, headers)

    @staticmethod
    def _stream_openai_format(url, payload, headers):
        try:
            with httpx.stream("POST", url, json=payload, headers=headers, timeout=120) as r:
                if r.status_code >= 400:
                    yield f'data: {json.dumps({"error": f"AI 服务返回错误：HTTP {r.status_code}"})}\n\n'
                    return
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        delta = json.loads(data_str)["choices"][0]["delta"].get("content", "")
                        if delta:
                            delta = delta.replace("*", "")
                            yield f'data: {json.dumps({"text": delta})}\n\n'
                    except Exception:
                        pass
            yield f'data: {json.dumps({"done": True})}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'


# ═══════════════════════════════════════════════════════════════════════════
# OpenAI Provider（与 DeepSeek 格式兼容）
# ═══════════════════════════════════════════════════════════════════════════

class OpenAIProvider(DeepSeekProvider):
    """OpenAI 使用与 DeepSeek 相同的 OpenAI 兼容 API 格式。"""

    def __init__(self, api_key: str, base_url: str = None):
        super().__init__(api_key, base_url or "https://api.openai.com")


# ═══════════════════════════════════════════════════════════════════════════
# Anthropic Provider（消息 API 格式）
# ═══════════════════════════════════════════════════════════════════════════

class AnthropicProvider(AbstractAIChatProvider):
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.anthropic.com"

    def stream_chat(self, system_prompt, user_message, model):
        payload = {
            "model": model,
            "max_tokens": 2500,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "stream": True,
        }
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        url = f"{self.base_url}/v1/messages"

        try:
            with httpx.stream("POST", url, json=payload, headers=headers, timeout=120) as r:
                if r.status_code >= 400:
                    yield f'data: {json.dumps({"error": f"Anthropic API 返回错误：HTTP {r.status_code}"})}\n\n'
                    return
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    try:
                        event = json.loads(data_str)
                        event_type = event.get("type", "")
                        if event_type == "content_block_delta":
                            delta = event.get("delta", {}).get("text", "")
                            if delta:
                                yield f'data: {json.dumps({"text": delta})}\n\n'
                        elif event_type == "message_stop":
                            break
                    except Exception:
                        pass
            yield f'data: {json.dumps({"done": True})}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'


# ═══════════════════════════════════════════════════════════════════════════
# 供应商工厂
# ═══════════════════════════════════════════════════════════════════════════

def get_provider(db_session=None) -> AbstractAIChatProvider:
    """
    从 DB 或环境变量获取 AI 供应商实例。

    优先级：
    1. DB ai_config 表 (is_configured=True)
    2. 环境变量 (settings.DEEPSEEK_API_KEY 等)
    3. 报错：未配置 AI 服务
    """
    provider_name = None
    api_key = None
    base_url = None

    # 1. 尝试 DB
    if db_session is not None:
        config = db_session.query(AIConfig).filter_by(id=1).first()
        if config and config.is_configured:
            provider_name = config.provider or "deepseek"
            api_key = decrypt(config.api_key_encrypted or "")
            base_url = config.api_base_url or ""

    # 2. 回退到环境变量
    if not api_key:
        if settings.DEEPSEEK_API_KEY:
            provider_name = "deepseek"
            api_key = settings.DEEPSEEK_API_KEY
            base_url = settings.DEEPSEEK_BASE_URL
        elif settings.ANTHROPIC_API_KEY:
            provider_name = "anthropic"
            api_key = settings.ANTHROPIC_API_KEY

    if not api_key:
        raise ValueError("未配置 AI 服务：请在 /settings 页面设置 API Key，或在 .env 中设置 DEEPSEEK_API_KEY")

    # 创建供应商实例
    provider_name = (provider_name or "").strip().lower()
    if provider_name == "openai":
        return OpenAIProvider(api_key, base_url or None)
    elif provider_name == "anthropic":
        return AnthropicProvider(api_key, base_url or None)
    else:
        # 默认 DeepSeek
        return DeepSeekProvider(api_key, base_url or None)


def get_ai_model(db_session=None) -> str:
    """
    从 DB 或环境变量获取当前配置的 model 名称。
    供 ai_service.py 调用，确保 stream_chat 使用正确的 model。
    """
    # 1. 尝试 DB
    if db_session is not None:
        config = db_session.query(AIConfig).filter_by(id=1).first()
        if config and config.is_configured and config.model:
            return config.model
    # 2. 回退到环境变量
    if settings.DEEPSEEK_API_KEY:
        return settings.DEEPSEEK_MODEL
    return settings.DEEPSEEK_MODEL  # 默认


def test_provider_connection(db_session=None) -> dict:
    """测试 AI 供应商连接。"""
    try:
        provider = get_provider(db_session)
        # 发送一个极简请求测试连接
        gen = provider.stream_chat("回复 OK", "ping", "default")
        for msg in gen:
            if '"done": true' in msg:
                return {"ok": True}
            if '"error"' in msg:
                return {"ok": False, "error": "供应商返回错误"}
            break  # 收到第一条响应即确认连接成功
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
