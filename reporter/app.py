#!/usr/bin/env python3
"""
reporter/app.py — 周报内容生成后端
运行：  python3 /Users/admin/Desktop/周报/reporter/app.py
访问：  http://localhost:8766
依赖：  pip install -r /Users/admin/Desktop/周报/requirements.txt
"""

import json, os, sys, zipfile, subprocess, functools, time
from pathlib import Path
from datetime import datetime

from flask import Flask, request, Response, stream_with_context, session, redirect
from werkzeug.exceptions import RequestEntityTooLarge

# ── 路径配置 ────────────────────────────────────────────────────────────────
REPORTER_DIR = Path(__file__).parent
REPORT_DIR   = REPORTER_DIR.parent           # /Users/admin/Desktop/周报/
SKILL_ROOT   = Path('/Users/admin/Desktop/项目文件/claude')
if str(REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(REPORT_DIR))

from reporter.ai_service import stream_weekly_generation
from reporter.dashboard_api import load_dashboard_payload
from reporter.dashboard_data import parse_excel
from reporter.excel_store import find_excel, get_existing_week_content, get_project_row, get_projects, push_to_excel, update_project_fields
from reporter.export_service import export_project_markdown, export_projects_csv, export_weekly_markdown
from reporter.governance import load_governance_report, save_governance_issue_state
from reporter.operation_log import log_operation, read_recent_operations
from reporter.shadow_store import recent_diffs, record_diffs, sync_dashboard_data
from reporter.statuses import FUNNEL_STAGES, PRIORITY_ORDER, SCORE_DISPLAY_ORDER, SCORE_LABELS
from reporter.summary_cache import update_summary_cache
from reporter.validation import validate_project_patch, validate_project_week_content, validate_uploads

# ── .env 自动加载 ────────────────────────────────────────────────────────────
def _load_dotenv():
    env_file = REPORT_DIR / '.env'
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_dotenv()

# ── Skill 加载 ──────────────────────────────────────────────────────────────
def _load_skill(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            for fn in z.namelist():
                if fn.endswith('.md'):
                    return z.read(fn).decode('utf-8')
    except Exception as e:
        print(f'[warn] 无法加载 skill {path}: {e}')
    return ''

_IT  = _load_skill(SKILL_ROOT / '【Skill】investment taste/语涵的investment-taste.skill')
_WS  = _load_skill(SKILL_ROOT / '【Skill】yuhan writing style/yuhan-writing-style.skill')

SYSTEM_PROMPT = f"""{_WS}

---

{_IT}

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

GENERATION_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-pro')
APP_PORT = int(os.environ.get('PORT', '8766'))
APP_STARTED_AT = datetime.now()

# ── Flask 应用 ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key   = os.environ.get('FLASK_SECRET', 'yuhan-pipeline-secret-2026-xk9')
app.config.update(
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)
PORTAL_PASSWORD  = os.environ.get('PORTAL_PASSWORD', 'yuhanvc')
LOGIN_COOLDOWN_SECONDS = 20


def json_response(payload: dict, status: int = 200):
    return app.response_class(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        content_type='application/json; charset=utf-8'
    )


def _mtime_label(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S') if path.exists() else ''


def _sync_meta() -> dict:
    import sqlite3
    db = REPORT_DIR / 'pipeline_shadow.db'
    if not db.exists():
        return {}
    try:
        conn = sqlite3.connect(db)
        rows = conn.execute('SELECT key,value FROM sync_meta').fetchall()
        conn.close()
        return {k: v for k, v in rows}
    except Exception:
        return {}


def system_status_payload() -> dict:
    try:
        excel = find_excel(REPORT_DIR)
        excel_file = excel.name
        excel_mtime = _mtime_label(excel)
    except Exception:
        excel_file = ''
        excel_mtime = ''
    dash = REPORT_DIR / 'dashboard.html'
    meta = _sync_meta()
    return {
        'ok': True,
        'app': 'zhangtou-workbench',
        'pid': os.getpid(),
        'started_at': APP_STARTED_AT.strftime('%Y-%m-%d %H:%M:%S'),
        'uptime_seconds': int((datetime.now() - APP_STARTED_AT).total_seconds()),
        'model': GENERATION_MODEL,
        'port': APP_PORT,
        'excel_file': excel_file,
        'excel_mtime': excel_mtime,
        'dashboard_mtime': _mtime_label(dash),
        'last_sync': meta.get('last_sync', ''),
        'source_file': meta.get('source_file', ''),
    }


def field_options_payload() -> dict:
    excel = find_excel(REPORT_DIR)
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


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(_):
    return json_response({'error': '上传内容超过 25MB 总大小限制'}, 413)

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('authed'):
            if request.path.startswith('/api/'):
                return app.response_class(
                    json.dumps({'error': '未登录'}, ensure_ascii=False),
                    status=401, content_type='application/json; charset=utf-8')
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper


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
    path = REPORT_DIR / 'logs' / 'server.log'
    if not path.exists():
        return json_response({'path': str(path), 'lines': []})
    try:
        content = path.read_text(encoding='utf-8', errors='replace').splitlines()
        return json_response({'path': str(path), 'lines': content[-lines:]})
    except Exception as e:
        return json_response({'error': f'读取服务日志失败：{e}'}, 500)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        lock_until = session.get('login_lock_until', 0)
        if lock_until and time.time() < lock_until:
            error = '登录尝试过多，请稍后再试'
            html = _LOGIN_HTML.replace('{{ERROR}}', error) \
                              .replace('{{ERR_CLASS}}', 'show')
            return Response(html, content_type='text/html; charset=utf-8')
        if request.form.get('password', '') == PORTAL_PASSWORD:
            session['authed'] = True
            session.pop('login_failures', None)
            session.pop('login_lock_until', None)
            return redirect('/')
        failures = int(session.get('login_failures', 0)) + 1
        session['login_failures'] = failures
        if failures >= 5:
            session['login_lock_until'] = time.time() + LOGIN_COOLDOWN_SECONDS
        error = '密码错误，请重试'
    html = _LOGIN_HTML.replace('{{ERROR}}', error) \
                      .replace('{{ERR_CLASS}}', 'show' if error else '')
    return Response(html, content_type='text/html; charset=utf-8')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
@login_required
def portal():
    try:
        pcount = len(get_projects(REPORT_DIR))
    except Exception:
        pcount = 0
    dash   = REPORT_DIR / 'dashboard.html'
    mtime  = datetime.fromtimestamp(dash.stat().st_mtime).strftime('%Y-%m-%d %H:%M') \
             if dash.exists() else '—'
    html   = _PORTAL_HTML \
        .replace('{{PROJECT_COUNT}}', str(pcount)) \
        .replace('{{LAST_UPDATED}}', mtime)
    return Response(html, content_type='text/html; charset=utf-8')


@app.route('/status')
@login_required
def status_page():
    return Response(_STATUS_HTML, content_type='text/html; charset=utf-8')

@app.route('/dashboard')
@login_required
def dashboard():
    dash = REPORT_DIR / 'dashboard.html'
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


@app.route('/api/projects')
@login_required
def api_projects():
    try:
        return json_response(get_projects(REPORT_DIR))
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
    try:
        payload = load_dashboard_payload(REPORT_DIR)
        sync_dashboard_data(REPORT_DIR, payload)
        return json_response(payload)
    except Exception as e:
        return json_response({'error': f'读取看板数据失败：{e}'}, 500)


@app.route('/api/governance-data')
@login_required
def api_governance_data():
    try:
        return json_response(load_governance_report(REPORT_DIR))
    except Exception as e:
        return json_response({'error': f'读取健康检查失败：{e}'}, 500)


@app.route('/api/governance/issue-state', methods=['POST'])
@login_required
def api_governance_issue_state():
    body = request.get_json() or {}
    try:
        result = save_governance_issue_state(
            REPORT_DIR,
            issue_key=body.get('issue_key', ''),
            state=body.get('state', 'active'),
            note=body.get('note', ''),
            days=body.get('days', 30),
        )
        log_operation(
            REPORT_DIR, 'governance_issue_state',
            issue_key=result['issue_key'], state=result['state'],
            note=body.get('note', '')
        )
        return json_response(result)
    except Exception as e:
        return json_response({'error': f'更新问题状态失败：{e}'}, 400)


@app.route('/api/projects/<path:project>', methods=['GET'])
@login_required
def api_project_detail(project):
    try:
        row = get_project_row(REPORT_DIR, project)
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
    try:
        result = update_project_fields(REPORT_DIR, project, body)
        record_diffs(REPORT_DIR, result['project'], result['changes'], backup_path=result.get('backup_path', ''))
        payload = load_dashboard_payload(REPORT_DIR)
        sync_dashboard_data(REPORT_DIR, payload)
        log_operation(
            REPORT_DIR, 'project_patch',
            project=result['project'], changes=result['changes'],
            backup_path=result.get('backup_path', '')
        )
        return json_response(result)
    except KeyError as e:
        return json_response({'error': str(e)}, 404)
    except Exception as e:
        log_operation(REPORT_DIR, 'project_patch_failed', project=project, error=str(e))
        return json_response({'error': f'更新项目失败：{e}'}, 500)


@app.route('/api/audit/project/<path:project>')
@login_required
def api_project_audit(project):
    project = project.strip()
    try:
        return json_response({
            'project': project,
            'diffs': recent_diffs(REPORT_DIR, project=project, limit=20),
            'operations': read_recent_operations(REPORT_DIR, project=project, limit=20),
        })
    except Exception as e:
        return json_response({'error': f'读取变更记录失败：{e}'}, 500)


@app.route('/api/audit/recent')
@login_required
def api_recent_audit():
    try:
        return json_response({
            'diffs': recent_diffs(REPORT_DIR, limit=30),
            'operations': read_recent_operations(REPORT_DIR, limit=30),
        })
    except Exception as e:
        return json_response({'error': f'读取变更记录失败：{e}'}, 500)


@app.route('/api/export/projects.csv')
@login_required
def api_export_projects_csv():
    payload = load_dashboard_payload(REPORT_DIR)
    body = export_projects_csv(payload, request.args)
    return Response(
        '\ufeff' + body,
        content_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="projects.csv"'}
    )


@app.route('/api/export/project/<path:project>.md')
@login_required
def api_export_project_md(project):
    try:
        payload = load_dashboard_payload(REPORT_DIR)
        body = export_project_markdown(payload, project)
        return Response(
            body,
            content_type='text/markdown; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{project}.md"'}
        )
    except KeyError as e:
        return json_response({'error': str(e)}, 404)


@app.route('/api/export/weekly.md')
@login_required
def api_export_weekly_md():
    payload = load_dashboard_payload(REPORT_DIR)
    week = request.args.get('week', '').strip() or payload['meta']['latest_week']
    body = export_weekly_markdown(payload, week)
    return Response(
        body,
        content_type='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="weekly-{week[:10]}.md"'}
    )

@app.route('/api/generate', methods=['POST'])
@login_required
def api_generate():
    """流式返回 AI 生成的周报内容（SSE）。"""
    project   = request.form.get('project',  '').strip()
    week      = request.form.get('week',     '').strip()
    extra     = request.form.get('extra',    '').strip()
    category  = request.form.get('category', '').strip()
    biz_scope = request.form.get('biz_scope','').strip()
    stage     = request.form.get('stage',    '').strip()
    progress  = request.form.get('progress', '').strip()
    files     = request.files.getlist('files')

    errors = validate_project_week_content(project, week, stage=stage)
    errors.extend(validate_uploads(files))
    if errors:
        return json_response({'error': '；'.join(errors)}, 400)

    return Response(
        stream_with_context(stream_weekly_generation(
            project=project, week=week, extra=extra, category=category,
            biz_scope=biz_scope, stage=stage, progress=progress, files=files,
            system_prompt=SYSTEM_PROMPT, model=GENERATION_MODEL
        )),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@app.route('/api/push', methods=['POST'])
@login_required
def api_push():
    """写入 Excel（周报内容 + 阶段 + 类别） + 更新摘要缓存 + 重新生成 dashboard.html。"""
    body      = request.get_json() or {}
    project   = body.get('project',  '').strip()
    week      = body.get('week',     '').strip()
    content   = body.get('content',  '').strip()
    stage     = body.get('stage',    '').strip()
    category  = body.get('category', '').strip()
    biz_scope = body.get('biz_scope','').strip()
    score     = str(body.get('score', '') or '').strip()
    force     = bool(body.get('force', False))

    errors = validate_project_week_content(project, week, content, stage, score, require_content=True, require_score=True)
    if errors:
        return json_response({'error': '；'.join(errors)}, 400)

    existing = get_existing_week_content(REPORT_DIR, project, week)
    try:
        before_project = get_project_row(REPORT_DIR, project)
    except Exception:
        before_project = {}
    if existing['exists'] and not force:
        return json_response({
            'error': '该项目本周已有内容',
            'duplicate': True,
            'project': project,
            'week': week,
            'existing_preview': existing['content'][:160],
        }, 409)

    try:
        result = push_to_excel(REPORT_DIR, project, week, content, stage, category, biz_scope, score)
    except Exception as e:
        log_operation(REPORT_DIR, 'push_failed', project=project, week=week, error=str(e))
        return json_response({'error': f'写入 Excel 失败：{e}'}, 500)

    try:
        update_summary_cache(REPORT_DIR, project, content)
    except Exception as e:
        log_operation(REPORT_DIR, 'summary_cache_failed', project=project, week=week, error=str(e))

    try:
        proc = subprocess.run(
            [sys.executable, 'generate_dashboard.py'],
            cwd=REPORT_DIR, capture_output=True, text=True, timeout=120
        )
        regen_ok  = proc.returncode == 0
        regen_msg = proc.stdout.strip() or proc.stderr.strip()
    except Exception as e:
        regen_ok, regen_msg = False, str(e)

    changes = []
    if result.get('old_content') != result.get('new_content'):
        changes.append({'field': 'weekly_content', 'old': result.get('old_content', ''), 'new': result.get('new_content', '')})
    if stage and before_project.get('status', '') != stage:
        changes.append({'field': 'status', 'old': before_project.get('status', ''), 'new': stage})
    if score and before_project.get('score', '') != score:
        changes.append({'field': 'score', 'old': before_project.get('score', ''), 'new': score})
    record_diffs(REPORT_DIR, project, changes, week=week, backup_path=result.get('backup_path', ''))
    try:
        payload = load_dashboard_payload(REPORT_DIR)
        sync_dashboard_data(REPORT_DIR, payload)
    except Exception as e:
        log_operation(REPORT_DIR, 'shadow_sync_failed', project=project, week=week, error=str(e))

    log_operation(
        REPORT_DIR, 'push',
        project=project, week=week, stage=stage, category=category,
        is_new=result.get('is_new', False), overwritten=existing['exists'],
        backup_path=result.get('backup_path', ''),
        regen_ok=regen_ok, regen_msg=regen_msg,
    )

    return json_response({
        'ok': True, 'project': project, 'week': week,
        'is_new': result.get('is_new', False),
        'stage': stage, 'score': score,
        'regen_ok': regen_ok, 'regen_msg': regen_msg,
        'backup_path': result.get('backup_path', ''),
        'overwritten': existing['exists'],
    })

# ── 前端模板 ────────────────────────────────────────────────────────────────
TEMPLATE_DIR = REPORTER_DIR / 'templates'

def _read_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding='utf-8')

_LOGIN_HTML = _read_template('login.html')
_PORTAL_HTML = _read_template('portal.html').replace('{{GENERATION_MODEL}}', GENERATION_MODEL)
_HTML = _read_template('reporter.html').replace('{{GENERATION_MODEL}}', GENERATION_MODEL)
_GOVERNANCE_HTML = _read_template('governance.html')
_STATUS_HTML = _read_template('status.html')

# ── 启动 ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    pwd     = os.environ.get('PORTAL_PASSWORD', 'yuhanvc')
    print('─' * 56)
    print('  战投工作台已启动')
    print()
    print(f'  打开方式：http://localhost:{APP_PORT}')
    print(f'  登录密码：{pwd}')
    print()
    print(f'  工作台 →  http://localhost:{APP_PORT}/')
    print(f'  看   板 →  http://localhost:{APP_PORT}/dashboard')
    print(f'  生成器 →  http://localhost:{APP_PORT}/reporter')
    print(f'  治   理 →  http://localhost:{APP_PORT}/governance')
    print(f'  模   型 →  {GENERATION_MODEL}')
    print()
    if api_key:
        print(f'  DeepSeek Key：已设置（...{api_key[-6:]}）')
    else:
        print('  ⚠ DEEPSEEK_API_KEY 未设置，AI 生成功能不可用')
        print('  设置方式：在 周报/.env 文件中填入 DEEPSEEK_API_KEY=sk-...')
    print('─' * 56)
    app.run(host='127.0.0.1', port=APP_PORT, debug=False, threaded=True)
