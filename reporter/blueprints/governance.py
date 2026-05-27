"""
reporter/blueprints/governance.py — 数据治理 API。
"""

from flask import Blueprint, request, g, jsonify
from reporter.middleware.auth import require_auth
from reporter.services.governance_service import (
    load_governance_report, save_governance_issue_state,
)

governance_bp = Blueprint("governance", __name__)


@governance_bp.route("/api/governance-data")
@require_auth
def api_governance_data():
    try:
        stale = int(request.args.get("stale_weeks", 8))
    except ValueError:
        stale = 8
    try:
        report = load_governance_report(g.db, stale_weeks=stale)
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": f"读取健康检查失败：{e}"}), 500


@governance_bp.route("/api/governance/issue-state", methods=["POST"])
@require_auth
def api_governance_issue_state():
    body = request.get_json() or {}
    try:
        result = save_governance_issue_state(
            g.db, issue_key=body.get("issue_key", ""),
            state=body.get("state", "active"),
            note=body.get("note", ""),
            days=body.get("days", 30),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"更新问题状态失败：{e}"}), 400
