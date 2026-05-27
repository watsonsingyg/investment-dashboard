"""
reporter/services/dashboard_service.py — Dashboard 数据聚合服务。

从数据库查询项目列表并组装为看板 JSON（兼容旧版前端格式）。
所有查询自动带 tenant_id 隔离。结果通过 reporter.cache 提供 60 秒 TTL。
"""

from datetime import datetime
from typing import Optional
from flask import g
from sqlalchemy.orm import Session
from models.project import Project
from models.weekly_entry import WeeklyEntry
from reporter.cache import cached, invalidate
from reporter.statuses import SCORE_DISPLAY_ORDER, SCORE_LABELS


def _tenant_id() -> Optional[int]:
    """获取当前请求的 tenant_id。"""
    return getattr(g, "tenant_id", None)


@cached(ttl_seconds=60)
def _build_dashboard_payload(tid: int, total_hint: int) -> dict:
    """内部：构建 dashboard payload（带缓存），tid 和 total_hint 作为缓存 key 的一部分。"""
    # total_hint 是用于缓存失效的占位 — 当项目数变化时缓存自动过期
    # 实际从 DB 重新查询
    db = g.db
    query = db.query(Project).filter(Project.deleted_at.is_(None))
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    projects = query.all()

    project_ids = [p.id for p in projects]
    entries = {}
    if project_ids:
        rows = (
            db.query(WeeklyEntry)
            .filter(WeeklyEntry.project_id.in_(project_ids))
            .order_by(WeeklyEntry.week.asc())
            .all()
        )
        for r in rows:
            entries.setdefault(r.project_id, {})[r.week] = r.content or ""

    all_weeks = set()
    for wmap in entries.values():
        all_weeks.update(wmap.keys())
    sorted_weeks = sorted(all_weeks, reverse=True)
    latest_week = sorted_weeks[0] if sorted_weeks else "—"
    oldest_week = sorted_weeks[-1] if sorted_weeks else "—"

    project_list = []
    for p in projects:
        weekly = entries.get(p.id, {})
        latest_content = ""
        latest_label = ""
        last_active = ""
        first_active = ""
        timeline = []

        for w in sorted(weekly.keys(), reverse=True):
            c = weekly[w]
            if c:
                if not latest_content:
                    latest_content = c
                    latest_label = w
                    last_active = w
                if not first_active:
                    first_active = w
                timeline.append({"week": w, "content": c})
            first_active = w

        is_active = latest_week in weekly and bool(weekly[latest_week])
        is_new = len(weekly) <= 1

        project_list.append({
            "name": p.name,
            "biz_scope": p.biz_scope or "",
            "industry": p.industry or "",
            "category": p.category or "",
            "owner": p.owner or "",
            "status": p.status or "",
            "status_raw": p.status_raw or "",
            "priority": p.priority or "",
            "score": p.score or "",
            "score_label": SCORE_LABELS.get(p.score or "", ""),
            "last_active": last_active or "",
            "last_active_iso": last_active or "",
            "latest_content": latest_content or "",
            "is_ai": p.is_ai,
            "is_active": is_active,
            "is_new": is_new,
            "first_active": first_active or "",
            "latest_label": latest_label or "",
            "weekly": weekly,
            "timeline": timeline,
        })

    total = len(project_list)
    ai_count = sum(1 for p in project_list if p["is_ai"])
    active_count = sum(1 for p in project_list if p["is_active"])
    new_count = sum(1 for p in project_list if p["is_new"])
    avg_score = 0.0
    scores = [int(p["score"]) for p in project_list if p["score"] and p["score"].isdigit()]
    if scores:
        avg_score = sum(scores) / len(scores)

    score_counts = {}
    for p in project_list:
        s = p.get("score", "") or "0"
        if s:
            score_counts[s] = score_counts.get(s, 0) + 1

    status_counts = {}
    for p in project_list:
        s = p["status"] or "未知"
        status_counts[s] = status_counts.get(s, 0) + 1

    category_counts = {}
    for p in project_list:
        c = p["category"] or "未分类"
        category_counts[c] = category_counts.get(c, 0) + 1

    priority_counts = {}
    for p in project_list:
        pr = p["priority"] or ""
        if pr:
            priority_counts[pr] = priority_counts.get(pr, 0) + 1

    dd_count = sum(1 for p in project_list if p["status"] not in ("前期沟通", "", "未知"))

    return {
        "meta": {
            "generated": datetime.utcnow().isoformat(),
            "latest_week": latest_week,
            "oldest_week": oldest_week,
            "total_projects": total,
            "source_file": "",
        },
        "metrics": {
            "total": total,
            "ai_count": ai_count,
            "non_ai": total - ai_count,
            "ai_pct": round(ai_count / total * 100, 1) if total else 0,
            "active_count": active_count,
            "new_count": new_count,
            "dd_count": dd_count,
            "avg_score": round(avg_score, 1),
            "scored_count": len(scores),
        },
        "projects": project_list,
        "counts": {
            "stages": status_counts,
            "status": status_counts,
            "categories": category_counts,
            "category": category_counts,
            "priorities": priority_counts,
            "scores": {k: score_counts.get(k, 0) for k in SCORE_DISPLAY_ORDER},
            "score_labels": SCORE_LABELS,
        },
        "filters": {
            "statuses": sorted(status_counts.keys()),
            "priorities": sorted(priority_counts.keys()),
            "categories": sorted(category_counts.keys()),
            "ai_types": ["创新/AI", "传统"],
            "scores": [SCORE_LABELS[k] for k in SCORE_DISPLAY_ORDER],
        },
    }


def load_dashboard_payload(db: Session) -> dict:
    """从 DB 查询 Dashboard 数据，带 60 秒 TTL 缓存。"""
    tid = _tenant_id()
    # 用当前租户的项目总数作为缓存 key 的一部分（变更时自动失效）
    total = db.query(Project).filter(
        Project.deleted_at.is_(None),
        Project.tenant_id == tid,
    ).count() if tid else db.query(Project).filter(Project.deleted_at.is_(None)).count()
    return _build_dashboard_payload(tid or 0, total)


def invalidate_dashboard_cache():
    """当项目数据变更时，使 Dashboard 缓存失效。"""
    invalidate("_build_dashboard_payload")
