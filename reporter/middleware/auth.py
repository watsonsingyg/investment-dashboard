"""
reporter/middleware/auth.py — JWT 认证装饰器。

替代原有的 session-based login_required。所有 API 路由用 @require_auth 装饰。
从 JWT payload 中提取 user_id、tenant_id、role 注入 g.current_user。

用法:
    from reporter.middleware import require_auth, require_role

    @app.route('/api/projects')
    @require_auth
    def api_projects(): ...

    @app.route('/api/admin/users')
    @require_auth
    @require_role('admin')
    def admin_route(): ...
"""

from functools import wraps
from flask import g, request, jsonify, redirect, url_for
from reporter.jwt_utils import decode_token
from jose import JWTError


def _is_browser_request():
    """判断是否为浏览器页面请求（非 API 路径）。"""
    return not request.path.startswith("/api/")


def _auth_fail(msg, status=401):
    """认证失败：浏览器请求跳转登录，API 请求返回 JSON。"""
    if _is_browser_request():
        return redirect("/login")
    return jsonify({"error": msg}), status


def get_bearer_token():
    """从 Authorization header 或 cookie 提取 Bearer token。"""
    # 优先 Bearer header（API 调用）
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    # 其次 cookie（浏览器页面导航）
    cookie_token = request.cookies.get("pipeline_token", "")
    if cookie_token:
        return cookie_token
    return None


def require_auth(f):
    """JWT 认证装饰器：从 Bearer token 验证用户身份，注入 g.current_user（含 tenant_id）。"""

    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_bearer_token()
        if not token:
            return _auth_fail("未提供认证令牌")

        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                return _auth_fail("令牌类型无效")
            g.current_user = {
                "user_id": int(payload["sub"]),
                "tenant_id": payload.get("tenant_id"),
                "role": payload.get("role", "member"),
            }
        except JWTError:
            return _auth_fail("令牌无效或已过期")
        except Exception:
            return _auth_fail("认证失败")

        return f(*args, **kwargs)

    return wrapper


def require_role(*roles):
    """角色权限装饰器：检查 g.current_user 的角色是否在允许列表中。"""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not hasattr(g, "current_user") or g.current_user["role"] not in roles:
                return jsonify({"error": "权限不足"}), 403
            return f(*args, **kwargs)

        return wrapper

    return decorator


def optional_auth(f):
    """可选的认证装饰器：有 token 则解析（含 tenant_id），没有也放行。"""

    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_bearer_token()
        if token:
            try:
                payload = decode_token(token)
                g.current_user = {
                    "user_id": int(payload["sub"]),
                    "tenant_id": payload.get("tenant_id"),
                    "role": payload.get("role", "member"),
                }
            except Exception:
                pass
        return f(*args, **kwargs)

    return wrapper
