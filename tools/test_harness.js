// test_harness.js —— 三个测试脚本共用的「加载产物 HTML + 沙箱引导」工具
//
// 为什么存在（2026-09-23）：
//   test_html.js / test_layout_events.js / scan_all.js 各自抄了一份「从产物 HTML 里
//   取含 `const DB` 的 <script> 段 + 语法门禁」的引导逻辑，三份逐字相同。
//   产物结构一变（例如平台托管页在 <head> 插了带属性的 <script src>）就要改三处 ——
//   漏改一处的表现是「某个测试静默测了个错的段」，极难发现。
//
// 抽出的范围刻意保守：**只抽无副作用、无状态的纯引导逻辑**。
//   ⚠️ 不抽 mkEl（迷你 DOM 替身）—— test_html 与 test_layout_events 的两份
//   **语义不同**（后者要沿 _host 链做 closest 匹配、要 getBoundingClientRect，
//   前者只需纯文本断言），合并会改变 test_html 730 条断言的运行基础。
//   详见 test_layout_events.js 里 v104 的踩坑注释。
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// 默认产物路径：<repo>/终末地基建查询.html（可用 $KB_HTML 或参数覆盖）
function defaultHtml() {
  return process.env.KB_HTML || path.join(__dirname, '..', '终末地基建查询.html');
}

// 从 HTML 全文里取「含 const DB 的那段 <script>」。
// 不能取第一个、也不能贪婪匹配：平台托管的页面会在 <head> 里另插一个 <script src>。
function extractMainScript(html) {
  for (const mm of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
    if (mm[1].includes('const DB')) return mm[1];
  }
  return null;
}

// 加载 + 提段 + 语法门禁一步到位。
// 返回 { html, rawCode, code }，其中 code 是 const/let → var 的沙箱转写版。
// 语法门禁**必须先于转写**：var 允许重复声明，会把「重复 const」这种真 SyntaxError 吞掉。
function load(htmlPath) {
  const html = fs.readFileSync(htmlPath || defaultHtml(), 'utf8');
  const rawCode = extractMainScript(html);
  if (!rawCode) {
    console.error('FATAL 找不到含 const DB 的 <script> 段');
    process.exit(1);
  }
  try {
    new vm.Script(rawCode, { filename: 'main.js' });
  } catch (e) {
    console.error('FATAL 脚本语法错误（真实浏览器会整段作废 → 页面空白）');
    console.error('  ' + e.name + ': ' + e.message);
    process.exit(1);
  }
  const code = rawCode.replace(/\bconst\s+/g, 'var ').replace(/\blet\s+/g, 'var ');
  return { html, rawCode, code };
}

module.exports = { load, extractMainScript, defaultHtml };
