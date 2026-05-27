"""
reporter/middleware/rate_limit.py — 速率限制中间件。

使用 flask-limiter 实现 API 频率控制：
- 全局: 200 req/min（所有接口）
- 认证: 10 req/min（登录/注册，防止暴力破解）
- AI 生成: 30 req/min（控制 API 费用）

存储: 开发环境用内存，生产可切换 Redis。
"""

from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_GLOBAL],
    storage_uri="memory://",
)

# 导出快捷装饰器
auth_limit = limiter.shared_limit(
    settings.RATE_LIMIT_AUTH,
    scope="auth",
)

ai_limit = limiter.shared_limit(
    settings.RATE_LIMIT_AI,
    scope="ai",
)


def register_rate_limit_handlers(app):
    """注册 429 错误处理器，返回 JSON 而非 HTML。"""

    from reporter.errors import too_many_requests

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return too_many_requests()
