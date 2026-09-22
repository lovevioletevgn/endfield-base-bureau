// 终末地基建知识库 —— 布局试摆「事件层」回归测试
//
// 用法：
//   node tools/test_layout_events.js                 # 测项目里的 终末地基建查询.html
//   node tools/test_layout_events.js <别的.html>      # 测指定文件
//
// 为什么单独一个文件：
//   test_html.js 只调 render()，**从不触发事件**，所以鼠标交互（拖拽框选、拖动移动、
//   双击删除、快捷键）出问题它一律看不见 —— 而这类 bug 在真机上就是「点了没反应」，
//   比渲染坏了更难查。这份用一个迷你 DOM 把 mousedown/mousemove/mouseup 真跑一遍。
//
// 迷你 DOM 覆盖不到的：真实排版与命中测试（坐标是我喂的固定值）。
// 它能抓的是：状态机错乱、坐标换算错、碰撞/越界回滚、撤销栈串味、DOM 引用失效。
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const HTML = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(__dirname, '..', '终末地基建查询.html');
const html = fs.readFileSync(HTML, 'utf8');

let rawCode = null;
for (const mm of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
  if (mm[1].includes('const DB')) { rawCode = mm[1]; break; }
}
if (!rawCode) { console.error('FATAL 找不到含 const DB 的 <script> 段'); process.exit(1); }

// 语法门禁：必须用原始代码（const/let 转 var 会吞掉重复声明错误）
try {
  new vm.Script(rawCode, { filename: 'main.js' });
} catch (e) {
  console.error('FATAL 脚本语法错误（真实浏览器会整段作废 → 页面空白）');
  console.error('  ' + e.name + ': ' + e.message);
  process.exit(1);
}
const code = rawCode.replace(/\bconst\s+/g, 'var ').replace(/\blet\s+/g, 'var ');

// ---------- 迷你 DOM ----------
function mkClassList() {
  const s = new Set();
  return { add(c) { s.add(c); }, remove(c) { s.delete(c); }, contains(c) { return s.has(c); }, _s: s };
}
function matches(el, sel) {
  if (sel === '.lo-canvas') return el._canvas === true;
  if (sel === '.lo-cell') return el._cell === true;
  if (sel === '.card') return el._card === true;
  if (sel === '.lo-gasbar') return el._gasbar === true;   // ⭐v104 就地选气条（画布内浮层）
  // ⭐v109 协议核心出货：内部箭头 .lo-dlv 与选货浮层 .lo-dlvpop 也自成一套点击，
  //   LonMouseDown 里靠 closest 早退 —— 迷你 DOM 必须认识这两个选择器，否则真机上
  //   「点箭头被当成点画布 → 清选中 / 摆新件」这个 bug 在事件层测不出来。
  if (sel === '.lo-dlv') return el._dlv === true;
  if (sel === '.lo-dlvpop') return el._dlvpop === true;
  const m = /^\[data-uid="([^"]+)"\]$/.exec(sel);
  if (m) return !!(el.dataset && el.dataset.uid === m[1]);
  return false;
}
function mkEl(tag) {
  const el = {
    tagName: tag, style: {}, dataset: {}, children: [], parentNode: null,
    className: '', _html: '', classList: mkClassList(),
    appendChild(c) { c.parentNode = el; el.children.push(c); return c; },
    removeChild(c) { const i = el.children.indexOf(c); if (i >= 0) el.children.splice(i, 1); c.parentNode = null; return c; },
    setAttribute() {}, focus() {}, addEventListener() {}, removeEventListener() {},
    // ⭐ closest 必须沿 _host 链逐层匹配到顶，语义才与真实 DOM 一致。
    // v104 踩坑：旧写法「自身不中就返回 _host 一层」导致 cellEl.closest('.lo-gasbar')
    // 恒返回 canvas（真值），v104 的 gasbar 早退 guard 误吞所有格子 mousedown，
    // 撤销栈里只剩 Lput 的摆放项 → Lundo 删对象 → pick(mv.uid) undefined。
    closest(sel) {
      let n = el;
      while (n) { if (matches(n, sel)) return n; n = n._host; }
      return null;
    },
    querySelectorAll(sel) { return (el._cells || []).filter(c => matches(c, sel)); },
    querySelector(sel) { const a = (el._cells || []).filter(c => matches(c, sel)); return a.length ? a[0] : null; },
    getBoundingClientRect() { return el._rect || { left: 0, top: 0, width: 0, height: 0 }; },
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(v) { el._html = String(v); onOutHtml(el); },
  });
  return el;
}

const outEl = mkEl('div');
const canvas = mkEl('div');
canvas._canvas = true;

// render() 把 HTML 塞进 #out 的 innerHTML；这里顺手把画布里的格子解析成对象
function onOutHtml(el) {
  const v = el._html;
  if (v.indexOf('lo-canvas') < 0) return;
  canvas._cells = [];
  const re = /<div class="lo-cell((?: [^"]*)?)" data-uid="([^"]+)"/g;
  let m;
  while ((m = re.exec(v))) {
    const c = mkEl('div');
    c._cell = true;
    c._host = canvas;
    c.dataset = { uid: m[2] };
    if (m[1].indexOf('sel') >= 0) c.classList.add('sel');
    canvas._cells.push(c);
  }
  // ⚠️ 别用"一条正则从 class 一路匹配到 px\"" 的写法：style 里后来加了 --locell 前缀和
  // transform，末尾不再是 height:(\d+)px\" 直接收尾，那种正则从 v14 起就静默失配，
  // _rect 一直是全 0 兜底值，老断言全靠 left=0 凑巧通过（2026-09-21 发现）。先取 style 值再拆。
  const sv = (/class="lo-canvas" style="([^"]*)"/.exec(v) || [])[1] || "";
  const mw = /width:(\d+)px/.exec(sv), mh = /height:(\d+)px/.exec(sv);
  if (mw && mh) canvas._rect = { left: 0, top: 0, width: +mw[1], height: +mh[1] };

  // ⭐v109 协议核心出货块：解析出 .lo-dlv 与 .lo-dlvpop，挂到画布上（供事件层探针使用）
  canvas._dlvs = [];
  canvas._dlvpop = null;
  const dre = /<div class="lo-dlv( set)?" style="left:(-?[\d.]+)px;top:(-?[\d.]+)px"/g;
  let dm2;
  while ((dm2 = dre.exec(v))) {
    const d = mkEl('div');
    d._dlv = true; d._host = canvas;
    if (dm2[1]) d.classList.add('set');
    canvas._dlvs.push(d);
  }
  if (v.indexOf('class="lo-dlvpop"') >= 0) {
    const p = mkEl('div');
    p._dlvpop = true; p._host = canvas;
    canvas._dlvpop = p;
  }
}

const doc = {
  body: mkEl('body'),
  querySelector(sel) {
    if (sel === '.lo-canvas') return canvas;
    if (sel === '#out') return outEl;
    return mkEl(sel);
  },
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

let pass = 0, fail = 0;
const log = [];
function chk(name, cond, extra) {
  if (cond) pass++;
  else { fail++; log.push('  FAIL ' + name + (extra ? '  :: ' + extra : '')); }
}

try {
  vm.runInContext(code, ctx, { timeout: 20000 });
} catch (e) {
  console.log('CTX ERROR: ' + e.message + '\n' + e.stack);
  process.exit(1);
}
const A = ctx;

const CELL = A.LOCELL;   // 格子边长从页面读，别硬编码（v14 起默认 14→20）
// 格子中心坐标（画布左上角是 0,0）
function px(cell) { return cell * CELL + CELL / 2; }
function ev(target, cx, cy, opt) {
  return Object.assign({
    button: 0, target: target, clientX: cx, clientY: cy,
    shiftKey: false, preventDefault() {}, _pd: false,
  }, opt || {});
}
function cellEl(uid) { return canvas._cells.filter(c => c.dataset.uid === uid)[0]; }
function pick(uid) { return A.LO.objs.filter(o => o.uid === uid)[0]; }

function resetCanvas(size) {
  A.Linit();   // LO 是懒初始化的，第一次得先建出来
  A.LO.objs = []; A.LO.sel = []; A.LO.undo = []; A.LO.redo = [];
  A.LO.pickRot = 0; A.LO.msg = ''; A.LO.pick = null; A.LO.size = size || 40;
  A.LO.lastT = 0; A.LO.lastUid = '';
  A.tab = 'layout';
  A.render();
}

// 挑两座小占地建筑，坐标好算（1×1 最好，没有就取最小的）
const small = A.DB.blueprint.buildings
  .slice()
  .sort((a, b) => {
    const f = x => x.gridFootprint.split('×').map(Number);
    return f(a)[0] * f(a)[1] - f(b)[0] * f(b)[1];
  })[0];
const SF = small.gridFootprint.split('×').map(Number);

// ---------- 1. 点击摆放 / 点空取消选中 ----------
resetCanvas(40);
A.Lpick(small.id);
A.LonMouseDown(ev(canvas, px(5), px(5)));
A.LonMouseUp();
chk('点画布摆下一座', A.LO.objs.length === 1, String(A.LO.objs.length));
const first = A.LO.objs[0];
chk('落在点击的格位上', first.x === 5 && first.y === 5, first.x + ',' + first.y);
chk('摆放后自动选中', A.LO.sel.length === 1, String(A.LO.sel.length));

A.LonMouseDown(ev(canvas, px(30), px(30)));
A.LonMouseUp();
chk('继续点继续摆（选中跟着新建筑走）', A.LO.objs.length === 2 && A.LO.sel.length === 1,
    A.LO.objs.length + '/' + A.LO.sel.length);

// 没有待放置建筑时，点空白只取消选中
A.LO.pick = null;
A.LonMouseDown(ev(canvas, px(38), px(38)));
A.LonMouseUp();
chk('没有待放置建筑时点空白不摆新东西', A.LO.objs.length === 2, String(A.LO.objs.length));
chk('点空白清空选中', A.LO.sel.length === 0, String(A.LO.sel.length));

// ---------- 2. 拖拽框选 ----------
resetCanvas(40);
A.Lpick(small.id);
A.Lput(2, 2); A.Lput(20, 2); A.Lput(2, 20);
chk('摆了三座（框选前提）', A.LO.objs.length === 3, String(A.LO.objs.length));
A.LO.sel = [];

const t0 = cellEl(A.LO.objs[0].uid);
chk('框选前画布上能查到格子元素', !!t0, t0 ? t0.dataset.uid : 'none');
A.LonMouseDown(ev(canvas, px(0), px(0)));
chk('空白处按下进入框选态', !!A.LODRAG && A.LODRAG.mode === 'band');
A.LonMouseMove(ev(canvas, px(10), px(10)));
chk('拖拽生成橡皮筋矩形', canvas.children.some(c => c.className === 'lo-band'),
    String(canvas.children.length));
const band = canvas.children.filter(c => c.className === 'lo-band')[0];
chk('橡皮筋尺寸跟手（10 格 = ' + (10 * CELL) + 'px）', band && band.style.width === String(10 * CELL) + 'px', band ? band.style.width : 'none');

A.LonMouseUp();
chk('框选命中左上角 1 座', A.LO.objs.length === 3 && A.LO.sel.length === 1, String(A.LO.sel.length));
chk('框选后橡皮筋被移除', !canvas.children.some(c => c.className === 'lo-band'));
chk('框选把命中项标记成选中态', cellEl(A.LO.sel[0]).classList.contains('sel'));
A.render();
chk('渲染结果里选中态是 lo-cell sel', outEl._html.indexOf('lo-cell sel') >= 0);

// 框选整片
A.LonMouseDown(ev(canvas, px(-1) + 1, px(-1) + 1));
A.LonMouseMove(ev(canvas, px(39), px(39)));
A.LonMouseUp();
chk('框选全画布命中 3 座', A.LO.sel.length === 3, String(A.LO.sel.length));

// ---------- 3. 拖动整体移动 ----------
resetCanvas(40);
A.Lpick(small.id);
A.Lput(2, 2);
const mv = A.LO.objs[0];
A.LonMouseDown(ev(cellEl(mv.uid), px(2), px(2)));
chk('按在建筑上进入移动态', A.LODRAG && A.LODRAG.mode === 'move');
A.LonMouseMove(ev(canvas, px(5), px(4)));
chk('拖动时 DOM 位置即时预览（先动 DOM，松手才落数据）',
    cellEl(mv.uid).style.left === String(5 * CELL) + 'px',
    cellEl(mv.uid).style.left);
chk('拖动中不写数据', mv.x === 2 && mv.y === 2, mv.x + ',' + mv.y);
A.LonMouseUp();
chk('松手落到新格位', mv.x === 5 && mv.y === 4, mv.x + ',' + mv.y);
chk('移动写入撤销栈', A.LO.undo.length > 0, String(A.LO.undo.length));
A.Lundo();
chk('撤销移动回到原位', pick(mv.uid).x === 2 && pick(mv.uid).y === 2,
    pick(mv.uid).x + ',' + pick(mv.uid).y);

// 拖到别人身上要被挡回
resetCanvas(40);
A.Lpick(small.id);
A.Lput(2, 2); A.Lput(2, 20);
const mover = A.LO.objs[0];
A.LselIn(0, 0, 10, 10);
chk('拖动前只选中被拖的那座', A.LO.sel.length === 1 && A.LO.sel[0] === mover.uid);
A.LonMouseDown(ev(cellEl(mover.uid), px(2), px(2)));
A.LonMouseMove(ev(canvas, px(2), px(20)));
A.LonMouseUp();
chk('拖到已占位置会被挡回原处', mover.x === 2 && mover.y === 2, mover.x + ',' + mover.y);
chk('被挡时有提示', String(A.LO.msg).indexOf('还原') >= 0, String(A.LO.msg));

// ---------- 4. 单击选中 / 双击移除 ----------
resetCanvas(40);
A.Lpick(small.id);
A.Lput(3, 3); A.Lput(20, 3);
const dbl = A.LO.objs[0];
A.LO.sel = []; A.LO.lastT = 0; A.LO.lastUid = '';
A.LonMouseDown(ev(cellEl(dbl.uid), px(3), px(3)));
A.LonMouseUp();
chk('单击选中', A.LO.sel.length === 1 && A.LO.objs.length === 2, String(A.LO.objs.length));
A.LonMouseDown(ev(cellEl(dbl.uid), px(3), px(3)));
A.LonMouseUp();
chk('同一座快速点第二下 = 双击移除', A.LO.objs.length === 1 && A.LO.objs[0].uid !== dbl.uid,
    String(A.LO.objs.length));
A.Lundo();
chk('双击移除可撤销', A.LO.objs.length === 2, String(A.LO.objs.length));

// 两次点不同的建筑不算双击
resetCanvas(40);
A.Lpick(small.id);
A.Lput(3, 3); A.Lput(20, 3);
const a1 = A.LO.objs[0].uid, a2 = A.LO.objs[1].uid;
A.LO.lastT = 0; A.LO.lastUid = '';
A.LonMouseDown(ev(cellEl(a1), px(3), px(3))); A.LonMouseUp();
A.LonMouseDown(ev(cellEl(a2), px(20), px(3))); A.LonMouseUp();
chk('连点两座不同建筑不误删', A.LO.objs.length === 2, String(A.LO.objs.length));

// ---------- 5. 快捷键 ----------
function key(k, opt) {
  const e = Object.assign({ key: k, target: null, ctrlKey: false, metaKey: false, shiftKey: false, preventDefault() {} }, opt || {});
  A.LonKeyDown(e);
  return e;
}
resetCanvas(40);
A.Lpick(small.id);
A.Lput(5, 5);
const kb = A.LO.objs[0];
const w0 = kb.w, d0 = kb.d;
key('r');
chk('R 旋转选中建筑', kb.rot === 90 && kb.w === d0 && kb.d === w0, kb.rot + ' ' + kb.w + '×' + kb.d);
key('z', { ctrlKey: true });
chk('Ctrl+Z 撤销旋转', pick(kb.uid).rot === 0, String(pick(kb.uid).rot));
key('y', { ctrlKey: true });
chk('Ctrl+Y 重做旋转', pick(kb.uid).rot === 90, String(pick(kb.uid).rot));
const before = A.LO.objs.length;
key('d', { ctrlKey: true });
chk('Ctrl+D 复制选中', A.LO.objs.length === before + 1, String(A.LO.objs.length));
key('Delete');
chk('Delete 删除选中', A.LO.objs.length === before, String(A.LO.objs.length));
A.LselIn(-1, -1, 41, 41);
key('Escape');
chk('Esc 取消选中', A.LO.sel.length === 0, String(A.LO.sel.length));
// 搜索框里打字不能被抢键
const r0 = pick(kb.uid).rot;
key('r', { target: { tagName: 'INPUT' } });
chk('输入框里按 R 不触发旋转', pick(kb.uid).rot === r0, String(pick(kb.uid).rot));

// ---------- 5b. 物流件连铺（mousedown → mousemove → mouseup） ----------
// 这是唯一「拿着东西在空白处拖动」的手势：手里是建筑时拖 = 框选，手里是物流件时拖 = 连铺。
// 两条路都压一次撤销栈，必须各测一遍，别只测渲染。
resetCanvas(40);
A.Lpick('grid_belt_01');
A.LonMouseDown(ev(canvas, px(0), px(0)));
chk('拿物流件在空白格按下进入连铺态', !!A.LODRAG && A.LODRAG.mode === 'lay',
    A.LODRAG ? A.LODRAG.mode : 'null');
chk('按下即铺下起手那一格', A.LO.objs.length === 1, String(A.LO.objs.length));
A.LonMouseMove(ev(canvas, px(6), px(0)));
chk('横向拖动一次铺满一排 7 格', A.LO.objs.length === 7, String(A.LO.objs.length));
chk('每格走向朝下一格（0°=右）', A.LO.objs.every(o => o.rot === 0),
    A.LO.objs.map(o => o.rot).join(','));
A.LonMouseMove(ev(canvas, px(3), px(0)));
chk('往回拖不留残段（只剩 4 格）', A.LO.objs.length === 4, String(A.LO.objs.length));
A.LonMouseUp();
chk('松手后选中整段', A.LO.sel.length === 4, String(A.LO.sel.length));
chk('整段手势只压一次撤销栈', A.LO.undo.length === 1, String(A.LO.undo.length));
chk('松手后拖拽态清空', A.LODRAG === null);
A.Lundo();
chk('撤销把整段一次撤掉', A.LO.objs.length === 0, String(A.LO.objs.length));

// 竖向连铺 + 走向
resetCanvas(40);
A.Lpick('log_pipe_01');
A.LonMouseDown(ev(canvas, px(2), px(2)));
A.LonMouseMove(ev(canvas, px(2), px(6)));
A.LonMouseUp();
chk('竖向拖动按列铺 5 格', A.LO.objs.length === 5 && A.LO.objs.every(o => o.x === 2),
    A.LO.objs.length + ' 格');
chk('竖向走向是 90°（下）', A.LO.objs.every(o => o.rot === 90),
    A.LO.objs.map(o => o.rot).join(','));

// 压到建筑上要跳过那几格，而不是整段作废
resetCanvas(40);
const oneByOne = A.DB.blueprint.buildings.find(b => b.gridFootprint === '1×1');
A.Lpick(oneByOne.id); A.Lput(3, 0);
A.Lpick('grid_belt_01');
A.LonMouseDown(ev(canvas, px(0), px(0)));
A.LonMouseMove(ev(canvas, px(9), px(0)));
A.LonMouseUp();
const beltCells = A.LO.objs.filter(o => o.id === 'grid_belt_01');
chk('连铺跳过被建筑占住的格（10 格留 9 格）', beltCells.length === 9, String(beltCells.length));
chk('连铺没压在建筑上', !beltCells.some(o => o.x === 3 && o.y === 0),
    beltCells.map(o => o.x).join(','));

// 手里是建筑时仍然是「点一下摆一座」，不能变成连铺
resetCanvas(40);
A.Lpick(small.id);
A.LonMouseDown(ev(canvas, px(1), px(1)));
chk('拿着建筑时不进连铺态', A.LODRAG.mode === 'band', A.LODRAG.mode);
A.LonMouseMove(ev(canvas, px(8), px(1)));
A.LonMouseUp();
chk('建筑拖拽仍是框选，没顺手多摆东西', A.LO.objs.length === 0, String(A.LO.objs.length));
A.LonMouseDown(ev(canvas, px(1), px(1)));
A.LonMouseUp();
chk('建筑单击仍然摆一座', A.LO.objs.length === 1, String(A.LO.objs.length));

// 物流件的单击摆放（点画布 = 摆一格）与旋转
resetCanvas(40);
A.Lpick('log_splitter');
A.LonMouseDown(ev(canvas, px(4), px(4)));
A.LonMouseUp();
chk('物流件单击也能摆一格', A.LO.objs.length === 1, String(A.LO.objs.length));
const sp = A.LO.objs[0];
chk('物流件摆放后自动选中', A.LO.sel.length === 1 && A.LO.sel[0] === sp.uid);
key('r');
chk('R 转物流件走向但不位移', sp.rot === 90 && sp.x === 4 && sp.y === 4,
    sp.rot + ' @' + sp.x + ',' + sp.y);
key('z', { ctrlKey: true });
chk('物流件旋转可撤销', pick(sp.uid).rot === 0, String(pick(sp.uid).rot));

// 接口显示开关（工具栏按钮）
resetCanvas(40);
A.Lpick('shaper_1'); A.Lput(6, 6);
A.render();
chk('默认渲染出接口标记', outEl._html.indexOf('lo-port') >= 0);
A.LtogglePort(); A.render();
chk('关掉接口后不再渲染 lo-port', outEl._html.indexOf('lo-port') < 0);
A.LtogglePort(); A.render();
chk('再打开又有了', outEl._html.indexOf('lo-port') >= 0);

// ---------- 6. 事件层不该破坏其他 tab ----------
A.tab = 'building';
A.render();
A.LonMouseDown(ev(canvas, px(1), px(1)));
chk('非布局页按下画布不进入拖拽态', A.LODRAG === null);
A.LonMouseUp();
chk('非布局页松手不报错', true);
A.tab = 'layout';
A.render();

// ---------- 7. 视角旋转后的坐标换算（Lxy 逆变换）----------
// 画布是正方形，CSS rotate 后包围盒尺寸不变；视口坐标要按角度逆变换回画布坐标。
// 四个角度各取一个"旋转后跑到对角"的视口点，点它必须落回画布格 (0,0)。
A.Linit();
A.LO.objs = []; A.LO.sel = []; A.LO.undo = []; A.LO.redo = []; A.LO.viewRot = 0;
A.render();
const rotW = canvas._rect.width;
const rotCases = [[90, rotW - 10, 10], [180, rotW - 10, rotW - 10], [270, 10, rotW - 10], [0, 10, 10]];
for (const [deg, vx, vy] of rotCases) {
  A.LO.viewRot = deg; A.render();
  const r = A.Lxy({ clientX: vx, clientY: vy }, canvas);
  chk('视角旋转 ' + deg + '°：视口点 (' + vx + ',' + vy + ') 落回画布格 (0,0)',
      Math.floor(r.fx) === 0 && Math.floor(r.fy) === 0,
      r.fx.toFixed(2) + ',' + r.fy.toFixed(2));
}
// 转了视角之后再点摆：落点必须跟视口一致（这是"转镜头"的实用性所在）
A.LO.viewRot = 90; A.render();
A.Lpick('storager_1');
A.LonMouseDown(ev(canvas, rotW - 10, 10));
A.LonMouseUp();
const rotPut = A.LO.objs[A.LO.objs.length - 1];
chk('视角旋转 90°：点右上角摆下的建筑落在画布格 (0,0)',
    rotPut && rotPut.x === 0 && rotPut.y === 0, rotPut ? rotPut.x + ',' + rotPut.y : 'none');
A.LO.viewRot = 0; A.LO.objs = []; A.LO.pick = null; A.render();

// ---------- ⑤-1 局部锁定：锁定件在事件层动不了（2026-09-22）----------
// test_html.js 只调 render()，看不见「按下去还能拖走」这类问题 —— 这条必须在事件层守。
resetCanvas(40);
A.Lpick(small.id);
A.Lput(2, 2);
const lkg = A.LO.objs[0];
A.LO.sel = [lkg.uid];
A.LlockSel(true);
chk('事件层：锁定件进拖动集合为空', (() => {
  A.LonMouseDown(ev(cellEl(lkg.uid), px(2), px(2)));
  const st = A.LODRAG;
  return !st || (st.sel || []).length === 0;
})(), A.LODRAG ? JSON.stringify(A.LODRAG.sel) : 'null');
A.LonMouseMove(ev(canvas, px(9), px(9)));
A.LonMouseUp();
chk('事件层：按在锁定件上拖动，位置一格不动', lkg.x === 2 && lkg.y === 2, lkg.x + ',' + lkg.y);
chk('事件层：给出「动不了」的提示', (A.LO.msg || '').indexOf('锁定') >= 0, A.LO.msg);
// 双击锁定件不能误删
A.LonMouseDown(ev(cellEl(lkg.uid), px(2), px(2)));
A.LonMouseUp();
A.LonMouseDown(ev(cellEl(lkg.uid), px(2), px(2)));
A.LonMouseUp();
chk('事件层：双击锁定件不会误删', A.LO.objs.length === 1, String(A.LO.objs.length));
// L 键 = 锁定 / 解锁（选中已锁 → 解锁）
const keyEv = k => ({ key: k, target: null, ctrlKey: false, metaKey: false, shiftKey: false, preventDefault() {} });
A.LO.sel = [lkg.uid];
A.LonKeyDown(keyEv('l'));
chk('事件层：L 键给已锁的选中项解锁', !pick(lkg.uid).lock);
A.LO.sel = [pick(lkg.uid).uid];
A.LonKeyDown(keyEv('l'));
chk('事件层：L 键再按一次又锁上', !!pick(lkg.uid).lock);
A.LO.sel = [lkg.uid];
A.LunlockAll();

// ---------- v104 就地选气条：点色块不能被当成「点画布摆放」 ----------
// 博士 2026-09-23 实测：手里拿着散布机时点选气条色块 → 又摆了一座（mousedown 冒泡进画布
// 摆放逻辑 → 清选中 → mouseup 判「单击空白 + 有 pick」→ Lput）。修复 = LonMouseDown 入口排除 .lo-gasbar。
resetCanvas(40);
A.Lpick('vaporizer_1');
A.LonMouseDown(ev(canvas, px(5), px(5)));
A.LonMouseUp();
chk('事件层：先摆下一座散布机（前提）', A.LO.objs.length === 1 && A.LO.objs[0].id === 'vaporizer_1',
    A.LO.objs.length + ' ' + (A.LO.objs[0] && A.LO.objs[0].id));
const gasBtn = mkEl('button');
gasBtn._gasbar = true;
gasBtn._host = canvas;          // DOM 上选气条挂在画布里，closest 链要能走到 canvas
const _n = A.LO.objs.length, _sn = A.LO.sel.length;
A.LonMouseDown(ev(gasBtn, px(6), px(3)));
A.LonMouseUp();
chk('事件层：点选气条色块不摆新建筑（v104 修复的正是这个）', A.LO.objs.length === _n,
    A.LO.objs.length + ' vs ' + _n);
chk('事件层：点选气条不清掉选中（LgasSet 还能批量生效）', A.LO.sel.length === _sn,
    A.LO.sel.length + ' vs ' + _sn);

// ---------- v107 拐弯第一轴跟手势轨迹（博士图2「想要红箭头那种」）----------
// 手势：起手 (2,2) → 先往上拖到 (2,5) → 再往右拖到 (5,5)。旧版按总位移定轴（|dx|>=|dy|），
// 3>=3 先横，画成镜像；v107 轨迹里 y 先偏移过 1 格 → 第一轴 = 竖。
resetCanvas(40);
A.Lpick('grid_belt_01');
A.LonMouseDown(ev(canvas, px(2), px(2)));
A.LonMouseMove(ev(canvas, px(2), px(5)));
A.LonMouseMove(ev(canvas, px(5), px(5)));
A.LonMouseUp();
const v107cells = A.LO.objs.map(o => o.x + ',' + o.y);
chk('事件层：轨迹先竖后横铺出 7 格', A.LO.objs.length === 7, v107cells.join(' '));
const v107bend = A.LO.objs.filter(o => o.x === 2 && o.y === 5)[0];
chk('事件层：拐弯格在轨迹转折点 (2,5)、朝向第二轴（rot=0）',
    !!v107bend && v107bend.rot === 0, v107bend ? 'rot=' + v107bend.rot : '缺格');
chk('事件层：先铺的是竖段（起手第一方向优先）',
    A.LO.objs.filter(o => o.x === 2).length === 4 &&
    A.LO.objs.filter(o => o.y === 5).length === 4,
    v107cells.join(' '));

// ---------- v108 从机器口格（游戏里的「红圈」）起手拉带子 ----------
// 博士 2026-09-23：「游戏里是从红圈里开始拉」——按在机器朝外的输出口格上，
// 带子要从口**外**那一格开始铺，不能把口格自己占了。
resetCanvas(40);
(function () {
  const fb = A.DB.blueprint.buildings.find(b => b.id === 'furnance_1');
  A.Lpick('furnance_1'); A.Lput(4, 4);
  const rods = [];
  (fb.ports || []).forEach(p => {
    const q = A.LportXY(p, 0, 3, 3), d = A.LportDir(q, 3, 3);
    rods.push({ kind: p.kind, gx: 4 + q.x, gy: 4 + q.z, dir: d });
  });
  const ro = rods.filter(p => p.kind === 'output' && p.dir === 'r')[0];
  const DV = { r: [1, 0], l: [-1, 0], d: [0, 1], u: [0, -1] };
  const ox = ro.gx + DV.r[0], oy = ro.gy + DV.r[1];
  A.Lpick('grid_belt_01');
  A.LO.undo = [];   /* 摆机器那层撤掉别算进来：只量本次手势压了几层 */
  A.LonMouseDown(ev(canvas, px(ro.gx), px(ro.gy)));   // 按在「红圈」口格上
  chk('事件层：按在输出口格上进连铺态并从口外起手',
      !!A.LODRAG && A.LODRAG.mode === 'lay' && A.LODRAG.sx === ox && A.LODRAG.sy === oy,
      A.LODRAG ? A.LODRAG.mode + ' ' + A.LODRAG.sx + ',' + A.LODRAG.sy : 'null');
  A.LonMouseMove(ev(canvas, px(ox + 3), px(oy)));
  A.LonMouseUp();
  const bv = A.LO.objs.filter(o => o.id === 'grid_belt_01');
  chk('事件层：从红圈起手铺出的带子不含口格',
      bv.length === 4 && !bv.some(o => o.x === ro.gx && o.y === ro.gy),
      bv.map(o => o.x + ',' + o.y).join(' '));
  chk('事件层：整段手势只压一次撤销栈', A.LO.undo.length === 1, String(A.LO.undo.length));
})();

// ---------- v109 口上「点击=拉线 / 拖动=移机器」待决态（博士：「点机器口机器会被拖动」）----------
// 手里拿着物流件、按在机器的口格上：旧版直接进 move → 想从口红圈拉线，一动就把机器拖走了。
// v109：先只选中进 portpend（机器不动）→ 原地松手 = 从口外起手铺；拖过阈值 = 转 move 移机器。
function v109Setup() {
  resetCanvas(40);
  const fb = A.DB.blueprint.buildings.find(b => b.id === 'furnance_1');
  A.Lpick('furnance_1'); A.Lput(4, 4);
  const o = A.LO.objs.filter(q => q.id === 'furnance_1')[0];
  const rods = [];
  (fb.ports || []).forEach(p => {
    const q = A.LportXY(p, 0, 3, 3), d = A.LportDir(q, 3, 3);
    rods.push({ kind: p.kind, gx: 4 + q.x, gy: 4 + q.z, dir: d });
  });
  const ro = rods.filter(p => p.kind === 'output' && p.dir === 'r')[0];
  const DV = { r: [1, 0], l: [-1, 0], d: [0, 1], u: [0, -1] };
  return { o: o, ro: ro, ox: ro.gx + DV.r[0], oy: ro.gy + DV.r[1] };
}
// 1) 按在口上 → 待决态，机器没被拖
var s1 = v109Setup();
A.LO.pick = null; A.Lpick('grid_belt_01');
A.LonMouseDown(ev(cellEl(s1.o.uid), px(s1.ro.gx), px(s1.ro.gy)));
chk('事件层：手拿物流件按在口格上进「待决态」', !!A.LODRAG && A.LODRAG.mode === 'portpend',
    A.LODRAG ? A.LODRAG.mode : 'null');
A.LonMouseMove(ev(cellEl(s1.o.uid), px(s1.ro.gx), px(s1.ro.gy)));   // 原地抖一下（未过阈值）
chk('事件层：原地没动时仍是待决态（不误移动机器）',
    !!A.LODRAG && A.LODRAG.mode === 'portpend' && A.LO.objs.filter(q => q.id === 'furnance_1')[0].x === 4,
    A.LODRAG ? A.LODRAG.mode : 'null');
// 2) 原地松手 → 从口外起手铺
A.LonMouseUp();
chk('事件层：口上原地松手 = 从口外起手铺（mode=lay）',
    !!A.LODRAG && A.LODRAG.mode === 'lay' && A.LODRAG.sx === s1.ox && A.LODRAG.sy === s1.oy,
    A.LODRAG ? A.LODRAG.mode + ' ' + A.LODRAG.sx + ',' + A.LODRAG.sy : 'null');
chk('事件层：拉线起手后机器仍在原位（没被拖走）',
    A.LO.objs.filter(q => q.id === 'furnance_1')[0].x === 4 && A.LO.objs.filter(q => q.id === 'furnance_1')[0].y === 4,
    A.LO.objs.filter(q => q.id === 'furnance_1').map(q => q.x + ',' + q.y).join(''));
A.LonMouseMove(ev(canvas, px(s1.ox + 3), px(s1.oy)));
A.LonMouseUp();
chk('事件层：从口外拉出的带子不含口格',
    A.LO.objs.filter(q => q.id === 'grid_belt_01').length === 4 &&
    !A.LO.objs.some(q => q.id === 'grid_belt_01' && q.x === s1.ro.gx && q.y === s1.ro.gy),
    A.LO.objs.filter(q => q.id === 'grid_belt_01').map(q => q.x + ',' + q.y).join(' '));
// 3) 口上按下后拖过阈值 → 移机器（旧习惯保留），且不误铺
var s3 = v109Setup();
A.LO.pick = null; A.Lpick('grid_belt_01');
const nBefore3 = A.LO.objs.filter(q => q.id === 'grid_belt_01').length;
A.LonMouseDown(ev(cellEl(s3.o.uid), px(s3.ro.gx), px(s3.ro.gy)));
A.LonMouseMove(ev(cellEl(s3.o.uid), px(s3.ro.gx + 2), px(s3.ro.gy)));
chk('事件层：口上拖过阈值 → 转成移动机器', !!A.LODRAG && A.LODRAG.mode === 'move',
    A.LODRAG ? A.LODRAG.mode : 'null');
A.LonMouseUp();
chk('事件层：口上拖动移机器、不误铺物流件',
    A.LO.objs.filter(q => q.id === 'furnance_1')[0].x === 6 &&
    A.LO.objs.filter(q => q.id === 'grid_belt_01').length === nBefore3,
    A.LO.objs.filter(q => q.id === 'furnance_1').map(q => q.x + ',' + q.y).join(''));
// 4) 手里没拿物流件时点口 → 普通移动（不误进待决态）
var s4 = v109Setup();
A.LO.pick = null;
A.LonMouseDown(ev(cellEl(s4.o.uid), px(s4.ro.gx), px(s4.ro.gy)));
chk('事件层：空手点口走普通移动（不误进待决态）',
    !!A.LODRAG && A.LODRAG.mode === 'move' && A.LO.sel.length === 1,
    A.LODRAG ? A.LODRAG.mode : 'null');
A.LonMouseUp();
// 5) 拿物流件按机器**非口格**（正中）→ 仍是普通移动
var s5 = v109Setup();
A.LO.pick = null; A.Lpick('grid_belt_01');
A.LonMouseDown(ev(cellEl(s5.o.uid), px(5), px(5)));
chk('事件层：拿件按机器内部（非口格）仍是普通移动',
    !!A.LODRAG && A.LODRAG.mode === 'move', A.LODRAG ? A.LODRAG.mode : 'null');
A.LonMouseUp();
A.LO.pick = null;

// ---------- v109 第二半：协议核心出货箭头（博士：「出货口可以点击选择物品出货」+「内部给个箭头」）----------
// 箭头 .lo-dlv 是画布内的可点浮层，LonMouseDown 必须放行 —— 否则点箭头会被当成
// 「点画布」：清掉选中、手里有件时还会顺手再摆一座（v104 的 gasbar 同款坑）。
resetCanvas(40);
(function () {
  A.Lpick('sp_hub_1'); A.Lput(4, 4);
  const hub = A.LO.objs.filter(o => o.id === 'sp_hub_1')[0];
  A.LO.pick = null; A.LO.sel = [hub.uid];
  A.render();
  chk('事件层：协议核心渲染出 6 个出货箭头', canvas._dlvs.length === 6, String(canvas._dlvs.length));

  // 1) 手里拿着物流件点箭头 → 不能摆出新件、不能清选中、不能起拖
  A.Lpick('grid_belt_01');
  const nBefore = A.LO.objs.filter(o => o.id === 'grid_belt_01').length;
  const selBefore = A.LO.sel.slice();
  const arrow = canvas._dlvs[0];
  A.LonMouseDown(ev(arrow, px(0), px(0)));
  chk('事件层：手拿物流件点出货箭头 → 不摆新件',
      A.LO.objs.filter(o => o.id === 'grid_belt_01').length === nBefore,
      nBefore + ' → ' + A.LO.objs.filter(o => o.id === 'grid_belt_01').length);
  chk('事件层：点出货箭头不清掉选中', A.LO.sel.join() === selBefore.join(),
      A.LO.sel.join() + ' vs ' + selBefore.join());
  chk('事件层：点出货箭头不起拖动（LODRAG 仍为 null）', A.LODRAG === null,
      A.LODRAG ? A.LODRAG.mode : 'null');

  // 2) 空手点箭头同样不能摆件 / 清选中
  A.LO.pick = null;
  A.LO.sel = [hub.uid];
  const n2 = A.LO.objs.length;
  A.LonMouseDown(ev(canvas._dlvs[1], px(0), px(0)));
  chk('事件层：空手点出货箭头 → 画布对象数不变', A.LO.objs.length === n2,
      n2 + ' → ' + A.LO.objs.length);
  chk('事件层：空手点出货箭头不清选中', A.LO.sel.indexOf(hub.uid) >= 0, A.LO.sel.join());

  // 3) 点选货浮层本体（.lo-dlvpop）也要放行
  A.LO.dlvPop = { uid: hub.uid, idx: 0 };
  A.render();
  chk('事件层：浮层打开后渲染出 .lo-dlvpop', !!canvas._dlvpop);
  A.LO.pick = null;
  A.LO.sel = [hub.uid];
  const n3 = A.LO.objs.length;
  A.LonMouseDown(ev(canvas._dlvpop, px(0), px(0)));
  chk('事件层：点选货浮层本体 → 不摆件、不清选中、不起拖',
      A.LO.objs.length === n3 && A.LO.sel.indexOf(hub.uid) >= 0 && A.LODRAG === null,
      A.LO.objs.length + ' sel=' + A.LO.sel.join() + ' drag=' + (A.LODRAG ? A.LODRAG.mode : 'null'));
  A.LO.dlvPop = null;

  // 4) 点画布别处 → 顺手收起浮层（浮层外点击 = 关闭）
  A.LO.dlvPop = { uid: hub.uid, idx: 0 };
  A.LO.pick = null;
  A.LonMouseDown(ev(canvas, px(30), px(30)));
  chk('事件层：点画布别处 → 自动收起选货浮层', A.LO.dlvPop === null,
      JSON.stringify(A.LO.dlvPop));
  A.LonMouseUp();

  // 5) 选货走 LdlvPick：写入 → 再点同一件 → 取消
  A.LO.pick = null;
  const cand = A.hubCands(A.hubDomainOf(hub))[0];
  A.LdlvPick(hub.uid, 3, cand.id);
  chk('事件层：LdlvPick 把货记到该口上',
      A.hubPickGet(hub, 3) === cand.id, A.hubPickGet(hub, 3));
  A.LdlvPick(hub.uid, 3, cand.id);
  chk('事件层：再点同一件 → 取消该口出货',
      A.hubPickGet(hub, 3) === '', JSON.stringify(A.hubPickGet(hub, 3)));
  chk('事件层：取消后该核心记录清空', Object.keys(A.hubPicksOf(hub)).length === 0);

  // 6) 出货记录挂在对象上、与「移动机器」无关；撤销不该动它（它不属于 Lsnap 快照）
  const cand2 = A.hubCands(A.hubDomainOf(hub))[1];
  A.LdlvPick(hub.uid, 0, cand2.id);
  const keep = A.hubPickGet(hub, 0);
  A.Lpush(); A.Lundo();
  chk('事件层：撤销不影响已选的出货物品（独立于摆放快照）',
      A.hubPickGet(hub, 0) === keep && !!keep, keep);
})();
A.LO.pick = null;

log.unshift(`RESULT pass=${pass} fail=${fail}`);
console.log(log.join('\n'));
process.exit(fail ? 1 : 0);
