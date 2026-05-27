"""
reporter/services/crypto.py — AES-256-GCM 加解密工具。

用于加密存储 AI API Key。密钥由 JWT_SECRET 派生。
cryptography 库已作为 PyJWT 的依赖安装，无需额外安装。
"""

import base64
import hashlib
import os
from config import settings


def _get_key() -> bytes:
    """从 JWT_SECRET 派生 32 字节 AES-256 密钥。"""
    return hashlib.sha256(settings.JWT_SECRET.encode()).digest()


def encrypt(plaintext: str) -> str:
    """
    AES-256-GCM 加密。
    返回 base64(iv + ciphertext) 字符串。
    """
    if not plaintext:
        return ""

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        # 无 cryptography 库时退化为 base64（不安全，仅开发用途）
        import logging
        logging.getLogger("pipeline").warning("cryptography 未安装，API Key 将以明文存储")
        return base64.b64encode(plaintext.encode()).decode()

    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # nonce + ciphertext
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(encrypted: str) -> str:
    """
    AES-256-GCM 解密。
    失败时返回空字符串，永不抛异常。
    """
    if not encrypted:
        return ""

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        try:
            return base64.b64decode(encrypted).decode()
        except Exception:
            return ""

    try:
        key = _get_key()
        aesgcm = AESGCM(key)
        raw = base64.b64decode(encrypted)
        nonce = raw[:12]
        ciphertext = raw[12:]
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
    except Exception:
        return ""
