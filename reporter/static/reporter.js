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

// ── 项目列表（下拉选择）──────────────────────────────────────────────────────
(async () => {
  try {
    const r = await fetch('/api/projects');
    const projs = await r.json();
    document.getElementById('projOpts').innerHTML =
      projs.map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join('');
    const el = document.getElementById('excelName');
    if (el) el.textContent = '共 ' + projs.length + ' 个项目';
  } catch(e) { console.warn(e); }
})();

async function loadFieldOptions(){
  try {
    const r = await fetch('/api/field-options');
    const opts = await r.json();
    if (!r.ok || opts.error) throw new Error(opts.error || '字段选项读取失败');
    const fill = (id, values) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.innerHTML = (values || []).map(v => `<option value="${esc(v)}"></option>`).join('');
    };
    fill('industryOptions', opts.industries);
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
function getProj() {
  const v = document.getElementById('projSelect').value;
  return v === '__new__' ? document.getElementById('projCustom').value.trim() : v;
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
function renderFiles() {
  document.getElementById('fileList').innerHTML = files.map(f =>
    `<div class="file-row">
      <span class="file-name">${f.name}</span>
      <button class="file-rm" onclick="rmFile(${JSON.stringify(f.name)})">✕</button>
    </div>`).join('');
}
const dz = document.getElementById('dropZone');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('over'));
dz.addEventListener('drop', e => {
  e.preventDefault(); dz.classList.remove('over'); onFileSelect(e.dataTransfer.files);
});

// ── 生成 ──────────────────────────────────────────────────────────────────────
let generated = '';
async function startGen() {
  const proj     = getProj();
  const week     = _selWeek;
  const extra    = document.getElementById('extraInput').value.trim();
  const category = document.getElementById('catInput').value.trim();
  const progress = document.getElementById('progressInput').value.trim();
  if (!proj) { alert('请选择或输入项目名称'); return; }
  if (!week) { alert('请选择周次'); return; }

  const fd = new FormData();
  fd.append('project',   proj);
  fd.append('week',      week);
  fd.append('extra',     extra);
  fd.append('category',  category);
  fd.append('biz_scope', _inferredBiz);
  fd.append('stage',     _stage);
  fd.append('progress',  progress);
  files.forEach(f => fd.append('files', f));

  document.getElementById('genBtn').disabled = true;
  document.getElementById('progBar').style.display = 'flex';
  const st2 = document.getElementById('pushStatus');
  if (st2) { st2.className = 'push-status'; st2.style.display = 'none'; }

  const outArea = document.getElementById('outArea');
  outArea.innerHTML = '<div class="stream-box" id="sb"></div>';
  const sb = document.getElementById('sb');
  generated = '';

  try {
    const resp = await fetch('/api/generate', { method: 'POST', body: fd });
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
            document.getElementById('genBtn').disabled = false;
            return;
          }
          if (msg.status) { sb.textContent = msg.status; continue; }
          if (msg.text) { if (!generated) sb.textContent = ''; generated += msg.text; sb.textContent = generated; }
          if (msg.done) {
            document.getElementById('progBar').style.display = 'none';
            document.getElementById('genBtn').disabled = false;
            document.getElementById('actionRow').style.display = 'flex';
            document.getElementById('outMeta').textContent =
              generated.length + ' 字 · ' + new Date().toLocaleTimeString('zh-CN');
            outArea.innerHTML =
              `<textarea class="out-edit" id="oe"
                oninput="handleOutputInput(this.value)">${esc(generated)}</textarea>`;
            scheduleDraftSave();
          }
        } catch(e2) {}
      }
    }
  } catch(e) {
    sb.textContent = '⚠ 请求失败：' + e.message;
    document.getElementById('progBar').style.display = 'none';
    document.getElementById('genBtn').disabled = false;
  }
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
      const regenTxt = res.regen_ok
        ? '<br><span style="opacity:.7;font-size:9px;">看板已重新生成 — <a href="/dashboard" target="_blank" style="color:inherit">刷新查看 →</a></span>'
        : '<br><span style="opacity:.7;font-size:9px;">看板重新生成失败：' + esc(res.regen_msg || '未返回具体原因') + '</span>';
      st.innerHTML = '✓ 已写入 · 项目：' + esc(proj) + newBadge + stageTxt + scoreTxt + overwriteTxt + ' · 周次：' + esc(week) + regenTxt;
      // 粒子特效
      const rect2 = st.getBoundingClientRect();
      const pcx = rect2.left + rect2.width * .5;
      const pcy = rect2.top + rect2.height * .5;
      ['✦','◆','▲','●','★','◉','✚','◈'].forEach((ch, i) => {
        const p = document.createElement('span');
        const tx = ((i%2?1:-1)*(28 + Math.random()*70)).toFixed(1)+'px';
        const ty = (-(45 + Math.random()*90)).toFixed(1)+'px';
        const tr = (Math.random()*360).toFixed(0)+'deg';
        p.textContent = ch;
        p.style.cssText = 'position:fixed;pointer-events:none;z-index:9999;font-size:'
          +(11+i%4*3)+'px;left:'+(pcx+(i-3.5)*22)+'px;top:'+pcy+'px;'
          +'color:'+['var(--amber)','var(--green)','var(--text2)'][i%3]+';'
          +'animation:confetti-fly .95s ease-out '+(i*55)+'ms both;'
          +'--tx:'+tx+';--ty:'+ty+';--tr:'+tr+';';
        document.body.appendChild(p);
        setTimeout(()=>p.remove(), 1600);
      });
      setTimeout(()=>location.reload(), 2200);
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
