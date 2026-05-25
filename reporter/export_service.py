"""CSV and Markdown export helpers."""

import csv
import io
from urllib.parse import unquote


def _match_filters(project: dict, args) -> bool:
    status = args.get('status', '').strip()
    priority = args.get('priority', '').strip()
    category = args.get('category', '').strip()
    ai_type = args.get('ai', '').strip()
    q = args.get('q', '').strip().lower()
    if status and project.get('status') != status:
        return False
    if priority and project.get('priority') != priority:
        return False
    if category and project.get('category') != category:
        return False
    if ai_type == '创新/AI' and not project.get('is_ai'):
        return False
    if ai_type == '传统' and project.get('is_ai'):
        return False
    if q:
        hay = ' '.join(str(project.get(k, '')) for k in ('name', 'industry', 'category', 'status', 'owner', 'score', 'score_label')).lower()
        if q not in hay:
            return False
    return True


def export_projects_csv(payload: dict, args) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['项目', '行业大类', '细分行业', '状态', '优先级', '评分', '负责人', '最后活跃', 'AI/传统'])
    for p in payload['projects']:
        if not _match_filters(p, args):
            continue
        writer.writerow([
            p.get('name', ''), p.get('category', ''), p.get('industry', ''),
            p.get('status', ''), p.get('priority', ''), p.get('score_label', ''),
            p.get('owner', ''),
            p.get('last_active', ''), '创新/AI' if p.get('is_ai') else '传统',
        ])
    return out.getvalue()


def export_project_markdown(payload: dict, project: str) -> str:
    project = unquote(project)
    p = next((x for x in payload['projects'] if x['name'] == project), None)
    if not p:
        raise KeyError(f'未找到项目：{project}')
    lines = [
        f'# {p["name"]}',
        '',
        f'- 状态：{p.get("status", "")}',
        f'- 优先级：{p.get("priority", "")}',
        f'- 评分：{p.get("score_label", "") or "未评分"}',
        f'- 行业：{p.get("category", "")} / {p.get("industry", "")}',
        f'- 负责人：{p.get("owner", "")}',
        '',
        '## 时间轴',
        '',
    ]
    for e in p.get('timeline', []):
        lines.extend([
            f'### {e.get("week", "")}',
            '',
            e.get('medium') or e.get('content', ''),
            '',
            '<details><summary>原文</summary>',
            '',
            e.get('content', ''),
            '',
            '</details>',
            '',
        ])
    return '\n'.join(lines)


def export_weekly_markdown(payload: dict, week: str) -> str:
    week = week or payload['meta'].get('latest_week', '')
    lines = [f'# 本周动态 {week}', '']
    for p in payload['projects']:
        entry = next((e for e in p.get('timeline', []) if e.get('week') == week), None)
        if not entry:
            continue
        lines.extend([
            f'## {p["name"]}',
            '',
            f'- 状态：{p.get("status", "")}',
            f'- 行业：{p.get("category", "")} / {p.get("industry", "")}',
            '',
            entry.get('medium') or entry.get('content', ''),
            '',
        ])
    return '\n'.join(lines)
