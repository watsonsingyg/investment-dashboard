"""Input validation for reporter API writes and uploads."""

from pathlib import Path

try:
    from .dashboard_data import is_week_header
    from .statuses import FUNNEL_STAGES, PRIORITY_ORDER, SCORE_OPTIONS
except ImportError:
    from dashboard_data import is_week_header
    from statuses import FUNNEL_STAGES, PRIORITY_ORDER, SCORE_OPTIONS

ALLOWED_UPLOAD_EXTS = {'.pdf', '.docx', '.txt', '.xlsx', '.md', '.csv'}
MAX_SINGLE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_CONTENT_CHARS = 50000
MAX_PROJECT_CHARS = 80


def validate_project_week_content(project: str, week: str, content: str = '',
                                  stage: str = '', score: str = '',
                                  require_content: bool = False,
                                  require_score: bool = False) -> list:
    errors = []
    if not project:
        errors.append('缺少项目名称')
    elif len(project) > MAX_PROJECT_CHARS:
        errors.append(f'项目名称过长，最多 {MAX_PROJECT_CHARS} 个字符')
    if not week:
        errors.append('缺少周次')
    elif not is_week_header(week):
        errors.append('周次格式应为 YYYY/MM/DD-YYYY/MM/DD')
    if stage and stage not in FUNNEL_STAGES:
        errors.append('项目阶段不在允许范围内')
    score = str(score or '').strip()
    if require_score and not score:
        errors.append('请选择项目打分')
    if score and score not in SCORE_OPTIONS:
        errors.append('项目打分应为 1 / 2 / 3 / 4 / 5')
    if require_content and not content:
        errors.append('内容为空')
    if content and len(content) > MAX_CONTENT_CHARS:
        errors.append(f'内容过长，最多 {MAX_CONTENT_CHARS} 个字符')
    return errors


def validate_uploads(files) -> list:
    errors = []
    total = 0
    for f in files:
        filename = f.filename or ''
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXTS:
            errors.append(f'{filename or "未命名文件"} 格式不支持')
            continue
        pos = f.stream.tell()
        f.stream.seek(0, 2)
        size = f.stream.tell()
        f.stream.seek(pos)
        total += size
        if size > MAX_SINGLE_UPLOAD_BYTES:
            errors.append(f'{filename} 超过 10MB 单文件限制')
    if total > MAX_TOTAL_UPLOAD_BYTES:
        errors.append('上传文件总大小超过 25MB')
    return errors


def validate_project_patch(fields: dict) -> list:
    errors = []
    allowed = {'status', 'priority', 'owner', 'biz_scope', 'industry', 'score'}
    unknown = set(fields) - allowed
    if unknown:
        errors.append('存在不支持的字段：' + '、'.join(sorted(unknown)))
    status = str(fields.get('status', '') or '').strip()
    priority = str(fields.get('priority', '') or '').strip()
    if status and status not in FUNNEL_STAGES:
        errors.append('项目阶段不在允许范围内')
    if priority and priority not in PRIORITY_ORDER:
        errors.append('优先级应为 高 / 中 / 低')
    score = str(fields.get('score', '') or '').strip()
    if score and score not in SCORE_OPTIONS:
        errors.append('项目打分应为 1 / 2 / 3 / 4 / 5')
    for key in ('owner', 'biz_scope', 'industry'):
        if len(str(fields.get(key, '') or '')) > 120:
            errors.append(f'{key} 过长，最多 120 个字符')
    return errors
