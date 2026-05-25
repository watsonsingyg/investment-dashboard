"""Shared status and priority vocabulary for the weekly report app."""

FUNNEL_STAGES = ['前期沟通', '正式尽调', '协议签署/交割', '投后']

STATUS_ALIASES = {
    '前期沟通': '前期沟通',
    '尽调准备': '正式尽调',
    '财务/法律尽调': '正式尽调',
    '正式尽调': '正式尽调',
    '投决通过&协议沟通': '协议签署/交割',
    '协议签署/交割': '协议签署/交割',
    '投后项目': '投后',
    '投后': '投后',
}

STATUS_TAG = {
    '前期沟通': ('tag-gray', '前期沟通'),
    '正式尽调': ('tag-amber', '正式尽调'),
    '协议签署/交割': ('tag-blue', '协议/交割'),
    '投后': ('tag-green', '投后'),
}

PRIORITY_ORDER = ['高', '中', '低']
PRIORITY_TAG = {
    '高': ('tag-red', '高'),
    '中': ('tag-amber', '中'),
    '低': ('tag-gray', '低'),
}

SCORE_OPTIONS = ['1', '2', '3', '4', '5']
SCORE_DISPLAY_ORDER = ['5', '4', '3', '2', '1']
SCORE_LABELS = {
    '1': '1 拉完了',
    '2': '2 NPC',
    '3': '3 人上人',
    '4': '4 顶级',
    '5': '5 夯爆了',
}


def normalize_status(status: str) -> str:
    status = str(status or '').strip()
    return STATUS_ALIASES.get(status, status)


def status_order(status: str) -> int:
    status = normalize_status(status)
    return FUNNEL_STAGES.index(status) if status in FUNNEL_STAGES else 99


def priority_order(priority: str) -> int:
    priority = str(priority or '').strip()
    return PRIORITY_ORDER.index(priority) if priority in PRIORITY_ORDER else 99


def status_tag(status: str) -> tuple:
    status = normalize_status(status)
    return STATUS_TAG.get(status, ('tag-gray', status))


def priority_tag(priority: str) -> tuple:
    priority = str(priority or '').strip()
    return PRIORITY_TAG.get(priority, ('tag-gray', priority))


def normalize_score(score) -> str:
    raw = str(score or '').strip()
    if raw.endswith('.0'):
        raw = raw[:-2]
    return raw if raw in SCORE_OPTIONS else ''


def score_label(score) -> str:
    return SCORE_LABELS.get(normalize_score(score), '')
