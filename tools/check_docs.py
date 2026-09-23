#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_docs.py —— 文档健康检查器（v130 新增，起因：v129 文档拆分暴露的隐性依赖无人守护）

背景：v129 把 118 KB 的 README 拆成 README + docs/×3 + 演进记录迁入段，交叉引用从 0 变多，
     且拆分当场挖出 release_note.py 锚点被搬走导致工具罢工的回归 —— 文档层需要自己的门禁。

检查项：
  1. 相对链接有效性：所有仓库 md 里的 [text](相对路径) 指向的文件必须存在
     （锚点 #fragment 只做宽松校验：目标文件是 md 时提示无法精确校验中文锚点，不算 FAIL）
  2. changelog:next 锚点：必须恰好存在一处（release_note.py 的插入点，多处会插错位置）
  3. 分享链接口径（v121 规矩）：README 与 docs/ 的对外文档里禁止出现
     workbuddy.cn/space/d/ 登录态链接 —— 对外只写 workbuddy.link/p/ 短链
     （演进记录/日志是历史记录，提到该 URL 属于记录事实，豁免）
  4. 基线行存在性：docs/维护与更新.md 必须有可解析的回归基线行
     （真正的数字对账由 release.py 在测试跑完后做——它手里有实际 RESULT）

用法：
  python tools/check_docs.py              # 全量检查，FAIL 非零退出
  python tools/check_docs.py --quiet      # 只输出 FAIL 行
"""
import argparse
import glob
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_GLOBS = ["*.md", "docs/*.md"]          # 参与链接互查的文档
FACE_GLOBS = ["README.md", "docs/*.md"]       # 「对外门面」口径（分享链接检查范围）
ANCHOR = "<!-- changelog:next"
BAN_URL = "workbuddy.cn/space/d/"


def collect(globs):
    out = []
    for g in globs:
        out += sorted(glob.glob(os.path.join(ROOT, g)))
    return [p for p in out if os.path.isfile(p)]


def check_links(all_files, quiet):
    """[text](target) 的相对 target 必须落在仓库里且存在"""
    bad = 0
    n_links = 0
    for p in all_files:
        base = os.path.dirname(p)
        text = open(p, encoding="utf-8").read()
        # 剔除代码块（代码块里的示例链接不作数）
        parts = re.split(r"```.*?```", text, flags=re.S)
        for m in re.finditer(r"\[([^\]]*)\]\(([^)\s]+)\)", " ".join(parts)):
            raw = m.group(2)
            if raw.startswith(("http://", "https://", "mailto:")) or raw.startswith("#"):
                continue
            n_links += 1
            path_part = urllib.parse.unquote(raw.split("#")[0])
            if not path_part:
                continue
            full = os.path.normpath(os.path.join(base, path_part))
            if not os.path.exists(full):
                bad += 1
                print("FAIL 链接失效: %s -> (%s)" % (os.path.relpath(p, ROOT), raw))
    if not quiet:
        print("OK   相对链接 %d 条全部有效" % n_links)
    return bad


def check_anchor(all_files, quiet):
    hits = []
    for p in all_files:
        if ANCHOR in open(p, encoding="utf-8").read():
            hits.append(p)
    if len(hits) != 1:
        print("FAIL changelog:next 锚点出现在 %d 处（须恰好 1 处）: %s"
              % (len(hits), "、".join(os.path.relpath(h, ROOT) for h in hits) or "无"))
        return 1
    if not quiet:
        print("OK   changelog:next 锚点恰好在 %s" % os.path.relpath(hits[0], ROOT))
    return 0


def check_share_links(quiet):
    """对外门面文档禁止登录态链接（v121 规矩）"""
    bad = 0
    for p in collect(FACE_GLOBS):
        for i, ln in enumerate(open(p, encoding="utf-8").read().splitlines(), 1):
            if BAN_URL in ln:
                bad += 1
                print("FAIL 对外文档含登录态链接（应写 workbuddy.link/p/ 短链）: %s L%d"
                      % (os.path.relpath(p, ROOT), i))
    if not bad and not quiet:
        print("OK   分享链接口径（README/docs 无 space/d 登录态链接）")
    return bad


def check_baseline(quiet):
    """docs/维护与更新.md 必须有可解析的回归基线行（数字对账在 release.py）"""
    p = os.path.join(ROOT, "docs", "维护与更新.md")
    if not os.path.exists(p):
        print("FAIL 缺 docs/维护与更新.md（基线行无处安放）")
        return 1
    text = open(p, encoding="utf-8").read()
    m = re.search(r"当前\s*(\d+)/(\d+)\s*(?:skip=\d+)?[，,]?\s*另有事件层\s*(\d+)/(\d+)", text)
    if not m:
        print("FAIL docs/维护与更新.md 找不到可解析的基线行（格式：当前 N/N skip=N，另有事件层 N/N）")
        return 1
    if not quiet:
        print("OK   基线行可解析（页面 %s/%s · 事件层 %s/%s）—— 数字对账由 release.py 测试后执行"
              % m.groups())
    return 0


def main():
    ap = argparse.ArgumentParser(description="文档健康检查（链接/锚点/分享口径/基线行）")
    ap.add_argument("--quiet", action="store_true", help="只输出 FAIL 行")
    a = ap.parse_args()

    all_files = collect(PUBLIC_GLOBS)
    if not all_files:
        sys.exit("FATAL 仓库里一个 md 都没有？")
    bad = 0
    bad += check_links(all_files, a.quiet)
    bad += check_anchor(all_files, a.quiet)
    bad += check_share_links(a.quiet)
    bad += check_baseline(a.quiet)
    if not a.quiet:
        print("== check_docs: %s（%d 个 md）==" % ("全部通过" if not bad else "%d 项 FAIL" % bad, len(all_files)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
