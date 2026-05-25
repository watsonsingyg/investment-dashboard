"""Dashboard payload assembly shared by API, exports, and SQLite sync."""

import json
from collections import Counter

try:
    from .dashboard_data import parse_excel
    from .dashboard_render import build_projects_json
    from .excel_store import find_excel
    from .statuses import FUNNEL_STAGES, SCORE_DISPLAY_ORDER, SCORE_LABELS
except ImportError:
    from dashboard_data import parse_excel
    from dashboard_render import build_projects_json
    from excel_store import find_excel
    from statuses import FUNNEL_STAGES, SCORE_DISPLAY_ORDER, SCORE_LABELS


def load_dashboard_payload(report_dir) -> dict:
    excel = find_excel(report_dir)
    data = parse_excel(str(excel))
    data['script_dir'] = str(report_dir)
    projects = data['projects']
    projects_json = build_projects_json(projects, str(report_dir))
    api_projects = json.loads(projects_json)
    by_name = {p['name']: p for p in projects}
    for item in api_projects:
        src = by_name.get(item['name'], {})
        item.update({
            'biz_scope': src.get('biz_scope', ''),
            'priority': src.get('priority', ''),
            'score': src.get('score', ''),
            'score_label': src.get('score_label', ''),
            'last_active': src.get('last_active', ''),
            'last_active_iso': src.get('last_active_iso', ''),
            'latest_content': src.get('latest_content', ''),
            'is_new': src.get('is_new', False),
        })

    total = len(projects)
    ai_count = sum(1 for p in projects if p['is_ai'])
    active_count = sum(1 for p in projects if p['is_active'])
    new_count = sum(1 for p in projects if p['is_new'])
    dd_count = sum(1 for p in projects if p['status'] not in ('前期沟通', ''))
    stage_cnt = Counter(p['status'] for p in projects if p['status'])
    cat_cnt = Counter(p['category'] for p in projects)
    priority_cnt = Counter(p['priority'] for p in projects if p['priority'])
    score_cnt = Counter(p['score'] for p in projects if p.get('score'))
    score_values = [int(p['score']) for p in projects if p.get('score')]
    scored_count = len(score_values)

    return {
        'meta': {
            'latest_week': data['latest_week'],
            'oldest_week': data['oldest_week'],
            'generated': data['generated'],
            'source_file': data['source_file'],
        },
        'metrics': {
            'total': total,
            'ai_count': ai_count,
            'non_ai': total - ai_count,
            'active_count': active_count,
            'new_count': new_count,
            'dd_count': dd_count,
            'scored_count': scored_count,
            'avg_score': round(sum(score_values) / scored_count, 1) if scored_count else 0,
        },
        'filters': {
            'statuses': [s for s in FUNNEL_STAGES if stage_cnt.get(s, 0)],
            'priorities': ['高', '中', '低'],
            'categories': sorted(cat_cnt),
            'ai_types': ['创新/AI', '传统'],
            'scores': [SCORE_LABELS[k] for k in SCORE_DISPLAY_ORDER],
        },
        'counts': {
            'stages': dict(stage_cnt),
            'categories': dict(cat_cnt),
            'priorities': dict(priority_cnt),
            'scores': {k: score_cnt.get(k, 0) for k in SCORE_DISPLAY_ORDER},
            'score_labels': SCORE_LABELS,
        },
        'projects': api_projects,
    }
