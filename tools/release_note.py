#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release_note.py —— README 版本条目一键生成（2026-09-22，博士拍板的 README 提效三招之二/三）

做什么：
  1. 自动取版本号：扫 README 里现有「**vNN 更新」的最大 NN，+1 作为本次版本；
  2. 按三行短格式生成条目（结论一句 + 验证数字 + 影响）；
  3. 自动抓 HTML 体积（KB）附在「验证」行尾；
  4. 插到 README 的固定锚点行 `<!-- changelog:next ... -->` 之前 —— 不再 grep 找插入点。

用法：
  python tools/release_note.py --title "一句话标题" --text "正文一句" \
      --verify "日常档 27.2s pass=659 skip=12，HEAVY=1 全量 671" \
      --impact "日常回归 44.5 → 27.2s；发布前须 HEAVY=1 全量；页面产物无变化"
  加 --dry-run 只预览不写。

为什么有它：以前每轮发布要人工 grep 定位插入点、手写 5~8 行长条目；
现在固定锚点 + 短格式，写作量降到 title/text/verify/impact 四个短语。
版本条目的读者是未来的自己 —— 结论、证据、影响三件事够了，细节在 daily 和测试里。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
HTML = os.path.join(ROOT, "终末地基建查询.html")
ANCHOR = "<!-- changelog:next"

def html_kb():
    try:
        return os.path.getsize(HTML) / 1024.0
    except OSError:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True, help="括号里的一句话标题（发生了什么）")
    ap.add_argument("--text", required=True, help="正文一句：怎么做的/抓到了什么")
    ap.add_argument("--verify", required=True, help="验证数字：测试通过数/耗时/对账")
    ap.add_argument("--impact", default="工具链侧，页面产物无变化", help="影响：对页面/用户/流程")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(README, encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)

    ver = 0
    for ln in lines:
        for m in re.finditer(r"\*\*v(\d+) 更新", ln):
            ver = max(ver, int(m.group(1)))
    if ver == 0:
        sys.exit("FATAL README 里没找到任何「**vNN 更新」条目，版本号无法递增")

    kb = html_kb()
    verify = a.verify + ("；HTML %.1f KB" % kb if kb else "")
    entry = (
        "  **v%d 更新（%s）**：%s\n"
        "  验证：%s。\n"
        "  影响：%s。\n"
    ) % (ver + 1, a.title, a.text, verify, a.impact)

    idx = None
    for i, ln in enumerate(lines):
        if ANCHOR in ln:
            idx = i
            break
    if idx is None:
        sys.exit("FATAL README 里找不到 changelog:next 锚点行 —— 锚点被误删了？")

    print("== release_note ==")
    print("版本: v%d（现有最新 v%d + 1）" % (ver + 1, ver))
    print("--- 生成的条目 ---")
    print(entry, end="")
    if a.dry_run:
        print("--- dry-run：未写入 ---")
        return

    lines[idx:idx] = [entry]
    with open(README, "w", encoding="utf-8", newline="") as f:
        f.write("".join(lines))
    print("--- 已写入 README（锚点前）---")

if __name__ == "__main__":
    main()
