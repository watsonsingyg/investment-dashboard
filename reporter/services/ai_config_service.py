"""
reporter/services/ai_config_service.py — AI 配置 DB CRUD。

操作 models/ai_config.py 单例记录（id=1）。
"""

from models.ai_config import AIConfig
from reporter.services.crypto import encrypt, decrypt


def get_ai_config(db) -> dict:
    """读取当前 AI 配置。返回 dict，Key 已解密。"""
    config = db.query(AIConfig).filter_by(id=1).first()
    if not config:
        return {
            "provider": "deepseek",
            "api_key": "",
            "api_base_url": "",
            "model": "",
            "tavily_api_key": "",
            "is_configured": False,
        }

    api_key = decrypt(config.api_key_encrypted or "")
    tavily_key = decrypt(config.tavily_api_key_encrypted or "")

    return {
        "provider": config.provider or "deepseek",
        "api_key": api_key,
        "api_base_url": config.api_base_url or "",
        "model": config.model or "",
        "tavily_api_key": tavily_key,
        "is_configured": config.is_configured or False,
    }


def save_ai_config(db, provider: str, api_key: str, api_base_url: str,
                   model: str, tavily_api_key: str) -> dict:
    """保存 AI 配置。Key 加密存储。返回 masked 配置供展示。"""
    config = db.query(AIConfig).filter_by(id=1).first()
    if not config:
        config = AIConfig(id=1)
        db.add(config)

    config.provider = provider or "deepseek"
    if api_key:
        config.api_key_encrypted = encrypt(api_key)
    if api_base_url:
        config.api_base_url = api_base_url
    if model:
        config.model = model
    if tavily_api_key:
        config.tavily_api_key_encrypted = encrypt(tavily_api_key)

    config.is_configured = bool(decrypt(config.api_key_encrypted or ""))
    config.updated_at = __import__("datetime").datetime.utcnow()

    db.commit()

    # 返回 masked 版本
    stored_key = decrypt(config.api_key_encrypted or "")
    return {
        "provider": config.provider,
        "api_key_masked": (
            stored_key[:4] + "****" + stored_key[-4:]
            if len(stored_key) > 8 else "****"
        ),
        "api_base_url": config.api_base_url,
        "model": config.model,
        "is_configured": config.is_configured,
    }
