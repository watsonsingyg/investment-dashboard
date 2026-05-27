"""
reporter/blueprints/system.py — 系统状态 API（健康检查、服务器日志等）。
"""

import os
from datetime import datetime
from flask import Blueprint, request, g, jsonify
from reporter.middleware.auth import require_auth
from config import settings

system_bp = Blueprint("system", __name__)

APP_STARTED_AT = datetime.now()


@system_bp.route("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "app": "pipeline-saas",
        "pid": os.getpid(),
        "started_at": APP_STARTED_AT.strftime("%Y-%m-%d %H:%M:%S"),
        "model": settings.DEEPSEEK_MODEL,
    })


@system_bp.route("/api/system-status")
@require_auth
def api_system_status():
    up = int((datetime.now() - APP_STARTED_AT).total_seconds())
    return jsonify({
        "ok": True,
        "app": "pipeline-saas",
        "pid": os.getpid(),
        "started_at": APP_STARTED_AT.strftime("%Y-%m-%d %H:%M:%S"),
        "uptime_seconds": up,
        "model": settings.DEEPSEEK_MODEL,
        "port": settings.APP_PORT,
        "database": settings.DATABASE_URL.split("://")[0],
    })


@system_bp.route("/api/server-log")
@require_auth
def api_server_log():
    try:
        lines = max(20, min(int(request.args.get("lines", 200) or 200), 500))
    except ValueError:
        lines = 200
    log_path = settings.SERVER_LOG
    if not log_path.exists():
        return jsonify({"path": str(log_path), "lines": []})
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return jsonify({"path": str(log_path), "lines": content[-lines:]})
    except Exception as e:
        return jsonify({"error": f"读取服务日志失败：{e}"}), 500
