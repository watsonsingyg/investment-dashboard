"""
reporter/services/governance_service.py — 数据治理规则引擎。

在数据库上运行 7 条治理规则，生成健康检查报告。
所有查询自动带 tenant_id 隔离。
"""

from datetime import datetime, timedelta
from typing import Optional
from flask import g
from sqlalchemy.orm import Session
from models.project import Project
from models.weekly_entry import WeeklyEntry
from models.governance_issue import GovernanceIssue


def _tenant_id() -> Optional[int]:
    """获取当前请求的 tenant_id。"""
    return getattr(g, "tenant_id", None)


_ISSUE_LABELS = {
    "missing_owner": "缺负责人",
    "missing_priority": "缺优先级",
    "missing_score": "缺评分",
    "missing_status": "缺状态",
    "stale_project": "长期无更新",
    "no_weekly_updates": "无任何周报",
    "no_current_week_update": "无本周更新",
}


def load_governance_report(
    db: Session, stale_weeks: int = 8,
) -> dict:
    """生成治理报告（兼容旧版 API 格式），限定当前租户。"""
    tid = _tenant_id()

    query = db.query(Project).filter(Project.deleted_at.is_(None))
    if tid is not None:
        query = query.filter(Project.tenant_id == tid)
    projects = query.all()

    project_ids = [p.id for p in projects]
    entries_map = {}
    if project_ids:
        rows = (
            db.query(WeeklyEntry)
            .filter(WeeklyEntry.project_id.in_(project_ids))
            .all()
        )
        for r in rows:
            entries_map.setdefault(r.project_id, {})[r.week] = r.content or ""

    all_weeks = set()
    for wmap in entries_map.values():
        all_weeks.update(wmap.keys())
    sorted_weeks = sorted(all_weeks, reverse=True)
    latest_week = sorted_weeks[0] if sorted_weeks else "—"
    oldest_week = sorted_weeks[-1] if sorted_weeks else "—"

    # 计算 stale cutoff
    stale_cutoff_idx = min(stale_weeks, len(sorted_weeks))
    stale_cutoff_week = sorted_weeks[stale_cutoff_idx - 1] if stale_cutoff_idx > 0 else latest_week

    issues = []

    for p in projects:
        weekly = entries_map.get(p.id, {})
        last_content = (p.latest_content or "").strip()

        # 1. 缺负责人
        if not p.owner or not p.owner.strip():
            issues.append(_make_issue(p, "missing_owner", "缺负责人", "medium",
                                       "未指定项目负责人", "请指定负责人", True, "owner"))

        # 2. 缺优先级
        if not p.priority or not p.priority.strip():
            issues.append(_make_issue(p, "missing_priority", "缺优先级", "medium",
                                       "未设置项目优先级", "请设置高/中/低", True, "priority"))

        # 3. 缺评分
        if not p.score or not p.score.strip():
            issues.append(_make_issue(p, "missing_score", "缺评分", "medium",
                                       "未对项目打分", "请打 1-5 分", True, "score"))

        # 4. 缺状态
        if not p.status or not p.status.strip():
            issues.append(_make_issue(p, "missing_status", "缺状态", "high",
                                       "未设置项目当前阶段", "请选择项目阶段", True, "status"))

        # 5. 长期无更新
        if last_content and stale_cutoff_week:
            last_week = p.last_active or ""
            if last_week and last_week < stale_cutoff_week:
                issues.append(_make_issue(p, "stale_project", "长期无更新", "medium",
                                           f"最后更新于 {last_week}，已超过 {stale_weeks} 周",
                                           "请更新项目进展", False, None))

        # 6. 无任何周报
        if not weekly:
            issues.append(_make_issue(p, "no_weekly_updates", "无任何周报", "high",
                                       "该项目没有任何周报记录", "请添加第一条周报", False, None))

        # 7. 本周无更新
        if latest_week and latest_week not in weekly:
            issues.append(_make_issue(p, "no_current_week_update", "无本周更新", "low",
                                       f"本周 ({latest_week}) 无更新", "请更新本周进展", False, None))

    # 汇总
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    type_counts = {}
    for iss in issues:
        severity_counts[iss["severity"]] = severity_counts.get(iss["severity"], 0) + 1
        type_counts[iss["type"]] = type_counts.get(iss["type"], 0) + 1

    return {
        "meta": {
            "generated": datetime.utcnow().isoformat(),
            "latest_week": latest_week,
            "oldest_week": oldest_week,
            "stale_weeks": stale_weeks,
            "stale_cutoff_week": stale_cutoff_week,
        },
        "summary": {
            "total_projects": len(projects),
            "total_issues": len(issues),
            "affected_projects": len(set(i["project"] for i in issues)),
            "high": severity_counts["high"],
            "medium": severity_counts["medium"],
            "low": severity_counts["low"],
        },
        "issue_types": [
            {"type": t, "label": _ISSUE_LABELS.get(t, t), "count": c}
            for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
        ],
        "issues": issues,
    }


def _make_issue(project, issue_type, label, severity, reason, suggestion, fixable, field):
    return {
        "id": f"{project.id}-{issue_type}",
        "type": issue_type,
        "type_label": label,
        "severity": severity,
        "reason": reason,
        "suggestion": suggestion,
        "fixable": fixable,
        "field": field,
        "project": project.name,
        "status": project.status or "",
        "priority": project.priority or "",
        "owner": project.owner or "",
        "score": project.score or "",
        "last_active": project.last_active or "",
        "issue_state": "active",
    }


def save_governance_issue_state(db: Session, issue_key: str,
                                 state: str, note: str = "", days: int = 30) -> dict:
    """保存治理问题的处理状态。"""
    tid = _tenant_id()
    query = db.query(GovernanceIssue).filter_by(issue_key=issue_key)
    if tid is not None:
        query = query.filter(GovernanceIssue.tenant_id == tid)
    issue = query.first()

    if issue:
        issue.issue_state = state
        issue.ignore_note = note
        if state == "ignored":
            issue.expires_at = datetime.utcnow() + timedelta(days=days)
    else:
        issue = GovernanceIssue(
            tenant_id=tid,
            issue_key=issue_key,
            issue_state=state,
            ignore_note=note,
            expires_at=datetime.utcnow() + timedelta(days=days) if state == "ignored" else None,
        )
        db.add(issue)

    db.commit()
    return {"issue_key": issue_key, "state": state}
