function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
const SCORE_LABELS = {'1':'1 拉完了','2':'2 NPC','3':'3 人上人','4':'4 顶级','5':'5 夯爆了'};
function scoreLabel(score){ return SCORE_LABELS[String(score || '').trim()] || ''; }
const DRAFT_PREFIX = 'zhangtou-reporter-draft-v1:';
let activeProjectDetail = null;
let draftTimer = null;

function shortText(s, n){
  s = String(s || '').replace(/\s+/g, ' ').trim();
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function handleOutputInput(value){
  generated = value;
  scheduleDraftSave();
}

function draftKey(project, week){
  project = String(project || '').trim();
  week = String(week || '').trim();
  return project && week ? DRAFT_PREFIX + encodeURIComponent(project) + '|' + week : '';
}

function currentDraftKey(){
  return draftKey(getProj(), _selWeek);
}

function setDraftStatus(text){
  const el = document.getElementById('draftStatus');
  if (!el) return;
  if (!text) { el.style.display = 'none'; el.textContent = ''; return; }
  el.style.display = 'block';
  el.textContent = text;
}

function draftPayload(){
  const project = getProj();
  return {
    project,
    week: _selWeek,
    industry: document.getElementById('catInput')?.value || '',
    biz_scope: _inferredBiz,
    stage: _stage,
    score: document.getElementById('scoreSelect')?.value || '',
    progress: document.getElementById('progressInput')?.value || '',
    extra: document.getElementById('extraInput')?.value || '',
    content: document.getElementById('oe')?.value || generated || '',
    saved_at: new Date().toLocaleString('zh-CN'),
  };
}

function saveDraftNow(){
  const key = currentDraftKey();
  if (!key) return;
  const payload = draftPayload();
  const hasContent = ['industry','stage','score','progress','extra','content']
    .some(k => String(payload[k] || '').trim());
  if (!hasContent) return;
  localStorage.setItem(key, JSON.stringify(payload));
  setDraftStatus('草稿已自动保存 · ' + payload.saved_at);
}

function scheduleDraftSave(){
  clearTimeout(draftTimer);
  draftTimer = setTimeout(saveDraftNow, 350);
}

function setOutputText(text){
  generated = text || '';
  document.getElementById('outArea').innerHTML =
    `<textarea class="out-edit" id="oe"
      placeholder="在此输入本周进展，或点击「生成周报内容」由 AI 生成后在此编辑"
      oninput="handleOutputInput(this.value)">${esc(generated)}</textarea>`;
  document.getElementById('actionRow').style.display = 'flex';
  document.getElementById('outMeta').textContent =
    generated ? generated.length + ' 字 · ' + new Date().toLocaleTimeString('zh-CN') : '';
  scheduleDraftSave();
}

function restoreDraftIfExists(){
  const key = currentDraftKey();
  if (!key) { setDraftStatus(''); return; }
  const raw = localStorage.getItem(key);
  if (!raw) { setDraftStatus(''); return; }
  try {
    const d = JSON.parse(raw);
    if (d.industry !== undefined) {
      document.getElementById('catInput').value = d.industry || '';
      inferCat(d.industry || '');
    }
    if (d.biz_scope) {
      _inferredBiz = d.biz_scope;
      const badge = document.getElementById('catBadge');
      badge.textContent = '→ ' + d.biz_scope;
      badge.style.display = 'inline-block';
    }
    if (d.stage !== undefined) setStage(d.stage || '');
    if (d.score !== undefined) document.getElementById('scoreSelect').value = d.score || '';
    if (d.progress !== undefined) document.getElementById('progressInput').value = d.progress || '';
    if (d.extra !== undefined) document.getElementById('extraInput').value = d.extra || '';
    if (d.content) setOutputText(d.content);
    setDraftStatus('已恢复本项目本周草稿 · ' + (d.saved_at || ''));
  } catch(e) {
    console.warn(e);
  }
}

function clearCurrentDraft(){
  const key = currentDraftKey();
  if (key) localStorage.removeItem(key);
  setDraftStatus('');
}

// ── 项目列表（搜索选择器）─────────────────────────────────────────────────
let allProjects = [];

(async () => {
  try {
    const r = await fetch('/api/projects');
    allProjects = await r.json();
    const el = document.getElementById('excelName');
    if (el) el.textContent = '共 ' + allProjects.length + ' 个项目';
  } catch(e) { console.warn(e); }
})();

function renderProjOptions(filter){
  const q = (filter || '').toLowerCase().trim();
  const list = document.getElementById('projOptionList');
  if (!list) return;
  const filtered = q
    ? allProjects.filter(p => p.toLowerCase().includes(q))
    : allProjects;
  list.innerHTML = filtered.length
    ? filtered.map(p => `<div class="ss-option" onmousedown="selectProj('${esc(p)}')">${esc(p)}</div>`).join('')
    : '<div class="ss-option ss-empty">无匹配项目</div>';
}

function showProjDropdown(){
  const dd = document.getElementById('projDropdown');
  if (dd) dd.style.display = 'block';
  renderProjOptions(document.getElementById('projSearchInput').value);
}

function hideProjDropdown(){
  setTimeout(() => {
    const dd = document.getElementById('projDropdown');
    if (dd) dd.style.display = 'none';
  }, 180);
}

function filterProjOptions(){
  renderProjOptions(document.getElementById('projSearchInput').value);
  document.getElementById('projDropdown').style.display = 'block';
}

function handleProjKeydown(e){
  const dd = document.getElementById('projDropdown');
  if (dd.style.display === 'none') return;
  const items = dd.querySelectorAll('.ss-option:not(.ss-empty):not(.ss-new)');
  if (!items.length) return;
  const current = dd.querySelector('.ss-option.ss-hl');
  let idx = -1;
  if (current) { idx = Array.from(items).indexOf(current); current.classList.remove('ss-hl'); }
  if (e.key === 'ArrowDown') { e.preventDefault(); idx = (idx + 1) % items.length; items[idx].classList.add('ss-hl'); items[idx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); idx = idx <= 0 ? items.length - 1 : idx - 1; items[idx].classList.add('ss-hl'); items[idx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    if (current) current.click();
  }
  else if (e.key === 'Escape') { dd.style.display = 'none'; }
}

function selectProj(value){
  const input = document.getElementById('projSearchInput');
  input.value = (value === '__new__') ? '＋ 新增项目' : value;
  document.getElementById('projDropdown').style.display = 'none';
  onProjSelect(value);
}

function getProj() {
  const input = document.getElementById('projSearchInput');
  const v = input ? input.value : '';
  const cu = document.getElementById('projCustom');
  if (cu && cu.style.display !== 'none') return cu.value.trim();
  return v === '＋ 新增项目' ? '' : v;
}

// ── 行业搜索选择器 ──────────────────────────────────────────────────────────
let allIndustries = [];

function renderIndOptions(filter){
  const q = (filter || '').toLowerCase().trim();
  const list = document.getElementById('indOptionList');
  if (!list) return;
  const filtered = q
    ? allIndustries.filter(s => s.toLowerCase().includes(q))
    : allIndustries;
  list.innerHTML = filtered.length
    ? filtered.map(s => `<div class="ss-option" onmousedown="selectInd('${esc(s)}')">${esc(s)}</div>`).join('')
    : '<div class="ss-option ss-empty">无匹配分类，可直接输入新类别</div>';
}

function showIndDropdown(){
  const dd = document.getElementById('indDropdown');
  if (dd) dd.style.display = 'block';
  renderIndOptions(document.getElementById('catInput').value);
}

function hideIndDropdown(){
  setTimeout(() => {
    const dd = document.getElementById('indDropdown');
    if (dd) dd.style.display = 'none';
  }, 180);
}

function filterIndOptions(){
  renderIndOptions(document.getElementById('catInput').value);
  document.getElementById('indDropdown').style.display = 'block';
}

function handleIndKeydown(e){
  const dd = document.getElementById('indDropdown');
  if (dd.style.display === 'none') return;
  const items = dd.querySelectorAll('.ss-option:not(.ss-empty)');
  if (!items.length) return;
  const current = dd.querySelector('.ss-option.ss-hl');
  let idx = -1;
  if (current) { idx = Array.from(items).indexOf(current); current.classList.remove('ss-hl'); }
  if (e.key === 'ArrowDown') { e.preventDefault(); idx = (idx + 1) % items.length; items[idx].classList.add('ss-hl'); items[idx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); idx = idx <= 0 ? items.length - 1 : idx - 1; items[idx].classList.add('ss-hl'); items[idx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'Enter') { e.preventDefault(); if (current) current.click(); }
  else if (e.key === 'Escape') { dd.style.display = 'none'; }
}

function selectInd(value){
  document.getElementById('catInput').value = value;
  document.getElementById('indDropdown').style.display = 'none';
  inferCat(value);
}
async function loadFieldOptions(){
  try {
    const r = await fetch('/api/field-options');
    const opts = await r.json();
    if (!r.ok || opts.error) throw new Error(opts.error || '字段选项读取失败');
    allIndustries = opts.industries || [];
    renderIndOptions('');
    const fill = (id, values) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.innerHTML = (values || []).map(v => `<option value="${esc(v)}"></option>`).join('');
    };
    fill('bizScopeOptions', opts.biz_scopes);
    fill('ownerOptions', opts.owners);
  } catch(e) { console.warn(e); }
}

function onProjSelect(v) {
  const cu = document.getElementById('projCustom');
  cu.style.display = v === '__new__' ? 'block' : 'none';
  if (v === '__new__') cu.focus();
  if (v && v !== '__new__') fillProjectInfo(v);
  if (!v || v === '__new__') {
    activeProjectDetail = null;
    renderRecentProject(null);
    document.getElementById('scoreSelect').value = '';
    restoreDraftIfExists();
  }
  scheduleDraftSave();
}

// ── 周次（日历 week-picker）───────────────────────────────────────────────────
let _wcY, _wcM, _selWeek = '';

function fmtD(d) {
  return d.getFullYear() + '/' +
    String(d.getMonth() + 1).padStart(2, '0') + '/' +
    String(d.getDate()).padStart(2, '0');
}
function initWC() {
  const now = new Date();
  _wcY = now.getFullYear(); _wcM = now.getMonth();
  const dow = now.getDay() || 7;
  const mon = new Date(now); mon.setDate(now.getDate() - dow + 1);
  const fri = new Date(mon); fri.setDate(mon.getDate() + 4);
  _selWeek = fmtD(mon) + '-' + fmtD(fri);
  document.getElementById('weekDisplay').value = _selWeek;
}
function toggleWC(e) {
  e.stopPropagation();
  const cal = document.getElementById('weekCal');
  document.removeEventListener('click', closeWCOut);
  if (cal.style.display === 'block') { cal.style.display = 'none'; return; }
  renderWC();
  cal.style.display = 'block';
  setTimeout(() => document.addEventListener('click', closeWCOut), 0);
}
function closeWCOut(e) {
  const wrap = document.querySelector('.week-picker-wrap');
  if (!wrap || !wrap.contains(e.target)) {
    document.getElementById('weekCal').style.display = 'none';
    document.removeEventListener('click', closeWCOut);
  }
}
function renderWC() {
  document.getElementById('wcTitle').textContent = _wcY + ' · ' + (_wcM + 1) + '月';
  const first = new Date(_wcY, _wcM, 1);
  const dow = first.getDay() || 7;
  const start = new Date(first); start.setDate(1 - dow + 1);
  let html = '', cur = new Date(start);
  for (let w = 0; w < 6; w++) {
    const mon = new Date(cur), fri = new Date(cur);
    fri.setDate(cur.getDate() + 4);
    if (mon.getMonth() !== _wcM && fri.getMonth() !== _wcM) {
      cur.setDate(cur.getDate() + 7); continue;
    }
    const ws = fmtD(mon) + '-' + fmtD(fri);
    html += `<div class="wc-row${ws === _selWeek ? ' wc-sel' : ''}" onclick="pickWeek('${ws}',event)">`;
    for (let d = 0; d < 5; d++) {
      const dd = new Date(mon); dd.setDate(mon.getDate() + d);
      html += `<span${dd.getMonth() !== _wcM ? ' class="wc-out"' : ''}>${dd.getDate()}</span>`;
    }
    html += '</div>';
    cur.setDate(cur.getDate() + 7);
  }
  document.getElementById('wcGrid').innerHTML = html;
}
function pickWeek(ws, e) {
  e.stopPropagation();
  _selWeek = ws;
  document.getElementById('weekDisplay').value = ws;
  document.getElementById('weekCal').style.display = 'none';
  document.removeEventListener('click', closeWCOut);
  restoreDraftIfExists();
  scheduleDraftSave();
}
function wcPrev(e) { e.stopPropagation(); if(--_wcM<0){_wcM=11;_wcY--;} renderWC(); }
function wcNext(e) { e.stopPropagation(); if(++_wcM>11){_wcM=0;_wcY++;} renderWC(); }

// ── 项目类别推断 ─────────────────────────────────────────────────────────────
const CAT_RULES = [
  ['AI / 大模型',          ['ai','大模型','llm','机器学习','智能','算法','深度学习','生成式','神经网络','chatbot']],
  ['Fintech / 金融科技',   ['金融','支付','保险','fintech','区块链','web3','加密','理财','银行','财富管理','不良资产','amc']],
  ['B2B SaaS / 企业服务',  ['saas','b2b','企业服务','erp','crm','协同','管理系统','paas','数字化','供应链','oa','rpa']],
  ['Consumer / 消费品牌',  ['消费','品牌','零售','电商','dtc','新消费','门店','快消','餐饮']],
  ['Healthcare / 医疗健康',['医疗','健康','生物','医药','器械','biotech','基因','制药']],
  ['Deep Tech / 硬科技',   ['芯片','半导体','量子','机器人','物联网','iot','航天','硬件','传感器']],
  ['数据 / 投研服务',      ['数据服务','另类数据','专家访谈','投研','资管','私募','数据资产','知识图谱']],
];
let _inferredBiz = '';
function inferCat(v) {
  const badge = document.getElementById('catBadge');
  if (!v.trim()) { badge.style.display = 'none'; _inferredBiz = ''; return; }
  const s = v.toLowerCase();
  for (const [cat, kws] of CAT_RULES) {
    if (kws.some(k => s.includes(k))) {
      _inferredBiz = cat;
      badge.textContent = '→ ' + cat;
      badge.style.display = 'inline-block';
      return;
    }
  }
  _inferredBiz = '';
  badge.style.display = 'none';
}

function setStage(value) {
  _stage = '';
  document.querySelectorAll('.s-chip').forEach(c => {
    c.classList.remove('sel');
    if (c.dataset.s === value) {
      c.classList.add('sel');
      _stage = value;
    }
  });
}

async function fillProjectInfo(name) {
  try {
    const r = await fetch('/api/projects/' + encodeURIComponent(name));
    if (!r.ok) return;
    const p = await r.json();
    activeProjectDetail = p;
    document.getElementById('catInput').value = p.industry || '';
    inferCat(p.industry || '');
    if (p.biz_scope) {
      _inferredBiz = p.biz_scope;
      const badge = document.getElementById('catBadge');
      badge.textContent = '→ ' + p.biz_scope;
      badge.style.display = 'inline-block';
    }
    setStage(p.status || '');
    document.getElementById('scoreSelect').value = p.score || '';
    renderRecentProject(p);
    restoreDraftIfExists();
  } catch(e) { console.warn(e); }
}

function renderRecentProject(p){
  const box = document.getElementById('recentBox');
  if (!box) return;
  if (!p || !p.latest_content) {
    box.style.display = 'none';
    document.getElementById('recentWeek').textContent = '';
    document.getElementById('recentText').textContent = '';
    return;
  }
  document.getElementById('recentWeek').textContent = p.latest_week || p.last_active || '';
  document.getElementById('recentText').textContent = shortText(p.latest_content, 180);
  box.style.display = 'block';
}

function useRecentAsContext(){
  if (!activeProjectDetail || !activeProjectDetail.latest_content) return;
  const extra = document.getElementById('extraInput');
  const insert = '参考最近一次进展（' + (activeProjectDetail.latest_week || '') + '）：\n'
    + activeProjectDetail.latest_content;
  extra.value = extra.value.trim() ? extra.value.trim() + '\n\n' + insert : insert;
  scheduleDraftSave();
}

function useRecentAsDraft(){
  if (!activeProjectDetail || !activeProjectDetail.latest_content) return;
  setOutputText(activeProjectDetail.latest_content);
}

// ── 阶段选择 ─────────────────────────────────────────────────────────────────
let _stage = '';
function pickStage(el) {
  const next = el.dataset.s;
  document.querySelectorAll('.s-chip').forEach(c => c.classList.remove('sel'));
  if (_stage === next) { _stage = ''; scheduleDraftSave(); return; }
  el.classList.add('sel');
  _stage = next;
  scheduleDraftSave();
}

// ── 文件管理 ─────────────────────────────────────────────────────────────────
let files = [];
function onFileSelect(fl) {
  for (const f of fl) if (!files.find(x => x.name === f.name)) files.push(f);
  renderFiles();
}
function rmFile(n) { files = files.filter(f => f.name !== n); renderFiles(); }
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/(1024*1024)).toFixed(1) + ' MB';
}
function fileIcon(name) {
  const ext = (name||'').split('.').pop().toLowerCase();
  const icons = {pdf:'PDF',docx:'DOC',xlsx:'XLS',csv:'CSV',md:'MD',txt:'TXT'};
  return icons[ext] || 'FILE';
}
function renderFiles() {
  document.getElementById('fileList').innerHTML = files.map(f =>
    `<div class="file-row">
      <span class="file-type-badge">${fileIcon(f.name)}</span>
      <span class="file-name">${esc(f.name)}</span>
      <span class="file-size">${formatSize(f.size)}</span>
      <button class="file-rm" onclick="rmFile(${JSON.stringify(f.name)})">✕</button>
    </div>`).join('');
}
// ── 文件上传（包裹在 DOMContentLoaded 中，防止脚本加载时 DOM 未就绪）──────────────────────────────────
let files = [];
function onFileSelect(fl) {
  for (const f of fl) if (!files.find(x => x.name === f.name)) files.push(f);
  renderFiles();
}
function rmFile(n) { files = files.filter(f => f.name !== n); renderFiles(); }
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/(1024*1024)).toFixed(1) + ' MB';
}
function fileIcon(name) {
  const ext = (name||'').split('.').pop().toLowerCase();
  const icons = {pdf:'PDF',docx:'DOC',xlsx:'XLS',csv:'CSV',md:'MD',txt:'TXT'};
  return icons[ext] || 'FILE';
}
function renderFiles() {
  const fl = document.getElementById('fileList');
  if (!fl) return;
  fl.innerHTML = files.map(f =>
    `<div class="file-row">
      <span class="file-type-badge">${fileIcon(f.name)}</span>
      <span class="file-name">${esc(f.name)}</span>
      <span class="file-size">${formatSize(f.size)}</span>
      <button class="file-rm" onclick="rmFile(${JSON.stringify(f.name)})">✕</button>
    </div>`).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  const dz = document.getElementById('dropZone');
  if (!dz) return;
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('over'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('over'); onFileSelect(e.dataTransfer.files);
  });
});

// ── 生成 ──────────────────────────────────────────────────────────────────────
let generated = '';
let abortController = null;
const HISTORY_PREFIX = 'zhangtou-reporter-history-v1:';
const MAX_HISTORY = 5;

function getHistoryKey(proj, wk) {
  return HISTORY_PREFIX + encodeURIComponent(proj||'') + '|' + (wk||'');
}
function saveToHistory() {
  if (!generated || generated.trim().length < 50) return;
  const key = getHistoryKey(getProj(), _selWeek);
  if (!key) return;
  let h = [];
  try { h = JSON.parse(localStorage.getItem(key) || '[]'); } catch(e) {}
  h.unshift({content:generated,ts:Date.now()});
  h = h.slice(0, MAX_HISTORY);
  localStorage.setItem(key, JSON.stringify(h));
  renderHistoryTabs();
}
function renderHistoryTabs() {
  const c = document.getElementById('historyTabs');
  if (!c) return;
  const key = getHistoryKey(getProj(), _selWeek);
  let h = [];
  try { h = JSON.parse(localStorage.getItem(key) || '[]'); } catch(e) {}
  if (h.length <= 1) { c.style.display = 'none'; return; }
  c.style.display = 'flex';
  c.innerHTML = h.map((hi, i) => {
    const d = new Date(hi.ts);
    const t = d.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
    return `<span class="hist-tab${i===0?' active':''}" onclick="switchHistory(${i})">v${i+1} · ${t}</span>`;
  }).join('');
}
function switchHistory(idx) {
  if (generated && generated.trim().length > 50) saveToHistory();
  const key = getHistoryKey(getProj(), _selWeek);
  let h = [];
  try { h = JSON.parse(localStorage.getItem(key) || '[]'); } catch(e) {}
  if (!h[idx]) return;
  generated = h[idx].content;
  const outArea = document.getElementById('outArea');
  outArea.innerHTML = `<textarea class="out-edit" id="oe" oninput="handleOutputInput(this.value)">${esc(generated)}</textarea>`;
  document.getElementById('actionRow').style.display = 'flex';
  document.getElementById('outMeta').textContent = generated.length + ' 字 · 历史版本';
  scheduleDraftSave();
  renderHistoryTabs();
}

async function startGen() {
  const proj     = getProj();
  const week     = _selWeek;
  const extra    = document.getElementById('extraInput').value.trim();
  const category = document.getElementById('catInput').value.trim();
  const progress = document.getElementById('progressInput').value.trim();
  if (!proj) { alert('请选择或输入项目名称'); return; }
  if (!week) { alert('请选择周次'); return; }

  // Auto-save current to history before overwriting
  if (generated && generated.trim().length > 50) saveToHistory();

  const fd = new FormData();
  fd.append('project',   proj);
  fd.append('week',      week);
  fd.append('extra',     extra);
  fd.append('category',  category);
  fd.append('biz_scope', _inferredBiz);
  fd.append('stage',     _stage);
  fd.append('progress',  progress);
  files.forEach(f => fd.append('files', f));

  if (abortController) abortController.abort();
  abortController = new AbortController();

  document.getElementById('genBtn').style.display = 'none';
  const cancelBtn = document.getElementById('cancelGenBtn');
  if (cancelBtn) cancelBtn.style.display = 'block';
  document.getElementById('progBar').style.display = 'flex';
  const st2 = document.getElementById('pushStatus');
  if (st2) { st2.className = 'push-status'; st2.style.display = 'none'; }

  const outArea = document.getElementById('outArea');
  outArea.innerHTML = '<div class="stream-box" id="sb"></div>';
  const sb = document.getElementById('sb');
  generated = '';

  try {
    const resp = await fetch('/api/generate', { method: 'POST', body: fd, signal: abortController.signal });
    const reader = resp.body.getReader(), dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n'); buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const msg = JSON.parse(line.slice(6));
          if (msg.error) {
            sb.textContent = '⚠ 生成失败：' + msg.error;
            document.getElementById('progBar').style.display = 'none';
            document.getElementById('genBtn').style.display = 'block';
            if (cancelBtn) cancelBtn.style.display = 'none';
            abortController = null;
            return;
          }
          if (msg.status) { sb.textContent = msg.status; continue; }
          if (msg.text) { if (!generated) sb.textContent = ''; generated += msg.text; sb.textContent = generated; }
          if (msg.done) {
            document.getElementById('progBar').style.display = 'none';
            document.getElementById('genBtn').style.display = 'block';
            if (cancelBtn) cancelBtn.style.display = 'none';
            abortController = null;
            document.getElementById('actionRow').style.display = 'flex';
            document.getElementById('outMeta').textContent =
              generated.length + ' 字 · ' + new Date().toLocaleTimeString('zh-CN');
            outArea.innerHTML =
              `<textarea class="out-edit" id="oe"
                oninput="handleOutputInput(this.value)">${esc(generated)}</textarea>`;
            scheduleDraftSave();
            saveToHistory();
          }
        } catch(e2) {}
      }
    }
  } catch(e) {
    if (e.name === 'AbortError') {
      sb.textContent = '生成已取消';
      if (generated) saveToHistory();
    } else {
      sb.textContent = '⚠ 请求失败：' + e.message;
    }
    document.getElementById('progBar').style.display = 'none';
    document.getElementById('genBtn').style.display = 'block';
    if (cancelBtn) cancelBtn.style.display = 'none';
    abortController = null;
  }
}

function cancelGen() {
  if (abortController) abortController.abort();
}

// ── 复制 ──────────────────────────────────────────────────────────────────────
function copyOut() {
  const t = document.getElementById('oe')?.value || generated;
  navigator.clipboard.writeText(t).then(() => {
    const b = document.querySelector('.btn-copy');
    b.textContent = '已复制 ✓';
    setTimeout(() => b.textContent = '复制内容', 1500);
  });
}

// ── 推送至看板 ────────────────────────────────────────────────────────────────
async function pushDash() {
  await sendPush(false);
}

async function sendPush(force) {
  const proj    = getProj();
  const week    = _selWeek;
  const content = document.getElementById('oe')?.value || generated;
  const score   = document.getElementById('scoreSelect').value;
  if (!proj) { alert('请选择或输入项目名称'); return; }
  if (!week) { alert('请选择周次'); return; }
  if (!score) { alert('请选择项目打分'); return; }
  if (!content) { alert('内容为空'); return; }

  document.getElementById('pushBtn').disabled = true;
  const st = document.getElementById('pushStatus');
  st.className = 'push-status'; st.style.display = 'block';
  st.textContent = '正在写入 Excel 并重新生成看板…';

  try {
    const r = await fetch('/api/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project:   proj,
        week:      week,
        content:   content,
        stage:     _stage,
        category:  document.getElementById('catInput').value.trim(),
        biz_scope: _inferredBiz,
        score:     score,
        force:     !!force,
      })
    });
    const res = await r.json();
    if (r.status === 409 && res.duplicate) {
      const preview = res.existing_preview ? '\n\n已有内容预览：\n' + res.existing_preview : '';
      const ok = confirm('这个项目在该周次已经有内容。是否覆盖原内容？' + preview);
      document.getElementById('pushBtn').disabled = false;
      if (ok) return sendPush(true);
      st.className = 'push-status';
      st.style.display = 'none';
      return;
    }
    if (res.ok) {
      clearCurrentDraft();
      st.className = 'push-status push-ok';
      const newBadge = res.is_new
        ? ' <span style="background:var(--amber-bg);color:var(--amber);padding:1px 6px;border-radius:3px;font-size:9px;margin-left:4px;">新项目</span>'
        : '';
      const stageTxt = res.stage ? ' · 阶段 → ' + res.stage : '';
      const scoreTxt = scoreLabel(res.score || score) ? ' · 评分 → ' + scoreLabel(res.score || score) : '';
      const overwriteTxt = res.overwritten ? ' · 已覆盖原内容' : '';
      st.innerHTML = '✓ 已推送 · 项目：' + esc(proj) + newBadge + stageTxt + scoreTxt + overwriteTxt + ' · 周次：' + esc(week);
      // Clear form but keep project, no page refresh
      document.getElementById('progressInput').value = '';
      document.getElementById('extraInput').value = '';
      document.getElementById('scoreSelect').value = '';
      setStage('');
      document.getElementById('outArea').innerHTML = '<textarea class="out-edit" id="oe" placeholder="在此输入本周进展，或点击「生成周报内容」由 AI 生成后在此编辑" oninput="handleOutputInput(this.value)"></textarea>';
      document.getElementById('actionRow').style.display = 'none';
      document.getElementById('outMeta').textContent = '';
      generated = '';
      files = [];
      renderFiles();
      showToast('✓ 已推送到看板', 'success');
      document.getElementById('pushBtn').disabled = false;
    } else {
      st.className = 'push-status push-err';
      st.textContent = '✗ 推送失败：' + (res.error || '未知错误');
    }
  } catch(e) {
    st.className = 'push-status push-err';
    st.textContent = '✗ 网络错误：' + e.message;
  }
  document.getElementById('pushBtn').disabled = false;
}

// ── 初始化 ────────────────────────────────────────────────────────────────────
initWC();
loadFieldOptions();
['scoreSelect','catInput','progressInput','extraInput','projCustom'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('input', scheduleDraftSave);
  if (el) el.addEventListener('change', scheduleDraftSave);
});
window.addEventListener('beforeunload', saveDraftNow);

// ── Toast 通知 ─────────────────────────────────────────────────────────────────
function showToast(msg, type) {
  const e = document.querySelector('.reporter-toast');
  if (e) e.remove();
  const t = document.createElement('div');
  t.className = 'reporter-toast ' + (type||'');
  t.textContent = msg;
  t.style.cssText = 'position:fixed;bottom:40px;right:40px;z-index:9999;padding:12px 24px;border-radius:8px;font-family:Georgia,serif;font-size:13px;color:#fff;background:'+(type==='success'?'var(--green)':'var(--red)')+';box-shadow:0 4px 16px rgba(0,0,0,.2);animation:fadeInUp .3s ease-out';
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity .3s';
    setTimeout(() => t.remove(), 300); }, 3000);
}

// ── 队列模式 ───────────────────────────────────────────────────────────────────
let queueMode = false;
let projectQueue = [];
function toggleQueueMode() {
  queueMode = document.getElementById('queueModeCheck').checked;
  localStorage.setItem('reporter-queue-mode', queueMode?'1':'0');
}
function addToQueue(proj, wk) {
  if (projectQueue.find(q => q.project===proj && q.week===wk)) return;
  projectQueue.push({project:proj, week:wk, status:'pending'});
  renderQueue();
}
function removeFromQueue(i) { projectQueue.splice(i,1); renderQueue(); }
function clearQueue() { projectQueue=[]; renderQueue(); }
function renderQueue() {
  const p = document.getElementById('queuePanel');
  const l = document.getElementById('queueList');
  const t = document.getElementById('queueTotal');
  const c = document.getElementById('queueCount');
  if (!p) return;
  if (projectQueue.length === 0) { p.style.display='none'; if(c)c.style.display='none'; return; }
  p.style.display='block'; if(c){c.style.display='inline';c.textContent=projectQueue.length;}
  if(t) t.textContent = projectQueue.length;
  l.innerHTML = projectQueue.map((q,i) =>
    `<div class="queue-item${q.status==='done'?' done':''}${q.status==='error'?' error':''}">
      <span class="queue-idx">${i+1}</span>
      <span class="queue-proj">${esc(q.project)}</span>
      <span class="queue-week">${esc(q.week)}</span>
      <span class="queue-status">${q.status==='pending'?'等待中':q.status==='generating'?'生成中…':q.status==='done'?'✓ 完成':'✗ 失败'}</span>
      ${q.status==='pending'?`<button class="queue-rm" onclick="removeFromQueue(${i})">移除</button>`:''}
    </div>`).join('');
}

// ── 键盘快捷键 ───────────────────────────────────────────────
document.addEventListener('keydown', function(e) {
  // 只在 reporter 页面生效
  if (!document.getElementById('genBtn')) return;
  // 不在输入框中生效（textarea/input）
  if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

  if (e.ctrlKey && e.key === 'Enter') {
    e.preventDefault();
    if (e.shiftKey) { pushDash(); }
    else { startGen(); }
  }
  if (e.ctrlKey && e.shiftKey && e.key === 'C') {
    e.preventDefault();
    copyOut();
  }
  if (e.key === 'Escape') {
    if (abortController) cancelGen();
  }
});
