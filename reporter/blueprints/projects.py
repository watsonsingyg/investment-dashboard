"""
reporter/blueprints/projects.py — 项目 CRUD API（含分页）。
"""

from flask import Blueprint, request, g, jsonify
from reporter.middleware.auth import require_auth
from reporter.services.project_service import (
    get_projects, get_projects_paginated, get_project_detail,
    update_project_fields, update_week_content, get_field_options,
    get_existing_week_content, delete_project,
)
from reporter.errors import bad_request, not_found, server_error

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("/api/projects")
@require_auth
def api_projects():
    """获取项目列表（支持分页和搜索）
    ---
    tags: [项目]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: page
        type: integer
        description: 页码（默认1）
      - in: query
        name: per_page
        type: integer
        description: 每页数量（默认50，提供此参数启用分页）
      - in: query
        name: search
        type: string
        description: 项目名称关键词搜索
    responses:
      200:
        description: 项目列表（无分页参数时返回数组，有分页时返回 {projects, meta}）
    """
    """获取项目列表。支持分页参数 ?page=N&per_page=N&search=keyword。"""
    try:
        page = request.args.get("page", type=int)
        per_page = request.args.get("per_page", type=int)
        search = (request.args.get("search") or "").strip()

        if page is not None or per_page is not None or search:
            # 分页/搜索模式
            result = get_projects_paginated(
                g.db,
                page=page or 1,
                per_page=per_page or 50,
                search=search,
            )
            return jsonify(result)
        else:
            # 兼容旧版：返回全部项目名称列表
            return jsonify(get_projects(g.db))
    except Exception as e:
        return server_error(f"读取项目列表失败：{e}")


@projects_bp.route("/api/field-options")
@require_auth
def api_field_options():
    try:
        return jsonify(get_field_options(g.db))
    except Exception as e:
        return server_error(f"读取字段选项失败：{e}")


@projects_bp.route("/api/projects/<path:project>", methods=["GET"])
@require_auth
def api_project_detail(project):
    try:
        return jsonify(get_project_detail(g.db, project))
    except KeyError as e:
        return not_found(str(e))
    except Exception as e:
        return server_error(f"读取项目失败：{e}")


@projects_bp.route("/api/projects/<path:project>", methods=["PATCH"])
@require_auth
def api_project_patch(project):
    body = request.get_json() or {}
    try:
        result = update_project_fields(
            g.db, project, body,
            user_id=g.current_user.get("user_id"),
        )
        return jsonify(result)
    except KeyError as e:
        return not_found(str(e))
    except Exception as e:
        return server_error(f"更新项目失败：{e}")


@projects_bp.route("/api/projects/<path:project>", methods=["DELETE"])
@require_auth
def api_project_delete(project):
    try:
        result = delete_project(g.db, project)
        return jsonify(result)
    except KeyError as e:
        return not_found(str(e))
    except Exception as e:
        return server_error(f"删除项目失败：{e}")


@projects_bp.route("/api/projects/<path:project>/week/<path:week>", methods=["PATCH"])
@require_auth
def api_project_week_patch(project, week):
    body = request.get_json() or {}
    content = (body.get("content") or "").strip()
    if not content:
        return bad_request("内容不能为空")
    try:
        result = update_week_content(
            g.db, project, week, content,
            user_id=g.current_user.get("user_id"),
        )
        return jsonify({"ok": True, **result})
    except KeyError as e:
        return not_found(str(e))
    except Exception as e:
        return server_error(f"更新周报内容失败：{e}")
