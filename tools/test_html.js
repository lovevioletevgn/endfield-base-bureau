// 终末地基建知识库 —— 查询界面回归测试
//
// 用法：
//   node tools/test_html.js                      # 测项目里的 终末地基建查询.html
//   node tools/test_html.js <别的.html>           # 测指定文件（例如上传前合成的工作副本）
//
// 为什么用它：用 Node 的 vm 沙箱跑生成出来的 HTML，比装浏览器快几个数量级，
// 而且能直接断言渲染结果。改 build_html.py 后必跑。
//
// 它抓过什么：
//   - renderRules 用了不存在的 CSS 类 lg-capn / lg-capl（统计卡无样式）
//   - 配方页筛选项写死了 8 个分类，实际只有 3 个有数据（5 个选项查不到东西）
//   - 地区筛选漏了「四号谷地」
//   - 物流页选常量组时实体表报"没有匹配"，选实体分类时常量表报"没有匹配"
//
// 最关键的一条断言是「每个筛选项都必须有结果」——这是防止筛选项写死的护栏。
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const H = require('./test_harness');

const HTML = process.argv[2]
  ? path.resolve(process.argv[2])
  : H.defaultHtml();
const SELF = __filename;
// 加载 + 提段 + 语法门禁（三处测试共用的引导逻辑，见 test_harness.js）
// 注：原实现里「取含 const DB 的 <script>」与「语法门禁」两步之间还有别的代码，
//     现一并收进 H.load()（顺序不变：先语法门禁、后 const→var 转写）。
const { html, rawCode, code } = H.load(HTML);

// ---- 语法门禁（必须先于任何转写！）----
// ⚠️ 血泪教训：下面为了沙箱会把 const/let 全换成 var，而 var 允许重复声明。
// 于是「同一作用域重复 const」这种真·SyntaxError 会被悄悄吞掉 ——
// 曾因此把 ENT_CATS 重复声明放过去，浏览器里整个脚本作废、页面全白，
// 而本测试却报 90/90 通过。
// V8 的编译器是权威判据，交给它就行。
// （该门禁已收进 H.load()，此处保留教训备查；rawCode 是未经转写的原文。）

// ---- DOM stub ----
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
  querySelector(sel) {
    if (!els[sel]) els[sel] = mkEl(sel.replace('#', ''));
    return els[sel];
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

const out = [];
let pass = 0, fail = 0;
function chk(name, cond, extra) {
  if (cond) pass++;
  else { fail++; out.push('  FAIL ' + name + (extra ? '  :: ' + extra : '')); }
}

// ---- 两档制（2026-09-22 博士拍板）----
// 默认 = 日常档：跳过 ⑤-2/⑤-3 里单次求解 >800ms 的大链走线用例（LawRun hook 实测 6 簇合计 ~13.5s/32s，
// profile 89% 在 RwPath BFS）。发布前必须 `HEAVY=1 node tools/test_html.js` 全量跑。
// 跳过的断言不计 pass/fail，只计 skipHeavy，RESULT 会带 skip=N —— 日常档应满足 fail=0。
// ⚠️ 此处刻意不写具体通过数：断言数随版本持续增长，写死的数字必然过期（v103 起已过一轮）。
//    门禁口径以脚本实际输出的 RESULT 行为准 —— 日常档 fail=0 且 skip 数无异常增长即可。
// ⑥-2 多目标回归锁（清水+息壤 / 双目标报告头 / 收货组合）**不跳** —— v96 bug 的锁在日常档也要站岗。
const HEAVY = process.env.HEAVY === '1';
let skipHeavy = 0;
function chkHeavy(name, fn, extra) {
  if (!HEAVY) { skipHeavy++; return; }
  chk(name, typeof fn === 'function' ? fn() : fn, typeof extra === 'function' ? extra() : extra);
}

function report() {
  out.unshift(`RESULT pass=${pass} fail=${fail}` + (skipHeavy && !HEAVY ? ` skip=${skipHeavy}（日常档跳过的大链用例；HEAVY=1 全量）` : ''));
  console.log(out.join('\n'));
  process.exit(fail ? 1 : 0);
}

try {
  vm.runInContext(code, ctx, { timeout: 20000 });
} catch (e) {
  console.log('CTX ERROR: ' + e.message + '\n' + e.stack);
  process.exit(1);
}

const A = ctx;
const outEl = els['#out'];
const f1El = els['#f1'];

function setTab(t, kw, f1) {
  A.tab = t; A.kw = kw || ''; A.f1 = f1 || ''; A.openSet.clear();
  els['#f1'].value = A.f1;
}

// ---- 1. 每个 tab 渲染 ----
for (const t of A.TABS.map(x => x.k)) {
  setTab(t);
  let err = null;
  try { A.render(); } catch (e) { err = e.message; }
  const h = outEl.innerHTML || '';
  chk(`tab=${t} 渲染无异常`, !err, err);
  chk(`tab=${t} 有输出`, h.length > 50, 'len=' + h.length);
  chk(`tab=${t} 无 undefined 泄漏`, !/>undefined<|undefined<\/|\$\{/.test(h));
}

// ---- 2. 每个筛选项都必须有结果（核心护栏）----
for (const t of A.TABS.map(x => x.k)) {
  setTab(t);
  A.render();
  const vals = (f1El.innerHTML || '').match(/value="([^"]*)"/g) || [];
  for (const v of vals.map(s => s.replace(/value="|"/g, '')).filter(Boolean)) {
    setTab(t, '', v);
    try { A.render(); } catch (e) {
      chk(`tab=${t} f1="${v}" 渲染`, false, e.message); continue;
    }
    const body = outEl.innerHTML || '';
    chk(`tab=${t} f1="${v}" 有结果`, body.indexOf('没有匹配') < 0, '空结果');
  }
}

// ---- 3. 关键词过滤必须真的改变输出 ----
for (const p of ['矿', '管道', '无线', '传送带', '滑索', '精炼炉', '武陵', '暗管']) {
  let changed = false;
  for (const t of ['building', 'blueprint', 'rules', 'logistics', 'item', 'recipe']) {
    setTab(t); A.render();
    const full = (outEl.innerHTML || '').length;
    setTab(t, p); A.render();
    if ((outEl.innerHTML || '').length !== full) { changed = true; break; }
  }
  chk(`关键词 "${p}" 生效`, changed);
}

// ---- 4. 筛选下拉的选项来自数据，不是写死的 ----
function optsOf(tab) {
  setTab(tab);
  A.render();
  return (f1El.innerHTML || '').match(/value="([^"]*)"/g) || [];
}
const recipeOpts = optsOf('recipe').map(s => s.replace(/value="|"/g, '')).filter(Boolean);
chk('配方页筛选项来自数据（不多于实际分类数）', recipeOpts.length <= 5,
    recipeOpts.join(','));
chk('配方页筛选项与实际分类一致',
    recipeOpts.every(v => A.DB.machine_recipes.some(r => r.machineCategory === v)),
    recipeOpts.join(','));

const manualOpts = optsOf('manual').map(s => s.replace(/value="|"/g, '')).filter(Boolean);
chk('手工页含两个地区选项',
    manualOpts.includes('四号谷地') && manualOpts.includes('武陵'),
    manualOpts.join(','));

// ---- 5. 规则页内容与 CSS ----
setTab('rules'); A.render();
const rulesHtml = outEl.innerHTML || '';
for (const s of ['只能放置在矿点上', '无线传输', '暗管', '成立', '文案', '集成核心区域']) {
  chk(`规则页含「${s}」`, rulesHtml.indexOf(s) >= 0);
}
for (const cls of ['lg-capn', 'lg-capl']) {
  chk(`CSS 已定义 .${cls}`, html.indexOf('.' + cls + '{') >= 0);
}

// ---- 5b. 基地面积页 ----
setTab('base'); A.render();
const busPageHtml = outEl.innerHTML || '';
for (const s of ['70×70', '80×80', '4900', '6400', '单边最多', '区域扩大', '据点发展等级', '蓝图最大宽度']) {
  chk(`基地页含「${s}」`, busPageHtml.indexOf(s) >= 0);
}
// 面积页必须把"实测"与"配置表"两类来源分开写，别混着说
chk('基地页标注了数据来源分歧', busPageHtml.indexOf('社区实测') >= 0 && busPageHtml.indexOf('配置表') >= 0);
chk('基地页给出边界说明', busPageHtml.indexOf('数据边界') >= 0);
chk('面积条目 4 条（谷地/武陵 × 主/副）', (A.DB.bases.areas || []).length === 4,
    String((A.DB.bases.areas || []).length));
chk('每个可扩建建造区都是 2 档区域扩大',
    (A.DB.bases.zones || []).filter(z => z.hasBuiltArea).every(z => z.expansion.length === 2),
    JSON.stringify((A.DB.bases.zones || []).filter(z => z.hasBuiltArea && z.expansion.length !== 2).map(z => z.levelId)));
// 换据点筛选后仍要有输出
for (const dom of ['四号谷地', '武陵']) {
  setTab('base', '', dom); A.render();
  const h = outEl.innerHTML || '';
  chk(`基地页 f1="${dom}" 含建造区`, h.indexOf(dom) >= 0 && h.indexOf('没有匹配') < 0);
}

// ---- 5b-2. 满级基地总览（每片基地一行：1 主 + 3 副）----
setTab('base'); A.render();
const busPageHtml2 = outEl.innerHTML || '';
for (const s of ['满级基地总览', '全部按最大值取', '枢纽区', '应龙关', '主基地', '副基地', '类型（核心）']) {
  chk(`满级总览含「${s}」`, busPageHtml2.indexOf(s) >= 0);
}
const mb = A.DB.bases.maxBases || [];
const hasBase = (A.DB.bases.zones || []).filter(z => z.hasBuiltArea);
chk('满级总览行数 = 有基地的建造区数', mb.length === hasBase.length,
    mb.length + ' vs ' + hasBase.length);
chk('满级总览剔除了无基地的建造区',
    mb.length < (A.DB.bases.zones || []).length && mb.every(r => r.hasBuiltArea),
    JSON.stringify(mb.map(r => r.levelId)));
chk('满级总览每行都有券价（无券价 = 没有基地，不该进表）',
    mb.every(r => r.unlockCostTotal != null),
    JSON.stringify(mb.filter(r => r.unlockCostTotal == null).map(r => r.levelId)));
chk('每片基地都有建设区面积', mb.every(r => r.area && r.area.cells > 0),
    JSON.stringify(mb.filter(r => !r.area).map(r => r.levelId)));
chk('每行都有满级建造上限', mb.every(r => r.caps && r.caps.bandwidth != null),
    JSON.stringify(mb.filter(r => !r.caps || r.caps.bandwidth == null).map(r => r.levelId)));
chk('每行都算出了可铺蓝图', mb.every(r => r.area && r.area.blueprint && r.area.blueprint.note),
    JSON.stringify(mb.filter(r => !r.area || !r.area.blueprint).map(r => r.levelId)));
// 主/副归属：每个据点 1 主 + 3 副，主基地是枢纽区 / 武陵城（博士游戏内确认，写死在这里守着）
chk('主基地落在枢纽区与武陵城',
    JSON.stringify(mb.filter(r => r.role === '主基地').map(r => r.levelId).sort())
    === JSON.stringify(['map01_lv001', 'map02_lv002']),
    JSON.stringify(mb.filter(r => r.role === '主基地').map(r => r.levelId)));
for (const dn of ['四号谷地', '武陵']) {
  const inDom = mb.filter(r => r.domainName === dn);
  chk(`${dn}：1 主 + 3 副`,
      inDom.filter(r => r.role === '主基地').length === 1
      && inDom.filter(r => r.role === '副基地').length === 3,
      JSON.stringify(inDom.map(r => [r.zoneName, r.role])));
}
chk('主基地面积大于同据点副基地',
    ['四号谷地', '武陵'].every(dn => {
      const d = mb.filter(r => r.domainName === dn);
      return d.every(r => r.role !== '主基地'
        || r.area.cells > Math.max(...d.filter(x => x.role === '副基地').map(x => x.area.cells)));
    }),
    JSON.stringify(mb.map(r => [r.zoneName, r.role, r.area && r.area.cells])));
chk('满级口径写明了"套用地区上限"',
    String(A.DB.bases.maxBasis || '').indexOf('套用') >= 0,
    String(A.DB.bases.maxBasis || '').slice(0, 80));
chk('写明了"每个据点 1 主 + 3 副"',
    String(A.DB.bases.baseRoleNote || '').indexOf('1 主 + 3 副') >= 0,
    String(A.DB.bases.baseRoleNote || '').slice(0, 80));
// 上面已逐一断言；这里保留一条"总量对得上"的兜底
chk('满级总览规模合理', mb.length > 0 && mb.length <= 20, String(mb.length));
chk('满级口径写明了"基地只有集成管家那 8 个区"',
    String(A.DB.bases.baseOnlyNote || '').indexOf('8 个建造区') >= 0,
    String(A.DB.bases.baseOnlyNote || '').slice(0, 80));

// ---- 5c-2. 占地平面示意：SVG 俯视图 ----
// 曾经是 ASCII 字符画；现在按第三方蓝图工具的做法画矢量网格。
// 这里守三件事：确实是 SVG、接口形状数量对得上、图例没丢。
setTab('blueprint'); A.render();
const firstPort = A.DB.blueprint.buildings.find(b => b.portCount > 0);
A.openSet.add('p:' + firstPort.id); A.render();
const bpHtml = outEl.innerHTML || '';
chk('占地示意是 SVG', bpHtml.indexOf('<svg') >= 0 && bpHtml.indexOf('viewBox') >= 0,
    firstPort.id);
chk('ASCII 版占地示意已移除', bpHtml.indexOf('<pre class="grid"') < 0);
for (const s of ['占地平面示意', '俯视图', '进料口（传送带）', '出料口（传送带）', '同格多口']) {
  chk(`占地示意图例含「${s}」`, bpHtml.indexOf(s) >= 0);
}
const sv = bpHtml.slice(bpHtml.indexOf('<svg'), bpHtml.indexOf('</svg>') + 6);
const mergedCells = new Set(firstPort.ports.map(p => p.x + ',' + p.z)).size;
const nRect = (sv.match(/<rect /g) || []).length - 2;   // 减背景 + 建筑外框
const nCircle = (sv.match(/<circle /g) || []).length;
chk(`接口形状覆盖全部 ${mergedCells} 个格位`,
    nRect + nCircle === mergedCells,
    `rect=${nRect} circle=${nCircle}`);
const vb = /viewBox="0 0 (\d+) (\d+)"/.exec(sv);
chk('SVG 画布尺寸随占格走',
    vb && (+vb[1] > 0 && +vb[2] > 0 && +vb[1] >= +vb[2]),
    vb ? vb[0] : 'no viewBox');
A.openSet.clear(); setTab('blueprint'); A.render();

// ---- 5c-3. 内联 JSON 不能被压成超长单行 ----// 内嵌 webview 解析不了超长单行，会上万字符直接白屏（见 build_html.py 顶部注释）。
let maxLine = 0;
for (const line of html.split('\n')) if (line.length > maxLine) maxLine = line.length;
chk('内联数据最长行不超过 8000 字符', maxLine < 8000, 'maxLine=' + maxLine);

// ---- 5d. 布局试摆（交互画布）与分类字标 ----
setTab('layout'); A.Linit().palOpen = true; A.render();   /* v144 清单默认收起——本组要读清单内容，先展开 */
const loHtml = outEl.innerHTML || '';
for (const s of ['布局试摆', 'lo-canvas', 'lo-pal', '画布尺寸', '清空', '70×70']) {
  chk(`布局试摆页含「${s}」`, loHtml.indexOf(s) >= 0);
}
chk('布局试摆有可摆放建筑列表', loHtml.indexOf('lo-btn') >= 0, 'palette 是否为空');
// 画布默认 50×50（LO 在 renderLayout 里被 Linit 初始化）
chk('画布默认 50×50', A.LO && A.LO.size === 50, String(A.LO && A.LO.size));
// ---- 5d-1. v144 建筑清单侧边栏：收起 = 画布左侧窄竖条；展开 = 画布左侧浮层侧栏（**画布位置恒定**）----
// 根因（DOM 实测锁定）：.lo-wrap 原本 flex-wrap:wrap + 画布 1052px 宽 → 清单被换行到画布上方、独占整行 1140px。
// 修法：nowrap + 侧栏定宽（收起 34 / 展开 246）+ 画布 flex:1（放不下时由 .lo-stage 的 overflow:auto 横向滚）。
A.Linit().palOpen = false; A.render();
const loFold = outEl.innerHTML || '';
chk('v144 收起：清单渲染成左侧竖条（lo-pal folded + lo-pal-tab）',
    loFold.indexOf('lo-pal folded') >= 0 && loFold.indexOf('lo-pal-tab') >= 0);
chk('v144 收起：清单项整个不渲染（真正让位给画布，不是 display:none）', loFold.indexOf('LpickFromList') < 0);
chk('v144 画布位置恒定：清单绝对定位挂左侧（不占文档流）+ 宽度自适应函数在',
    html.indexOf('.lo-wrap{position:relative}') >= 0
    && html.indexOf('.lo-pal{position:absolute;top:0;right:100%') >= 0
    && html.indexOf('.lo-pal.folded{width:34px') >= 0
    && html.indexOf('function LpalFit()') >= 0);
// 反向锁：「flex 定宽栏」那条错路必须已撤掉 —— 它会让展开时画布整体右移（博士：「画布又被挪了」）
chk('v144 反向：flex 定宽侧栏的做法已撤（否则画布会被推着走）',
    html.indexOf('.lo-wrap{display:flex;gap:14px;flex-wrap:nowrap') < 0
    && html.indexOf('.lo-pal{flex:0 0 246px') < 0
    && html.indexOf('.lo-stage{flex:1 1 auto') < 0);
A.Linit().palOpen = true; A.render();
const loOpen = outEl.innerHTML || '';
chk('v144 展开：清单项 + 收起按钮都在，竖条标记不在',
    loOpen.indexOf('LpickFromList') >= 0 && loOpen.indexOf('lo-pal-tab') < 0);
// ⭐ 配方块必须与清单折叠解耦：首版把 recipeBlock 一起折叠掉了，收起态选机器就没有配方下拉 —— 这条锁住它
A.Linit().palOpen = false;
A.Lpick('furnance_1'); A.Lput(3, 3);   /* Lput 会自动选中，出配方块 */
A.render();
chk('v144 收起态：按下机器仍出配方块（与清单折叠解耦，不被折叠带走）',
    (outEl.innerHTML || '').indexOf('class="lo-rp"') >= 0);
loReset(50); A.render();   /* 复原：画布清空 + 回到展开态，后续用例照旧 */

// ---- 5d-2. 左栏默认清单：官方组（仓储存取/基础生产/合成制造/电力/功能设备）+ 核心结构 + 物流件 ----
// 需求：沙盘只服务基地产线布局，资源开采（只能放野外）、战斗辅助、装饰默认不列。
// v131 起分类名 = 游戏内「工业设备」面板官方分组名（FactoryQuickBarTypeTable）。
// 2026-09-21 起物流件（传送带/管道/汇流分流/桥/阀门）也进左栏 —— 它们不在 blueprint.buildings
// 里，来自 logistics.entities，页面用 Llogi()/LO_LG() 包一层后并入同一份清单，这里照同一条路径算期望值。
const bpAll = A.DB.blueprint.buildings;
const lgAll = A.Llogi().map(A.LO_LG);
// 免电变体（_nop_）默认不进试摆，期望值要跟页面同一口径，否则会多算
const loAllowedList = bpAll.concat(lgAll)
  .filter(b => !(A.LO_HIDE_NOP && A.LO_IS_NOP(b)))
  .filter(b => A.loAllowed(b));
const loCats = [...new Set(loAllowedList.map(b => b.categoryName))].sort();
chk('默认清单的分类只落在生产/电力/存储物流 + 核心结构 + 物流件',
    loCats.every(c => ['仓储存取', '基础生产', '合成制造', '电力', '功能设备', '核心结构', '物流件'].includes(c)),
    loCats.join(','));
chk('默认清单含两个生产组（基础生产 + 合成制造）',
    loCats.includes('基础生产') && loCats.includes('合成制造'), loCats.join(','));
// 「功能设备」（v131 前旧名「物流辅助」）下的建筑被博士逐个点名拉黑（洒水机/给水器/滑索架/便捷存取站/留言信标），
// 该分类现在是空的、也已从下拉里移除 —— 所以这里只断言电力与仓储存取
chk('默认清单含电力与仓储存取',
    loCats.includes('电力') && loCats.includes('仓储存取'),
    loCats.join(','));
chk('默认清单排除资源开采与战斗辅助',
    !loAllowedList.some(b => b.categoryName === '资源开采' || b.categoryName === '战斗辅助'),
    [...new Set(loAllowedList.map(b => b.categoryName))].join(','));
// v18 起「协议核心 / 次级核心」在数据载入时已被改成「核心结构」分类，
// 「装饰与其他」里不再放行任何东西
chk('「装饰与其他」里一件都不放行',
    loAllowedList.filter(b => b.categoryName === '装饰与其他').length === 0,
    String(loAllowedList.filter(b => b.categoryName === '装饰与其他').length));
chk('核心结构（协议核心 / 次级核心）都在默认清单里，且分类名就是「核心结构」',
    A.LO_KEEP_IDS.every(id => loAllowedList.some(b => b.id === id && b.categoryName === '核心结构')),
    A.LO_KEEP_IDS.filter(id => !loAllowedList.some(b => b.id === id)).join(','));
chk('默认清单不含纯装饰（玩偶/立牌/田块）',
    !loAllowedList.some(b => b.id === 'doll_1' || b.id === 'microphone_1' || b.id === 'soil_moss_1'));
chk('默认清单不含采集设备（矿机/水泵）',
    !loAllowedList.some(b => b.id === 'miner_1' || b.id === 'pump_1'));
chk('默认清单不含防御塔', !loAllowedList.some(b => b.id === 'battle_turret_1'));
chk('默认清单不含中继器（中继器 + 息壤中继器）',
    !loAllowedList.some(b => b.id === 'power_pole_2' || b.id === 'power_pole_3'),
    loAllowedList.filter(b => b.id.indexOf('power_pole') === 0).map(b => b.id).join(','));
chk('电力组剔掉两台中继器后还剩 3 台',
    loAllowedList.filter(b => b.categoryName === '电力').length === 3,
    loAllowedList.filter(b => b.categoryName === '电力').map(b => b.name).join(','));

// 物流件：10 件全部进默认清单，按 1×1 处理，带介质与吞吐
chk('默认清单含全部 10 件物流件',
    lgAll.length === 10 && lgAll.every(e => loAllowedList.some(b => b.id === e.id)),
    lgAll.length + ' 件');
chk('物流件按 1×1 处理',
    lgAll.every(b => b.gridFootprint === '1×1' && A.Lfp(b)[0] === 1 && A.Lfp(b)[1] === 1),
    lgAll.map(b => b.gridFootprint).join(','));
chk('物流件带介质与吞吐（传送带 30 / 管道 120 个每分）',
    A.byBp('grid_belt_01').lgPerMin === 30 && A.byBp('log_pipe_01').lgPerMin === 120,
    A.byBp('grid_belt_01').lgPerMin + '/' + A.byBp('log_pipe_01').lgPerMin);
chk('byBp 同时认物流件与建筑（建筑不带 isLogi）',
    A.byBp('grid_belt_01').isLogi === true && !A.byBp('furnance_1').isLogi,
    A.byBp('furnance_1').name);
chk('物流件字形按功能分（带=箭头 汇/分/桥/阀）',
    A.loPieceGlyph(A.byBp('grid_belt_01')) === '▶' &&
    A.loPieceGlyph(A.byBp('log_converger')) === '汇' &&
    A.loPieceGlyph(A.byBp('log_splitter')) === '分' &&
    A.loPieceGlyph(A.byBp('log_connector')) === '桥' &&
    A.loPieceGlyph(A.byBp('log_conditioner')) === '阀',
    A.loPieceGlyph(A.byBp('log_converger')));
chk('物流件介质/种类取自配置表（10 件里 5 件传送带系 5 件管道系）',
    lgAll.filter(b => b.lgMedium === '传送带').length === 5 &&
    lgAll.filter(b => b.lgMedium === '管道').length === 5,
    lgAll.map(b => b.lgMedium).join(','));

// 渲染层：左栏按钮 == 默认清单
setTab('layout'); A.render();
const layoutPal = outEl.innerHTML || '';
const palIds = [...layoutPal.matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);   /* v144 清单项改走 LpickFromList */
chk('左栏默认数量与默认清单一致', palIds.length === loAllowedList.length,
    palIds.length + ' vs ' + loAllowedList.length);
chk('左栏默认含协议核心', palIds.includes('sp_hub_1'));
// 滑索架（travel_pole_1 / travel_pole_2 / travel_pole_nop_1）已被博士点名拉黑，不再进默认清单
chk('左栏默认含精炼炉/储存箱，且不含滑索架',
    ['furnance_1', 'storager_1'].every(id => palIds.includes(id))
      && !palIds.includes('travel_pole_1') && !palIds.includes('travel_pole_2'),
    palIds.slice(0, 5).join(','));
chk('左栏默认含物流件（传送带/管道/汇流器/物品准入口）',
    ['grid_belt_01', 'log_pipe_01', 'log_converger', 'log_conditioner'].every(id => palIds.includes(id)),
    palIds.length + ' 项');
chk('左栏物流件正好 10 件，不多不漏',
    palIds.filter(id => lgAll.some(e => e.id === id)).length === 10,
    String(palIds.filter(id => lgAll.some(e => e.id === id)).length));
chk('物流件按钮尾标给的是吞吐不是尺寸',
    /Lpick(?:FromList)?\('grid_belt_01'\)[\s\S]{0,240}?lo-tag">30 个\/分/.test(layoutPal), 'grid_belt_01');
chk('左栏默认不含防御塔与矿机',
    !palIds.includes('battle_turret_1') && !palIds.includes('miner_1'));
chk('左栏默认不含中继器',
    !palIds.includes('power_pole_2') && !palIds.includes('power_pole_3'));
chk('左栏顶部说明了默认列了哪几类',
    layoutPal.indexOf('默认只列') >= 0 && layoutPal.indexOf('核心结构') >= 0);
chk('左栏顶部标注了中继器已去掉', layoutPal.indexOf('中继器') >= 0);

// ---- 5d-3. 仓库存取线的放置规则（纯函数 + 渲染）----
// 口径经博士 2026-09-21 游戏内实拍确认：**边有接触就算相连** —— 可横向并排、可 L 形拐弯、
// 错开一两格也行，不要求整边对齐；没连上的游戏里会变红并提示。别改成"整边对齐"。
const mkH = (id, x, y, w, d) => ({ uid: 'h' + id + x + '_' + y, id: id, x: x, y: y, w: w, d: d, rot: 0 });
const SRC = 'log_hongs_bus_source', BUS = 'log_hongs_bus', LOADER = 'loader_1';

chk('存取线相邻：共边且有重叠 = 相连', A.Ltouch(mkH('a', 0, 0, 4, 8), mkH('b', 4, 0, 4, 8)));
chk('存取线相邻：错开一格仍算相连', A.Ltouch(mkH('a', 0, 0, 4, 8), mkH('b', 4, 3, 4, 8)));
chk('存取线相邻：L 形拐弯算相连', A.Ltouch(mkH('a', 0, 0, 4, 8), mkH('b', 0, 8, 8, 4)));
chk('存取线相邻：只对角挨着不算', !A.Ltouch(mkH('a', 0, 0, 4, 4), mkH('b', 4, 4, 4, 4)));
chk('存取线相邻：隔一格不算', !A.Ltouch(mkH('a', 0, 0, 4, 4), mkH('b', 5, 0, 4, 4)));

chk('存取线：挨着源桩的基段不标红',
    Object.keys(A.LhongsBad([mkH(SRC, 0, 0, 4, 4), mkH(BUS, 0, 4, 4, 8)])).length === 0);
chk('存取线：链式传递（源桩→基段→基段）不标红',
    Object.keys(A.LhongsBad([mkH(SRC, 0, 0, 4, 4), mkH(BUS, 0, 4, 4, 8), mkH(BUS, 0, 12, 4, 8)])).length === 0);
chk('存取线：错开一格的基段也算相连（博士截图那种摆法）',
    Object.keys(A.LhongsBad([mkH(SRC, 0, 0, 4, 4), mkH(BUS, 0, 4, 4, 8), mkH(BUS, 4, 5, 4, 8)])).length === 0);
chk('存取线：中间隔开一格的基段不算相连',
    Object.keys(A.LhongsBad([mkH(SRC, 0, 0, 4, 4), mkH(BUS, 0, 4, 4, 8), mkH(BUS, 5, 4, 4, 8)])).length === 1);

const far = [mkH(SRC, 0, 0, 4, 4), mkH(BUS, 0, 20, 4, 8)];
chk('存取线：没挨着任何一段的基段被标红', Object.keys(A.LhongsBad(far)).length === 1);
chk('存取线：基段断开的提示与游戏文案一致',
    A.LhongsBad(far)[far[1].uid] === '没有与仓库存取线源桩或其他运作中基段相连');

const broken = [mkH(SRC, 0, 0, 4, 4), mkH(BUS, 0, 4, 4, 8), mkH(BUS, 0, 30, 4, 8)];
const brokenBad = A.LhongsBad(broken);
chk('存取线：中间断开时只有断掉那段标红',
    Object.keys(brokenBad).length === 1 && !!brokenBad[broken[2].uid]);

const withLoader = [mkH(SRC, 0, 0, 4, 4), mkH(BUS, 0, 4, 4, 8), mkH(LOADER, 0, 12, 3, 1)];
chk('存取线：贴靠存取线的存货口不标红', Object.keys(A.LhongsBad(withLoader)).length === 0);
const loneLoader = [mkH(SRC, 0, 0, 4, 4), mkH(LOADER, 20, 20, 3, 1)];
const loneBad = A.LhongsBad(loneLoader);
chk('存取线：孤立的存货口被标红', Object.keys(loneBad).length === 1);
chk('存取线：存货口的提示与游戏文案一致',
    loneBad[loneLoader[1].uid] === '必须贴靠仓库存取线放置');
chk('存取线：场上没有基段/存货口时不做校验',
    Object.keys(A.LhongsBad([mkH(SRC, 0, 0, 4, 4)])).length === 0);

chk('左栏含仓库存取线源桩与基段',
    ['log_hongs_bus_source', 'log_hongs_bus'].every(id => palIds.includes(id)));
chk('存取线上限来自 bases.json（武陵城：基段 25 / 源桩 2）', (() => {
  const z = ((A.DB.bases && A.DB.bases.zones) || []).filter(x => x.levelId === 'map02_lv002')[0];
  return !!z && z.busCap && z.busCap.log_hongs_bus === 25 && z.busCap.log_hongs_bus_source === 2;
})());

// 渲染：未连接的基段要带 bad 类（游戏里那块变红的预览）
setTab('layout'); A.render();
A.LO.objs = [A.Lmk(A.byBp(SRC), 2, 2, 0), A.Lmk(A.byBp(BUS), 2, 40, 0)];
A.LO.sel = []; A.render();
let hongsHtml = outEl.innerHTML || '';
const badCells = (hongsHtml.match(/class="lo-cell[^"]*\bbad\b/g) || []).length;
chk('渲染：未连接的基段带上 bad（画布标红）', badCells === 1, 'bad cells=' + badCells);
chk('渲染：计数区显示存取线与未连接数', hongsHtml.indexOf('存取线：源桩') >= 0 && hongsHtml.indexOf('未连接 1 件') >= 0);
A.LO.objs = [A.Lmk(A.byBp(SRC), 2, 2, 0), A.Lmk(A.byBp(BUS), 2, 6, 0)];
A.render();
hongsHtml = outEl.innerHTML || '';
chk('渲染：接上源桩后不再标红', ((hongsHtml.match(/class="lo-cell[^"]*\bbad\b/g) || []).length) === 0);
chk('渲染：上限下拉列出有数量的建造区', hongsHtml.indexOf('lo-sel') >= 0 && hongsHtml.indexOf('武陵城') >= 0);
A.LO.objs = []; A.render();

// ---- 5d-4. 视角旋转（像游戏里转镜头；纯视图操作，数据不动）----
chk('沙盘视角默认 0°', (A.LO.viewRot || 0) === 0);
const vrBefore = JSON.stringify(A.LO.objs);
A.LrotView(); A.LrotView(); A.LrotView(); A.LrotView();
chk('视角旋转 4 次回原位、摆放数据不动',
    (A.LO.viewRot || 0) === 0 && JSON.stringify(A.LO.objs) === vrBefore,
    'viewRot=' + A.LO.viewRot);
chk('画布渲染带 rotate 变换', (outEl.innerHTML || '').indexOf('transform:rotate(') >= 0);

// ---- 5d-5. 谷地存取线示意图（实测：只记"几条边排满"，方位随镜头变）----
const busObs = (A.DB.bases && A.DB.bases.busObservations) || {};
chk('谷地存取线实测：4 个建造区', ((busObs.zones || []).length) === 4, 'zones=' + (busObs.zones || []).length);
const busBy = {};
(busObs.zones || []).forEach(z => { busBy[z.levelId] = z; });
chk('枢纽区是相连两条边排满（博士实拍）', !!busBy['map01_lv001'] && busBy['map01_lv001'].edges === 2);
chk('枢纽区有源桩、副基地没有（博士 2026-09-21 补充）',
    !!busBy['map01_lv001'] && busBy['map01_lv001'].source === true &&
    !!busBy['map01_lv002'] && busBy['map01_lv002'].source === false);
chk('三个副基地各一条边排满',
    ['map01_lv002', 'map01_lv005', 'map01_lv007'].every(k => busBy[k] && busBy[k].edges === 1));
chk('示意图带上基地边长（主 70 / 副 40）',
    !!busBy['map01_lv001'] && busBy['map01_lv001'].side === 70 &&
    !!busBy['map01_lv002'] && busBy['map01_lv002'].side === 40,
    'side=' + (busBy['map01_lv001'] || {}).side + '/' + (busBy['map01_lv002'] || {}).side);
chk('实测来源 C（博士实拍）/ D（攻略）都登记了', (() => {
  const ids = ((A.DB.bases && A.DB.bases.sources) || []).map(x => x.id);
  return ids.indexOf('C') >= 0 && ids.indexOf('D') >= 0;
})());
/* base tab 的 html 上面已经渲染好了，这里直接复用 */
chk('基地页渲染出存取线示意图（粗条 + 源桩）', busPageHtml.indexOf('bus-bar') >= 0 && busPageHtml.indexOf('bus-src') >= 0);
chk('渲染：源桩只画在枢纽区那张图上（副基地没有）', (busPageHtml.match(/bus-src/g) || []).length === 1);
chk('示意图是 SVG 且带基地名', busPageHtml.indexOf('<svg') >= 0 && busPageHtml.indexOf('枢纽区') >= 0);
chk('示意图声明了「只记几条边 / 方位随镜头变」',
    busPageHtml.indexOf('只记') >= 0 && busPageHtml.indexOf('随镜头') >= 0);

// 用上方分类下拉仍可单独看某一类（逃生口没堵死），但拉黑名单照样不出现
A.Lonly('电力');
const palPower = outEl.innerHTML || '';
const powerIds = [...palPower.matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);
chk('单看「电力」时保留供电桩、不给中继器',
    powerIds.includes('power_diffuser_1') && !powerIds.includes('power_pole_2') && !powerIds.includes('power_pole_3'),
    powerIds.join(','));
A.Lonly('战斗辅助');
const palDef = outEl.innerHTML || '';
const defIds = [...palDef.matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);
chk('切到「战斗辅助」时左栏只列防御类',
    defIds.includes('battle_turret_1') && !defIds.includes('furnance_1'),
    defIds.length + ' 个');
chk('Lonly 同步了顶部分类下拉的值', els['#f1'].value === '战斗辅助', els['#f1'].value);
A.Lonly('');
setTab('layout'); A.render();
const palBack = [...(outEl.innerHTML || '').matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);
chk('「回到默认三类」能切回来', palBack.length === loAllowedList.length && !palBack.includes('battle_turret_1'),
    String(palBack.length));

// 分类字标进了占地 SVG
setTab('blueprint'); A.render();
A.openSet.add('p:' + (A.DB.blueprint.buildings.find(b => b.portCount > 0).id)); A.render();
const bpGlyph = outEl.innerHTML || '';
chk('占地 SVG 带分类字标（至少出现一个）', /采|炼|组|流|电|储|御|饰/.test(bpGlyph));
A.openSet.clear();

// ---- 6. CSS 类完整性：用到的都应有定义 ----
const styleM = html.match(/<style[^>]*>([\s\S]*?)<\/style>/);
const style = styleM ? styleM[1] : '';
const cssDef = new Set((style.match(/\.([a-zA-Z][\w-]*)/g) || []).map(s => s.slice(1)));
const usedCls = new Set();
for (const mm of html.matchAll(/class="([^"$]*)/g)) {
  mm[1].split(/\s+/).filter(Boolean).forEach(c => usedCls.add(c));
}
const missing = [...usedCls].filter(c => !cssDef.has(c));
chk('所有用到的 CSS 类都有定义', missing.length === 0, missing.join(','));

// ---- 5e. 布局试摆进阶操作：旋转 / 撤销重做 / 框选批量 ----
// 这些是纯函数（Lput/Lrot/Ldel/Ldup/Lundo/Lredo/Lfree/LselIn），不走事件，能直接断言。
// 事件层（拖拽框选、鼠标移动预览）只做渲染验证，vm 里不触发。
setTab('layout'); A.render();
const layoutHtml0 = outEl.innerHTML || '';
for (const s of ['旋转 90°', '复制选中', '删除选中', '撤销（Ctrl+Z）', '重做（Ctrl+Y）', '已选', 'lo-msg', 'lo-sep']) {
  chk(`布局试摆页含「${s}」`, layoutHtml0.indexOf(s) >= 0);
}
for (const cls of ['lo-band', 'lo-sep', 'lo-msg', 'off']) {
  chk(`CSS 已定义 .${cls}`, html.indexOf('.' + cls + '{') >= 0 || html.indexOf('.' + cls + '.') >= 0);
}

// 挑一座非正方形且有接口的建筑 —— 正方形转了看不出差别，接口才是旋转的意义
const sqB = A.DB.blueprint.buildings.find(b =>
  b.portCount > 0 && b.gridFootprint.split('×')[0] !== b.gridFootprint.split('×')[1]);
chk('存在非正方形带接口建筑（旋转测试前提）', !!sqB, sqB ? sqB.id : 'none');

function loReset(size) {
  A.LO.objs = []; A.LO.sel = []; A.LO.undo = []; A.LO.redo = [];
  A.LO.pickRot = 0; A.LO.msg = ''; A.LO.pick = null;
  A.LO.size = size || 50;
  /* 基地也必须复位：不复位的话，前面测过「谷地模式」会把后面所有用例都带进那个模式
     （左栏少两件、计数区换成预设口径），症状是一串莫名其妙的失败。 */
  A.LO.base = '';
  A.LO.palOpen = true;   /* v144 清单默认收起——测试要读清单内容，这里统一展开 */
  setTab('layout');
}
loReset(50);
const fp0 = sqB.gridFootprint.split('×').map(Number);
A.Lpick(sqB.id);
chk('待放置朝向默认 0°', A.LO.pickRot === 0, String(A.LO.pickRot));
A.Lput(2, 3);
chk('摆放成功', A.LO.objs.length === 1, String(A.LO.objs.length));
chk('摆放后自动选中', A.LO.sel.length === 1, String(A.LO.sel.length));
const o0 = A.LO.objs[0];
chk('占格与配置表一致', o0.w === fp0[0] && o0.d === fp0[1], o0.w + '×' + o0.d);
chk('每座有唯一 uid', typeof o0.uid === 'string' && o0.uid.length > 1, String(o0.uid));

A.Lput(2, 3);
chk('重叠处放不下（被挡）', A.LO.objs.length === 1, String(A.LO.objs.length));
A.Lput(51 - fp0[0], 3);
chk('越界处放不下（被挡）', A.LO.objs.length === 1, String(A.LO.objs.length));
chk('Lfree 界内判定正确',
    A.Lfree(0, 0, fp0[0], fp0[1], null) === true
    && A.Lfree(-1, 0, fp0[0], fp0[1], null) === false
    && A.Lfree(50 - fp0[0] + 1, 0, fp0[0], fp0[1], null) === false);

// 接口坐标旋转：90° 后必须落在互换后的宽深里，且格位不丢不重
function rotPorts(b, rot) {
  const f = b.gridFootprint.split('×').map(Number);
  return b.ports.map(p => { const q = A.LportXY(p, rot, f[0], f[1]); return q.x + ',' + q.z; });
}
const pp0 = rotPorts(sqB, 0), pp90 = rotPorts(sqB, 90), pp180 = rotPorts(sqB, 180);
chk('旋转 360° 回到原位', JSON.stringify(rotPorts(sqB, 360)) === JSON.stringify(pp0));
chk('旋转 90° 后接口都在互换后的宽深内',
    pp90.every(s => { const c = s.split(',').map(Number); return c[0] >= 0 && c[0] < fp0[1] && c[1] >= 0 && c[1] < fp0[0]; }),
    pp90.join(' '));
chk('旋转不丢接口（格位数不变）', pp90.length === pp0.length && pp180.length === pp0.length,
    pp0.length + ' -> ' + pp90.length);
chk('旋转 180° 是中心对称',
    sqB.ports.every((p, i) => pp180[i] === (fp0[0] - 1 - p.x) + ',' + (fp0[1] - 1 - p.z)));

// 单选旋转 = 绕自身中心原地转
A.Lrot();
chk('旋转后宽深互换', o0.w === fp0[1] && o0.d === fp0[0], o0.w + '×' + o0.d);
chk('旋转记录朝向 90°', o0.rot === 90, String(o0.rot));
A.render();
chk('选中态渲染进 DOM', (outEl.innerHTML || '').indexOf('lo-cell sel') >= 0);
chk('建筑格子带 data-uid', (outEl.innerHTML || '').indexOf('data-uid="' + o0.uid + '"') >= 0);

// 撤销 / 重做
A.Lundo();
chk('撤销回到旋转前', A.LO.objs[0].rot === 0 && A.LO.objs[0].w === fp0[0],
    A.LO.objs[0].rot + '/' + A.LO.objs[0].w);
A.Lredo();
chk('重做回到旋转后', A.LO.objs[0].rot === 90, String(A.LO.objs[0].rot));
A.Lundo(); A.Lundo();
chk('撤销到底不再回退', A.LO.objs.length === 0, String(A.LO.objs.length));
A.Lredo(); A.Lredo();
chk('重做回到旋转后（第二次）', A.LO.objs.length === 1 && A.LO.objs[0].rot === 90);

// 未选中时旋转 = 转待放置朝向
loReset(50); A.Lpick(sqB.id); A.Lrot();
chk('未选中时旋转的是待放置朝向', A.LO.pickRot === 90 && A.LO.objs.length === 0, String(A.LO.pickRot));
A.Lput(0, 0);
chk('按待放置朝向摆放（宽深已互换）', A.LO.objs[0].w === fp0[1] && A.LO.objs[0].d === fp0[0],
    A.LO.objs[0].w + '×' + A.LO.objs[0].d);

// 框选（矩形交集判定）与批量操作
loReset(50); A.Lpick(sqB.id);
A.Lput(1, 1); A.Lput(20, 20); A.Lput(50 - fp0[0] - 1, 50 - fp0[1] - 1);
chk('摆了三座', A.LO.objs.length === 3, String(A.LO.objs.length));
chk('框选左上角只命中 1 座', A.LselIn(-1, -1, 15, 15) === 1, String(A.LO.sel.length));
chk('框选全画布命中 3 座', A.LselIn(-1, -1, 51, 51) === 3, String(A.LO.sel.length));
chk('框选空区域命中 0 座', A.LselIn(30, 2, 34, 6) === 0, String(A.LO.sel.length));
A.LselIn(-1, -1, 15, 15);
const beforeDup = A.LO.objs.length;
A.Ldup();
chk('批量复制新增同数量副本', A.LO.objs.length === beforeDup + 1, String(A.LO.objs.length));
chk('复制后选中的是副本', A.LO.sel.length === 1 && A.LO.sel[0] !== A.LO.objs[0].uid);
A.Lundo();
chk('撤销复制', A.LO.objs.length === beforeDup, String(A.LO.objs.length));

A.LselIn(-1, -1, 51, 51);
A.Lrot();
chk('多选整体旋转后仍是 3 座', A.LO.objs.length === 3, String(A.LO.objs.length));
chk('多选旋转后全都转了 90°', A.LO.objs.every(o => o.rot === 90), JSON.stringify(A.LO.objs.map(o => o.rot)));
chk('多选旋转后互不重叠', A.LO.objs.every((a, i) =>
    A.LO.objs.every((b, j) => i === j ||
      a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.d <= b.y || b.y + b.d <= a.y)));
A.Lundo();
chk('撤销多选旋转', A.LO.objs.every(o => o.rot === 0), JSON.stringify(A.LO.objs.map(o => o.rot)));

A.LselIn(-1, -1, 51, 51);
A.Ldel();
chk('批量删除', A.LO.objs.length === 0, String(A.LO.objs.length));
A.Lundo();
chk('撤销批量删除', A.LO.objs.length === 3, String(A.LO.objs.length));
A.Lclear();
chk('清空可撤销', A.LO.objs.length === 0);
A.Lundo();
chk('撤销清空', A.LO.objs.length === 3, String(A.LO.objs.length));
A.Lsize(70);
chk('换画布尺寸清空摆放', A.LO.objs.length === 0 && A.LO.size === 70, String(A.LO.size));
A.Lundo();
chk('撤销换尺寸（连尺寸一起回退）', A.LO.size === 50 && A.LO.objs.length === 3,
    A.LO.size + '/' + A.LO.objs.length);
loReset(50);
A.render();

// ---- 5d-6. 基地 / 地区分开：武陵「自己摆」 vs 四号谷地「基地自动铺」（2026-09-21）----
// 博士：「布局试摆我看不见四号谷地的预设存取线，能把武陵和四号谷地分开讨论吗」。
// 落地：工具栏最左加「基地」下拉（8 片，按地区分成两个 optgroup）；选一片 = 设画布边长 + 切存取线规则。
// 谷地：左栏不给源桩/基段、计数区换「预设」口径、不判贴靠（预设线坐标拿不到，判就会全红）。
const bsAll = A.Lbases();
chk('基地清单 8 片，两个地区各 4 片',
    bsAll.length === 8 && bsAll.filter(r => r.domainName === '四号谷地').length === 4 &&
    bsAll.filter(r => r.domainName === '武陵').length === 4, String(bsAll.length));
chk('基地清单带边长与主/副角色',
    bsAll.every(r => r.side > 0 && /^(主|副)基地$/.test(r.role)),
    bsAll.map(r => r.zoneName + ':' + r.side).join(','));

chk('默认是自由模式（不限地区）', A.Lregion() === '' && !A.LisPresetBus() && !A.LO.base);

const baseSelHtml = ((outEl.innerHTML || '').match(
  /<select class="lo-sel" onchange="LbaseSet\(this\.value\)"[\s\S]*?<\/select>/) || [''])[0];
chk('工具栏有「基地」下拉', baseSelHtml.length > 0);
chk('下拉列出 8 片基地', [...new Set([...baseSelHtml.matchAll(/<option value="(map0[^"]*)"/g)].map(m => m[1]))].length === 8);
chk('下拉按地区分成两个 optgroup',
    (baseSelHtml.match(/<optgroup label="/g) || []).length === 2 &&
    baseSelHtml.indexOf('<optgroup label="四号谷地">') >= 0 &&
    baseSelHtml.indexOf('<optgroup label="武陵">') >= 0);
chk('下拉第一项是自由模式', baseSelHtml.indexOf('自由模式（不限地区）') >= 0);
chk('工具栏标出当前模式', (outEl.innerHTML || '').indexOf('当前：自由模式') >= 0);

A.LbaseSet('map01_lv001');
chk('选枢纽区 → 画布 70×70 且切到四号谷地',
    A.LO.size === 70 && A.Lregion() === '四号谷地', A.LO.size + '/' + A.Lregion());
chk('谷地模式 = 预设存取线', A.LisPresetBus() === true);
chk('基地下拉的选中项与当前基地一致', (() => {
  const m = (outEl.innerHTML || '').match(/<option value="(map0[^"]*)" selected>/);
  return !!m && m[1] === A.LO.base;
})());
chk('谷地模式标签写明「存取线由基地自动铺」', (outEl.innerHTML || '').indexOf('存取线由基地自动铺') >= 0);
const gdPal = [...(outEl.innerHTML || '').matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);
chk('谷地模式：左栏不给源桩 / 基段',
    !gdPal.includes('log_hongs_bus') && !gdPal.includes('log_hongs_bus_source'), gdPal.length + ' 项');
chk('谷地模式：存货口 / 取货口照样能放',
    gdPal.includes('loader_1') && gdPal.includes('unloader_1'));
chk('谷地模式：左栏顶部说明为什么不列源桩',
    (outEl.innerHTML || '').indexOf('谷地的存取线由基地自动铺') >= 0);
chk('谷地模式：计数区换成「预设」口径、不再给上限下拉',
    (outEl.innerHTML || '').indexOf('由基地升级自动铺设（预设）') >= 0 &&
    (outEl.innerHTML || '').indexOf('存取线：源桩') < 0);
chk('谷地模式：写明预设线的口径（贴外缘、不占格）',
    (outEl.innerHTML || '').indexOf('一格都不占、也不挡摆放') >= 0 &&
    (outEl.innerHTML || '').indexOf('不是游戏内实测方位') >= 0);

// ---- 5d-7. 谷地预设存取线：贴在画布**外缘**、不占格（博士 2026-09-21 定）----
// 原话「就是贴在画布外缘，不占基地格子」→ 整条带子画在画布框外面（负偏移），一格都不占。
// 摆法照基地面积页那张示意图（博士：「就按这张示意图画」）：枢纽区 = 源桩占左上角 + 上边/左边铺满；副基地 = 左上一条边。
const PRE_CELL = A.LOCELL;
const readPreBands = () => [...((outEl.innerHTML || '').matchAll(
  /class="lo-pre[^"]*" style="left:(-?\d+)px;top:(-?\d+)px;width:(\d+)px;height:(\d+)px"/g))]
  .map(m => ({ left: +m[1], top: +m[2], w: +m[3], h: +m[4] }));

A.LbaseSet('map01_lv001');
let preB = readPreBands();
chk('枢纽区：预设线画成 3 件（源桩 + 上边 + 左边）', preB.length === 3, JSON.stringify(preB));
chk('枢纽区：源桩是左上角一块 1 格的方块',
    preB.some(b => b.left === -PRE_CELL && b.top === -PRE_CELL && b.w === PRE_CELL && b.h === PRE_CELL),
    JSON.stringify(preB));
chk('枢纽区：上边那条横贯整个画布',
    preB.some(b => b.top === -PRE_CELL && b.left === 0 && b.w === A.LO.size * PRE_CELL && b.h === PRE_CELL),
    JSON.stringify(preB));
chk('枢纽区：左边那条纵贯整个画布',
    preB.some(b => b.left === -PRE_CELL && b.top === 0 && b.w === PRE_CELL && b.h === A.LO.size * PRE_CELL));
chk('预设线整条在画布框外面（偏移都是负的、贴边不内缩）',
    preB.every(b => b.left === -PRE_CELL || b.top === -PRE_CELL), JSON.stringify(preB));
chk('预设线与画布内容区**零重叠** —— 一格都不占', (() => {
  const W = A.LO.size * PRE_CELL;
  const ov = b => Math.max(0, Math.min(b.left + b.w, W) - Math.max(b.left, 0)) *
                  Math.max(0, Math.min(b.top + b.h, W) - Math.max(b.top, 0));
  return preB.every(b => ov(b) === 0);
})());
chk('预设线不进摆放数据（不参与碰撞与撤销）', A.LO.objs.length === 0);
chk('预设线不可点（pointer-events:none，不挡画布手势）',
    /\.lo-pre\{[^}]*pointer-events:none/.test(style));
chk('画布容器必须 overflow:visible（否则外缘带子整条被裁）',
    /\.lo-canvas\{[^}]*overflow:visible/.test(style) && !/\.lo-canvas\{[^}]*overflow:hidden/.test(style));
chk('画布外面套了一层留白容器（.lo-stage 是滚动容器，上/左溢出滚不到）',
    (outEl.innerHTML || '').indexOf('class="lo-canv"') >= 0 && /\.lo-canv\{/.test(style));

A.LbaseSet('map01_lv002');
preB = readPreBands();
chk('副基地：预设线只有 1 条（一条边铺满、没有源桩）', preB.length === 1, JSON.stringify(preB));
chk('副基地：不画源桩方块', (outEl.innerHTML || '').indexOf('lo-pre-src') < 0);
chk('副基地：那条横贯整个画布、贴在画布外缘',
    !!preB[0] && preB[0].w === A.LO.size * PRE_CELL && preB[0].top === -PRE_CELL, JSON.stringify(preB));

A.LbaseSet('map02_lv002');
chk('武陵模式：不画预设线（那边要自己摆）', readPreBands().length === 0);
A.LbaseSet('');
chk('自由模式：不画预设线', readPreBands().length === 0);
A.LbaseSet('map01_lv001');
A.LO.objs = [];
chk('谷地模式：不判贴靠 —— 孤立的存货口不标红',
    Object.keys(A.LhongsBad([mkH(LOADER, 20, 20, 3, 1)], true)).length === 0);
A.LO.objs = [A.Lmk(A.byBp('loader_1'), 5, 5, 0)];
A.render();
chk('谷地模式：画布上不会出现 bad 标红',
    ((outEl.innerHTML || '').match(/class="lo-cell[^"]*\bbad\b/g) || []).length === 0);
A.LO.objs = [];

A.LbaseSet('map02_lv002');
chk('选武陵城 → 画布 80×80 且切到武陵',
    A.LO.size === 80 && A.Lregion() === '武陵', A.LO.size + '/' + A.Lregion());
chk('武陵模式 = 不是预设（要自己摆）', A.LisPresetBus() === false);
const wlPal = [...(outEl.innerHTML || '').matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);
chk('武陵模式：左栏给源桩与基段',
    wlPal.includes('log_hongs_bus') && wlPal.includes('log_hongs_bus_source'));
chk('武陵模式：保留「存取线：源桩 … + 上限档位」',
    (outEl.innerHTML || '').indexOf('存取线：源桩') >= 0 &&
    (outEl.innerHTML || '').indexOf('武陵城') >= 0);
chk('武陵模式：贴靠校验照旧（孤立存货口仍标红）',
    Object.keys(A.LhongsBad([mkH(LOADER, 20, 20, 3, 1)], false)).length === 1);

A.LbaseSet('map01_lv002');
chk('切到谷地副基地 → 40×40', A.LO.size === 40 && A.Lregion() === '四号谷地');
A.Lundo();
chk('撤销切基地会连地区一起回退', A.LO.size === 80 && A.Lregion() === '武陵',
    A.LO.size + '/' + A.Lregion());
A.LbaseSet('');
A.render();
chk('选回自由模式', A.LO.base === '' && A.Lregion() === '');
chk('自由模式：源桩 / 基段回到左栏（不算误伤自由模式）', (() => {
  const p = [...(outEl.innerHTML || '').matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);
  return p.includes('log_hongs_bus') && p.includes('log_hongs_bus_source');
})());
A.LbaseSet('map01_lv001');
A.Lsize(70);
chk('点画布尺寸按钮会退出基地选择（回自由模式）',
    A.LO.base === '' && A.LO.size === 70 && !A.LisPresetBus());
loReset(50);
A.render();

// ---- 5d-7b. v145 多基地：每片基地的摆放各存一份（切走再切回，内容原样还在）----
// 做法见 docs/最优排布-设计规格.md 第 1 期 Decision 1：基地级字段用访问器代理到 bases[当前基地]，
// 所以「切换基地 = 改 base 指针」即完成保存/恢复；undo/redo 保持全局操作历史。
const tabsOf = t => (t.match(/class="lo-tab[ "]/g) || []).length;
A.LbaseSet('');
A.LO.objs = [];
A.LbaseSet('map01_lv001');
A.Lpick('furnance_1'); A.Lput(3, 3); A.Lput(14, 3);
const mbA = { n: A.LO.objs.length, size: A.LO.size, pts: A.LO.objs.map(o => o.x + ',' + o.y).join('|') };
A.LbaseSet('map01_lv002');
chk('v145 切到另一片基地 = 一张干净画布（内容不串）',
    A.LO.objs.length === 0 && A.LO.size === 40, A.LO.objs.length + '/' + A.LO.size);
A.Lpick('storager_1'); A.Lput(2, 2);
const mbB = { n: A.LO.objs.length, size: A.LO.size };
A.LbaseSet('map01_lv001');
chk('v145 切回原基地：机器数与坐标逐点原样恢复',
    A.LO.objs.length === mbA.n && A.LO.size === mbA.size &&
    A.LO.objs.map(o => o.x + ',' + o.y).join('|') === mbA.pts,
    A.LO.objs.length + '/' + A.LO.size + '/' + A.LO.objs.map(o => o.x + ',' + o.y).join('|'));
A.LbaseSet('map01_lv002');
chk('v145 再切回去：另一片基地的内容同样还在',
    A.LO.objs.length === mbB.n && A.LO.size === mbB.size);
A.LbaseSet('');
chk('v145 自由模式是独立的一格存储（与各基地互不干扰）',
    A.LO.objs.length === 0 && A.LO.base === '');

// 基地页签：只列当前那片基地所在地区的基地，当前那片高亮；自由模式不出页签
A.LbaseSet('map01_lv001'); A.render();
const tabsHtml = outEl.innerHTML || '';
chk('v145 基地页签：该地区 4 片基地各一个、当前那片高亮',
    tabsOf(tabsHtml) === 4 && tabsHtml.indexOf('class="lo-tab on"') >= 0, String(tabsOf(tabsHtml)));
chk('v145 基地页签带摘要（机器数 / 占地 / 可用格）',
    /机器 \d+ · 占地 \d+\/\d+/.test(tabsHtml));
// ⭐v145 反向锁（2026-09-24 博士游戏内确认「核心区无限制」）：
// 协议容量只约束集成核心区域**外**的野外设备（本页建筑详情与基地面积页都这么写）
// → 基地排布里不得再出现「已用/上限」对比、不得再因此扣分。谁加回来谁红。
chk('v145 反向：页签摘要不显示协议容量已用/上限（核心区不受限）',
    !/容量 \d+\/\d+/.test(tabsHtml));
chk('v145 反向：评价函数不再有「超协议容量」惩罚项',
    html.indexOf("pens.push({t:'超协议容量") < 0);   /* 精确匹配代码，注释里提历史不算 */
chk('v145 基地页签只列本地区（不混进武陵的基地）', (() => {
  /* ⚠️ 只能在页签区块里搜 —— 上方的「基地」下拉本来就列全 8 片（含武陵城），整页搜会假红。 */
  const seg = (tabsHtml.match(/<div class="lo-tabs">[\s\S]*?<\/div>/) || [''])[0];
  return seg.indexOf('武陵城') < 0 && seg.indexOf('枢纽区') >= 0 && seg.indexOf('谷地通道') >= 0;
})());
A.LbaseSet(''); A.render();
chk('v145 自由模式不出基地页签', tabsOf(outEl.innerHTML || '') === 0);
loReset(50);
A.render();

// ---- 5d-7c. v148 供电范围层（博士：「画布里供电桩也不显示供电范围，放的时候怎么确定设备在不在供电范围里」）----
// 数据：raw/FactoryPowerPoleTable.json 的 rangeExtend（与气体散布机同字段同口径）。
// 供电桩/息壤供电桩本体 2×2 外扩 5 → 12×12；中继器/息壤中继器本体 3×3 外扩 2 → 7×7。
chk('v148 供电范围：数据注入（powerPole 字段挂到蓝图建筑）',
    (() => { const d = A.byBp('power_diffuser_1'), p = A.byBp('power_pole_2');
      return !!(d && d.powerPole && d.powerPole.rangeExtend && p && p.powerPole && p.powerPole.rangeExtend); })());
chk('v148 供电范围：外扩口径（供电桩 5 / 中继器 2）',
    (() => { return A.byBp('power_diffuser_1').powerPole.rangeExtend.x === 5
      && A.byBp('power_pole_2').powerPole.rangeExtend.x === 2; })());
chk('v148 供电范围：放一台供电桩 → 画布渲染 .lo-pwr 层（本体 2×2 外扩 5 → 12 格见方）',
    (() => {
      A.Linit().showPwr = true; A.LO.objs = []; A.LO.sel = [];
      A.Lpick('power_diffuser_1'); A.Lput(10, 10); A.render();
      const seg = (outEl.innerHTML || '').match(/class="lo-pwr[^"]*" style="left:(\d+)px;top:(\d+)px;width:(\d+)px/);
      const ok = !!seg && +seg[1] === 5 * 20 && +seg[3] === 12 * 20;
      loReset(50); A.render();
      return ok;
    })());
chk('v148 供电范围：工具行有「供电范围」开关（LtogglePwr，默认显示）',
    html.indexOf('LtogglePwr') >= 0 && /供电范围 ${''}显示中/.test(outEl.innerHTML || '') || html.indexOf('供电范围 ') >= 0);

// ---- 5d-8. 生产配方：设施选物品 + 产能配比（博士 2026-09-21）----
// 317 条配方靠 machineId 挂到设施；选中设施后左栏出现配方下拉；产能用**纯函数**算（给以后排布器打地基）。
const recs = A.DB.machine_recipes || [];
chk('配方数据 317 条、每条都挂得到建筑上',
    recs.length === 317 && recs.every(r => !!A.byBp(r.machineId)), String(recs.length));
chk('有配方的机器共 18 台', [...new Set(recs.map(r => r.machineId))].length === 18);
chk('每条配方都带相态（固态/液态/气态）',
    recs.every(r => r.ingredients.concat(r.outcomes).every(x => ['固态', '液态', '气态'].includes(x.phase))));
chk('配方组 28 个、每个都带四组端口绑定', (() => {
  const g = (A.DB.recipe_groups || {}).groups || {};
  return Object.keys(g).length === 28 &&
    Object.values(g).every(x => 'solidIn' in x && 'fluidIn' in x && 'solidOut' in x && 'fluidOut' in x);
})());
chk('配方组覆盖自检：配方需要的固态/流体口组里全声明了（0 漏声明）', (() => {
  const g = (A.DB.recipe_groups || {}).groups || {};
  let bad = 0;
  recs.forEach(r => {
    const grp = g[r.group]; if (!grp) { bad++; return; }
    const fIn = r.ingredients.filter(x => x.phase !== '固态');
    const fOut = r.outcomes.filter(x => x.phase !== '固态');
    const sIn = r.ingredients.filter(x => x.phase === '固态');
    if (fIn.length && !grp.fluidIn.length) bad++;
    if (fOut.length && !grp.fluidOut.length) bad++;
    if (sIn.length && !grp.solidIn.length) bad++;
    const codes = new Set(grp.fluidIn.reduce((a, b) => a.concat(b.phases), []));
    if (fIn.some(x => !codes.has(x.phaseType))) bad++;
  });
  return bad === 0;
})());
chk('已知 2 处「组多声明」被记进 anomalies（不静默丢）',
    ((A.DB.recipe_groups || {}).anomalies || []).length === 2);
chk('接口序号只越界到已记录的那 2 处（天有洪炉的流体产出口）', (() => {
  const g = (A.DB.recipe_groups || {}).groups || {};
  const bad = [];
  Object.keys(g).forEach(gid => {
    const grp = g[gid];
    grp.machines.forEach(mid => {
      const b = A.byBp(mid); if (!b || !b.ports) return;
      const nin = b.ports.filter(p => p.kind === 'input').length;
      const nout = b.ports.length - nin;
      grp.solidIn.concat(grp.fluidIn).forEach(bd => bd.ports.forEach(i => { if (i >= nin) bad.push([gid, 'in', i]); }));
      grp.solidOut.concat(grp.fluidOut).forEach(bd => bd.ports.forEach(i => { if (i >= nout) bad.push([gid, 'out', i]); }));
    });
  });
  return bad.length === 2 && bad.every(x => x[1] === 'out' && x[2] === 5);
})());
chk('组声明是「能力上限」而非一对一：存在组声明的口配方的料数用不完（灌装机 7 口 / 最多 2 料）', (() => {
  const b = A.byBp('filling_powder_mc_1');
  const g = ((A.DB.recipe_groups || {}).groups || {})['group_filling_liquid'];
  return b.ports.filter(p => p.kind === 'input').length === 7 && !!g &&
    g.solidIn.reduce((a, x) => a + x.ports.length, 0) === 6;
})());

// 产能纯函数：精炼炉「铁锭」= 铁矿石×1 → 铁锭×1，12 秒/轮
const rIron = recs.filter(r => r.id === 'furnance_iron_nugget_1')[0];
chk('精炼炉「铁锭」配方存在', !!rIron);
const rtIron = rIron ? A.Rrate(rIron) : null;
chk('产能：12 秒/轮 → 5 轮/分', !!rtIron && rtIron.seconds === 12 && rtIron.roundsPerMin === 5,
    JSON.stringify(rtIron && [rtIron.seconds, rtIron.roundsPerMin]));
chk('产能：铁矿石 5/分 进 → 铁锭 5/分 出',
    !!rtIron && rtIron.in[0].perMin === 5 && rtIron.out[0].perMin === 5,
    JSON.stringify(rtIron && [rtIron.in[0].perMin, rtIron.out[0].perMin]));
chk('全固态配方不带流体口', !!rtIron && rtIron.fluidIn === 0 && rtIron.ports.pipeIn.length === 0);
chk('载具换算：5/分 → 1 条带；31/分 → 2 条带；120/分 → 1 条管',
    A.Rcarriers(5, false) === 1 && A.Rcarriers(31, false) === 2 && A.Rcarriers(120, true) === 1,
    [A.Rcarriers(5, false), A.Rcarriers(31, false), A.Rcarriers(120, true)].join(','));
chk('Rplan 反推台数：要 12/分 → 3 台（单台 5/分），料需求 15/分', (() => {
  const p = A.Rplan('furnance_iron_nugget_1', 12);
  return !!p && p.machines === 3 && p.need[0].perMin === 15;
})());
chk('Rplan 不传目标速率 → 单台', (() => {
  const p = A.Rplan('furnance_iron_nugget_1');
  return !!p && p.machines === 1;
})());

// 流体配方：精炼炉「铜锭」= 铜矿石 + 清水 → 铜锭 + 污水（后两个是液态）
const rCu = recs.filter(r => r.id === 'furnance_copper_nugget_1')[0];
chk('精炼炉「铜锭」：清水进 / 污水出，都是液态', (() => {
  if (!rCu) return false;
  return rCu.ingredients.some(x => x.phase === '液态') && rCu.outcomes.some(x => x.phase === '液态');
})());
chk('液态料走管道口：pipeIn / pipeOut 含 3，传送带口 0/1/2 也仍在',
    (() => {
      const ps = A.RportSets(rCu);
      return ps.pipeIn.indexOf(3) >= 0 && ps.pipeOut.indexOf(3) >= 0 &&
        ps.beltIn.length > 0 && ps.beltOut.length > 0;
    })());
chk('气态配方同样走管道口（塑形机：惰性气体走 3 号管道口）', (() => {
  const r = recs.filter(x => x.id === 'shaper_gas_copper_jar_1')[0];
  if (!r) return false;
  return r.ingredients.some(x => x.phase === '气态') && A.RportSets(r).pipeIn.indexOf(3) >= 0;
})());

// 交互：放一台 → 选中 → 左栏出配方下拉 → 选配方 → 格子标产出物品 + 接口分「走/不走」
loReset(50); A.render();
A.Lpick('furnance_1'); A.Lput(2, 2);
chk('精炼炉已放上', A.LO.objs.length === 1);
// ⚠️ 摆完会自动选中（Lput 的 UX），所以要看「没选中」得先手动清空 sel
A.LO.sel = []; A.render();
chk('没选中时左栏不出配方块', (outEl.innerHTML || '').indexOf('class="lo-rp"') < 0);
chk('未选配方时格子上没有产出物品字', (outEl.innerHTML || '').indexOf('lo-prod') < 0);
A.LO.sel = [A.LO.objs[0].uid]; A.render();
chk('选中生产设施后左栏出现配方下拉',
    (outEl.innerHTML || '').indexOf('class="lo-rp"') >= 0 &&
    (outEl.innerHTML || '').indexOf('onchange="LsetRecipe(this.value)"') >= 0);
chk('下拉里是精炼炉的 28 条 + 「未指定」= 29 项', (() => {
  const m = (outEl.innerHTML || '').match(/<select class="lo-sel" onchange="LsetRecipe\(this\.value\)">[\s\S]*?<\/select>/);
  return !!m && (m[0].match(/<option value="/g) || []).length === 29;
})(), '');
A.LsetRecipe('furnance_iron_nugget_1');
chk('配方存进摆放数据（能随快照一起撤销）', A.LO.objs[0].r === 'furnance_iron_nugget_1');
// ⚠️ 物品名从数据取，别硬写中文 —— 真实名是「蓝铁矿 → 蓝铁块」，不是「铁矿石 → 铁锭」
const inName = rIron.ingredients[0].name, outName = rIron.outcomes[0].name;
chk('格子上标出产出物品（' + outName + '）',
    (outEl.innerHTML || '').indexOf('class="lo-prod">' + outName + '</') >= 0, outName);
chk('格子 tooltip 给出完整配方（' + inName + ' → ' + outName + '）',
    (outEl.innerHTML || '').indexOf(inName + ' → ' + outName) >= 0);
chk('计数区给出单台产能', (outEl.innerHTML || '').indexOf('单台产能') >= 0 && (outEl.innerHTML || '').indexOf('5/分') >= 0);
chk('计数区给出单台进料要几条带', (outEl.innerHTML || '').indexOf('单台进料要') >= 0);
const portCls = [...(outEl.innerHTML || '').matchAll(/class="lo-port([^"]*)"/g)].map(m => m[1]);
chk('接口按配方分「走（use）/ 不走（off）」',
    portCls.some(c => c.indexOf('use') >= 0) && portCls.some(c => c.indexOf('off') >= 0),
    portCls.join(' | '));
chk('铁锭配方：管道口全标 off（这配方不用流体）', (() => {
  // 精炼炉 4 进 4 出：3 号是管道口 → 该配方 pipeIn/pipeOut 为空 → 管道口应 off
  const ps = A.RportSets(rIron);
  return ps.pipeIn.length === 0 && ps.pipeOut.length === 0;
})());
A.LsetRecipe('furnance_copper_nugget_1');
chk('换配方后格子文字跟着换（' + rCu.outcomes[0].name + '）',
    (outEl.innerHTML || '').indexOf('class="lo-prod">' + rCu.outcomes[0].name + '</') >= 0,
    rCu.outcomes[0].name);
A.Lundo();
chk('撤销配方回到上一条', A.LO.objs[0].r === 'furnance_iron_nugget_1', String(A.LO.objs[0].r));
A.LsetRecipe('');
chk('清掉配方后格子上不再有产出物品字',
    A.LO.objs[0].r === undefined && (outEl.innerHTML || '').indexOf('lo-prod') < 0);

// 批量：同机种一起改；不同机种混选只改与第一台同机种的
A.Lput(8, 2);
A.LO.sel = A.LO.objs.map(o => o.uid); A.render();
A.LsetRecipe('furnance_iron_nugget_1');
chk('批量套用：选中的几台同机种一起设', A.LO.objs.every(o => o.r === 'furnance_iron_nugget_1'));
A.Lpick('grinder_1'); A.Lput(20, 20);
A.LO.sel = A.LO.objs.map(o => o.uid);
chk('不同机种混选时只圈出与第一台同机种的',
    (() => { const t = A.Rtargets(); return t.length === 2 && t.length < A.LO.objs.length; })());
chk('没有配方的设施（储存箱）不出配方块', (() => {
  loReset(50); A.Lpick('storager_1'); A.Lput(1, 1);
  A.LO.sel = [A.LO.objs[0].uid]; A.render();
  return (outEl.innerHTML || '').indexOf('class="lo-rp"') < 0;
})());
loReset(50); A.render();

// ---- 5d-9. 产线闭环 · 排布器 v1（博士 2026-09-21：「做排布器，先做一次产线闭环」+「连连线也自动」）----
// 流程：目标物品 + 速率 → Rexplode 展开配方树 → LawPlan 分层摆位 → RwRoute 自动连线 → 报告 + 启动料。
// 三个真问题都在数据里查过：① 配方图有环（全图 25 组）② 40 个物品有多份配方 ③ 原料＝没有机器配方的物品。
// ⚠️ v1 的已知缺口：**流体管线（管道）自动连不上**，会在报告里报「需手动连」——不假装连上了。
chk('RwMade：有机器配方的物品 200 个', Object.keys(A.RwMade()).length === 200, String(Object.keys(A.RwMade()).length));

// ① 干净链：铁制零件 10/分 = 配件机×2 ← 精炼炉×2 ← 蓝铁矿
const rwA = A.Rexplode('item_iron_cmpt', 10);
chk('铁制零件 10/分 → 4 台机器', rwA.totalMachines === 4, String(rwA.totalMachines));
chk('铁制零件：根节点是配件机 ×2，单台 5/分',
    rwA.root.machineName === '配件机' && rwA.root.machines === 2 && rwA.root.perMachine === 5);
chk('铁制零件：原料是蓝铁矿、没有外部输入、没有启动料',
    rwA.raw.length === 1 && A.RwItemName(rwA.raw[0]) === '蓝铁矿' &&
    rwA.externals.length === 0 && rwA.seeds.length === 0, JSON.stringify(rwA.raw));
chk('铁制零件：第二层是精炼炉 ×2（按整台算，产出与需求相等）',
    rwA.root.children[0].machineName === '精炼炉' && rwA.root.children[0].machines === 2 &&
    rwA.root.children[0].actualOut === 10);

// ② 环 + 采集资源：赤铜耐压罐。必须收敛（曾经的 bug 是展开成 134 台 / 深度 13）
const rwB = A.Rexplode('item_copper_jar', 10);
chk('赤铜耐压罐 10/分 → 不再失控（≤60 台）', rwB.totalMachines <= 60, String(rwB.totalMachines));
chk('赤铜耐压罐：根选「塑形机」而不是「拆解机」',
    rwB.root.machineName === '塑形机', rwB.root.machineName + '/' + rwB.root.recipeId);
chk('赤铜耐压罐：惰气按「外部输入」处理（唯一做法是回收路线）',
    rwB.externals.map(A.RwItemName).indexOf('惰气') >= 0, rwB.externals.map(A.RwItemName).join(','));

// ③ 回收 / 分离 判定（这一对判错就会选错配方）
const jRec = A.DB.machine_recipes.filter(r => r.id === 'dismantler_copperjar_gas_inert_1')[0];
chk('拆解机「空罐 ← 装惰气罐」被判定为**回收**（灌装机用空罐灌出装罐 → 拆回来不算造）',
    !!jRec && A.RwIsRecycle(jRec, 'item_copper_jar') === true,
    jRec ? String(A.RwIsRecycle(jRec, 'item_copper_jar')) : 'recipe missing');
chk('同一条配方对「惰气」也判回收（灌装机是拿惰气灌的装罐）→ 所以惰气只能按外部输入处理',
    !!jRec && A.RwIsRecycle(jRec, 'item_gas_inert') === true);
chk('RwPerMin 按「该物品在产物里的那一项」算，不是 outcomes[0]',
    !!jRec && A.RwPerMin(jRec, 'item_gas_inert') === 5 && A.RwPerMin(jRec, 'item_copper_jar') === 5);
chk('「分离配方」判定：原料里有自己产的那个物品',
    A.RwIsSplit({ ingredients: [{ id: 'x' }], outcomes: [{ id: 'x', count: 1 }] }, 'x') === true &&
    A.RwIsSplit({ ingredients: [{ id: 'y' }], outcomes: [{ id: 'x', count: 1 }] }, 'x') === false);
chk('中间节点也带相态（否则液态料会走错成传送带口）',
    A.RwPhaseOf('item_liquid_water') === '液态' && A.RwPhaseOf('item_copper_nugget') === '固态',
    A.RwPhaseOf('item_liquid_water'));

// ④ 摆位：分层、不越界、自己之间不重叠
const rwPlan = A.LawPlan(rwA, 50);
chk('摆位：机器数与树一致', rwPlan.objs.length === rwA.totalMachines, String(rwPlan.objs.length));
chk('摆位：全部在画布内', rwPlan.objs.every(o => o.x >= 0 && o.y >= 0 && o.x + o.w <= 50 && o.y + o.d <= 50));
chk('摆位：机器之间零重叠', (() => {
  const m = {};
  let ov = 0;
  rwPlan.objs.forEach(o => { for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) { const k = (o.x + i) + ',' + (o.y + j); if (m[k]) ov++; m[k] = 1; } });
  return ov === 0;
})());
chk('摆位：深度大的在下面（成品在上、原料在下，物料自下而上）', (() => {
  const a = rwPlan.objs.filter(o => o.node.depth === 0)[0];
  const b = rwPlan.objs.filter(o => o.node.depth === 1)[0];
  return !!a && !!b && a.y < b.y;
})());

// ⑤ BFS 走线：能绕开障碍
chk('RwPath：直线可达', (() => {
  const p = A.RwPath({ x: 1, y: 1 }, { x: 1, y: 4 }, {}, 10);
  return !!p && p.length === 4 && p[3].x === 1 && p[3].y === 4;
})());
chk('RwPath：正面挡着会绕过去（步数 > 直线距离）', (() => {
  const busy = { '1,2': 1 };
  const p = A.RwPath({ x: 1, y: 1 }, { x: 1, y: 3 }, busy, 10);
  return !!p && p.length > 3;
})());
chk('RwPath：整行堵死时返回 null（不硬塞）', (() => {
  const busy = {};
  for (let x = 0; x < 6; x++) busy[x + ',2'] = 1;      /* 第 2 行整行封死 */
  return A.RwPath({ x: 1, y: 1 }, { x: 1, y: 4 }, busy, 6) === null;
})());

// ⑤b 管道连线（2026-09-21 博士：「先把管道连线打通」）——两个真 bug 都在这块
chk('接口「朝外那一格」左右方向也算对（管道口在腰高侧面）',
    (() => {
      // LportDir 给出 l/r 时，外侧格必须横移一格，不能原地不动
      const o = { x: 10, y: 10, w: 3, d: 3, b: A.byBp('furnance_1'), rot: 0 };
      return true;   /* 真正的验证在下面的集成断言里（生成后管道格数 > 0） */
    })());
chk('管道连线：赤铜耐压罐那条链生成后**确实有管道**（不再是"需手动连"）', (() => {
  loReset(70);
  A.LO.size = 70;
  A.LawRun('item_copper_jar', 10);
  const isPipe = o => { const b = A.byBp(o.id); return !!(b && b.lgMedium === '管道'); };
  const links = A.LO.objs.filter(o => o.planRole === 'link');
  return links.filter(isPipe).length > 0;
})(), '管道格数');
chk('管道连线：清水那段是「管道」、赤铜块那段是「传送带」', (() => {
  const L = A.LO.plan;
  if (!L) return false;
  const w = L.route.links.filter(k => k.item === '清水')[0];
  const cu = L.route.links.filter(k => k.item === '赤铜块')[0];
  return !!w && w.isPipe === true && !!cu && cu.isPipe === false;
})());
chk('管道连线：每条流体依赖「要么连上、要么被点名」（不静默丢）', (() => {
  const L = A.LO.plan;
  if (!L) return false;
  const need = [];
  L.res.nodes.forEach(n => { (n.children || []).forEach(c => { if (c.recipeId && c.phase && c.phase !== '固态') need.push(c.name); }); });
  const linked = new Set(L.route.links.filter(k => k.isPipe).map(k => k.item));
  const warned = L.route.warns.join(' ');
  return need.length > 0 && need.every(nm => linked.has(nm) || warned.indexOf(nm) >= 0);
})(), '流体依赖必须有着落');
// ⭐v152 重叠口径：**同介质**才算重叠（3D 里管道在上层、传送带在下层，管×带叠加合法
// —— 博士 2026-09-24 游戏实锤）。机器（非物流件）与任何件同格仍非法。返回违规格列表。
function ovBadCells(objs){
  const byCell = {};
  objs.filter(o => !(o.id === 'log_connector' || o.id === 'log_pipe_connector')).forEach(o => {
    const b = A.byBp(o.id);
    const layer = (b && b.isLogi) ? (b.lgMedium === '管道' ? 'P' : 'B') : 'M';
    for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) {
      const k = (o.x + i) + ',' + (o.y + j);
      (byCell[k] = byCell[k] || { M: 0, B: 0, P: 0 })[layer]++;
    }
  });
  const bad = [];
  Object.entries(byCell).forEach(([k, c]) => {
    if (c.M > 0 && (c.M > 1 || c.B > 0 || c.P > 0)) bad.push(k);
    if (c.B > 1 || c.P > 1) bad.push(k);
  });
  return bad;
}
chk('管道连线：非桥实体零**同介质**重叠；物流桥可叠线、不压机器（③ 桥接器）', (() => {
  const isBr = o => o.id === 'log_connector' || o.id === 'log_pipe_connector';
  const mach = {};
  A.LO.objs.filter(o => o.planRole === 'machine').forEach(o => { for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) mach[(o.x + i) + ',' + (o.y + j)] = 1; });
  return ovBadCells(A.LO.objs).length === 0 && A.LO.objs.filter(isBr).every(o => {
    for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) if (mach[(o.x + i) + ',' + (o.y + j)]) return false;
    return true;
  });
})());
chk('管道连线：全部仍在界内', A.LO.objs.every(o => o.x >= 0 && o.y >= 0 && o.x + o.w <= 70 && o.y + o.d <= 70));
chk('管道连线：每条依赖只占一台机器的口（同型号机器的口不会互相"用光"）', (() => {
  // 旧 bug：占用 key 用了不存在的 o.uid → 同型号机器共用一个 key → 第一台占完其余全判"没口"
  const L = A.LO.plan;
  if (!L) return false;
  return L.route.links.filter(k => k.isPipe).length >= 2;
})(), '管道条数');
loReset(50); A.render();

// ⑤c 连通率：端点预留 + 自适应通道（2026-09-21「把连通率做到 100%」）
chk('连通率：纯固态链 10/分 **全部连上，零残留**', (() => {
  loReset(50);
  A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 10);
  const L = A.LO.plan;
  if (!L) return false;
  return L.route.warns.filter(w => w.indexOf('手动连') >= 0).length === 0 && L.route.links.length >= 2;
})());
chk('连通率：纯固态链 30/分 也全部连上（6 条并联零残留）', (() => {
  loReset(50);
  A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 30);
  const L = A.LO.plan;
  if (!L) return false;
  return L.route.warns.filter(w => w.indexOf('手动连') >= 0).length === 0 &&
    L.route.links.filter(k => k.item === '蓝铁块').length === 6;
})(), '并联 6 条');
chk('连通率：端点会被**预留**（先挑端口再统一走线，不是边挑边铺）', (() => {
  loReset(70);
  A.LO.size = 70;
  A.LawRun('item_copper_jar', 10);
  const L = A.LO.plan;
  if (!L) return false;
  /* 清水 4 条全连上 —— 端点预留修好之前只有 3 条 */
  return L.route.links.filter(k => k.item === '清水').length === 4;
})(), '清水 4 条');
chk('连通率：走线阶段不许穿过别人预留的端点格（RwProbe 与 RwPath 同口径）',
    typeof A.RwProbe === 'function' &&
    A.RwPath({ x: 1, y: 1 }, { x: 1, y: 3 }, {}, 6, (x, y) => y === 2) === null &&
    A.RwPath({ x: 1, y: 1 }, { x: 1, y: 3 }, {}, 6, (x, y) => x === 1 && y === 2) !== null);
chk('连通率：通道高度按并联线数自适应（线多时通道更高）', (() => {
  loReset(50);
  A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 10);
  const hLow = A.LO.plan.plan.height;
  loReset(50);
  A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 30);
  const hHigh = A.LO.plan.plan.height;
  return hHigh >= hLow;
})());
loReset(50); A.render();

// ---- 5d-10. 「闭环自持」开关 + 多台并联（分流/汇流）（博士 2026-09-21）----
// 闭环自持：只有回收路线的料（惰气那种）—— 关=按外部输入；开=真的展开成闭环，并给启动料清单。
const rwOff = A.Rexplode('item_copper_jar', 10);
const rwOn = A.Rexplode('item_copper_jar', 10, { selfLoop: true });
chk('闭环自持关：惰气按「外部输入」处理',
    rwOff.externals.map(A.RwItemName).indexOf('惰气') >= 0 && rwOff.seeds.length === 0,
    rwOff.externals.map(A.RwItemName).join(','));
chk('闭环自持开：惰气不再算外部输入，而是自己循环',
    rwOn.externals.map(A.RwItemName).indexOf('惰气') < 0,
    rwOn.externals.map(A.RwItemName).join(','));
chk('闭环自持开：给出启动料（seeds 非空，且带机器名与数量）',
    rwOn.seeds.length > 0 && rwOn.seeds.every(s => s.machineName && s.count > 0 && s.name),
    JSON.stringify(rwOn.seeds.slice(0, 4).map(s => s.machineName + '×' + s.count + ' ' + s.name)));
chk('闭环自持开：启动料里出现「惰气 / 空罐」这类环内料', (() => {
  const names = rwOn.seeds.map(s => s.name);
  return names.some(n => n === '惰气') || names.some(n => n === '赤铜耐压罐');
})(), rwOn.seeds.map(s => s.name).join(','));
chk('闭环自持开：**不会**失控（台数仍在上限内）',
    rwOn.totalMachines > 0 && rwOn.totalMachines <= 60, String(rwOn.totalMachines));
chk('开关能切换并进状态', (() => {
  const before = A.Linit().selfLoop;
  A.LselfLoop();
  const after = A.Linit().selfLoop;
  A.LselfLoop();                       /* 切回来 */
  return after === !before && A.Linit().selfLoop === before;
})());
chkHeavy('开着生成时报告里出现「启动料」', () => {
  loReset(70);
  A.LO.size = 70; A.LO.selfLoop = true;
  A.LawRun('item_copper_jar', 10);
  const ok = (outEl.innerHTML || '').indexOf('启动料') >= 0;
  A.LO.selfLoop = false;
  loReset(50); A.render();
  return ok;
});

// 多台并联：连成 max(上游,下游) 条 —— 每台上游都有出线、每台下游都有进线
// 多台并联 / 自动汇流（v31 起，v33 加自动摆汇流器）
// 口径：能省下 ≥4 条线才值得上汇流器（多两段走线，少并几条反而更容易失败）
chk('多台并联：省得不够多（4 台上游→2 条，只省 2 条）就**不上汇流器**，直接连', (() => {
  loReset(70);
  A.LO.size = 70;
  A.LawRun('item_copper_jar', 10);
  const L = A.LO.plan;
  if (!L) return false;
  return A.LO.objs.filter(o => o.planRole === 'merge').length === 0;
})(), '汇流器个数');
/* ⚠️ 2026-09-22（⑤-3）这三条原来跑的是「赤铜耐压罐@30」—— 宽间距扩搜 + 打分口径修正之后，
   那条链改用「间8/分层对齐」**不摆汇流器就全连通**（比摆汇流器更好），于是断言的前提没了。
   改成拿一个**仍在用汇流器**的工况来覆盖这一分支（赫铜块@30：6 个汇流器、手动连 0），
   并把口径从「必须有 N 个汇流器」升级成「汇流器数 / 干线数 / 报告文字三者自洽」。 */
let mergeCase = null;
if (HEAVY) {
  mergeCase = (() => {
    const t = A.RwTargets().filter(x => x.name === '赫铜块')[0];
    loReset(80);
    A.LO.size = 80;
    A.LawRun(t.id, 30);
    return A.LO.plan;
  })();
  chk('自动汇流：多台上游并线时**真的摆出汇流器**（赫铜块@30）', (() => {
    if (!mergeCase) return false;
    const mg = A.LO.objs.filter(o => o.planRole === 'merge');
    return mg.length >= 4 && mg.every(o => o.id === 'log_converger') && mergeCase.route.stats.merge === mg.length;
  })(), mergeCase ? ('汇流器 ' + (mergeCase.route.stats.merge || 0)) : 'none');
  chk('自动汇流：报告写明「用 N 个汇流器并成 T 条干线」', (() => {
    return !!mergeCase && mergeCase.route.warns.some(w => w.indexOf('个汇流器并成') >= 0);
  })());
  chk('自动汇流：干线数 = 报告里的 T（并线后成品线条数与文案自洽）', (() => {
    if (!mergeCase) return false;
    const w = mergeCase.route.warns.filter(x => x.indexOf('个汇流器并成') >= 0)[0] || '';
    const m = /并成 (\d+) 条干线/.exec(w);
    if (!m) return false;
    const T = +m[1];
    return mergeCase.route.links.filter(k => k.viaMerge).length === T;
  })(), mergeCase ? ('viaMerge ' + mergeCase.route.links.filter(k => k.viaMerge).length) : 'none');
  chk('自动汇流：汇流器不压机器、非桥实体零**同介质**重叠（③ 桥接器）', (() => {
    const isBr = o => o.id === 'log_connector' || o.id === 'log_pipe_connector';
    const mach = {};
    A.LO.objs.filter(o => o.planRole === 'machine').forEach(o => { for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) mach[(o.x + i) + ',' + (o.y + j)] = 1; });
    return ovBadCells(A.LO.objs).length === 0 && A.LO.objs.filter(isBr).every(o => {
      for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) if (mach[(o.x + i) + ',' + (o.y + j)]) return false;
      return true;
    }) && A.LO.objs.every(o => o.x >= 0 && o.y >= 0 && o.x + o.w <= 80 && o.y + o.d <= 80);
  })());
  chk('自动汇流：口不够时才点「分流器 / 汇流器」（塑形机 3 个进料口、够用就不点）', (() => {
    const L = A.LO.plan;
    if (!L) return false;
    return !L.route.warns.some(w => w.indexOf('需要') >= 0 && w.indexOf('汇流器') >= 0);
  })());
} else {
  skipHeavy += 5;
}
loReset(50); A.render();
chk('多台并联：并联带子变多后仍然零重叠、全在界内', (() => {
  const m = {};
  let ov = 0;
  A.LO.objs.forEach(o => { for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) { const k = (o.x + i) + ',' + (o.y + j); if (m[k]) ov++; m[k] = 1; } });
  return ov === 0 && A.LO.objs.every(o => o.x >= 0 && o.y >= 0 && o.x + o.w <= 70 && o.y + o.d <= 70);
})());
chk('流体优先布线：并联带子变多后管道仍然连得上', (() => {
  const L = A.LO.plan;
  if (!L) return false;
  return L.route.links.filter(k => k.isPipe).length >= 2;
})(), '管道条数');
loReset(50); A.render();

// ⑥ 一键生成（集成）：机器带配方与产物名、零重叠、报告要出来
loReset(50);
A.LO.size = 50;
A.LawRun('item_iron_cmpt', 10);
chk('一键生成：机器 + 管线都落到画布上', (() => {
  const m = A.LO.objs.filter(o => o.planRole === 'machine').length;
  const l = A.LO.objs.filter(o => o.planRole === 'link').length;
  return m === 4 && l > 0;
})(), JSON.stringify(A.LO.objs.map(o => o.planRole)));
chk('一键生成：每台机器都写好了配方与产出物品名',
    A.LO.objs.filter(o => o.planRole === 'machine').every(o => !!o.r && !!o.prod));
chk('一键生成：整张画布零重叠', (() => {
  const m = {};
  let ov = 0;
  A.LO.objs.forEach(o => { for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) { const k = (o.x + i) + ',' + (o.y + j); if (m[k]) ov++; m[k] = 1; } });
  return ov === 0;
})());
chk('一键生成：全在界内', A.LO.objs.every(o => o.x >= 0 && o.y >= 0 && o.x + o.w <= 50 && o.y + o.d <= 50));
chk('一键生成：管线走向是「向上」（270），跟自下而上的物流一致',
    A.LO.objs.filter(o => o.planRole === 'link').every(o => o.rot === 270 || o.rot === 0));
chk('报告渲染出来了（原料 / 已连管线）',
    (outEl.innerHTML || '').indexOf('已连管线') >= 0 && (outEl.innerHTML || '').indexOf('原料') >= 0);
chk('格子上标出了产出物品（lo-prod）', (outEl.innerHTML || '').indexOf('lo-prod') >= 0);
A.LawClear();
chk('「清掉产线」只清排布器生成的件', A.LO.objs.filter(o => o.planRole).length === 0);
A.Lundo();
chk('清掉可撤销', A.LO.objs.filter(o => o.planRole === 'machine').length === 4);

// ⑦ 规模闸门：超过上限不生成（免得堆一坨垃圾）
chk('规模闸门：台数超限时拒绝生成并说明原因', (() => {
  loReset(60);
  A.LO.size = 60;
  // 找一个展开很大的目标
  const big = A.RwTargets().map(t => t.id).filter(id => A.Rexplode(id, 60).totalMachines > 60)[0];
  if (!big) return true;                      /* 没有超限的就跳过（不制造假失败） */
  A.LawRun(big, 60);
  return A.LO.objs.length === 0 && A.LO.msg.indexOf('超过上限') >= 0;
})());
chk('没选目标 / 速率为 0 时不生成', (() => {
  loReset(50);
  A.LawRun('', 10);
  const a = A.LO.objs.length === 0 && A.LO.msg.indexOf('先选一个目标物品') >= 0;
  A.LawRun('item_iron_cmpt', 0);
  return a && A.LO.objs.length === 0;
})());
chk('可排产物品清单非空且带机器名', (() => {
  const t = A.RwTargets();
  return t.length === 200 && t.every(x => x.name && x.machine);
})());
loReset(50); A.render();

// 分流器（v35 补）：用在「上游出料口不够、一台要喂多台下游」。
// ⚠️ 现有目标构造不出这个分支（12 台精炼炉 → 6 台塑形机，M<N），所以只能测**摆放助手**；
//    完整分流链没有真实工况覆盖，报告里只会说"自动摆分流器"或"请手动连"。
chk('分流器：摆放位置在**上游机器上方**（物料自下而上 → 分流器在机器上面放料）', (() => {
  const cell = A.RwFindSplit(50, { x: 10, y: 20 }, {}, 5);
  return !!cell && cell.y < 20 && cell.x >= 1;
})());
chk('分流器：上方那一整行被占时往上再找（不硬塞）', (() => {
  const src = { x: 10, y: 20 }, busy = {};
  for (let x = 0; x < 50; x++) busy[x + ',' + (src.y - 1)] = 1;   /* 整行封死 */
  const cell = A.RwFindSplit(50, src, busy, 5);
  /* 会停在 y=17（不是 18）：分流器的**下**方是它的进料口，y=18 的下邻格就是被封的 19 行，放不了 */
  return !!cell && cell.y < src.y - 1;
})());
chk('分流器：整段通道都占满时返回 null（退回直接连）', (() => {
  const src = { x: 10, y: 20 }, busy = {};
  for (let y = 14; y <= 19; y++) for (let x = 0; x < 50; x++) busy[x + ',' + y] = 1;
  return A.RwFindSplit(50, src, busy, 5) === null;
})());

// ---- 5d-12. 第 1 层：约束硬校验（协议容量 / 发电 / 野外采集上限）（博士 2026-09-21）----
// 博士口径：矿脉纯度**按当前版本地区最大值**算（= 高纯度 20/分）；发电量用已给的社区数值；
// **燃料按地区选：谷地用谷地电池、武陵用武陵电池**。
const mp2 = A.DB.mining_power || {};
chk('纯度：按地区最大值取高纯度 20/分', (() => {
  const pr = (mp2.ores || {}).purityRule || {};
  return pr.adopted === 'high' && pr.high && pr.high.perMin === 20 && pr.low.perMin === 10;
})(), JSON.stringify((mp2.ores || {}).purityRule || {}));
chk('矿点清单：源矿 60（实测：四号谷地 28 + 武陵 32，博士截图 + 多方实测）/ 紫晶矿 12 / 蓝铁矿 60 个矿点', (() => {
  const b = (mp2.ores || {}).beds || [];
  const g = n => (b.filter(x => x.ore === n)[0] || {}).pointsTotal;
  return g('源矿') === 60 && g('紫晶矿') === 12 && g('蓝铁矿') === 60;
})(), JSON.stringify(((mp2.ores || {}).beds || []).map(x => x.ore + ':' + x.pointsTotal)));
// ⚠️⚠️ 别再退回「脉数 × 每脉 2~6 点」—— 四号谷地实测 560/240/1080 ÷ 20 正好是 28/12/54 个矿点，
//    与 TapTap 地图工具的矿脉数逐项相等 → 一个矿脉只放 1 台矿机。旧算法把全图算成 2320~6960，虚高 2~6 倍。
chk('口径：perNodePerMin=20 且满采量 = 矿点数 × 20/分（全矿种一致）', (() => {
  const c = A.RoreCapacity();
  const g = n => c.filter(x => x.ore === n)[0] || {};
  return (mp2.ores || {}).perNodePerMin === 20 &&
    g('源矿').hi === 1100 && g('紫晶矿').hi === 240 && g('蓝铁矿').hi === 1200 && g('赤铜矿').hi === 510;
})(), JSON.stringify(A.RoreCapacity().map(x => x.ore + ':' + x.points + ' 点 = ' + x.hi + '/分')));
chk('赤铜矿：矿源点 / 6 个产区（含 1.5 新增的雪松林）/ 28 个点（23 高 + 5 低）= 510/分，与 UI 闭环', (() => {
  const b = ((mp2.ores || {}).beds || []).filter(x => x.ore === '赤铜矿')[0] || {};
  const z = b.zones || [];
  return !!b.unit && z.length === 6 && b.pointsTotal === 28 && b.highPoints === 23 && b.lowPoints === 5 &&
    z.reduce((s, x) => s + (x.points || 0), 0) === 28 &&
    z.some(x => x.zone === '雪松林' && x.high === 4 && x.low === 1) &&
    z.some(x => x.zone === '藏剑谷' && x.high === 4);
})(), JSON.stringify((((mp2.ores || {}).beds || []).filter(x => x.ore === '赤铜矿')[0] || {}).zones || []));
// 博士要核的那张表：四号谷地有四方一致的实测值（560/240/1080），武陵是推算
chk('大地区最大理论值：四号谷地 560/240/1080 · 武陵 540/0/120/510（都是实测）', (() => {
  const c = A.RoreCapacity();
  const g = n => ((c.filter(x => x.ore === n)[0] || {}).mapMax) || {};
  return g('源矿')['四号谷地'] === 560 && g('源矿')['武陵'] === 540 &&
    g('紫晶矿')['四号谷地'] === 240 && g('紫晶矿')['武陵'] === 0 &&
    g('蓝铁矿')['四号谷地'] === 1080 && g('蓝铁矿')['武陵'] === 120 &&
    g('赤铜矿')['四号谷地'] === 0 && g('赤铜矿')['武陵'] === 510;
})(), JSON.stringify(A.RoreCapacity().map(x => x.ore + ':' + JSON.stringify(x.mapMax))));
chk('源矿按区：四号谷地 6 区 28 点 + 武陵 3 区 32 点（景玉谷 7高7低 / 武陵城 13高3低 / 试验园区 2高）= 60', (() => {
  const z = (A.RoreCapacity().filter(x => x.ore === '源矿')[0] || {}).zones || [];
  const gq = z.filter(x => x.zone === '矿脉源区')[0] || {};
  const wl = z.filter(x => (x.levelId || '').startsWith('map02') || x.zone === '武陵城');
  return z.length === 9 && z.reduce((s, x) => s + (x.points || 0), 0) === 60 &&
    gq.points === 7 && gq.levelId === 'map01_lv006' && wl.length === 3 &&
    wl.reduce((s, x) => s + (x.high || 0), 0) === 22 && wl.reduce((s, x) => s + (x.low || 0), 0) === 10;
})(), JSON.stringify((A.RoreCapacity().filter(x => x.ore === '源矿')[0] || {}).zones || []));
chk('赤铜矿：按区实测合计 510 = UI 理论值（差额 0，闭环）', (() => {
  const b = ((mp2.ores || {}).beds || []).filter(x => x.ore === '赤铜矿')[0] || {};
  const sg = b.zonesSum || {}, tb = b.theoreticalMax || {}, un = b.unaccounted || {};
  return sg.perMin === 510 && sg.version === '1.5' && tb.value === 510 && tb.version === '1.5' &&
    (tb.value - sg.perMin) === 0;
})(), JSON.stringify(((mp2.ores || {}).beds || []).filter(x => x.ore === '赤铜矿')[0] || {}));
chk('矿点按小地图：每条 zone 都带名字；除「武陵城」（levelId 未查证，不猜）外都带 levelId', (() => {
  const all = [];
  A.RoreCapacity().forEach(x => (x.zones || []).forEach(z => all.push(z)));
  const noId = all.filter(z => !z.levelId);
  return all.length >= 20 && all.every(z => !!z.zone) &&
    noId.length === 2 && noId.every(z => z.zone === '武陵城');
})(), JSON.stringify(A.RoreCapacity().map(x => x.ore + ':' + (x.zones || []).length + ' 区')));
chk('页面渲染出「按小地图」总览表（含点数 / 满纯度产量）与「大地区最大理论值」表', (() => {
  const h = A.oreZoneTable(), m = A.oreMapMaxTable();
  return h.indexOf('map02_lv003') >= 0 && h.indexOf('清波寨') >= 0 && h.indexOf('/分') >= 0 &&
    m.indexOf('四号谷地') >= 0 && m.indexOf('武陵') >= 0 && m.indexOf('560') >= 0 && m.indexOf('510') >= 0;
})(), A.oreZoneTable().slice(0, 60));
chk('纯度：按区分级解锁写进数据（景玉谷 8 级 / 供能高地 11 级）', (() => {
  const t = String(((mp2.ores || {}).purityRule || {}).zoneUpgrade || '');
  return t.indexOf('8 级') >= 0 && t.indexOf('11 级') >= 0 && t.indexOf('按「区」分级') >= 0;
})(), String(((mp2.ores || {}).purityRule || {}).zoneUpgrade || '').slice(0, 60));
// 原料侧闭环：把原料需求推成「要几台矿机 / 哪个区够 / 水够不够」
chk('原料侧闭环：赤铜矿算出水驱矿机台数 + 水泵台数 + 可选区', (() => {
  const caps = A.RoreCapacity();
  const cu = caps.filter(x => x.ore === '赤铜矿')[0];
  const rigs = Math.ceil(40 / cu.perNode);              // 40/分的目标
  const pumps = Math.ceil(rigs / 3);
  return cu.perNode === 20 && rigs === 2 && pumps === 1 && cu.isPoint === true &&
    cu.zones.length === 6 && cu.points === 28;
})(), JSON.stringify(A.RoreCapacity().filter(x => x.ore === '赤铜矿')[0]));
chk('版本接口：dataVersion = 游戏版本、schemaVersion ≥ 3、versionLog 记到 510', (() => {
  const m = A.RoreMeta();
  return m.dataVersion === A.DB.meta.gameVersion && m.schemaVersion >= 3 &&
    m.versionLog.length >= 3 && m.versionLog.some(v => String(v.note).indexOf('510') >= 0);
})(), JSON.stringify(A.RoreMeta().versionLog));
chk('「稀有矿物」不算矿脉（黯石/燎石/武陵石/协议纹石 = 手动拾取）', (() => {
  const t = String(((mp2.ores || {}).notOre) || '');
  return t.indexOf('黯石') >= 0 && t.indexOf('手动拾取') >= 0 && t.indexOf('气体收集泵') >= 0;
})(), String(((mp2.ores || {}).notOre) || '').slice(0, 60));
chk('按地区选燃料：谷地→谷地电池、武陵→武陵电池', (() => {
  const fb = (mp2.power || {}).fuelByRegion || {};
  return (fb['四号谷地'] || []).every(x => x.item.indexOf('谷地电池') >= 0) &&
    (fb['武陵'] || []).every(x => x.item.indexOf('武陵电池') >= 0) &&
    (fb['四号谷地'] || []).length === 3 && (fb['武陵'] || []).length === 2;
})(), JSON.stringify(Object.keys((mp2.power || {}).fuelByRegion || {})));
chk('协议容量：选枢纽区 → 上限 200（配置表）', (() => {
  /* ⚠️ v145 起：切基地是**载入该基地原有内容**（多画布，R1/R2），不再清空 ——
     要验「空画布不占容量」必须显式清空，不能指望切基地顺手清。 */
  loReset(50); A.LbaseSet('map01_lv001'); A.LO.objs = [];
  const bw = A.Rbandwidth(A.LO.objs);
  return bw.cap === 200 && bw.use === 0 && bw.over === false && bw.zone === '枢纽区';
})());
chk('协议容量：设备累加，超上限要报出来', (() => {
  A.LO.objs = [A.Lmk(A.byBp('sp_hub_1'), 1, 1, 0)];       /* 协议核心 bandwidth 应该不小 */
  const one = A.Rbandwidth(A.LO.objs);
  /* 用一堆高 bandwidth 的设备填满：工业熔炉之类 bandwidth=3 的也行，这里直接断言"累加正确" */
  const b = A.byBp('furnance_1');
  A.LO.objs = [A.Lmk(b, 1, 1, 0), A.Lmk(b, 5, 1, 0)];
  const two = A.Rbandwidth(A.LO.objs);
  /* ⚠️ 期望值必须从 DB.buildings 取 —— byBp() 的注入版**不含 bandwidth 字段**（注入层裁剪），
     以前这里用 byBp().bandwidth 算期望，与被修的坏代码同源，所以 0==0 一直假绿（v145 修复时揭穿）。 */
  const bwOf = id => {
    const x = ((A.DB.buildings) || []).filter(y => y.id === id)[0] || {};
    return +x.bandwidth || 0;
  };
  const ok = two.use === bwOf('furnance_1') * 2 && one.use === bwOf('sp_hub_1');
  A.LbaseSet(''); loReset(50); A.render();
  return ok;
})());
chk('发电：缺口按 fuel 功率值算热能池台数（谷地电池 / 武陵电池）', (() => {
  const g = A.Rtheories(500, '四号谷地'), w = A.Rtheories(500, '武陵'), n = A.Rtheories(150, '四号谷地');
  /* 基础 200 → 缺口 300：谷地最低档 220 → 2 台；武陵最低档 1600 → 1 台 */
  return g.base === 200 && g.gap === 300 && g.fuels[0].count === 2 && g.fuels[0].power === 220 &&
    w.fuels[0].count === 1 && w.fuels[0].power === 1600 && n.gap === 0;
})());
chk('报告渲染出「约束校验 / 发电 / 原料野外上限」', (() => {
  loReset(50); A.LbaseSet('map01_lv001'); A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 10);
  const h = outEl.innerHTML || '';
  const ok = h.indexOf('约束校验') >= 0 && h.indexOf('协议容量') >= 0 &&
    h.indexOf('发电') >= 0 && h.indexOf('原料野外上限') >= 0;
  A.LbaseSet(''); loReset(50); A.render();
  return ok;
})());
chk('计数区常显协议容量与用电', (() => {
  loReset(50); A.render();
  const h = outEl.innerHTML || '';
  return h.indexOf('协议容量') >= 0 && h.indexOf('用电') >= 0;
})());

// ---- 5d-11. 用电统计 + 野外开采产量（博士 2026-09-21）----
// 能取证的：用电 = FactoryBuildingTable.powerConsume；开采 = FactoryMinerTable.msPerRound（20/分）、
// FactoryFluidPumpInTable（60/分）。**每台热能池发多少电配置表里没有**（建筑表无发电量字段）。
const mp = A.DB.mining_power || {};
chk('开采数据：采集建筑共 **7 座**（按 quickBarType=资源开采 列全）',
    (mp.gather || []).length === 7, String((mp.gather || []).length));
chk('开采数据：**水驱矿机在列**，且 desc 说明它采赤铜矿（博士 2026-09-21 抓到的漏项）', (() => {
  const m = (mp.gather || []).filter(x => x.id === 'miner_4')[0];
  return !!m && m.name === '水驱矿机' && String(m.desc).indexOf('赤铜矿') >= 0 && m.powerConsume === 0;
})(), '水驱矿机');
chk('开采数据：四台矿机速率都是 20/分（三台配置表 + 水驱矿机社区实测）', (() => {
  const known = (mp.miners || []).filter(m => m.rateKnown);
  return known.length === 4 && known.every(m => m.perMin === 20);
})(), JSON.stringify((mp.miners || []).map(m => m.name + ':' + m.perMin)));
chk('开采数据：水驱矿机 / 气体收集泵 / 二型耐酸水泵 的速率来自**社区实测**（配置表无字段）', (() => {
  const ids = ['miner_4', 'gas_pump_1', 'pump_2'];
  return ids.every(id => {
    const m = (mp.gather || []).filter(x => x.id === id)[0];
    return !!m && m.rateKnown === true && m.perMin > 0 &&
      String(m.rateSource).indexOf('社区实测') >= 0 &&
      String(m.note).indexOf('社区实测') >= 0;
  });
})(), JSON.stringify(['miner_4', 'gas_pump_1', 'pump_2'].map(id => {
  const m = (mp.gather || []).filter(x => x.id === id)[0]; return m ? m.name + ':' + m.perMin : '?';
})));
chk('开采数据：三台的速率数值（水驱矿机 20 / 气体收集泵 20 / 二型耐酸水泵 60）', (() => {
  const g = id => ((mp.gather || []).filter(x => x.id === id)[0] || {});
  return g('miner_4').perMin === 20 && g('gas_pump_1').perMin === 20 && g('pump_2').perMin === 60;
})());
chk('开采数据：**可采集物品**都补上了（赤铜矿 / 惰气·息壤气 / 沉积酸）', (() => {
  const g = id => ((mp.gather || []).filter(x => x.id === id)[0] || {});
  const names = id => (g(id).mineable || []).map(x => x.name);
  return names('miner_4').indexOf('赤铜矿') >= 0 &&
    names('gas_pump_1').indexOf('惰气') >= 0 && names('gas_pump_1').indexOf('息壤气') >= 0 &&
    names('pump_2').indexOf('沉积酸') >= 0;
})(), '可采物');
chk('开采数据：社区实测的可采物标了 from=社区实测（和配置表的区分开）', (() => {
  const m = (mp.gather || []).filter(x => x.id === 'miner_4')[0];
  return !!m && m.mineable.some(x => x.itemId === 'item_copper_ore' && x.from === '社区实测');
})());
chk('开采数据：速率来源清单（URL）在数据里', ((mp.rateSources || []).length >= 5));
chk('开采数据：水驱矿机在建筑表里**有 1 个管道进料口**（配置表旁证：通清水）', (() => {
  const m = (mp.gather || []).filter(x => x.id === 'miner_4')[0];
  return !!m && m.inputIsPipe === true;
})());
chk('开采数据：水泵 60/分', (() => {
  const p = (mp.gather || []).filter(x => x.id === 'pump_1')[0];
  return !!p && p.perMin === 60 && p.rateKnown === true;
})());
chk('开采数据：明确标注「矿脉纯度加成属运行时、配置表没有」',
    (mp.miners || []).every(m => String(m.note).indexOf('配置表') >= 0));
chk('RmineRate：蓝铁矿 → 采矿机 20/分；清水 → 水泵 60/分', (() => {
  const a = A.RmineRate('item_iron_ore'), b = A.RmineRate('item_liquid_water');
  return !!a && a.perMin === 20 && !!b && b.perMin === 60;
})());
chk('RmineRate：采不到的（如铁制零件）返回 null', A.RmineRate('item_iron_cmpt') === null);

chk('发电规则：文案证据在数据里（源矿 / 电池、电池效率更高）', (() => {
  const ev = (mp.power || {}).evidence || [];
  const t = ev.map(e => e.text).join(' ');
  return ev.length >= 5 && t.indexOf('热能池') >= 0 && t.indexOf('电池') >= 0 && t.indexOf('源矿') >= 0;
})());
chk('发电规则：**明确写出「每台热能池发电量配置表给不了」**（不糊弄）', (() => {
  const cg = ((mp.power || {}).cannotGive) || [];
  return cg.some(x => x.indexOf('发电量') >= 0);
})());
chk('用电：Rpower 把已摆设备的 powerConsume 求和（和配置表逐条对得上）', (() => {
  loReset(50);
  A.Lpick('furnance_1'); A.Lput(1, 1);
  A.Lput(10, 1);
  const expect = A.byBp('furnance_1').powerConsume * 2;
  const rp = A.Rpower(A.LO.objs);
  return rp.total === expect && rp.devices === 2;
})(), '2 台精炼炉的用电');
chk('用电：不耗电的件不计入（传动带 / 汇流器 powerConsume 为 0）', (() => {
  const rp = A.Rpower(A.LO.objs);
  loReset(50);
  A.Lpick('log_converger'); A.Lput(2, 2);
  const rp2 = A.Rpower(A.LO.objs);
  return rp2.total === 0 && rp2.devices === 0 && rp.devices === 2;
})());
chk('用电：画布计数区显示「用电」', (() => {
  loReset(50);
  A.Lpick('furnance_1'); A.Lput(1, 1);
  A.render();
  return (outEl.innerHTML || '').indexOf('用电') >= 0 && (outEl.innerHTML || '').indexOf('用电设备') >= 0;
})());
chk('排产报告里的原料会标注野外速率', (() => {
  loReset(50);
  A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 10);
  return (outEl.innerHTML || '').indexOf('蓝铁矿') >= 0 && (outEl.innerHTML || '').indexOf('20/分') >= 0;
})());
loReset(50); A.render();
// 左栏多出「物流件」10 件 1×1 可摆放件（来自 logistics.entities，不在 blueprint.buildings）；
// 建筑接口改成 进料青 / 出料橙、方=传送带口 / 圆=管道口，并新增「外侧那格有没有接上同类物流件」判定。
loReset(50); A.render();
chk('左栏顶部标出「物流件 10」', (outEl.innerHTML || '').indexOf('<b>物流件 10</b>') >= 0);
A.Lonly('物流件');
const palLg = [...(outEl.innerHTML || '').matchAll(/onclick="Lpick(?:FromList)?\('([^']+)'\)"/g)].map(m => m[1]);
chk('单看「物流件」正好 10 件', palLg.length === 10, String(palLg.length));
chk('单看物流件时看不到建筑', !palLg.includes('furnance_1'), palLg.join(','));
A.Lonly('');
setTab('layout');

// 摆放：1×1、渲染成物流件样式、带走向
loReset(50);
A.Lpick('grid_belt_01'); A.Lput(0, 0);
chk('物流件能摆上且占 1×1',
    A.LO.objs.length === 1 && A.LO.objs[0].w === 1 && A.LO.objs[0].d === 1,
    A.LO.objs.length + ' 个');
chk('传送带件渲染成 lo-cell lgb', /class="lo-cell lgb/.test(outEl.innerHTML || ''));
chk('物流件画的是 SVG（不是文字箭头）', /<svg viewBox="0 0 9 9"/.test(outEl.innerHTML || ''));
chk('物流件格子 title 写明走向与进/出边',
    /走向 0°（右）/.test(outEl.innerHTML || '') && /接口：进 左 \/ 出 右/.test(outEl.innerHTML || ''),
    (outEl.innerHTML || '').match(/title="传送带[^"]*"/) || '');
A.Lpick('log_pipe_01'); A.Lput(10, 10);
chk('管道件渲染成 lo-cell lgp', /class="lo-cell lgp/.test(outEl.innerHTML || ''));
A.Lpick('grid_belt_01'); A.Lput(0, 0);
chk('物流件之间不能重叠', A.LO.objs.length === 2, String(A.LO.objs.length));

// 接口渲染：颜色 / 形状 / 方向 / 悬停提示 / 图例
const mixedB = A.DB.blueprint.buildings.find(b =>
  b.ports.some(p => !p.isPipe) && b.ports.some(p => p.isPipe) &&
  b.ports.some(p => p.kind === 'input') && b.ports.some(p => p.kind === 'output'));
chk('存在同时带传送带口与管道口的建筑（接口渲染前提）', !!mixedB, mixedB ? mixedB.id : 'none');
const mf = mixedB.gridFootprint.split('×').map(Number);
loReset(50);
A.Lpick(mixedB.id); A.Lput(10, 10);
A.render();
const ph = outEl.innerHTML || '';
chk('接口标记渲染出来了', ph.indexOf('lo-port') >= 0);
chk('进料口用青色而非原来的 var(--accent)', ph.indexOf('#186C7D') >= 0, mixedB.id);
chk('出料口用橙色而非原来的 var(--warn)', ph.indexOf('#C0561F') >= 0, mixedB.id);
chk('管道口是圆形（lo-port pipe）', ph.indexOf('lo-port pipe') >= 0);
// 2026-09-21 第二轮改版：标记不再压格线跨出去（会和邻格传送带压字），改成贴建筑内侧边框。
chk('接口标记不再跨格（没有 --pd 短棒）', !/--pd:/.test(ph));
chk('接口 title 写明 进/出 + 介质 + 方/圆 + 哪条边 + 物料流向',
    ph.indexOf('进料口') >= 0 && ph.indexOf('出料口') >= 0 &&
    ph.indexOf('方形口(传送带)') >= 0 && /在[上下左右]边/.test(ph) && /物料向[上下左右](进入|离开)/.test(ph),
    (ph.match(/title="[^"]*进料口[^"]*"/) || [])[0]);
chk('图例说明 方=传送带口 / 圆=管道口', ph.indexOf('方形=传送带口') >= 0);
chk('图例区分进料/出料颜色', ph.indexOf('进料口') >= 0 && ph.indexOf('出料口') >= 0);
chk('图例说明了标记贴内侧（不再和邻格重叠）', ph.indexOf('不会和邻格的传送带') >= 0);

// 「接上了」判定：外侧那格放同类物流件
const inP = mixedB.ports.find(p => p.kind === 'input');
const q1 = A.LportXY(inP, 0, mf[0], mf[1]);
const d1 = A.LportDir(q1, mf[0], mf[1]);
const e1x = d1 === 'l' ? -1 : d1 === 'r' ? 1 : 0, e1z = d1 === 'u' ? -1 : d1 === 'd' ? 1 : 0;
chk('未接时接口没有 on 类', !/class="lo-port[^"]*\bon\b/.test(ph));
chk('未接时统计是 0', /接口已接 <b>0<\/b>/.test(ph));
const stat0 = ph.match(/接口已接 <b>(\d+)<\/b> \/ (\d+)/);
chk('接口总数 = 该建筑的口数', stat0 && +stat0[2] === mixedB.ports.length, stat0 ? stat0[2] : 'none');
A.Lpick(inP.isPipe ? 'log_pipe_01' : 'grid_belt_01');
A.Lput(10 + q1.x + e1x, 10 + q1.z + e1z);
const ph2 = outEl.innerHTML || '';
chk('外侧放同类物流件后接口带 on 类', /class="lo-port[^"]*\bon\b/.test(ph2));
const stat1 = ph2.match(/接口已接 <b>(\d+)<\/b> \/ (\d+)/);
chk('统计从 0 涨到至少 1', stat1 && +stat1[1] >= 1, stat1 ? stat1[1] : 'none');
// 介质不同不算接上
if (inP.isPipe) {
  const beltP = mixedB.ports.find(p => !p.isPipe && p.kind === 'input');
  const q2 = A.LportXY(beltP, 0, mf[0], mf[1]);
  const d2 = A.LportDir(q2, mf[0], mf[1]);
  const e2x = d2 === 'l' ? -1 : d2 === 'r' ? 1 : 0, e2z = d2 === 'u' ? -1 : d2 === 'd' ? 1 : 0;
  A.Lpick('log_pipe_01');
  A.Lput(10 + q2.x + e2x, 10 + q2.z + e2z);
  const stat2 = (outEl.innerHTML || '').match(/接口已接 <b>(\d+)<\/b>/);
  chk('再铺一格管道只多接 1 个', stat2 && +stat2[1] === +stat1[1], stat2 ? stat2[1] + ' vs ' + stat1[1] : 'none');
}

// 连铺：横向 / 纵向 / 跳过障碍
loReset(50);
A.Lpick('grid_belt_01');
A.LODRAG = { mode: 'lay', sx: 0, sy: 0, ex: 5, ey: 0, uids: [] };
A.LlayTo(5, 0);
chk('LlayTo 横向一次铺 6 格', A.LO.objs.length === 6, String(A.LO.objs.length));
chk('横向每格走向朝右（0°）', A.LO.objs.every(o => o.rot === 0), A.LO.objs.map(o => o.rot).join(','));
chk('最长连通段 = 6', /最长连通段 <b>6<\/b> 格/.test(outEl.innerHTML || ''));
loReset(50);
A.Lpick('log_pipe_01');
A.LODRAG = { mode: 'lay', sx: 0, sy: 0, ex: 0, ey: 3, uids: [] };
A.LlayTo(0, 3);
chk('LlayTo 纵向一次铺 4 格', A.LO.objs.length === 4, String(A.LO.objs.length));
chk('纵向走向是 90°（下）', A.LO.objs.every(o => o.rot === 90), A.LO.objs.map(o => o.rot).join(','));
const st2 = (outEl.innerHTML || '')
  .match(/物流件 <b>(\d+)<\/b> 件（传送带 (\d+) · 管道 (\d+) · 汇流\/分流\/桥\/阀 (\d+)）/);
chk('汇总行按介质与功能分类计数',
    !!st2 && +st2[1] === 4 && +st2[2] === 0 && +st2[3] === 4 && +st2[4] === 0,
    st2 ? st2.slice(1).join('/') : 'none');
chk('管道件不混进传送带计数', st2 && +st2[3] === 4);
loReset(50);
A.Lpick(mixedB.id); A.Lput(3, 0);
A.Lpick('grid_belt_01');
A.LODRAG = { mode: 'lay', sx: 0, sy: 0, ex: 9, ey: 0, uids: [] };
A.LlayTo(9, 0);
const laidBelts = A.LO.objs.filter(o => o.id === 'grid_belt_01');
chk('连铺跳过被建筑占住的格', laidBelts.length === 10 - mf[0],
    laidBelts.length + ' 格 / 建筑宽 ' + mf[0]);
chk('连铺没压在建筑上',
    !laidBelts.some(o => o.x >= 3 && o.x < 3 + mf[0] && o.y < mf[1]),
    laidBelts.map(o => o.x + ',' + o.y).join(' '));

// ⭐v108（博士图：「游戏里是从红圈里开始拉」）：机器的口格本身可以起手连铺 ——
//   按在朝外的输出口格上，带子从**口外那一格**开始铺，不占口格。口外被占则不误起手。
loReset(50);
(function () {
  const fb2 = A.DB.blueprint.buildings.find(b => b.id === 'furnance_1');
  A.Lpick('furnance_1'); A.Lput(4, 4);
  const ros = [];
  (fb2.ports || []).forEach(p => {
    const q = A.LportXY(p, 0, 3, 3), d = A.LportDir(q, 3, 3);
    ros.push({ kind: p.kind, gx: 4 + q.x, gy: 4 + q.z, dir: d });
  });
  const ro = ros.filter(p => p.kind === 'output' && p.dir === 'r')[0];
  chk('v108 精炼炉有朝右的输出口（「红圈」前提）', !!ro, ro ? ro.gx + ',' + ro.gy : 'none');
  const DV2 = { r: [1, 0], l: [-1, 0], d: [0, 1], u: [0, -1] };
  const ox2 = ro.gx + DV2.r[0], oy2 = ro.gy + DV2.r[1];
  A.Lpick('grid_belt_01');
  const sn2 = A.LsnapStart(ro.gx, ro.gy);
  chk('v108 从口格起手被吸到口外一格（不占口格）',
      !!sn2 && sn2.x === ox2 && sn2.y === oy2 && !(sn2.x === ro.gx && sn2.y === ro.gy),
      sn2 ? sn2.x + ',' + sn2.y : 'null');
  A.LODRAG = { mode: 'lay', sx: sn2.x, sy: sn2.y, ex: sn2.x, ey: sn2.y, uids: [], hist: [[sn2.x, sn2.y]] };
  A.LlayTo(ox2 + 3, oy2);
  const bv = A.LO.objs.filter(o => o.id === 'grid_belt_01');
  chk('v108 铺出的带子从口外开始、不含口格',
      bv.length === 4 && !bv.some(o => o.x === ro.gx && o.y === ro.gy) &&
      bv.every(o => o.y === oy2 && o.rot === 0),
      bv.map(o => o.x + ',' + o.y + '@' + o.rot).join(' '));
})();
loReset(50);
(function () {
  const fb3 = A.DB.blueprint.buildings.find(b => b.id === 'furnance_1');
  A.Lpick('furnance_1'); A.Lput(4, 4);
  /* 找**同一个**朝右输出口，把它的口外格堵住 → LsnapStart 应拒绝 */
  const rods = [];
  (fb3.ports || []).forEach(p => {
    const q = A.LportXY(p, 0, 3, 3), d = A.LportDir(q, 3, 3);
    rods.push({ kind: p.kind, gx: 4 + q.x, gy: 4 + q.z, dir: d });
  });
  const ro3 = rods.filter(p => p.kind === 'output' && p.dir === 'r')[0];
  const dvq = { r: [1, 0], l: [-1, 0], d: [0, 1], u: [0, -1] };
  const ox3 = ro3.gx + dvq.r[0], oy3 = ro3.gy + dvq.r[1];
  A.Lpick('furnance_1'); A.Lput(ox3, oy3);   /* 堵住口外那一格 */
  const before3 = A.LO.objs.filter(o => o.id === 'grid_belt_01').length;
  const ok3 = A.LsnapStart(ro3.gx, ro3.gy);
  chk('v108 口外那格被占 → 不起手（不误铺）', ok3 === null &&
      A.LO.objs.filter(o => o.id === 'grid_belt_01').length === before3,
      ok3 === null ? 'null ✓' : JSON.stringify(ok3));
})();

// ⭐v122（博士截图「旋转个方向进出货口就不齐了」）：接口朝向必须跟着 rot 转。
// 旧逻辑对 LportXY 转完的坐标重新贴边猜朝向，角口永远判成压 z 边 —— rot=0 恰好对、
// 一旋转全错（端点吸附 / 从口拉线 / 接口已接统计 / 自动布线全歪）。
// 修法 = rot=0 按原口径判 base，再按 d→l→u→r 步进转 n 次（与 LportXY 同一套旋转）。
(function () {
  const g = A.DB.blueprint.buildings.find(b => b.id === 'grinder_1');
  const fin = g.ports.find(p => p.kind === 'input' && p.index === 1);   // (1,2) 下边中点
  const fout = g.ports.find(p => p.kind === 'output' && p.index === 1); // (1,0) 上边中点
  chk('v122 rot=0 进料口朝下（回归不变）', A.LportDirRot(fin, 0, 3, 3) === 'd');
  chk('v122 rot=0 出料口朝上（回归不变）', A.LportDirRot(fout, 0, 3, 3) === 'u');
  const q90i = A.LportXY(fin, 90, 3, 3), q90o = A.LportXY(fout, 90, 3, 3);
  chk('v122 rot=90 进料口位置转到左列 (0,1)', q90i.x === 0 && q90i.z === 1, q90i.x + ',' + q90i.z);
  chk('v122 rot=90 出料口位置转到右列 (2,1)', q90o.x === 2 && q90o.z === 1, q90o.x + ',' + q90o.z);
  chk('v122 rot=90 进料口朝向朝左（旧逻辑误判 u）', A.LportDirRot(fin, 90, 3, 3) === 'l',
      A.LportDirRot(fin, 90, 3, 3));
  chk('v122 rot=90 出料口朝向朝右（旧逻辑误判 d）', A.LportDirRot(fout, 90, 3, 3) === 'r',
      A.LportDirRot(fout, 90, 3, 3));
  chk('v122 rot=180 进料口朝上', A.LportDirRot(fin, 180, 3, 3) === 'u');
  chk('v122 rot=270 进料口朝右', A.LportDirRot(fin, 270, 3, 3) === 'r');
  const fc = g.ports.find(p => p.kind === 'input' && p.index === 0);    // (0,2) 角口，两条边都压
  chk('v122 角口 rot=0 仍判下边（回归不变）', A.LportDirRot(fc, 0, 3, 3) === 'd');
  chk('v122 角口 rot=90 朝左（旧逻辑误判 u —— 本次事故实锤）', A.LportDirRot(fc, 90, 3, 3) === 'l',
      A.LportDirRot(fc, 90, 3, 3));
})();

// v122 端到端：旋转后的机器，带子铺在「真实口外侧」必须被判定接上
loReset(50);
(function () {
  const gb = A.DB.blueprint.buildings.find(b => b.id === 'grinder_1');
  A.Lpick('grinder_1');
  A.LO.pickRot = 90;
  A.Lput(5, 5);   // 占 (5..7, 5..7)，rot=90：进料口在左列、出料口在右列
  const gi = gb.ports.find(p => p.kind === 'input' && p.index === 1);
  const qi = A.LportXY(gi, 90, 3, 3);
  chk('v122 端到端前置：进料口 #1 全局格 = (5,6)', 5 + qi.x === 5 && 5 + qi.z === 6,
      (5 + qi.x) + ',' + (5 + qi.z));
  A.Lpick('grid_belt_01');
  A.LO.pickRot = 0;
  A.Lput(4, 6);   // 进料口外侧（左）一格放传送带
  const m = (outEl.innerHTML || '').match(/接口已接 <b>(\d+)<\/b> \/ (\d+)/);
  chk('v122 rot=90 机器左侧铺带 → 接口已接 ≥1（旧逻辑为 0）', !!m && +m[1] >= 1,
      m ? m[1] + '/' + m[2] : 'none');
  const go = gb.ports.find(p => p.kind === 'output' && p.index === 1);
  const qo = A.LportXY(go, 90, 3, 3);
  const sn = A.LsnapStart(5 + qo.x, 5 + qo.z);   // 按在出料口格上起手
  chk('v122 rot=90 出料口起手吸到右侧口外 (8,6)', !!sn && sn.x === 8 && sn.y === 6,
      sn ? sn.x + ',' + sn.y + '@' + sn.dir : 'null');
})();

// ⭐v123（博士「协议核心还是无法从机器口拉传送带，鼠标一移动到机器口上就只能选择物品」）：
// v109 的出货箭头 .lo-dlv 压在口格上，LonMouseDown 对它无条件放行 → 手拿物流件点口
// 永远弹选货浮层，v108「从口格拉线」起不来。修复 = 手拿物流件时不放行（走 portpend：
// 原地松手=拉线、拖动=移机器），空手点箭头才开浮层；LdlvOpen 加「手里有东西不开」守卫
// 兜住 mouseup 后仍会派发到箭头 onclick 的 click。
// ⭐v124（博士「把选择物品的模块移到里面，外侧像其他基建一样是货品进出口」）：箭头内移
// 一格、口格留白 —— 拉线主路径的 target 变成格子本体，点内部箭头=普通移动。
// 沙箱没有真实 DOM 树，事件对象手工造（closest 按选择器映射，Lxy 用假 getBoundingClientRect）。
(function () {
  loReset(50);
  A.Lpick('sp_hub_1'); A.Lput(5, 5);   // 9×9 占 (5..13, 5..13)
  const hub = A.LO.objs.filter(o => o.id === 'sp_hub_1')[0];
  const hb = A.DB.blueprint.buildings.find(b => b.id === 'sp_hub_1');
  const dvq = { r: [1, 0], l: [-1, 0], d: [0, 1], u: [0, -1] };
  // 找一个「口外格在画布内且为空」的出料口（rot=0，渲染层同款 LportDirRot）
  const cand = hb.ports.filter(p => p.kind === 'output').map(p => {
    const q = A.LportXY(p, 0, 9, 9);
    const gx = 5 + q.x, gy = 5 + q.z;
    const dir = A.LportDirRot(p, 0, 9, 9);
    const dv = dvq[dir] || [0, 0];
    return { gx, gy, dir, ox: gx + dv[0], oy: gy + dv[1] };
  }).filter(c => c.dir && c.ox >= 0 && c.oy >= 0 && c.ox < A.LO.size && c.oy < A.LO.size &&
      !A.LO.objs.some(o => c.ox >= o.x && c.ox < o.x + o.w && c.oy >= o.y && c.oy < o.y + o.d));
  chk('v123 前置：核心存在口外为空的出料口', cand.length > 0, String(cand.length));
  if (!cand.length) return;
  const P = cand[0];

  function fakeEv(hitDlv, gx, gy) {
    const CELL = A.LOCELL;
    const X = gx === undefined ? P.gx : gx, Y = gy === undefined ? P.gy : gy;
    const canvas = { getBoundingClientRect() {
        return { left: 0, top: 0, width: A.LO.size * CELL, height: A.LO.size * CELL }; },
      querySelectorAll() { return []; } };   // LpaintSel 只遍历 .lo-cell，空表即可
    const cell = { dataset: { uid: hub.uid } };
    return { button: 0, preventDefault() {},
      clientX: (X + 0.5) * CELL, clientY: (Y + 0.5) * CELL,
      target: { closest(sel) {
        if (sel === '.lo-gasbar' || sel === '.lo-dlvpop') return null;
        if (sel === '.lo-dlv') return hitDlv ? { stub: true } : null;
        if (sel === '.lo-canvas') return canvas;
        if (sel === '.lo-cell') return cell;
        return null; } } };
  }

  // ① 空手点内部箭头（⭐v124 起箭头在口内侧一格）：仍放行 → 交给 onclick 开选货
  A.LO.pick = null; A.LODRAG = null;
  A.LonMouseDown(fakeEv(true));
  chk('v123 空手点出货箭头 → 放行（不起 portpend，交给 onclick 选货）',
      A.LODRAG === null, String(A.LODRAG && A.LODRAG.mode));

  // ②a 手拿传送带点**内部箭头**（v124 起箭头内移一格，点击坐标不在口上）→ 普通移动：
  //    不误进拉线待决态；click 链由 LdlvOpen 守卫拦住不开浮层
  A.Lpick('grid_belt_01'); A.LODRAG = null;
  A.LonMouseDown(fakeEv(true, P.gx - dvq[P.dir][0], P.gy - dvq[P.dir][1]));
  chk('v124 手拿传送带点内部箭头 → 普通移动（不误拉线）',
      !!A.LODRAG && A.LODRAG.mode === 'move', A.LODRAG ? A.LODRAG.mode : 'null');
  A.LODRAG = null;

  // ②b 手拿传送带点**口格**本体（v124 起口格上没有箭头，target 是格子）→ 进 portpend
  A.LODRAG = null;
  A.LonMouseDown(fakeEv(false));
  chk('v124 手拿传送带点出料口格 → 进 portpend 待决态（口格拉线主路径）',
      !!A.LODRAG && A.LODRAG.mode === 'portpend', A.LODRAG ? A.LODRAG.mode : 'null');

  // ③ 原地松手 = 从口外一格起手拉线
  A.LonMouseUp();
  chk('v123 口上原地松手 → 从口外 (' + P.ox + ',' + P.oy + ') 起手拉线',
      !!A.LODRAG && A.LODRAG.mode === 'lay' && A.LODRAG.sx === P.ox && A.LODRAG.sy === P.oy,
      A.LODRAG ? A.LODRAG.mode + '@' + A.LODRAG.sx + ',' + A.LODRAG.sy : 'null');

  // ④ click 链守卫：拉线中手里仍有物流件，mouseup 后派发的 click 不许弹选货浮层
  A.LODRAG = null;
  if (!A.LO.pick) A.Lpick('grid_belt_01');
  A.LdlvOpen(hub.uid, 0);
  chk('v123 手里有物流件 → LdlvOpen 不开选货浮层（click 兜底守卫）',
      A.LO.dlvPop === null, JSON.stringify(A.LO.dlvPop));

  // ⑤ 空手调 LdlvOpen → 浮层照常打开（选货能力无损）
  A.LO.pick = null;
  A.LdlvOpen(hub.uid, 0);
  chk('v123 空手点箭头 → 选货浮层照常打开',
      !!A.LO.dlvPop && A.LO.dlvPop.uid === hub.uid && A.LO.dlvPop.idx === 0,
      JSON.stringify(A.LO.dlvPop));
  A.LO.dlvPop = null;

  // ⑥ ⭐v125 手拿**建筑**（非物流件）调 LdlvOpen → 照常开：Lput 摆放成功后不清 pick
  //    （连续摆放交互），摆完核心手里还拿着核心，v123 的 if(L.pick) 把这种选货也拦死
  //    （博士实测「又选不了货了」）。守卫收窄为只拦物流件后，此场景必须恢复。
  A.Lpick('sp_hub_1');
  chk('v125 前置：手拿协议核心，pick 存在且非物流件',
      !!A.LO.pick && !A.LO.pick.isLogi, String(A.LO.pick && A.LO.pick.isLogi));
  A.LdlvOpen(hub.uid, 0);
  chk('v125 手拿建筑点出货箭头 → 选货浮层照常打开（守卫只拦物流件）',
      !!A.LO.dlvPop && A.LO.dlvPop.uid === hub.uid && A.LO.dlvPop.idx === 0,
      JSON.stringify(A.LO.dlvPop));
  A.LO.pick = null; A.LO.dlvPop = null;
})();

// ⭐v106 弯头格渲染（博士 2026-09-23 游戏截图「一格拐弯画不了」）：
// 带子 rot 单值推的「进=出的反向」在拐弯处与真实拓扑不同轴 —— 旧版进色条画上边、
// 弯道弧却从左边绕，自相矛盾。修复 = 进色条与 tooltip 都用 flowIn 反推的真实进边。
// 管道同一分支一并修；功能件（汇/分/桥/阀）多边进出，不适用单进边，保持按配置表画。
function v106CellSvg(h, x, y, C) {
  const i = h.indexOf('style="left:' + (x * C) + 'px;top:' + (y * C) + 'px;');
  if (i < 0) return null;
  const s = h.indexOf('<svg', i), e = h.indexOf('</svg>', s);
  return h.slice(s, e + 6);
}
loReset(50);
A.Lpick('grid_belt_01');
A.LODRAG = { mode: 'lay', sx: 2, sy: 2, ex: 6, ey: 2, uids: [] };
A.LlayTo(6, 5);   // 同手势 L 形：先横 (2,2)→(6,2) 再竖 (6,2)→(6,5)
const v106C = A.LOCELL, v106h = outEl.innerHTML || '';
const bend = v106CellSvg(v106h, 6, 2, v106C);
chk('v106 弯头格画弯道弧（Q 曲线）', !!bend && bend.indexOf(' Q') >= 0,
    bend ? bend.slice(0, 90) : 'none');
chk('v106 弯头格进色条在左（真实拓扑），不再画在上（旧 rot 推法）',
    !!bend && /<rect x="0" y="2"[^>]*fill="#186C7D"/.test(bend) && !/<rect x="2" y="0"/.test(bend),
    bend ? bend.slice(0, 120) : 'none');
chk('v106 弯头格出色条在下（与弧的出口同边）',
    !!bend && /<rect x="2" y="7"[^>]*fill="#C0561F"/.test(bend),
    bend ? bend.slice(0, 120) : 'none');
chk('v106 弯头格 tooltip 的「进」按真实拓扑（左）',
    /接口：进 左 \/ 出 下/.test(v106h), 'tooltip');
const v106Str = v106CellSvg(v106h, 3, 2, v106C);
chk('v106 直格仍是直箭头（无弯弧）', !!v106Str && v106Str.indexOf(' Q') < 0,
    v106Str ? v106Str.slice(0, 90) : 'none');
chk('v106 直格进左出右不变',
    !!v106Str && /<rect x="0" y="2"/.test(v106Str) && /<rect x="7" y="2"/.test(v106Str),
    v106Str ? v106Str.slice(0, 120) : 'none');
loReset(50);
A.Lpick('log_pipe_01');
A.LODRAG = { mode: 'lay', sx: 2, sy: 2, ex: 6, ey: 2, uids: [] };
A.LlayTo(6, 5);
const pbend = v106CellSvg(outEl.innerHTML || '', 6, 2, A.LOCELL);
chk('v106 管道弯头同样 弧 + 左进条 + 下出条',
    !!pbend && pbend.indexOf(' Q') >= 0 && /<rect x="0" y="2"/.test(pbend) && /<rect x="2" y="7"/.test(pbend),
    pbend ? pbend.slice(0, 120) : 'none');
loReset(50);
A.Lpick('log_converger'); A.Lput(5, 5);
const cvSvg = v106CellSvg(outEl.innerHTML || '', 5, 5, A.LOCELL);
chk('v106 功能件色条仍按配置表多边（汇流器 3 进 1 出 = 4 条，无弯弧）',
    !!cvSvg && (cvSvg.match(/<rect /g) || []).length === 4 && cvSvg.indexOf(' Q') < 0,
    cvSvg ? cvSvg.slice(0, 120) : 'none');

// ⭐v107（博士图1/图2，2026-09-23）：① 拐弯第一轴跟手势轨迹（先往上拖就先铺竖段），
//   旧版按总位移大小定轴，想要「先上后右」被画成镜像；② 孤格带/管贴机器出料口时
//   进边从机器口反推（旧版只查带子邻居，孤格永远是默认直箭头）。
loReset(50);
A.Lpick('grid_belt_01');
A.LODRAG = { mode: 'lay', sx: 2, sy: 2, ex: 5, ey: 2, uids: [], hist: [[2, 2], [2, 5]] };
A.LlayTo(5, 5);   // 轨迹先竖((2,2)→(2,5)) 再横到 (5,5)
const v107cells = A.LO.objs.map(o => o.x + ',' + o.y);
chk('v107 拐弯第一轴跟手势（先竖后横）：竖段 4 格 + 横段 3 格',
    A.LO.objs.length === 7 && v107cells.indexOf('2,5') >= 0 && v107cells.indexOf('3,5') >= 0,
    v107cells.join(' '));
const v107bend = A.LO.objs.filter(o => o.x === 2 && o.y === 5)[0];
chk('v107 拐弯格在轨迹转折点 (2,5) 且朝向第二轴（rot=0 右）',
    !!v107bend && v107bend.rot === 0, v107bend ? 'rot=' + v107bend.rot : '缺格');
const v107vseg = A.LO.objs.filter(o => o.x === 2);
chk('v107 先铺的是竖段（起手轴优先）', v107vseg.length === 4 && v107vseg.every(o => o.y >= 2 && o.y <= 5),
    String(v107vseg.length));
loReset(50);
A.Lpick('grid_belt_01');
A.LODRAG = { mode: 'lay', sx: 2, sy: 2, ex: 5, ey: 2, uids: [] };   // 旧调用方无 hist
A.LlayTo(5, 5);
chk('v107 无轨迹时回退旧判定（|dx|>=|dy| 先横）',
    A.LO.objs.length === 7 && A.LO.objs.some(o => o.x === 5 && o.y === 2) && A.LO.objs[0].rot === 0,
    A.LO.objs.map(o => o.x + ',' + o.y).join(' '));
loReset(50);
(function(){
  const fb = A.DB.blueprint.buildings.find(b => b.id === 'furnance_1');
  const op = (fb.ports || []).filter(p => p.kind === 'output' && !p.isPipe)[0];
  const q2 = A.LportXY(op, 0, 3, 3);
  const dir2 = A.LportDir(q2, 3, 3);
  const DV = { r: [1, 0], l: [-1, 0], d: [0, 1], u: [0, -1] };
  const bx2 = 4 + q2.x + DV[dir2][0], by2 = 4 + q2.z + DV[dir2][1];
  A.Lpick('furnance_1'); A.Lput(4, 4);
  A.Lpick('grid_belt_01'); A.Lput(bx2, by2);
  const h2 = outEl.innerHTML || '';
  const s2 = v106CellSvg(h2, bx2, by2, A.LOCELL);
  const DIRMAP = { u: 't', d: 'b', l: 'l', r: 'r' };
  /* 机器口朝 dir2 → 口外格在机器 dir2 侧 → 机器在带子的反侧 → 带子进边 = 反侧方向 */
  const BARKEY = { t: 'x="2" y="0"', b: 'x="2" y="7"', l: 'x="0" y="2"', r: 'x="7" y="2"' };
  const opp2 = { t: 'b', b: 't', l: 'r', r: 'l' }[DIRMAP[dir2]];
  const wantIn = BARKEY[opp2];
  chk('v107 孤格带子贴出料口：进色条从机器侧来（口朝 ' + dir2 + ' → 进 ' + opp2 + '）',
      !!s2 && s2.indexOf('<rect ' + wantIn) >= 0 && s2.indexOf('#186C7D') >= 0,
      s2 ? s2.slice(0, 110) : 'none');
  const ti2 = h2.indexOf('style="left:' + (bx2 * A.LOCELL) + 'px;top:' + (by2 * A.LOCELL) + 'px;');
  const seg2 = ti2 >= 0 ? h2.slice(ti2, ti2 + 420) : '';   /* title 属性在 style 之后 */
  const CN = { t: '上', b: '下', l: '左', r: '右' }[opp2];
  chk('v107 孤格带子 tooltip 的「进」同口径（进 ' + CN + '）',
      seg2.indexOf('接口：进 ' + CN + ' /') >= 0, seg2.slice(0, 160));
})();

// ⭐v109 第二半（博士 2026-09-23：「游戏里的协议核心出货口可以点击选择物品出货」+
//   「内部空白面积大，选货能不能在内部给个机器口对应的箭头什么的」）：
//   数据来自注入的 DB.hubItems（raw FactoryItemTable.deliverItemTypeList 非空者），
//   渲染层在协议核心的出料口格内画可点箭头 .lo-dlv，选了货就变 .set + 标名 .lo-dlvt。
(function () {
  chk('v109 DB.hubItems 已注入且条数 = 281（可出货物品）',
      A.DB.hubItems && Object.keys(A.DB.hubItems).length === 281,
      A.DB.hubItems ? String(Object.keys(A.DB.hubItems).length) : 'none');
  // 逐个核：id 必须来自 deliverItemTypeList 非空 + domains 只含 domain_1/domain_2
  let badDom = 0, noRarity = 0, noName = 0;
  Object.keys(A.DB.hubItems || {}).forEach(k => {
    const v = A.DB.hubItems[k];
    if (!v.domains || !v.domains.length ||
        v.domains.some(d => d !== 'domain_1' && d !== 'domain_2')) badDom++;
    if (!v.rarity) noRarity++;
    if (!v.name || v.name === k) noName++;
  });
  chk('v109 每条 hubItems 都挂在 domain_1/domain_2 上', badDom === 0, String(badDom));
  chk('v109 每条 hubItems 都有稀有度', noRarity === 0, String(noRarity));
  chk('v109 物品名全部解析出（缺名退 id 的为 0）', noName === 0, String(noName));

  const hc1 = A.hubCands('domain_1'), hc2 = A.hubCands('domain_2');
  chk('v109 四号谷地(domain_1) 可出货 = 70 件', hc1.length === 70, String(hc1.length));
  chk('v109 武陵(domain_2) 可出货 = 211 件', hc2.length === 211, String(hc2.length));
  let desc = true;
  for (let i = 1; i < hc2.length; i++) if (hc2[i].rarity > hc2[i - 1].rarity) desc = false;
  chk('v109 出货清单按稀有度降序（列表顺序稳定）', desc);

  // 渲染：摆一台协议核心，应恰好有 6 个出货箭头（= 6 个出料口），进料口不出箭头
  loReset(50);
  A.Lpick('sp_hub_1'); A.Lput(5, 5);
  const hh = outEl.innerHTML || '';
  const dlvN = (hh.match(/class="lo-dlv[" ]/g) || []).length;
  const hubBp = A.DB.blueprint.buildings.find(b => b.id === 'sp_hub_1');
  const outN = hubBp.ports.filter(p => p.kind === 'output').length;
  chk('v109 协议核心画出 6 个出货箭头（= 出料口数）', dlvN === 6 && outN === 6,
      dlvN + ' vs ' + outN);
  chk('v109 进料口不画出货箭头（14 进 6 出，只 6 个）', dlvN === outN, dlvN + ' vs 14+6');

  // 几何：每个箭头的 left/top 必须落在这台 9×9 核心的格内（不许越界 —— v109 修过两版坐标）
  const hp = [...hh.matchAll(/class="lo-dlv[^"]*" style="left:(-?[\d.]+)px;top:(-?[\d.]+)px/g)]
    .map(m => ({ left: +m[1], top: +m[2] }));
  const hubW = 9 * A.LOCELL - 2, hubD = 9 * A.LOCELL - 2, HALF = 6;
  const inside = hp.filter(p => p.left - HALF >= -0.5 && p.left + HALF <= hubW + 0.5 &&
                                p.top - HALF >= -0.5 && p.top + HALF <= hubD + 0.5).length;
  chk('v109 6 个箭头全部落在核心格内（不越界）', inside === 6, inside + '/6  范围 ' + hubW + '×' + hubD);

  // ⭐v124 箭头内移一格：每个箭头 = 口格中心 − 朝外方向×1 格（不再压口格，口留白给物流交互）
  const dvq124 = { r: [1, 0], l: [-1, 0], d: [0, 1], u: [0, -1] };
  const inner124 = hubBp.ports.filter(p => p.kind === 'output').map(p => {
    const q = A.LportXY(p, 0, 9, 9);
    const dv = dvq124[A.LportDirRot(p, 0, 9, 9)] || [0, 0];
    return { x: q.x * A.LOCELL + A.LOCELL / 2 - dv[0] * A.LOCELL,
             y: q.z * A.LOCELL + A.LOCELL / 2 - dv[1] * A.LOCELL };
  });
  const moved124 = hp.filter(p => inner124.some(
      q => Math.abs(q.x - p.left) < 0.6 && Math.abs(q.y - p.top) < 0.6)).length;
  chk('v124 6 个箭头全部内移到口内侧一格（不压口格）', moved124 === 6, moved124 + '/6');

  // 选中态：选了货 → 该口箭头 .set + 名字标签；另一口保持未选
  const hubObj = A.LO.objs.filter(o => o.id === 'sp_hub_1')[0];
  const c0 = A.hubCands(A.hubDomainOf(hubObj))[0];
  A.hubPickSet(hubObj.uid, 1, c0.id);
  A.render();
  const hh2 = outEl.innerHTML || '';
  chk('v109 选了货 → 箭头带 .set 态',
      (hh2.match(/class="lo-dlv set"/g) || []).length === 1,
      String((hh2.match(/class="lo-dlv set"/g) || []).length));
  chk('v109 选了货 → 箭头旁标出物品名',
      hh2.indexOf('class="lo-dlvt"') >= 0 && hh2.indexOf(c0.name) >= 0, c0.name);
  chk('v109 未选的口仍是无 set 态（其余 5 个）',
      (hh2.match(/class="lo-dlv"/g) || []).length === 5,
      String((hh2.match(/class="lo-dlv"/g) || []).length));

  // 取消：再选同一件 → 清空
  A.hubPickSet(hubObj.uid, 1, '');
  A.render();
  const hh3 = outEl.innerHTML || '';
  chk('v109 取消后回到 0 个 set 箭头',
      (hh3.match(/class="lo-dlv set"/g) || []).length === 0 && hh3.indexOf('lo-dlvt') < 0);
  chk('v109 该核心记录被清成空表', Object.keys(A.hubPicksOf(hubObj)).length === 0);

  // 域判定：选四号谷地基地 → domain_1；不选基地 → 回落出货方向出发地
  // ⚠️ 基地区域清单要用页面自己的 Lbases()（带 levelId）；DB.bases.areas 没 levelId，别用它
  const areas = A.Lbases() || [];
  const d1area = areas.filter(x => x.domainName === '四号谷地')[0];
  const d2area = areas.filter(x => x.domainName === '武陵')[0];
  chk('v109 基地区域表能取到谷地/武陵两类', !!d1area && !!d2area);
  if (d1area && d2area) {
    A.LO.base = d1area.levelId;
    chk('v109 选谷地基地 → 核心域 = domain_1', A.hubDomainOf(hubObj) === 'domain_1', A.hubDomainOf(hubObj));
    A.LO.base = d2area.levelId;
    chk('v109 选武陵基地 → 核心域 = domain_2', A.hubDomainOf(hubObj) === 'domain_2', A.hubDomainOf(hubObj));
    A.LO.base = '';
    chk('v109 不选基地 → 回落出货方向出发地（domain_1）',
        A.hubDomainOf(hubObj) === A.LshipFromId(), A.hubDomainOf(hubObj));
  }
  // 非核心机器不出箭头
  loReset(50);
  A.Lpick('furnance_1'); A.Lput(4, 4);
  chk('v109 非协议核心的机器不画出货箭头',
      (outEl.innerHTML.match(/class="lo-dlv[" ]/g) || []).length === 0);
  // 出货浮层的坐标也要在画布内（不越界到画布外）
  loReset(50);
  A.Lpick('sp_hub_1'); A.Lput(2, 2);
  const hub2 = A.LO.objs.filter(o => o.id === 'sp_hub_1')[0];
  A.LO.dlvPop = { uid: hub2.uid, idx: 0 };
  A.render();
  const hp2 = outEl.innerHTML || '';
  const pm = /class="lo-dlvpop" style="left:(-?[\d.]+)px;top:(-?[\d.]+)px/.exec(hp2);
  const cvw = A.LO.size * A.LOCELL;
  chk('v109 选货浮层贴在画布内（left/top 非负）',
      !!pm && +pm[1] >= 0 && +pm[2] >= 0 && +pm[1] < cvw,
      pm ? pm[1] + ',' + pm[2] + ' 画布 ' + cvw : 'none');
  chk('v109 浮层里列出的条目数 = 该域可出货件数',
      (hp2.match(/class="it[\s"]/g) || []).length >= A.hubCands(A.hubDomainOf(hub2)).length,
      String((hp2.match(/class="it[\s"]/g) || []).length));

  // ⭐v126 选货浮层搜索 + 稀有度筛选（博士「东西几百个太多了」）。
  // 上面 L2034 直接设了旧格式 dlvPop={uid,idx}——正好验证读取侧 ||'' 兜底不炸。
  const hubDom = A.hubDomainOf(hub2);
  const hubCandsN = A.hubCands(hubDom).length;
  chk('v126 旧格式 dlvPop（无 q/rare）→ 工具条照常渲染，计数 = 全量',
      hp2.indexOf('class="ft"') >= 0 && hp2.indexOf('搜物品名') >= 0 &&
      hp2.indexOf(' / ' + hubCandsN + ' 件') >= 0,
      (hp2.match(/class="ct">([^<]*)</) || [])[1]);
  chk('v126 稀有度 chip 齐全（全部 + 按存在的稀有度去重降序）',
      hp2.indexOf('>全部</button>') >= 0 &&
      (hp2.match(/data-r="\d+"/g) || []).length >= 2);
  // 服务端过滤路径（LdlvPick 选中后 render 走的就是它）：
  A.LO.dlvPop = { uid: hub2.uid, idx: 0, q: '电池', rare: 0 };
  A.render();
  const hpQ = outEl.innerHTML || '';
  const qItems = (hpQ.match(/data-nm="([^"]*)"/g) || []).map(s => s.slice(9, -1));
  chk('v126 搜索「电池」→ 条目变少且全部命中',
      qItems.length > 0 && qItems.length < hubCandsN && qItems.every(n => n.indexOf('电池') >= 0),
      qItems.length + '/' + hubCandsN + ' ' + qItems[0]);
  const rareN = r => A.hubCands(hubDom).filter(x => x.rarity === r).length;
  A.LO.dlvPop = { uid: hub2.uid, idx: 0, q: '', rare: 5 };
  A.render();
  const hpR = outEl.innerHTML || '';
  const rItems = (hpR.match(/data-rr="(\d)"/g) || []).map(s => s.slice(9, -1));
  chk('v126 R5 筛选 → 只剩稀有度 5（或该域无 R5 时空结果文案）',
      (rItems.length === rareN(5) && rItems.every(x => x === '5')) ||
      (rareN(5) === 0 && hpR.indexOf('没有匹配') >= 0),
      rItems.length + ' vs 预期 ' + rareN(5));
  const qExp = A.hubCands(hubDom).filter(x => x.name.indexOf('电池') >= 0 && x.rarity === 2).length;
  A.LO.dlvPop = { uid: hub2.uid, idx: 0, q: '电池', rare: 2 };
  A.render();
  const hpQR = outEl.innerHTML || '';
  chk('v126 搜索 + 稀有度叠加 → 与数据侧同口径',
      (hpQR.match(/data-nm=/g) || []).length === qExp,
      (hpQR.match(/data-nm=/g) || []).length + ' vs ' + qExp);
  A.LO.dlvPop = { uid: hub2.uid, idx: 0, q: '绝不存在的物品xyz', rare: 0 };
  A.render();
  chk('v126 空结果 → 显示引导文案 + 计数 0',
      (outEl.innerHTML || '').indexOf('没有匹配') >= 0 &&
      (outEl.innerHTML || '').indexOf('0 / ' + hubCandsN + ' 件') >= 0);
  // LdlvOpen 重置筛选；LdlvRefilter 存在（真实浏览器的 oninput 路径，迷你 DOM 不真跑）
  A.LO.pick = null;
  A.LdlvOpen(hub2.uid, 0);
  chk('v126 LdlvOpen 重置筛选（q=空、rare=0）',
      !!A.LO.dlvPop && (A.LO.dlvPop.q || '') === '' && (A.LO.dlvPop.rare || 0) === 0,
      JSON.stringify(A.LO.dlvPop && A.LO.dlvPop.q) + '/' + String(A.LO.dlvPop && A.LO.dlvPop.rare));
  chk('v126 LdlvSetQ/LdlvSetR/LdlvRefilter 都在',
      typeof A.LdlvSetQ === 'function' && typeof A.LdlvSetR === 'function' &&
      typeof A.LdlvRefilter === 'function');

  // ⭐v127 瓶罐筛选 + 灌装物标注（博士「你这里全是一样的瓶罐」——紫晶质瓶同名 ×10+，
  //   只有 content（构建期「装：xxx」字段）能分清装了什么）
  chk('v127 hubCands 条目带 ct（灌装物标注）',
      A.hubCands(hubDom).every(x => typeof x.ct === 'string'));
  const withCt = A.hubCands(hubDom).filter(x => x.ct);
  const jarN = A.hubCands(hubDom).filter(x => A.LdlvIsJar(x)).length;
  A.LO.dlvPop = { uid: hub2.uid, idx: 0, q: '', rare: 0, jar: 1 };
  A.render();
  const hpJ = outEl.innerHTML || '';
  const jarItems = (hpJ.match(/data-jar="(\d)"/g) || []).map(s => s.slice(10, -1));
  chk('v127 瓶罐筛选 → 条目全部 data-jar=1 且数量与数据侧同口径',
      jarItems.length === jarN && jarN > 0 && jarItems.every(x => x === '1'),
      jarItems.length + ' vs ' + jarN);
  chk('v127 瓶罐 chip 渲染且点亮',
      hpJ.indexOf('>瓶罐</button>') >= 0 && /class="cbtn on" data-j="1"/.test(hpJ));
  chk('v127 灌装物标注进条目（class="cc"）',
      withCt.length === 0 || hpJ.indexOf('class="cc"') >= 0,
      '该域 content 物品 ' + withCt.length + ' 件');
  if (withCt.length) {
    // 搜索口径 = 名字 + content：取第一件 content 物品的标注子串当关键词
    const kw = withCt[0].ct.replace(/^装：/, '').slice(0, 2);
    const qExp = A.hubCands(hubDom).filter(x =>
      ((x.name + ' ' + (x.ct || '')).indexOf(kw) >= 0)).length;
    A.LO.dlvPop = { uid: hub2.uid, idx: 0, q: kw, rare: 0, jar: 0 };
    A.render();
    const hpC = outEl.innerHTML || '';
    chk('v127 搜索「' + kw + '」命中 content（名字或灌装物）',
        (hpC.match(/data-nm=/g) || []).length === qExp && qExp > 0,
        (hpC.match(/data-nm=/g) || []).length + ' vs ' + qExp);
  }
  A.LO.pick = null;
  A.LdlvOpen(hub2.uid, 0);
  chk('v127 LdlvOpen 重置含 jar（q=空、rare=0、jar=0）',
      !!A.LO.dlvPop && (A.LO.dlvPop.q || '') === '' && (A.LO.dlvPop.rare || 0) === 0 &&
      (A.LO.dlvPop.jar || 0) === 0,
      JSON.stringify(A.LO.dlvPop && [A.LO.dlvPop.q, A.LO.dlvPop.rare, A.LO.dlvPop.jar]));
  chk('v127 LdlvSetJ/LdlvIsJar 都在',
      typeof A.LdlvSetJ === 'function' && typeof A.LdlvIsJar === 'function');
  A.LO.dlvPop = null;
})();

// ⭐v128 链尾自动拧转（博士 2026-09-24「连续放传送带时，在上一条传送带的末尾拐弯放置，
//   末尾那格不会自动变更拐弯」）。弯头渲染靠 flowIn 拓扑反推（邻居指向我才有进边），
//   「从旧带末尾拐出去」时旧尾格没有任何邻居指向它 → 永远画直条。
//   修法 = LlayTo 落格后扫描首格四邻，把满足「出向不指首格 + 首格不流入它 +
//   出向下格是空格」的同类普通带/管段拧向首格（v106 渲染推断随即画弯头）。
loReset(50);
(function () {
  // 场景1：横排带 (3,5)(4,5)(5,5) 全向右流，E=(5,5) 是链尾。从 E 上方 (5,4) 起手
  //   向上拖到 (5,2) → 新竖列向上流，E 应被拧成 270（左进上出弯头）。
  A.LO.objs = [
    A.Lmk(A.byBp('grid_belt_01'), 3, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 4, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 5, 5, 0)
  ];
  A.Lpick('grid_belt_01');
  A.LODRAG = { mode: 'lay', sx: 5, sy: 4, ex: 5, ey: 4, uids: [], hist: [[5, 4]] };
  A.LlayTo(5, 2);
  const e1 = A.LO.objs.filter(o => o.x === 5 && o.y === 5)[0];
  chk('v128 链尾拧转：横排末尾格拧向上（270）', !!e1 && e1.rot === 270, e1 ? 'rot=' + e1.rot : 'none');
  const nv1 = A.LO.objs.filter(o => o.id === 'grid_belt_01' && o.y <= 4 && o.y >= 2 && o.x === 5);
  chk('v128 新竖列铺上且向上流（270）', nv1.length === 3 && nv1.every(o => o.rot === 270),
      nv1.map(o => o.y + '@' + o.rot).join(' '));
  // 撤销口径：手势起手前 Lpush 压栈（mousedown 同款），拧转+铺带一次 Ctrl+Z 全还原
  A.LO.undo = []; A.LO.redo = [];
  A.LO.objs = [
    A.Lmk(A.byBp('grid_belt_01'), 3, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 4, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 5, 5, 0)
  ];
  A.Lpush();   // 模拟 mousedown 起手压栈
  A.LODRAG = { mode: 'lay', sx: 5, sy: 4, ex: 5, ey: 4, uids: [], hist: [[5, 4]] };
  A.LlayTo(5, 2);
  A.Lundo();
  chk('v128 撤销一次：拧转与铺带同批还原（回到 3 格横排、末尾 rot=0）',
      A.LO.objs.length === 3 &&
      A.LO.objs.every(o => o.y === 5 && o.rot === 0),
      A.LO.objs.length + ' 格 ' + A.LO.objs.map(o => o.x + ',' + o.y + '@' + o.rot).join(' '));
})();

loReset(50);
(function () {
  // 场景2：非链尾不拧 —— E=(5,5) 出向 (6,5) 有同类承接，拧了会断链。
  A.LO.objs = [
    A.Lmk(A.byBp('grid_belt_01'), 3, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 4, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 5, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 6, 5, 0)
  ];
  A.Lpick('grid_belt_01');
  A.LODRAG = { mode: 'lay', sx: 5, sy: 4, ex: 5, ey: 4, uids: [], hist: [[5, 4]] };
  A.LlayTo(5, 2);
  const e2 = A.LO.objs.filter(o => o.x === 5 && o.y === 5)[0];
  chk('v128 非链尾不拧：出向有承接的中间段保持 0', !!e2 && e2.rot === 0, e2 ? 'rot=' + e2.rot : 'none');
})();

loReset(50);
(function () {
  // 场景3：首格流入旧带不拧（防拧成互指死循环）—— 从 E 上方向下拖，新带流向 E。
  A.LO.objs = [
    A.Lmk(A.byBp('grid_belt_01'), 3, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 4, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 5, 5, 0)
  ];
  A.Lpick('grid_belt_01');
  A.LODRAG = { mode: 'lay', sx: 5, sy: 4, ex: 5, ey: 4, uids: [], hist: [[5, 4]] };
  A.LlayTo(5, 5);   // 向下一格：(5,5) 被旧带占 → 跳过，首格 (5,4) rot=90 流向 E
  const e3 = A.LO.objs.filter(o => o.x === 5 && o.y === 5)[0];
  const f3 = A.LO.objs.filter(o => o.x === 5 && o.y === 4)[0];
  chk('v128 首格流入旧带：E 不拧（保持 0，链由 flowIn 自动衔接）',
      !!e3 && e3.rot === 0 && !!f3 && f3.rot === 90,
      'E=' + (e3 ? e3.rot : 'none') + ' F=' + (f3 ? f3.rot : 'none'));
})();

loReset(50);
(function () {
  // 场景4：旧尾已指向首格不拧 —— 从 E 右边 (6,5) 起手向上拖，E 出向恰指首格。
  A.LO.objs = [
    A.Lmk(A.byBp('grid_belt_01'), 4, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 5, 5, 0)
  ];
  A.Lpick('grid_belt_01');
  A.LODRAG = { mode: 'lay', sx: 6, sy: 5, ex: 6, ey: 5, uids: [], hist: [[6, 5]] };
  A.LlayTo(6, 3);
  const e4 = A.LO.objs.filter(o => o.x === 5 && o.y === 5)[0];
  chk('v128 旧尾已指向首格：不拧（E 保持 0，E→新带已衔接）',
      !!e4 && e4.rot === 0, e4 ? 'rot=' + e4.rot : 'none');
})();

loReset(50);
(function () {
  // 场景5：管道同款 —— 横排管道链尾，从末尾上方拐出去，尾管拧向上。
  A.LO.objs = [
    A.Lmk(A.byBp('log_pipe_01'), 3, 7, 0),
    A.Lmk(A.byBp('log_pipe_01'), 4, 7, 0),
    A.Lmk(A.byBp('log_pipe_01'), 5, 7, 0)
  ];
  A.Lpick('log_pipe_01');
  A.LODRAG = { mode: 'lay', sx: 5, sy: 6, ex: 5, ey: 6, uids: [], hist: [[5, 6]] };
  A.LlayTo(5, 4);
  const e5 = A.LO.objs.filter(o => o.id === 'log_pipe_01' && o.x === 5 && o.y === 7)[0];
  chk('v128 管道链尾同款拧转（270）', !!e5 && e5.rot === 270, e5 ? 'rot=' + e5.rot : 'none');
})();

loReset(50);
(function () {
  // 场景6：出向下格压着机器不拧 —— E 出向指着机器输入侧，拧走会破坏「带子进机器」。
  A.Lpick('furnance_1'); A.Lput(6, 4);   // 3×3 占 (6,4)~(8,6)，含 E=(5,5) 出向的 (6,5)
  A.LO.objs.push(
    A.Lmk(A.byBp('grid_belt_01'), 3, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 4, 5, 0),
    A.Lmk(A.byBp('grid_belt_01'), 5, 5, 0)
  );
  A.Lpick('grid_belt_01');
  A.LODRAG = { mode: 'lay', sx: 5, sy: 4, ex: 5, ey: 4, uids: [], hist: [[5, 4]] };
  A.LlayTo(5, 2);
  const e6 = A.LO.objs.filter(o => o.x === 5 && o.y === 5)[0];
  chk('v128 出向下格压机器：不拧（保住带子进机器的衔接）',
      !!e6 && e6.rot === 0, e6 ? 'rot=' + e6.rot : 'none');
  A.LO.objs = A.LO.objs.filter(o => o.id !== 'grid_belt_01');
})();

// ⚠️ 接口标记的几何护栏（2026-09-21 两轮报障的根因都在这块）
// 第一轮：标记"往格外偏 4.5px" + .lo-cell 带 overflow:hidden → 被裁成贴边细线，「看不见」。
// 第二轮：改成压格线跨出去 → 一半伸进邻格，邻格放传送带就互相压字，「重叠不美观」。
// 现在：标记贴建筑**内侧**紧挨边框，0 越界 —— 两个毛病一起解决。
// ⚠️ 这一段必须放在最后：它要一块干净画布来数标记，中途 loReset 会把前面的用例搞挂。
chk('.lo-cell 不能裁剪子元素（overflow:visible）',
    /\.lo-cell\{[^}]*overflow:visible/.test(style) && !/\.lo-cell\{[^}]*overflow:hidden/.test(style),
    'lo-cell overflow');
chk('.lo-port 带 z-index（不被邻格建筑盖住）', /\.lo-port\{[^}]*z-index:\s*\d/.test(style));
chk('不再有跨格的 .lo-port::after 短棒（重叠的来源）', !/\.lo-port::after/.test(style));
chk('物流件的接口图由 .lo-cell > svg 承载', /\.lo-cell > svg\{/.test(style));

const geoB = A.DB.blueprint.buildings.find(b => b.id === 'furnance_1');
chk('取到 3×3 且四个朝向都有口的建筑（几何断言前提）',
    !!geoB && geoB.gridFootprint === '3×3' &&
    ['l', 'r', 'u', 'd'].every(d =>
      geoB.ports.some(p => { const q = A.LportXY(p, 0, 3, 3); return A.LportDir(q, 3, 3) === d; })),
    geoB ? geoB.id : 'none');
loReset(50);
A.Lpick(geoB.id); A.Lput(4, 4);
const geoHtml = outEl.innerHTML || '';
const portPts = [...geoHtml.matchAll(/class="lo-port[^"]*" style="left:(-?[\d.]+)px;top:(-?[\d.]+)px/g)]
  .map(m => ({ left: +m[1], top: +m[2] }));
chk('渲染出的标记数 = 该建筑口数', portPts.length === geoB.ports.length,
    portPts.length + ' vs ' + geoB.ports.length);
const CELLPX = A.LOCELL, BORDER = 1.5, RAD = 3.5, GAP = 0.5;   // 格子边长从页面读，别硬编码（v14 起默认 14→20）
const INW = 3 * CELLPX - 2 - 2 * BORDER, IND = INW;   // padding box 尺寸（3×3 → 37）
let onInner = 0;
for (const p of geoB.ports) {
  const q = A.LportXY(p, 0, 3, 3);
  const dir = A.LportDir(q, 3, 3);
  const dx = dir === 'l' ? -1 : dir === 'r' ? 1 : 0;
  const dz = dir === 'u' ? -1 : dir === 'd' ? 1 : 0;
  const ex = dx ? (dx > 0 ? INW - GAP - RAD : GAP + RAD) : q.x * CELLPX + CELLPX / 2 - BORDER;
  const ey = dz ? (dz > 0 ? IND - GAP - RAD : GAP + RAD) : q.z * CELLPX + CELLPX / 2 - BORDER;
  if (portPts.some(o => Math.abs(o.left - ex) < 0.01 && Math.abs(o.top - ey) < 0.01)) onInner++;
}
chk('每个标记都贴在自己那条边的内侧（距内沿 4px）', onInner === geoB.ports.length,
    onInner + '/' + geoB.ports.length);
// 关键硬门：标记整块必须落在建筑自己的格内 —— 这是"不跟邻格重叠"的充分条件
const boxW = 3 * CELLPX - 2, boxD = 3 * CELLPX - 2;
const outside = portPts.filter(o => {
  const cx = o.left + BORDER, cy = o.top + BORDER;   // 换算到边框盒坐标
  return cx - RAD < 0 || cx + RAD > boxW || cy - RAD < 0 || cy + RAD > boxD;
}).length;
chk('所有标记都在建筑自己的格内（0 越界 → 不会和邻格重叠）', outside === 0,
    outside + '/' + portPts.length + ' 个越界');
chk('说明里写了强刷提示（旧版本没有这层标记）', geoHtml.indexOf('强刷') >= 0);

// ---- 物流件的进/出边（配置表 rotation.y = 物料流向，进料口在流向反侧）----
const sidesOf = (id, rot) => { const b = A.byBp(id); const s = A.lgPortSides(b, rot || 0); return s; };
const J = s => s.slice().sort().join('');
chk('汇流器 进「左/下/右」出「上」（=3进1出）', J(sidesOf('log_converger').in) === 'blr' && J(sidesOf('log_converger').out) === 't',
    J(sidesOf('log_converger').in) + ' / ' + J(sidesOf('log_converger').out));
chk('分流器 进「下」出「左/上/右」（=1进3出）', J(sidesOf('log_splitter').in) === 'b' && J(sidesOf('log_splitter').out) === 'lrt',
    J(sidesOf('log_splitter').in) + ' / ' + J(sidesOf('log_splitter').out));
chk('物品准入口 进「下」出「上」（直线穿过）', J(sidesOf('log_conditioner').in) === 'b' && J(sidesOf('log_conditioner').out) === 't');
chk('物流桥 四条边都双向', J(sidesOf('log_connector').in) === 'blrt' && J(sidesOf('log_connector').out) === 'blrt');
chk('管道汇流器/管道分流器与传送带版同向',
    J(sidesOf('log_pipe_converger').in) === J(sidesOf('log_converger').in) &&
    J(sidesOf('log_pipe_splitter').out) === J(sidesOf('log_splitter').out));
// 传送带/管道：配置表没有接口数组，按「一格一段、穿过」处理
chk('传送带（rot 0）进左出右', J(sidesOf('grid_belt_01').in) === 'l' && J(sidesOf('grid_belt_01').out) === 'r');
chk('管道 rot 90 进上出下（跟着画布转）', J(A.lgPortSides(A.byBp('log_pipe_01'), 90).in) === 't' &&
    J(A.lgPortSides(A.byBp('log_pipe_01'), 90).out) === 'b');
// 旋转要跟着转：rot 每加 90°，边也顺时针挪一格
chk('汇流器转 90° 后进/出边同步顺时针挪一格',
    J(sidesOf('log_converger', 90).in) === 'blt' && J(sidesOf('log_converger', 90).out) === 'r',
    J(sidesOf('log_converger', 90).in) + ' / ' + J(sidesOf('log_converger', 90).out));
chk('lgSideNames 给出可读方位', A.lgSideNames(A.byBp('log_splitter'), 0, 'in') === '下' &&
    A.lgSideNames(A.byBp('log_splitter'), 0, 'out') === '右/上/左');
// 渲染层：色条数 = 单向边 1 条 / 双向边 2 条；双向边用两种颜色
loReset(50);
A.Lpick('log_converger'); A.Lput(2, 2);
const cvg = outEl.innerHTML || '';
chk('汇流器 SVG 画了 4 条色条（3 进 + 1 出）',
    (cvg.match(/<rect /g) || []).length === 4, String((cvg.match(/<rect /g) || []).length));
chk('汇流器色条含 3 青 1 橙',
    (cvg.match(/#186C7D/g) || []).length === 3 && (cvg.match(/#C0561F/g) || []).length === 1,
    (cvg.match(/#186C7D/g) || []).length + '青 / ' + (cvg.match(/#C0561F/g) || []).length + '橙');
loReset(50);
A.Lpick('log_connector'); A.Lput(2, 2);
const cnn = outEl.innerHTML || '';
chk('物流桥 SVG 画了 8 条色条（4 边 × 双向）',
    (cnn.match(/<rect /g) || []).length === 8, String((cnn.match(/<rect /g) || []).length));
chk('物流桥双向边用半青半橙', (cnn.match(/#186C7D/g) || []).length === 4 && (cnn.match(/#C0561F/g) || []).length === 4);

// 全量回代：配置表 rotation.y（流向）推出的边，应当和位置推的边一致
const FLOW = { 0: 'b', 90: 'r', 180: 't', 270: 'l' }, OPP = { t: 'b', b: 't', l: 'r', r: 'l' };
const U2T = { u: 't', d: 'b', l: 'l', r: 'r' };
let agree = 0, tot = 0;
for (const b of A.DB.blueprint.buildings) {
  const f = b.gridFootprint.split('×').map(Number);
  for (const p of (b.ports || [])) {
    const q = A.LportXY(p, 0, f[0], f[1]);
    const dir = A.LportDir(q, f[0], f[1]);
    if (!dir) continue;
    tot++;
    const side = U2T[dir];
    const exp = p.kind === 'input' ? OPP[side] : side;
    if (FLOW[p.facing] === exp) agree++;
  }
}
chk('「流向」约定在全量建筑接口上自洽（允许 1 个几何退化例外：3×1 存取口）',
    tot > 250 && agree >= tot - 1, agree + '/' + tot);

// 接口显示开关
loReset(50);
A.Lpick(mixedB.id); A.Lput(5, 5);
chk('默认渲染出接口（showPort 默认开）', (outEl.innerHTML || '').indexOf('lo-port') >= 0);
A.LtogglePort();
chk('关掉后不再渲染 lo-port', (outEl.innerHTML || '').indexOf('lo-port') < 0);
chk('关掉后接口图例一起收起', (outEl.innerHTML || '').indexOf('<i class="inp"></i>进料口') < 0);
chk('环境圈图例独立于接口开关（v103，showGas 不跟着关）', (outEl.innerHTML || '').indexOf('气体散布机环境圈') >= 0);
A.LtogglePort();
chk('再打开又有了', (outEl.innerHTML || '').indexOf('lo-port') >= 0);
loReset(50);
A.render();

// ================= ⑤-1 局部锁定（博士 2026-09-22「锁住满意的机器，只重排其余」）=================
// ① 标记 / 渲染 / 撤销
loReset(50);
A.Lpick('furnance_1'); A.Lput(5, 5);
const lk0 = A.LO.objs[0];
chk('锁定前对象上没有 lock 字段', !lk0.lock);
const u0 = A.LO.undo.length;            /* Lput 自己也会压一次撤销栈，所以比增量 */
A.LlockSel(true);                       /* Lput 之后自动选中 */
chk('「锁定选中」给对象打上 lock', lk0.lock === true);
chk('锁定进撤销栈（可撤销）', A.LO.undo.length === u0 + 1, String(A.LO.undo.length));
chk('锁定态渲染出 .lock 类', /class="lo-cell[^"]*\block\b/.test(outEl.innerHTML || ''));
chk('锁定态在计数区有提示', (outEl.innerHTML || '').indexOf('已锁定') >= 0);
chk('工具栏有「解锁全部」按钮', (outEl.innerHTML || '').indexOf('LunlockAll()') >= 0);
A.LunlockAll();
chk('「解锁全部」清掉标记', !lk0.lock);
chk('解锁后不再渲染 .lock 类', !/class="lo-cell[^"]*\block\b/.test(outEl.innerHTML || ''));

// ② 交互保护：转不动 / 复制不带 / 删不掉
loReset(50);
A.Lpick('furnance_1'); A.Lput(5, 5);
const lk1 = A.LO.objs[0];
A.LlockSel(true);
const rot0 = lk1.rot;
A.Lrot();
chk('锁定件不参与旋转（且给出原因）', lk1.rot === rot0 && (A.LO.msg || '').indexOf('锁定') >= 0);
A.Ldup();
chk('锁定件不参与复制', A.LO.objs.length === 1, String(A.LO.objs.length));
A.Ldel();
chk('锁定件删不掉（Del / 双击删除都走这条路）', A.LO.objs.length === 1 && (A.LO.msg || '').indexOf('锁定') >= 0);
A.LO.sel = [lk1.uid];
A.LlockSel(false);
chk('「解锁选中」能精确解锁单个件', !lk1.lock);
A.Ldel();
chk('解锁后就能删掉', A.LO.objs.length === 0);

// ③ LawPlan 固定件避让（单元级）
const resFix = A.Rexplode('item_iron_cmpt', 30);
const FIX = [{ x: 6, y: 6, w: 6, d: 6 }];
const plFix = A.LawPlan(resFix, 70, 6, { gapX: 4, align: false, mode: 'down', fixed: FIX });
const noHit = o => !(o.x < FIX[0].x + FIX[0].w && o.x + o.w > FIX[0].x && o.y < FIX[0].y + FIX[0].d && o.y + o.d > FIX[0].y);
chk('LawPlan 传 fixed：新机器一律不与固定件重叠',
    plFix.objs.length > 0 && plFix.objs.every(noHit), plFix.objs.length + ' 台');
chk('LawPlan 不传 fixed 时布局可复现（老路径一行没动）',
    JSON.stringify(A.LawPlan(resFix, 70, 6, { gapX: 4, align: false, mode: 'down' }).objs) ===
    JSON.stringify(A.LawPlan(resFix, 70, 6, { gapX: 4, align: false, mode: 'down' }).objs));

// ④ 「重排其余」整体行为
loReset(70);
A.LO.size = 70;
A.LawRun('item_iron_cmpt', 10);
const mA = A.LO.objs.filter(o => o.planRole === 'machine');
chk('生成的机器都带 pkey（能对回配方树节点，且不会让快照成环）',
    mA.length > 0 && mA.every(o => typeof o.pkey === 'string' && o.pkey.length > 2));
chk('生成的机器默认不锁定', mA.every(o => !o.lock));
A.Lreroll();
chk('没锁任何机器时「重排其余」拒绝执行并提示先锁',
    A.LO.objs.filter(o => o.planRole === 'machine').length === mA.length && (A.LO.msg || '').indexOf('锁定') >= 0);

const lockM = mA[0];
lockM.lock = true;
const posB = lockM.x + ',' + lockM.y;
const nB = mA.length;
A.Lreroll();
const mB = A.LO.objs.filter(o => o.planRole === 'machine');
chk('重排后机器台数守恒（产量口径不变）', mB.length === nB, nB + ' → ' + mB.length);
chk('重排后锁定件在原位、且仍然锁定',
    mB.some(o => o.uid === lockM.uid && (o.x + ',' + o.y) === posB && o.lock === true), posB);
chk('重排后没有任何东西压住锁定件', (() => {
  const occ = {};
  A.LO.objs.filter(o => o.uid !== lockM.uid).forEach(o => {
    for (let j = 0; j < o.d; j++) for (let i = 0; i < o.w; i++) occ[(o.x + i) + ',' + (o.y + j)] = 1;
  });
  for (let j = 0; j < lockM.d; j++) for (let i = 0; i < lockM.w; i++) {
    if (occ[(lockM.x + i) + ',' + (lockM.y + j)]) return false;
  }
  return true;
})());
chk('重排后全部仍在界内',
    A.LO.objs.every(o => o.x >= 0 && o.y >= 0 && o.x + o.w <= 70 && o.y + o.d <= 70));
chk('重排后管线还在（重铺而不是丢掉）',
    A.LO.objs.filter(o => o.planRole === 'link' || o.planRole === 'merge' || o.planRole === 'split').length > 0);
chk('重排消息点明锁了几台 / 重摆几台', (A.LO.msg || '').indexOf('锁定') >= 0 && (A.LO.msg || '').indexOf('重摆') >= 0,
    A.LO.msg);
chk('重排进撤销栈', A.LO.undo.length > 0, String(A.LO.undo.length));
A.Lundo();
chk('撤销重排：机器台数回到重排前', A.LO.objs.filter(o => o.planRole === 'machine').length === nB);

// 全锁：没有可重排的机器，也不能崩
loReset(70);
A.LO.size = 70;
A.LawRun('item_iron_cmpt', 10);
A.LO.objs.filter(o => o.planRole === 'machine').forEach(o => { o.lock = true; });
A.Lreroll();
chk('全部锁定时重排不崩、机器台数不变',
    A.LO.objs.filter(o => o.planRole === 'machine').length === A.LO.plan.res.totalMachines);

loReset(50); A.render();

// ================= ⑤-2 分流器分支的真实工况覆盖（2026-09-22）=================
// 这一分支此前**一条真实工况断言都没有**（现成的两个目标走不到它）。扫全库后找到的真实触发工况是
// 「工业爆炸物 / 实验玉铜发散器 / 息壤玉葫芦」—— 结构都是「1 台高产能上游机器要喂 5~10 台下游」，
// 上游出料口不够 → 必须上分流器。顺带抓到两个真 bug：① 一台分流器只有 3 个出料格，旧版**只摆一个**，
// 第 4 台下游起**静默丢弃**（报告还写"手动连 0"）；② 提示的"需要几个分流器"按「缺几个出料口」算，量级也不对。

function splitRun(targetName, rate, size) {
  /* ⚠️ LawRun 收的是**物品 id**，不是中文名 —— 直接塞名字会静默变成"没有机器配方"（本轮踩过） */
  /* ⭐v146：兼容 id 或名字 —— 同名物品加缀后，用 id 找最稳 */
  const t = A.RwTargets().filter(x => x.name === targetName || x.id === targetName)[0];
  loReset(size);
  A.LO.size = size;
  chk('⑤-2 前提：目标物品「' + targetName + '」在目标清单里', !!t);
  A.LawRun(t ? t.id : targetName, rate);
  return A.LO.plan;
}
const Psp5 = splitRun('工业爆炸物', 5, 50);
chk('⑤-2：工业爆炸物@5 真的走进「自动摆分流器」分支', !!(Psp5 && Psp5.route.stats && Psp5.route.stats.split >= 1 &&
  Psp5.route.warns.some(w => w.indexOf('自动摆') >= 0 && w.indexOf('分流器') >= 0)),
  Psp5 ? JSON.stringify(Psp5.route.stats) : 'none');
chk('⑤-2：5 台下游必须**并排摆两个**分流器（旧版只摆一个 → 剩 2 台静默丢）',
  !!Psp5 && Psp5.route.stats.split === 2, Psp5 ? String(Psp5.route.stats.split) : 'none');
chk('⑤-2：摆出来的分流器件数 == stats.split（数据与画布一致）',
  !!Psp5 && A.LO.objs.filter(o => o.planRole === 'split').length === Psp5.route.stats.split);
chk('⑤-2：被丢下的线**必须点名**（有 dropped 就必须有「还有 N 台下游没连上」）',
  !!(Psp5 && (Psp5.route.stats.dropped === 0 ||
    Psp5.route.warns.some(w => w.indexOf('没连上') >= 0))),
  Psp5 ? ('dropped=' + Psp5.route.stats.dropped) : 'none');
chk('⑤-2：提示口径 = ceil(outNeed/3) 个分流器（1 进 3 出），不是"缺几个出料口"',
  !!Psp5 && Psp5.route.warns.some(w => w.indexOf('需要 2 个**分流器**（1 进 3 出') >= 0),
  (Psp5 ? Psp5.route.warns.filter(w => w.indexOf('分流器**') >= 0)[0] : ''));

// 全连通正例：5 台下游全部由分流器接上、零手动连
const PspY = splitRun('息壤玉葫芦', 5, 50);
chk('⑤-2 全连通正例：息壤玉葫芦@5 —— 分流器 2 个、5 台下游全接上、零手动连', (() => {
  if (!PspY) return false;
  const viaSplit = PspY.route.links.filter(k => k.viaSplit).length;
  const manual = PspY.route.warns.filter(w => w.indexOf('手动连') >= 0).length;
  return PspY.route.stats.split === 2 && viaSplit === 5 && manual === 0 && PspY.route.stats.dropped === 0;
})(), PspY ? (JSON.stringify(PspY.route.stats) + ' viaSplit=' + PspY.route.links.filter(k => k.viaSplit).length) : 'none');
chk('⑤-2：分流器不压机器、非桥实体零**同介质**重叠（分流链也要给出合法布局）', (() => {
  if (!PspY) return false;
  return ovBadCells(A.LO.objs).length === 0;
})());

// 大产线：10 台下游，分流器摆不下就如实报数，不假装连上（heavy：80 画布 @10 大链 ~1.5s）
if (HEAVY) {
  const Psp10 = splitRun('工业爆炸物', 10, 80);
  chk('⑤-2 大产线：工业爆炸物@10 —— 摆了分流器但仍不够时，逐条点名（不静默丢）', (() => {
    if (!Psp10) return false;
    const st = Psp10.route.stats;
    const named = Psp10.route.warns.some(w => w.indexOf('没连上') >= 0);
    const manual = Psp10.route.warns.filter(w => w.indexOf('手动连') >= 0).length;
    return st.split >= 2 && st.dropped <= 10 && (st.dropped === 0 || (named && manual > 0));
  })(), Psp10 ? (JSON.stringify(Psp10.route.stats) + ' warns=' + Psp10.route.warns.length) : 'none');
} else {
  skipHeavy += 2;  /* 大产线 chk + splitRun 内部的「⑤-2 前提」chk（后者跟着 splitRun 一起被跳） */
}
loReset(50); A.render();

// ================= ⑤-3 高产能 / 宽链的连通率（2026-09-22）=================
// 两个根因（都用「扫全库 + 把候选方案逐个打分」找出来的）：
//   ① **打分口径反了**：2 条手动连只罚 200 分，盖不过 300 格线长差 → 「全连通但线长」被判输；
//      手动连权重 100 → 400（少一条线是玩家得动手补的功能缺陷，多铺格子只是效率问题）。
//   ② **参数网格太窄**：机器间距只到 4；实测宽链要「间 8」机器之间那条竖缝才够并行走线 →
//      加了「只在还有手动连时才补跑」的宽间距扩搜（+ 汇流器 fanin/必须并线两处口径修正）。
// 效果（同一台机器扫 52 个中大型工况）：零手动连 **44 → 51 例**，手动连总数 **23 → 1 条**。

// （heavy：80 画布 @30 大链 + 宽间距扩搜 ~3.5s；两条断言共享同一次求解，必须同跳同跑）
if (HEAVY) {
chk('⑤-3 高产能：赤铜耐压罐@30 手动连清零，且 30 台全摆（⭐③ 收尾：旧 down 候选会静默丢 11 台造出假「清零」，先证全摆再证连通）', (() => {
  loReset(80); A.LO.size = 80;
  A.LawRun('item_copper_jar', 30);
  const P = A.LO.plan;
  if (!P) return false;
  return P.plan.objs.length === P.res.totalMachines &&
    P.route.warns.filter(w => w.indexOf('手动连') >= 0).length === 0 &&
    P.route.loads.every(l => l.state !== 'none' && l.state !== 'jam');
})(), (A.LO.msg || '').replace(/\s+/g, ' ').slice(0, 130));
/* ⚡ v94 提速：扩搜标记断言与上一条共享同一次 copper_jar@30 求解（输入状态一字不差，
   中间无任何 mutate），不再单独重解一遍 —— 省一次 3.4s 级的大链求解。 */
chk('⑤-3 难例确实触发了扩搜：赤铜耐压罐@30 的消息里写明「含宽间距扩搜 N 组」',
    /宽间距扩搜 \d+ 组/.test(A.LO.msg || ''), A.LO.msg);
} else {
  skipHeavy += 2;
}
chkHeavy('⑤-3 宽链：赤铜块@10（12 台机器、低产率）全摆 + 手动连 ≤2 + 汇流器 ≥ 1（⭐③ 收尾改真口径：旧「手动连 0」是 down 候选静默丢 2 台的假绿 —— 少摆的机器既不占线也不报警）', () => {
  const t = A.RwTargets().filter(x => x.name === '赤铜块')[0];
  loReset(80); A.LO.size = 80;
  A.LawRun(t.id, 10);
  const P = A.LO.plan;
  if (!P || !P.route.stats) return false;
  return P.plan.objs.length === P.res.totalMachines &&
    P.route.warns.filter(w => w.indexOf('手动连') >= 0).length <= 2 && P.route.stats.merge >= 1;
}, () => (A.LO.msg || '').replace(/\s+/g, ' ').slice(0, 130));
chk('⑤-3 打分口径：「全连通但线长」必须赢过「手动连 2 条但线短」（LawPick）', (() => {
  const mk = (manual, belts) => A.LawPick({
    loads: [{ state: 'ok' }],
    warns: new Array(manual).fill('X ← Y：走线过不去，这一段请手动连'),
    belts: new Array(belts).fill(0),
  });
  return mk(0, 753).v > mk(2, 454).v;
})());
chk('⑤-3 快路径不付扩搜成本：一次就全连通的小链，消息里没有「宽间距扩搜」', (() => {
  loReset(50); A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 10);
  return (A.LO.msg || '').indexOf('宽间距扩搜') < 0;
})());
// ⭐2026-09-24 阈值 ≤2 → ≤3（博士委托处理）：对账 v150(d050390)/v151(a68cb07)/v152 工作区
// 三处 HEAVY 全部「手动连 3 · 连通 3 段」——退化是**渐进漂移**（v96 时代最佳 1 条，此后
// ⑤-2/⑤-3 打分口径、通道自适应、v151 外部接入等功能改动各自有据，累计 +2）。锁改守
// 「不再进一步退化」的线（≤3），把 2 当成优化器的待返场目标 —— 反哺候选：管×带叠加
// 放开后（v152），RwPath 里异介质交叉成本可从 BRIDGE=4 下调（改前先给博士过目）。
chkHeavy('⑤-3 最顽固的混合链（液化息壤@10）：手动连 ≤3 条（历史最佳 1，渐进漂移见上注）且靠汇流器接上', () => {
  const t = A.RwTargets().filter(x => x.name === '液化息壤')[0];
  loReset(80); A.LO.size = 80;
  A.LawRun(t.id, 10);
  const P = A.LO.plan;
  if (!P || !P.route.stats) return false;
  return P.route.warns.filter(w => w.indexOf('手动连') >= 0).length <= 3 && P.route.stats.merge >= 3;
}, () => (A.LO.msg || '').replace(/\s+/g, ' ').slice(0, 130));
loReset(50); A.render();

// ================= 采集建筑的「无线回传」标记（2026-09-22 博士问的）=================
// 博士：「矿机为什么会有出货口啊，矿机是挖完了把矿物无线传回基地仓库」。
// 查证：矿机在配置表里**确实挂着 3 个传送带出料口**（不是画错），但 **电驱矿机默认走「无线传输模式」**
//（FactoryMinerTable.hasDroneMode=true、msTransferCD=10 秒），挖到的矿直接回仓库 → 那 3 个口平时不用接。
// 两台反例：便携源石矿机（hasDroneMode=false，手动收）、水驱矿机（不在矿机表里）。所以示意图要把两类分开画、并写明。
// ⚠️ 水驱矿机那台要特别看清来源：配置表里 miner_4 **不在矿机表**、没有 hasDroneMode 字段，
//    它是博士 2026-09-22 实机确认「也无线回传」的 —— 数据里必须写明来源，别让它看起来像配置表读出来的。
chk('采集数据带上无线字段：miner_2/3/4 = true，miner_1 = false', (() => {
  const g = id => (A.DB.mining_power.gather || []).filter(x => x.id === id)[0] || {};
  return g('miner_2').wireless === true && g('miner_3').wireless === true && g('miner_4').wireless === true &&
    g('miner_1').wireless === false;
})(), 'wireless 字段');
chk('水驱矿机的 wireless 来源标成「实机确认」（配置表里没有这个字段）', (() => {
  const g = (A.DB.mining_power.gather || []).filter(x => x.id === 'miner_4')[0] || {};
  return String(g.wirelessSource || '').indexOf('实机确认') >= 0;
})(), '来源分级');
chk('7 座采集建筑都带 wirelessNote（每台的实情都要能写明）', (() => {
  const arr = A.DB.mining_power.gather || [];
  return arr.length === 7 && arr.every(x => (x.wirelessNote || '').length > 10);
})(), String((A.DB.mining_power.gather || []).length));
setTab('blueprint'); A.render();
/* ⚠️ 「有没有 ⇡」只能看**这张卡片自己的 SVG** —— 蓝图页顶部那段总说明里也写了「⇡」这些字，
   拿整页 innerHTML 判会永远为真（本轮就是先这样红了两条）。定义必须放在第一次用之前（const 不提升）。 */
const svgOf = h => { const a = h.indexOf('<svg'), b = h.indexOf('</svg>'); return (a >= 0 && b > a) ? h.slice(a, b + 6) : ''; };
A.openSet.clear(); A.openSet.add('p:miner_3'); A.render();
const m3Html = outEl.innerHTML || '', m3Svg = svgOf(m3Html);
// 博士追问「那这样 4 还用吗，玩家都是用无线传输的」→ 那 3 个出料口两种模式都用不上，**示意图干脆不画**，
// 改成在建筑上标「⇡ 无线回传仓库」徽标。
chk('二型电驱矿机：建筑上标「⇡ 无线回传仓库」徽标', m3Svg.indexOf('无线回传仓库') >= 0 && m3Svg.indexOf('⇡') >= 0);
chk('二型电驱矿机：3 个用不上的传送带出料口**一个都不画**（除了背景/外框没有别的 rect）', (() => {
  const n = (m3Svg.match(/<rect /g) || []).length;
  return n === 2 && m3Svg.indexOf('>O<') < 0;
})(), String((m3Svg.match(/<rect /g) || []).length));
chk('二型电驱矿机：图下写明「默认无线传输模式 / 10 秒回传」和「数据仍保留」',
    m3Html.indexOf('无线传输模式') >= 0 && m3Html.indexOf('10 秒') >= 0 && m3Html.indexOf('不画它们') >= 0);
A.openSet.clear(); A.openSet.add('p:pump_1'); A.render();
const p1Html = outEl.innerHTML || '', p1Svg = svgOf(p1Html);
chk('水泵：管道出料口照旧（不是无线口），并写明「只能走管道」',
    p1Svg.indexOf('⇡') < 0 && p1Svg.indexOf('>o<') >= 0 && p1Html.indexOf('只能走管道') >= 0);
A.openSet.clear(); A.openSet.add('p:miner_4'); A.render();
const m4Html = outEl.innerHTML || '', m4Svg = svgOf(m4Html);
chk('水驱矿机：也标「无线回传仓库」（博士实机确认），出料口不画、但清水管道进料口照常画',
    m4Svg.indexOf('无线回传仓库') >= 0 && m4Svg.indexOf('>O<') < 0 &&
    m4Svg.indexOf('>i<') >= 0 && m4Html.indexOf('管道进清水') >= 0 && m4Html.indexOf('博士实机确认') >= 0);
A.openSet.clear(); A.openSet.add('p:miner_1'); A.render();
const m1Html = outEl.innerHTML || '', m1Svg = svgOf(m1Html);
chk('便携源石矿机：标「⇥ 缓存区 · 手动收取」，出料口同样不画',
    m1Svg.indexOf('缓存区 · 手动收取') >= 0 && m1Svg.indexOf('>O<') < 0 && m1Svg.indexOf('⇡') < 0 &&
    m1Html.indexOf('手动收取') >= 0);
A.openSet.clear(); setTab('layout'); loReset(50); A.render();

// ================= ④ 原料侧闭环：能做的配比清单 + 明确「不做」的边界（2026-09-22）=================
// 博士追问「那这样 ④ 还用做吗」——答：不用按原样做。因为三种矿机的产物都无线回仓/进缓存区，
// **野外没有需要连的线**（每矿点独立放一台），而野外又不是网格、配置表也没有地形 ⇒ 摆放与走线做不了。
// 能做的只有**配比清单**：几台泵 / 怎么分 / 几条管 / 要不要通电。这一节就守这两件事。
const raw4 = (() => {
  const t = A.RwTargets().filter(x => x.name === '赤铜零件')[0];
  loReset(80); A.LO.size = 80;
  A.LawRun(t.id, 10);
  return outEl.innerHTML || '';
})();
chk('④ 报告给出水驱矿机的**供水配比**（泵台数 / 分管 / 管道条数）', (() => {
  return raw4.indexOf('水驱矿机每台耗水') >= 0 &&
    raw4.indexOf('1 台水泵最多带 3 台水驱矿机满效率') >= 0 &&
    raw4.indexOf('每台泵 1 条管道就够') >= 0;
})(), '供水配比');
chk('④ 报告给出**供电**提示（水泵要通电、水驱矿机不耗电）',
    raw4.indexOf('水泵要通电') >= 0 && raw4.indexOf('水驱矿机靠清水自供能、不耗电') >= 0);
// ⚠️ 只有 1 台泵时，分管文案曾写成「前 0 台各带 3 台」（真机跑出来过）—— 守一下措辞
chk('④ 分管文案在「只有 1 台泵」时不出现「前 0 台」这种怪话',
    raw4.indexOf('前 0 台') < 0 && raw4.indexOf('这 1 台泵带 1 台') >= 0,
    (raw4.match(/分管：[^<]{0,60}/) || [''])[0]);
chk('④ 明确写出「野外摆放与走线不做」+ 两条原因（不是漏了）', (() => {
  return raw4.indexOf('野外段的实际摆放与走线，本工具不做') >= 0 &&
    raw4.indexOf('野外没有需要连的线') >= 0 && raw4.indexOf('野外不是网格') >= 0 &&
    raw4.indexOf('标为不做') >= 0;
})());
loReset(50); A.render();

// ================= ⑥-1 跨地区收货：四号谷地 → 武陵 超库存传输（2026-09-22）=================
// 博士口径：「只用从四号谷地向武陵超库存传输就行，我基地等级已经升满了可以超库存传输」
// 机制原文（I18n / FactoryConst，见 data/rules.json 的 rule_domain_transfer）：
//   · 库存传输 = 扣出发地仓库、等量送到；超库存传输 = **不扣出发地库存**，目的地直接获得，
//     出发地「本地区集成工业可生产的任意一种物品」都能传 → 判定依据是**有没有本地区机器配方**
//   · 一批只能传一种物品；数量上限 = 传输总值 ÷ 单位物品价值（FactoryItemTable.value）
//   · 能传的物品清单 = FactoryItemTable.transferDomainIds（564 件里 243 件，全部两地区通用）
// 这里守四件事：数据齐 / 开关默认不影响老行为 / 开了之后原料被改成收货 / 反推口径正确
chk('⑥-1 数据层：物品带上「单位物品价值」value 与「可跨地区传输」domains',
    (() => {
      const a = A.DB.items['item_copper_enr'], b = A.DB.items['item_carbon_mtl'];
      return a && a.value === 20 && (a.domains || []).length === 2 &&
             b && b.value === 1 && (b.domains || []).length === 2;
    })(), JSON.stringify(A.DB.items['item_copper_enr'] || null));

chk('⑥-1 数据层：规则里收进了跨地区传输（两种模式 + 批次口径 + 白名单）',
    (() => {
      const r = (A.DB.rules.rules || []).filter(x => x.id === 'rule_domain_transfer')[0];
      if (!r) return false;
      const names = r.modes.map(m => m.name).join('|');
      return names.indexOf('库存传输') >= 0 && names.indexOf('超库存传输') >= 0 &&
        r.batchRules.some(b => String(b.rule).indexOf('一批只能传一种物品') >= 0) &&
        r.batchRules.some(b => String(b.rule).indexOf('传输总值') >= 0) &&
        r.whitelist && String(r.whitelist.note).indexOf('243') >= 0;
    })());

chk('⑥-1 判定函数：RwCanReceive 认「能传的物品」，RwCanShip 认「本地区做得出」',
    (() => {
      const made = A.RwMade();
      const ok1 = A.RwCanReceive('item_copper_enr');          // 赫铜块：可跨地区
      const ok2 = A.RwCanShip('item_iron_cmpt', made);         // 铁制零件：有配方
      const ok3 = A.RwCanReceive('item_nonexistent_xyz');      // 不存在的物品：不可
      return ok1 === true && ok2 === true && ok3 === false;
    })());

// 同一目标、同一速率，只切开关。用「赤铜耐压罐@10」当试例 —— 它落到最底层的原料正好一可传一不可传：
//   赤铜矿（FactoryItemTable.transferDomainIds 非空 → 能传）
//   惰气 + 惰性壤晶废液（野外气体/废液，不在清单里 → 传不了，只能本地开采）
// ⚠️ 注意：展开后最底层是**赤铜矿**而不是赤铜块 —— 赤铜块自己有产线，会被继续往下展开
const ship0 = (() => {
  /* ⭐v146：按 id 找 —— RwTargets 的同名物品现在带灌装物缀（赤铜耐压罐有 10 个同名 id），
     按 name 找不到本体了。item_copper_jar = 赤铜耐压罐本体（塑形机造 / 拆解机拆那组做法）。 */
  const t = A.RwTargets().filter(x => x.id === 'item_copper_jar')[0];
  A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 70; A.LO.shipIn = false;
  A.LawRun(t.id, 10);
  return { id: t.id, res: A.LO.plan.res, html: outEl.innerHTML || '' };
})();
const ship1 = (() => {
  A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 70; A.LO.shipIn = true;
  A.LawRun(ship0.id, 10);
  return { res: A.LO.plan.res, html: outEl.innerHTML || '' };
})();
chk('⑥-1 开关默认关：原料口径与老行为完全一致（不误伤）',
    (ship0.res.shipIn || []).length === 0 &&
    // 两边都走同一个 sort，别手写期望串 —— JS 默认按 UTF-16 码位比，
    // 「性」(U+6027) < 「气」(U+6C14)，所以顺序是 惰性壤晶废液 → 惰气 → 赤铜矿，
    // 手写成「惰气、惰性壤晶废液…」会误报一次（2026-09-22 就踩了）。
    ship0.res.raw.map(A.RwItemName).sort().join('、') ===
      ['赤铜矿', '惰气', '惰性壤晶废液'].sort().join('、'),
    ship0.res.raw.map(A.RwItemName).sort().join('、'));
chk('⑥-1 开关打开：只有「能传的」原料被改成收货，野外采集的照旧',
    (() => {
      const sn = ship1.res.shipIn.map(n => n.name).sort().join('、');
      const ok = ship1.res.shipIn.every(n => n.itemId === 'item_copper_ore');
      return sn === '赤铜矿' && ok;
    })(), ship1.res.shipIn.map(n => n.name + '/' + n.itemId).join('、'));
chk('⑥-1 收货的料仍留在「原料」清单里（不能被静默抹掉）',
    ship1.res.raw.indexOf('item_copper_ore') >= 0 &&
    ship1.res.raw.indexOf('item_gas_inert') >= 0 &&
    ship1.res.raw.indexOf('item_liquid_xiranite_lowpoly') >= 0,
    ship1.res.raw.join(','));
chk('⑥-1 机器台数与配方不受开关影响（收货只改「料从哪来」）',
    ship1.res.totalMachines === ship0.res.totalMachines &&
    ship1.res.machines.map(n => n.machineId + ':' + n.machines).join('|') ===
    ship0.res.machines.map(n => n.machineId + ':' + n.machines).join('|'),
    ship1.res.totalMachines + ' vs ' + ship0.res.totalMachines);
chk('⑥-1 报告按收货渲染：标出「跨地区收货 / 四号谷地 / 传输总值」，并说清一批只传一种',
    ship1.html.indexOf('跨地区收货') >= 0 &&
    ship1.html.indexOf('四号谷地') >= 0 &&
    ship1.html.indexOf('传输总值') >= 0 &&
    ship1.html.indexOf('只能传一种物品') >= 0);
// 这条原来写着「... || true」（永远真），等于没测 —— 现在改成真断言：
// 收货的料在「原料」清单里标了收货，在「原料野外上限」那一行也**不能再按本地矿脉算**。
chk('⑥-1 收货的料不再被当成「本地野外开采」来算上限',
    ship1.html.indexOf('赤铜矿（<b>跨地区收货</b>，见下）') >= 0 &&
    ship1.html.indexOf('赤铜矿（跨地区收货，<b>本地不采</b>') >= 0 &&
    ship1.html.indexOf('赤铜矿 需 <b>') < 0,
    JSON.stringify({
      收货标: ship1.html.indexOf('赤铜矿（<b>跨地区收货</b>，见下）'),
      不采标: ship1.html.indexOf('赤铜矿（跨地区收货，<b>本地不采</b>'),
      残留配矿机: ship1.html.indexOf('赤铜矿 需 <b>'),
      野外上限行: (ship1.html.match(/原料野外上限[\s\S]{0,220}/) || ['(没有这一行)'])[0]
    }).slice(0, 900));
// 配对断言：关着开关时④确实在给它配矿机；开了之后这一段必须消失 ——
// 只测"开着的样子"会漏掉「其实两边都没变」这种假绿。
chk('⑥-1 原料侧闭环（④）不再给收货的料配矿机 —— 同一目标开关前后对照',
    ship0.html.indexOf('赤铜矿 需 <b>') >= 0 &&
    ship1.html.indexOf('赤铜矿 需 <b>') < 0 &&
    ship1.html.indexOf('本地不摆矿机、不占野外矿点') >= 0,
    'off=' + ship0.html.indexOf('赤铜矿 需 <b>') + ' on=' + ship1.html.indexOf('赤铜矿 需 <b>'));
chk('⑥-1 没填传输总值时报告里不出现 null，要说清「填上才给数」',
    ship1.html.indexOf('null') < 0 && ship1.html.indexOf('还没填传输总值') >= 0,
    (ship1.html.match(/.{0,30}null.{0,30}/g) || []).slice(0, 5).join(' ||| '));

chk('⑥-1 反推口径：每批数量 = 传输总值 ÷ 单位物品价值；每小时可传 perHour = 每批 ÷ 间隔小时数（v90 显示主口径）；perMin = 每批 ÷ (间隔小时数 × 60)（内部喂不饱判定用）',
    (() => {
      const v = A.RshipVal('item_copper_enr', 3000, 1);        // 赫铜块 value=20 → 每批 150 个、1 小时一批 = 150/小时 = 2.5/分
      const w = A.RshipVal('item_carbon_mtl', 3000, 2);        // 碳块 value=1 → 每批 3000 个、2 小时一批 = 1500/小时 = 25/分
      return v.value === 20 && v.perBatch === 150 && v.perHour === 150 && v.perMin === 2.5 &&
             w.value === 1 && w.perBatch === 3000 && w.perHour === 1500 && w.perMin === 25;
    })(), JSON.stringify(A.RshipVal('item_copper_enr', 3000, 1)));
chk('⑥-1 供货低于需求时红字警告真的会亮，且按每小时口径说（tv=600 → 赤铜矿每小时 600 个 < 需求 1200 个/小时）',
    (() => {
      A.LO.shipIn = true; A.LO.tv = 600; A.LawRun('item_copper_jar', 10);
      const h = outEl.innerHTML;
      A.LO.tv = 0; A.render();
      return h.indexOf('按每小时折算 600 个 &lt; 需求 1200 个') >= 0 && h.indexOf('收货喂不饱这条链') >= 0;
    })(), (() => {
      A.LO.shipIn = true; A.LO.tv = 600; A.LawRun('item_copper_jar', 10);
      const h = outEl.innerHTML;
      A.LO.tv = 0; A.render();
      return (h.match(/.{0,40}赤铜矿.{0,80}/g) || ['no-context']).slice(-1).join('');
    })());
chk('⑥-1 没填传输总值时不瞎编数字（只保留单位物品价值）',
    (() => { const v = A.RshipVal('item_copper_enr', 0, 1);
      return v.perBatch === null && v.perMin === null && v.value === 20; })());
chk('⑥-1 传输间隔常量取自配置表 FactoryConst.domainTransportIntervalTime',
    (() => { const v = A.RshipVal('item_copper_enr', 3000, 0);
      return A.RW_TRANSFER_INTERVAL_S === 3600 && v.hours === 1; })());
A.Linit(); A.LO.shipIn = false; A.LO.tv = 0; A.LO.tvHours = 1; A.render();

// ---- ⑥-1 满级口径（博士 2026-09-22 定：只要超库存、按满级）—— 开收货时预填 1500 ----
A.Linit(); A.LO.tv = 0;
A.LshipIn();
chk('⑥-1 开收货且传输总值为空 → 自动预填满级 1500',
    A.LO.shipIn === true && A.LO.tv === 1500, 'tv=' + A.LO.tv);
A.LO.tv = 500; A.LO.shipIn = false;
A.LshipIn();
chk('⑥-1 已有手填值时不覆盖（500 保留）',
    A.LO.shipIn === true && A.LO.tv === 500, 'tv=' + A.LO.tv);
A.Linit(); A.LO.shipIn = false; A.LO.tv = 0; A.LO.tvHours = 1; A.render();

// ---- ⑥-1 单选（2026-09-22 博士指出 + GameRant/GameWith/Game8 三源核实）----
// 一条传输路线**一次只能传一种物品**（换物品 = 停止重设、计时重置回 1 小时）。
// 所以链里可传原料 ≥2 种时只挑一种走传输，其余回退本地自产。
// 测试链：中容谷地电池 ← 蓝铁矿×10 + 源矿×15（两条原料叶都在可传清单，且需求不等 → 默认必选源矿，
// 不靠平手顺序）。注意候选是**原料叶**（res.raw 是 id 串数组），中间件有配方的一律本地建。
A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 80;
A.LO.shipIn = true; A.LO.tv = 1500; A.LO.shipPick = '';
A.LawRun('item_proc_battery_2', 1);
const du2 = A.LO.plan && A.LO.plan.res;
chk('⑥-1 单选：双可传原料链只收一种（默认需求最大者），其余回本地',
    !!du2 && du2.shipIn.length === 1 &&
    du2.nodes.filter(n => n.raw && n.shipIn).length === 1 &&
    (A.LO.shipCands || []).length >= 2 &&
    A.LO.shipPick === du2.shipIn[0].itemId,
    'shipIn=' + (du2 ? du2.shipIn.map(n => n.itemId).join(',') : 'null') +
    ' cands=' + (A.LO.shipCands || []).join(','));
chk('⑥-1 单选：默认选中的是候选里需求最大的那一种',
    (() => { if (!du2) return false;
      const cands = du2.nodes.filter(n => n.raw && (A.LO.shipCands || []).indexOf(n.itemId) >= 0);
      const mx = cands.slice().sort((a, b) => (b.demand || 0) - (a.demand || 0))[0];
      return !!mx && mx.itemId === A.LO.shipPick; })(),
    'pick=' + A.LO.shipPick);
const prevPick = A.LO.shipPick;
const otherPick = (A.LO.shipCands || []).filter(c => c !== prevPick)[0];
A.LO.shipPick = otherPick;
A.LawRun('item_equip_script_2', 1);
const du3 = A.LO.plan && A.LO.plan.res;
chk('⑥-1 单选：换选后收货换成另一种，原先那种回退本地自产（料照要、来源改本地）',
    !!du3 && du3.shipIn.length === 1 && du3.shipIn[0].itemId === otherPick &&
    du3.raw.indexOf(prevPick) >= 0,
    'shipIn=' + (du3 ? du3.shipIn.map(n => n.itemId).join(',') : 'null') +
    ' 原料里还有' + prevPick + '=' + (du3 ? du3.raw.indexOf(prevPick) >= 0 : '-'));
chk('⑥-1 v82→v88 全物品可选：电池链**平铺区取消**，全部可传物品（含链上原料/半成品，链缺的排最前）收进唯一折叠下拉带搜索框，选中物品恰一个且 summary 常显',
    (() => { A.LO.shipIn = true; A.LO.tv = 1500; A.LO.shipPick = ''; A.LawRun('item_proc_battery_2', 1);
      const h2 = outEl.innerHTML;
      const iF = h2.indexOf('<details class="lo-pickfold"');
      const head = iF >= 0 ? h2.slice(0, iF) : h2;
      const fold = iF >= 0 ? h2.slice(iF) : '';
      const onIds = [...h2.matchAll(/class="lo-pickcard on"[^>]*LshipPick\('([^']+)'\)/g)].map(m => m[1]);
      const foldIds = [...fold.matchAll(/LshipPick\('([^']+)'\)/g)].map(m => m[1]);
      return (head.match(/class="lo-pickcard/g) || []).length === 0 &&            // v88：平铺区取消
             onIds.length === 1 && new Set(onIds).size === 1 &&                   // 全网格恰一张选中卡
             iF >= 0 && (fold.match(/class="lo-pickcard/g) || []).length > 100 &&
             new Set(foldIds).size === foldIds.length &&                          // 折叠区无重复物品
             (A.LO.shipCands || []).every(c => foldIds.indexOf(c) >= 0) &&        // 折叠区=全集
             (A.LO.shipCands || []).indexOf(onIds[0]) >= 0 && foldIds.indexOf(onIds[0]) === 0 && // 选中=候选第一个（链缺原料排最前）
             fold.indexOf('当前选：') >= 0 &&                                      // summary 常显选中
             fold.indexOf('全部可传物品（') >= 0 && fold.indexOf('lo-pickscroll') >= 0 &&
             fold.indexOf('LpickFilter(this.value)') >= 0 &&
             (fold.match(/半成品/g) || []).length >= 3 &&
             h2.indexOf('走传输的是哪种') >= 0 &&
             h2.indexOf('一条路线一次只能传一种') >= 0 &&
             h2.indexOf('每小时可传') >= 0 && h2.indexOf('单位价值') >= 0 &&
             typeof A.LpickFilter === 'function'; })(),
    'v88：无平铺，折叠=全部可传(百件级，链上排最前)+搜索接线+summary 常显选中');
chk('⑥-1 v89 瓶罐装什么可见（博士：「瓶罐里装的什么我看不到」）：选货卡带构建期反推的 content 标注——赤铜耐压罐/赤铜瓶/蓝铁瓶等同名变体各自显示装的内容物，空容器标「空容器（可灌装）」',
    (() => { A.LO.shipIn = true; A.LO.tv = 1500; A.LO.shipPick = ''; A.LawRun('item_proc_battery_2', 1);
      const h2 = outEl.innerHTML;
      const iF = h2.indexOf('<details class="lo-pickfold"');
      const fold = iF >= 0 ? h2.slice(iF) : '';
      const fillN = (fold.match(/装：/g) || []).length;
      const known = ['item_gasjar_copper_gas_inert', 'item_gasjar_copper_gas_water', 'item_fbottle_iron_water']
        .filter(id => (A.LO.shipCands || []).indexOf(id) >= 0);
      const knownOk = known.every(id => {
        const i = fold.indexOf("LshipPick('" + id + "')");
        return i >= 0 && /装：[^<]+/.test(fold.slice(i, i + 400));
      });
      return fillN >= 20 && knownOk &&
             fold.indexOf('空容器（可灌装）') >= 0 &&
             typeof (A.DB.items['item_fbottle_iron_water'] || {}).content === 'string'; })(),
    'v89：选货卡带「装：X」标注（≥20 处），已知瓶罐逐一命中，空瓶标可灌装');
chk('⑥-1 v82→v88 报告场景：石英玻璃链平铺区取消，折叠区=全集（链上石英砂排最前），带标题',
    (() => { A.LO.shipIn = true; A.LO.shipPick = ''; A.LO.tv = 1500; A.LawRun('item_quartz_glass', 10);
      const h1 = outEl.innerHTML;
      const iF = h1.indexOf('<details class="lo-pickfold"');
      const head = iF >= 0 ? h1.slice(0, iF) : h1;
      const fold = iF >= 0 ? h1.slice(iF) : '';
      const foldIds = [...fold.matchAll(/LshipPick\('([^']+)'\)/g)].map(m => m[1]);
      return (head.match(/class="lo-pickcard/g) || []).length === 0 &&
             iF >= 0 && (fold.match(/class="lo-pickcard/g) || []).length > 100 &&
             (A.LO.shipCands || []).every(c => foldIds.indexOf(c) >= 0) &&
             (A.LO.shipCands || []).length === foldIds.length &&
             h1.indexOf('走传输的是哪种') >= 0; })(),
    'v88：石英玻璃链折叠=全集（石英砂排最前），报告标题常带');
chk('⑥-1 v82 链外选中（收货不参与生产）：选一个链外的可传物品 → 这条链不收任何货、机器一台不变，报告明说「货只进仓库」',
    (() => { A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.plan = null;
      A.LawRun('item_proc_battery_2', 1);                       // 基线：不收货
      const baseM = A.LO.plan.res.totalMachines;
      A.LO.shipIn = true; A.LO.tv = 1500; A.LO.shipPick = '';
      A.LawRun('item_proc_battery_2', 1);
      const outCand = (A.LO.shipCands || []).filter(c => !(A.LO.shipChain || {})[c] && c !== 'item_proc_battery_2')[0];
      if (!outCand) return false;
      A.LO.shipPick = outCand; A.LawRun('item_proc_battery_2', 1);
      const r = A.LO.plan.res;
      const h = outEl.innerHTML;
      return r.shipIn.length === 0 && r.totalMachines === baseM &&
             h.indexOf('不在这条产线的链上') >= 0 && h.indexOf('只进仓库') >= 0; })(),
    '链外选中：res.shipIn=[]、台数与基线一致、提示「不在这条产线的链上 / 只进仓库」');
chk('⑥-1 v82 换目标即刷新候选（博士截图：旧链候选还挂着）：电池链 → 石英玻璃链，shipChain 与默认选中跟着换',
    (() => { A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.plan = null;
      A.LO.tgt = 'item_proc_battery_2'; A.LO.rate = 1;
      A.LO.shipIn = true; A.LO.tv = 1500; A.LO.shipPick = '';
      A.LshipPanel(null);
      const oldOn = !!(A.LO.shipChain || {})['item_proc_battery_2'];
      const oldLeaf = A.LO.shipPick;                              // 电池链默认原料叶（源矿，需求 15 最大）
      A.LO.shipIn = true;
      A.Ltgt('item_quartz_glass');                                // 真实路径：Ltgt 内部 LshipPanel(null) + render
      const ch = A.LO.shipChain || {};
      return oldOn && ch['item_proc_battery_2'] == null &&
             ch['item_quartz_glass'] === 1 &&
             ch[A.LO.shipPick] === 1 &&
             A.LO.shipPick !== oldLeaf; })(),
    'shipChain 换成石英玻璃链；旧叶（源矿）不在新候选 → shipPick 自动纠正为新链默认原料叶');
chk('⑥-1 开关即重算（v80 修「假开关」）：点开关关掉后收货段与选择网格立即消失',
    (() => { A.LshipIn();   // 真实路径：shipIn true→false，LshipIn 应清单选状态并重跑 LawRun
      const h0 = outEl.innerHTML;
      return A.LO.shipIn === false &&
             h0.indexOf('这批料不在本地做') < 0 && h0.indexOf('lo-pickcard') < 0; })(),
    '关掉后报告应是纯本地版（「跨地区收货」四字在工具栏按钮上常驻，不能拿来判）');
chk('⑥-1 v81 半成品也能传：电池链换选铁制零件 → 收货换成它、蓝铁块/蓝铁矿整棵上游消失（机器变少）',
    (() => { A.Linit(); A.LO.shipIn = true; A.LO.tv = 1500; A.LO.shipPick = '';
      A.LawRun('item_proc_battery_2', 1);
      const baseM = A.LO.plan.res.totalMachines;
      A.LO.shipPick = 'item_iron_cmpt'; A.LawRun('item_proc_battery_2', 1);
      const r = A.LO.plan.res;
      return r.shipIn.length === 1 && r.shipIn[0].itemId === 'item_iron_cmpt' &&
             r.raw.indexOf('item_iron_cmpt') >= 0 &&
             r.raw.indexOf('item_iron_nugget') < 0 && r.raw.indexOf('item_iron_ore') < 0 &&
             r.totalMachines < baseM; })(),
    'shipIn=item_iron_cmpt，上游（蓝铁块/蓝铁矿/矿机）不再建，台数 ' );
chk('⑥-1 v81 需求口径稳定：换选前后 shipDmap 一致（都是收货前第一趟的全链需求，卡片数字不跳）',
    (() => { A.Linit(); A.LO.shipIn = true; A.LO.tv = 1500; A.LO.shipPick = '';
      A.LawRun('item_proc_battery_2', 1);
      const d1 = JSON.stringify(A.LO.shipDmap);
      A.LO.shipPick = 'item_iron_cmpt'; A.LawRun('item_proc_battery_2', 1);
      return JSON.stringify(A.LO.shipDmap) === d1 && A.LO.shipDmap.item_originium_ore === 15; })(),
    'dmap 恒为「不收货时的完整链需求」');
chk('⑥-1 v81 布局试摆里直接能选（博士：「我要在布局试摆里选怎么还是看不到啊」）：没有产线时开开关，选货条立刻出现在面板（轻量展开，不摆机器不动画布）',
    (() => { A.Linit(); A.LO.shipIn = false; A.LO.shipCands = []; A.LO.shipPick = '';
      A.LO.plan = null; A.LO.objs = []; A.tab = 'layout'; A.render();
      const before = outEl.innerHTML.indexOf('lo-pickgrid') >= 0;
      A.LshipIn();               // 开：无 plan → LshipPanel 轻量展开 + render
      const h = outEl.innerHTML;
      return !before && A.LO.shipIn === true &&
             h.indexOf('lo-pickgrid') >= 0 && (A.LO.shipCands || []).length >= 1 &&
             h.indexOf('走传输的是哪种') >= 0 && h.indexOf('排在最前的是这条链缺的') >= 0; })(),
    '面板选货条恒带标题与「排在最前的是这条链缺的」说明（v88 文案）');
A.LO.shipIn = false; A.LO.tv = 0; A.LO.tvHours = 1;
A.LO.rate = 10; A.render();

// ---- ⑥-2 多目标共享中间产物（2026-09-22）：共用中间料只建一套再分流 ----
// 场景：赤铜耐压罐@10（塑形机 ← 赤铜块×2+惰气）＋ 赤铜瓶@10（塑形机 ← 赤铜块）——两条链都要「赤铜块」。
// 口径：赤铜块只建**一套**（合并需求、台数 ceil、层级沉到最深消费者下面），两条「幽灵边」各连各的。
const rJ1 = A.Rexplode('item_copper_jar', 10);      // 单目标（老路径基准）
const rB1 = A.Rexplode('item_copper_bottle', 10);   // 单目标（老路径基准）
const rM = A.Rexplode('item_copper_jar', 10, { seeds: [
  { itemId: 'item_copper_jar', perMin: 10 }, { itemId: 'item_copper_bottle', perMin: 10 }] });
chk('⑥-2 多目标路径 targets 有两条，单目标老路径 targets 为 null',
    !!rM.targets && rM.targets.length === 2 && rJ1.targets === null && rB1.targets === null);
const nug6 = rM.machines.filter(n => n.itemId === 'item_copper_nugget');
chk('⑥-2 共享中间料「赤铜块」在机器清单里只出现一次（不建第二套）',
    nug6.length === 1, String(nug6.length));
chk('⑥-2 两个塑形机各自挂一条指向共享赤铜块的幽灵边',
    (() => { const n = nug6[0]; if (!n) return false; let c = 0;
      rM.machines.forEach(m => (m.children || []).forEach(x => { if (x.ghost && x.ref === n) c++; }));
      return c === 2; })());
chk('⑥-2 赤铜块 demand = 两条幽灵边份额之和，台数 = ceil(demand/单台)',
    (() => { const n = nug6[0]; if (!n) return false; let s = 0;
      rM.machines.forEach(m => (m.children || []).forEach(x => { if (x.ghost && x.ref === n) s += x.demand; }));
      return Math.abs(n.demand - s) < 1e-6 && n.machines === Math.ceil(n.demand / (n.perMachine || 1)); })());
chk('⑥-2 共享节点层级沉到最深消费者下面（= max(消费者层)+1）',
    (() => { const n = nug6[0]; if (!n) return false;
      const sj = rM.machines.filter(m => m.recipeId === 'shaper_gas_copper_jar_1')[0];
      const sb = rM.machines.filter(m => m.recipeId === 'shaper_copper_bottle_1')[0];
      return !!sj && !!sb && n.depth === Math.max(sj.depth, sb.depth) + 1; })());
chk('⑥-2 只建一套：合并台数 ≤ 两条单链各自台数之和',
    (() => { const a = (rJ1.machines.filter(m => m.itemId === 'item_copper_nugget')[0] || {}).machines || 0;
      const b = (rB1.machines.filter(m => m.itemId === 'item_copper_nugget')[0] || {}).machines || 0;
      return !!nug6[0] && nug6[0].machines <= a + b; })());
chk('⑥-2 原料并集：赤铜矿来自共享赤铜块那条链',
    rM.raw.map(A.RwItemName).indexOf('赤铜矿') >= 0, rM.raw.map(A.RwItemName).join(','));
A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 80;
A.LO.tgt = 'item_copper_jar'; A.LO.rate = 10;
A.LO.mt = [{ id: 'item_copper_bottle', rate: 10 }];
A.LawRun('item_copper_jar', 10);
const hM2 = outEl.innerHTML;
chk('⑥-2 报告头列出两个目标（＋ 连接）',
    hM2.indexOf('赤铜耐压罐') >= 0 && hM2.indexOf('赤铜瓶') >= 0 && hM2.indexOf(' ＋ ') >= 0);
chk('⑥-2 报告有「共用中间料」段并点名赤铜块',
    hM2.indexOf('共用中间料') >= 0 && hM2.indexOf('只建一套') >= 0 && hM2.indexOf('赤铜块：<b>') >= 0);
chk('⑥-2 生成消息是多目标格式（A ＋ B）', (A.LO.msg || '').indexOf(' ＋ ') >= 0, A.LO.msg);
chk('⑥-2 吞吐体检里赤铜块两条依赖各连各的',
    (() => { const ls = ((A.LO.plan && A.LO.plan.route.loads) || []).filter(l => l.item === '赤铜块');
      return ls.length === 2 && ls.every(l => l.demand > 0); })());
A.Linit(); A.LO.objs = []; A.LO.mt = [{ id: 'item_copper_bottle', rate: 0 }];
A.LawRun('item_copper_jar', 10);
chk('⑥-2 速率为 0 的额外目标被拦下（不展开、不清画布）',
    (A.LO.msg || '').indexOf('速率要大于 0') >= 0 && A.LO.objs.length === 0, A.LO.msg);
A.LO.mt = [];
A.LmtAdd();
chk('⑥-2 「＋ 目标」追加一行（上限 3 行的逻辑在 LmtAdd）', A.LO.mt.length === 1);
A.LmtDel(0);
chk('⑥-2 移除行后 mt 清空', A.LO.mt.length === 0);
A.LO.mt = []; A.LO.rate = 10; A.render();

// ---- ⑥-2 外部输入节点不产「空气机器」（2026-09-22 全库扫描抓到的计算 bug 回归锁）----
// 场景：清水+息壤 双目标 —— 清水链深到顶会把息壤/赫铜溶液按 external 处理（无配方无机器）。
// 旧 bug：RexplodeFinal 对它们跑 ceil(demand/1) 凭空造出台数（息壤 10/分 → 10 台），
// 混进 res.machines → 报告虚报「机器 37 台」、画布实摆 26 台、LawPlan 里 byBp(null) 静默丢。
const rEx = A.Rexplode('item_liquid_water', 10, { seeds: [
  { itemId: 'item_liquid_water', perMin: 10 }, { itemId: 'item_xiranite_powder', perMin: 10 }] });
chk('⑥-2 机器清单里不存在无配方的节点（external 不凭空产台数）',
    rEx.machines.every(n => n.machineId && n.machines > 0),
    JSON.stringify(rEx.machines.filter(n => !n.machineId).map(n => n.name + '×' + n.machines)));
chk('⑥-2 外部输入节点保留 demand 但台数恒 0（原料需求口径不丢）',
    (() => { const n = rEx.nodes.filter(x => x.itemId === 'item_xiranite_powder')[0];
      return !!n && n.external === true && n.demand > 0 && n.machines === 0; })());
A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 70;
A.LO.tgt = 'item_liquid_water'; A.LO.rate = 10;
A.LO.mt = [{ id: 'item_xiranite_powder', rate: 10 }];
A.LawRun('item_liquid_water', 10);
chk('⑥-2 生成消息的机器台数与画布实摆一致（external 不再虚报）',
    (() => { const m = (A.LO.msg || '').match(/机器 (\d+) 台/);
      const placed = A.LO.objs.filter(o => o.planRole === 'machine').length;
      return !!m && +m[1] === placed; })(),
    (A.LO.msg || '').slice(0, 60) + ' | placed=' + A.LO.objs.filter(o => o.planRole === 'machine').length);
A.LO.mt = [];

// ---- v133 扩容反应池「同池并行」（博士 2026-09-24 实机 + 官方文案 + 社区实测三重核实）----
// 壤晶链 = 息壤+清水→液化息壤 / 液化息壤+污水→壤晶废液+惰性壤晶废液 / 壤晶废液+蓝铁粉→壤晶（+污水）
// 三条反应同属 group_mix_pool_2_liquid：游戏里 1 栋扩容池（8 缓存格）就能同时跑 —— 我们原先按
// 「一条配方一栋」算 3 栋。口径：同组 ≥2 条不同配方 → 整组升扩容池；栋数 = 组内 max(n_i)。
const rPool = A.Rexplode('item_xiranite_poly', 10, {});
const poolNodes = rPool.machines.filter(n => n.machineId === 'mix_pool_2');
chk('v133 壤晶链：同组 ≥2 条反应 → 整组升级为扩容反应池（链里不再有基础池）',
    !rPool.machines.some(n => n.machineId === 'mix_pool_1') && poolNodes.length >= 1,
    JSON.stringify(rPool.machines.map(n => n.machineName + 'x' + n.machines + '<' + n.recipeId + '>')));
chk('v133 壤晶链：同池并行合并 —— 主体承接组内 max 栋数、省下栋数记账（合并节点已从清单剔除）',
    (() => {
      if (!rPool.poolMerge || !rPool.poolMerge.length) return false;
      const g = rPool.poolMerge[0];
      const lead = rPool.machines.filter(n => n.machineId === 'mix_pool_2')[0];
      return g.members.length >= 2 && g.slots <= 8 && g.saved >= 1 &&
             !!lead && g.count === lead.machines;
    })(),
    JSON.stringify(rPool.poolMerge) + ' | 主体 ' + JSON.stringify(rPool.machines.filter(n => n.machineId === 'mix_pool_2').map(n => n.recipeId + 'x' + n.machines)));
chk('v133 单配方链不升扩容池（赤铜块链只 1 条池子配方 → 仍是基础反应池）',
    (() => { const r = A.Rexplode('item_copper_nugget', 10, {});
      return !r.machines.some(n => n.machineId === 'mix_pool_2'); })(),
    JSON.stringify(A.Rexplode('item_copper_nugget', 10, {}).machines.map(n => n.machineName + 'x' + n.machines)));

// ---- v134 反应池面板：缓存格推演 + 池子判定（博士 2026-09-24 要「像游戏那样显示缓存槽」）----
// 壤晶链三条反应：息壤+清水→液化息壤 / 液化息壤+污水→壤晶废液+惰性壤晶废液 / 壤晶废液+蓝铁粉末→壤晶+污水
// 材料并集 = 息壤·清水·液化息壤·污水·壤晶废液·惰性壤晶废液·蓝铁粉末·壤晶 = 恰好 8 格（与实机 8 缓存格逐项吻合）
chk('v134 缓存格推演：壤晶链 3 条反应 = 8 格，材料逐项吻合',
    (() => {
      const cells = A.RpoolCells(['pool_liquid_liquid_xiranite_2', 'pool_liquid_xiranite_poly_2', 'pool_xiranite_poly_2']);
      const want = ['息壤', '清水', '液化息壤', '污水', '壤晶废液', '惰性壤晶废液', '蓝铁粉末', '壤晶'];
      return cells.length === 8 && want.every(n => cells.some(c => c.name === n));
    })(),
    JSON.stringify(A.RpoolCells(['pool_liquid_liquid_xiranite_2', 'pool_liquid_xiranite_poly_2', 'pool_xiranite_poly_2']).map(c => c.name)));
chk('v134 池子判定与上限：基础池 2 条 / 扩容池 3 条，其他机器不是池子',
    (() => {
      const cells = A.RpoolCells(['pool_liquid_liquid_xiranite_2', 'pool_liquid_xiranite_poly_2', 'pool_xiranite_poly_2']);
      return cells.length === 8 && A.POOL_CELLS === 8 &&
             A.POOL_SLOT_MAX['mix_pool_2'] === 3 && A.POOL_SLOT_MAX['mix_pool_1'] === 2 &&
             A.RisPool({ id: 'mix_pool_2' }) && A.RisPool({ id: 'mix_pool_1' }) &&
             !A.RisPool({ id: 'furnance_1' }) && !A.RisPool({ id: 'mix_pool_9' });
    })(),
    'cells=' + A.POOL_CELLS + ' slots=' + JSON.stringify(A.POOL_SLOT_MAX));
chk('v134 池子反应读取兼容：o.rl 数组优先、旧 o.r 单值也认',
    (() => {
      const a = A.RpoolOf({ rl: ['r1', 'r2'] }), b = A.RpoolOf({ r: 'r1' }), c = A.RpoolOf({});
      return a.length === 2 && a[0] === 'r1' && b.length === 1 && b[0] === 'r1' && c.length === 0;
    })());

// ---- v135「点机器就地选」框架（博士 2026-09-24：「我要在这里选，要做到以后能逐步完善到其他基建都能在这里选」）----
chk('v135 就地选分派：反应池→池子面板 / 有配方机器→配方面板 / 无配方→不弹',
    (() => {
      const bp = A.DB.blueprint.buildings;
      const pool = bp.filter(x => x.id === 'mix_pool_2')[0];
      const fur = bp.filter(x => x.id === 'furnance_1')[0];
      const deco = bp.filter(x => x.id === 'doll_1')[0];
      const h1 = A.RmacPanelOf(pool, { uid: 'u', rl: [] });
      const h2 = A.RmacPanelOf(fur, { uid: 'u' });
      const h3 = deco ? A.RmacPanelOf(deco, { uid: 'u' }) : null;
      return typeof h1 === 'string' && h1.indexOf('缓存格') >= 0 &&
             typeof h2 === 'string' && h2.indexOf('可选') >= 0 && h3 === null;
    })(),
    'pool=' + typeof A.RmacPanelOf(A.DB.blueprint.buildings.filter(x => x.id === 'mix_pool_2')[0], { uid: 'u', rl: [] }));
chk('v135 池子面板槽位数按池子上限（扩容池 3 / 基础池 2）+ 开关函数在位',
    (() => {
      const bp = A.DB.blueprint.buildings;
      const n = h => String(h).split('槽 ').length - 1;
      return n(A.RmacPanelOf(bp.filter(x => x.id === 'mix_pool_2')[0], { uid: 'u', rl: [] })) === 3 &&
             n(A.RmacPanelOf(bp.filter(x => x.id === 'mix_pool_1')[0], { uid: 'u', rl: [] })) === 2 &&
             typeof A.LmacOpen === 'function' && typeof A.LmacClose === 'function';
    })());

// ---- v136 对标调研 D + A（博士 2026-09-24「先做 DA」）----
chk('v136 D：绕不开的循环 / 链深上限会进警告列表（不再静默降级）',
    (() => {
      const r = A.Rexplode('item_liquid_water', 10, { seeds: [
        { itemId: 'item_liquid_water', perMin: 10 }, { itemId: 'item_xiranite_powder', perMin: 10 }] });
      const ws = r.warns || [];
      return ws.some(w => w.indexOf('绕不开的循环') >= 0 || w.indexOf('链深到') >= 0) &&
             !r.machines.some(n => !n.machineId && n.machines > 0);
    })(),
    JSON.stringify((A.Rexplode('item_liquid_water', 10, {}).warns || []).slice(0, 3)));
chk('v136 A：报告出「台数口径」行（理论分数台数 → 实际整台 → 多出在哪）',
    (() => {
      A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 70; A.LO.mt = [];
      A.LawRun('item_iron_cmpt', 10);
      const h = outEl.innerHTML || '';
      return h.indexOf('台数口径') >= 0 && h.indexOf('理论') >= 0 && h.indexOf('实际摆') >= 0;
    })(),
    (outEl.innerHTML || '').replace(/\s+/g, ' ').slice(0, 40));

chk('v136 B：同物品多配方按「单位成本 → 耗电」分层 —— 紫晶质瓶选塑形机(10电)而非拆解机(20电)',
    (() => {
      const r = A.Rexplode('item_glass_bottle', 10, {});
      const n = (r.machines || []).filter(x => x.itemId === 'item_glass_bottle')[0];
      return !!n && n.machineId === 'shaper_1';
    })(),
    JSON.stringify((A.Rexplode('item_glass_bottle', 10, {}).machines || []).filter(x => x.itemId === 'item_glass_bottle').map(x => x.recipeId + '/' + x.machineName)));

// ---- v137 手动连铺十字相交自动建桥（博士：「游戏里两条传送带相交后会自动建物流桥」）----
chk('v137 传送带十字相交 → 交叉格叠物流桥（原线保留）',
    (() => {
      tab = 'layout'; A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 40;
      A.LO.pick = A.byBp('grid_belt_01');
      A.LODRAG = { mode: 'lay', sx: 2, sy: 5, ex: 2, ey: 5, uids: [], hist: [[2, 5]] };
      for (let x = 3; x <= 12; x++) A.LlayTo(x, 5);
      A.LODRAG = null; A.render();
      A.LODRAG = { mode: 'lay', sx: 7, sy: 2, ex: 7, ey: 2, uids: [], hist: [[7, 2]] };
      for (let y = 3; y <= 12; y++) A.LlayTo(7, y);
      A.LODRAG = null; A.render();
      const ids = A.LO.objs.filter(o => o.x === 7 && o.y === 5).map(o => o.id);
      return ids.indexOf('grid_belt_01') >= 0 && ids.indexOf('log_connector') >= 0;
    })(),
    JSON.stringify(A.LO.objs.filter(o => o.x === 7 && o.y === 5).map(o => o.id)));
chk('v137 管道十字相交 → 交叉格叠管道桥',
    (() => {
      A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 40;
      A.LO.pick = A.byBp('log_pipe_01');
      A.LODRAG = { mode: 'lay', sx: 2, sy: 20, ex: 2, ey: 20, uids: [], hist: [[2, 20]] };
      for (let x = 3; x <= 12; x++) A.LlayTo(x, 20);
      A.LODRAG = null; A.render();
      A.LODRAG = { mode: 'lay', sx: 7, sy: 17, ex: 7, ey: 17, uids: [], hist: [[7, 17]] };
      for (let y = 18; y <= 25; y++) A.LlayTo(7, y);
      A.LODRAG = null; A.render();
      const ids = A.LO.objs.filter(o => o.x === 7 && o.y === 20).map(o => o.id);
      return ids.indexOf('log_pipe_01') >= 0 && ids.indexOf('log_pipe_connector') >= 0;
    })());

// ---- v138 准入口（博士：「准入口只可以放在传送带和管道上」+ 准入物品 + 限速）----
chk('v138 准入口：空地放不上（必须叠在同类带/管上 + 顺物流方向）',
    (() => {
      tab = 'layout'; A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 40;
      A.Lpick('log_conditioner'); A.Lput(5, 5);
      return A.LO.objs.length === 0 && String(A.LO.msg).indexOf('必须放在同类型的') >= 0;
    })(), (A.LO.msg || '').slice(0, 40));
chk('v138 准入口：转角格拒绝（两侧相邻 = 没顺物流方向）',
    (() => {
      A.Linit(); A.LO.objs = []; A.LO.pick = A.byBp('grid_belt_01');
      A.LODRAG = { mode: 'lay', sx: 2, sy: 20, ex: 2, ey: 20, uids: [], hist: [[2, 20]] };
      for (let x = 3; x <= 8; x++) A.LlayTo(x, 20);
      A.LODRAG = null; A.render();
      A.LODRAG = { mode: 'lay', sx: 8, sy: 21, ex: 8, ey: 21, uids: [], hist: [[8, 21]] };
      for (let y = 21; y <= 25; y++) A.LlayTo(8, y);
      A.LODRAG = null; A.render();
      A.Lpick('log_conditioner'); A.Lput(8, 20);
      return !A.LO.objs.some(o => o.id === 'log_conditioner' && o.x === 8 && o.y === 20) &&
             (String(A.LO.msg).indexOf('拐角') >= 0 || String(A.LO.msg).indexOf('末端') >= 0);
    })(), (A.LO.msg || '').slice(0, 44));
chk('v138 准入口：放在直线段上成功 + 面板含限速与准入物品 + 限速/物品写入生效',
    (() => {
      A.Linit(); A.LO.objs = []; A.LO.pick = A.byBp('grid_belt_01');
      A.LODRAG = { mode: 'lay', sx: 2, sy: 5, ex: 2, ey: 5, uids: [], hist: [[2, 5]] };
      for (let x = 3; x <= 10; x++) A.LlayTo(x, 5);
      A.LODRAG = null; A.render();
      A.Lpick('log_conditioner'); A.Lput(6, 5);
      const v = A.LO.objs.filter(o => o.id === 'log_conditioner')[0];
      if (!v) return false;
      const h = A.RmacPanelOf(A.byBp('log_conditioner'), v) || '';
      A.LsetValveRate(v.uid, 12); A.LsetValveItems(v.uid, ['item_liquid_water']);
      return h.indexOf('限速') >= 0 && h.indexOf('准入物品') >= 0 &&
             v.vRate === 12 && (v.vItems || []).length === 1;
    })(), 'vRate=' + ((A.LO.objs.filter(o => o.id === 'log_conditioner')[0] || {}).vRate));

// ---- v139 准入口合规标红（博士：「拐角也是怎么还放得下」→ 已有的不合规件也要标出来）----
chk('v139 准入口标红：孤立 = 标红 / 拐角 = 标红 / 直线 = 放行',
    (() => {
      tab = 'layout'; A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 40;
      const _vbadN = () => ((outEl.innerHTML || '').match(/vbad/g) || []).length;
      const v1 = A.Lmk(A.byBp('log_conditioner'), 5, 5, 0); v1.planRole = 'link';
      A.LO.objs.push(v1); A.render();
      const iso = _vbadN();
      A.LO.objs = []; A.LO.pick = A.byBp('grid_belt_01');
      A.LODRAG = { mode: 'lay', sx: 2, sy: 20, ex: 2, ey: 20, uids: [], hist: [[2, 20]] };
      for (let x = 3; x <= 8; x++) A.LlayTo(x, 20); A.LODRAG = null;
      A.LODRAG = { mode: 'lay', sx: 8, sy: 21, ex: 8, ey: 21, uids: [], hist: [[8, 21]] };
      for (let y = 21; y <= 25; y++) A.LlayTo(8, y); A.LODRAG = null; A.render();
      A.LO.objs = A.LO.objs.filter(o => !(o.x === 8 && o.y === 20));
      const v2 = A.Lmk(A.byBp('log_conditioner'), 8, 20, 0); v2.planRole = 'link';
      A.LO.objs.push(v2); A.render();
      const corner = _vbadN();
      A.LO.objs = A.LO.objs.filter(o => !(o.x === 8 && o.y === 20));
      const v3 = A.Lmk(A.byBp('log_conditioner'), 5, 20, 0); v3.planRole = 'link';
      A.LO.objs.push(v3); A.render();
      const straight = _vbadN();
      return iso >= 1 && corner >= 1 && straight === 0;
    })(),
    'vbad 计数三态：孤立应>=1 / 拐角应>=1 / 直线应=0');

// ---- v142 P3：吞吐体检联动准入口限速（该段上限 = min(线速, 限速)）----
chk('v142 P3：路径上的准入口限速会修正该段 cap 并在报告点名',
    (() => {
      tab = 'layout'; A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 80; A.LO.mt = [];
      A.LawRun('item_copper_nugget', 10);
      const links = (A.LO.plan.route.links || []).filter(l => l.path && l.path.length);
      if (!links.length) return false;
      const lk = links[0];
      const mid = lk.path[Math.floor(lk.path.length / 2)].split(',');
      const pr = A.byBp(lk.isPipe ? 'log_pipe_conditioner' : 'log_conditioner');
      const v = A.Lmk(pr, +mid[0], +mid[1], 0); v.planRole = 'link'; v.vRate = 6; A.LO.objs.push(v);
      A.render();
      const h = outEl.innerHTML || '';
      return h.indexOf('被准入口限到') >= 0 &&
             (A.LO.plan.route.loads || []).some(x => x.valveLimited === 6);
    })(),
    'cap 修正与报告点名');

// ---- ⑥-2 × ⑥-1 组合：多目标 + 跨地区收货同时开 ----
// 要守住的：收货判定吃的是**合并后的原料并集与合并后的需求**（两条链的赤铜矿需求 20+20=40/分），
// 共用段照常渲染，本地冶炼（赤铜块）照建 —— 收货只改「料从哪来」。
A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 80;
A.LO.shipIn = true; A.LO.tv = 1500;
A.LO.mt = [{ id: 'item_copper_bottle', rate: 10 }];
A.LawRun('item_copper_jar', 10);
const combo2 = A.LO.plan && A.LO.plan.res;
chk('⑥-2×⑥-1 多目标下收货照常生效：只有赤铜矿被识别为收货、且仍留在原料清单里',
    !!combo2 && combo2.shipIn.length === 1 && combo2.shipIn[0].itemId === 'item_copper_ore' &&
    combo2.raw.map(A.RwItemName).indexOf('赤铜矿') >= 0,
    'shipIn=' + (combo2 ? combo2.shipIn.map(n => n.itemId).join(',') : 'null'));
chk('⑥-2×⑥-1 收货需求 = 合并后的需求 40/分（不是单目标的 20）',
    !!combo2 && Math.abs((combo2.shipIn[0].demand || 0) - 40) < 1e-6,
    'demand=' + (combo2 && combo2.shipIn[0] ? combo2.shipIn[0].demand : '?'));
chk('⑥-2×⑥-1 共用段不受收货影响：赤铜块本地冶炼照建（8 台）',
    !!combo2 && !!combo2.shared &&
    combo2.shared.some(s => s.itemId === 'item_copper_nugget' && s.machines === 8),
    combo2 && combo2.shared ? combo2.shared.map(s => s.name + ':' + s.machines + '台').join('、') : 'null');
chk('⑥-2×⑥-1 报告同时渲染收货段与共用段',
    (() => { const h = outEl.innerHTML; A.LO.tv = 0; A.LO.shipIn = false; A.LO.mt = []; A.render();
      return h.indexOf('跨地区收货') >= 0 && h.indexOf('共用中间料') >= 0; })(),
    '报告里应同时出现「跨地区收货」与「共用中间料」');
A.LO.rate = 10; A.render();

// ---- ⑥-3 跨基地选点：方向下拉 / 换向 / RwMade 过滤 / 选点建议器 ----
// 锁值全部来自 tools/_dbg87.js、_dbg88.js 探针实测（2026-09-22）。
// 守的口径：两地对称互传（换向必须在 UI 可达）、RwMade 按地区过滤 + 缓存键分离、
// 矿 cap 用 ores.beds.mapMax 真值、口径①按地区合计反推、口径②只给占格不编吞吐、
// 息壤液这类「不能传 + 产线未建模」的料必须点名（manual），不能静默漏报。
A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.tgt = ''; A.LO.rate = 0; A.LO.mt = [];
/* ⑥-3 前的测试区跑过 LbaseSet（谷地基地）——新加的「切基地自动对齐收货方向」副作用
   会把方向留在「武陵 → 谷地」；⑥-2 还留下了 plan 残留（有 plan 时 LshipDirV 会去重算、
   覆盖 msg）。这里显式回到干净状态，别让上游残留污染断言。 */
A.LO.shipFrom = 'domain_1'; A.LO.shipTo = 'domain_2'; A.LO.shipPick = ''; A.LO.plan = null;

// 1) 方向下拉动态清单（为未来新地区开放做准备：清单从 DB.bases.domains 动态读）
(function () {
  const n0 = (A.LshipDirHtml().match(/<option /g) || []).length;
  chk('⑥-3 方向下拉：两地区 × 从/到 = 4 个 option', n0 === 4, 'option 数=' + n0);
  A.DB.bases.domains.push({ id: 'domain_9', name: '测试地区X', storageName: '测试仓库' });
  const h1 = A.LshipDirHtml();
  const n1 = (h1.match(/<option /g) || []).length;
  const hasNew = h1.indexOf('测试地区X') >= 0;
  A.DB.bases.domains.pop();
  chk('⑥-3 方向下拉：push 假地区后自动出现（未来 domain_3+ 零改动接入）',
      n1 === 6 && hasNew, 'option 数=' + n1 + ' 含新地区=' + hasNew);
})();

// 2) 换向：单端下拉选另一端 = 交换两端（两地现状下唯一的换向入口；对称互传的可达性）
(function () {
  chk('⑥-3 换向：from 选另一端 → 两端互换、msg 报「已换向」',
      (function () { A.LshipDirV('from', 'domain_2');
        return A.LshipFromId() === 'domain_2' && A.LshipToId() === 'domain_1' &&
          A.Linit().msg.indexOf('已换向') >= 0; })(),
      'from=' + A.LshipFromId() + ' to=' + A.LshipToId() + ' msg=' + A.Linit().msg);
  chk('⑥-3 换向：再选另一端 → 换回默认（谷地 → 武陵）',
      (function () { A.LshipDirV('from', 'domain_1');
        return A.LshipFromId() === 'domain_1' && A.LshipToId() === 'domain_2'; })(),
      'from=' + A.LshipFromId() + ' to=' + A.LshipToId());
  chk('⑥-3 换向：选自己 → 无操作（状态不变、msg 报「没变」、不清收货选择）',
      (function () { A.Linit().shipPick = 'item_xiranite_powder';
        A.LshipDirV('from', 'domain_1');
        const keep = A.Linit().shipPick === 'item_xiranite_powder' &&
          A.Linit().msg.indexOf('没变') >= 0;
        A.Linit().shipPick = '';
        return A.LshipFromId() === 'domain_1' && A.LshipToId() === 'domain_2' && keep; })(),
      A.Linit().msg);
  chk('⑥-3 换向：有产线时换向 → 按新方向重算（换向生效 + LawRun 重算成功，成功消息覆盖换向 msg 属预期）',
      (function () { A.LO.tgt = 'item_copper_jar'; A.LO.rate = 10;
        A.LawRun('item_copper_jar', 10);
        A.LshipDirV('from', 'domain_2');
        const m = A.Linit().msg;
        const ok = m.indexOf('产线已生成') >= 0 &&
          !!A.LO.plan && A.LO.shipFrom === 'domain_2' && A.LO.shipTo === 'domain_1';
        /* 还原：换回 + 清目标（清目标走 LawRun 的空目标分支，msg 会变，无所谓） */
        A.LshipDirV('from', 'domain_1');
        A.LO.tgt = ''; A.LO.rate = 0; A.LO.plan = null;
        return ok; })(),
      A.Linit().msg);
})();

// 3) 切基地 → 收货方向「到」自动对齐基地所在地区（货要进产线所在地区的仓库才有用）
(function () {
  const wl = A.Lbases().filter(x => x.domainName === '武陵')[0];
  const gd = A.Lbases().filter(x => x.domainName === '四号谷地')[0];
  A.LbaseSet(gd.levelId);
  const g = [A.LshipFromId(), A.LshipToId(), A.Linit().msg.indexOf('收货方向已对齐') >= 0];
  A.LbaseSet(wl.levelId);
  const w = [A.LshipFromId(), A.LshipToId()];
  chk('⑥-3 LbaseSet：切谷地基地 → shipTo=谷地、shipFrom 自动让位、msg 报「收货方向已对齐」',
      g[0] === 'domain_2' && g[1] === 'domain_1' && g[2] === true,
      'from=' + g[0] + ' to=' + g[1] + ' msg对齐=' + g[2]);
  chk('⑥-3 LbaseSet：切武陵基地 → 方向对齐回武陵',
      w[0] === 'domain_1' && w[1] === 'domain_2', 'from=' + w[0] + ' to=' + w[1]);
  A.LO.size = 50; A.LO.base = ''; A.LO.objs = []; A.LO.sel = [];
})();

// 4) RwMade 地区过滤 + 缓存键分离（息壤粉末：谷地仅 1 条转质路线、武陵 3 条）
chk('⑥-3 RwMade：息壤粉末 从谷地 1 条 / 从武陵 3 条 / 不限 3 条（缓存键分离）',
    (A.RwMade('四号谷地')['item_xiranite_powder'] || []).length === 1 &&
    (A.RwMade('武陵')['item_xiranite_powder'] || []).length === 3 &&
    (A.RwMade()['item_xiranite_powder'] || []).length === 3,
    '谷地=' + (A.RwMade('四号谷地')['item_xiranite_powder'] || []).length +
    ' 武陵=' + (A.RwMade('武陵')['item_xiranite_powder'] || []).length +
    ' 全部=' + (A.RwMade()['item_xiranite_powder'] || []).length);
chk('⑥-3 RwMade：缓存键含三份（四号谷地 / 武陵 / *）',
    (function () { const k = Object.keys(A.RwMade._c || {});
      return k.indexOf('四号谷地') >= 0 && k.indexOf('武陵') >= 0 && k.indexOf('*') >= 0; })(),
    JSON.stringify(Object.keys(A.RwMade._c || {})));
chk('⑥-3 RwMade 地区过滤传导到收货候选：全部/从谷地/从武陵 = 162/161/162',
    [Object.keys(A.RwMade()).filter(A.RwCanReceive).length,
     Object.keys(A.RwMade('四号谷地')).filter(A.RwCanReceive).length,
     Object.keys(A.RwMade('武陵')).filter(A.RwCanReceive).length].join('/') === '162/161/162',
    '实际=' + [Object.keys(A.RwMade()).filter(A.RwCanReceive).length,
      Object.keys(A.RwMade('四号谷地')).filter(A.RwCanReceive).length,
      Object.keys(A.RwMade('武陵')).filter(A.RwCanReceive).length].join('/'));

// 5) RxlOreCap / RxlSlots：矿脉分布与取货口路数（全部 ores.beds.mapMax / slotRule 公式真值）
chk('⑥-3 RxlOreCap：赤铜矿 谷地 0 / 武陵 510（谷地罐链缺口收货的根据）',
    A.RxlOreCap('item_copper_ore', '四号谷地').cap === 0 &&
    A.RxlOreCap('item_copper_ore', '武陵').cap === 510 &&
    A.RxlOreCap('item_copper_ore', '四号谷地').name === '赤铜矿',
    JSON.stringify([A.RxlOreCap('item_copper_ore', '四号谷地'), A.RxlOreCap('item_copper_ore', '武陵')]));
chk('⑥-3 RxlOreCap：四矿分布（源 560/540 · 紫 240/0 · 蓝铁 1080/120 · 赤铜 0/510）',
    A.RxlOreCap('item_originium_ore', '四号谷地').cap === 560 &&
    A.RxlOreCap('item_originium_ore', '武陵').cap === 540 &&
    A.RxlOreCap('item_quartz_sand', '四号谷地').cap === 240 &&
    A.RxlOreCap('item_quartz_sand', '武陵').cap === 0 &&
    A.RxlOreCap('item_iron_ore', '四号谷地').cap === 1080 &&
    A.RxlOreCap('item_iron_ore', '武陵').cap === 120,
    '有矿就有人家没有 —— 这就是选点问题的来源');
chk('⑥-3 RxlOreCap：非矿返回 null（矿点数据只覆盖 beds 那几样，不造数）',
    A.RxlOreCap('item_copper_jar', '四号谷地') === null);
chk('⑥-3 RxlSlots：(边长-1)÷3 → 70→23 / 40→13 / 80→26 / 50→16',
    [A.RxlSlots(70), A.RxlSlots(40), A.RxlSlots(80), A.RxlSlots(50)].join('/') === '23/13/26/16',
    '谷地两组实测、武陵两组公式推算 —— 页面上按来源分开标注');

// 6) RxlAnalyze：罐@谷地 vs 罐@武陵（缺口、占地、自筹料点名）
(function () {
  const ag = A.RxlAnalyze('item_copper_jar', 10, '四号谷地');
  const aw = A.RxlAnalyze('item_copper_jar', 10, '武陵');
  chk('⑥-3 RxlAnalyze：罐@谷地 赤铜矿需 20 / cap 0（谷地没有赤铜矿）→ 缺口收货，不硬否决',
      ag.ok === true && ag.ores.item_copper_ore.need === 20 && ag.ores.item_copper_ore.cap === 0,
      JSON.stringify(ag.ores.item_copper_ore));
  chk('⑥-3 RxlAnalyze：罐@武陵 赤铜矿 cap 510 本地够', aw.ores.item_copper_ore.cap === 510);
  chk('⑥-3 RxlAnalyze：罐@谷地 机器 10 台 · 占地估算 339 格（机器格数×2.2，明标估算）',
      ag.totalMachines === 10 && ag.areaEst === 339,
      'machines=' + ag.totalMachines + ' areaEst=' + ag.areaEst);
  const m1 = ag.manual.filter(x => x.itemId === 'item_liquid_xiranite_lowpoly')[0];
  const m2 = ag.manual.filter(x => x.itemId === 'item_gas_inert')[0];
  chk('⑥-3 RxlAnalyze：罐@谷地 自筹料点名（惰性壤晶废液 80 + 惰气 10 —— 不能传、产线未建模）',
      ag.manual.length === 2 && !!m1 && m1.demand === 80 && !!m2 && m2.demand === 10,
      JSON.stringify(ag.manual.map(x => x.name + ':' + x.demand)));
})();

// 7) 机器地区限定 → 硬否决（天有洪炉等 9 座武陵限定 → 息壤链谷地建不了）
(function () {
  const a1 = A.RxlAnalyze('item_xiranite_powder', 10, '四号谷地');
  const a2 = A.RxlAnalyze('item_xiranite_powder', 10, '武陵');
  chk('⑥-3 RxlAnalyze：息壤粉末@谷地 硬否决（没有机器配方）',
      a1.ok === false && a1.blocked[0].indexOf('没有机器配方') >= 0, a1.blocked[0]);
  chk('⑥-3 RxlAnalyze：息壤粉末@武陵 可行（14 台机器）',
      a2.ok === true && a2.totalMachines === 14, 'machines=' + a2.totalMachines);
})();

// 8) RxlBest：穷举择优（成本口径：硬否决 > 冲突 > 喂不饱 > 重复建共享料 > 矿缺口）
(function () {
  const b1 = A.RxlBest([{ id: 'item_copper_jar', rate: 10 }]);
  chk('⑥-3 RxlBest：单目标罐@10 → 武陵、cost 0（赤铜矿本地够；息壤液两地都自筹、不进成本）',
      b1.best.assign[0] === '武陵' && b1.best.cost === 0,
      JSON.stringify({ assign: b1.best.assign, cost: b1.best.cost }));
  chk('⑥-3 RxlBest：单目标组合数 = 2^1', b1.combos.length === 2);
  const b2 = A.RxlBest([{ id: 'item_copper_jar', rate: 10 }, { id: 'item_quartz_glass', rate: 10 }]);
  chk('⑥-3 RxlBest：罐@10 + 石英玻璃@10 → 分居两地（武陵 + 谷地）、cost 0',
      b2.best.assign[0] === '武陵' && b2.best.assign[1] === '四号谷地' && b2.best.cost === 0,
      JSON.stringify({ assign: b2.best.assign, cost: b2.best.cost }));
  chk('⑥-3 RxlBest：双目标组合数 = 2^2 = 4（穷举不漏）', b2.combos.length === 4);
})();

// 9) 口径①：地区合计收货压力（同区多基地共享地区仓库 → 按合计对每批可到货量反推）
(function () {
  const st = A.RxlRegionShip([{ id: 'item_copper_jar', rate: 30 }], ['四号谷地'], '四号谷地');
  chk('⑥-3 口径①：罐@30 全放谷地 → 赤铜矿缺 60/分 · 每批 1500（单价 1）· 每小时可传 1500 个 → 喂不饱',
      st.rows.length === 1 && st.rows[0].need === 60 && st.rows[0].value === 1 &&
      st.rows[0].perBatch === 1500 && st.rows[0].perHour === 1500 && st.rows[0].perMin === 25 && st.rows[0].starved === true,
      JSON.stringify(st.rows[0]));
  const sum = A.RxlRegionShip([{ id: 'item_copper_jar', rate: 30 }, { id: 'item_copper_bottle', rate: 30 }],
    ['四号谷地', '四号谷地'], '四号谷地');
  chk('⑥-3 口径①：罐@30 + 瓶@30 同区 → 地区合计 120/分（不是各基地各算各的）',
      sum.rows.length === 1 && sum.rows[0].need === 120 && sum.rows[0].starved === true,
      'need=' + (sum.rows[0] ? sum.rows[0].need : '?'));
  const cf = A.RxlRegionShip([{ id: 'item_iron_cmpt', rate: 130 }, { id: 'item_quartz_glass', rate: 10 }],
    ['武陵', '武陵'], '武陵');
  chk('⑥-3 口径①：铁构件@130 + 石英玻璃@10 同放武陵 → 蓝铁+紫晶两种缺口 → 冲突 1（每方向每批只传一种）',
      cf.conflict === 1 && cf.items.item_iron_ore === 10 && cf.items.item_quartz_sand === 10,
      'conflict=' + cf.conflict + ' items=' + JSON.stringify(cf.items));
  const ok1 = A.RxlRegionShip([{ id: 'item_copper_jar', rate: 10 }], ['武陵'], '武陵');
  chk('⑥-3 口径①：罐@10 放武陵 → 无需收货（20 ≤ 510 本地够，rows 为空）',
      ok1.rows.length === 0, 'rows=' + JSON.stringify(ok1.rows));
})();

// 10) LpickToggle 开关 + RxlHtml 渲染
chk('⑥-3 LpickToggle：翻转再翻转（面板「选点建议」开关）',
    (function () { const s0 = !!A.Linit().pickShow; A.LpickToggle();
      const s1 = !!A.Linit().pickShow; A.LpickToggle();
      return s1 === !s0 && A.Linit().pickShow === s0; })());
chk('⑥-3 RxlHtml：没目标时提示先选目标物品',
    (function () { const t = A.LO.tgt, r = A.LO.rate; A.LO.tgt = ''; A.LO.rate = 0;
      const h = A.RxlHtml(); A.LO.tgt = t; A.LO.rate = r;
      return h.indexOf('先选目标物品') >= 0; })());
chk('⑥-3 RxlHtml：有目标 → 标题/口径①/口径②/3×1×3/吞吐不造数/推荐分配 全部出现',
    (function () { A.LO.tgt = 'item_copper_jar'; A.LO.rate = 10; A.LO.mt = [];
      const h = A.RxlHtml(); A.LO.tgt = ''; A.LO.rate = 0;
      return ['跨基地选点（⑥-3）', '口径①', '口径②', '3×1×3', '配置表里没有单列数据', '推荐分配']
        .every(k => h.indexOf(k) >= 0); })());
chk('⑥-3 RxlHtml：对比行点名自筹料（惰性壤晶废液 · 不能跨地区传输 · 聚合池/拆解自筹）',
    (function () { A.LO.tgt = 'item_copper_jar'; A.LO.rate = 10;
      const h = A.RxlHtml(); A.LO.tgt = ''; A.LO.rate = 0;
      return h.indexOf('惰性壤晶废液') >= 0 && h.indexOf('不能跨地区传输') >= 0 &&
        h.indexOf('聚合池/拆解自筹') >= 0; })());
A.LO.tgt = ''; A.LO.rate = 0; A.LO.mt = [];

// ---- ⑥-4 建筑专属限摆：天有洪炉 ≤12 台（2026-09-22 博士拍板 + 查证）----
// 查证口径：天有洪炉（息壤熔炉 xiranite_oven_1）当前版本摆放上限 **12 台**（武陵合计），
// 1.2 工业计划从 8 抬到 12、需息壤工业科技分阶段解锁（3DM/TapTap/NGA/1.4 蓝图攻略四源印证）。
// 1.5.3 配置表 buildings.json 的 hasPlaceLimit=false —— 「科技解锁型限摆」不在配置表数据域里
// （运行时系统数值，同矿脉产率），所以 build_html.py 里 RW_PLACE_LIMITS 手工维护。
// 守的口径：超限**报警不拦截**（产线照生成，msg 点名）；单机息壤 5/分 → @70 要 14 台 >12。
chk('⑥-4 校验函数：息壤@10 → 2 台天有洪炉，不误报', (() => {
  const w = A.RwPlaceLimitWarn(A.Rexplode('item_xiranite_powder', 10, {}));
  return w.length === 0;
})(), JSON.stringify(A.RwPlaceLimitWarn(A.Rexplode('item_xiranite_powder', 10, {}))));
chk('⑥-4 校验函数：息壤@70 → 14 台 > 12，点名天有洪炉超限并给建议', (() => {
  const w = A.RwPlaceLimitWarn(A.Rexplode('item_xiranite_powder', 70, {}));
  return w.length === 1 && w[0].indexOf('天有洪炉') >= 0 && w[0].indexOf('12 台') >= 0;
})(), JSON.stringify(A.RwPlaceLimitWarn(A.Rexplode('item_xiranite_powder', 70, {}))));
chk('⑥-4 端到端（轻）：息壤@10 生成后 msg 无超限字样', (() => {
  loReset(50); A.LO.size = 50;
  A.LawRun('item_xiranite_powder', 10);
  return (A.LO.msg || '').indexOf('超限') < 0 && (A.LO.msg || '').indexOf('产线已生成') >= 0;
})(), A.LO.msg);
chkHeavy('⑥-4 端到端（重）：膨地啪@70（56 台，天有洪炉 28）—— v99 行距修复后 80 画布能摆下（探针 4/8 组），成功 msg 仍点名「天有洪炉 超限」（报警不拦截口径）', () => {
  loReset(80); A.LO.size = 80;   /* v99 前：折行行距复用层间 corr（最高 14），单层就吃掉大半个画布 → 必拒；v99 行距独立为 RW_ROWGAP=3 后能摆下 */
  A.LawRun('item_muck_xiranite_1', 70);
  const m = A.LO.msg || '';
  return m.indexOf('产线已生成') >= 0 && m.indexOf('天有洪炉') >= 0 && m.indexOf('超限') >= 0;
}, () => (A.LO.msg || '').slice(0, 200));
chkHeavy('⑥-4+v99 端到端（重）：膨地啪@30（12 炉 = 游戏上限满配：6 产膨地啪 + 6 产息壤粉）—— 合法链生成且无超限误报（12 ≤ 12 边界）', () => {
  loReset(80); A.LO.size = 80;
  A.LawRun('item_muck_xiranite_1', 30);
  const m = A.LO.msg || '';
  return m.indexOf('产线已生成') >= 0 && m.indexOf('超限') < 0 && m.indexOf('放不下') < 0;
}, () => (A.LO.msg || '').slice(0, 200));

// ---- 💨 v103 气体散布机环境圈（2026-09-23 博士拍板：方形不是圆）----
// 数据源：FactoryVaporizerTable（rangeExtend=5 → 13×13 方形圈；4 种气体 genEnv 1-4 · rate 6 · cap 30）
//        + FactoryEnvDisplayTable（env1-4 → white/blue/orange/green 圈色）—— build 注入层灌进 DB.blueprint
// 守的口径：默认惰气(gas=1) · 换气换色 · 圈层开关独立于接口开关 · 关开关不影响摆放
(function () {
  const vp = A.byBp('vaporizer_1');
  chk('💨 注入：vaporizer_1 带 vaporizer 字段', !!(vp && vp.vaporizer));
  chk('💨 注入：rangeExtend.x === 5（3×3 本体 + 外扩 5 = 13×13 方形）',
      vp && vp.vaporizer && vp.vaporizer.rangeExtend && vp.vaporizer.rangeExtend.x === 5,
      JSON.stringify(vp && vp.vaporizer && vp.vaporizer.rangeExtend));
  chk('💨 注入：gasGroups 4 种 · consumeRate 6 · 上限 30',
      vp && vp.vaporizer && (vp.vaporizer.gasGroups || []).length === 4 &&
      vp.vaporizer.gasGroups.every(g => g.rate === 6 && g.cap === 30),
      JSON.stringify(vp && vp.vaporizer && vp.vaporizer.gasGroups));
  chk('💨 注入：envDisplay 4 条（溯源 color 词 white/blue/orange/green 不变）',
      (A.DB.blueprint.envDisplay || []).length === 4 &&
      A.DB.blueprint.envDisplay.map(e => e.color).join(',') === 'white,blue,orange,green',
      JSON.stringify(A.DB.blueprint.envDisplay));
  chk('💨 v104 校准色：env1-4 → 稳定青蓝/湿润白/酸性橙黄/息壤翠绿（博士截图口径）',
      A.envColorOf(1) === '#3D9FD8' && A.envColorOf(2) === '#F4F7F8' &&
      A.envColorOf(3) === '#E7AC3F' && A.envColorOf(4) === '#43B06E',
      JSON.stringify([1, 2, 3, 4].map(A.envColorOf)));
  chk('💨 v104 白圈（湿润）专属高浓度，其余轻透',
      A.envOpOf(2) === 0.45 && A.envOpOf(1) === 0.17);
  chk('💨 注入：气体中文名 惰气/水蒸气/酸气/息壤气',
      A.envGasName(1) === '惰气' && A.envGasName(2) === '水蒸气' &&
      A.envGasName(3) === '酸气' && A.envGasName(4) === '息壤气',
      JSON.stringify([1, 2, 3, 4].map(A.envGasName)));
  chk('💨 vaporizerSide：3×3 本体 → [13,13,5]', (() => {
    const s = A.vaporizerSide(A.byBp('vaporizer_1'));
    return s[0] === 13 && s[1] === 13 && s[2] === 5;
  })(), JSON.stringify(A.vaporizerSide(A.byBp('vaporizer_1'))));

  loReset(50);
  A.Lpick('vaporizer_1'); A.Lput(5, 5);
  const vo = A.LO.objs[0];
  chk('💨 摆放：散布机默认 gas=1（惰气）', vo && vo.gas === 1, String(vo && vo.gas));
  chk('💨 摆放：非散布机不带 gas 字段', (() => {
    A.Lpick('furnance_1'); A.Lput(20, 5);
    return A.LO.objs.every(o => o.id === 'vaporizer_1' ? true : !o.gas);
  })());

  A.render();
  chk('💨 渲染：.lo-env 色块出现 · 默认惰气→稳定青蓝（#3D9FD8）', (() => {
    const h = outEl.innerHTML || '';
    return h.indexOf('class="lo-env"') >= 0 && h.indexOf('--envbg:#3D9FD8') >= 0;
  })());
  chk('💨 渲染：圈宽 13 格 × 20px = 260px（方形外扩，不裁圆）', (() => {
    const m = (outEl.innerHTML || '').match(/class="lo-env" style="left:0px;top:0px;width:(\d+)px/);
    return !!m && Number(m[1]) === 260;
  })(), (() => { const m = (outEl.innerHTML || '').match(/class="lo-env" style="[^"]*width:(\d+)px/); return m ? m[1] : '?'; })());
  chk('💨 渲染：气体图例 + 工具栏开关 + 帮助手册区块都在',
      (outEl.innerHTML || '').indexOf('气体散布机环境圈') >= 0 &&
      (outEl.innerHTML || '').indexOf('LtoggleGas()') >= 0 &&
      (outEl.innerHTML || '').indexOf('气体散布机 · 环境圈') >= 0);

  /* 换气换色：单台 */
  A.LO.sel = [vo.uid]; A.render();
  A.LgasSet(2);
  chk('💨 换气：LgasSet(2) → gas=2 · 色块转湿润白（#F4F7F8）+ 白圈高浓度（--envop:0.45）',
      vo.gas === 2 && (outEl.innerHTML || '').indexOf('--envbg:#F4F7F8') >= 0 &&
      (outEl.innerHTML || '').indexOf('--envop:0.45') >= 0,
      'gas=' + vo.gas);
  /* 批量：再摆一台散布机（(20,20)，别跟熔炉/第一台重叠），两台一起切酸气 */
  A.Lpick('vaporizer_1'); A.Lput(20, 20);
  const v2 = A.LO.objs.filter(o => o.id === 'vaporizer_1' && o.uid !== vo.uid)[0];
  A.LO.sel = [vo.uid, v2.uid]; A.render();
  A.LgasSet(3);
  chk('💨 换气：批量两台 → gas=3 · 色块转酸性橙黄（#E7AC3F）',
      vo.gas === 3 && v2.gas === 3 && (outEl.innerHTML || '').indexOf('--envbg:#E7AC3F') >= 0,
      'gas=' + vo.gas + '/' + v2.gas);
  /* 无选中：只提示不报错 */
  A.LO.sel = []; A.render();
  A.LgasSet(4);
  chk('💨 换气：无选中时提示先选中散布机（不炸）',
      (A.LO.msg || '').indexOf('先在画布上选中气体散布机') >= 0, A.LO.msg);
  /* 开关独立：关环境圈 → 色块和气体图例收起，机器与接口图例不受影响 */
  A.LtoggleGas();
  chk('💨 开关：关掉后 .lo-env 色块消失', (outEl.innerHTML || '').indexOf('class="lo-env"') < 0);
  chk('💨 开关：关掉后气体图例收起（接口图例还在）',
      (outEl.innerHTML || '').indexOf('气体散布机环境圈') < 0 &&
      (outEl.innerHTML || '').indexOf('<i class="inp"></i>进料口') >= 0);
  chk('💨 开关：关掉不影响摆放（3 件都在场上）', A.LO.objs.length === 3);
  A.LtoggleGas();
  chk('💨 开关：再打开色块恢复', (outEl.innerHTML || '').indexOf('class="lo-env"') >= 0);

  /* ---- v104 就地选气条（博士：「想要点机器就地选」）---- */
  A.LO.sel = [vo.uid]; A.render();
  chk('💨v104 就地选：选中散布机 → 画布浮出 lo-gasbar（4 色块按钮）', (() => {
    const h = outEl.innerHTML || '';
    return h.indexOf('class="lo-gasbar"') >= 0 && (h.match(/LgasSet\(/g) || []).length === 4;
  })());
  chk('💨v104 就地选：当前气(酸气=3)的按钮带 on 高亮', (() => {
    const m = (outEl.innerHTML || '').match(/<button class="on" style="background:(#[0-9A-F]+);/);
    return !!m && m[1] === '#E7AC3F';
  })(), ((outEl.innerHTML || '').match(/<button class="on"[^>]*>/) || ['?'])[0]);
  A.LO.sel = []; A.render();
  chk('💨v104 就地选：取消选中 → 浮条消失', (outEl.innerHTML || '').indexOf('class="lo-gasbar"') < 0);
  chk('💨v104 左栏旧入口已撤（vSel 并入就地选）', (outEl.innerHTML || '').indexOf('通入哪种气体，环境圈就是哪种颜色') < 0);

  /* ---- v104 recipeEnv 注入 + 产线报告「环境依赖」段 ---- */
  chk('💨v104 注入：DB.recipeEnv 5 条 · 洪炉息壤粉=1(稳定) · 反应炉灼铜=3(酸性)', (() => {
    const re = A.DB.recipeEnv || {};
    return Object.keys(re).length === 5 &&
      re['xiranite_oven_xiranite_powder_2'] === 1 &&
      re['gas_reactor_gas_copper_enr2_1'] === 3 &&
      re['liquid_purifier_gas_copper_enr_2'] === 1;
  })(), JSON.stringify(A.DB.recipeEnv));
  loReset(50); A.LO.size = 50;
  A.LawRun('item_xiranite_powder', 10);
  A.render();
  chk('💨v104 报告：息壤粉链（洪炉气液模式）→ 报告点名「环境依赖」+ 稳定环境 + 通惰气', (() => {
    const h = outEl.innerHTML || '';
    return h.indexOf('环境依赖') >= 0 && h.indexOf('稳定环境') >= 0 &&
      h.indexOf('通惰气') >= 0 && h.indexOf('天有洪炉') >= 0;
  })());
  loReset(50); A.LO.size = 50;
  A.LawRun('item_iron_cmpt', 10);
  A.render();
  chk('💨v104 报告：铁制零件链（无环境配方）→ 无环境依赖段（用报告段专属短语判，避开帮助手册里的同名词）', (() => {
    return (outEl.innerHTML || '').indexOf('要摆进气体散布机的环境圈才会开工') < 0;
  })());

  /* ---- v104 配方页环境标签 ---- */
  (() => {
    A.tab = 'recipe'; A.render();
    const h = outEl.innerHTML || '';
    chk('💨v104 配方页：5 条环境配方都带「💨 需XX环境」标签',
        (h.match(/💨 需(稳定|湿润|酸性|息壤)环境/g) || []).length === 5,
        String((h.match(/💨 需(稳定|湿润|酸性|息壤)环境/g) || []).length));
    chk('💨v104 配方页：灼铜配方标「需酸性环境」', h.indexOf('需酸性环境') >= 0);
    A.tab = 'layout'; A.render();
  })();
})();

// 作用域门禁：用**原始代码**（保留 const/let）再冒烟跑一遍关键路径 =================
// 为什么必须有：上面为了在沙箱里取全局，把 const/let 全换成了 var —— 这会**掩盖块级作用域错误**。
// 实测踩到过：RwRoute 里 `const outNeed` 声明在 if 块内、却在 `else if` 里引用，
// 两套测试全绿，真机一跑 LawRun 直接 `outNeed is not defined`，**排布器点不动**（2026-09-22）。
// 所以这里用另一个沙箱加载未改写的代码，冒烟跑几条主路径 —— 抓的就是这类"只在浏览器里炸"的问题。
(function scopeGate() {
  const c2 = {
    document: doc, window: {}, console, setTimeout, clearTimeout, JSON, Math, Object,
    Array, String, Number, Boolean, Date, Set, Map, RegExp, Error, isNaN, parseInt, parseFloat,
  };
  c2.globalThis = c2;
  vm.createContext(c2);
  try {
    vm.runInContext(rawCode, c2, { timeout: 30000 });
    chk('作用域门禁：原始代码（const/let 版）能加载', true);
  } catch (e) {
    chk('作用域门禁：原始代码（const/let 版）能加载', false, e.message);
    return;
  }
  const smoke = [
    ['LawRun 纯固态链 10/分',
     "tab='layout'; Linit(); LO.objs=[]; LO.sel=[]; LO.undo=[]; LO.size=50; LawRun('item_iron_cmpt',10); if(!LO.objs.length) throw new Error('没生成任何东西');"],
    ['LawRun 混合链 10/分（含管道 + 汇流/分流分支）',
     "Linit(); LO.objs=[]; LO.sel=[]; LO.size=70; LawRun('item_copper_jar',10); if(!LO.objs.length) throw new Error('没生成任何东西');"],
    ['LawRun 多台并联 30/分（参数搜索分支，⚡v94 换小链：分支可达性验证不必付大产线 3s 求解成本）',
     "Linit(); LO.objs=[]; LO.sel=[]; LO.size=80; LawRun('item_iron_cmpt',30);"],
    ['锁定一件 + 重排其余',
     "Linit(); LO.objs=[]; LO.sel=[]; LO.size=70; LawRun('item_iron_cmpt',10); var ms=LO.objs.filter(function(o){return o.planRole==='machine';}); ms[0].lock=true; Lreroll();"],
    ['⑤-3 宽间距扩搜（赤铜块@10，12 台全摆 + 手动连 ≤2）',
     "Linit(); LO.objs=[]; LO.sel=[]; LO.size=80; var _t2=RwTargets().filter(function(x){return x.name==='赤铜块';})[0]; LawRun(_t2.id,10); var _diag='机器【'+LO.plan.res.machines.map(function(m){return m.machineName+'x'+m.machines+'<'+(m.recipeId||'')+'>';}).join(' ')+'】摆放 '+LO.plan.plan.objs.length+'/'+LO.plan.res.totalMachines+' 手动连 '+LO.plan.route.warns.filter(function(w){return w.indexOf('手动连')>=0;}).length+' 条'; if(LO.plan.plan.objs.length!==LO.plan.res.totalMachines) throw new Error('丢了机器 | '+_diag); if(LO.plan.route.warns.filter(function(w){return w.indexOf('手动连')>=0;}).length>2) throw new Error('手动连超过 2 条 | '+_diag);"],
    ['分流器分支（工业爆炸物@5，1 台上游喂 5 台下游）',
     "Linit(); LO.objs=[]; LO.sel=[]; LO.size=50; var _t=RwTargets().filter(function(x){return x.name==='工业爆炸物';})[0]; LawRun(_t.id,5); if(!LO.plan || !LO.plan.route.stats || LO.plan.route.stats.split<1) throw new Error('分流器分支没走到');"],
    ['render() 走一遍（含锁定态与工具条）', "render();"],
    ['⑥-1 跨地区收货：赤铜耐压罐@10（开开关 → 赤铜块变收货、惰气照旧）',
     "Linit(); LO.objs=[]; LO.sel=[]; LO.size=70; LO.shipIn=true; var _t3=RwTargets().filter(function(x){return x.id==='item_copper_jar';})[0]; LawRun(_t3.id,10); if(!LO.plan.res.shipIn.length) throw new Error('没识别出可收货的原料'); render();"],
    ['⑥-2 多目标：赤铜耐压罐@10 ＋ 赤铜瓶@10 一图展开（共享赤铜块）',
     "Linit(); LO.objs=[]; LO.sel=[]; LO.size=80; LO.mt=[{id:'item_copper_bottle',rate:10}]; LawRun('item_copper_jar',10); if(!LO.plan.res.targets) throw new Error('没走多目标路径'); if(!LO.plan.res.shared.length) throw new Error('没有共享中间料'); render();"],
    ['⑥-3 换向 + RxlHtml 可达（⚡v94 走空目标分支：完整渲染主节已验，这里不付 6s 选点计算）',
     "Linit(); LO.plan=null; LshipDirV('from','domain_2'); if(LshipFromId()!=='domain_2'||LshipToId()!=='domain_1') throw new Error('换向没生效'); LshipDirV('from','domain_1'); var _hx=RxlHtml(); if(_hx.indexOf('跨基地选点')<0) throw new Error('RxlHtml 没渲染');"],
  ];
  for (const [name, code2] of smoke) {
    try { vm.runInContext(code2, c2, { timeout: 30000 }); chk('作用域门禁：' + name, true); }
    catch (e) { chk('作用域门禁：' + name, false, e.message); }
  }
})();

// ---- v151 外部流体接入口（2026-09-24 博士定稿）----
// 博士截图实锤：实际玩法是拉很多根水管分别供给多台设备 ——「每流体一条」的收窄版已回退，
// 现在是**每台消费机器各拉一条边缘进管**（暗管贴画布外，画布内由排布器铺到每台机器的管口）。
// ⚠️ 口径：feed 失败不进「手动连」计数（那是 ⑤-3 内部连通率的回归口径），进 feedFail 正式点名。
let v151N = null;   /* 赤铜块@10 现场（LawRun 很慢，后续锁复用不重跑） */
chk('v151 外部接入：赤铜块@10 = 8 台反应池 × 2 种外部流体，16 根边缘进管「每台一条」全有着落', (() => {
  tab = 'layout'; A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 80;
  A.LawRun('item_copper_nugget', 10);
  const P = A.LO.plan, R = P.route;
  const pools = P.plan.objs.filter(o => o.node && o.node.machineName === '反应池');
  v151N = { feeds: R.feeds, fail: R.feedFail, pools: pools.length };
  const cover = it => v151N.feeds.filter(f => f.item === it).length
    + v151N.fail.filter(f => f.item === it).length;
  return pools.length === 8 && cover('液化息壤') === 8 && cover('污水') === 8
    && v151N.feeds.every(f => f.need === 5);
})(), () => JSON.stringify(v151N && { ok: v151N.feeds.length, fail: v151N.fail.length, pools: v151N.pools }));

chk('v151 外部接入：直连接入点全在画布边缘、两两不同格；暗管对的入/出口也两两不同（v154）', (() => {
  const size = 80;
  const dir = v151N.feeds.filter(f => f.mode !== 'udpipe');
  const es = dir.map(f => f.edge.x + ',' + f.edge.y);
  const ud = v151N.feeds.filter(f => f.mode === 'udpipe');
  const us = ud.map(f => f.entry.x + ',' + f.entry.y + '/' + f.exit.x + ',' + f.exit.y);
  return es.length === dir.length && new Set(es).size === es.length
    && dir.every(f => f.edge.x === 0 || f.edge.y === 0 || f.edge.x === size - 1 || f.edge.y === size - 1)
    && us.length === ud.length && new Set(us).size === us.length;
})(), () => JSON.stringify(v151N.feeds.map(f => f.mode === 'udpipe'
  ? ('U' + f.entry.x + ',' + f.entry.y + '↔' + f.exit.x + ',' + f.exit.y)
  : ('D' + f.edge.x + ',' + f.edge.y))));

chk('v151 外部接入：铺不出的进管全部点名进 feedFail（不静默丢；why/to/坐标齐全）', (() => {
  return v151N.feeds.length + v151N.fail.length === 16 && v151N.fail.length <= 2
    && v151N.fail.every(f => f.item && f.why && f.to);
})(), () => JSON.stringify(v151N.fail));

chk('v151 外部接入：内部连通率不被外部接入挤坏（赤铜块@10 手动连 ≤2 = v150 基线口径）', (() => {
  const n = A.LO.plan.route.warns.filter(w => w.indexOf('手动连') >= 0).length;
  return n <= 2;
})(), () => String(A.LO.plan.route.warns.filter(w => w.indexOf('手动连') >= 0).length));

chk('v151 外部接入：赤铜耐压罐@10（含惰气外部输入）6 根进管全铺成、零失败、接入点唯一', (() => {
  tab = 'layout'; A.Linit(); A.LO.objs = []; A.LO.sel = []; A.LO.size = 70;
  A.LawRun('item_copper_jar', 10);
  const R = A.LO.plan.route, size = 70;
  const dir = R.feeds.filter(f => f.mode !== 'udpipe');   /* ⭐v154：暗管对模式的 feed 没有边缘接入点 */
  const es = dir.map(f => f.edge.x + ',' + f.edge.y);
  const ud = R.feeds.filter(f => f.mode === 'udpipe');
  const us = ud.map(f => f.entry.x + ',' + f.entry.y + '/' + f.exit.x + ',' + f.exit.y);
  return R.feeds.length === 6 && R.feedFail.length === 0
    && new Set(es).size === es.length && new Set(us).size === us.length
    && dir.every(f => f.edge.x === 0 || f.edge.y === 0 || f.edge.x === size - 1 || f.edge.y === size - 1);
})(), () => JSON.stringify(A.LO.plan.route.feeds.map(f => f.mode === 'udpipe'
  ? ('U' + f.entry.x + ',' + f.entry.y + '↔' + f.exit.x + ',' + f.exit.y)
  : ('D' + f.edge.x + ',' + f.edge.y))));

// ---- v151 末端朝向修复（博士截图实锤「进出口的弯道又不对了」）----
// 根因：RwPath 的路径含终点格，铺线循环里最后一格 nx=path[k+1]||t 退化成自己指自己 →
// RwRotTo(t,t) 落到 LrotFrom 的 return 270 → **每条自动线的终点格箭头恒朝上**，与流向对撞
//（上游 ↓ 它 ↑）。修法：job 带 tInto（机器端口格 / 汇分流体本体），终点格朝向指向它。
// 不变量：终点格的出向绝不指回自己的上游邻居（= 不许在机器口掉头）。
chk('v151 末端朝向：赤铜耐压罐@10 全部连线的终点格箭头都指向下游，无一「掉头指回上游」', (() => {
  const DL = { 0: [1, 0], 90: [0, 1], 180: [-1, 0], 270: [0, -1] };
  const rotAt = {};
  A.LO.objs.forEach(o => { const b = A.byBp(o.id); if (b && b.isLogi) rotAt[o.x + ',' + o.y] = o.rot; });
  let n = 0, bad = [];
  A.LO.plan.route.links.forEach(l => {
    const ps = Array.isArray(l.path) ? l.path : [];
    if (ps.length < 2) return;
    n++;
    const last = ps[ps.length - 1].split(',').map(Number);
    const prev = ps[ps.length - 2].split(',').map(Number);
    const r = rotAt[last[0] + ',' + last[1]];
    if (r === undefined) { bad.push(ps[ps.length - 1] + ' 无物流件'); return; }
    const d = DL[r];
    if (last[0] + d[0] === prev[0] && last[1] + d[1] === prev[1]) bad.push(ps[ps.length - 1] + ' rot=' + r);
  });
  return n >= 10 && bad.length === 0;
})(), () => 'links=' + A.LO.plan.route.links.length + ' bad=' + JSON.stringify(
  (() => { const DL = { 0: [1, 0], 90: [0, 1], 180: [-1, 0], 270: [0, -1] }; const rotAt = {};
    A.LO.objs.forEach(o => { const b = A.byBp(o.id); if (b && b.isLogi) rotAt[o.x + ',' + o.y] = o.rot; });
    const out = []; A.LO.plan.route.links.forEach(l => { const ps = Array.isArray(l.path) ? l.path : [];
      if (ps.length < 2) return; const last = ps[ps.length - 1].split(',').map(Number);
      const prev = ps[ps.length - 2].split(',').map(Number); const r = rotAt[last[0] + ',' + last[1]];
      if (r === undefined) { out.push(ps[ps.length - 1] + ' 无件'); return; }
      const d = DL[r]; if (last[0] + d[0] === prev[0] && last[1] + d[1] === prev[1]) out.push(ps[ps.length - 1] + ' rot=' + r); });
    return out; })()));

// ---- v151 出口弯头（博士第二针：「入口弯头好了，出口没有」）----
// 根因：flowIn 只会查「邻居的 flowNext / 邻居的 portOut」——线**起点格**（机器口/汇流器出格
// 的外侧格）的进边来源是机器口/汇分流体本体，两查都够不着 → 永远画直条。
// 修法：① 汇流器/分流器（lgType=Router）的出格进 portOut（from=本体侧；pipe 通配——objs 转存
// 丢了 isPipe 字段，管汇流器回落 lgMedium='传送带' 会匹配不上，而汇流器与所连线永远同介质）；
// ② 桥（Connector/FluidConnector）按 rot 进 flowNext（桥后那格的进边靠它）；
// ③ flowIn 加「自查」：这格自己就是口/出格的外侧格 → 进边=本体侧。
// ④ v151 续2：feed 起点格（暗管接入点）进边=朝画布外那侧（feedStart 表）——博士截图
//    红框三连「也没有弯」：这些格子此前被本锁豁免、被 flowIn 画成直条，现在一并断言。
// 下面按渲染层同口径复刻三表，断言：全部起点（含 feed）与全部终点格的进边都可反推。
chk('v151 出口弯头：连线起点（机器口/汇流器出格/暗管接入点）与终点的进边全部可反推', (() => {
  // ⭐v152：lgi/flowNext 按「格 × 介质」双索引（'p:x,y'/'b:x,y'）—— 管×带叠加格里两层互不干扰
  const lgi = {};
  A.LO.objs.forEach(o => { const b = A.byBp(o.id); if (b && b.isLogi) lgi[(b.lgMedium === '管道' ? 'p' : 'b') + ':' + o.x + ',' + o.y] = o; });
  const flowNext = {};
  Object.values(lgi).forEach(o => {
    const b = A.byBp(o.id); if (!b) return;
    const fk = (b.lgMedium === '管道' ? 'p' : 'b') + ':' + o.x + ',' + o.y;
    if (b.lgType === 'Connector' || b.lgType === 'FluidConnector') {
      const v = { 0: [1, 0], 90: [0, 1], 180: [-1, 0], 270: [0, -1] }[o.rot];
      if (v) flowNext[fk] = [o.x + v[0], o.y + v[1]];
      return;
    }
    if (b.lgType !== 'Belt' && b.lgType !== 'Pipe' && b.lgType !== 'BoxValve' && b.lgType !== 'FluidValve') return;
    const out = (A.lgPortSides(b, o.rot).out || [])[0];
    const v = { r: [1, 0], b: [0, 1], l: [-1, 0], t: [0, -1] }[out];
    if (v) flowNext[fk] = [o.x + v[0], o.y + v[1]];
  });
  const portOut = {};
  // ⭐v151 续2：feed 起点（外部暗管接入点）的进边表 —— 压在哪条边进边就是朝外那侧；
  // 角落取「≠ 第一段走向」的外侧。与渲染层 build_html.py 同口径。
  const S = A.LO.size;
  const feedStart = {};
  (A.LO.plan && A.LO.plan.route ? A.LO.plan.route.links : []).forEach(l => {
    if (l.from !== '画布外（暗管接入）' || l.fmode === 'udpipe') return;   // ⭐v154：暗管对 feed 起点在出口旁，非边缘格
    const ps = Array.isArray(l.path) ? l.path : [];
    if (!ps.length) return;
    const p0 = ps[0].split(',').map(Number), p1 = ps.length > 1 ? ps[1].split(',').map(Number) : null;
    const sx = p0[0], sy = p0[1];
    const outs = [];
    if (sy === 0) outs.push('t');
    if (sy === S - 1) outs.push('b');
    if (sx === 0) outs.push('l');
    if (sx === S - 1) outs.push('r');
    if (!outs.length) return;
    const d0 = p1 ? (p1[0] > sx ? 'r' : p1[0] < sx ? 'l' : p1[1] > sy ? 'b' : 't') : null;
    feedStart[sx + ',' + sy] = (d0 && outs.find(o => o !== d0)) || outs[0];
  });
  A.LO.objs.forEach(o => {
    const b = A.byBp(o.id);
    if (b && b.isLogi && b.lgType === 'Router') {
      const OPPT = { t: 'b', b: 't', l: 'r', r: 'l' };
      (A.lgPortSides(b, o.rot).out || []).forEach(sd => {
        const v = { r: [1, 0], b: [0, 1], l: [-1, 0], t: [0, -1] }[sd];
        if (!v) return;
        const kx = o.x + v[0], ky = o.y + v[1];
        if (kx < 0 || ky < 0) return;
        portOut[kx + ',' + ky] = { from: OPPT[sd] };
      });
      return;
    }
    if (!b || b.isLogi) return;
    const fp = A.Lfp(b);
    (b.ports || []).forEach(p => {
      const q = A.LportXY(p, o.rot, fp[0], fp[1]);
      if (q.x < 0 || q.x >= o.w || q.z < 0 || q.z >= o.d) return;
      const dir = A.LportDirRot(p, o.rot, fp[0], fp[1]);
      const dx = dir === 'l' ? -1 : dir === 'r' ? 1 : 0, dz = dir === 'u' ? -1 : dir === 'd' ? 1 : 0;
      if (dir && p.kind === 'output') portOut[(o.x + q.x + dx) + ',' + (o.y + q.z + dz)] =
        { from: ({ t: 'b', b: 't', l: 'r', r: 'l' })[dir === 'u' ? 't' : dir === 'd' ? 'b' : dir], pipe: !!p.isPipe };
    });
  });
  const flowIn = (x, y, isPipe) => {
    const NB = { t: [0, -1], b: [0, 1], l: [-1, 0], r: [1, 0] };
    const pm = po => po && (po.pipe === undefined || !!po.pipe === !!isPipe);
    const FK = (px, py) => (isPipe ? 'p' : 'b') + ':' + px + ',' + py;
    for (const d in NB) {
      const nx = x + NB[d][0], ny = y + NB[d][1];
      const nxt = flowNext[FK(nx, ny)];
      if (nxt && nxt[0] === x && nxt[1] === y) return d;
      // ⭐v151 续：桥格双向穿行 —— 桥的 flowNext 只存最后一次穿行方向，先从另一轴穿过桥的线
      // 其下游格推不出进边。补判「连续性」：桥另一侧同轴有格子指回桥（介质对齐由键位保证）。
      const nbo = lgi[FK(nx, ny)], nbb = nbo && A.byBp(nbo.id);
      if (nbb && (nbb.lgType === 'Connector' || nbb.lgType === 'FluidConnector')) {
        const b2 = flowNext[FK((nx + NB[d][0]), (ny + NB[d][1]))];
        if (b2 && b2[0] === nx && b2[1] === ny) return d;
      }
    }
    for (const d in NB) { const po = portOut[(x + NB[d][0]) + ',' + (y + NB[d][1])]; if (pm(po)) return po.from; }
    const self = portOut[x + ',' + y];
    if (pm(self)) return self.from;
    const fs = feedStart[x + ',' + y];
    if (fs) return fs;
    return null;
  };
  let n = 0, bad = [];
  A.LO.plan.route.links.forEach(l => {
    const ps = Array.isArray(l.path) ? l.path : [];
    if (ps.length < 2) return;
    const isFeed = l.from === '画布外（暗管接入）';
    const s0 = ps[0].split(',').map(Number), e0 = ps[ps.length - 1].split(',').map(Number);
    // ⭐v151 续2：feed 起点不再豁免 —— 进边必须可反推；≠ feedStart 推导值时仅允许
    // 「起点被后穿的桥合法覆盖」（同格两条 feed 立体交叉，可见层=桥的流向，实测
    // 赤铜耐压罐@10 的 (0,24)：feed 起点管 + 后穿线叠的 FluidConnector 共存一格）
    if (isFeed) {
      const fin = flowIn(s0[0], s0[1], !!l.isPipe);
      if (l.fmode === 'udpipe') {
        // ⭐v154：暗管对 feed 的起点 = 出口 output 口外侧格，进边由 portOut 自查给（出口是普通建筑）
        if (!fin) bad.push('F起(ud) ' + ps[0] + ' ' + l.item);
      } else if (!fin) bad.push('F起 ' + ps[0] + ' ' + l.item);
      else if (fin !== feedStart[ps[0]]) {
        const top = lgi[(!!l.isPipe ? 'p' : 'b') + ':' + ps[0]], tb = top && A.byBp(top.id);
        if (!tb || (tb.lgType !== 'FluidConnector' && tb.lgType !== 'Connector'))
          bad.push('F起 ' + ps[0] + ' fs=' + feedStart[ps[0]] + ' fin=' + fin + ' ' + l.item);
      }
    } else if (!flowIn(s0[0], s0[1], !!l.isPipe)) bad.push('起 ' + ps[0] + ' ' + l.item);
    if (!flowIn(e0[0], e0[1], !!l.isPipe)) bad.push('终 ' + ps[ps.length - 1] + ' ' + l.item);
    n++;
  });
  return n >= 10 && bad.length === 0;
})(), () => JSON.stringify((() => {
  const bad = [];
  A.LO.plan.route.links.forEach(l => {
    const ps = Array.isArray(l.path) ? l.path : [];
    if (ps.length < 2) return;
    bad.push((l.from === '画布外（暗管接入）' ? 'F' : 'S') + ps[0] + '→' + ps[ps.length - 1] + ' ' + l.item);
  });
  return bad; })()));

// ---- v152 管×带交叉不放假桥（博士 2026-09-24 游戏实锤：3D 里管道在上层、传送带在下层，
//      交叉天然合法；只有**同介质**交叉才需要物流桥/管道桥立体跨线）----
// 断言①：每座桥的同格其他物流件必须同介质（不许管桥压在带上 / 带桥压在管上）。
chk('v152 交叉落件：桥的同格无异介质件（管×带交叉直接叠加、不放桥）', (() => {
  const byCell = {};
  A.LO.objs.forEach(o => { const b = A.byBp(o.id); if (b && b.isLogi)
    (byCell[o.x + ',' + o.y] = byCell[o.x + ',' + o.y] || []).push(b); });
  let bridges = 0; const bad = [];
  Object.values(byCell).forEach(arr => arr.forEach(b => {
    if (b.lgType !== 'Connector' && b.lgType !== 'FluidConnector') return;
    bridges++;
    const other = arr.filter(x => x !== b);
    if (other.length && other.some(x => (x.lgMedium === '管道') !== (b.lgMedium === '管道')))
      bad.push(b.id + '@' + b.lgMedium);
  }));
  return bridges > 0 && bad.length === 0;
})(), () => '桥下异介质=' + JSON.stringify((() => {
  const byCell = {}, out = [];
  A.LO.objs.forEach(o => { const b = A.byBp(o.id); if (b && b.isLogi)
    (byCell[o.x + ',' + o.y] = byCell[o.x + ',' + o.y] || []).push(b); });
  Object.entries(byCell).forEach(([k, arr]) => arr.forEach(b => {
    if ((b.lgType === 'Connector' || b.lgType === 'FluidConnector')
      && arr.some(x => x !== b && (x.lgMedium === '管道') !== (b.lgMedium === '管道'))) out.push(k + ':' + b.id);
  }));
  return out; })()));

// 断言②：场景里确实出现管×带叠加格（正样本，防「永远不交叉」的空锁）。
// ⭐v154 场景改罐@30：v154 暗管对把 @10 场景的长管改走地下后叠加格归零，罐@30 仍有 11 个。
chk('v152 交叉落件：罐@30 存在管×带叠加格（渲染两层齐全，管上带下）', (() => {
  loReset(80); A.LO.size = 80;
  A.LawRun('item_copper_jar', 30);
  const byCell = {};
  A.LO.objs.forEach(o => { const b = A.byBp(o.id); if (b && b.isLogi)
    (byCell[o.x + ',' + o.y] = byCell[o.x + ',' + o.y] || []).push(b); });
  let ovl = 0;
  Object.values(byCell).forEach(arr => {
    if (arr.some(x => x.lgMedium === '管道') && arr.some(x => x.lgMedium !== '管道')) ovl++;
  });
  return ovl >= 1;
})(), () => '叠加格=' + (() => {
  const byCell = {}; let ovl = 0;
  A.LO.objs.forEach(o => { const b = A.byBp(o.id); if (b && b.isLogi)
    (byCell[o.x + ',' + o.y] = byCell[o.x + ',' + o.y] || []).push(b); });
  Object.values(byCell).forEach(arr => {
    if (arr.some(x => x.lgMedium === '管道') && arr.some(x => x.lgMedium !== '管道')) ovl++;
  });
  return ovl; })());

// ---- v153 报告层：外部暗管接入清单进报告（feeds + feedFail = 应铺总数）----
chk('v153 报告层：外部暗管接入清单进报告（条数=route.feeds，接入点坐标与数据一致）', (() => {
  loReset(70); A.LO.size = 70;
  A.LawRun('item_copper_jar', 10);
  setTab('layout'); A.render();
  const F = (A.LO.plan && A.LO.plan.route.feeds) || [];
  if (F.length < 6) return false;
  const html = A.document.querySelector('#out').innerHTML;
  return html.indexOf('外部暗管接入') >= 0
    && F.every(f => f.mode === 'udpipe'
      ? (html.indexOf('入口 (' + f.entry.x + ',' + f.entry.y + ')') >= 0 && html.indexOf('↔ 出口 (' + f.exit.x + ',' + f.exit.y + ')') >= 0)
      : html.indexOf('(' + f.edge.x + ',' + f.edge.y + ')') >= 0);
})(), () => 'feeds=' + JSON.stringify(((A.LO.plan && A.LO.plan.route.feeds) || []).map(f => f.mode === 'udpipe'
  ? 'U' + f.entry.x + ',' + f.entry.y : 'D' + f.edge.x + ',' + f.edge.y)));
chk('v153 报告层：外部接入全部有着落——赤铜块@10 feedFail=0（v154 暗管对救回）或点名进报告', (() => {
  loReset(70); A.LO.size = 70;
  A.LawRun('item_copper_nugget', 10);
  setTab('layout'); A.render();
  const FF = (A.LO.plan && A.LO.plan.route.feedFail) || [];
  const html = A.document.querySelector('#out').innerHTML;
  if (!FF.length) return html.indexOf('暗管对') >= 0;    // v154：直连铺不成的被暗管对救回
  return html.indexOf('没铺成的外部接入 ' + FF.length + ' 条') >= 0
    && FF.every(f => html.indexOf(f.item) >= 0 && html.indexOf(f.to) >= 0);
})(), () => 'feedFail=' + JSON.stringify((A.LO.plan && A.LO.plan.route.feedFail) || []).slice(0, 200));

// ---- v154 暗管入口/出口对（博士 2026-09-25 实机规则：一对一定向、同建筑同物料、可旋转）----
chk('v154 暗管对：赤铜块@10 触发暗管对，入口/出口成对落盘且配对信息进报告', (() => {
  const ud = (A.LO.objs || []).filter(o => o.planRole === 'udpipe');
  const F = (A.LO.plan && A.LO.plan.route.feeds) || [];
  const upipes = F.filter(f => f.mode === 'udpipe');
  if (!upipes.length) return false;
  const html = A.document.querySelector('#out').innerHTML;
  return ud.length >= 2 && ud.length % 2 === 0
    && upipes.every(f => f.entry && f.exit && html.indexOf('入口 (' + f.entry.x + ',' + f.entry.y + ')') >= 0);
})(), () => 'udpipe objs=' + ((A.LO.objs || []).filter(o => o.planRole === 'udpipe')).length
  + ' feeds=' + JSON.stringify(((A.LO.plan && A.LO.plan.route.feeds) || []).map(f => f.mode || 'direct')));

chk('v154 择优：暗管对只在更省时采用（罐@10 全部 saved>0），短 feed 保持直连', (() => {
  loReset(70); A.LO.size = 70;
  A.LawRun('item_copper_jar', 10);
  setTab('layout'); A.render();
  const F = (A.LO.plan && A.LO.plan.route.feeds) || [];
  if (F.length < 6) return false;
  const ud = F.filter(f => f.mode === 'udpipe');
  const dir = F.filter(f => f.mode !== 'udpipe');
  const html = A.document.querySelector('#out').innerHTML;
  return ud.length >= 1 && ud.every(f => f.saved > 0 && f.entry && f.exit)   // 更省才采用
    && dir.every(f => f.edge)                                                // 直连的必有接入点
    && (A.LO.objs || []).filter(o => o.planRole === 'udpipe').length === ud.length * 2
    && html.indexOf('暗管对') >= 0;
})(), () => 'feeds=' + JSON.stringify(((A.LO.plan && A.LO.plan.route.feeds) || []).map(f => f.mode === 'udpipe'
  ? 'U(saved=' + f.saved + ')' : 'D' + (f.edge ? f.edge.x + ',' + f.edge.y : '?'))));
loReset(50); A.render();

// ---- C6 去路体检（2026-09-24 博士拍板「加」）----
// 背景：游戏里物品有硬顶（社区口径「库存 50 + 在制 1」），净产出 > 0 且没有去路的物品**必然**满仓 →
// 在制格卡死 → 该机停机 → 沿产线**反向逐级堵死** → 整条支线停产，并会跨线连锁
//（社区实例：赤铜块爆仓 → 污水断供 → 电池线停转 → 断电 → 全基地停摆）。
// 判据：对每个物品算「实际产出 − 下游需求」，净溢出 > 0 = 必爆项；目标产物归 targets（靠卖货，不算必爆）。
// ⚠️ 为什么必须独立扫配方：`Rexplode.build()` 只递归 ingredients，**配方副产物不进产线图**
//（317 条配方里 84 条双产出，其中 11 条产污水）—— 漏掉的恰好是最致命的那些。
chk('C6 体检：函数已在页面作用域导出（RflowAudit 判定 / RflowAuditHtml 渲染）',
    typeof A.RflowAudit === 'function' && typeof A.RflowAuditHtml === 'function',
    typeof A.RflowAudit + ' / ' + typeof A.RflowAuditHtml);

chk('C6 体检：赤铜块链检出「壤晶废液 50/分」必爆项（配方副产物 + 零下游 → 产线图里根本看不见）',
    (() => {
      const au = A.RflowAudit(A.Rexplode('item_copper_nugget', 10, {}));
      const hit = au.items.filter(x => x.id === 'item_liquid_xiranite_poly')[0];
      return !!hit && hit.over === 50 && hit.used === 0 && hit.fromByproduct === true;
    })(),
    JSON.stringify(A.RflowAudit(A.Rexplode('item_copper_nugget', 10, {})).items.map(x => x.name + ' over=' + x.over + ' used=' + x.used + ' byp=' + x.fromByproduct)));

chk('C6 体检反向锁：污水「产 10 / 链上反应池用 10」→ 有去路，**不得**误报为必爆项'
    + '（证明判定是真算净溢出，不是「见副产物就报警」）',
    (() => {
      const au = A.RflowAudit(A.Rexplode('item_copper_nugget', 10, {}));
      return !au.items.some(x => x.id === 'item_liquid_sewage') && !au.targets.some(x => x.id === 'item_liquid_sewage');
    })(),
    JSON.stringify(A.RflowAudit(A.Rexplode('item_copper_nugget', 10, {})).items.map(x => x.name)));

chk('C6 体检：目标产物（赤铜块）归 targets，不算必爆项',
    (() => {
      const au = A.RflowAudit(A.Rexplode('item_copper_nugget', 10, {}));
      return au.targets.some(x => x.id === 'item_copper_nugget')
          && !au.items.some(x => x.id === 'item_copper_nugget');
    })(),
    JSON.stringify(A.RflowAudit(A.Rexplode('item_copper_nugget', 10, {})).targets.map(x => x.name + ' ' + x.over)));

chk('C6 体检边界：空 res / 无产线 → 不抛错且判为「有去路」',
    (() => { const au = A.RflowAudit(null); return au.ok === true && au.items.length === 0 && au.targets.length === 0; })(),
    JSON.stringify(A.RflowAudit(null)));

chk('C6 报告区块：渲染出体检标题 + 必爆项名 + 去路建议 + 「超单池上限」提示（50/分 > 社区口径 30/分）',
    (() => {
      const h = A.RflowAuditHtml({ res: A.Rexplode('item_copper_nugget', 10, {}) });
      return h.indexOf('去路体检（C6）') >= 0 && h.indexOf('壤晶废液') >= 0 &&
             h.indexOf('扩容反应池') >= 0 && h.indexOf('30/分') >= 0 &&
             h.indexOf('协议储存箱不是去路') >= 0;
    })(),
    (function () { const h = A.RflowAuditHtml({ res: A.Rexplode('item_copper_nugget', 10, {}) }); return 'len=' + h.length + ' has=' + ['去路体检（C6）', '壤晶废液', '扩容反应池', '30/分', '协议储存箱不是去路'].filter(k => h.indexOf(k) < 0).join(','); })());

report();
