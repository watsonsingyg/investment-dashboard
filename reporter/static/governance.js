let REPORT = null;
let FILTERED = [];
let CURRENT_EDIT = null;
const ISSUE_BY_ID = new Map();
const SELECTED = new Set();

const severityClass = {high:'tag-high',medium:'tag-medium',low:'tag-low'};
const severityOrder = {high:0,medium:1,low:2};
const fieldLabels = {owner:'负责人',priority:'优先级',status:'状态',score:'项目打分'};
const scoreOptions = [
  ['5','5 夯爆了'],['4','4 顶级'],['3','3 人上人'],['2','2 NPC'],['1','1 拉完了']
];

function esc(value){
  return String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function attr(value){return esc(value).replace(/'/g,'&#39;');}
function tag(label, cls){return `<span class="tag ${cls || 'tag-gray'}">${esc(label || '')}</span>`;}
function shortWeek(label){
  if(!label) return '—';
  try{const p=String(label).split('/');return `${p[1]}/${p[2].split('-')[0]}`;}catch(e){return String(label).slice(0,5);}
}
function fieldStatus(issue){
  return `<div class="field-stack">
    <span>状态：${esc(issue.status || '未设置')}</span>
    <span>负责人：${esc(issue.owner || '未设置')}</span>
    <span>优先级：${esc(issue.priority || '未设置')}</span>
    <span>评分：${esc(issue.score_label || '未评分')}</span>
  </div>`;
}
function stateTag(issue){
  if(issue.confirmed) return tag('已确认', 'tag-green');
  if(issue.ignored) return tag('已忽略', 'tag-gray');
  return '';
}
function actionButton(issue){
  const disabled = issue.issue_state !== 'active';
  const fix = issue.fixable && !disabled
    ? `<button class="fix-btn" onclick="openEdit('${attr(issue.id)}')">修正</button>`
    : `<button class="fix-btn" disabled>${disabled ? '已处理' : '核对'}</button>`;
  const state = issue.issue_state === 'active'
    ? `<div class="mini-action">
        <button onclick="setIssueState('${attr(issue.issue_key)}','confirmed')">确认</button>
        <button onclick="setIssueState('${attr(issue.issue_key)}','ignored')">忽略30天</button>
      </div>`
    : `<div class="mini-action"><button onclick="setIssueState('${attr(issue.issue_key)}','active')">恢复</button></div>`;
  return fix + state;
}

async function loadGovernance(){
  const r = await fetch('/api/governance-data');
  const payload = await r.json();
  if(!r.ok || payload.error) throw new Error(payload.error || '健康检查读取失败');
  REPORT = payload;
  ISSUE_BY_ID.clear();
  SELECTED.clear();
  for(const issue of REPORT.issues || []) ISSUE_BY_ID.set(issue.id, issue);
  renderAll();
}

function renderAll(){
  renderMeta();
  renderMetrics();
  renderIssueTypes();
  renderFilters();
  applyFilters();
}

function renderMeta(){
  const meta = REPORT.meta || {};
  document.getElementById('mastheadMeta').innerHTML = [
    `最新周：${esc(meta.latest_week || '—')}`,
    `长期无更新阈值：${esc(meta.stale_weeks || 8)} 周`,
    `来源：${esc(meta.source_file || '—')}`,
    `检查时间：${esc(meta.generated || '—')}`,
  ].map(x=>`<span>${x}</span>`).join('');
  document.getElementById('distributionSub').textContent = `覆盖 ${REPORT.summary.total_projects} 个项目，异常周次继续标记但不纳入周报时间线。`;
}

function renderMetrics(){
  const s = REPORT.summary || {};
  const cards = [
    ['未处理问题', s.active_issues ?? s.total_issues ?? 0, `${s.affected_projects || 0} 个项目受影响`, 'hi'],
    ['可直接修正', s.fixable_issues || 0, '状态 / 负责人 / 优先级 / 评分', ''],
    ['高风险', s.active_high ?? s.high ?? 0, '缺状态 / 无任何周报', ''],
    ['中风险', s.active_medium ?? s.medium ?? 0, '长期无更新 / 重复 / 异常', ''],
    ['已处理', (s.ignored_issues || 0) + (s.confirmed_issues || 0), '已确认 / 暂时忽略', ''],
  ];
  document.getElementById('metrics').innerHTML = cards.map(c=>`<div class="metric ${c[3]}"><div class="metric-label">${esc(c[0])}</div><div class="metric-value">${c[1]}</div><div class="metric-sub">${esc(c[2])}</div></div>`).join('');
}

function renderIssueTypes(){
  const current = document.getElementById('typeFilter')?.value || '';
  document.getElementById('typeGrid').innerHTML = (REPORT.issue_types || []).map(item=>{
    const active = current === item.type ? ' active' : '';
    return `<button class="type-card${active}" onclick="setTypeFilter('${attr(item.type)}')">
      <div class="type-top"><span class="type-name">${esc(item.label)}</span><span class="type-count">${item.count}</span></div>
      <div class="type-meta">${tag(item.severity === 'high' ? '高' : item.severity === 'low' ? '低' : '中', severityClass[item.severity])}</div>
    </button>`;
  }).join('');
}

function renderFilters(){
  const typeFilter = document.getElementById('typeFilter');
  const first = '<option value="">全部问题</option>';
  typeFilter.innerHTML = first + (REPORT.issue_types || []).map(item=>`<option value="${esc(item.type)}">${esc(item.label)}（${item.count}）</option>`).join('');
  document.getElementById('searchInput').oninput = applyFilters;
  typeFilter.onchange = applyFilters;
  document.getElementById('severityFilter').onchange = applyFilters;
  document.getElementById('fixableFilter').onchange = applyFilters;
  document.getElementById('stateFilter').onchange = applyFilters;
  document.getElementById('refreshBtn').onclick = async () => {
    document.getElementById('refreshBtn').textContent = '刷新中';
    try{await loadGovernance();}finally{document.getElementById('refreshBtn').textContent = '刷新检查';}
  };
  document.getElementById('bulkField').onchange = renderBulkValue;
  document.getElementById('bulkApplyBtn').onclick = applyBulkFix;
  document.getElementById('selectFixableBtn').onclick = selectCurrentFixable;
  document.getElementById('clearSelectedBtn').onclick = clearSelected;
  renderBulkValue();
  renderBulkStatus();
}

function setTypeFilter(type){
  document.getElementById('typeFilter').value = type;
  applyFilters();
}

function applyFilters(){
  const q = document.getElementById('searchInput').value.toLowerCase().trim();
  const type = document.getElementById('typeFilter').value;
  const severity = document.getElementById('severityFilter').value;
  const fixable = document.getElementById('fixableFilter').value;
  const state = document.getElementById('stateFilter').value || 'active';
  FILTERED = (REPORT.issues || []).filter(issue => {
    const hay = [issue.project, issue.type_label, issue.status, issue.priority, issue.owner, issue.score, issue.score_label, issue.last_active, issue.reason, issue.suggestion].join(' ').toLowerCase();
    return (!q || hay.includes(q))
      && (!type || issue.type === type)
      && (!severity || issue.severity === severity)
      && (!fixable || (fixable === 'fixable' ? issue.fixable : !issue.fixable))
      && (state === 'all' || (state === 'handled' ? issue.issue_state !== 'active' : issue.issue_state === 'active'));
  }).sort((a,b)=>{
    const sev = (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9);
    if(sev !== 0) return sev;
    return String(a.project || a.reason).localeCompare(String(b.project || b.reason), 'zh-CN');
  });
  for(const key of Array.from(SELECTED)){
    if(!FILTERED.some(issue => issue.issue_key === key && canSelect(issue))) SELECTED.delete(key);
  }
  renderIssueTypes();
  renderIssues();
  renderBulkStatus();
}

function canSelect(issue){
  return Boolean(issue.project && issue.fixable && issue.issue_state === 'active');
}

function checkboxCell(issue){
  if(!canSelect(issue)) return '<input class="row-check" type="checkbox" disabled>';
  return `<input class="row-check" type="checkbox" ${SELECTED.has(issue.issue_key)?'checked':''} onchange="toggleSelected('${attr(issue.issue_key)}', this.checked)">`;
}

function toggleSelected(key, checked){
  if(checked) SELECTED.add(key); else SELECTED.delete(key);
  renderBulkStatus();
}

function renderIssues(){
  document.getElementById('issueLabel').textContent = `问题明细（${FILTERED.length}/${(REPORT.issues || []).length} 条）`;
  const rows = FILTERED.map(issue => `<tr>
    <td>${checkboxCell(issue)}</td>
    <td>${tag(issue.type_label, severityClass[issue.severity])}</td>
    <td><div class="issue-project ${issue.project ? '' : 'empty-name'}">${esc(issue.project || '工作表级问题')}</div><div class="state-line">${stateTag(issue)}</div></td>
    <td>${fieldStatus(issue)}</td>
    <td>${esc(shortWeek(issue.last_active))}</td>
    <td class="reason-cell">${esc(issue.reason)}</td>
    <td class="suggest-cell">${esc(issue.suggestion)}</td>
    <td>${actionButton(issue)}</td>
  </tr>`).join('');
  document.getElementById('issueTbody').innerHTML = rows;

  document.getElementById('issueCards').innerHTML = FILTERED.map(issue => `<article class="issue-card">
    <div class="issue-card-head"><h3>${checkboxCell(issue)} ${esc(issue.project || '工作表级问题')}</h3>${tag(issue.type_label, severityClass[issue.severity])}</div>
    <div class="state-line">${stateTag(issue)}</div>
    <dl>
      <dt>状态</dt><dd>${esc(issue.status || '未设置')}</dd>
      <dt>负责人</dt><dd>${esc(issue.owner || '未设置')}</dd>
      <dt>优先级</dt><dd>${esc(issue.priority || '未设置')}</dd>
      <dt>评分</dt><dd>${esc(issue.score_label || '未评分')}</dd>
      <dt>最后活跃</dt><dd>${esc(shortWeek(issue.last_active))}</dd>
      <dt>原因</dt><dd>${esc(issue.reason)}</dd>
      <dt>动作</dt><dd>${esc(issue.suggestion)}</dd>
    </dl>
    <div class="card-action">${actionButton(issue)}</div>
  </article>`).join('');
  document.getElementById('emptyState').style.display = FILTERED.length ? 'none' : 'block';
}

function editControl(issue){
  if(issue.field === 'priority'){
    return `<label>优先级<select id="editValue">
      ${['高','中','低'].map(v=>`<option value="${v}" ${issue.priority===v?'selected':''}>${v}</option>`).join('')}
    </select></label>`;
  }
  if(issue.field === 'status'){
    return `<label>状态<select id="editValue">
      ${['前期沟通','正式尽调','协议签署/交割','投后'].map(v=>`<option value="${v}" ${issue.status===v?'selected':''}>${v}</option>`).join('')}
    </select></label>`;
  }
  if(issue.field === 'score'){
    return `<label>项目打分<select id="editValue">
      ${scoreOptions.map(([value,label])=>`<option value="${value}" ${issue.score===value?'selected':''}>${label}</option>`).join('')}
    </select></label>`;
  }
  return `<label>负责人<input id="editValue" value="${esc(issue.owner || '')}" placeholder="输入负责人姓名"></label>`;
}

function openEdit(id){
  const issue = ISSUE_BY_ID.get(id);
  if(!issue || !issue.fixable) return;
  CURRENT_EDIT = issue;
  document.getElementById('editProjectName').textContent = issue.project;
  document.getElementById('editReason').textContent = issue.reason;
  document.getElementById('editFieldWrap').innerHTML = editControl(issue);
  document.getElementById('saveStatus').textContent = '';
  document.getElementById('saveEditBtn').onclick = saveEdit;
  document.getElementById('editLayer').classList.add('open');
  document.body.style.overflow = 'hidden';
  setTimeout(()=>document.getElementById('editValue')?.focus(), 20);
}

async function saveEdit(){
  if(!CURRENT_EDIT) return;
  const field = CURRENT_EDIT.field;
  const value = String(document.getElementById('editValue').value || '').trim();
  const status = document.getElementById('saveStatus');
  if(!value){
    status.textContent = `${fieldLabels[field] || '字段'}不能为空`;
    return;
  }
  status.textContent = '正在保存';
  const body = {};
  body[field] = value;
  try{
    const r = await fetch('/api/projects/' + encodeURIComponent(CURRENT_EDIT.project), {
      method:'PATCH',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body),
    });
    const res = await r.json();
    if(!r.ok) throw new Error(res.error || '保存失败');
    status.textContent = '已保存，正在刷新';
    await loadGovernance();
    closeEdit();
  }catch(e){
    status.textContent = '保存失败：' + e.message;
  }
}

function renderBulkValue(){
  const field = document.getElementById('bulkField').value;
  const wrap = document.getElementById('bulkValueWrap');
  if(field === 'priority'){
    wrap.innerHTML = `<select id="bulkValue">${['高','中','低'].map(v=>`<option value="${v}">${v}</option>`).join('')}</select>`;
  }else if(field === 'status'){
    wrap.innerHTML = `<select id="bulkValue">${['前期沟通','正式尽调','协议签署/交割','投后'].map(v=>`<option value="${v}">${v}</option>`).join('')}</select>`;
  }else if(field === 'score'){
    wrap.innerHTML = `<select id="bulkValue">${scoreOptions.map(([v,label])=>`<option value="${v}">${label}</option>`).join('')}</select>`;
  }else{
    wrap.innerHTML = '<input id="bulkValue" placeholder="输入负责人姓名">';
  }
}

function renderBulkStatus(){
  document.getElementById('bulkCount').textContent = `已选择 ${SELECTED.size} 项`;
}

function selectCurrentFixable(){
  for(const issue of FILTERED){
    if(canSelect(issue)) SELECTED.add(issue.issue_key);
  }
  renderIssues();
  renderBulkStatus();
}

function clearSelected(){
  SELECTED.clear();
  renderIssues();
  renderBulkStatus();
}

async function applyBulkFix(){
  const field = document.getElementById('bulkField').value;
  const value = String(document.getElementById('bulkValue')?.value || '').trim();
  const status = document.getElementById('bulkStatus');
  if(!SELECTED.size){ status.textContent = '请先选择问题'; return; }
  if(!value){ status.textContent = `${fieldLabels[field] || '字段'}不能为空`; return; }
  const issues = (REPORT.issues || []).filter(issue => SELECTED.has(issue.issue_key) && canSelect(issue));
  const projects = [...new Set(issues.map(issue => issue.project).filter(Boolean))];
  if(!projects.length){ status.textContent = '没有可修正项目'; return; }
  const ok = confirm(`将为 ${projects.length} 个项目批量更新${fieldLabels[field]}，每个项目都会生成备份和审计记录。是否继续？`);
  if(!ok) return;

  document.getElementById('bulkApplyBtn').disabled = true;
  status.textContent = `正在修正 0/${projects.length}`;
  const failed = [];
  for(let i=0;i<projects.length;i++){
    const project = projects[i];
    const body = {}; body[field] = value;
    try{
      const r = await fetch('/api/projects/' + encodeURIComponent(project), {
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body),
      });
      const res = await r.json();
      if(!r.ok) throw new Error(res.error || '保存失败');
    }catch(e){
      failed.push(project + '：' + e.message);
    }
    status.textContent = `正在修正 ${i + 1}/${projects.length}`;
  }
  document.getElementById('bulkApplyBtn').disabled = false;
  if(failed.length){
    status.textContent = `部分失败：${failed.slice(0,2).join('；')}`;
  }else{
    status.textContent = '批量修正完成，正在刷新';
  }
  await loadGovernance();
}

async function setIssueState(issueKey, state){
  let note = '';
  if(state === 'ignored'){
    note = prompt('填写忽略原因，默认 30 天后重新出现：', '已人工核对，暂不处理');
    if(note === null) return;
  }else if(state === 'confirmed'){
    note = prompt('填写确认备注：', '已人工确认，暂不修正');
    if(note === null) return;
  }
  try{
    const r = await fetch('/api/governance/issue-state', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({issue_key:issueKey,state,note,days:30}),
    });
    const res = await r.json();
    if(!r.ok) throw new Error(res.error || '保存失败');
    await loadGovernance();
  }catch(e){
    alert('处理失败：' + e.message);
  }
}

function closeEdit(){
  document.getElementById('editLayer').classList.remove('open');
  document.body.style.overflow = '';
  CURRENT_EDIT = null;
}
function handleLayerClick(event){
  if(event.target === document.getElementById('editLayer')) closeEdit();
}
document.addEventListener('keydown', event => {
  if(event.key === 'Escape') closeEdit();
});

loadGovernance().catch(error => {
  document.body.innerHTML = `<div class="page"><div class="masthead"><div><div class="masthead-label">战投 · 数据治理</div><h1>健康检查加载失败</h1><div class="masthead-meta">${esc(error.message)}</div></div></div></div>`;
});
