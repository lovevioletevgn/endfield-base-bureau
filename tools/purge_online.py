# -*- coding: utf-8 -*-
"""purge_online.py —— 把托管页上**不该存在的产物**覆盖为占位文本，并提交新版本。

背景（v116 事故，2026-09-23）：
  push_kb 的自动上传曾把 raw/（游戏解包原文）、.workbuddy/memory/（本地记忆）、_archive/
  （内部审计报告）推到公开静态域，零鉴权即可下载。平台侧**没有删除产物的接口**，
  `unpublish_page` 也只摘发布状态、不动 COS 对象（实测：下线后历史版本 URL 照样 200）。

⚠️ 因此本工具的止损是「覆盖」而非「删除」：
   - 最新版 URL 内容变为占位 → 干净
   - **历史版本 URL 仍返回原文 → 无法消除**（这是平台限制，不是本工具的缺陷）

用法（在知识库任意位置）：
  python tools/purge_online.py --token <op_...> --yes            # 覆盖默认三处内部目录
  python tools/purge_online.py --token <op_...> --dry-run        # 只打清单，不动线上
  python tools/purge_online.py --token <op_...> --prefix raw/ --yes

默认覆盖前缀：raw/ 、.workbuddy/ 、_archive/
占位内容：一行说明文本（73 字节），与 v114 止血时一致，便于识别。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
LIB = os.environ.get("KB_LIB_DIR") or (
    r"D:\Program Files\wb\WorkBuddy\resources\app.asar.unpacked"
    r"\resources\plugins\workbuddy-builtin\skills\library\page")
DEF_NODE = os.environ.get("KB_NODE_ID") or "YQO3ePeFiFgF6BrMKIpFbs"
PREFIX = "终末地基建知识库/"
DEFAULT_PREFIXES = ["raw/", ".workbuddy/", "_archive/"]
PLACEHOLDER = "该文件属于本地工作资产，不应随产物发布，已移除。\n".encode("utf-8")
CT = {".json": "application/json",
      ".txt": "text/plain; charset=utf-8",
      ".md": "text/markdown; charset=utf-8",
      ".html": "text/html; charset=utf-8"}


def api(script: str, args: list[str], token: str) -> dict:
    r = subprocess.run([sys.executable, os.path.join(LIB, script), "--token-stdin"] + args,
                       input=(token + "\n").encode(), capture_output=True, timeout=180)
    out = r.stdout.decode("utf-8", errors="replace")
    d = None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("{"):
            try:
                d = json.loads(s)
                break
            except Exception:
                pass
    if d is None:
        raise SystemExit("%s 无 JSON 输出: %s" % (script, out[:300]))
    if d.get("code") not in (0, None):
        raise SystemExit("%s 业务失败: %s" % (script, d))
    return d.get("data") or {}


def put(url: str, data: bytes, ctype: str) -> int:
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.status


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--token", default="")
    ap.add_argument("--node-id", dest="node_id", default=DEF_NODE)
    ap.add_argument("--prefix", dest="prefixes", action="append", default=[])
    ap.add_argument("--message", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a, _ = ap.parse_known_args()

    if not a.token:
        print("缺 --token（op_...）", file=sys.stderr)
        return 2
    prefixes = a.prefixes or DEFAULT_PREFIXES
    full = [PREFIX + p for p in prefixes]

    # 1) 拉线上清单
    d = api("list_page_artifacts.py", ["--node-id", a.node_id], a.token)
    artifacts = [x.get("path") for x in (d.get("artifacts") or []) if isinstance(x, dict)]
    targets = sorted(p for p in artifacts if any(p.startswith(f) for f in full))
    print("线上版本 v%s，产物 %d 项；命中待覆盖 %d 项" % (d.get("version"), len(artifacts), len(targets)))
    if not targets:
        print("无需覆盖。")
        return 0
    if a.dry_run or not a.yes:
        for p in targets[:20]:
            print("   ", p)
        if len(targets) > 20:
            print("    ... 共 %d 项" % len(targets))
        print("(dry-run) 加 --yes 才实际执行" if not a.yes else "")
        return 0

    # 2) 建事务
    d = api("create_page_transaction.py", ["--node-id", a.node_id], a.token)
    tx = d.get("transactionId")
    print("tx=%s base=%s" % (tx, d.get("baseVersion")))

    # 3) 逐个覆盖
    for i, rel in enumerate(targets, 1):
        d = api("get_page_upload_url.py", ["--transaction-id", tx, "--path", rel], a.token)
        url = d.get("uploadUrl")
        if not url:
            raise SystemExit("uploadUrl 为空: %s" % rel)
        put(url, PLACEHOLDER, CT.get(os.path.splitext(rel)[1], "application/octet-stream"))
        if i % 10 == 0 or i == len(targets):
            print("  覆盖 %d/%d" % (i, len(targets)))

    # 4) commit
    msg = a.message or ("purge：%s 覆盖为占位（平台无删除接口，历史版本 URL 仍保留原文）"
                        % "/".join(prefixes))
    d = api("commit_page_transaction.py", ["--transaction-id", tx, "--message", msg], a.token)
    print("commit v%s  %s" % (d.get("newVersion"), d.get("url")))
    print("⚠ 历史版本 URL 无法删除，请人工登记残留。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
