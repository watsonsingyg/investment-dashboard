"""SQLite shadow store for fast local queries and migration rehearsal."""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import settings  # noqa: E402


def db_path(report_dir) -> Path:
    return settings.SHADOW_DB


def connect(report_dir):
    conn = sqlite3.connect(db_path(report_dir))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
      name TEXT PRIMARY KEY,
      biz_scope TEXT,
      industry TEXT,
      category TEXT,
      owner TEXT,
      status TEXT,
      status_raw TEXT,
      priority TEXT,
      score TEXT,
      is_ai INTEGER,
      last_active TEXT,
      first_active TEXT,
      latest_content TEXT
    );
    CREATE TABLE IF NOT EXISTS weekly_entries (
      project TEXT,
      week TEXT,
      content TEXT,
      short TEXT,
      medium TEXT,
      PRIMARY KEY (project, week)
    );
    CREATE TABLE IF NOT EXISTS sync_meta (
      key TEXT PRIMARY KEY,
      value TEXT
    );
    CREATE TABLE IF NOT EXISTS field_diffs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT,
      project TEXT,
      week TEXT,
      field TEXT,
      old_value TEXT,
      new_value TEXT,
      backup_path TEXT
    );
    """)
    existing_cols = {row[1] for row in conn.execute('PRAGMA table_info(projects)').fetchall()}
    if 'score' not in existing_cols:
        conn.execute('ALTER TABLE projects ADD COLUMN score TEXT')
    conn.commit()


def sync_dashboard_data(report_dir, data: dict):
    conn = connect(report_dir)
    init_db(conn)
    conn.execute('DELETE FROM projects')
    conn.execute('DELETE FROM weekly_entries')
    for p in data.get('projects', []):
        conn.execute("""
        INSERT OR REPLACE INTO projects
        (name,biz_scope,industry,category,owner,status,status_raw,priority,score,is_ai,last_active,first_active,latest_content)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            p.get('name', ''), p.get('biz_scope', ''), p.get('industry', ''),
            p.get('category', ''), p.get('owner', ''), p.get('status', ''),
            p.get('status_raw', ''), p.get('priority', ''), p.get('score', ''),
            1 if p.get('is_ai') else 0,
            p.get('last_active', ''), p.get('first_active', ''),
            p.get('latest_content', ''),
        ))
        for e in p.get('timeline', []):
            conn.execute("""
            INSERT OR REPLACE INTO weekly_entries (project,week,content,short,medium)
            VALUES (?,?,?,?,?)
            """, (
                p.get('name', ''), e.get('week', ''), e.get('content', ''),
                e.get('short', ''), e.get('medium', ''),
            ))
    conn.execute(
        'INSERT OR REPLACE INTO sync_meta (key,value) VALUES (?,?)',
        ('last_sync', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    meta = data.get('meta', {})
    conn.execute(
        'INSERT OR REPLACE INTO sync_meta (key,value) VALUES (?,?)',
        ('source_file', data.get('source_file', '') or meta.get('source_file', ''))
    )
    conn.commit()
    conn.close()


def record_diffs(report_dir, project: str, changes: list, week: str = '', backup_path: str = ''):
    if not changes:
        return
    conn = connect(report_dir)
    init_db(conn)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for change in changes:
        conn.execute("""
        INSERT INTO field_diffs (ts,project,week,field,old_value,new_value,backup_path)
        VALUES (?,?,?,?,?,?,?)
        """, (
            ts, project, week, change.get('field', ''),
            str(change.get('old', '') or ''), str(change.get('new', '') or ''),
            backup_path,
        ))
    conn.commit()
    conn.close()


def counts(report_dir) -> dict:
    conn = connect(report_dir)
    init_db(conn)
    result = {
        'projects': conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0],
        'weekly_entries': conn.execute('SELECT COUNT(*) FROM weekly_entries').fetchone()[0],
        'field_diffs': conn.execute('SELECT COUNT(*) FROM field_diffs').fetchone()[0],
    }
    conn.close()
    return result


def recent_diffs(report_dir, project: str = '', limit: int = 20) -> list:
    conn = connect(report_dir)
    init_db(conn)
    limit = max(1, min(int(limit or 20), 100))
    if project:
        rows = conn.execute("""
            SELECT ts,project,week,field,old_value,new_value,backup_path
            FROM field_diffs
            WHERE project=?
            ORDER BY id DESC
            LIMIT ?
        """, (project, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT ts,project,week,field,old_value,new_value,backup_path
            FROM field_diffs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result
