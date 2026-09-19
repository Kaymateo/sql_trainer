/* SQL 训练场 · 前端逻辑（无框架，原生 JS） */
'use strict';

const S = {
  catalog: null, progress: null, bankStats: null,
  cur: null,                 // 当前题目实例
  hintsUsed: 0, usedSolution: false,
  view: 'bank',
  editor: null, startedAt: 0, tick: null,
  flash: [], flashModule: '全部',
  stats: null, wrong: [],
};

/* ───────────────────────── 工具 ───────────────────────── */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ls = {
  get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set: (k, v) => localStorage.setItem(k, JSON.stringify(v)),
};

function toast(msg, ok = false) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show' + (ok ? ' ok' : '');
  clearTimeout(t._t);
  t._t = setTimeout(() => { t.className = 'toast'; }, 2600);
}

async function api(path, body) {
  const opt = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : {};
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
  return r.json();
}

/* 极简 Markdown → HTML（支持标题/加粗/行内代码/代码块/表格/列表） */
function mdToHtml(text) {
  if (!text) return '';
  const lines = String(text).replace(/\r/g, '').split('\n');
  const out = [];
  let i = 0;
  const inline = (s) => esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\s\|\s/g, ' | ');

  while (i < lines.length) {
    const ln = lines[i];
    if (/^```/.test(ln)) {                       // 代码块
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push(`<pre><code>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }
    if (/^\s*\|/.test(ln)) {                     // 表格
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      const cells = (r) => r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
      const head = cells(rows[0]);
      const body = rows.slice(1).filter((r) => !/^\s*\|[\s:|-]+\|\s*$/.test(r)).map(cells);
      out.push('<table><thead><tr>' + head.map((h) => `<th>${inline(h)}</th>`).join('') +
        '</tr></thead><tbody>' + body.map((r) => '<tr>' +
          r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
      continue;
    }
    const h = ln.match(/^(#{1,6})\s+(.*)$/);
    if (h) { out.push(`<h${Math.min(h[1].length + 2, 6)}>${inline(h[2])}</h${Math.min(h[1].length + 2, 6)}>`); i++; continue; }
    if (/^\s*([-*]|\d+\.)\s+/.test(ln)) {        // 列表
      const ordered = /^\s*\d+\./.test(ln);
      const buf = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        buf.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ''));
      }
      out.push(`<${ordered ? 'ol' : 'ul'}>` + buf.map((b) => `<li>${inline(b)}</li>`).join('') +
        `</${ordered ? 'ol' : 'ul'}>`);
      continue;
    }
    if (!ln.trim()) { i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(\s*[|#`]|\s*([-*]|\d+\.)\s)/.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${inline(buf.join(' '))}</p>`);
  }
  return out.join('\n');
}

const progOf = (id) => (S.progress && S.progress.exercises[id]) || null;

/* ───────────────────────── 侧栏（题库） ───────────────────────── */
function renderSidebar(filter = '') {
  const box = $('sidebar');
  if (!S.catalog) { box.innerHTML = '<div class="empty">加载题库中…</div>'; return; }
  const kw = filter.trim().toLowerCase();
  const byCat = {};
  for (const ex of S.catalog.exercises) {
    const hit = !kw || (ex.title + ex.id + (ex.knowledge || []).join('')).toLowerCase().includes(kw);
    if (!hit) continue;
    (byCat[ex.category] ||= []).push(ex);
  }
  let html = `<input class="search" id="search" placeholder="搜索题目 / 知识点…" value="${esc(filter)}">`;
  let total = 0, passed = 0;
  for (const [cat, list] of Object.entries(byCat)) {
    const catPassed = list.filter((e) => progOf(e.id)?.passed).length;
    total += list.length; passed += catPassed;
    html += `<div class="cat-title"><span>${esc(cat)}</span>
      <span class="count">${catPassed}/${list.length}</span></div>`;
    for (const ex of list) {
      const p = progOf(ex.id);
      const dot = p?.passed ? '<span class="dot ok">✓</span>'
        : p?.tries ? '<span class="dot try">●</span>' : '<span class="dot">○</span>';
      html += `<div class="ex-item${S.cur?.id === ex.id ? ' active' : ''}" data-id="${ex.id}">
        ${dot}<div class="body"><div class="t">${esc(ex.title)}</div>
        <div class="m"><span class="stars">${ex.diff_text}</span> · ${ex.tables.length} 张表${p ? ` · 提交 ${p.tries} 次` : ''}</div></div></div>`;
    }
  }
  if (!total) html += '<div class="empty">没有匹配的题目</div>';
  box.innerHTML = html;
  const si = $('search');
  si?.addEventListener('input', (e) => {
    const v = e.target.value;
    renderSidebar(v);
    const el = $('search');
    el?.focus();
    el?.setSelectionRange(v.length, v.length);
  });
  box.querySelectorAll('.ex-item').forEach((el) => {
    el.addEventListener('click', () => openExercise(el.dataset.id));
  });
}

/* ───────────────────────── 题目详情 ───────────────────────── */
function schemaHtml(ex) {
  return Object.entries(ex.schema).map(([tbl, info]) => `
    <details>
      <summary>📋 ${esc(tbl)} · ${info.columns.length} 列 · ${info.sample.total_rows} 行</summary>
      <div class="schema-grid">
        <div class="schema-table">
          <div class="name">${esc(tbl)}</div>
          ${info.columns.map((c) => `<div class="col"><span>${esc(c.column)}</span><span>${esc(c.type)}</span></div>`).join('')}
        </div>
      </div>
      <div class="sample">${gridHtml(info.sample.columns, info.sample.rows)}</div>
    </details>`).join('');
}

function gridHtml(cols, rows, maxRows = 100) {
  if (!cols?.length) return '<div class="empty">无数据</div>';
  const body = rows.slice(0, maxRows).map((r) => '<tr>' + r.map((c) =>
    c === 'NULL' ? '<td class="null">NULL</td>' : `<td>${esc(c)}</td>`).join('') + '</tr>').join('');
  return `<table class="grid"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead>
    <tbody>${body}</tbody></table>`;
}

function renderExercise() {
  const ex = S.cur;
  const box = $('content');
  const hints = ls.get(`hints_${ex.id}`, 0);
  S.hintsUsed = Math.min(hints, ex.hints.length);
  S.usedSolution = ls.get(`sol_${ex.id}`, false);
  box.innerHTML = `
  <div class="card">
    <h2>${esc(ex.title)}</h2>
    <div class="tags">
      <span class="tag red">${ex.diff_text}</span>
      <span class="tag">${esc(ex.category)}</span>
      ${ex.knowledge.map((k) => `<span class="tag dim">${esc(k)}</span>`).join('')}
      <span class="tag dim">数据种子 #${ex.seed}</span>
    </div>
    <div class="md">${mdToHtml(ex.prompt)}</div>
    <details><summary>📚 数据字典与样例数据（点开看表结构和前 4 行）</summary>${schemaHtml(ex)}</details>
  </div>

  <div class="toolbar">
    <button class="btn primary" id="btn-submit">提交判题 <span class="hint-text">Ctrl+Enter</span></button>
    <button class="btn" id="btn-run">仅运行看结果</button>
    <button class="btn ghost" id="btn-hint">提示 (${S.hintsUsed}/${ex.hints.length})</button>
    <button class="btn ghost" id="btn-sol">看参考解</button>
    <button class="btn ghost" id="btn-reset">清空代码</button>
    <button class="btn ghost" id="btn-new">换一道新数据</button>
    <span class="timer" id="timer">00:00</span>
  </div>
  <div class="editor-wrap"><textarea id="editor"></textarea></div>
  <div id="hintbox"></div>
  <div id="result"></div>
  <div class="card" style="margin-top:16px">
    <div style="font-size:13px;color:var(--text-dim);margin-bottom:6px">📝 我的笔记（这个知识点我踩了什么坑）</div>
    <textarea class="note" id="note" placeholder="例：last_value 默认帧只到当前行，必须写 ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING">${esc(ls.get(`note_${ex.id}`, ''))}</textarea>
    <div style="margin-top:8px"><button class="btn ghost" id="btn-note">保存笔记</button></div>
  </div>`;

  const cm = CodeMirror.fromTextArea($('editor'), {
    mode: 'text/x-sql', theme: 'material-darker', lineNumbers: true,
    matchBrackets: true, lineWrapping: true, indentUnit: 2,
    extraKeys: {
      'Ctrl-Enter': () => doSubmit(),
      'Cmd-Enter': () => doSubmit(),
      'Ctrl-Space': 'autocomplete',
    },
  });
  S.editor = cm;
  cm.setValue(ls.get(`draft_${ex.id}`, defaultSql(ex)));
  cm.on('change', () => ls.set(`draft_${ex.id}`, cm.getValue()));
  cm.focus();

  S.startedAt = Date.now();
  clearInterval(S.tick);
  S.tick = setInterval(() => {
    const s = Math.floor((Date.now() - S.startedAt) / 1000);
    $('timer') && ($('timer').textContent =
      `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`);
  }, 1000);

  $('btn-submit').onclick = () => doSubmit();
  $('btn-run').onclick = () => doRun();
  $('btn-hint').onclick = () => showHint();
  $('btn-sol').onclick = () => showSolution();
  $('btn-reset').onclick = () => S.editor.setValue('');
  $('btn-new').onclick = () => openExercise(ex.id, true);
  $('btn-note').onclick = async () => {
    await api('/api/note', { id: ex.id, content: $('note').value });
    ls.set(`note_${ex.id}`, $('note').value);
    toast('笔记已保存', true);
  };
  if (S.hintsUsed) showHint(true);
}

function defaultSql(ex) {
  return [
    `-- ${ex.title}`,
    `-- 可用表：${ex.tables.join(', ')}`,
    '-- Ctrl+Enter 提交判题 ｜ Ctrl+Space 补全表名字段名',
    '',
    'SELECT',
    '  ',
    `FROM ${ex.tables[0]}`,
    'LIMIT 20;',
  ].join('\n');
}

/* ───────────────────────── 动作 ───────────────────────── */
function setBusy(btn, busy, text) {
  if (!btn) return;
  btn.disabled = busy;
  if (busy) { btn._t = btn.innerHTML; btn.innerHTML = '<span class="spin"></span> ' + text; }
  else if (btn._t) btn.innerHTML = btn._t;
}

async function doRun() {
  const btn = $('btn-run');
  setBusy(btn, true, '运行中…');
  try {
    const r = await api('/api/run', { id: S.cur.id, seed: S.cur.seed, sql: S.editor.getValue() });
    renderResult(r, 'run');
  } catch (e) { toast('运行失败：' + e.message); }
  finally { setBusy(btn, false); }
}

async function doSubmit() {
  const btn = $('btn-submit');
  setBusy(btn, true, '判题中…');
  try {
    const r = await api('/api/submit', {
      id: S.cur.id, seed: S.cur.seed, sql: S.editor.getValue(),
      hints_used: S.hintsUsed, used_solution: S.usedSolution,
    });
    renderResult(r, 'submit');
    if (r.ok) {
      ls.set(`solved_${S.cur.id}`, true);
      toast(`通过！用时 ${(r.elapsed_ms / 1000).toFixed(2)}s`, true);
      await refreshProgress();
    } else {
      toast('未通过：' + (r.verdict || '结果不一致'));
    }
  } catch (e) { toast('提交失败：' + e.message); }
  finally { setBusy(btn, false); }
}

function renderResult(r, mode) {
  const box = $('result');
  if (!r.ok && r.error) {
    box.innerHTML = `<div class="verdict fail"><div class="v-title">⛔ 执行被拦截 / 出错</div>
      <pre>${esc(r.error)}</pre></div>`;
    return;
  }
  if (mode === 'run') {
    box.innerHTML = `<div class="verdict info"><div class="v-title">▶ 运行结果（未判题）</div>
      <div class="rowcount">返回 ${r.total_rows} 行${r.truncated ? '（仅展示前 100 行）' : ''}</div>
      ${gridHtml(r.columns, r.rows)}</div>`;
    return;
  }
  const pass = r.ok;
  box.innerHTML = `
    <div class="verdict ${pass ? 'pass' : 'fail'}">
      <div class="v-title">${pass ? '✅ 通过' : '❌ 未通过'} · ${esc(r.verdict || '')}</div>
      <div>${esc(r.detail || '')}</div>
      <div class="rowcount" style="margin-top:6px">耗时 ${(r.elapsed_ms / 1000).toFixed(2)}s ｜ 你的结果 ${r.your_total} 行 ｜ 参考结果 ${r.ref_total} 行</div>
    </div>
    <div class="tabs">
      <button class="active" data-tab="mine">我的结果</button>
      <button data-tab="ref">参考结果</button>
      <button data-tab="sol">参考解</button>
      <button data-tab="notes">讲解</button>
    </div>
    <div class="pane active" id="pane-mine">${gridHtml(r.your_columns, r.your_rows)}</div>
    <div class="pane" id="pane-ref">${gridHtml(r.ref_columns, r.ref_rows)}</div>
    <div class="pane" id="pane-sol"><div class="md"><pre><code>${esc(ls.get(`soltext_${S.cur.id}`, '（点上方「看参考解」按钮加载）'))}</code></pre></div></div>
    <div class="pane" id="pane-notes"><div class="md" id="notes-md">${mdToHtml(ls.get(`notestext_${S.cur.id}`, '（点上方「看参考解」按钮加载讲解）'))}</div></div>`;
  box.querySelectorAll('.tabs button').forEach((b) => {
    b.onclick = () => {
      box.querySelectorAll('.tabs button').forEach((x) => x.classList.remove('active'));
      box.querySelectorAll('.pane').forEach((x) => x.classList.remove('active'));
      b.classList.add('active');
      $('pane-' + b.dataset.tab)?.classList.add('active');
    };
  });
  autoloadExplanation(pass);
}

/** 提交后自动补齐「讲解」；通过则连参考解一起显示（不用再手动点按钮）。
 *  注意：自动加载不计入「看过答案」标记 —— 那个标记只在主动点「看参考解」时设置。 */
async function autoloadExplanation(pass) {
  const id = S.cur?.id;
  if (!id) return;
  const haveSol = !!ls.get(`soltext_${id}`, '');
  const haveNotes = !!ls.get(`notestext_${id}`, '');
  if (haveNotes && (!pass || haveSol)) return;
  try {
    const r = await api(`/api/solution?id=${encodeURIComponent(id)}&seed=${S.cur.seed}`);
    ls.set(`soltext_${id}`, r.solution || '');
    ls.set(`notestext_${id}`, r.notes || '');
    if (pass && $('pane-sol')) {
      $('pane-sol').innerHTML = `<div class="md"><pre><code>${esc(r.solution)}</code></pre></div>`;
    }
    if ($('notes-md')) $('notes-md').innerHTML = mdToHtml(r.notes);
    // 失败时只补讲解（不提前泄露 SQL），想看 SQL 仍然要点「看参考解」
    if (!pass && $('pane-sol')) {
      $('pane-sol').innerHTML = '<div class="md"><p>先别看答案：点上方「看参考解」按钮才会显示完整 SQL（会被记录）。</p></div>';
    }
  } catch (e) { /* 讲解加载失败不影响判题结果展示 */ }
}

function showHint(silent) {
  if (S.hintsUsed >= S.cur.hints.length) { if (!silent) toast('提示已经全部看完了，试着自己写'); return; }
  S.hintsUsed++;
  ls.set(`hints_${S.cur.id}`, S.hintsUsed);
  $('btn-hint').textContent = `提示 (${S.hintsUsed}/${S.cur.hints.length})`;
  $('hintbox').innerHTML = `<div class="card" style="border-color:rgba(245,182,66,.4)">
    <div style="color:var(--amber);font-size:12px;margin-bottom:6px">💡 提示 ${S.hintsUsed} / ${S.cur.hints.length}</div>
    <div class="md">${mdToHtml(S.cur.hints[S.hintsUsed - 1])}</div></div>`;
  if (!silent) toast(`已展示第 ${S.hintsUsed} 条提示`);
}

async function showSolution() {
  S.usedSolution = true;
  ls.set(`sol_${S.cur.id}`, true);
  const r = await api(`/api/solution?id=${encodeURIComponent(S.cur.id)}&seed=${S.cur.seed}`);
  ls.set(`soltext_${S.cur.id}`, r.solution || '');
  ls.set(`notestext_${S.cur.id}`, r.notes || '');
  toast('参考解与讲解已加载（本次提交会标记为「看过答案」）');
  if ($('pane-sol')) {
    $('pane-sol').innerHTML = `<div class="md"><pre><code>${esc(r.solution)}</code></pre></div>`;
    $('notes-md').innerHTML = mdToHtml(r.notes);
  } else {
    $('result').innerHTML = `<div class="tabs">
        <button class="active" data-tab="sol">参考解</button><button data-tab="notes">讲解</button></div>
      <div class="pane active" id="pane-sol"><div class="md"><pre><code>${esc(r.solution)}</code></pre></div></div>
      <div class="pane" id="pane-notes"><div class="md" id="notes-md">${mdToHtml(r.notes)}</div></div>`;
    $('result').querySelectorAll('.tabs button').forEach((b) => {
      b.onclick = () => {
        $('result').querySelectorAll('.tabs button').forEach((x) => x.classList.remove('active'));
        $('result').querySelectorAll('.pane').forEach((x) => x.classList.remove('active'));
        b.classList.add('active');
        $('pane-' + b.dataset.tab)?.classList.add('active');
      };
    });
  }
}

/* ───────────────────────── 其它视图 ───────────────────────── */
async function renderWrong() {
  const box = $('content');
  box.innerHTML = '<div class="empty">加载错题本…</div>';
  S.stats = await api('/api/stats');
  const all = S.stats.mistakes || [];
  S.wrong = S.stats.wrongbook || [];
  const solved = all.filter((m) => m.passed_now);

  const card = (m, done) => `
    <div class="flash-card">
      <div class="q">${esc(m.title)} <span class="stars">${'★'.repeat(m.difficulty)}</span>
        ${done ? '<span class="tag" style="margin-left:6px">已攻克</span>' : ''}</div>
      <div class="mod">${esc(m.category)} · 错 ${m.fails} 次 · 最近 ${esc(m.last_at || '')}</div>
      ${m.last_detail ? `<div class="a" style="margin-top:6px;color:var(--text-dim2)">最近一次反馈：${esc(String(m.last_detail).slice(0, 120))}</div>` : ''}
      ${m.note ? `<div class="a" style="margin-top:6px">📝 ${esc(m.note)}</div>` : ''}
      <div class="foot"><button class="btn ${done ? 'ghost' : 'primary'}" data-redo="${m.id}">用新数据重做</button></div>
    </div>`;

  box.innerHTML = `
  <div class="card"><h2>错题本</h2>
    <div class="rowcount">共错过 ${all.length} 道，其中 ${S.wrong.length} 道还没攻克。
      点「用新数据重做」会换一套随机数据重新出题 —— 同一道题数据不同，背答案没有用。</div>
  </div>
  <div class="card"><h2>⏳ 待攻克 · ${S.wrong.length} 道</h2>
    ${S.wrong.length ? S.wrong.map((m) => card(m, false)).join('')
      : '<div class="empty">全部攻克了，继续往下刷题库 🎉</div>'}
  </div>
  <div class="card"><h2>✅ 曾错已攻克 · ${solved.length} 道</h2>
    ${solved.length ? solved.map((m) => card(m, true)).join('')
      : '<div class="empty">还没有「错过又做对」的记录，加油。</div>'}
  </div>`;
  box.querySelectorAll('[data-redo]').forEach((b) => {
    b.onclick = () => { S.view = 'bank'; syncNav(); openExercise(b.dataset.redo, true); };
  });
}

async function renderFlash() {
  const box = $('content');
  box.innerHTML = '<div class="empty">加载理论卡片…</div>';
  const r = await api('/api/flashcards');
  S.flash = r.cards;
  const mods = ['全部', ...new Set(S.flash.map((c) => c.module))];
  const list = S.flashModule === '全部' ? S.flash : S.flash.filter((c) => c.module === S.flashModule);
  const mastered = S.flash.filter((c) => c.status === '已掌握').length;
  box.innerHTML = `<div class="card"><h2>理论卡片 · 八股自测</h2>
    <div class="rowcount">共 ${S.flash.length} 张，已掌握 ${mastered} 张。先自己想答案，再点「显示答案」对照。</div>
    <div class="tags" style="margin-top:10px">${mods.map((m) => `<span class="tag${m === S.flashModule ? ' red' : ' dim'}" data-mod="${esc(m)}" style="cursor:pointer">${esc(m)}</span>`).join('')}</div>
  </div>
  <div id="flashlist">${list.map((c) => `
    <div class="flash-card">
      <div class="q">${esc(c.q)}</div>
      <div class="a" id="fa-${c.id}" style="display:none">${esc(c.a)}</div>
      <div class="foot">
        <span class="mod">${esc(c.module)} · ${c.status}</span>
        <button class="btn ghost" data-show="${c.id}">显示答案</button>
        <button class="btn ghost" data-mark="${c.id}" data-v="已掌握">✓ 已掌握</button>
        <button class="btn ghost" data-mark="${c.id}" data-v="未掌握">↻ 还不熟</button>
      </div>
    </div>`).join('')}</div>`;
  box.querySelectorAll('[data-mod]').forEach((el) => {
    el.onclick = () => { S.flashModule = el.dataset.mod; renderFlash(); };
  });
  box.querySelectorAll('[data-show]').forEach((b) => {
    b.onclick = () => {
      const el = $('fa-' + b.dataset.show);
      const open = el.style.display !== 'none';
      el.style.display = open ? 'none' : 'block';
      b.textContent = open ? '显示答案' : '隐藏答案';
    };
  });
  box.querySelectorAll('[data-mark]').forEach((b) => {
    b.onclick = async () => {
      await api('/api/flashcard', { id: b.dataset.mark, status: b.dataset.v });
      toast(`已标记为「${b.dataset.v}」`, true);
      renderFlash();
    };
  });
}

async function renderStats() {
  const box = $('content');
  box.innerHTML = '<div class="empty">统计中…</div>';
  const st = await api('/api/stats');
  S.stats = st;
  const p = st.progress;
  const total = S.bankStats?.total || st.progress.total_submits;
  const pct = Math.round((st.progress.total_passed ? Object.keys(p.exercises).filter((k) => p.exercises[k].passed).length : 0) / (S.catalog?.exercises.length || 1) * 100);
  box.innerHTML = `
  <div class="stat-grid">
    <div class="stat-box"><div class="label">已通过题目</div><div class="value">${Object.values(p.exercises).filter((x) => x.passed).length}<span style="font-size:14px;color:var(--text-dim2)">/${S.catalog?.exercises.length || 0}</span></div>
      <div class="bar"><i style="width:${pct}%"></i></div></div>
    <div class="stat-box"><div class="label">总提交次数</div><div class="value">${p.total_submits}</div></div>
    <div class="stat-box"><div class="label">提交通过率</div><div class="value">${p.pass_rate}%</div></div>
    <div class="stat-box"><div class="label">练习天数</div><div class="value">${p.practice_days}</div></div>
    <div class="stat-box"><div class="label">通过题均耗时</div><div class="value">${(p.avg_passed_ms / 1000).toFixed(1)}s</div></div>
    <div class="stat-box"><div class="label">理论卡片</div><div class="value">${st.flash_mastered}<span style="font-size:14px;color:var(--text-dim2)">/${st.flash_total}</span></div></div>
  </div>

  <div class="card" style="margin-top:16px"><h2>分类掌握度</h2>
    <table class="list"><thead><tr><th>分类</th><th>已通过 / 总数</th><th style="width:45%">进度</th></tr></thead><tbody>
    ${Object.entries(st.categories).map(([cat, d]) => {
      const w = Math.round(d.passed / d.total * 100);
      return `<tr><td>${esc(cat)}</td><td>${d.passed} / ${d.total}</td>
        <td><div class="bar"><i style="width:${w}%"></i></div></td></tr>`;
    }).join('')}
    </tbody></table>
  </div>

  <div class="card"><h2>难度分布</h2>
    <table class="list"><thead><tr><th>难度</th><th>已通过 / 总数</th><th style="width:45%">进度</th></tr></thead><tbody>
    ${Object.entries(st.difficulties).map(([k, d]) => {
      const w = Math.round(d.passed / d.total * 100);
      return `<tr><td><span class="stars">${k}</span></td><td>${d.passed} / ${d.total}</td>
        <td><div class="bar"><i style="width:${w}%"></i></div></td></tr>`;
    }).join('')}
    </tbody></table>
  </div>

  <div class="card"><h2>服务端状态</h2>
    <div class="rowcount">已在内存中缓存 ${st.instances.cached} 个数据实例（每道题一套独立随机数据）</div>
    <table class="list"><thead><tr><th>题目</th><th>数据种子</th><th>建模耗时</th></tr></thead><tbody>
    ${st.instances.items.map((i) => `<tr><td>${esc(i.exercise)}</td><td>#${i.seed}</td><td>${i.build_seconds}s</td></tr>`).join('')}
    </tbody></table>
    <div class="rowcount" style="margin-top:8px">服务器时间 ${esc(st.server_time)}</div>
  </div>`;
}

/* ───────────────────────── 视图切换 ───────────────────────── */
function syncNav() {
  document.querySelectorAll('nav button').forEach((b) =>
    b.classList.toggle('active', b.dataset.view === S.view));
  $('sidebar').style.display = S.view === 'bank' ? '' : 'none';
  document.querySelector('main').style.gridTemplateColumns = S.view === 'bank' ? '320px 1fr' : '1fr';
}

async function setView(v) {
  S.view = v;
  syncNav();
  if (v === 'bank') {
    renderSidebar();
    if (S.cur) renderExercise();
    else if (S.catalog?.exercises.length) openExercise(S.catalog.exercises[0].id);
  } else if (v === 'wrong') await renderWrong();
  else if (v === 'flash') await renderFlash();
  else if (v === 'stats') await renderStats();
}

async function openExercise(id, newSeed = false) {
  S.view = 'bank'; syncNav();
  $('content').innerHTML = '<div class="empty"><span class="spin"></span> 生成随机题目与数据…</div>';
  try {
    const q = newSeed ? '' : `&seed=${ls.get('seed_' + id, '') || ''}`;
    const r = await api('/api/exercise?id=' + encodeURIComponent(id) + q);
    S.cur = r.exercise;
    if (!ls.get('seed_' + id, '')) ls.set('seed_' + id, S.cur.seed);
    renderSidebar($('search')?.value || '');
    renderExercise();
  } catch (e) {
    $('content').innerHTML = `<div class="verdict fail"><div class="v-title">出题失败</div><pre>${esc(e.message)}</pre></div>`;
  }
}

async function refreshProgress() {
  const r = await api('/api/catalog');
  S.progress = r.progress;
  const passed = Object.values(r.progress.exercises).filter((x) => x.passed).length;
  $('kpi-passed').textContent = passed;
  $('kpi-total').textContent = r.exercises.length;
  $('kpi-submits').textContent = r.progress.total_submits;
  $('kpi-days').textContent = r.progress.practice_days ? `练习 ${r.progress.practice_days} 天` : '';
  renderSidebar($('search')?.value || '');
}

/* ───────────────────────── 启动 ───────────────────────── */
(async function init() {
  document.querySelectorAll('nav button').forEach((b) => {
    b.onclick = () => setView(b.dataset.view);
  });
  try {
    const r = await api('/api/catalog');
    S.catalog = r; S.progress = r.progress; S.bankStats = r.bank_stats;
    $('kpi-passed').textContent = Object.values(r.progress.exercises).filter((x) => x.passed).length;
    $('kpi-total').textContent = r.exercises.length;
    $('kpi-submits').textContent = r.progress.total_submits;
    renderSidebar();
    const firstUnsolved = r.exercises.find((e) => !r.progress.exercises[e.id]?.passed) || r.exercises[0];
    const last = ls.get('last_exercise', '');
    await openExercise(last && r.exercises.some((e) => e.id === last) ? last : firstUnsolved.id);
  } catch (e) {
    $('content').innerHTML = `<div class="verdict fail"><div class="v-title">无法连接服务端</div><pre>${esc(e.message)}</pre></div>`;
  }
})();
window.addEventListener('beforeunload', () => { if (S.cur) ls.set('last_exercise', S.cur.id); });
