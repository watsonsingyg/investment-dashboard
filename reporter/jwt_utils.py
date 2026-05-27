"""
reporter/jwt_utils.py — JWT token 生成、验证、密码哈希。

使用 python-jose + bcrypt。token 通过 Authorization: Bearer 头传递。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
import bcrypt
from config import settings


def create_access_token(user_id: int, role: str, tenant_id: Optional[int] = None) -> str:
    """生成 access token（短期，默认 60 分钟）。包含 tenant_id 用于多租户隔离。"""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """生成 refresh token（长期，默认 30 天）。"""
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证 JWT token，返回 payload。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(plain: str) -> str:
    """哈希密码。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
