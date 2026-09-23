#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release_note.py —— 版本条目一键生成（2026-09-22，博士拍板的 README 提效三招之二/三）

做什么：
  1. 自动取版本号：扫候选文档里现有 vNN 的最大值，+1 作为本次版本；
  2. 按三行短格式生成条目（结论一句 + 验证数字 + 影响）；
  3. 自动抓 HTML 体积（KB）附在「验证」行尾；
  4. 插到固定锚点行 `<!-- changelog:next ... -->` 之前 —— 不再 grep 找插入点。

⭐v130（v129 文档重构的回归修复）：目标文件改为**探测制** ——
  v129 把版本日志从 README 迁进《排布器版本演进记录.md》，锚点 `<!-- changelog:next -->`
  随之迁移，本工具原来硬编码 README.md 会双重罢工（锚点找不到 + 版本号扫不到）。
  现在锚点在哪个候选文件里，条目就写进哪个文件。

⭐v130 首战实战教训（插入错号 v129，删掉重插）：版本号**不要靠文档扫描推断** ——
  工具罢工期间（v123+）发布的版本在文档里没有条目，扫描「最大+1」天然断链；
  docs/ 里的 v 号说法也不在候选范围。**正解：发布时显式传 `--version N`（发布事实由人带进来）**，
  不传才回退扫描兜底（候选 + docs/*.md 全局扫），且回退时大字警告「请核对版本号」。

用法：
  python tools/release_note.py --version 130 --title "一句话标题" --text "正文一句" \
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
HTML = os.path.join(ROOT, "终末地基建查询.html")
ANCHOR = "<!-- changelog:next"
# 锚点可能在的候选文件（按优先级）：v129 起版本日志在演进记录，README 只留门面
CANDIDATES = ["排布器版本演进记录.md", "README.md"]

def html_kb():
    try:
        return os.path.getsize(HTML) / 1024.0
    except OSError:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, default=None, help="本次版本号 N（强烈建议显式传入；不传才回退扫描推断）")
    ap.add_argument("--title", required=True, help="括号里的一句话标题（发生了什么）")
    ap.add_argument("--text", required=True, help="正文一句：怎么做的/抓到了什么")
    ap.add_argument("--verify", required=True, help="验证数字：测试通过数/耗时/对账")
    ap.add_argument("--impact", default="工具链侧，页面产物无变化", help="影响：对页面/用户/流程")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # ⭐v130 目标探测：锚点在哪个候选文件，条目就写进哪个文件
    target_name = target_path = lines = None
    all_texts = {}
    for name in CANDIDATES:
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            ls = f.read().splitlines(keepends=True)
        all_texts[name] = ls
        if target_name is None and any(ANCHOR in ln for ln in ls):
            target_name, target_path, lines = name, p, ls
    if target_name is None:
        sys.exit("FATAL 候选文件（%s）里都找不到 changelog:next 锚点行 —— 锚点被误删了？" % "、".join(CANDIDATES))

    # 版本号：显式 --version 优先（发布事实由人带进来）；不传才回退扫描兜底。
    # 扫描范围 = 候选文件 + docs/*.md 全局取最大 —— 只扫目标文件会把 v123+（没走过本工具
    # 的版本）漏掉，docs 里的 v 号说法也该算数（v130 首战抓过：标成 v129 实为 v130）。
    scan_texts = dict(all_texts)
    docs_dir = os.path.join(ROOT, "docs")
    if os.path.isdir(docs_dir):
        for fn in os.listdir(docs_dir):
            if fn.endswith(".md"):
                with open(os.path.join(docs_dir, fn), encoding="utf-8") as f:
                    scan_texts["docs/" + fn] = f.read().splitlines(keepends=True)
    if a.version is not None:
        ver = a.version
        print("版本: v%d（--version 显式指定）" % ver)
    else:
        ver = 0
        for ls in scan_texts.values():
            for ln in ls:
                for m in re.finditer(r"\bv(\d+)\b", ln):
                    ver = max(ver, int(m.group(1)))
        if ver == 0:
            sys.exit("FATAL 候选文件与 docs/ 里没扫到任何 vNN，版本号无法递增 —— 请显式传 --version")
        print("⚠️ 版本: v%d（回退推断 = 文档最大 v%d + 1 —— 工具罢工期间发布的版本不在文档里，请人工核对！）" % (ver + 1, ver))
        ver = ver + 1

    kb = html_kb()
    verify = a.verify + ("；HTML %.1f KB" % kb if kb else "")
    # 条目顶格（与 v121/v122 既有条目一致；v130 首战曾带两格缩进，已修）
    entry = (
        "**v%d 更新（%s）**：%s\n"
        "验证：%s。\n"
        "影响：%s。\n"
    ) % (ver, a.title, a.text, verify, a.impact)

    idx = None
    for i, ln in enumerate(lines):
        if ANCHOR in ln:
            idx = i
            break

    print("== release_note ==")
    print("目标文件: %s（锚点所在）" % target_name)
    print("--- 生成的条目 ---")
    print(entry, end="")
    if a.dry_run:
        print("--- dry-run：未写入 ---")
        return

    lines[idx:idx] = [entry]
    with open(target_path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(lines))
    print("--- 已写入 %s（锚点前）---" % target_name)

if __name__ == "__main__":
    main()
