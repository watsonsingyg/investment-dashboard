"""
reporter/blueprints/admin.py — 管理员 API。

用户列表、角色修改、创建用户、重置密码。
所有端点仅 admin 可访问，用户管理限定当前租户范围。
"""

from datetime import datetime
from flask import Blueprint, request, g, jsonify, render_template
from reporter.middleware.auth import require_auth, require_role
from reporter.jwt_utils import hash_password
from models.user import User, UserRole

admin_bp = Blueprint("admin", __name__)

# ═══════════════════════════════════════════════════════════════════════════
# 页面
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/admin/users")
@require_auth
@require_role("admin")
def users_page():
    return render_template("admin_users.html",
        auth_required=True,
        show_navbar=True,
        nav_full=False,
        active_page="admin",
        show_scripts=True,
        body_class="",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 用户列表（限定当前租户）
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/api/admin/users")
@require_auth
@require_role("admin")
def list_users():
    tid = g.current_user.get("tenant_id")
    query = g.db.query(User)
    if tid is not None:
        query = query.filter(User.tenant_id == tid)
    users = query.order_by(User.created_at).all()
    return jsonify([
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role,
            "is_active": u.is_active,
            "tenant_id": u.tenant_id,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ])


# ═══════════════════════════════════════════════════════════════════════════
# 更新用户
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_user(user_id):
    body = request.get_json() or {}
    tid = g.current_user.get("tenant_id")

    query = g.db.query(User).filter_by(id=user_id)
    if tid is not None:
        query = query.filter(User.tenant_id == tid)
    user = query.first()

    if not user:
        return jsonify({"error": "用户不存在"}), 404

    my_id = g.current_user["user_id"]
    changes = []

    # 角色更新
    new_role = (body.get("role") or "").strip()
    if new_role and new_role in ("admin", "member", "viewer"):
        if user_id == my_id and new_role != "admin":
            return jsonify({"error": "不能修改自己的管理员角色"}), 403
        if user.role != new_role:
            user.role = new_role
            changes.append(f"角色 → {new_role}")

    # 启用/禁用
    if "is_active" in body:
        if user_id == my_id and not body["is_active"]:
            return jsonify({"error": "不能禁用自己"}), 403
        user.is_active = bool(body["is_active"])
        changes.append("状态 → " + ("启用" if body["is_active"] else "禁用"))

    # 重置密码
    new_password = (body.get("reset_password") or "").strip()
    if new_password:
        if len(new_password) < 6:
            return jsonify({"error": "密码至少 6 位"}), 400
        user.password_hash = hash_password(new_password)
        changes.append("密码已重置")

    if changes:
        g.db.commit()

    return jsonify({
        "ok": True,
        "user_id": user.id,
        "changes": changes,
    })


# ═══════════════════════════════════════════════════════════════════════════
# 创建用户（绑定当前租户）
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/api/admin/users", methods=["POST"])
@require_auth
@require_role("admin")
def create_user():
    body = request.get_json() or {}
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    role = (body.get("role") or "member").strip()
    tid = g.current_user.get("tenant_id")

    errors = []
    if not email or "@" not in email:
        errors.append("请输入有效的邮箱地址")
    if len(password) < 6:
        errors.append("密码至少 6 位")
    if role not in ("admin", "member", "viewer"):
        errors.append("角色无效")
    if g.db.query(User).filter_by(email=email).first():
        errors.append("该邮箱已被使用")
    if errors:
        return jsonify({"error": "；".join(errors)}), 400

    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name or email.split("@")[0],
        role=role,
        tenant_id=tid,
    )
    g.db.add(user)
    g.db.commit()

    return jsonify({
        "ok": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "tenant_id": user.tenant_id,
        },
    }), 201
