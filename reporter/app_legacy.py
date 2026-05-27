#!/usr/bin/env python3
"""
reporter/app.py — 投资 Pipeline 管理系统后端

运行：  python3 reporter/app.py
访问：  http://localhost:8766

所有配置由环境变量控制，参见项目根目录 .env.example。
"""

import json
import os
import sys
import zipfile
import subprocess
import functools
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, Response, stream_with_context, session, redirect
from werkzeug.exceptions import RequestEntityTooLarge

# ── 配置（从环境变量读取）──────────────────────────────────────────────────
REPORTER_DIR = Path(__file__).parent

# 把项目根目录加入 sys.path，确保跨模块导入可用
_PROJECT_ROOT = str(REPORTER_DIR.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import settings  # noqa: E402

# ── 日志 ────────────────────────────────────────────────────────────────────
from reporter.logger import get_logger   # noqa: E402
log = get_logger('app')

# ── 业务模块 ────────────────────────────────────────────────────────────────
from reporter.ai_service import stream_weekly_generation                    # noqa: E402
from reporter.dashboard_api import load_dashboard_payload                   # noqa: E402
from reporter.dashboard_data import parse_excel                             # noqa: E402
from reporter.excel_store import (                                          # noqa: E402
    ExcelLockError, find_excel, get_existing_week_content,
    get_project_row, get_projects, push_to_excel,
    update_project_fields, update_week_content,
)
from reporter.export_service import (                                       # noqa: E402
    export_project_markdown, export_projects_csv, export_weekly_markdown,
)
from reporter.governance import load_governance_report, save_governance_issue_state  # noqa: E402
from reporter.operation_log import log_operation, read_recent_operations    # noqa: E402
from reporter.shadow_store import recent_diffs, record_diffs, sync_dashboard_data  # noqa: E402
from reporter.statuses import (                                             # noqa: E402
    FUNNEL_STAGES, PRIORITY_ORDER, SCORE_DISPLAY_ORDER, SCORE_LABELS,
)
from reporter.summary_cache import update_summary_cache                     # noqa: E402
from reporter.validation import (                                           # noqa: E402
    validate_project_patch, validate_project_week_content, validate_uploads,
)

# ── Skill 加载 ──────────────────────────────────────────────────────────────
def _load_skill(path: Path) -> str:
    """从 .skill 压缩包中提取 Markdown 内容。"""
    try:
        with zipfile.ZipFile(path) as z:
            for fn in z.namelist():
                if fn.endswith('.md'):
                    return z.read(fn).decode('utf-8')
    except Exception as e:
        print(f'[warn] 无法加载 skill {path}: {e}')
    return ''


_SKILL_IT = ''
_SKILL_WS = ''
SYSTEM_PROMPT = ''

if settings.SKILL_ROOT and settings.SKILL_ROOT.exists():
    _IT_PATH = settings.SKILL_ROOT / '【Skill】investment taste/语涵的investment-taste.skill'
    _WS_PATH = settings.SKILL_ROOT / '【Skill】yuhan writing style/yuhan-writing-style.skill'
    _SKILL_IT = _load_skill(_IT_PATH) if _IT_PATH.exists() else ''
    _SKILL_WS = _load_skill(_WS_PATH) if _WS_PATH.exists() else ''

    if _SKILL_WS and _SKILL_IT:
        SYSTEM_PROMPT = f"""{_SKILL_WS}

---

{_SKILL_IT}

---

## 当前任务

分析以上材料，严格按 investment-taste skill 的完整七节框架逐节展开，每节内容深度和分析维度与 investment-taste 的描述一致。

语言与排版全程遵循 yuhan-writing-style 规范，其格式规定优先级高于 investment-taste 内的任何 Markdown 格式标注：
- 节标题：不用 **粗体**，用"一、二、三…"编号，或 `【节名】`
- 子标题：`1.` `2.` 编号或 `- ` bullet，不加粗
- 禁止使用任何星号（*）字符
- → 只用于因果推导，- 用于平行列举
- 专业术语直接英文（ARR/ACV/NRR/LLM/SaaS/FDD 等），不加中文注释
- 数字格式：金额用万/亿元，增速带正负号如 +56%，倍数小写 x

总字数 2000 字以内：有数据的地方用数据，定性判断精简 1-2 句；数据缺失直接写"未披露，待尽调确认"，不填充文字。

第一行输出：`核心结论：[公司本质是做什么 + 最关键投资判断]`，之后直接进入纪要正文。
"""

# ── 常量 ────────────────────────────────────────────────────────────────────
APP_STARTED_AT = datetime.now()

# ── Flask 应用 ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = settings.FLASK_SECRET
app.config.update(
    MAX_CONTENT_LENGTH=settings.MAX_CONTENT_LENGTH_MB * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# 确保必要目录存在
settings.ensure_dirs()


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def json_response(payload: dict, status: int = 200):
    return app.response_class(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        content_type='application/json; charset=utf-8',
    )


def _mtime_label(path: Path) -> str:
    if not path.exists():
        return ''
    return datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')


def _sync_meta() -> dict:
    import sqlite3
    db = settings.SHADOW_DB
    if not db.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db))
        rows = conn.execute('SELECT key,value FROM sync_meta').fetchall()
        conn.close()
        return {k: v for k, v in rows}
    except Exception:
        return {}


def system_status_payload() -> dict:
    report_dir = settings.REPORT_DIR
    try:
        excel = find_excel(report_dir)
        excel_file = excel.name
        excel_mtime = _mtime_label(excel)
    except Exception:
        excel_file = ''
        excel_mtime = ''
    meta = _sync_meta()
    up = int((datetime.now() - APP_STARTED_AT).total_seconds())
    return {
        'ok': True,
        'app': 'pipeline-workbench',
        'pid': os.getpid(),
        'started_at': APP_STARTED_AT.strftime('%Y-%m-%d %H:%M:%S'),
        'uptime_seconds': up,
        'model': settings.DEEPSEEK_MODEL,
        'port': settings.APP_PORT,
        'excel_file': excel_file,
        'excel_mtime': excel_mtime,
        'dashboard_mtime': _mtime_label(settings.DASHBOARD_FILE),
        'last_sync': meta.get('last_sync', ''),
        'source_file': meta.get('source_file', ''),
    }


def field_options_payload() -> dict:
    report_dir = settings.REPORT_DIR
    excel = find_excel(report_dir)
    data = parse_excel(str(excel))

    def unique(field):
        values = {
            str(p.get(field, '') or '').strip()
            for p in data.get('projects', [])
            if str(p.get(field, '') or '').strip()
        }
        return sorted(values, key=lambda v: v.lower())

    return {
        'biz_scopes': unique('biz_scope'),
        'industries': unique('industry'),
        'owners': unique('owner'),
        'statuses': FUNNEL_STAGES,
        'priorities': PRIORITY_ORDER,
        'scores': [{'value': key, 'label': SCORE_LABELS[key]} for key in SCORE_DISPLAY_ORDER],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 中间件
# ═══════════════════════════════════════════════════════════════════════════

@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(_):
    limit_mb = settings.MAX_CONTENT_LENGTH_MB
    return json_response({'error': f'上传内容超过 {limit_mb}MB 总大小限制'}, 413)


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('authed'):
            if request.path.startswith('/api/'):
                return app.response_class(
                    json.dumps({'error': '未登录'}, ensure_ascii=False),
                    status=401, content_type='application/json; charset=utf-8',
                )
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════
# 健康 & 系统
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/health')
def api_health():
    payload = system_status_payload()
    return json_response({
        'ok': payload['ok'],
        'app': payload['app'],
        'pid': payload['pid'],
        'started_at': payload['started_at'],
        'model': payload['model'],
    })


@app.route('/api/system-status')
@login_required
def api_system_status():
    return json_response(system_status_payload())


@app.route('/api/server-log')
@login_required
def api_server_log():
    try:
        lines = max(20, min(int(request.args.get('lines', 200) or 200), 500))
    except ValueError:
        lines = 200
    log_path = settings.SERVER_LOG
    if not log_path.exists():
        return json_response({'path': str(log_path), 'lines': []})
    try:
        content = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
        return json_response({'path': str(log_path), 'lines': content[-lines:]})
    except Exception as e:
        return json_response({'error': f'读取服务日志失败：{e}'}, 500)


# ═══════════════════════════════════════════════════════════════════════════
# 认证
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    password = settings.PORTAL_PASSWORD
    if request.method == 'POST':
        lock_until = session.get('login_lock_until', 0)
        if lock_until and time.time() < lock_until:
            error = '登录尝试过多，请稍后再试'
            html = _LOGIN_HTML.replace('{{ERROR}}', error).replace('{{ERR_CLASS}}', 'show')
            return Response(html, content_type='text/html; charset=utf-8')
        if password and request.form.get('password', '') == password:
            session['authed'] = True
            session.pop('login_failures', None)
            session.pop('login_lock_until', None)
            return redirect('/')
        failures = int(session.get('login_failures', 0)) + 1
        session['login_failures'] = failures
        if failures >= 5:
            session['login_lock_until'] = time.time() + settings.LOGIN_COOLDOWN_SECONDS
        error = '密码错误，请重试'
    html = _LOGIN_HTML.replace('{{ERROR}}', error).replace('{{ERR_CLASS}}', 'show' if error else '')
    return Response(html, content_type='text/html; charset=utf-8')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ═══════════════════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def portal():
    report_dir = settings.REPORT_DIR
    try:
        pcount = len(get_projects(report_dir))
    except Exception:
        pcount = 0
    dash = settings.DASHBOARD_FILE
    mtime = datetime.fromtimestamp(dash.stat().st_mtime).strftime('%Y-%m-%d %H:%M') if dash.exists() else '—'
    html = _PORTAL_HTML.replace('{{PROJECT_COUNT}}', str(pcount)).replace('{{LAST_UPDATED}}', mtime)
    return Response(html, content_type='text/html; charset=utf-8')


@app.route('/status')
@login_required
def status_page():
    return Response(_STATUS_HTML, content_type='text/html; charset=utf-8')


@app.route('/dashboard')
@login_required
def dashboard():
    dash = settings.DASHBOARD_FILE
    if not dash.exists():
        return '看板文件不存在，请先运行 generate_dashboard.py', 404
    return Response(dash.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')


@app.route('/reporter')
@login_required
def reporter_page():
    return Response(_HTML, content_type='text/html; charset=utf-8')


@app.route('/governance')
@login_required
def governance_page():
    return Response(_GOVERNANCE_HTML, content_type='text/html; charset=utf-8')


# ═══════════════════════════════════════════════════════════════════════════
# 项目 API
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/projects')
@login_required
def api_projects():
    try:
        return json_response(get_projects(settings.REPORT_DIR))
    except Exception as e:
        return json_response({'error': f'读取项目列表失败：{e}'}, 500)


@app.route('/api/field-options')
@login_required
def api_field_options():
    try:
        return json_response(field_options_payload())
    except Exception as e:
        return json_response({'error': f'读取字段选项失败：{e}'}, 500)


@app.route('/api/dashboard-data')
@login_required
def api_dashboard_data():
    report_dir = settings.REPORT_DIR
    try:
        payload = load_dashboard_payload(report_dir)
        sync_dashboard_data(report_dir, payload)
        return json_response(payload)
    except Exception as e:
        return json_response({'error': f'读取看板数据失败：{e}'}, 500)


@app.route('/api/governance-data')
@login_required
def api_governance_data():
    try:
        return json_response(load_governance_report(settings.REPORT_DIR))
    except Exception as e:
        return json_response({'error': f'读取健康检查失败：{e}'}, 500)


@app.route('/api/governance/issue-state', methods=['POST'])
@login_required
def api_governance_issue_state():
    body = request.get_json() or {}
    report_dir = settings.REPORT_DIR
    try:
        result = save_governance_issue_state(
            report_dir, issue_key=body.get('issue_key', ''),
            state=body.get('state', 'active'),
            note=body.get('note', ''),
            days=body.get('days', 30),
        )
        log_operation(report_dir, 'governance_issue_state',
                      issue_key=result['issue_key'], state=result['state'],
                      note=body.get('note', ''))
        return json_response(result)
    except Exception as e:
        return json_response({'error': f'更新问题状态失败：{e}'}, 400)


@app.route('/api/projects/<path:project>', methods=['GET'])
@login_required
def api_project_detail(project):
    try:
        row = get_project_row(settings.REPORT_DIR, project)
        return json_response(row)
    except KeyError as e:
        return json_response({'error': str(e)}, 404)
    except Exception as e:
        return json_response({'error': f'读取项目失败：{e}'}, 500)


@app.route('/api/projects/<path:project>', methods=['PATCH'])
@login_required
def api_project_patch(project):
    body = request.get_json() or {}
    errors = validate_project_patch(body)
    if errors:
        return json_response({'error': '；'.join(errors)}, 400)
    report_dir = settings.REPORT_DIR
    try:
        result = update_project_fields(report_dir, project, body)
        record_diffs(report_dir, result['project'], result['changes'],
                     backup_path=result.get('backup_path', ''))
        payload = load_dashboard_payload(report_dir)
        sync_dashboard_data(report_dir, payload)
        log_operation(report_dir, 'project_patch',
                      project=result['project'], changes=result['changes'],
                      backup_path=result.get('backup_path', ''))
        return json_response(result)
    except ExcelLockError as e:
        return json_response({'error': str(e)}, 423)
    except KeyError as e:
        return json_response({'error': str(e)}, 404)
    except Exception as e:
        log_operation(report_dir, 'project_patch_failed', project=project, error=str(e))
        return json_response({'error': f'更新项目失败：{e}'}, 500)


@app.route('/api/projects/<path:project>/week/<path:week>', methods=['PATCH'])
@login_required
def api_project_week_patch(project, week):
    body = request.get_json() or {}
    content = body.get('content', '').strip()
    if not content:
        return json_response({'error': '内容不能为空'}, 400)
    report_dir = settings.REPORT_DIR
    try:
        result = update_week_content(report_dir, project, week, content)
        changes = [{
            'field': 'weekly_content', 'week': week,
            'old': result['old_content'], 'new': result['new_content'],
        }]
        record_diffs(report_dir, project, changes, week=week,
                     backup_path=result.get('backup_path', ''))
        # 重新生成看板
        try:
            proc = subprocess.run(
                [sys.executable, 'generate_dashboard.py'],
                cwd=report_dir, capture_output=True, text=True, timeout=120,
            )
            regen_ok = proc.returncode == 0
            regen_msg = proc.stdout.strip() or proc.stderr.strip()
        except Exception as e:
            regen_ok, regen_msg = False, str(e)
        # 同步影子库
        try:
            payload = load_dashboard_payload(report_dir)
            sync_dashboard_data(report_dir, payload)
        except Exception:
            pass
        log_operation(report_dir, 'week_content_edit',
                      project=project, week=week, regen_ok=regen_ok, regen_msg=regen_msg)
        return json_response({
            'ok': True, 'project': project, 'week': week,
            'regen_ok': regen_ok, 'regen_msg': regen_msg,
        })
    except ExcelLockError as e:
        return json_response({'error': str(e)}, 423)
    except KeyError as e:
        return json_response({'error': str(e)}, 404)
    except Exception as e:
        return json_response({'error': f'更新周报内容失败：{e}'}, 500)


# ═══════════════════════════════════════════════════════════════════════════
# 审计
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/audit/project/<path:project>')
@login_required
def api_project_audit(project):
    report_dir = settings.REPORT_DIR
    try:
        return json_response({
            'project': project.strip(),
            'diffs': recent_diffs(report_dir, project=project.strip(), limit=20),
            'operations': read_recent_operations(report_dir, project=project.strip(), limit=20),
        })
    except Exception as e:
        return json_response({'error': f'读取变更记录失败：{e}'}, 500)


@app.route('/api/audit/recent')
@login_required
def api_recent_audit():
    report_dir = settings.REPORT_DIR
    try:
        return json_response({
            'diffs': recent_diffs(report_dir, limit=30),
            'operations': read_recent_operations(report_dir, limit=30),
        })
    except Exception as e:
        return json_response({'error': f'读取变更记录失败：{e}'}, 500)


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/export/projects.csv')
@login_required
def api_export_projects_csv():
    payload = load_dashboard_payload(settings.REPORT_DIR)
    body = export_projects_csv(payload, request.args)
    return Response(
        '\ufeff' + body,
        content_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="projects.csv"'},
    )


@app.route('/api/export/project/<path:project>.md')
@login_required
def api_export_project_md(project):
    try:
        payload = load_dashboard_payload(settings.REPORT_DIR)
        body = export_project_markdown(payload, project)
        return Response(
            body, content_type='text/markdown; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{project}.md"'},
        )
    except KeyError as e:
        return json_response({'error': str(e)}, 404)


@app.route('/api/export/weekly.md')
@login_required
def api_export_weekly_md():
    payload = load_dashboard_payload(settings.REPORT_DIR)
    week = request.args.get('week', '').strip() or payload['meta']['latest_week']
    body = export_weekly_markdown(payload, week)
    return Response(
        body, content_type='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="weekly-{week[:10]}.md"'},
    )


# ═══════════════════════════════════════════════════════════════════════════
# AI 生成
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/generate', methods=['POST'])
@login_required
def api_generate():
    project = request.form.get('project', '').strip()
    week = request.form.get('week', '').strip()
    extra = request.form.get('extra', '').strip()
    category = request.form.get('category', '').strip()
    biz_scope = request.form.get('biz_scope', '').strip()
    stage = request.form.get('stage', '').strip()
    progress = request.form.get('progress', '').strip()
    files = request.files.getlist('files')

    errors = validate_project_week_content(project, week, stage=stage)
    errors.extend(validate_uploads(files))
    if errors:
        return json_response({'error': '；'.join(errors)}, 400)

    file_data = []
    for f in files:
        try:
            file_data.append((f.filename or '', f.read()))
        except Exception as e:
            return json_response({'error': f'读取文件 {f.filename} 失败：{e}'}, 400)

    return Response(
        stream_with_context(stream_weekly_generation(
            project=project, week=week, extra=extra, category=category,
            biz_scope=biz_scope, stage=stage, progress=progress, file_data=file_data,
            system_prompt=SYSTEM_PROMPT, model=settings.DEEPSEEK_MODEL,
        )),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 推送至 Excel
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/push', methods=['POST'])
@login_required
def api_push():
    body = request.get_json() or {}
    project = body.get('project', '').strip()
    week = body.get('week', '').strip()
    content = body.get('content', '').strip()
    stage = body.get('stage', '').strip()
    category = body.get('category', '').strip()
    biz_scope = body.get('biz_scope', '').strip()
    score = str(body.get('score', '') or '').strip()
    force = bool(body.get('force', False))

    errors = validate_project_week_content(
        project, week, content, stage, score,
        require_content=True, require_score=True,
    )
    if errors:
        return json_response({'error': '；'.join(errors)}, 400)

    report_dir = settings.REPORT_DIR
    existing = get_existing_week_content(report_dir, project, week)
    try:
        before_project = get_project_row(report_dir, project)
    except Exception:
        before_project = {}
    if existing['exists'] and not force:
        return json_response({
            'error': '该项目本周已有内容',
            'duplicate': True, 'project': project, 'week': week,
            'existing_preview': existing['content'][:160],
        }, 409)

    try:
        result = push_to_excel(report_dir, project, week, content, stage, category, biz_scope, score)
    except ExcelLockError as e:
        return json_response({'error': str(e)}, 423)
    except Exception as e:
        log_operation(report_dir, 'push_failed', project=project, week=week, error=str(e))
        return json_response({'error': f'写入 Excel 失败：{e}'}, 500)

    try:
        update_summary_cache(report_dir, project, content)
    except Exception as e:
        log_operation(report_dir, 'summary_cache_failed', project=project, week=week, error=str(e))

    try:
        proc = subprocess.run(
            [sys.executable, 'generate_dashboard.py'],
            cwd=report_dir, capture_output=True, text=True, timeout=120,
        )
        regen_ok = proc.returncode == 0
        regen_msg = proc.stdout.strip() or proc.stderr.strip()
    except Exception as e:
        regen_ok, regen_msg = False, str(e)

    changes = []
    if result.get('old_content') != result.get('new_content'):
        changes.append({
            'field': 'weekly_content',
            'old': result.get('old_content', ''), 'new': result.get('new_content', ''),
        })
    if stage and before_project.get('status', '') != stage:
        changes.append({'field': 'status', 'old': before_project.get('status', ''), 'new': stage})
    if score and before_project.get('score', '') != score:
        changes.append({'field': 'score', 'old': before_project.get('score', ''), 'new': score})
    record_diffs(report_dir, project, changes, week=week, backup_path=result.get('backup_path', ''))
    try:
        payload = load_dashboard_payload(report_dir)
        sync_dashboard_data(report_dir, payload)
    except Exception as e:
        log_operation(report_dir, 'shadow_sync_failed', project=project, week=week, error=str(e))

    log_operation(report_dir, 'push',
                  project=project, week=week, stage=stage, category=category,
                  is_new=result.get('is_new', False), overwritten=existing['exists'],
                  backup_path=result.get('backup_path', ''),
                  regen_ok=regen_ok, regen_msg=regen_msg)

    return json_response({
        'ok': True, 'project': project, 'week': week,
        'is_new': result.get('is_new', False),
        'stage': stage, 'score': score,
        'regen_ok': regen_ok, 'regen_msg': regen_msg,
        'backup_path': result.get('backup_path', ''),
        'overwritten': existing['exists'],
    })


# ═══════════════════════════════════════════════════════════════════════════
# 前端模板
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE_DIR = REPORTER_DIR / 'templates'


def _read_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding='utf-8')


_LOGIN_HTML = _read_template('login.html')
_PORTAL_HTML = _read_template('portal.html').replace('{{GENERATION_MODEL}}', settings.DEEPSEEK_MODEL)
_HTML = _read_template('reporter.html').replace('{{GENERATION_MODEL}}', settings.DEEPSEEK_MODEL)
_GOVERNANCE_HTML = _read_template('governance.html')
_STATUS_HTML = _read_template('status.html')


# ═══════════════════════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    log.info('server_starting',
             host=settings.APP_HOST, port=settings.APP_PORT,
             model=settings.DEEPSEEK_MODEL,
             has_api_key=bool(settings.DEEPSEEK_API_KEY),
             has_skill_root=bool(settings.SKILL_ROOT))
    app.run(host=settings.APP_HOST, port=settings.APP_PORT,
            debug=settings.APP_DEBUG, threaded=True)
