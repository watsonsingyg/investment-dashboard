"""
reporter/services/project_service.py — 项目核心 CRUD 服务。

替代 excel_store.py 的 Excel 操作，所有查询自动带 tenant_id 隔离。
"""

import json
from datetime import datetime
from typing import Optional, List
from flask import g
from sqlalchemy.orm import Session
from models.project import Project
from models.weekly_entry import WeeklyEntry
from models.field_diff import FieldDiff
from models.operation_log import OperationLog
from reporter.statuses import FUNNEL_STAGES, PRIORITY_ORDER, SCORE_DISPLAY_ORDER, SCORE_LABELS
from reporter.services.dashboard_service import invalidate_dashboard_cache


def _tenant_id() -> Optional[int]:
    """获取当前请求的 tenant_id。"""
    return getattr(g, "tenant_id", None)


def get_projects(db: Session) -> List[dict]:
    """获取当前租户下所有未删除的项目（仅名称列表，兼容旧 API 格式）。"""
    tid = _tenant_id()
    query = db.query(Project).filter(Project.deleted_at.is_(None))
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    rows = query.order_by(Project.updated_at.desc()).all()
    return [r.name for r in rows]


def get_projects_paginated(db: Session, page: int = 1, per_page: int = 50, search: str = "") -> dict:
    """分页获取项目名称列表（含搜索）。返回分页元数据。"""
    tid = _tenant_id()
    query = db.query(Project).filter(Project.deleted_at.is_(None))
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)

    # 搜索（项目名称模糊匹配）
    if search:
        query = query.filter(Project.name.contains(search))

    # 总数
    total = query.count()

    # 分页
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    offset = (page - 1) * per_page

    rows = query.order_by(Project.updated_at.desc()).offset(offset).limit(per_page).all()

    return {
        "projects": [r.name for r in rows],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
        },
    }


def get_project_detail(db: Session, project_name: str) -> dict:
    """获取单个项目的完整信息（含周报），自动限定当前租户。"""
    tid = _tenant_id()
    query = db.query(Project).filter(
        Project.name == project_name,
        Project.deleted_at.is_(None),
    )
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    project = query.first()

    if not project:
        raise KeyError(f"项目不存在: {project_name}")

    entries = (
        db.query(WeeklyEntry)
        .filter(WeeklyEntry.project_id == project.id)
        .order_by(WeeklyEntry.week.desc())
        .all()
    )

    return {
        "name": project.name,
        "biz_scope": project.biz_scope or "",
        "industry": project.industry or "",
        "category": project.category or "",
        "owner": project.owner or "",
        "status": project.status or "",
        "status_raw": project.status_raw or "",
        "priority": project.priority or "",
        "score": project.score or "",
        "is_ai": project.is_ai,
        "last_active": project.last_active or "",
        "first_active": project.first_active or "",
        "latest_content": project.latest_content or "",
        "latest_label": project.latest_label or "",
        "weekly": {e.week: e.content or "" for e in entries},
    }


def update_project_fields(
    db: Session, project_name: str,
    fields: dict, user_id: Optional[int] = None,
) -> dict:
    """更新项目字段（不存在则创建），记录变更到 field_diffs。自动加入当前租户。"""
    tid = _tenant_id()

    query = db.query(Project).filter(
        Project.name == project_name,
        Project.deleted_at.is_(None),
    )
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    project = query.first()

    is_new = False
    if not project:
        # 检查是否为软删除项目（恢复而非新建，避免唯一约束冲突）
        deleted_query = db.query(Project).filter(Project.name == project_name)
        if tid is not None:
            deleted_query = deleted_query.filter(Project.tenant_id == tid)
        deleted = deleted_query.first()
        if deleted and deleted.deleted_at:
            # 恢复软删除的项目
            project = deleted
            project.deleted_at = None
            is_new = True
        else:
            project = Project(name=project_name, tenant_id=tid)
            db.add(project)
            db.flush()
            is_new = True

    changes = []
    field_map = {
        "status": "status",
        "priority": "priority",
        "score": "score",
        "owner": "owner",
        "biz_scope": "biz_scope",
        "industry": "industry",
        "stage": "status",
        "status_raw": "status_raw",
    }

    for key, value in fields.items():
        col = field_map.get(key.lower(), key.lower())
        if hasattr(project, col):
            old_val = getattr(project, col) or ""
            new_val = str(value) if value is not None else ""
            if old_val != new_val:
                setattr(project, col, new_val)
                changes.append({
                    "field": key,
                    "old": old_val,
                    "new": new_val,
                })

    if changes or is_new:
        project.updated_at = datetime.utcnow()
        if is_new and not changes:
            db.commit()
            invalidate_dashboard_cache()

        # 记录变更
        for c in changes:
            diff = FieldDiff(
                tenant_id=tid,
                project_id=project.id,
                changed_by=user_id,
                field=c["field"],
                old_value=c["old"],
                new_value=c["new"],
            )
            db.add(diff)
        db.commit()
        invalidate_dashboard_cache()

    return {"project": project.name, "changes": changes, "is_new": is_new}


def update_week_content(
    db: Session, project_name: str,
    week: str, content: str, user_id: Optional[int] = None,
) -> dict:
    """更新/创建周报内容，自动限定当前租户。"""
    tid = _tenant_id()
    query = db.query(Project).filter(
        Project.name == project_name,
        Project.deleted_at.is_(None),
    )
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    project = query.first()

    if not project:
        raise KeyError(f"项目不存在: {project_name}")

    entry = (
        db.query(WeeklyEntry)
        .filter(WeeklyEntry.project_id == project.id, WeeklyEntry.week == week)
        .first()
    )

    old_content = entry.content if entry else ""

    if entry:
        entry.content = content
        entry.updated_at = datetime.utcnow()
    else:
        entry = WeeklyEntry(
            tenant_id=tid,
            project_id=project.id,
            week=week,
            content=content,
        )
        db.add(entry)

    # 更新项目最后活跃信息
    project.latest_content = content
    project.last_active = week
    project.latest_label = week
    project.updated_at = datetime.utcnow()

    db.commit()
    invalidate_dashboard_cache()

    # 记录变更
    diff = FieldDiff(
        tenant_id=tid,
        project_id=project.id,
        changed_by=user_id,
        field="weekly_content",
        old_value=old_content,
        new_value=content,
        week=week,
    )
    db.add(diff)
    db.commit()
    invalidate_dashboard_cache()

    return {
        "project": project.name,
        "week": week,
        "old_content": old_content,
        "new_content": content,
    }


def push_weekly_content(
    db: Session, project_name: str,
    week: str, content: str, stage: str = "",
    category: str = "", biz_scope: str = "",
    score: str = "", user_id: Optional[int] = None,
) -> dict:
    """推送周报内容（可能创建新项目），自动加入当前租户。"""
    tid = _tenant_id()

    # 查找或创建项目
    query = db.query(Project).filter(Project.name == project_name)
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    project = query.first()

    is_new = False
    old_content = ""

    if not project:
        project = Project(
            tenant_id=tid,
            name=project_name,
            category=category or "",
            biz_scope=biz_scope or "",
            status=stage or "",
        )
        db.add(project)
        db.flush()
        is_new = True
    elif project.deleted_at:
        # 恢复已删除的项目
        project.deleted_at = None
        is_new = True

    # 更新字段
    if stage:
        project.status = stage
    if category:
        project.category = category
    if biz_scope:
        project.biz_scope = biz_scope
    if score:
        project.score = score

    # 查找已有周报
    entry = (
        db.query(WeeklyEntry)
        .filter(WeeklyEntry.project_id == project.id, WeeklyEntry.week == week)
        .first()
    )
    if entry:
        old_content = entry.content or ""
        entry.content = content
        entry.updated_at = datetime.utcnow()
    else:
        entry = WeeklyEntry(
            tenant_id=tid,
            project_id=project.id,
            week=week,
            content=content,
        )
        db.add(entry)

    project.latest_content = content
    project.last_active = week
    project.latest_label = week
    project.updated_at = datetime.utcnow()

    db.commit()
    invalidate_dashboard_cache()

    return {
        "project": project.name,
        "week": week,
        "is_new": is_new,
        "old_content": old_content,
        "new_content": content,
    }


def get_field_options(db: Session) -> dict:
    """获取字段下拉选项（去重），仅限当前租户。"""
    tid = _tenant_id()
    query = db.query(Project).filter(Project.deleted_at.is_(None))
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    projects = query.all()

    def unique(field):
        vals = {getattr(p, field, "") or "" for p in projects}
        return sorted([v for v in vals if v], key=lambda x: x.lower())

    return {
        "biz_scopes": unique("biz_scope"),
        "industries": unique("industry"),
        "owners": unique("owner"),
        "statuses": FUNNEL_STAGES,
        "priorities": PRIORITY_ORDER,
        "scores": [{"value": k, "label": SCORE_LABELS[k]} for k in SCORE_DISPLAY_ORDER],
    }


def get_existing_week_content(db: Session, project_name: str, week: str) -> dict:
    """检查指定项目/周次是否已有内容，自动限定当前租户。"""
    tid = _tenant_id()
    query = db.query(Project).filter(Project.name == project_name)
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    project = query.first()

    if not project:
        return {"exists": False, "content": ""}

    entry = (
        db.query(WeeklyEntry)
        .filter(WeeklyEntry.project_id == project.id, WeeklyEntry.week == week)
        .first()
    )
    if entry:
        return {"exists": True, "content": entry.content or ""}
    return {"exists": False, "content": ""}


def delete_project(db: Session, project_name: str) -> dict:
    """软删除项目，自动限定当前租户。"""
    tid = _tenant_id()
    query = db.query(Project).filter(
        Project.name == project_name,
        Project.deleted_at.is_(None),
    )
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    project = query.first()

    if not project:
        raise KeyError(f"项目不存在: {project_name}")

    project.deleted_at = datetime.utcnow()
    db.commit()
    invalidate_dashboard_cache()
    return {"project": project.name, "deleted": True}
