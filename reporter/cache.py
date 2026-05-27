"""
reporter/cache.py — 简单 TTL 内存缓存。

用于 Dashboard / 治理报告等计算密集型接口的短期缓存。
生产环境可替换为 Redis。
"""

import time
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, Optional, Tuple

_lock = Lock()
_cache: Dict[str, Tuple[float, Any]] = {}


def cached(ttl_seconds: int = 60):
    """
    装饰器：缓存函数返回值，TTL 过期后重新计算。

    用法:
        @cached(ttl_seconds=30)
        def my_expensive_function(key: str) -> dict: ...

    缓存 key 由函数名 + args + kwargs 生成。
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存 key
            key_parts = [func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            now = time.time()

            with _lock:
                if cache_key in _cache:
                    expiry, value = _cache[cache_key]
                    if now < expiry:
                        return value
                # 缓存未命中或已过期
                result = func(*args, **kwargs)
                _cache[cache_key] = (now + ttl_seconds, result)
                return result

        return wrapper

    return decorator


def invalidate(prefix: str = ""):
    """清除缓存。prefix 为空时清除全部。"""
    with _lock:
        if prefix:
            keys = [k for k in _cache if k.startswith(prefix)]
            for k in keys:
                del _cache[k]
        else:
            _cache.clear()


def cache_stats() -> dict:
    """返回缓存统计信息。"""
    now = time.time()
    active = 0
    expired = 0
    with _lock:
        for _, (expiry, _) in _cache.items():
            if now < expiry:
                active += 1
            else:
                expired += 1
    return {"active": active, "expired": expired, "total": active + expired}
