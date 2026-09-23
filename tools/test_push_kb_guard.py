# -*- coding: utf-8 -*-
"""push_kb 上线安全防线回归测试（v116 泄露事故后建）

背景：托管页曾把 raw/（游戏解包原文）、.workbuddy/memory/（本地记忆）、_archive/（内部审计）
推上公开静态域，且止血后又被下一轮推送顶回原文。防线有三道，本文件逐道断言：

  1. scan_local_artifacts()      —— auto 模式的扫描口径，不得含内部/排除目录
  2. _is_internal_path()         —— 通用防线：任一级目录以 . 或 _ 开头即内部
  3. 上传硬闸（push 列表确定后）  —— 剔除而非放行；--files 显式点名才中止
  4. strip_injection()           —— v117：平台注入 + 属性重排 + 内联 CSS 补空格的归一化

⚠ 第 3 道在 v117 改过行为：原来「发现内部路径 → 整批 fail」，但那些内部文件是**线上残留
占位**，线上产物树里永远存在 → auto 模式每次必挂、发布通道被防线自己堵死。现改为
「剔除 + 告警」，只有 --files 显式点名内部路径时才 fail。安全性等价（剔除点仍在最后一步，
没有任何路径能绕过），但通道保持可用 —— 下面为此专门加了一条回归断言。

用法：
    python tools/test_push_kb_guard.py                 # 只跑离线断言
    python tools/test_push_kb_guard.py --token <op_..> # 连跑硬闸（需网络，会建 dry-run 事务）

退出码：0 = 全通过；1 = 有失败。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
PUSH_KB = os.path.join(HERE, "push_kb.py")

PREFIX = "终末地基建知识库/"
# 这些目录下的文件一旦上线即属事故：版权（raw）或隐私（本地记忆 / 内部审计）
FORBIDDEN_TOP = {"raw"}


def load_pk():
    spec = importlib.util.spec_from_file_location("pk", PUSH_KB)
    pk = importlib.util.module_from_spec(spec)
    sys.argv = ["push_kb.py", "--help"]
    try:
        spec.loader.exec_module(pk)
    except SystemExit:
        pass
    return pk


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--token", default="")
    a, _ = ap.parse_known_args()

    pk = load_pk()
    fails: list[str] = []
    passes = 0
    skips = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passes
        if cond:
            passes += 1
        else:
            fails.append("%s %s" % (name, detail))

    # ---- 1. 扫描口径 ----
    scan = pk.scan_local_artifacts()
    check("scan 非空", len(scan) > 0, "扫到 %d" % len(scan))
    leaked = []
    for f in scan:
        rel = f[len(PREFIX):] if f.startswith(PREFIX) else f
        if pk._is_internal_path(rel) or rel.split("/")[0] in pk.SCAN_SKIP_DIRS:
            leaked.append(rel)
    check("scan 零泄露", not leaked, str(leaked[:5]))
    check("scan 含主产物", any(f.endswith("终末地基建查询.html") for f in scan))

    # ---- 2. _is_internal_path 单元断言 ----
    cases = [
        (".workbuddy/memory/MEMORY.md", True),
        ("_archive/代码质量审计报告.md", True),
        ("_tx_push/log.txt", True),
        ("data/items.json", False),
        ("tools/push_kb.py", False),
        ("README.md", False),
        ("index.html", False),
    ]
    for rel, want in cases:
        got = pk._is_internal_path(rel)
        check("internal(%s)==%s" % (rel, want), got == want, "got=%s" % got)

    # ---- 3. 上传硬闸（需 token）----
    if not a.token:
        skips += 5
        print("skip: 硬闸用例（未给 --token，不联网）")
    else:
        for rel, want_block in [("raw/ItemTable.json", True),
                                (".workbuddy/memory/MEMORY.md", True),
                                ("_archive/代码质量审计报告.md", True),
                                ("data/items.json", False)]:
            r = subprocess.run([sys.executable, PUSH_KB, "--token", a.token, "--message", "guard test",
                                "--dry-run", "--files", rel, "--allow-new"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            out = (r.stdout or "") + (r.stderr or "")
            blocked = "拒绝上传" in out
            check("hardblock(%s)==%s" % (rel, want_block), blocked == want_block,
                  "rc=%s out=%s" % (r.returncode, out[-160:].replace("\n", " ")))

        # v117：auto 模式不得再被线上残留占位整批挂掉（否则发布通道被防线自己堵死）
        r = subprocess.run([sys.executable, PUSH_KB, "--token", a.token, "--message", "guard test",
                            "--dry-run"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        check("auto 模式不被硬闸整批中止", "拒绝上传" not in out,
              "rc=%s out=%s" % (r.returncode, out[-200:].replace("\n", " ")))
        check("auto 模式仍剔除内部文件", "⛔ 剔除" in out,
              "rc=%s out=%s" % (r.returncode, out[-200:].replace("\n", " ")))

    # ---- 4. strip_injection：平台注入 / 属性重排 / 内联 CSS 补空格 都要归一化 ----
    #      本地原始态
    plain = ('<html lang="zh-CN"><head><meta name="viewport" content="W">'
             '<title>T</title></head><body>'
             '<p class="muted" style="margin-top:16px;font-size:14px">hi</p></body></html>')
    #      平台态：注入 data-page-node-id / data-pnid-children / inject.js / <!--pnid:-->，
    #      属性顺序重排（content 跑到 name 前），内联 CSS 分号后补空格
    injected = ('<html data-page-node-id="x1" lang="zh-CN"><head data-page-node-id="x2">'
                '<script data-page-node-id="x3" src="/page/page_comm/inject.js"></script>'
                '<meta data-page-node-id="x4" content="W" name="viewport">'
                '<title data-page-node-id="x5" data-pnid-children="x6">T</title></head>'
                '<body data-page-node-id="x7">'
                '<p data-page-node-id="x8" style="margin-top:16px; font-size:14px" class="muted">'
                '<!--pnid:x9-->hi</p></body></html>')
    si = pk.strip_injection
    check("strip: 平台态 == 本地态", si(plain) == si(injected))
    check("strip: 属性顺序不敏感",
          si('<meta name="a" content="b">') == si('<meta content="b" name="a">'))
    #      真改动必须仍然抓得出来（归一化不能把真实差异抹平）
    check("strip: 文本改动仍不等", si(plain) != si(injected.replace("hi</p>", "HELLO</p>")))
    check("strip: 属性值改动仍不等", si(plain) != si(injected.replace('content="W"', 'content="X"')))
    check("strip: style 值改动仍不等",
          si(plain) != si(injected.replace("font-size:14px", "font-size:99px")))
    check("strip: 属性名改动仍不等",
          si('<meta name="a" content="b">') != si('<meta name="a" describe="b">'))

    print("RESULT pass=%d fail=%d skip=%d" % (passes, len(fails), skips))
    for f in fails:
        print("  FAIL " + f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
