"""Append-only operation logging."""

import json
from datetime import datetime
from pathlib import Path


def log_operation(report_dir, event: str, **payload):
    log_dir = Path(report_dir) / 'logs'
    log_dir.mkdir(exist_ok=True)
    record = {
        'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'event': event,
        **payload,
    }
    with (log_dir / 'operations.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')


def read_recent_operations(report_dir, project: str = '', limit: int = 20) -> list:
    """Return recent operation-log records, newest first."""
    path = Path(report_dir) / 'logs' / 'operations.jsonl'
    if not path.exists():
        return []
    rows = []
    project = (project or '').strip()
    limit = max(1, min(int(limit or 20), 100))
    for raw in reversed(path.read_text(encoding='utf-8').splitlines()):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if project and item.get('project') != project:
            continue
        rows.append(item)
        if len(rows) >= limit:
            break
    return rows
