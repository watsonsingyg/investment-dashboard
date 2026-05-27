"""
reporter/services/excel_import.py — Excel 导入辅助。

从 Excel 文件导入项目到数据库（合并/覆盖模式）。
自动加入当前租户上下文。
"""

from typing import Optional
from flask import g
from sqlalchemy.orm import Session
from models.project import Project
from models.weekly_entry import WeeklyEntry
from reporter.dashboard_data import parse_excel
from reporter.summary_cache import clean_text


def _tenant_id() -> Optional[int]:
    """获取当前请求的 tenant_id。"""
    return getattr(g, "tenant_id", None)


def import_from_excel(
    db: Session,
    excel_path: str,
    mode: str = "merge",
) -> dict:
    """
    从 Excel 导入项目到数据库。

    Args:
        db: 数据库会话
        excel_path: Excel 文件路径
        mode: "merge" - 新增项目，已有跳过；"overwrite" - 覆盖已有项目数据

    Returns:
        {created, updated, skipped, total}
    """
    tid = _tenant_id()
    data = parse_excel(excel_path)
    projects_raw = data.get("projects", [])

    created = 0
    updated = 0
    skipped = 0

    for p_data in projects_raw:
        name = (p_data.get("name") or "").strip()
        if not name or name == "-":
            skipped += 1
            continue

        query = db.query(Project).filter(Project.name == name)
        if tid is not None:
            query = query.filter(Project.tenant_id == tid)
        existing = query.first()

        if existing and mode == "merge":
            skipped += 1
            continue

        if existing and mode == "overwrite":
            # 删旧周报
            db.query(WeeklyEntry).filter(WeeklyEntry.project_id == existing.id).delete()
            db.flush()
        else:
            existing = Project(tenant_id=tid, name=name)
            db.add(existing)
            db.flush()
            created += 1

        # 更新字段
        existing.biz_scope = p_data.get("biz_scope", "")
        existing.industry = p_data.get("industry", "")
        existing.category = p_data.get("category", "")
        existing.owner = p_data.get("owner", "")
        existing.status = p_data.get("status", "")
        existing.priority = p_data.get("priority", "")
        existing.score = str(p_data.get("score", "") or "")
        existing.is_ai = p_data.get("is_ai", False)
        existing.last_active = p_data.get("last_active", "")
        existing.first_active = p_data.get("first_active", "")
        existing.latest_content = p_data.get("latest_content", "")
        existing.latest_label = p_data.get("latest_label", "")

        # 导入周报
        for week, content in p_data.get("weekly", {}).items():
            content_val = (content or "").strip()
            if content_val:
                entry = WeeklyEntry(
                    tenant_id=tid,
                    project_id=existing.id,
                    week=week,
                    content=content_val,
                    short=clean_text(content_val)[:100] if clean_text else "",
                )
                db.add(entry)

        if mode == "overwrite":
            updated += 1

    db.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total": len(projects_raw),
    }
