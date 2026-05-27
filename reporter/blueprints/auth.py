"""
reporter/blueprints/auth.py — 认证 Blueprint。

提供: register, login, refresh, me, logout
JWT token 中包含 tenant_id，实现多租户隔离。
"""

import json
from datetime import datetime
from flask import Blueprint, request, g, jsonify, make_response
from models.base import SessionLocal
from models.tenant import Tenant
from models.user import User, UserRole
from models.ai_config import AIConfig
from reporter.jwt_utils import (
    create_access_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from reporter.middleware.auth import require_auth
from reporter.middleware.rate_limit import limiter, auth_limit
from config import settings

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _json(data, status=200):
    """构建 JSON 响应。"""
    return jsonify(data), status


def _get_or_create_default_tenant(db) -> Tenant:
    """获取或创建默认租户（开发/单租户模式）。"""
    from config import settings
    tenant = db.query(Tenant).filter_by(is_active=True).first()
    if not tenant:
        import hashlib
        slug = "default"
        name = settings.DEFAULT_TENANT_NAME if hasattr(settings, 'DEFAULT_TENANT_NAME') else "默认租户"
        # 确保 slug 唯一
        base_slug = slug
        counter = 1
        while db.query(Tenant).filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        tenant = Tenant(name=name, slug=slug)
        db.add(tenant)
        db.flush()
        db.commit()
    return tenant


# ═══════════════════════════════════════════════════════════════════════════
# 注册
# ═══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/register", methods=["POST"])
@auth_limit
def register():
    """注册新用户（自动绑定默认租户）
    ---
    tags: [认证]
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required: [email, password]
          properties:
            email: {type: string, example: "user@example.com"}
            password: {type: string, example: "password123"}
            display_name: {type: string, example: "张三"}
    responses:
      201:
        description: 注册成功
        schema:
          type: object
          properties:
            ok: {type: boolean}
            access_token: {type: string}
            refresh_token: {type: string}
            user: {type: object}
            tenant: {type: object}
      400:
        description: 参数错误
      409:
        description: 邮箱已注册
    """
    body = request.get_json() or {}
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    display_name = (body.get("display_name") or "").strip()

    # 验证
    errors = []
    if not email or "@" not in email:
        errors.append("请输入有效的邮箱地址")
    if len(password) < 6:
        errors.append("密码至少 6 位")
    if errors:
        return _json({"error": "；".join(errors)}, 400)

    db = SessionLocal()
    try:
        # 检查邮箱是否已注册
        if db.query(User).filter_by(email=email).first():
            return _json({"error": "该邮箱已注册"}, 409)

        # 获取或创建默认租户
        tenant = _get_or_create_default_tenant(db)

        # 第一个用户为管理员
        user_count = db.query(User).filter_by(tenant_id=tenant.id).count()
        role = UserRole.ADMIN.value if user_count == 0 else UserRole.MEMBER.value

        # 创建用户
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name or email.split("@")[0],
            role=role,
            tenant_id=tenant.id,
        )
        db.add(user)
        db.flush()

        # 确保全局 AI 配置存在（单实例）
        if not db.query(AIConfig).first():
            ai_config = AIConfig()
            db.add(ai_config)

        db.commit()

        # 生成 token（含 tenant_id）
        access_token = create_access_token(user.id, user.role, user.tenant_id)
        refresh_token = create_refresh_token(user.id)

        resp = make_response(_json({
            "ok": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "tenant_id": user.tenant_id,
            },
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
            },
        }, 201))
        # 设置 cookie 以便浏览器页面导航可以带 token
        resp.set_cookie("pipeline_token", access_token,
                        httponly=False, samesite="Lax",
                        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        return resp

    except Exception as e:
        db.rollback()
        return _json({"error": f"注册失败：{e}"}, 500)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 登录
# ═══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/login", methods=["POST"])
@auth_limit
def login():
    """JWT 登录
    ---
    tags: [认证]
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required: [email, password]
          properties:
            email: {type: string, example: "user@example.com"}
            password: {type: string, example: "password123"}
    responses:
      200:
        description: 登录成功
        schema:
          type: object
          properties:
            ok: {type: boolean}
            access_token: {type: string}
            refresh_token: {type: string}
            user: {type: object}
            tenant: {type: object}
      401:
        description: 邮箱或密码错误
    """
    body = request.get_json() or {}
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    if not email or not password:
        return _json({"error": "请输入邮箱和密码"}, 400)

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if not user or not verify_password(password, user.password_hash):
            return _json({"error": "邮箱或密码错误"}, 401)

        if not user.is_active:
            return _json({"error": "账号已被禁用"}, 403)

        # 更新最后登录时间
        user.last_login_at = datetime.utcnow()
        db.commit()

        # 获取租户信息
        tenant_info = None
        if user.tenant_id:
            tenant = db.query(Tenant).filter_by(id=user.tenant_id).first()
            if tenant:
                tenant_info = {
                    "id": tenant.id,
                    "name": tenant.name,
                    "slug": tenant.slug,
                }

        access_token = create_access_token(user.id, user.role, user.tenant_id)
        refresh_token = create_refresh_token(user.id)

        resp = make_response(_json({
            "ok": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "tenant_id": user.tenant_id,
            },
            "tenant": tenant_info,
        }))
        resp.set_cookie("pipeline_token", access_token,
                        httponly=False, samesite="Lax",
                        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        return resp

    except Exception as e:
        db.rollback()
        return _json({"error": f"登录失败：{e}"}, 500)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 刷新 token
# ═══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/refresh", methods=["POST"])
@auth_limit
def refresh():
    body = request.get_json() or {}
    refresh_token = (body.get("refresh_token") or "").strip()

    if not refresh_token:
        return _json({"error": "请提供 refresh_token"}, 400)

    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            return _json({"error": "令牌类型无效"}, 401)

        user_id = int(payload["sub"])
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user or not user.is_active:
                return _json({"error": "用户不存在或已禁用"}, 401)

            new_access = create_access_token(user.id, user.role, user.tenant_id)
            new_refresh = create_refresh_token(user.id)

            resp = make_response(_json({
                "access_token": new_access,
                "refresh_token": new_refresh,
            }))
            resp.set_cookie("pipeline_token", new_access,
                            httponly=False, samesite="Lax",
                            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
            return resp
        finally:
            db.close()

    except Exception:
        return _json({"error": "refresh_token 无效或已过期"}, 401)


# ═══════════════════════════════════════════════════════════════════════════
# 当前用户信息
# ═══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/me")
@require_auth
def me():
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=g.current_user["user_id"]).first()
        if not user:
            return _json({"error": "用户不存在"}, 404)

        # 获取租户信息
        tenant_info = None
        if user.tenant_id:
            tenant = db.query(Tenant).filter_by(id=user.tenant_id).first()
            if tenant:
                tenant_info = {
                    "id": tenant.id,
                    "name": tenant.name,
                    "slug": tenant.slug,
                }

        return _json({
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "tenant_id": user.tenant_id,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            },
            "tenant": tenant_info,
        })
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 登出
# ═══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    # JWT 是无状态的，登出主要由客户端删除 token
    # Phase 2 可加 Redis 黑名单
    return _json({"ok": True, "message": "已登出"})
