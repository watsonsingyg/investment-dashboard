"""
reporter/blueprints/export.py — 导出 API（CSV / Markdown）。
"""

from flask import Blueprint, request, g, jsonify, Response
from reporter.middleware.auth import require_auth
from reporter.services.dashboard_service import load_dashboard_payload
from reporter.export_service import (
    export_projects_csv, export_project_markdown, export_weekly_markdown,
)

export_bp = Blueprint("export", __name__)


@export_bp.route("/api/export/projects.csv")
@require_auth
def api_export_projects_csv():
    try:
        payload = load_dashboard_payload(g.db)
        body = export_projects_csv(payload, request.args)
        return Response(
            "\ufeff" + body,
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="projects.csv"'},
        )
    except Exception as e:
        return jsonify({"error": f"导出失败：{e}"}), 500


@export_bp.route("/api/export/project/<path:project>.md")
@require_auth
def api_export_project_md(project):
    try:
        payload = load_dashboard_payload(g.db)
        body = export_project_markdown(payload, project)
        return Response(
            body,
            content_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{project}.md"'},
        )
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"导出失败：{e}"}), 500


@export_bp.route("/api/export/weekly.md")
@require_auth
def api_export_weekly_md():
    try:
        payload = load_dashboard_payload(g.db)
        week = request.args.get("week", "").strip() or payload["meta"]["latest_week"]
        body = export_weekly_markdown(payload, week)
        return Response(
            body,
            content_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="weekly-{week[:10]}.md"'},
        )
    except Exception as e:
        return jsonify({"error": f"导出失败：{e}"}), 500
