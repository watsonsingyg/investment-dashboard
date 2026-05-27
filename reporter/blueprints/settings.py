"""
reporter/blueprints/settings.py — 系统设置蓝图。

提供: AI 配置读取/保存，连接测试。
"""

from flask import Blueprint, request, g, jsonify, render_template
from reporter.middleware.auth import require_auth
from reporter.services.ai_config_service import get_ai_config, save_ai_config
from reporter.services.ai_provider import test_provider_connection
from reporter.errors import server_error

settings_bp = Blueprint("settings", __name__)


# ═══════════════════════════════════════════════════════════════════════════
# 页面
# ═══════════════════════════════════════════════════════════════════════════

@settings_bp.route("/settings")
@require_auth
def settings_page():
    return render_template("settings.html",
        auth_required=True,
        show_navbar=True,
        nav_full=False,
        active_page="settings",
        show_scripts=True,
        body_class="",
    )


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════

@settings_bp.route("/api/settings/ai-config", methods=["GET"])
@require_auth
def api_get_ai_config():
    config = get_ai_config(g.db)
    api_key_raw = config.get("api_key", "")
    return jsonify({
        "provider": config.get("provider", "deepseek"),
        "api_key_masked": (
            api_key_raw[:4] + "****" + api_key_raw[-4:]
            if len(api_key_raw) > 8 else ("****" if api_key_raw else "")
        ),
        "api_base_url": config.get("api_base_url", ""),
        "model": config.get("model", ""),
        "tavily_api_key": "****" if config.get("tavily_api_key") else "",
        "is_configured": config.get("is_configured", False),
    })


@settings_bp.route("/api/settings/ai-config", methods=["POST"])
@require_auth
def api_save_ai_config():
    provider = (request.form.get("provider") or "").strip()
    api_key = (request.form.get("api_key") or "").strip()
    api_base_url = (request.form.get("api_base_url") or "").strip()
    model = (request.form.get("model") or "").strip()
    tavily_api_key = (request.form.get("tavily_api_key") or "").strip()

    if not api_key:
        return jsonify({"error": "请提供 API Key"}), 400

    try:
        result = save_ai_config(g.db, provider, api_key, api_base_url, model, tavily_api_key)
        return jsonify({"ok": True, "config": result})
    except Exception as e:
        return jsonify({"error": f"保存失败：{e}"}), 500


@settings_bp.route("/api/settings/test-connection", methods=["POST"])
@require_auth
def api_test_connection():
    try:
        result = test_provider_connection(g.db)
        return jsonify(result)
    except Exception as e:
        return server_error(f"连接测试失败：{e}")
