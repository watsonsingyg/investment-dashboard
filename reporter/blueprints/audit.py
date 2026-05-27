"""
reporter/blueprints/audit.py — 变更审计 API。
"""

from flask import Blueprint, request, g, jsonify
from reporter.middleware.auth import require_auth
from models.field_diff import FieldDiff
from models.operation_log import OperationLog
from models.project import Project

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/api/audit/project/<path:project>")
@require_auth
def api_project_audit(project):
    try:
        proj = (
            g.db.query(Project)
            .filter(Project.name == project)
            .first()
        )
        pid = proj.id if proj else None

        diffs = (
            g.db.query(FieldDiff)
            .filter(FieldDiff.project_id == pid)
            .order_by(FieldDiff.ts.desc())
            .limit(20)
            .all()
        )
        operations = (
            g.db.query(OperationLog)
            .filter(OperationLog.project == project)
            .order_by(OperationLog.ts.desc())
            .limit(20)
            .all()
        )

        return jsonify({
            "project": project.strip(),
            "diffs": [
                {
                    "ts": d.ts.isoformat() if d.ts else "",
                    "field": d.field,
                    "old_value": d.old_value,
                    "new_value": d.new_value,
                    "week": d.week,
                }
                for d in diffs
            ],
            "operations": [
                {
                    "ts": o.ts.isoformat() if o.ts else "",
                    "event": o.event,
                    "details": o.details,
                }
                for o in operations
            ],
        })
    except Exception as e:
        return jsonify({"error": f"读取变更记录失败：{e}"}), 500


@audit_bp.route("/api/audit/recent")
@require_auth
def api_recent_audit():
    try:
        diffs = (
            g.db.query(FieldDiff)
            
            .order_by(FieldDiff.ts.desc())
            .limit(30)
            .all()
        )
        operations = (
            g.db.query(OperationLog)
            
            .order_by(OperationLog.ts.desc())
            .limit(30)
            .all()
        )

        return jsonify({
            "diffs": [
                {
                    "ts": d.ts.isoformat() if d.ts else "",
                    "field": d.field,
                    "old_value": d.old_value,
                    "new_value": d.new_value,
                    "week": d.week,
                }
                for d in diffs
            ],
            "operations": [
                {
                    "ts": o.ts.isoformat() if o.ts else "",
                    "event": o.event,
                    "project": o.project,
                }
                for o in operations
            ],
        })
    except Exception as e:
        return jsonify({"error": f"读取变更记录失败：{e}"}), 500
