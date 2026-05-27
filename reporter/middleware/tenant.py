"""
reporter/middleware/tenant.py — 租户解析中间件。

在 before_request 中解析当前请求的租户上下文，注入 g.tenant_id。

优先级：
1. X-Tenant-ID header（API 调用显式指定）
2. JWT token 中的 tenant_id（已认证用户）
3. 不设置（公开端点或无租户上下文）
"""

from flask import g, request
from models.base import SessionLocal
from models.tenant import Tenant


def resolve_tenant():
    """解析请求的租户上下文，注入 g.tenant_id。"""
    # 1. 检查 X-Tenant-ID header
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        try:
            g.tenant_id = int(tenant_id)
        except (ValueError, TypeError):
            pass

    # 2. 从 JWT token 提取（已在 require_auth 中间件中设置 g.current_user）
    if not hasattr(g, "tenant_id") and hasattr(g, "current_user"):
        tid = g.current_user.get("tenant_id")
        if tid is not None:
            g.tenant_id = tid

    # 3. 如果仍未设置，尝试默认租户（开发/单租户模式）
    if not hasattr(g, "tenant_id"):
        try:
            db = SessionLocal()
            default_tenant = db.query(Tenant).filter_by(is_active=True).first()
            if default_tenant:
                g.tenant_id = default_tenant.id
            db.close()
        except Exception:
            pass
