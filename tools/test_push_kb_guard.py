# -*- coding: utf-8 -*-
"""push_kb 上线安全防线回归测试（v116 泄露事故后建）

背景：托管页曾把 raw/（游戏解包原文）、.workbuddy/memory/（本地记忆）、_archive/（内部审计）
推上公开静态域，且止血后又被下一轮推送顶回原文。防线有三道，本文件逐道断言：

  1. scan_local_artifacts()      —— auto 模式的扫描口径，不得含内部/排除目录
  2. _is_internal_path()         —— 通用防线：任一级目录以 . 或 _ 开头即内部
  3. 上传硬闸（push 列表确定后）  —— auto 与 --files 都拦，需 token 才跑（无 token 则 skip）

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
        skips += 4
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

    print("RESULT pass=%d fail=%d skip=%d" % (passes, len(fails), skips))
    for f in fails:
        print("  FAIL " + f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
