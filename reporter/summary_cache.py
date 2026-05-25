"""Summary-cache helpers shared by dashboard generation and reporter writes."""

import hashlib
import json
import os
import re
from pathlib import Path


def clean_text(s: str) -> str:
    return re.sub(r'\s+', ' ', str(s).replace('\n', ' ').replace('\r', '')).strip()


def cache_key(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:16]


def project_entry_key(project: str, content: str) -> str:
    return cache_key(project + clean_text(content))


def cache_path(report_dir) -> Path:
    return Path(report_dir) / '.summaries_cache.json'


def load_cache(report_dir) -> dict:
    p = cache_path(report_dir)
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def save_cache(report_dir, cache: dict):
    cache_path(report_dir).write_text(
        json.dumps(cache, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8'
    )


def make_short_summary(content: str) -> str:
    """<=20字节点标签：剥掉前缀杂质，取第一个有意义的小句。"""
    s = re.sub(r'^[\s\d]+[、.．。]', '', content.strip())
    s = re.sub(r'^[（(]\d+[)）][、.]?\s*', '', s)
    s = re.sub(r'^【[^】]{0,10}】\s*', '', s)
    s = re.sub(r'^(本周|本阶段|近期|目前|最新|当前|跟进：|进展：)\s*', '', s)
    s = re.sub(r'^核心结论[：:]\s*', '', s)
    s = s.strip()
    for sep in ('。', '！', '？'):
        pos = s.find(sep)
        if 0 < pos <= 20:
            return s[:pos + 1]
    for sep in ('，', ',', '；', ';', '：', ':'):
        pos = s.find(sep)
        if 0 < pos <= 16:
            return s[:pos + 1]
    return s[:16] + ('…' if len(s) > 16 else '')


def make_medium_summary(content: str) -> str:
    """提取前2句完整句子（约80-130字）作为详情摘要。"""
    s = content.strip()
    sentences, buf = [], ''
    for ch in s:
        buf += ch
        if ch in ('。', '！', '？'):
            sentences.append(buf.strip())
            buf = ''
            if len(''.join(sentences)) >= 80:
                break
    if not sentences:
        return s[:120] + ('…' if len(s) > 120 else '')
    result = ''.join(sentences)
    return result[:150] + ('…' if len(result) > 150 else result)


def update_summary_cache(report_dir, project: str, content: str):
    cache = load_cache(report_dir)
    content_norm = clean_text(content)
    cache[project_entry_key(project, content_norm)] = {
        'short': make_short_summary(content_norm),
        'medium': make_medium_summary(content_norm),
    }
    save_cache(report_dir, cache)
