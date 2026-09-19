/** 前端 DOM 冒烟测试（jsdom）：在真实 DOM 上下文执行 app.js，验证渲染与接口联动。
 *  用法： cd ~/sql_trainer && node tests/test_dom.mjs
 *  说明：CodeMirror 依赖真实布局，在 jsdom 中用最小桩件替代；其余前端逻辑全部真实执行。
 */
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';

const BASE = 'http://127.0.0.1:3000';
const html = fs.readFileSync(new URL('../static/index.html', import.meta.url), 'utf8');
const appjs = fs.readFileSync(new URL('../static/app.js', import.meta.url), 'utf8');
const realFetch = globalThis.fetch;                 // 先抓住 Node 原生 fetch，避免自递归

let ok = 0, fail = 0;
const check = (name, cond, extra = '') => {
  if (cond) { ok++; console.log(`✅ ${name} ${extra}`); }
  else { fail++; console.log(`❌ ${name} ${extra}`); }
};

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => errors.push('jsdomError: ' + (e.message || e)));
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));

const dom = new JSDOM(html, { url: BASE + '/', runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc });
const { window } = dom;

// 相对路径 fetch → 绝对 URL；Node 原生 fetch 不接受相对路径
window.fetch = (u, o) => realFetch(typeof u === 'string' && u.startsWith('/') ? BASE + u : u, o);
// CodeMirror 桩件（jsdom 无布局，真 CodeMirror 无法工作）
const cmState = { value: '' };
window.CodeMirror = {
  fromTextArea(el, opts) {
    return {
      opts, setValue: (v) => { cmState.value = v; }, getValue: () => cmState.value,
      on: () => {}, focus: () => {}, setOption: () => {}, refresh: () => {},
    };
  },
};
window.addEventListener('error', (e) => errors.push(String(e.message || e.error)));

// 注入并执行真实前端脚本
const script = window.document.createElement('script');
script.textContent = appjs;
window.document.body.appendChild(script);
check('app.js 在 DOM 上下文中执行无异常', errors.length === 0, errors.slice(0, 2).join(' | '));

const $ = (s) => window.document.querySelector(s);
const $$ = (s) => [...window.document.querySelectorAll(s)];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const state = (expr) => window.eval(expr);

await sleep(4000);   // 等 init() 拉目录 + 首题出题渲染

/* 1. 首屏渲染 */
const nItems = $$('.ex-item').length;
check('侧栏渲染题目列表', nItems >= 40, `${nItems} 条`);
check('顶栏 KPI 已填充', /^\d+$/.test($('#kpi-total')?.textContent || ''),
  `已通过 ${$('#kpi-passed')?.textContent}/${$('#kpi-total')?.textContent}`);
const title = $('.card h2')?.textContent || '';
check('题目卡片渲染标题与正文', title.length > 3 && ($('.card .md')?.textContent || '').length > 40, title);
check('知识点标签已渲染', $$('.tag').length >= 3, `${$$('.tag').length} 个标签`);
check('题目要求按 Markdown 渲染（含加粗/表格等标签）',
  /<(b|code|table|ul|ol|pre)[ >]/.test($('.card .md')?.innerHTML || ''));

/* 2. 数据字典与样例数据 */
$$('details')[0].open = true;
check('数据字典包含表结构 + 样例数据表',
  $$('.schema-table').length >= 1 && $$('.sample table.grid').length >= 1,
  `${$$('.schema-table').length} 张表 / ${$$('.sample table.grid').length} 个样例表`);
check('表结构展示字段名与类型',
  $$('.schema-table .col').length >= 5, `${$$('.schema-table .col').length} 个字段`);

/* 3. 默认 SQL 模板 */
check('默认 SQL 模板已注入编辑器',
  cmState.value.includes('SELECT') && cmState.value.includes('FROM'),
  cmState.value.split('\n')[0]);

/* 4. 分级提示 */
$('#btn-hint').onclick();
check('提示渲染到 #hintbox', ($('#hintbox')?.textContent || '').includes('提示 1 /'),
  ($('#hintbox')?.textContent || '').replace(/\s+/g, ' ').slice(0, 34));

/* 5. 仅运行（用本题真实存在的表） */
const t0 = state('S.cur.tables[0]');
cmState.value = `SELECT * FROM ${t0} LIMIT 5`;
$('#btn-run').onclick();
await sleep(2500);
const runRows = $$('#result table.grid tbody tr').length;
check('「仅运行」渲染结果表格', runRows > 0, `${runRows} 行（表 ${t0}）`);

/* 6. 错解 → 判失败并给差异反馈 */
cmState.value = "SELECT 'wrong' AS x";
$('#btn-submit').onclick();
await sleep(3000);
const v1 = ($('#result .verdict')?.textContent || '').replace(/\s+/g, ' ');
check('错解判失败并给出反馈', v1.includes('未通过'), v1.slice(0, 72));

/* 7. 参考解 → 判通过 + 四个标签页 + 讲解渲染 */
const exId = state('S.cur.id'), seed = state('S.cur.seed');
const sol = (await (await realFetch(`${BASE}/api/solution?id=${exId}&seed=${seed}`)).json()).solution;
cmState.value = sol;
$('#btn-submit').onclick();
await sleep(3500);
const v2 = ($('#result .verdict')?.textContent || '').replace(/\s+/g, ' ');
check('参考解判通过', v2.includes('通过'), v2.slice(0, 60));
check('结果区含 4 个标签页', $$('#result .tabs button').length === 4,
  $$('#result .tabs button').map((b) => b.textContent.trim()).join(' / '));
const notesHtml = $('#notes-md')?.innerHTML || '';
check('考点讲解渲染（Markdown → HTML，含代码块/表格）',
  notesHtml.length > 300 && (notesHtml.includes('<table') || notesHtml.includes('<pre')) &&
  !notesHtml.includes('（点上方'),
  `${notesHtml.length} 字节，含 <pre>=${notesHtml.includes('<pre')}`);

/* 8. 换一道 → 新随机数据 */
const oldSeed = state('S.cur.seed');
$('#btn-new').onclick();
await sleep(3500);
check('换一道 → 重新随机出题（种子变化）', state('S.cur.seed') !== oldSeed,
  `seed ${oldSeed} → ${state('S.cur.seed')}`);

/* 9. 视图切换 */
await state("setView('flash')");
check('理论卡片视图渲染', $$('.flash-card').length >= 100, `${$$('.flash-card').length} 张`);
$$('[data-show]')[0].onclick();
check('卡片答案可展开',
  window.document.getElementById('fa-' + $$('[data-show]')[0].dataset.show).style.display === 'block');

await state("setView('stats')");
check('统计视图渲染 KPI 卡与进度条',
  $$('.stat-box').length >= 6 && $$('.bar i').length >= 8,
  `${$$('.stat-box').length} 个指标 / ${$$('.bar i').length} 条进度条`);

await state("setView('wrong')");
const wb = $('.content').textContent || '';
check('错题本视图渲染（待攻克 / 已攻克 分组）', wb.includes('错题本') && wb.includes('待攻克'), '');

await state("setView('bank')");
await sleep(1500);

/* 10. 搜索过滤 */
const before = $$('.ex-item').length;
const sb = $('#search');
sb.value = '留存';
sb.dispatchEvent(new window.Event('input'));
await sleep(700);
check('搜索过滤生效', $$('.ex-item').length > 0 && $$('.ex-item').length < before,
  `${before} → ${$$('.ex-item').length}`);

/* 11. 无运行时异常 */
const real = errors.filter((e) => !/favicon|Not implemented/i.test(e));
check('全程无 JS 运行时异常', real.length === 0, real.slice(0, 2).join(' | '));

console.log(`\n${'='.repeat(66)}\nDOM 冒烟测试：通过 ${ok} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
