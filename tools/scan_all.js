// scan_all.js —— 全库扫描（2026-09-23 作者拍板「画布补 80」落地为正式工具）
//
// 遍历 RwTargets() 全部目标 × 产率档位 × 画布规格，逐格跑 LawRun 全流程，
// 按五道断言验收。历史来源：v96 ⑥-2「空气机器」bug 就是全库扫描抓出来的
// （当时是临时探针，本工具把它固化成可重跑的入库脚本）。
//
// 断言口径：
//   A1 不抛异常              LawRun 全流程不 throw
//   A2 出口合法              生成（LO.plan 存在）或拒绝（msg 含「放不下」），二者必居其一
//   A3 布局层台数守恒        plan.plan.objs.length === plan.res.totalMachines（不丢机器）
//   A4 无空气机器            res.machines 每个节点都有 machineId（external 节点台数恒 0）
//   A5 画布内且零重叠        摆下的机器全在画布内、两两外接框不相交
//   （jam / 手动连 / 超限只计数留观察，不判 FAIL —— 报警不拦截口径）
//
// 用法：
//   node tools/scan_all.js                      # 80 画布 × 档位 10/30/70
//   node tools/scan_all.js --sizes 50,70,80     # 多规格
//   node tools/scan_all.js --rates 10,70        # 指定档位
//   node tools/scan_all.js --target item_copper_jar   # 只扫一个目标（调试）
//   node tools/scan_all.js --quiet              # 只输出汇总与 FAIL 行
//
// 退出码：0 全绿 | 1 有 FAIL
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// ---- 参数 ----
const args = process.argv.slice(2);
function opt(name, dflt) {
  const i = args.indexOf('--' + name);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : dflt;
}
const has = name => args.indexOf('--' + name) >= 0;
const SIZES = (opt('sizes', '80') || '').split(',').map(Number).filter(Boolean);
const RATES = (opt('rates', '10,30,70') || '').split(',').map(Number).filter(Boolean);
const ONLY = opt('target', null);
const QUIET = has('quiet');

// ---- 加载 HTML（同 test_html.js 的沙箱模式）----
const H = require('./test_harness');
const HTML = H.defaultHtml();
const { html, rawCode, code } = H.load(HTML);

function mkEl(tag) {
  return {
    tagName: tag, style: {}, dataset: {}, children: [], _html: '',
    classList: { add() {}, remove() {}, contains() { return false; } },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); },
    set textContent(v) { this._text = String(v); },
    get textContent() { return this._text || ''; },
    value: '',
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, removeEventListener() {},
    closest() { return null; }, querySelector() { return null; },
    querySelectorAll() { return []; }, setAttribute() {}, focus() {},
  };
}
const els = {};
const doc = {
  body: mkEl('body'),
  querySelector(sel) { if (!els[sel]) els[sel] = mkEl(sel.replace('#', '')); return els[sel]; },
  createElement: mkEl,
  addEventListener() {},
};
const ctx = {
  document: doc, window: {}, console, setTimeout, clearTimeout,
  JSON, Math, Object, Array, String, Number, Boolean, Date, Set, Map, RegExp, Error,
  isNaN, parseInt, parseFloat,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
try { vm.runInContext(code, ctx, { timeout: 40000 }); }
catch (e) { console.error('CTX ERROR: ' + e.message); process.exit(1); }
const A = ctx;

// ---- 扫描 ----
const targets = A.RwTargets().filter(t => !ONLY || t.id === ONLY);
if (!targets.length) { console.error('FATAL 没有匹配的目标'); process.exit(1); }

let total = 0, pass = 0, fail = 0;
const fails = [], stats = { gen: 0, rej: 0, gate: 0, skip: 0, jam: 0, manual: 0, overLimit: 0 };
const t0 = Date.now();

function one(id, name, rate, size) {
  total++;
  const tag = name + '@' + rate + ' s' + size;
  const problems = [];
  let msg = '', plan = null, placed = 0, belts = 0, jamN = 0, manualN = 0, overLimit = false;
  try {
    A.Linit();
    A.LO.objs = []; A.LO.sel = []; A.LO.plan = null; A.LO.msg = '';
    A.LO.size = size;
    A.LO.mt = []; A.LO.shipIn = false;
    A.LawRun(id, rate);
    msg = A.LO.msg || '';
    plan = A.LO.plan;
    placed = A.LO.objs.filter(o => o.planRole === 'machine').length;
    belts = plan && plan.route ? (plan.route.belts || []).length : 0;
    jamN = plan && plan.route ? (plan.route.loads || []).filter(x => x.state === 'jam').length : 0;
    manualN = plan && plan.route ? (plan.route.warns || []).filter(w => w.indexOf('手动连') >= 0).length : 0;
    overLimit = msg.indexOf('超限') >= 0;
  } catch (e) {
    problems.push('A1 抛异常: ' + e.message);
  }
  if (!problems.length) {
    const rejected = msg.indexOf('放不下') >= 0 || msg.indexOf('先不生成') >= 0;
    const gated = msg.indexOf('超过上限') >= 0;   // RW_MAX_MACHINES 闸门拒绝
    const noRecipe = msg.indexOf('没有机器配方') >= 0;   // 野外采集/种植/灌装变体等 LawRun 不展开的目标（合法跳过）
    if (plan && plan.plan) {
      if (placed === 0) problems.push('A2 生成 0 台（plan 残留或空摆）');
      stats.gen++;
      // A3 布局层台数守恒
      if (plan.plan.objs.length !== plan.res.totalMachines) {
        problems.push('A3 布局层丢机器: objs=' + plan.plan.objs.length + ' res=' + plan.res.totalMachines);
      }
      // A4 无空气机器（external 节点台数恒 0）
      const ghost = plan.res.machines.filter(n => !n.machineId && n.machines > 0);
      if (ghost.length) problems.push('A4 空气机器: ' + ghost.map(n => n.name + '×' + n.machines).join('、'));
      // A5 画布内 + 零重叠（摆下的机器）
      const M = 1, S = size;
      const off = A.LO.objs.filter(o => o.planRole === 'machine' &&
        (o.x < M - 0 || o.y < M - 0 || o.x + o.w > S - M + 1 || o.y + o.d > S - M + 1));
      if (off.length) problems.push('A5 越出画布 ' + off.length + ' 台: maxY=' +
        Math.max.apply(null, A.LO.objs.filter(o => o.planRole === 'machine').map(o => o.y + o.d)));
      const ms = A.LO.objs.filter(o => o.planRole === 'machine');
      let ov2 = 0;
      for (let i = 0; i < ms.length; i++) for (let j = i + 1; j < ms.length; j++) {
        const a = ms[i], b = ms[j];
        if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.d && a.y + a.d > b.y) ov2++;
      }
      if (ov2) problems.push('A5 重叠对数=' + ov2);
      // 画布层台数与报告一致（⑥-2 口径）
      const mMsg = msg.match(/机器 (\d+) 台/);
      if (mMsg && +mMsg[1] !== placed) problems.push('报告虚报: msg=' + mMsg[1] + ' 实摆=' + placed);
    } else if (rejected) {
      if (gated) stats.gate++; else stats.rej++;
    } else if (noRecipe) {
      stats.skip++;   // LawRun 展不开的目标（采集/种植/灌装变体等），合法跳过不计 FAIL
    } else {
      problems.push('A2 异常出口: 无 plan 且 msg 不含「放不下/先不生成」 msg=' + msg.slice(0, 60));
    }
  }
  stats.jam += jamN; stats.manual += manualN;
  if (overLimit) stats.overLimit++;
  if (problems.length) {
    fail++;
    fails.push('FAIL ' + tag + ' :: ' + problems.join(' | '));
    if (!QUIET) console.log('FAIL ' + tag + ' :: ' + problems.join(' | '));
  } else {
    pass++;
    if (!QUIET) console.log('ok   ' + tag + '  ' +
      (plan && plan.plan ? '生成 台' + placed + ' 带' + belts + ' jam' + jamN + ' 手动' + manualN +
        (overLimit ? ' ⚠超限' : '')
        : '拒绝' + (overLimit ? '+超限提示' : '')));
  }
}

for (const t of targets) {
  for (const rate of RATES) {
    for (const size of SIZES) one(t.id, t.name, rate, size);
  }
}

console.log('SCAN ' + targets.length + ' 目标 × 档位' + RATES.join('/') + ' × 规格' + SIZES.join('/') +
  ' = ' + total + ' 格 | pass=' + pass + ' fail=' + fail +
  ' | 生成 ' + stats.gen + ' / 拒绝 ' + stats.rej + ' / 闸门 ' + stats.gate + ' / 跳过 ' + stats.skip +
  ' | 超限提示 ' + stats.overLimit + ' 格 | jam 合计 ' + stats.jam + ' / 手动连合计 ' + stats.manual +
  ' | 用时 ' + ((Date.now() - t0) / 1000).toFixed(1) + 's');
if (fails.length) { console.log(fails.join('\n')); process.exit(1); }
process.exit(0);
