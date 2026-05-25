"""HTML rendering for the investment pipeline dashboard."""

import json
import os
from collections import Counter, defaultdict

try:
    from .dashboard_data import esc, truncate, week_short
    from .statuses import FUNNEL_STAGES, normalize_status, priority_order, priority_tag, status_order, status_tag
    from .summary_cache import cache_key, load_cache, make_medium_summary, make_short_summary, save_cache
except ImportError:
    from dashboard_data import esc, truncate, week_short
    from statuses import FUNNEL_STAGES, normalize_status, priority_order, priority_tag, status_order, status_tag
    from summary_cache import cache_key, load_cache, make_medium_summary, make_short_summary, save_cache

_SUMMARY_MODEL = 'claude-3-5-haiku-20241022'

_SUMMARY_PROMPT = """\
你是一位 CVC 战投分析助手，请对以下一周进展记录生成简洁摘要。

项目：{name}
周次：{week}
周报原文：
{content}

输出格式（直接输出两行，不加任何其他内容）：
SHORT: [15字以内，核心进展/动向，名词短语，不以"本周"开头]
MEDIUM: [70字以内，1-2句完整话，涵盖关键事项与后续动向]"""


def _summarize_entry(name: str, week: str, content: str, client) -> tuple:
    """调用 Claude API，返回 (short, medium) 摘要对。"""
    try:
        msg = client.messages.create(
            model=_SUMMARY_MODEL,
            max_tokens=160,
            messages=[{
                'role': 'user',
                'content': _SUMMARY_PROMPT.format(
                    name=name, week=week, content=content[:600]
                )
            }]
        )
        text = msg.content[0].text.strip()
        short = make_short_summary(content)
        medium = make_medium_summary(content)
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('SHORT:'):
                v = line[6:].strip()
                if v:
                    short = v
            elif line.startswith('MEDIUM:'):
                v = line[7:].strip()
                if v:
                    medium = v
        return short, medium
    except Exception as ex:
        print(f'    ⚠ LLM 摘要失败 ({name} {week}): {ex}')
        return make_short_summary(content), make_medium_summary(content)


def status_span(s: str) -> str:
    cls, label = status_tag(s)
    return f'<span class="tag {cls}">{esc(label)}</span>'


def priority_span(s: str) -> str:
    cls, label = priority_tag(s)
    return f'<span class="tag {cls}">{esc(label)}</span>'

# ── SVG 漏斗 ────────────────────────────────────────────────────────────────

def generate_funnel_svg(funnel_data: list) -> str:
    if not funnel_data:
        return ''
    n        = len(funnel_data)
    total_w  = 460
    stage_h  = 58
    total_h  = stage_h * n
    margin   = total_w * 0.105
    COLORS   = ['#1a1a18', '#3d3d37', '#6a6a62', '#b87316', '#1d6b2e']

    parts = [
        f'<svg viewBox="0 0 {total_w} {total_h}" '
        f'style="width:100%;max-width:{total_w}px;display:block;margin:0 auto;">'
    ]
    for i, (label, count) in enumerate(funnel_data):
        color = COLORS[min(i, len(COLORS) - 1)]
        lt = margin * i;        rt = total_w - margin * i
        lb = margin * (i + 1); rb = total_w - margin * (i + 1)
        yt = i * stage_h;       yb = (i + 1) * stage_h
        d = f'M{lt:.1f},{yt} L{rt:.1f},{yt} L{rb:.1f},{yb} L{lb:.1f},{yb} Z'
        parts.append(f'  <path d="{d}" fill="{color}"/>')
        if i < n - 1:
            parts.append(f'  <line x1="{lb:.1f}" y1="{yb}" x2="{rb:.1f}" y2="{yb}" '
                         f'stroke="rgba(255,255,255,0.25)" stroke-width="1"/>')
        cx = total_w / 2; cy = yt + stage_h / 2
        parts.append(f'  <text x="{cx}" y="{cy-9}" text-anchor="middle" '
                     f'font-family="Georgia,serif" font-size="12" fill="rgba(255,255,255,0.82)">'
                     f'{esc(label)}</text>')
        parts.append(f'  <text x="{cx}" y="{cy+14}" text-anchor="middle" '
                     f'font-family="Courier New,monospace" font-size="19" font-weight="bold" fill="white">'
                     f'{count}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)


# ── 行业大类 HTML 列表 ──────────────────────────────────────────────────────

def generate_category_list(projects: list) -> str:
    # 聚合
    cat_cnt   = defaultdict(int)
    cat_inds  = defaultdict(list)
    for p in projects:
        cat  = p['category']
        ind  = p['industry']
        cat_cnt[cat]  += 1
        if ind and ind not in cat_inds[cat]:
            cat_inds[cat].append(ind)

    ordered = sorted(cat_cnt.items(), key=lambda x: -x[1])
    max_cnt  = ordered[0][1] if ordered else 1

    _AI_CATS = {'AI 语音 / 对话', 'AI Agent / 大模型', 'AI 营销 / GEO',
                'AI 金融 / 投研', 'AI 招聘 / HR', 'AI 工具 / 效率', '工业 AI'}

    rows = []
    for cat, cnt in ordered:
        pct       = round(cnt / max_cnt * 100)
        bar_color = '#1a1a18' if cat in _AI_CATS else '#c8c6c0'
        sub_inds  = '、'.join(cat_inds[cat][:5])
        if len(cat_inds[cat]) > 5:
            sub_inds += f' +{len(cat_inds[cat])-5}'
        rows.append(f'''
    <div class="ind-row">
      <div class="ind-label">{esc(cat)}</div>
      <div class="ind-bar-wrap" title="{esc(sub_inds)}">
        <div class="ind-bar" style="width:{pct}%;background:{bar_color};"></div>
      </div>
      <div class="ind-cnt">{cnt}</div>
      <div class="ind-sub">{esc(sub_inds)}</div>
    </div>''')

    return f'<div class="ind-list">{"".join(rows)}</div>'


# ── 投资逻辑框架 ────────────────────────────────────────────────────────────

LOGIC_CARDS = [
    {
        'num': '过滤器 01', 'title': '业务协同：第一道必答题',
        'items': ['与百融 Voice / BaaS / MaaS 能力能否形成技术乘法效应',
                  '能否借助百融 7,000+ 金融机构渠道打开新客户',
                  '能否为百融带来新的赋能维度（数据、场景、牌照）'],
        'verdict': '协同弱 → 直接降级，几乎必 pass',
    },
    {
        'num': '过滤器 02', 'title': '商业模式质量',
        'items': ['SaaS 订阅 / 结果付费 加分；纯项目制重交付 扣分',
                  'NDR > 110%、毛利率 > 60% 为优质参考线',
                  '规模化能力：产品能否低边际成本复制客户'],
        'verdict': '项目制为主 → 估值大幅打折',
    },
    {
        'num': '过滤器 03', 'title': '技术护城河深度',
        'items': ['专有数据壁垒：垂类语料、客户行为数据积累',
                  '行业 knowhow 壁垒：能否被大厂模型直接替代',
                  '头部客户深度绑定：迁移成本是否形成真实锁定'],
        'verdict': '无护城河 → 持续关注，不深推',
    },
    {
        'num': '过滤器 04', 'title': '财务与估值',
        'items': ['收入规模 / 增速是否支撑融资轮次隐含估值倍数',
                  '历史融资过多架高估值时主动降低优先级',
                  '现金流 / 盈利时间线需可验证，不接受纯故事'],
        'verdict': '估值虚高 → 谈不拢直接放弃',
    },
    {
        'num': '过滤器 05', 'title': '团队认知与动机',
        'items': ['创始人是否了解自身能力上限与短板（认知清醒加分）',
                  '技术与商业化能力是否均衡，偏学术基因须关注',
                  '有无套现离场动机（控股 + 全部出售 = 警示信号）'],
        'verdict': '创始人意图存疑 → 降低优先级',
    },
    {
        'num': '底层假设', 'title': 'CVC 定位约束',
        'items': ['战略协同优先于纯财务回报，资源撮合是核心增值',
                  '不追求"多看多投"，更倾向于精准高置信度机会',
                  '流动性 / 退出路径需在可见范围内（港股 IPO 友好）'],
        'verdict': '脱离百融主业的机会 → 门槛自动上升',
    },
]


def generate_logic_cards() -> str:
    cards = ''
    for c in LOGIC_CARDS:
        items = ''.join(f'<li>{esc(it)}</li>' for it in c['items'])
        cards += f'''
    <div class="logic-card">
      <div class="logic-num">{esc(c["num"])}</div>
      <div class="logic-title">{esc(c["title"])}</div>
      <ul class="logic-items">{items}</ul>
      <div class="logic-verdict">{esc(c["verdict"])}</div>
    </div>'''
    return cards


# ── 结构性观察 ──────────────────────────────────────────────────────────────

def generate_insights(data: dict, stats: dict) -> str:
    projects   = data['projects']
    total      = stats['total']
    ai_count   = stats['ai_count']
    active     = stats['active_count']
    new_count  = stats['new_count']
    dd_count   = stats['dd_count']
    stage_cnt  = stats['stage_cnt']
    front      = stage_cnt.get('前期沟通', 0)

    dd_names     = [p['name'] for p in projects if p['status'] not in ('前期沟通', '')]
    active_names = [p['name'] for p in projects if p['is_active']]
    voice_projs  = [p['name'] for p in projects
                    if any(k in p['industry'] for k in ('语音', '外呼', '质检', 'CC'))]
    new_projs    = [p['name'] for p in projects if p['is_new']]
    high_names    = [p['name'] for p in projects if p.get('priority') == '高']
    cat_cnt      = Counter(p['category'] for p in projects)
    top3_cats    = [f'{k}（{v}个）' for k, v in cat_cnt.most_common(3)]
    ai_sub_count = len([c for c in cat_cnt if 'AI' in c or '工业' in c])

    def pct(n: int, d: int) -> int:
        return round(n / d * 100) if d else 0

    def sample(items: list, limit: int = 5) -> str:
        return '、'.join(items[:limit]) or '暂无'

    cards = [
        {
            'kicker': '漏斗质量',
            'title': '深推资源集中在少数高置信度标的',
            'judgement': '当前 Pipeline 仍是典型前置漏斗，适合继续用战略协同和商业质量做强筛选，而不是追求平均推进。',
            'data': f'{front} 个项目停留在前期沟通，占 {pct(front,total)}%；进入正式尽调、协议或投后阶段的项目共 {dd_count} 个：{sample(dd_names, 4)}。',
            'action': '维持前期扫描宽度，但对进入尽调的标的设置更明确的协同验证清单，优先确认客户渠道、产品互补和估值可谈性。',
        },
        {
            'kicker': 'AI 结构',
            'title': '创新标的覆盖广，但深推仍需要收敛主线',
            'judgement': '创新/AI 是覆盖重心，说明 Sourcing 方向正确；下一步重点不是继续扩概念，而是从广覆盖转向可复用场景。',
            'data': f'创新/AI 标的 {ai_count} 个，占 {pct(ai_count,total)}%；已覆盖 {ai_sub_count} 个 AI 相关子赛道，Top 3 大类为 {"、".join(top3_cats) or "暂无"}。',
            'action': '把非核心 AI 项目按“可卖给金融客户 / 可增强百融产品 / 可形成数据闭环”三类重排，筛掉协同弱但叙事强的机会。',
        },
        {
            'kicker': '主线赛道',
            'title': '语音 / 对话 AI 仍是最接近百融能力边界的方向',
            'judgement': '与 BaaS、Voice 和金融机构渠道的连接最直接，适合作为 AI 投资主线，而不是与通用 Agent 或营销工具同等处理。',
            'data': f'语音、外呼、质检、CC 相关项目共 {len(voice_projs)} 个，代表项目包括 {sample(voice_projs, 4)}。',
            'action': '对该方向建立单独比较表，横向比较客户结构、交付深度、毛利率、数据壁垒和百融渠道导入难度。',
        },
        {
            'kicker': '近期活跃',
            'title': '本周推进高度集中，说明实际工作负荷由少数项目驱动',
            'judgement': '本周活跃项目数量不高，但更能反映真实精力投放；要避免低价值项目用零散沟通持续占用跟进时间。',
            'data': f'{data["latest_week"]} 有更新的项目 {active} 个：{sample(active_names, 6)}；其余 {max(total - active, 0)} 个项目本周无新增记录。',
            'action': '对连续多周无更新且无明确下一步的项目标记为低触达，仅保留关键事件触发式跟进。',
        },
        {
            'kicker': 'Sourcing 新增',
            'title': '近 8 周仍有新增，入口活跃但需要更快分层',
            'judgement': '新增项目证明外部扫描没有停，但如果不快速分层，会稀释对高质量标的的判断时间。',
            'data': f'近 8 周新进入 Pipeline 的项目 {new_count} 个，包括 {sample(new_projs, 6)}。',
            'action': '新增项目首轮统一输出一句投资假设、一条核心风险和一个下一步验证动作；两周内不能形成假设的项目降频。',
        },
        {
            'kicker': '资源配置',
            'title': '高优先级和深推项目需要形成明确的周度动作闭环',
            'judgement': '看板已经能反映状态，但下一步要让状态真正驱动动作，尤其是高优先级、尽调和协议阶段项目。',
            'data': f'高优先级项目 {len(high_names)} 个；深度推进项目 {dd_count} 个；本周活跃项目 {active} 个。',
            'action': '每周例会只重点讨论高优先级和深推项目的阻塞项、负责人和截止时间，其他项目以批量扫读为主。',
        },
    ]
    items = ''
    for c in cards:
        items += f'''
    <article class="insight-card">
      <div class="insight-kicker">{esc(c["kicker"])}</div>
      <h3>{esc(c["title"])}</h3>
      <p><span>判断</span>{esc(c["judgement"])}</p>
      <p><span>数据</span>{esc(c["data"])}</p>
      <p><span>动作</span>{esc(c["action"])}</p>
    </article>'''
    return f'<div class="insight-grid">{items}</div>'


# ── 项目 JSON（用于详情抽屉）──────────────────────────────────────────────

def build_projects_json(projects: list, script_dir: str = '') -> str:
    # ── 先加载本地缓存（无论有没有 API key 都读）──
    cache = load_cache(script_dir)
    client = None
    if cache:
        print(f'  摘要缓存已加载（{len(cache)} 条）')

    # ── 若有 API key，对缓存未命中的条目调用 LLM ──
    if os.environ.get('ANTHROPIC_API_KEY'):
        try:
            import anthropic as _ant
            client = _ant.Anthropic()
            print('  AI 摘要模式已启用，缓存未命中时将调用 API')
        except ImportError:
            print('  提示：pip install anthropic 后可启用 AI 周报摘要')

    all_pairs = [(p, e) for p in projects for e in p['timeline']]
    total = len(all_pairs)
    new_cnt = 0

    # ── 批量生成摘要（未命中缓存时调用 API）──
    summary_map: dict = {}
    for i, (p, e) in enumerate(all_pairs):
        key = cache_key(p['name'] + e['content'])
        if key in cache:
            summary_map[key] = cache[key]
        elif client:
            if i % 20 == 0 or i == total - 1:
                print(f'  AI 摘要进度：{i + 1}/{total}…')
            short, medium = _summarize_entry(p['name'], e['week'], e['content'], client)
            cache[key] = summary_map[key] = {'short': short, 'medium': medium}
            new_cnt += 1
        else:
            summary_map[key] = {
                'short':  make_short_summary(e['content']),
                'medium': make_medium_summary(e['content']),
            }

    if new_cnt:
        save_cache(script_dir, cache)
        print(f'  已缓存 {new_cnt} 条新 AI 摘要 → .summaries_cache.json')

    # ── 组装 JSON ──
    data = []
    for p in projects:
        tl = []
        for e in p['timeline']:
            key = cache_key(p['name'] + e['content'])
            sm = summary_map[key]
            tl.append({
                'week':    e['week'],
                'content': e['content'],
                'short':   sm['short'],
                'medium':  sm['medium'],
            })
        data.append({
            'name':     p['name'],
            'industry': p['industry'],
            'category': p['category'],
            'status':   p['status'],
            'owner':    p['owner'],
            'score':    p.get('score', ''),
            'score_label': p.get('score_label', ''),
            'is_ai':    p['is_ai'],
            'biz':      p['biz_scope'],
            'timeline': tl,
        })
    return json.dumps(data, ensure_ascii=False)


# ── 主 HTML 生成 ────────────────────────────────────────────────────────────

def generate_html(data: dict) -> str:
    projects    = data['projects']
    week_cols   = data['week_cols']
    latest_week = data['latest_week']
    oldest_week = data['oldest_week']
    generated   = data['generated']
    source_file = data['source_file']

    total        = len(projects)
    ai_count     = sum(1 for p in projects if p['is_ai'])
    non_ai       = total - ai_count
    active_count = sum(1 for p in projects if p['is_active'])
    new_count    = sum(1 for p in projects if p['is_new'])
    dd_count     = sum(1 for p in projects
                       if normalize_status(p['status']) not in ('前期沟通', ''))

    funnel_norm = Counter()
    for p in projects:
        if p['status']:
            funnel_norm[normalize_status(p['status'])] += 1
    funnel_data = [(s, funnel_norm[s]) for s in FUNNEL_STAGES if funnel_norm.get(s, 0) > 0]
    for s, c in funnel_norm.items():
        if s not in FUNNEL_STAGES:
            funnel_data.append((s, c))

    stats = {
        'total': total, 'ai_count': ai_count, 'non_ai': non_ai,
        'active_count': active_count, 'new_count': new_count,
        'dd_count': dd_count, 'stage_cnt': dict(funnel_norm),
    }

    funnel_svg    = generate_funnel_svg(funnel_data)
    category_html = generate_category_list(projects)
    logic_html    = generate_logic_cards()
    insights_html = generate_insights(data, stats)
    projects_json = build_projects_json(projects, data.get('script_dir', ''))
    donut_data    = json.dumps([ai_count, non_ai])

    # 本周动态卡片
    active_projects = [p for p in projects if p['is_active']]
    cards_html = ''
    for p in active_projects:
        snippet   = esc(truncate(p['latest_content'], 90))
        new_badge = '<span class="tag tag-green" style="font-size:9px;padding:1px 5px;">NEW</span> ' if p['is_new'] else ''
        cards_html += f'''
        <div class="activity-card">
          <div class="activity-head">
            {new_badge}<span class="activity-name">{esc(p["name"])}</span>
            <span style="margin-left:auto;">{status_span(p["status"])}</span>
          </div>
          <div class="activity-meta">{esc(p["industry"])}</div>
          <div class="activity-snippet">{snippet}</div>
        </div>'''
    if not cards_html:
        cards_html = '<div style="color:var(--text3);font-size:13px;padding:20px 0;">本周暂无项目更新记录</div>'

    # 全项目表
    table_rows = ''
    for idx, p in enumerate(projects):
        s_order  = status_order(p['status'])
        pr_order = priority_order(p['priority'])
        snippet_src = p['latest_content'] or p['last_content']
        snippet  = esc(truncate(snippet_src, 70)) if snippet_src else '<span style="color:var(--text3)">—</span>'
        last_wk  = week_short(p['last_active']) if p['last_active'] else '—'
        ai_dot   = '<span class="ai-dot" title="创新/AI"></span>' if p['is_ai'] else '<span class="ai-dot" style="background:transparent;border:.5px solid var(--border2);"></span>'
        new_badge = ' <span class="tag tag-green" style="font-size:9px;padding:1px 5px;">NEW</span>' if p['is_new'] else ''
        table_rows += f'''
        <tr onclick="openDetail({idx})" style="cursor:pointer;">
          <td data-name="{esc(p["name"])}"><span class="tbl-name">{ai_dot}{esc(p["name"])}</span>{new_badge}</td>
          <td class="tbl-cell" data-category="{esc(p["category"])}">{esc(p["category"])}</td>
          <td class="tbl-cell" data-industry="{esc(p["industry"])}">{esc(p["industry"])}</td>
          <td data-status="{s_order}">{status_span(p["status"])}</td>
          <td data-priority="{pr_order}">{priority_span(p["priority"])}</td>
          <td class="tbl-cell tbl-snippet">{snippet}</td>
          <td class="tbl-week" data-date="{p["last_active_iso"]}">{last_wk}</td>
        </tr>'''

    period_str = f'{oldest_week[:7]} — {latest_week[:7]}' if oldest_week and latest_week else '—'

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline 动态看板 · 语涵</title>
<style>
  :root {{
    --bg:#faf9f7; --bg2:#f2f0eb; --bg3:#ffffff;
    --border:rgba(0,0,0,0.08); --border2:rgba(0,0,0,0.14);
    --text:#1a1a18; --text2:#5c5b55; --text3:#8e8d86;
    --amber:#b87316; --amber-bg:#fef3e0; --amber-border:#f0c070;
    --blue:#185fa5; --blue-bg:#eaf2fc;
    --green:#1d6b2e; --green-bg:#edf5e0;
    --red:#9b2c2c; --red-bg:#fdf0f0;
    --r:8px; --r2:12px;
  }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Georgia','Noto Serif SC',serif;background:var(--bg);color:var(--text);line-height:1.6;font-size:14px;}}

  /* ── 全宽布局 ── */
  .page{{width:100%;padding:40px 4% 80px;}}

  .masthead{{border-bottom:1.5px solid var(--text);padding-bottom:20px;margin-bottom:36px;}}
  .masthead-label{{font-family:'Courier New',monospace;font-size:11px;letter-spacing:.12em;color:var(--text3);text-transform:uppercase;margin-bottom:8px;}}
  .masthead h1{{font-size:28px;font-weight:normal;letter-spacing:-.5px;line-height:1.2;}}
  .masthead-meta{{margin-top:10px;display:flex;gap:24px;flex-wrap:wrap;font-family:'Courier New',monospace;font-size:11px;color:var(--text3);}}

  .section{{margin-bottom:48px;}}
  .section-label{{font-family:'Courier New',monospace;font-size:10px;letter-spacing:.14em;color:var(--text3);text-transform:uppercase;border-top:.5px solid var(--border2);padding-top:12px;margin-bottom:20px;}}

  .metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:36px;}}
  .metric{{background:var(--bg3);border:.5px solid var(--border2);border-radius:var(--r);padding:16px;}}
  .metric-label{{font-family:'Courier New',monospace;font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;}}
  .metric-value{{font-size:32px;font-weight:normal;line-height:1;color:var(--text);}}
  .metric-sub{{font-size:11px;color:var(--text3);margin-top:4px;}}
  .metric.hi{{background:var(--text);}}
  .metric.hi .metric-label{{color:rgba(255,255,255,.5);}}
  .metric.hi .metric-value{{color:#fff;}}
  .metric.hi .metric-sub{{color:rgba(255,255,255,.4);}}

  .chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:20px;}}
  .chart-box{{background:var(--bg3);border:.5px solid var(--border2);border-radius:var(--r2);padding:20px;}}
  .chart-title{{font-size:12px;font-weight:bold;letter-spacing:.03em;margin-bottom:16px;color:var(--text2);}}
  .chart-wrap{{position:relative;}}

  .funnel-svg-wrap{{padding:8px 0 4px;}}
  .funnel-footer{{margin-top:14px;font-family:'Courier New',monospace;font-size:10px;color:var(--text3);}}

  .legend{{display:flex;gap:16px;margin-top:12px;justify-content:center;font-family:'Courier New',monospace;font-size:11px;color:var(--text3);}}
  .legend-dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle;}}

  /* 行业大类 */
  .ind-list{{padding:4px 0;}}
  .ind-row{{display:grid;grid-template-columns:160px 1fr 30px;align-items:center;gap:10px;padding:5px 0;}}
  .ind-label{{font-family:'Georgia',serif;font-size:13px;color:var(--text2);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .ind-bar-wrap{{background:var(--bg2);border-radius:2px;height:22px;overflow:hidden;cursor:default;position:relative;}}
  .ind-bar{{height:100%;border-radius:2px;transition:width .3s;}}
  .ind-cnt{{font-family:'Courier New',monospace;font-size:12px;color:var(--text2);text-align:right;}}
  .ind-sub{{grid-column:2/4;font-size:10px;color:var(--text3);font-family:'Courier New',monospace;padding-left:2px;margin-top:-2px;margin-bottom:2px;}}

  /* tags */
  .tag{{display:inline-block;font-family:'Courier New',monospace;font-size:10px;padding:2px 7px;border-radius:3px;letter-spacing:.04em;white-space:nowrap;}}
  .tag-amber{{background:var(--amber-bg);color:var(--amber);border:.5px solid var(--amber-border);}}
  .tag-blue{{background:var(--blue-bg);color:var(--blue);}}
  .tag-green{{background:var(--green-bg);color:var(--green);}}
  .tag-red{{background:var(--red-bg);color:var(--red);}}
  .tag-gray{{background:var(--bg2);color:var(--text3);}}

  /* 本周动态 */
  .activity-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;}}
  .activity-card{{background:var(--bg3);border:.5px solid var(--border2);border-radius:var(--r);padding:14px;}}
  .activity-head{{display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap;}}
  .activity-name{{font-size:13px;font-weight:bold;color:var(--text);}}
  .activity-meta{{font-size:11px;color:var(--text3);font-family:'Courier New',monospace;margin-bottom:6px;}}
  .activity-snippet{{font-size:12px;color:var(--text2);line-height:1.55;}}

  /* 表格 */
  .table-toolbar{{display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap;}}
  .search-wrap{{position:relative;flex:1;min-width:180px;}}
  .search-wrap input{{width:100%;padding:8px 12px 8px 34px;border:.5px solid var(--border2);border-radius:var(--r);background:var(--bg3);font-family:'Georgia',serif;font-size:13px;color:var(--text);outline:none;}}
  .search-wrap input:focus{{border-color:var(--text);}}
  .search-icon{{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--text3);font-size:13px;pointer-events:none;}}

  .proj-table{{width:100%;border-collapse:collapse;}}
  .proj-table th{{font-family:'Courier New',monospace;font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;padding:8px 10px;border-bottom:.5px solid var(--border2);text-align:left;font-weight:normal;white-space:nowrap;cursor:pointer;user-select:none;}}
  .proj-table th:hover{{color:var(--text2);}}
  .proj-table th.th-sorted{{color:var(--text);}}
  .sort-btn{{margin-left:4px;font-size:9px;opacity:.5;}}
  .proj-table td{{padding:9px 10px;border-bottom:.5px solid var(--border);font-size:13px;vertical-align:top;}}
  .proj-table tr:last-child td{{border-bottom:none;}}
  .proj-table tr:hover td{{background:var(--bg);}}
  .proj-table tr.hidden{{display:none;}}
  .tbl-name{{font-weight:bold;color:var(--text);display:flex;align-items:center;gap:5px;}}
  .tbl-cell{{color:var(--text2);font-size:12px;}}
  .tbl-snippet{{max-width:300px;}}
  .tbl-week{{font-family:'Courier New',monospace;font-size:10px;color:var(--text3);white-space:nowrap;}}
  .ai-dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#1a1a18;flex-shrink:0;}}

  /* ── 项目详情弹窗 ── */
  #modal-overlay{{
    display:none;position:fixed;inset:0;
    background:rgba(0,0,0,0.42);z-index:200;
    align-items:center;justify-content:center;padding:20px;
  }}
  #modal-overlay.open{{display:flex;}}
  #modal-box{{
    background:var(--bg3);border-radius:var(--r2);
    width:860px;max-width:96vw;max-height:88vh;overflow-y:auto;
    padding:28px 32px 36px;position:relative;
    box-shadow:0 24px 64px rgba(0,0,0,0.24);
  }}
  .modal-close{{
    position:absolute;top:18px;right:20px;font-size:18px;
    cursor:pointer;color:var(--text3);background:none;border:none;line-height:1;
  }}
  .modal-close:hover{{color:var(--text);}}
  .detail-proj-name{{font-size:22px;font-weight:normal;margin-bottom:10px;padding-right:32px;line-height:1.3;}}
  .detail-badges{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px;align-items:center;}}
  .detail-owner{{font-family:'Courier New',monospace;font-size:10px;color:var(--text3);}}
  .detail-section-label{{font-family:'Courier New',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--text3);border-top:.5px solid var(--border2);padding-top:12px;margin-bottom:14px;margin-top:4px;}}
  /* 横向时间轴 */
  .htl-container{{overflow-x:auto;padding-bottom:4px;}}
  .htl-track{{display:flex;position:relative;height:160px;min-width:max-content;}}
  .htl-line{{position:absolute;top:50%;left:0;right:0;height:1px;background:var(--border2);z-index:0;}}
  .htl-node{{width:120px;flex-shrink:0;position:relative;height:100%;cursor:pointer;}}
  .htl-node:hover .htl-dot{{background:var(--text2);}}
  .htl-dot{{
    position:absolute;top:50%;left:50%;
    transform:translate(-50%,-50%);
    width:9px;height:9px;border-radius:50%;
    background:var(--text3);border:2px solid var(--bg3);
    z-index:2;transition:all .15s;
  }}
  .htl-node.selected .htl-dot{{background:var(--amber);width:12px;height:12px;border-color:var(--amber-border);}}
  .htl-label-top{{position:absolute;bottom:calc(50% + 16px);left:4px;right:4px;text-align:center;}}
  .htl-label-bot{{position:absolute;top:calc(50% + 16px);left:4px;right:4px;text-align:center;}}
  .htl-week-lbl{{display:block;font-family:'Courier New',monospace;font-size:9px;color:var(--text3);margin-bottom:2px;}}
  .htl-short-lbl{{display:block;font-size:10px;color:var(--text2);line-height:1.35;word-break:break-all;}}
  .htl-node.selected .htl-short-lbl{{color:var(--text);font-weight:bold;}}
  .htl-detail-box{{background:var(--bg);border-radius:var(--r);padding:16px;margin-top:14px;}}
  .htl-detail-week{{font-family:'Courier New',monospace;font-size:10px;color:var(--text3);margin-bottom:8px;}}
  .htl-detail-summary{{font-size:13px;color:var(--text);line-height:1.75;}}
  .htl-raw-toggle{{
    display:inline-flex;align-items:center;gap:5px;margin-top:12px;
    font-family:'Courier New',monospace;font-size:10px;color:var(--text3);
    cursor:pointer;background:none;border:none;padding:2px 0;user-select:none;
  }}
  .htl-raw-toggle:hover{{color:var(--text2);}}
  .htl-raw-arrow{{display:inline-block;transition:transform .2s;}}
  .htl-raw-arrow.open{{transform:rotate(180deg);}}
  .htl-raw-box{{
    background:var(--bg2);border:.5px solid var(--border2);border-radius:6px;
    padding:12px 14px;margin-top:8px;
    font-size:12px;color:var(--text2);line-height:1.65;
    white-space:pre-wrap;word-break:break-all;
    max-height:180px;overflow-y:auto;
  }}

  /* 投资逻辑 */
  .logic-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
  .logic-card{{background:var(--bg3);border:.5px solid var(--border2);border-radius:var(--r2);padding:18px;}}
  .logic-num{{font-family:'Courier New',monospace;font-size:11px;color:var(--text3);margin-bottom:6px;}}
  .logic-title{{font-size:14px;font-weight:bold;margin-bottom:10px;color:var(--text);}}
  .logic-items{{list-style:none;}}
  .logic-items li{{font-size:12px;color:var(--text2);padding:4px 0;border-bottom:.5px solid var(--border);line-height:1.5;}}
  .logic-items li:last-child{{border-bottom:none;}}
  .logic-verdict{{margin-top:10px;font-family:'Courier New',monospace;font-size:10px;color:var(--text3);padding:6px 10px;background:var(--bg);border-radius:4px;}}

  /* 结构性观察 */
  .insight-box{{background:var(--text);color:#fff;border-radius:var(--r2);padding:24px 28px;}}
  .insight-box .section-label{{color:rgba(255,255,255,.35);border-top-color:rgba(255,255,255,.15);}}
  .insight-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;}}
  .insight-card{{background:rgba(255,255,255,.055);border:.5px solid rgba(255,255,255,.16);border-radius:var(--r);padding:16px 16px 15px;min-width:0;}}
  .insight-kicker{{font-family:'Courier New',monospace;font-size:10px;letter-spacing:.1em;color:rgba(255,255,255,.42);text-transform:uppercase;margin-bottom:6px;}}
  .insight-card h3{{font-size:15px;line-height:1.45;font-weight:normal;color:#fff;margin-bottom:12px;}}
  .insight-card p{{font-size:12px;line-height:1.68;color:rgba(255,255,255,.74);margin-top:9px;}}
  .insight-card p span{{display:inline-block;margin-right:7px;padding:1px 5px;border-radius:3px;background:rgba(255,255,255,.1);font-family:'Courier New',monospace;font-size:9px;letter-spacing:.08em;color:rgba(255,255,255,.58);}}

  @media(max-width:1100px){{
    .insight-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}
  }}
  @media(max-width:900px){{
    .logic-grid{{grid-template-columns:1fr 1fr;}}
    .chart-row{{grid-template-columns:1fr;}}
  }}
  @media(max-width:600px){{
    .metrics{{grid-template-columns:1fr 1fr;}}
    .logic-grid,.insight-grid{{grid-template-columns:1fr;}}
    .insight-box{{padding:22px 18px;}}
    .insight-card{{padding:14px;}}
    #modal-box{{padding:20px 16px 28px;}}
  }}
</style>
</head>
<body>
<div class="page">

<div class="masthead">
  <div class="masthead-label">战投 · 投资 Pipeline Dashboard</div>
  <h1>投资 Pipeline 动态看板</h1>
  <div class="masthead-meta">
    <span>统计周期：{period_str}</span>
    <span>项目总数：{total}</span>
    <span>负责人：语涵</span>
    <span>更新：{generated}</span>
    <span>来源：{esc(source_file)}</span>
  </div>
</div>

<div class="metrics">
  <div class="metric hi">
    <div class="metric-label">Pipeline 总量</div>
    <div class="metric-value">{total}</div>
    <div class="metric-sub">含协议 / 投后项目</div>
  </div>
  <div class="metric">
    <div class="metric-label">创新 / AI 标的</div>
    <div class="metric-value">{ai_count}</div>
    <div class="metric-sub">占比约 {round(ai_count/total*100) if total else 0}%</div>
  </div>
  <div class="metric">
    <div class="metric-label">本周有更新</div>
    <div class="metric-value">{active_count}</div>
    <div class="metric-sub">{latest_week[:10] if latest_week else '—'}</div>
  </div>
  <div class="metric">
    <div class="metric-label">深度推进中</div>
    <div class="metric-value">{dd_count}</div>
    <div class="metric-sub">尽调 / 投决 / 投后</div>
  </div>
</div>

<div class="chart-row section">
  <div class="chart-box">
    <div class="chart-title">创新 vs 传统分布</div>
    <div class="chart-wrap" style="height:220px;">
      <canvas id="donutChart"></canvas>
    </div>
    <div class="legend">
      <span><span class="legend-dot" style="background:#1a1a18;"></span>创新/AI {ai_count}个</span>
      <span><span class="legend-dot" style="background:#d4d2cc;"></span>传统 {non_ai}个</span>
    </div>
  </div>
  <div class="chart-box">
    <div class="chart-title">投资漏斗</div>
    <div class="funnel-svg-wrap">{funnel_svg}</div>
    <div class="funnel-footer">本周活跃 {active_count} 个 ／ 近 8 周新增 {new_count} 个</div>
  </div>
</div>

<div class="section">
  <div class="section-label">本周动态 · {esc(latest_week)}</div>
  <div class="activity-grid">{cards_html}</div>
</div>

<div class="section">
  <div class="section-label">行业大类分布（自动归类）</div>
  <div class="chart-box">
    <div class="chart-title">各大类标的数量（悬停查看细分行业）</div>
    {category_html}
  </div>
</div>

<div class="section">
  <div class="section-label">全项目追踪（共 {total} 个）—— 点击行查看详情</div>
  <div class="table-toolbar">
    <div class="search-wrap">
      <span class="search-icon">🔍</span>
      <input type="text" id="searchInput" placeholder="搜索项目名 / 行业 / 状态…" oninput="filterTable()">
    </div>
  </div>
  <div style="background:var(--bg3);border:.5px solid var(--border2);border-radius:var(--r2);overflow:hidden;">
    <table class="proj-table" id="projTable">
      <thead>
        <tr>
          <th data-sort="0" onclick="sortTable(0)" style="width:150px;">项目 <span class="sort-btn" id="sb0">⇅</span></th>
          <th data-sort="1" onclick="sortTable(1)" style="width:110px;">行业大类 <span class="sort-btn" id="sb1">⇅</span></th>
          <th data-sort="2" onclick="sortTable(2)" style="width:130px;">细分行业 <span class="sort-btn" id="sb2">⇅</span></th>
          <th data-sort="3" onclick="sortTable(3)" style="width:88px;">状态 <span class="sort-btn" id="sb3">⇅</span></th>
          <th data-sort="4" onclick="sortTable(4)" style="width:52px;">优先级 <span class="sort-btn" id="sb4">⇅</span></th>
          <th>最近动态摘要</th>
          <th data-sort="6" onclick="sortTable(6)" style="width:58px;">最后活跃 <span class="sort-btn" id="sb6">⇅</span></th>
        </tr>
      </thead>
      <tbody id="projTbody">{table_rows}</tbody>
    </table>
  </div>
  <div id="noResult" style="display:none;text-align:center;padding:24px;color:var(--text3);font-size:13px;">无匹配结果</div>
</div>

<div class="section">
  <div class="section-label">投资逻辑框架提炼（从 {total} 个项目分析归纳）</div>
  <div class="logic-grid">{logic_html}</div>
</div>

<div class="insight-box">
  <div class="section-label">结构性观察</div>
  {insights_html}
</div>

</div><!-- /page -->

<!-- 项目详情弹窗 -->
<div id="modal-overlay" onclick="handleOverlayClick(event)">
  <div id="modal-box">
    <button class="modal-close" onclick="closeDetail()">✕</button>
    <div class="detail-proj-name" id="dp-name"></div>
    <div class="detail-badges" id="dp-badges"></div>
    <div id="dp-body"></div>
  </div>
</div>

<script src="/static/vendor/chart.umd.js"></script>
<script>
// ── 数据 ──────────────────────────────────────────────────────────────────
const PROJECTS = {projects_json};

// ── 甜甜圈 ────────────────────────────────────────────────────────────────
new Chart(document.getElementById('donutChart').getContext('2d'), {{
  type: 'doughnut',
  data: {{
    labels: ['创新/AI','传统'],
    datasets: [{{ data: {donut_data}, backgroundColor: ['#1a1a18','#d4d2cc'],
      borderColor: ['#faf9f7','#faf9f7'], borderWidth: 3, hoverOffset: 4 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false, cutout: '65%',
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.label}}: ${{ctx.raw}}个 (${{Math.round(ctx.raw/{total}*100)}}%)` }} }}
    }}
  }}
}});

// ── 搜索 ──────────────────────────────────────────────────────────────────
function filterTable() {{
  const q = document.getElementById('searchInput').value.toLowerCase().trim();
  const rows = document.querySelectorAll('#projTbody tr');
  let visible = 0;
  rows.forEach(row => {{
    const show = !q || row.textContent.toLowerCase().includes(q);
    row.classList.toggle('hidden', !show);
    if (show) visible++;
  }});
  document.getElementById('noResult').style.display = visible === 0 ? 'block' : 'none';
}}

// ── 排序 ──────────────────────────────────────────────────────────────────
let _sortCol = -1, _sortDir = 1;
function sortTable(col) {{
  _sortDir = _sortCol === col ? _sortDir * -1 : 1;
  _sortCol = col;
  const tbody = document.getElementById('projTbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const val = row => {{
    const c = row.cells;
    if (col===0) return (c[0].getAttribute('data-name')||'').toLowerCase();
    if (col===1) return (c[1].getAttribute('data-category')||'').toLowerCase();
    if (col===2) return (c[2].getAttribute('data-industry')||'').toLowerCase();
    if (col===3) return parseInt(c[3].getAttribute('data-status')||99);
    if (col===4) return parseInt(c[4].getAttribute('data-priority')||99);
    if (col===6) return c[6].getAttribute('data-date')||'0000-00-00';
    return '';
  }};
  rows.sort((a,b)=>{{ const av=val(a),bv=val(b); return typeof av==='number'?_sortDir*(av-bv):_sortDir*av.localeCompare(bv,'zh-CN'); }});
  rows.forEach(r=>tbody.appendChild(r));
  for(let i of [0,1,2,3,4,6]){{
    const sb=document.getElementById('sb'+i); if(sb)sb.textContent='⇅';
    const th=document.querySelector(`th[data-sort="${{i}}"]`); if(th)th.classList.remove('th-sorted');
  }}
  const sb=document.getElementById('sb'+col); if(sb)sb.textContent=_sortDir===1?'▲':'▼';
  const th=document.querySelector(`th[data-sort="${{col}}"]`); if(th)th.classList.add('th-sorted');
  filterTable();
}}

// ── 项目详情弹窗 ──────────────────────────────────────────────────────────
const STATUS_CLASS = {{
  '前期沟通':'tag-gray','正式尽调':'tag-amber',
  '协议签署/交割':'tag-blue','投后':'tag-green'
}};
const STATUS_LABEL = {{
  '前期沟通':'前期沟通','正式尽调':'正式尽调',
  '协议签署/交割':'协议/交割','投后':'投后'
}};
let _currentTimeline = [];

function escHtml(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}
function weekShortJs(label) {{
  try {{
    const parts = String(label).split('/');
    return "'" + parts[0].slice(2) + ' ' + parts[1] + '/' + parts[2].split('-')[0];
  }} catch(e) {{ return String(label).slice(0, 7); }}
}}
function openDetail(idx) {{
  const p = PROJECTS[idx];
  document.getElementById('dp-name').textContent = p.name;
  const aiDot = p.is_ai ? '<span class="ai-dot" title="创新/AI" style="display:inline-block;"></span>' : '';
  const stCls = STATUS_CLASS[p.status]||'tag-gray';
  const stLbl = STATUS_LABEL[p.status]||p.status;
  document.getElementById('dp-badges').innerHTML =
    `${{aiDot}}<span class="tag ${{stCls}}">${{escHtml(stLbl)}}</span>
     <span class="tag tag-gray">${{escHtml(p.industry)}}</span>
     <span class="detail-owner">${{escHtml(p.owner)}}</span>`;
  _currentTimeline = [...p.timeline].reverse();
  document.getElementById('dp-body').innerHTML = buildTimelineHtml(_currentTimeline);
  document.getElementById('modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  if (_currentTimeline.length > 0) selectTlNode(_currentTimeline.length - 1);
}}
function buildTimelineHtml(items) {{
  if (items.length === 0)
    return '<div style="color:var(--text3);font-size:13px;margin-top:16px;">暂无历史记录</div>';
  let nodes = '';
  items.forEach((entry, i) => {{
    const posClass = i % 2 === 0 ? 'htl-label-top' : 'htl-label-bot';
    const wLbl = escHtml(weekShortJs(entry.week));
    const sLbl = escHtml(entry.short || String(entry.content).slice(0, 16));
    nodes += `<div class="htl-node" data-n="${{i}}" onclick="selectTlNode(${{i}})">
      <div class="htl-dot"></div>
      <div class="${{posClass}}">
        <span class="htl-week-lbl">${{wLbl}}</span>
        <span class="htl-short-lbl">${{sLbl}}</span>
      </div>
    </div>`;
  }});
  return `<div class="detail-section-label">进展时间轴（${{items.length}} 条记录，左旧右新）</div>
  <div class="htl-container">
    <div class="htl-track" id="htl-track">
      <div class="htl-line"></div>
      ${{nodes}}
    </div>
  </div>
  <div class="htl-detail-box">
    <div class="htl-detail-week" id="htl-sel-week"></div>
    <div class="htl-detail-summary" id="htl-sel-summary"></div>
    <button class="htl-raw-toggle" onclick="toggleRaw()">
      查看原文&nbsp;<span class="htl-raw-arrow" id="htl-raw-arrow">▾</span>
    </button>
    <div class="htl-raw-box" id="htl-raw-box" style="display:none;">
      <div id="htl-raw-content"></div>
    </div>
  </div>`;
}}
function selectTlNode(n) {{
  const entry = _currentTimeline[n];
  if (!entry) return;
  document.querySelectorAll('#htl-track .htl-node').forEach((el, i) => {{
    el.classList.toggle('selected', i === n);
  }});
  document.getElementById('htl-sel-week').textContent = entry.week;
  document.getElementById('htl-sel-summary').textContent = entry.medium || entry.content.slice(0, 130);
  const rawContent = document.getElementById('htl-raw-content');
  if (rawContent) rawContent.textContent = entry.content;
  // 切换节点时收起原文
  const rawBox = document.getElementById('htl-raw-box');
  const rawArrow = document.getElementById('htl-raw-arrow');
  if (rawBox) rawBox.style.display = 'none';
  if (rawArrow) rawArrow.classList.remove('open');
  const node = document.querySelectorAll('#htl-track .htl-node')[n];
  if (node) node.scrollIntoView({{behavior:'smooth', block:'nearest', inline:'center'}});
}}
function toggleRaw() {{
  const rawBox = document.getElementById('htl-raw-box');
  const rawArrow = document.getElementById('htl-raw-arrow');
  if (!rawBox) return;
  const isOpen = rawBox.style.display !== 'none';
  rawBox.style.display = isOpen ? 'none' : 'block';
  if (rawArrow) rawArrow.classList.toggle('open', !isOpen);
}}
function closeDetail() {{
  document.getElementById('modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}}
function handleOverlayClick(e) {{
  if (e.target === document.getElementById('modal-overlay')) closeDetail();
}}
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeDetail(); }});
</script>
</body>
</html>'''
