#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_kb.py —— 终末地基建知识库一键推送（建事务→diff→merge→上传→commit→终验）

替代分阶段的 _push.py：一次调用跑完全链，stdout 直接输出摘要，细节落 _tx_push/log.txt。

⚠️ 已知限制（v111 记录，均**不修**，属设计取舍）：
  1. 脚本**不删除**线上多余文件。本地删掉的文件，线上仍保留（只打 `(线上有本地无，跳过)`）。
     要清理线上残留得另想办法（或手动在托管页删）。
  2. 版本号由 base+1 自动递增。若同一次发布拆成多轮推送（如正文一次、补推新文件一次），
     托管页 commit 会连跳（本次 GitHub v111 / 托管页 v111+v112）→ 与 GitHub 编号错位。
     **口径：编号错位不等于内容不一致；两边内容以文件比对为准。**

用法（在知识库根或任意位置）:
  python tools/push_kb.py --token <op_...> --message "v86 说明" [选项]

模式:
  (默认) auto     : 拉线上产物做 diff，自动推送所有内容有差异的文件（raw/ 除外）。
                    ⭐v111 起**本地新增文件也会自动推送**（此前会被静默漏掉），
                    推送时打印 `NEW <路径>（本地新增，自动上传）` 供核对。
  --files a b c   : 只推指定文件（相对知识库根；线上已存在的，SAME 的自动跳过）
  --allow-new     : (兼容保留) 允许 --files 模式推送线上产物树中不存在的新文件。
                    auto 模式自 v111 起已默认允许新文件，此开关对它无影响。
  --dry-run       : 只做 diff，打印将推送什么，不动线上
  --resume        : 复用上次未 commit 的事务（跳过已成功上传的文件）
  --no-verify     : 跳过 commit 后的终验（默认开终验）
  --no-diff       : 跳过 diff 比对（配合 --files 直接推）

退出码: 0 成功 | 1 失败（状态已落盘，可 --resume） | 2 token 失效（拿新票后 --resume 重跑）
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PY = sys.executable
# ⭐v110：这两项原为硬编码（本机 WorkBuddy 安装路径 / 托管页节点 id）。
#   不是密钥，但属于本机私有信息，且在 Linux 云端不成立 → 改为环境变量可覆盖、默认值保底，
#   行为与改动前完全一致（不设环境变量时走同样的路径与节点）。
DEF_LIB = os.environ.get("KB_LIB_DIR") or (
    r"D:\Program Files\wb\WorkBuddy\resources\app.asar.unpacked"
    r"\resources\plugins\workbuddy-builtin\skills\library\page")
DEF_NODE = os.environ.get("KB_NODE_ID") or "YQO3ePeFiFgF6BrMKIpFbs"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
WORK = os.path.join(PROJ, "_tx_push")
STATE_P = os.path.join(WORK, "state.json")
LOG_P = os.path.join(WORK, "log.txt")
ONLINE = os.path.join(WORK, "online_tree")
MERGED = os.path.join(WORK, "merged.html")
PREFIX = "终末地基建知识库/"  # 线上产物路径前缀，本地 PROJ 已含该级
HOST_HTML = "终末地基建查询.html"
HOST_PATH = PREFIX + HOST_HTML  # 线上产物树里的完整路径

CT = {".html": "text/html; charset=utf-8",
      ".json": "application/json; charset=utf-8",
      ".py": "text/x-python; charset=utf-8",
      ".md": "text/markdown; charset=utf-8",
      ".js": "text/javascript; charset=utf-8"}

T0 = time.monotonic()


def log(msg):
    os.makedirs(WORK, exist_ok=True)
    with open(LOG_P, "a", encoding="utf-8") as f:
        f.write("[%6.1fs] %s\n" % (time.monotonic() - T0, msg))


def say(msg):
    print(msg, flush=True)


def fail(code, msg):
    say("FAIL " + msg)
    log("FAIL " + msg)
    sys.exit(code)


def load_state():
    if os.path.exists(STATE_P):
        try:
            with open(STATE_P, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(st):
    os.makedirs(WORK, exist_ok=True)
    with open(STATE_P, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def api(script, args, token):
    """调 page 工具脚本，返回 data；token/网络失效 exit 2，其它业务失败 exit 1。"""
    p = os.path.join(LIB, script)
    r = subprocess.run([PY, p, "--token-stdin"] + args,
                       input=(token + "\n").encode(),
                       capture_output=True, timeout=180)
    out = r.stdout.decode("utf-8", errors="replace")
    err = r.stderr.decode("utf-8", errors="replace")
    log("%s rc=%s out=%s" % (script, r.returncode, out[:300].replace("\n", " ")))
    # 部分脚本（commit 等）输出为「JSON 行 + KS_ 日志行」混合，取首个 { 开头的合法 JSON 行
    d = None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("{"):
            try:
                d = json.loads(s)
                break
            except Exception:
                continue
    if d is None:
        try:
            d = json.loads(out)
        except Exception:
            fail(1, "%s 输出非 JSON: %s | stderr: %s" % (script, out[:200], err[:200]))
    if d.get("code") != 0:
        msg = str(d.get("msg") or out[:200])
        low = msg.lower()
        if any(k in low for k in ("network", "token", "auth", "unauthorized", "401")):
            fail(2, "token 失效或网络错误（%s）。拿新票后加 --resume 重跑，已传文件不会重传。" % msg)
        fail(1, "%s 业务失败: %s" % (script, msg))
    return d.get("data") or {}


def http_get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "push_kb/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_put(url, data, ctype, timeout=180):
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def list_artifacts(token, version=None):
    args = ["--node-id", NODE]
    if version is not None:
        args += ["--version", str(version)]
    d = api("list_page_artifacts.py", args, token)
    url = str(d.get("url") or "")
    paths = [a["path"] for a in (d.get("artifacts") or []) if isinstance(a, dict)]
    if not url or not paths:
        fail(1, "产物清单异常（url=%r, n=%d）" % (url[:60], len(paths)))
    return url, paths


def download_tree(base_url, paths, out_dir, token_unused=None):
    """并行下载产物到 out_dir，保持相对结构。返回失败清单。"""
    os.makedirs(out_dir, exist_ok=True)
    errors = []

    def one(rel):
        dst = os.path.join(out_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        last = None
        for _ in range(2):  # 临时网络错误重试 1 次
            try:
                data = http_get(base_url + urllib.parse.quote(rel))
                with open(dst, "wb") as f:
                    f.write(data)
                return
            except Exception as e:
                last = e
        errors.append("%s: %r" % (rel, last))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, paths))
    return errors


def same_content(online_file, local_file):
    """JSON 规范化比对（忽略键序），其它按字节。"""
    try:
        if online_file.endswith(".json") and local_file.endswith(".json"):
            with open(online_file, encoding="utf-8") as f1, open(local_file, encoding="utf-8") as f2:
                return json.load(f1) == json.load(f2)
    except Exception:
        pass
    with open(online_file, "rb") as f1, open(local_file, "rb") as f2:
        return f1.read() == f2.read()


def local_of(rel):
    if rel.startswith(PREFIX):
        rel = rel[len(PREFIX):]
    return os.path.join(PROJ, rel)


def online_of(rel):
    """线上相对路径 -> 下载树里的本地文件。"""
    return os.path.join(ONLINE, rel.replace("/", os.sep))


# ⭐v111：托管页产物的扫描口径。
#   设计原则 = **宁可少扫、不可多扫**：多扫一个文件只是多推一个无用的，本无害；
#   但把 raw/ 或临时件扫进去就出事（版权 / 垃圾文件）。所以用「只认白名单扩展名 + 排除目录」
#   两道闸，而不是「排除几个已知坏项」的黑名单思路。
#   ⚠️ 与 .gitignore 的口径**有意不同**：托管页需要 终末地基建查询.html（构建产物，
#      在 .gitignore 里被挡），所以不能直接抄 git 规则。
#   ⚠️ v114 事故根因（必读）：此前只按**文件名**判断临时件，没检查文件所在的**目录**。
#      结果 `.workbuddy/memory/MEMORY.md`、`_archive/*.md` 这类「文件名正常、目录内部」的
#      文件被当成普通产物推上线（本地记忆 + 内部审计报告泄露）。
#      修法 = 目录黑名单补两项 + 一道通用防线 `_is_internal_path()`（任一级目录以 . 或 _
#      开头即跳过）。通用防线是关键 —— 否则下次新增任何 `_xxx/` 目录都会重蹈覆辙。
SCAN_EXTS = (".md", ".py", ".js", ".json", ".html")
SCAN_SKIP_DIRS = {"raw", "_tx_push", ".baseline", ".git", "__pycache__",
                  "node_modules", ".vscode", ".idea", "_shot",
                  ".workbuddy", "_archive"}


def _is_internal_path(rel):
    """v114 新增通用防线：相对路径任一级**目录**以 `.` 或 `_` 开头 → 内部目录，不上线。

    文件名本身正常（如 MEMORY.md）但位于内部目录时，靠文件名前缀是拦不住的，
    必须从路径段层面判断。
    """
    parts = rel.split("/")
    if len(parts) < 2:
        return False
    return any(p.startswith((".", "_")) for p in parts[:-1])


def scan_local_artifacts():
    """扫本地、返回**应上托管页**的文件（相对 PROJ，带 PREFIX 前缀），已排序。

    排除：raw/、`_archive/`、`.workbuddy/` 与其它排除目录；任一级路径以 . 或 _ 开头的
    内部目录；下划线/点开头的临时件（_*.py / _*.js / _*.md / .gitignore）；
    probe_ 探针、*.bak、*.log、_v*_ref.html。
    """
    out = []
    for root, dirs, files in os.walk(PROJ):
        dirs[:] = [d for d in dirs if d not in SCAN_SKIP_DIRS]
        for fn in files:
            if not fn.endswith(SCAN_EXTS):
                continue
            if fn.startswith(("_", ".")):                      # 临时件 / 隐藏文件
                continue
            if fn.startswith("probe_") or fn.endswith((".bak", ".log")):
                continue
            if fn.startswith("_v") and fn.endswith("_ref.html"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, PROJ).replace(os.sep, "/")
            if _is_internal_path(rel):                         # v114：内部目录防线
                continue
            out.append(PREFIX + rel)
    return sorted(out)


def strip_injection(html):
    """剥掉托管平台注入的痕迹，得到「本地原始产物」的可比对形态。

    v114：平台对**每个** HTML（不止成品页）都会注入 `data-page-node-id` 属性、
    `inject.js` 脚本、`<!--pnid:...-->` 注释，注入后字节必然与本地不同。
    此前终验对所有非 HOST_PATH 的 HTML 直接做字节比对 → 必然误报失败
    （index.html 就是这么被判「终验不一致」的）。
    """
    t = html
    t = re.sub(r'\s*data-page-node-id="[^"]*"', "", t)
    t = re.sub(r'\s*data-pnid-children="[^"]*"', "", t)
    t = re.sub(r'<script[^>]*src="/page/page_comm/inject\.js"[^>]*>\s*</script>', "", t)
    t = re.sub(r'<!--pnid:[^>]*-->', "", t)
    return t


def same_artifact(remote_bytes, src_path):
    """终验比对：HTML 剥注入后比对文本，其它按字节。"""
    if src_path.endswith(".html"):
        try:
            return strip_injection(remote_bytes.decode("utf-8", "replace")) == \
                   strip_injection(open(src_path, encoding="utf-8",
                                        errors="replace").read())
        except Exception:
            return False
    with open(src_path, "rb") as f:
        return f.read() == remote_bytes


def main():
    global LIB, NODE
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--token", default=os.environ.get("KB_TOKEN", ""))
    ap.add_argument("--node", default=DEF_NODE)
    ap.add_argument("--lib", default=DEF_LIB)
    ap.add_argument("--message", default="")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--allow-new", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--no-diff", action="store_true")
    a = ap.parse_args()
    LIB, NODE = a.lib, a.node

    if not a.token:
        fail(2, "缺 --token（op_ 票，用 connect_open_platform 取）。")
    if not a.message and not a.dry_run:
        fail(1, "缺 --message（版本说明，如 \"v86 一键推送工具\"）。")

    say("== push_kb @ %s ==" % time.strftime("%H:%M:%S"))

    # ---- 1. 事务（--resume 复用；dry-run 只读线上，不建事务） ----
    st = load_state()
    if a.dry_run:
        txid, base = "", None
        say("(dry-run：不建事务，直接对比线上最新编辑态)")
    elif a.resume and st.get("txid"):
        txid, base = st["txid"], st["base"]
        say("resume tx=%s base=%s" % (txid, base))
    else:
        d = api("create_page_transaction.py", ["--node-id", NODE], a.token)
        txid, base = d["transactionId"], d["baseVersion"]
        st = {"txid": txid, "base": base, "uploaded": {}}
        save_state(st)
        say("tx=%s base=%s" % (txid, base))

    # ---- 2. 拉线上产物 + diff ----
    base_url, paths = list_artifacts(a.token, base)
    if a.resume and os.path.exists(online_of(HOST_PATH)) and st.get("base_url") == base_url:
        say("diff: 复用已下载的线上产物")
    else:
        errs = download_tree(base_url, paths, ONLINE)
        if errs:
            fail(1, "线上产物下载失败: %s" % "; ".join(errs[:3]))
        st["base_url"] = base_url
        save_state(st)
    say("diff: 线上 %d 个产物已拉取" % len(paths))

    path_set = set(paths)
    if a.files:
        push = [r if r.startswith(PREFIX) else PREFIX + r for r in a.files]
        for rel in push:
            if rel not in path_set and not a.allow_new:
                fail(1, "%s 不在线上产物树中（新文件需 --allow-new）" % rel)
            if not os.path.exists(local_of(rel)):
                fail(1, "本地缺文件: %s" % rel)
    else:
        push = [p for p in paths
                if not p.startswith(PREFIX + "raw/")
                and os.path.exists(local_of(p))
                and not same_content(online_of(p), local_of(p))]
        gone = [p for p in paths if not p.startswith(PREFIX + "raw/")
                and not os.path.exists(local_of(p))]
        for g in gone:
            say("  (线上有本地无，跳过) %s" % g)

        # ⭐v111 修复：auto 模式原先只从「线上已有产物」反推 push，导致**本地新增文件
        #   静默漏推**（2026-09-23 踩到：排布器算法地图.md / test_harness.js 首次推送丢失，
        #   只能事后用 --allow-new --files 补推，且把托管页 commit 数字顶到了 v112）。
        #   这里补一段：扫本地、挑出「该上托管页但线上还没有」的文件，**默认一起推**
        #   （auto 模式的定位就是「自动推送所有差异」，新文件也是差异之一 → 不该再要人工闸门）。
        #   口径 = 托管页产物构成（.md/.py/.js/.html/.json），显式排除：
        #     raw/（版权）、临时件（_ / . 前缀 / probe_ / .bak / .log）、构建产物目录。
        local_new = [rel for rel in scan_local_artifacts()
                     if rel not in path_set]
        for rel in local_new:
            say("  NEW     %s（本地新增，自动上传）" % rel)
        if local_new:
            say("  ⚠ 本次推送含 %d 个线上没有的新文件（上表 NEW 行）—— 请确认都是该上线的。" % len(local_new))
            push.extend(local_new)

    # ---- 2.5 v116 硬闸：无论 auto 还是 --files，内部/排除目录一律拒绝上传 ----
    #    ⚠ 事故根因复盘：v114 曾把泄露文件覆盖为占位止血，但 v115 用 auto 模式又被本地
    #      真实文件顶了回去 —— 只靠 scan_local_artifacts() 的软过滤不够，只要本地文件还在，
    #      任何一条上传路径都可能把原文重新推上去。所以在 push 列表**确定之后**再兜一次底，
    #      --files 手动指定也躲不掉。
    blocked = []
    for rel in push:
        rel_np = rel[len(PREFIX):] if rel.startswith(PREFIX) else rel
        if _is_internal_path(rel_np) or rel_np.split("/")[0] in SCAN_SKIP_DIRS:
            blocked.append(rel)
    if blocked:
        fail(1, "拒绝上传 %d 个内部/排除目录文件（v116 泄露事故硬闸，改用 --files 也无效）：\n  %s"
             % (len(blocked), "\n  ".join(blocked)))

    changed, sames = [], []
    for rel in push:
        if rel in path_set and same_content(online_of(rel), local_of(rel)):
            sames.append(rel)
        else:
            changed.append(rel)
    for r in sames:
        say("  SAME    %s（跳过）" % r)
    for r in changed:
        say("  CHANGED %s" % r)
    if a.files:
        push = changed  # 显式模式也只推真正变化的
    if not push:
        say("diff: 无差异，无事可做。删除事务状态并退出。")
        if os.path.exists(STATE_P):
            os.remove(STATE_P)
        say("elapsed %.1fs" % (time.monotonic() - T0))
        return

    # ---- 3. merge 托管 HTML（平台注入保留） ----
    if HOST_PATH in push:
        r = subprocess.run(
            [PY, os.path.join(HERE, "merge_into_hosted.py"),
             "--base", online_of(HOST_PATH),
             "--new", local_of(HOST_PATH), "--out", MERGED, "--mid-from", "new"],
            capture_output=True, timeout=300)
        out = r.stdout.decode("utf-8", errors="replace")
        log("merge rc=%s\n%s" % (r.returncode, out[:1500]))
        if r.returncode != 0 and ("相同" in out or "mid" in out.lower()):
            # merge 工具 assert：注入剥离后 mid 已一致 = 数据段无实质变化
            say("merge: HTML 数据段与线上一致，剔除不推")
            push.remove(HOST_PATH)
            if not push:
                say("diff: 剔除后无差异，退出。")
                os.remove(STATE_P)
                say("elapsed %.1fs" % (time.monotonic() - T0))
                return
        elif r.returncode != 0:
            fail(1, "merge 失败: %s" % out[-300:])
        else:
            # 防 v84 式冗余版本：线上注入版与本地原始版字节必不同，
            # 所以以「merge 产物(注入) vs 线上(注入)」为准判断 HTML 是否真变了
            with open(MERGED, "rb") as f1, open(online_of(HOST_PATH), "rb") as f2:
                if f1.read() == f2.read():
                    say("merge: HTML 与线上注入版一致，剔除不推（防冗余版本）")
                    push.remove(HOST_PATH)
                    if not push:
                        say("diff: 剔除后无差异，退出。")
                        os.remove(STATE_P)
                        say("elapsed %.1fs" % (time.monotonic() - T0))
                        return
                else:
                    say("merge: ok (%d bytes)" % os.path.getsize(MERGED))
    if a.dry_run:
        say("dry-run 结束，将推送 %d 个文件（未动线上）。" % len(push))
        say("elapsed %.1fs" % (time.monotonic() - T0))
        return

    # ---- 4. 上传（断点续传：跳过已成功的） ----
    done = st.setdefault("uploaded", {})
    n_ok = 0
    for rel in push:
        if done.get(rel):
            say("upload: %s（已传过，跳过）" % rel)
            n_ok += 1
            continue
        src = MERGED if rel == HOST_PATH and os.path.exists(MERGED) and rel in changed else local_of(rel)
        d = api("get_page_upload_url.py", ["--transaction-id", txid, "--path", rel], a.token)
        url = d.get("uploadUrl")
        if not url:
            fail(1, "uploadUrl 为空: %s" % rel)
        with open(src, "rb") as f:
            data = f.read()
        try:
            http_put(url, data, CT.get(os.path.splitext(rel)[1], "application/octet-stream"))
        except Exception as e:
            log("PUT fail %s %r" % (rel, e))
            save_state(st)
            fail(1, "PUT 失败: %s（%r）。--resume 重跑，勿直接 commit。" % (rel, e))
        done[rel] = True
        save_state(st)
        n_ok += 1
        say("upload: %s (%d bytes)" % (rel, len(data)))
    say("upload: %d/%d ok" % (n_ok, len(push)))

    # ---- 5. commit ----
    d = api("commit_page_transaction.py", ["--transaction-id", txid, "--message", a.message], a.token)
    ver = d.get("newVersion")
    say("commit: v%s  %s" % (ver, d.get("url") or ""))
    os.remove(STATE_P)

    # ---- 6. 终验（按新版本号拉回，字节比对） ----
    if not a.no_verify:
        v_url, _ = list_artifacts(a.token, ver)
        bad = []
        for rel in push:
            src = MERGED if rel == HOST_PATH else local_of(rel)
            try:
                remote = http_get(v_url + urllib.parse.quote(rel))
            except Exception as e:
                bad.append("%s (GET %r)" % (rel, e))
                continue
            if not same_artifact(remote, src):
                bad.append(rel)
        if bad:
            fail(1, "终验不一致: %s（线上 v%s 与本地有出入，人工检查！）" % (bad, ver))
        say("verify: %d/%d 字节一致，v%s 上线确认" % (len(push) - len(bad), len(push), ver))
    say("elapsed %.1fs" % (time.monotonic() - T0))


if __name__ == "__main__":
    main()
