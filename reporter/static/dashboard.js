let DATA = null;
let FILTERED = [];
let DISPLAYED = [];
let donutChart = null;
let _detailProject = null;
let _detailOriginal = {};

const statusClass = {'前期沟通':'tag-gray','正式尽调':'tag-amber','协议签署/交割':'tag-blue','投后':'tag-green'};
const priorityClass = {'高':'tag-red','中':'tag-amber','低':'tag-gray'};
const scoreClass = {'1':'tag-gray','2':'tag-gray','3':'tag-blue','4':'tag-amber','5':'tag-red'};
const fallbackScoreLabels = {'1':'1 拉完了','2':'2 NPC','3':'3 人上人','4':'4 顶级','5':'5 夯爆了'};
const scoreOrder = ['5','4','3','2','1'];

// ── 排序 ────────────────────────────────────────────────────────────────────
let sortColumn = null;
let sortDirection = 0; // 0=无, 1=升序, -1=降序

const STATUS_ORDER = {'前期沟通':1,'正式尽调':2,'协议签署/交割':3,'投后':4};
const PRIORITY_ORDER = {'高':3,'中':2,'低':1};

function sortData(data, col, dir){
  if (!col || dir === 0) return [...data];
  return [...data].sort((a, b) => {
    let va = a[col] ?? '', vb = b[col] ?? '';
    if (col === 'score_label') { va = a['score'] ?? ''; vb = b['score'] ?? ''; }
    if (col === 'status') { va = STATUS_ORDER[va] ?? 0; vb = STATUS_ORDER[vb] ?? 0; return (va - vb) * dir; }
    if (col === 'priority') { va = PRIORITY_ORDER[va] ?? 0; vb = PRIORITY_ORDER[vb] ?? 0; return (va - vb) * dir; }
    if (col === 'last_active') { va = a['last_active_iso'] || a['last_active'] || ''; vb = b['last_active_iso'] || b['last_active'] || ''; }
    const na = Number(va), nb = Number(vb);
    if (!isNaN(na) && !isNaN(nb)) return (na - nb) * dir;
    return String(va).localeCompare(String(vb), 'zh-CN') * dir;
  });
}

function toggleSort(colKey){
  if (sortColumn === colKey) {
    if (sortDirection === 1) sortDirection = -1;
    else { sortDirection = 0; sortColumn = null; }
  } else {
    sortColumn = colKey;
    sortDirection = 1;
  }
  updateSortArrows();
  applyFilters();
}

function updateSortArrows(){
  document.querySelectorAll('.sort-arrow').forEach(el => el.textContent = '');
  if (sortColumn && sortDirection !== 0) {
    const arrow = document.getElementById('arrow-' + sortColumn);
    if (arrow) arrow.textContent = sortDirection === 1 ? ' ▲' : ' ▼';
  }
}
const logicCards = [
  ['过滤器 01','业务协同：第一道必答题',['与百融 Voice / BaaS / MaaS 能力能否形成技术乘法效应','能否借助百融 7,000+ 金融机构渠道打开新客户','能否为百融带来新的赋能维度（数据、场景、牌照）'],'协同弱 → 直接降级，几乎必 pass'],
  ['过滤器 02','商业模式质量',['SaaS 订阅 / 结果付费 加分；纯项目制重交付 扣分','NDR > 110%、毛利率 > 60% 为优质参考线','规模化能力：产品能否低边际成本复制客户'],'项目制为主 → 估值大幅打折'],
  ['过滤器 03','技术护城河深度',['专有数据壁垒：垂类语料、客户行为数据积累','行业 knowhow 壁垒：能否被大厂模型直接替代','头部客户深度绑定：迁移成本是否形成真实锁定'],'无护城河 → 持续关注，不深推'],
  ['过滤器 04','财务与估值',['收入规模 / 增速是否支撑融资轮次隐含估值倍数','历史融资过多架高估值时主动降低优先级','现金流 / 盈利时间线需可验证，不接受纯故事'],'估值虚高 → 谈不拢直接放弃'],
  ['过滤器 05','团队认知与动机',['创始人是否了解自身能力上限与短板（认知清醒加分）','技术与商业化能力是否均衡，偏学术基因须关注','有无套现离场动机（控股 + 全部出售 = 警示信号）'],'创始人意图存疑 → 降低优先级'],
  ['底层假设','CVC 定位约束',['战略协同优先于纯财务回报，资源撮合是核心增值','不追求"多看多投"，更倾向于精准高置信度机会','流动性 / 退出路径需在可见范围内（港股 IPO 友好）'],'脱离百融主业的机会 → 门槛自动上升'],
];

function esc(s){return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function shortWeek(label){try{const p=String(label).split('/');return p[1]+'/'+p[2].split('-')[0];}catch(e){return String(label).slice(0,5);}}
function trunc(s,n){s=String(s||'').replace(/\s+/g,' ').trim();return s.length>n?s.slice(0,n)+'…':s;}
function tag(label, cls){return `<span class="tag ${cls||'tag-gray'}">${esc(label||'')}</span>`;}
function fieldLabel(field){
  return ({weekly_content:'周报内容',status:'状态',priority:'优先级',score:'项目打分',owner:'负责人',biz_scope:'业务范畴',industry:'细分行业'}[field] || field || '字段');
}
function eventLabel(event){
  return ({push:'周报写入',project_patch:'项目资料编辑',push_failed:'写入失败',project_patch_failed:'编辑失败',shadow_sync_failed:'影子库同步失败'}[event] || event || '操作');
}

async function loadDashboard(){
  const r = await fetch('/api/dashboard-data');
  DATA = await r.json();
  if (DATA.error) throw new Error(DATA.error);
  renderAll();
}

function renderAll(){
  const m = DATA.metrics, meta = DATA.meta;
  document.getElementById('mastheadMeta').innerHTML = `<span>统计周期：${esc(meta.oldest_week.slice(0,7))} — ${esc(meta.latest_week.slice(0,7))}</span><span>项目总数：${m.total}</span><span>负责人：语涵</span><span>更新：${esc(meta.generated)}</span><span>来源：${esc(meta.source_file)}</span>`;
  document.getElementById('metrics').innerHTML = [
    ['Pipeline 总量',m.total,'含协议 / 投后项目','hi'],
    ['创新 / AI 标的',m.ai_count,`占比约 ${m.total?Math.round(m.ai_count/m.total*100):0}%`,''],
    ['本周有更新',m.active_count,meta.latest_week.slice(0,10),''],
    ['深度推进中',m.dd_count,'尽调 / 投决 / 投后',''],
    ['平均评分',m.scored_count ? m.avg_score : '—',`${m.scored_count||0}/${m.total} 已评分`,''],
  ].map(x=>`<div class="metric ${x[3]}"><div class="metric-label">${x[0]}</div><div class="metric-value">${x[1]}</div><div class="metric-sub">${x[2]}</div></div>`).join('');
  renderFilters();
  renderCharts();
  renderScores();
  renderActivities();
  renderCategories();
  renderLogic();
  renderInsights();
  applyFilters();
}

function fillSelect(id, values){
  const el=document.getElementById(id), first=el.options[0].outerHTML;
  el.innerHTML = first + values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
  el.onchange = applyFilters;
}
function renderFilters(){
  fillSelect('statusFilter', DATA.filters.statuses);
  fillSelect('priorityFilter', DATA.filters.priorities);
  fillSelect('aiFilter', DATA.filters.ai_types);
  fillSelect('categoryFilter', DATA.filters.categories);
  document.getElementById('searchInput').oninput = applyFilters;
}

function renderCharts(){
  const m=DATA.metrics;
  document.getElementById('donutLegend').innerHTML = `<span><span class="legend-dot" style="background:var(--amber);"></span>创新/AI ${m.ai_count}个</span><span><span class="legend-dot" style="background:var(--text3);"></span>传统 ${m.non_ai}个</span>`;
  const ctx=document.getElementById('donutChart').getContext('2d');
  if (donutChart && donutChart.destroy) donutChart.destroy();
  donutChart = new Chart(ctx,{type:'doughnut',data:{labels:['创新/AI','传统'],datasets:[{data:[m.ai_count,m.non_ai],backgroundColor:['#D97706','#C4BDB4'],borderColor:['#FAF7F2','#FAF7F2'],borderWidth:3}]},options:{responsive:true,maintainAspectRatio:false,cutout:'65%',plugins:{legend:{display:false}}}});
  const stages = DATA.counts.stages, labels = ['前期沟通','正式尽调','协议签署/交割','投后'].filter(s=>stages[s]);
  document.getElementById('funnelSvg').innerHTML = buildFunnel(labels.map(s=>[s,stages[s]]));
  document.getElementById('funnelFooter').textContent = `本周活跃 ${m.active_count} 个 ／ 近 8 周新增 ${m.new_count} 个`;
}
function renderScores(){
  const labels = DATA.counts.score_labels || fallbackScoreLabels;
  const scores = DATA.counts.scores || {};
  const entries = scoreOrder.filter(k=>labels[k]).map(k=>[k, labels[k], scores[k]||0]);
  const max = Math.max(1, ...entries.map(x=>x[2]));
  document.getElementById('scoreDist').innerHTML = entries.map(([score,label,count])=>`<div class="score-row">
    <div class="score-label">${esc(label)}</div>
    <div class="score-bar-wrap"><div class="score-bar score-${score}" style="width:${Math.round(count/max*100)}%;"></div></div>
    <div class="score-count">${count}</div>
  </div>`).join('');
}
function buildFunnel(rows){
  if(!rows.length) return '';
  const w=460,h=58,totalH=h*rows.length,margin=w*.105,colors=['var(--amber)','#A0781C','#8B6914','#D97706'];
  let out=`<svg viewBox="0 0 ${w} ${totalH}" style="width:100%;max-width:${w}px;display:block;margin:0 auto;">`;
  rows.forEach(([label,count],i)=>{
    const lt=margin*i,rt=w-margin*i,lb=margin*(i+1),rb=w-margin*(i+1),yt=i*h,yb=(i+1)*h,cx=w/2,cy=yt+h/2;
    out+=`<path d="M${lt},${yt} L${rt},${yt} L${rb},${yb} L${lb},${yb} Z" fill="${colors[i]||colors.at(-1)}"/>`;
    out+=`<text x="${cx}" y="${cy-9}" text-anchor="middle" font-family="Georgia,serif" font-size="12" fill="rgba(255,255,255,.82)">${esc(label)}</text><text x="${cx}" y="${cy+14}" text-anchor="middle" font-family="Courier New,monospace" font-size="19" font-weight="bold" fill="white">${count}</text>`;
  });
  return out+'</svg>';
}

function renderActivities(){
  const week=DATA.meta.latest_week;
  document.getElementById('activityLabel').textContent = '本周动态 · ' + week;
  const active = DATA.projects.filter(p => (p.timeline||[]).some(e=>e.week===week));
  document.getElementById('activityGrid').innerHTML = active.length ? active.map(p=>{
    const e=p.timeline.find(x=>x.week===week);
    return `<div class="activity-card"><div class="activity-head"><span class="activity-name">${esc(p.name)}</span><span style="margin-left:auto;">${tag(p.status,statusClass[p.status])}</span></div><div class="activity-meta">${esc(p.industry)}</div><div class="activity-snippet">${esc(trunc(e.content,90))}</div></div>`;
  }).join('') : '<div class="empty" style="display:block;">本周暂无项目更新记录</div>';
}
function renderCategories(){
  const entries=Object.entries(DATA.counts.categories).sort((a,b)=>b[1]-a[1]), max=entries[0]?.[1]||1;

  // 聚合每个大类下的细分行业
  const catInds = {};
  DATA.projects.forEach(p => {
    if (!catInds[p.category]) catInds[p.category] = [];
    if (p.industry && !catInds[p.category].includes(p.industry)) {
      catInds[p.category].push(p.industry);
    }
  });

  document.getElementById('categoryList').innerHTML=entries.map(([cat,cnt])=> {
    const inds = catInds[cat] || [];
    const sub = inds.length ? inds.join('、') : '';
    return `<div class="ind-row-wrap">
      <div class="ind-row"><div class="ind-label">${esc(cat)}</div><div class="ind-bar-wrap"><div class="ind-bar" style="width:${Math.round(cnt/max*100)}%;background:${cat.includes('AI')?'var(--amber)':'var(--text3)'};"></div></div><div class="ind-cnt">${cnt}</div></div>
      ${sub ? `<div class="ind-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }).join('');
}
function renderLogic(){
  document.getElementById('logicGrid').innerHTML = logicCards.map(c=>`<div class="logic-card"><div class="logic-num">${c[0]}</div><div class="logic-title">${c[1]}</div><ul class="logic-items">${c[2].map(i=>`<li>${esc(i)}</li>`).join('')}</ul><div class="logic-verdict">${esc(c[3])}</div></div>`).join('');
}
function renderInsights(){
  const m=DATA.metrics, stages=DATA.counts.stages, cats=Object.entries(DATA.counts.categories||{}).sort((a,b)=>b[1]-a[1]);
  const pct=(n,d)=>d?Math.round(n/d*100):0;
  const names=(arr,n=5)=>arr.slice(0,n).map(p=>p.name).join('、') || '暂无';
  const front=stages['前期沟通']||0;
  const dd=DATA.projects.filter(p=>p.status&&p.status!=='前期沟通');
  const active=DATA.projects.filter(p=>(p.timeline||[]).some(e=>e.week===DATA.meta.latest_week));
  const newest=DATA.projects.filter(p=>p.is_new);
  const voice=DATA.projects.filter(p=>['语音','外呼','质检','CC'].some(k=>String(p.industry||'').includes(k)));
  const high=DATA.projects.filter(p=>p.priority==='高');
  const aiSub=cats.filter(([c])=>c.includes('AI')||c.includes('工业')).length;
  const topCats=cats.slice(0,3).map(([c,n])=>`${c}（${n}个）`).join('、') || '暂无';
  const cards=[
    ['漏斗质量','深推资源集中在少数高置信度标的',
      `当前 Pipeline 仍是典型前置漏斗，适合继续用战略协同和商业质量做强筛选，而不是追求平均推进。`,
      `${front} 个项目停留在前期沟通，占 ${pct(front,m.total)}%；进入正式尽调、协议或投后阶段的项目共 ${dd.length} 个：${names(dd,4)}。`,
      '维持前期扫描宽度，但对进入尽调的标的设置更明确的协同验证清单，优先确认客户渠道、产品互补和估值可谈性。'],
    ['AI 结构','创新标的覆盖广，但深推仍需要收敛主线',
      `创新/AI 是覆盖重心，说明 Sourcing 方向正确；下一步重点不是继续扩概念，而是从广覆盖转向可复用场景。`,
      `创新/AI 标的 ${m.ai_count} 个，占 ${pct(m.ai_count,m.total)}%；已覆盖 ${aiSub} 个 AI 相关子赛道，Top 3 大类为 ${topCats}。`,
      '把非核心 AI 项目按“可卖给金融客户 / 可增强百融产品 / 可形成数据闭环”三类重排，筛掉协同弱但叙事强的机会。'],
    ['主线赛道','语音 / 对话 AI 仍是最接近百融能力边界的方向',
      `与 BaaS、Voice 和金融机构渠道的连接最直接，适合作为 AI 投资主线，而不是与通用 Agent 或营销工具同等处理。`,
      `语音、外呼、质检、CC 相关项目共 ${voice.length} 个，代表项目包括 ${names(voice,4)}。`,
      '对该方向建立单独比较表，横向比较客户结构、交付深度、毛利率、数据壁垒和百融渠道导入难度。'],
    ['近期活跃','本周推进高度集中，说明实际工作负荷由少数项目驱动',
      `本周活跃项目数量不高，但更能反映真实精力投放；要避免低价值项目用零散沟通持续占用跟进时间。`,
      `${DATA.meta.latest_week} 有更新的项目 ${active.length} 个：${names(active,6)}；其余 ${Math.max(m.total-active.length,0)} 个项目本周无新增记录。`,
      '对连续多周无更新且无明确下一步的项目标记为低触达，仅保留关键事件触发式跟进。'],
    ['Sourcing 新增','近 8 周仍有新增，入口活跃但需要更快分层',
      `新增项目证明外部扫描没有停，但如果不快速分层，会稀释对高质量标的的判断时间。`,
      `近 8 周新进入 Pipeline 的项目 ${m.new_count} 个，包括 ${names(newest,6)}。`,
      '新增项目首轮统一输出一句投资假设、一条核心风险和一个下一步验证动作；两周内不能形成假设的项目降频。'],
    ['资源配置','高优先级和深推项目需要形成明确的周度动作闭环',
      `看板已经能反映状态，但下一步要让状态真正驱动动作，尤其是高优先级、尽调和协议阶段项目。`,
      `高优先级项目 ${high.length} 个；深度推进项目 ${dd.length} 个；本周活跃项目 ${active.length} 个。`,
      '每周例会只重点讨论高优先级和深推项目的阻塞项、负责人和截止时间，其他项目以批量扫读为主。'],
  ];
  document.getElementById('insights').innerHTML = `<div class="insight-grid">${cards.map(c=>`<article class="insight-card"><div class="insight-kicker">${esc(c[0])}</div><h3>${esc(c[1])}</h3><p><span>判断</span>${esc(c[2])}</p><p><span>数据</span>${esc(c[3])}</p><p><span>动作</span>${esc(c[4])}</p></article>`).join('')}</div>`;
}

function applyFilters(){
  const q=document.getElementById('searchInput').value.toLowerCase().trim(), st=document.getElementById('statusFilter').value, pr=document.getElementById('priorityFilter').value, ai=document.getElementById('aiFilter').value, cat=document.getElementById('categoryFilter').value;
  FILTERED=DATA.projects.filter(p=>{
    const hay=[p.name,p.category,p.industry,p.status,p.priority,p.score,p.score_label,p.owner].join(' ').toLowerCase();
    return (!q||hay.includes(q))&&(!st||p.status===st)&&(!pr||p.priority===pr)&&(!cat||p.category===cat)&&(!ai||(ai==='创新/AI'?p.is_ai:!p.is_ai));
  });
  renderTable();
  const params=new URLSearchParams();
  if(q)params.set('q',q); if(st)params.set('status',st); if(pr)params.set('priority',pr); if(ai)params.set('ai',ai); if(cat)params.set('category',cat);
  document.getElementById('exportCsv').href='/api/export/projects.csv'+(params.toString()?`?${params}`:'');
  document.getElementById('exportWeekly').href='/api/export/weekly.md?week='+encodeURIComponent(DATA.meta.latest_week);
}
function renderTable(){
  const sorted = sortData(FILTERED, sortColumn, sortDirection);
  DISPLAYED = sorted;
  document.getElementById('tableLabel').textContent=`全项目追踪（${FILTERED.length}/${DATA.projects.length} 个）—— 点击行查看详情`;
  document.getElementById('projTbody').innerHTML = sorted.map((p,i)=>{
    const snippet=p.latest_content || (p.timeline?.[0]?.content || '');
    const aiDot=p.is_ai?'<span class="ai-dot" title="创新/AI"></span>':'<span class="ai-dot" style="background:transparent;border:.5px solid var(--border2);"></span>';
    return `<tr onclick="openDetail(${i})" style="cursor:pointer;"><td><span class="tbl-name">${aiDot}${esc(p.name)}</span></td><td class="tbl-cell">${esc(p.category)}</td><td class="tbl-cell">${esc(p.industry)}</td><td>${tag(p.status,statusClass[p.status])}</td><td>${tag(p.priority,priorityClass[p.priority])}</td><td>${tag(p.score_label||'未评分',scoreClass[p.score])}</td><td class="tbl-cell tbl-snippet">${esc(trunc(snippet,70))||'<span style="color:var(--text3)">—</span>'}</td><td class="tbl-week">${p.last_active?shortWeek(p.last_active):'—'}</td></tr>`;
  }).join('');
  document.getElementById('noResult').style.display = FILTERED.length ? 'none' : 'block';
}

function openDetail(idx){
  const p=DISPLAYED[idx];
  _detailProject = p.name;
  _detailOriginal = {};
  p.timeline.forEach(e => { _detailOriginal[e.week] = e.content; });
  document.getElementById('dp-name').textContent=p.name;
  const aiDot=p.is_ai?'<span class="ai-dot" title="创新/AI" style="display:inline-block;"></span>':'';
  document.getElementById('dp-badges').innerHTML=`${aiDot}${tag(p.status,statusClass[p.status])}${tag(p.score_label||'未评分',scoreClass[p.score])}${tag(p.industry,'tag-gray')}<span class="detail-owner">${esc(p.owner)}</span>`;
  document.getElementById('exportProjectBtn').onclick=()=>{location.href='/api/export/project/'+encodeURIComponent(p.name)+'.md';};
  document.getElementById('dp-body').innerHTML = buildEditForm(p)
    + `<div class="detail-section-label">最近变更</div><div id="audit-list" class="audit-list"><div class="empty" style="display:block;padding:8px 0;text-align:left;">正在读取…</div></div>`
    + `<div class="detail-section-label">进展时间轴（${p.timeline.length} 条记录，最新在前）</div>`
    + (p.timeline.length?p.timeline.map(e=>`<div class="tl-entry" id="tl-${esc(e.week)}"><div class="tl-week">${esc(e.week)}</div><div class="tl-summary">${esc(e.medium||e.content.slice(0,130))}</div><details><summary>查看原文</summary><div class="tl-raw">${esc(e.content)}</div></details><button class="tl-edit-btn" onclick="editTimelineNode(event,'${esc(e.week)}')">编辑</button></div>`).join(''):'<div class="empty" style="display:block;">暂无历史记录</div>');
  document.getElementById('modal-overlay').classList.add('open');
  document.body.style.overflow='hidden';
  loadAudit(p.name);
}
function buildEditForm(p){
  const statusOpts=['前期沟通','正式尽调','协议签署/交割','投后'].map(v=>`<option value="${v}" ${p.status===v?'selected':''}>${v}</option>`).join('');
  const prOpts=['','高','中','低'].map(v=>`<option value="${v}" ${p.priority===v?'selected':''}>${v||'未设置'}</option>`).join('');
  const labels = DATA.counts.score_labels || fallbackScoreLabels;
  const scoreOpts=['',...scoreOrder.filter(v=>labels[v])].map(v=>`<option value="${v}" ${p.score===v?'selected':''}>${v?labels[v]:'未评分'}</option>`).join('');
  return `<div class="detail-section-label">项目资料编辑</div>
  <div class="edit-grid">
    <label>状态<select id="edit-status">${statusOpts}</select></label>
    <label>优先级<select id="edit-priority">${prOpts}</select></label>
    <label>项目打分<select id="edit-score">${scoreOpts}</select></label>
    <label>负责人<input id="edit-owner" value="${esc(p.owner||'')}"></label>
    <label>业务范畴<input id="edit-biz" value="${esc(p.biz_scope||p.biz||'')}"></label>
    <label>细分行业<input id="edit-industry" value="${esc(p.industry||'')}"></label>
  </div>
  <button class="export-link" onclick="saveProjectEdit('${encodeURIComponent(p.name)}')">保存项目资料</button>
  <span class="edit-status" id="edit-status-msg"></span>`;
}
async function saveProjectEdit(encodedName){
  const msg=document.getElementById('edit-status-msg');
  msg.textContent='正在保存…';
  const body={
    status:document.getElementById('edit-status').value,
    priority:document.getElementById('edit-priority').value,
    score:document.getElementById('edit-score').value,
    owner:document.getElementById('edit-owner').value.trim(),
    biz_scope:document.getElementById('edit-biz').value.trim(),
    industry:document.getElementById('edit-industry').value.trim(),
  };
  const r=await fetch('/api/projects/'+encodedName,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const res=await r.json();
  if(!r.ok){msg.textContent='保存失败：'+(res.error||'未知错误');return;}
  msg.textContent='已保存';
  await loadDashboard();
  const idx = DISPLAYED.findIndex(p => p.name === _detailProject);
  if (idx >= 0) openDetail(idx);
}
async function loadAudit(name){
  const el=document.getElementById('audit-list');
  if(!el) return;
  try{
    const r=await fetch('/api/audit/project/'+encodeURIComponent(name));
    const res=await r.json();
    if(!r.ok) throw new Error(res.error||'读取失败');
    const diffs=(res.diffs||[]).slice(0,8);
    const ops=(res.operations||[]).slice(0,5);
    if(!diffs.length && !ops.length){
      el.innerHTML='<div class="empty" style="display:block;padding:8px 0;text-align:left;">暂无写入或编辑记录</div>';
      return;
    }
    const diffHtml=diffs.map(d=>`<div class="audit-row"><div class="audit-main"><span>${esc(fieldLabel(d.field))}</span>${d.week?`<span class="audit-week">${esc(d.week)}</span>`:''}</div><div class="audit-sub">${esc(trunc(d.old_value,46)||'空')} → ${esc(trunc(d.new_value,46)||'空')}</div><div class="audit-time">${esc(d.ts)}</div></div>`).join('');
    const opHtml=ops.map(o=>`<div class="audit-row audit-op"><div class="audit-main"><span>${esc(eventLabel(o.event))}</span>${o.week?`<span class="audit-week">${esc(o.week)}</span>`:''}</div><div class="audit-sub">${o.regen_ok===false?'看板重建失败':(o.overwritten?'覆盖原内容':'')}</div><div class="audit-time">${esc(o.ts)}</div></div>`).join('');
    el.innerHTML=diffHtml+opHtml;
  }catch(e){
    el.innerHTML='<div class="empty" style="display:block;padding:8px 0;text-align:left;">变更记录读取失败：'+esc(e.message)+'</div>';
  }
}
function closeDetail(){document.getElementById('modal-overlay').classList.remove('open');document.body.style.overflow='';}
function handleOverlayClick(e){if(e.target===document.getElementById('modal-overlay'))closeDetail();}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail();});

// ── 时间轴编辑 ──────────────────────────────────────────────────────────────
function editTimelineNode(e, week){
  e.stopPropagation();
  if (!_detailProject) return;
  const el = document.getElementById('tl-' + week);
  if (!el) return;
  const original = _detailOriginal[week] || '';
  el.innerHTML = `<div class="tl-week">${esc(week)}</div>
    <textarea class="tl-edit-area">${esc(original)}</textarea>
    <div class="tl-edit-actions">
      <button class="btn-tl-save" onclick="saveTimelineEdit(event,'${esc(week)}')">保存</button>
      <button class="btn-tl-cancel" onclick="cancelTimelineEdit(event,'${esc(week)}')">取消</button>
      <span class="tl-edit-status"></span>
    </div>`;
}

async function saveTimelineEdit(e, week){
  e.stopPropagation();
  if (!_detailProject) return;
  const el = document.getElementById('tl-' + week);
  if (!el) return;
  const textarea = el.querySelector('.tl-edit-area');
  const statusEl = el.querySelector('.tl-edit-status');
  const content = textarea ? textarea.value.trim() : '';
  if (!content) { if (statusEl) statusEl.textContent = '内容不能为空'; return; }
  if (statusEl) statusEl.textContent = '正在保存…';
  try {
    const r = await fetch('/api/projects/' + encodeURIComponent(_detailProject) + '/week/' + encodeURIComponent(week), {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content: content})
    });
    const res = await r.json();
    if (!r.ok) { if (statusEl) statusEl.textContent = '保存失败：' + (res.error || '未知错误'); return; }
    if (statusEl) statusEl.textContent = '已保存';
    await loadDashboard();
    const idx = DISPLAYED.findIndex(p => p.name === _detailProject);
    if (idx >= 0) openDetail(idx);
  } catch(err) {
    if (statusEl) statusEl.textContent = '网络错误：' + err.message;
  }
}

function cancelTimelineEdit(e, week){
  e.stopPropagation();
  if (!_detailProject) return;
  const el = document.getElementById('tl-' + week);
  if (!el) return;
  const original = _detailOriginal[week] || '';
  el.innerHTML = `<div class="tl-week">${esc(week)}</div>
    <div class="tl-summary">${esc(original.slice(0,130))}</div>
    <details><summary>查看原文</summary><div class="tl-raw">${esc(original)}</div></details>
    <button class="tl-edit-btn" onclick="editTimelineNode(event,'${esc(week)}')">编辑</button>`;
}

loadDashboard().catch(e=>{document.body.innerHTML=`<div class="page"><div class="masthead"><h1>看板加载失败</h1><div class="masthead-meta">${esc(e.message)}</div></div></div>`;});
