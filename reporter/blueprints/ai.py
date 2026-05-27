"""
reporter/blueprints/ai.py — AI 生成 + 推送 API。
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from flask import Blueprint, request, g, jsonify, Response, stream_with_context
from reporter.middleware.auth import require_auth
from reporter.middleware.rate_limit import ai_limit
from reporter.ai_service import stream_weekly_generation
from reporter.services.project_service import push_weekly_content, get_existing_week_content, get_project_detail
from reporter.summary_cache import update_summary_cache
from reporter.validation import validate_project_week_content, validate_uploads
from reporter.operation_log import log_operation
from config import settings

ai_bp = Blueprint("ai", __name__)

# ── Skill 加载 ──────────────────────────────────────────────────────────────
import zipfile


def _load_skill(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            for fn in z.namelist():
                if fn.endswith(".md"):
                    return z.read(fn).decode("utf-8")
    except Exception:
        pass
    return ""


_SYSTEM_PROMPT = ""
if settings.SKILL_ROOT and settings.SKILL_ROOT.exists():
    it_path = settings.SKILL_ROOT / "【Skill】investment taste/语涵的investment-taste.skill"
    ws_path = settings.SKILL_ROOT / "【Skill】yuhan writing style/yuhan-writing-style.skill"
    skill_it = _load_skill(it_path) if it_path.exists() else ""
    skill_ws = _load_skill(ws_path) if ws_path.exists() else ""

    if skill_ws and skill_it:
        _SYSTEM_PROMPT = f"""{skill_ws}

---

{skill_it}

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


# ═══════════════════════════════════════════════════════════════════════════
# AI 生成
# ═══════════════════════════════════════════════════════════════════════════

@ai_bp.route("/api/generate", methods=["POST"])
@require_auth
@ai_limit
def api_generate():
    project = request.form.get("project", "").strip()
    week = request.form.get("week", "").strip()
    extra = request.form.get("extra", "").strip()
    category = request.form.get("category", "").strip()
    biz_scope = request.form.get("biz_scope", "").strip()
    stage = request.form.get("stage", "").strip()
    progress = request.form.get("progress", "").strip()
    files = request.files.getlist("files")

    errors = validate_project_week_content(project, week, stage=stage)
    errors.extend(validate_uploads(files))
    if errors:
        return jsonify({"error": "；".join(errors)}), 400

    file_data = []
    for f in files:
        try:
            file_data.append((f.filename or "", f.read()))
        except Exception as e:
            return jsonify({"error": f"读取文件 {f.filename} 失败：{e}"}), 400

    return Response(
        stream_with_context(stream_weekly_generation(
            project=project, week=week, extra=extra, category=category,
            biz_scope=biz_scope, stage=stage, progress=progress, file_data=file_data,
            system_prompt=_SYSTEM_PROMPT, db_session=g.db,
        )),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 推送至数据库
# ═══════════════════════════════════════════════════════════════════════════

@ai_bp.route("/api/push", methods=["POST"])
@require_auth
@ai_limit
def api_push():
    body = request.get_json() or {}
    project = body.get("project", "").strip()
    week = body.get("week", "").strip()
    content = body.get("content", "").strip()
    stage = body.get("stage", "").strip()
    category = body.get("category", "").strip()
    biz_scope = body.get("biz_scope", "").strip()
    score = str(body.get("score", "") or "").strip()
    force = bool(body.get("force", False))

    errors = validate_project_week_content(
        project, week, content, stage, score,
        require_content=True, require_score=True,
    )
    if errors:
        return jsonify({"error": "；".join(errors)}), 400

    existing = get_existing_week_content(g.db, project, week)
    if existing["exists"] and not force:
        return jsonify({
            "error": "该项目本周已有内容",
            "duplicate": True, "project": project, "week": week,
            "existing_preview": existing["content"][:160],
        }), 409

    try:
        result = push_weekly_content(
            g.db, project, week, content,
            stage=stage, category=category, biz_scope=biz_scope, score=score,
            user_id=g.current_user.get("user_id"),
        )
    except Exception as e:
        log_operation(settings.REPORT_DIR, "push_failed", project=project, week=week, error=str(e))
        return jsonify({"error": f"写入数据库失败：{e}"}), 500

    # 记录操作日志
    log_operation(settings.REPORT_DIR, "push",
                  project=project, week=week, stage=stage, category=category,
                  is_new=result.get("is_new", False), overwritten=existing["exists"])

    return jsonify({
        "ok": True, "project": project, "week": week,
        "is_new": result.get("is_new", False),
        "stage": stage, "score": score,
        "overwritten": existing["exists"],
    })
