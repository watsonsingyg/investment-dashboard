"""
reporter/blueprints/dashboard.py — Dashboard 数据 API。
"""

from flask import Blueprint, g, jsonify
from reporter.middleware.auth import require_auth
from reporter.services.dashboard_service import load_dashboard_payload

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/dashboard-data")
@require_auth
def api_dashboard_data():
    """Dashboard 聚合数据（含评分分布、行业分类、漏斗图）
    ---
    tags: [看板]
    security: [{Bearer: []}]
    responses:
      200:
        description: 看板数据（60秒 TTL 缓存）
        schema:
          type: object
          properties:
            meta: {type: object}
            metrics:
              type: object
              properties:
                total: {type: integer}
                ai_pct: {type: number}
                avg_score: {type: number}
            projects: {type: array}
            counts:
              type: object
              properties:
                status: {type: object}
                category: {type: object}
                scores: {type: object}
    """
    try:
        payload = load_dashboard_payload(g.db)
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": f"读取看板数据失败：{e}"}), 500
