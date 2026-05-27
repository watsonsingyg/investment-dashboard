"""
models/ai_config.py — 全局 AI 配置表（单实例）。
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from .base import Base


class AIConfig(Base):
    __tablename__ = "ai_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(20), default="deepseek")  # deepseek / openai / anthropic
    api_key_encrypted = Column(Text)
    api_base_url = Column(String(300))
    model = Column(String(100), default="deepseek-v4-pro")
    tavily_api_key_encrypted = Column(Text)
    is_configured = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
