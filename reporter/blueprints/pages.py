"""
reporter/blueprints/pages.py — HTML 页面路由。

使用 Jinja2 render_template，所有页面共享 _base.html 布局。
"""
from flask import Blueprint, Response, redirect, request, render_template
from reporter.middleware.auth import require_auth
from models.project import Project

pages_bp = Blueprint("pages", __name__)

# ── 共享模板变量 ─────────────────────────────────────────────────

def _auth_ctx():
    """返回认证页面的共享上下文。"""
    return dict(
        auth_required=False,
        show_navbar=False,
        show_scripts=False,
        body_class="",
    )

def _app_ctx(active_page, nav_full=True, show_admin_link=False):
    """返回应用内页面的共享上下文。"""
    return dict(
        auth_required=True,
        show_navbar=True,
        nav_full=nav_full,
        active_page=active_page,
        show_admin_link=show_admin_link,
        show_scripts=True,
        body_class="",
    )


# ═══════════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════════

@pages_bp.route("/")
@require_auth
def portal():
    from config import settings
    from reporter.services.ai_config_service import get_ai_config
    try:
        count = g.db.query(Project).filter(Project.deleted_at.is_(None)).count()
    except Exception:
        count = 0

    config = get_ai_config(g.db)
    model_display = config.get("model") or settings.DEEPSEEK_MODEL
    ai_configured = "true" if config.get("is_configured") else "false"

    return render_template("portal.html",
        **_app_ctx("portal", show_admin_link=True),
        project_count=count,
        last_updated="—",
        generation_model=model_display,
        ai_configured=ai_configured,
    )


@pages_bp.route("/status")
@require_auth
def status_page():
    return render_template("status.html", **_app_ctx("status"))


@pages_bp.route("/dashboard")
@require_auth
def dashboard():
    return render_template("dashboard.html", **_app_ctx("dashboard"))


@pages_bp.route("/reporter")
@require_auth
def reporter_page():
    from config import settings
    from reporter.services.ai_config_service import get_ai_config
    config = get_ai_config(g.db)
    model_display = config.get("model") or settings.DEEPSEEK_MODEL
    return render_template("reporter.html",
        **_app_ctx("reporter"),
        generation_model=model_display,
    )


@pages_bp.route("/governance")
@require_auth
def governance_page():
    return render_template("governance.html", **_app_ctx("governance"))


@pages_bp.route("/login")
def login_page():
    return render_template("login.html", **_auth_ctx())


@pages_bp.route("/register")
def register_page():
    return render_template("register.html", **_auth_ctx())


@pages_bp.route("/logout")
def logout_page():
    """退出登录：清除 cookie 并重定向到登录页。"""
    resp = redirect("/login")
    resp.delete_cookie("pipeline_token")
    return resp


# ═══════════════════════════════════════════════════════════════════
# 错误处理
# ═══════════════════════════════════════════════════════════════════

@pages_bp.app_errorhandler(404)
def not_found(e):
    """全局 404：API 返回 JSON，页面返回 HTML。"""
    if request.path.startswith("/api/"):
        from flask import jsonify
        return jsonify({"error": "Not found"}), 404
    return render_template("404.html", **_auth_ctx()), 404


# 需要 g 对象
from flask import g
