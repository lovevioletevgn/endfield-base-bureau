#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终末地基建知识库 · 一条龙发布脚本（v94 新增；v130 双链路升级）

用法：
  python tools/release.py                       # 本地验证：文档健康 → build.py → build_html.py → 两个测试 + 基线对账
  python tools/release.py --docs-only           # 纯文档改动：只跑文档健康检查（跳过构建与测试）
  python tools/release.py --push --token <op票> --message "vXX 说明"
                                                # 上面全部 + 推托管页（push_kb 自带终验）
  python tools/release.py --push --gh --token <op票> --message "vXX 说明"
                                                # + 索引暂存(git add -A) → 推 GitHub → 推托管页 → 本地 commit 存档
  python tools/release.py --keep-going          # 某步失败后继续跑后续步骤（默认失败即停）

v130 升级（博士拍板的工具链提效三件套之三）：
  - 第 0 步文档健康检查（tools/check_docs.py：链接/锚点/分享口径/基线行）；
  - 测试跑完后做**基线对账**：实际 RESULT 数字 vs docs/维护与更新.md 里写的基线，
    不一致即 FAIL —— 文档数字过时从此发不出去，必须同步；
  - --gh 双链路：自动 git add -A（gh_deploy 推的是 git 索引，漏 add 会静默漏推）
    → gh_deploy.py → push_kb.py；
  - --commit：全部通过后本地 git commit 存档（v126 起的惯例自动化）。

设计说明：
  - 数据构建（build.py）与页面重建（build_html.py）合计 ~1.2s，永远跑（--docs-only 除外）；
  - 测试是发布门禁（当前 778 断言 + 106 断言），fail>0 或非零退出即终止；
  - 推送复用 gh_deploy.py / push_kb.py（各自自带终验），本脚本不重复实现，只做编排与对账。
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# ⭐v110：node/git 路径优先 $KB_NODE / $KB_GIT，其次 PATH，再回落常见位置 / 本机便携版。
import shutil as _sh
NODE = (os.environ.get('KB_NODE')
        or _sh.which('node')
        or next((c for c in (
            r'C:\Program Files\nodejs\node.exe',
            r'C:\Program Files (x86)\nodejs\node.exe',
        ) if os.path.exists(c)), None)
        or os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node',
                        'versions', '22.22.2-3', 'node.exe'))


def _find_git():
    g = os.environ.get('KB_GIT') or _sh.which('git')
    if g:
        return g
    for pat in (os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'PortableGit',
                             'versions', '*', 'cmd', 'git.exe'),
                r'C:\Program Files\Git\cmd\git.exe'):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return 'git'


GIT = _find_git()
PY = sys.executable or 'python3'
BASELINE_DOC = os.path.join(ROOT, 'docs', '维护与更新.md')


def run(step, cmd, keep_go=False, cwd=None):
    t0 = time.time()
    print(f'\n=== [{step}] {" ".join(os.path.basename(c) for c in cmd[:1])} ...')
    r = subprocess.run(cmd, cwd=cwd or ROOT)
    dt = time.time() - t0
    mark = 'OK' if r.returncode == 0 else 'FAIL'
    print(f'--- [{step}] {mark} {dt:.1f}s')
    if r.returncode != 0 and not keep_go:
        print(f'!!! {step} 失败，终止（--keep-going 可忽略失败继续）')
        sys.exit(r.returncode or 1)
    return r.returncode, dt


def parse_result_line(line):
    m = re.search(r'pass=(\d+)\s+fail=(\d+)(?:\s+skip=(\d+))?', line)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else None


def baseline_of_doc():
    """读 docs/维护与更新.md 的基线行 → (page_pass, page_skip, ev_pass) 或 None"""
    if not os.path.exists(BASELINE_DOC):
        return None
    t = open(BASELINE_DOC, encoding='utf-8').read()
    m = re.search(r'当前\s*(\d+)/(\d+)\s*(?:skip=(\d+))?\s*[，,]?\s*另有事件层\s*(\d+)/(\d+)', t)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(3) or 0), int(m.group(4)))


def baseline_reconcile(page, ev):
    """page/ev = 测试实际 RESULT (pass, fail, skip)；与文档基线对账，返回 (ok, 说明)"""
    doc = baseline_of_doc()
    if doc is None:
        return False, 'docs/维护与更新.md 基线行缺失或格式不可解析（格式：当前 N/N skip=N，另有事件层 N/N）'
    dp, dsk, dev = doc
    diffs = []
    if page[0] != dp:
        diffs.append('页面 pass %d ≠ 文档 %d' % (page[0], dp))
    if page[2] != dsk:
        diffs.append('页面 skip %d ≠ 文档 %d' % (page[2], dsk))
    if ev[0] != dev:
        diffs.append('事件层 pass %d ≠ 文档 %d' % (ev[0], dev))
    if diffs:
        return False, '；'.join(diffs) + ' —— 请同步 docs/维护与更新.md 基线行（防过时门禁）'
    return True, '页面 %d/%d skip=%d · 事件层 %d 与文档基线一致' % (page[0], page[0], page[2], ev[0])


def main():
    ap = argparse.ArgumentParser(description='一条龙：文档健康 → 构建 → 测试 →（可选）双链路推送 → 本地存档')
    ap.add_argument('--push', action='store_true', help='测试通过后推托管页（push_kb，需 --token --message）')
    ap.add_argument('--gh', action='store_true', help='同时推 GitHub（自动 git add -A 后 gh_deploy）')
    ap.add_argument('--commit', action='store_true', help='全部通过后本地 git commit 存档（用 --message）')
    ap.add_argument('--docs-only', action='store_true', help='纯文档改动：跳过构建与测试（文档健康照跑）')
    ap.add_argument('--token', help='open platform op_ 票（--push 时必填）')
    ap.add_argument('--message', help='推送/提交说明（--push/--commit 时必填，建议 50 字内）')
    ap.add_argument('--skip-test', action='store_true', help='跳过测试门禁（应急用，慎）')
    ap.add_argument('--keep-going', action='store_true', help='某步失败后继续跑后续步骤（默认失败即停）')
    a = ap.parse_args()

    if (a.push or a.gh or a.commit) and not a.message:
        print('!!! --push/--gh/--commit 需要 --message')
        sys.exit(2)
    if a.push and not a.token:
        print('!!! --push 需要 --token（op_ 票，30 分钟有效）')
        sys.exit(2)

    total0 = time.time()
    steps = [('文档健康', [PY, os.path.join(HERE, 'check_docs.py')])]
    if not a.docs_only:
        steps += [
            ('数据构建', [PY, os.path.join(HERE, 'build.py')]),
            ('页面重建', [PY, os.path.join(HERE, 'build_html.py')]),
        ]
        if not a.skip_test:
            steps += [
                ('页面回归', [NODE, os.path.join(HERE, 'test_html.js')]),
                ('布局事件回归', [NODE, os.path.join(HERE, 'test_layout_events.js')]),
            ]
    if a.gh:
        steps += [
            ('索引暂存', [GIT, 'add', '-A']),
            ('推GitHub', [PY, os.path.join(HERE, 'gh_deploy.py'), '--message', a.message]),
        ]
    if a.push:
        steps.append(('推托管页', [PY, os.path.join(HERE, 'push_kb.py'),
                                   '--token', a.token, '--message', a.message]))
    if a.commit:
        steps.append(('本地存档', [GIT, 'commit', '-m', a.message]))

    # ⭐v130 基线对账：测试实际数字 vs 文档基线。测试步骤走 capture 模式
    # （输出照常透传给人看，同时抓 RESULT 行），避免双跑 36s 的测试。
    report = []
    results = {}
    for name, cmd in steps:
        if name in ('页面回归', '布局事件回归'):
            t0 = time.time()
            print(f'\n=== [{name}] {os.path.basename(cmd[1])} ...')
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
            out = (r.stdout or '') + (r.stderr or '')
            sys.stdout.write(out)                      # 照常透传给人看
            dt = time.time() - t0
            res = None
            for ln in out.splitlines():
                if ln.startswith('RESULT'):
                    res = parse_result_line(ln)
            mark = 'OK' if (r.returncode == 0 and res and res[1] == 0) else 'FAIL'
            print(f'--- [{name}] {mark} {dt:.1f}s')
            if r.returncode != 0 and not a.keep_going:
                print(f'!!! {name} 失败，终止（--keep-going 可忽略失败继续）')
                sys.exit(r.returncode or 1)
            report.append((name, r.returncode, dt))
            results[name] = res
            continue
        code, dt = run(name, cmd, keep_go=a.keep_going)
        report.append((name, code, dt))

    # 基线对账（测试都跑了才做；fail>0 时不对账——先修测试）
    if not a.docs_only and not a.skip_test and '页面回归' in results and '布局事件回归' in results \
            and results['页面回归'] and results['布局事件回归'] and results['页面回归'][1] == 0:
        ok, msg = baseline_reconcile(results['页面回归'], results['布局事件回归'])
        print('\n=== [基线对账] %s' % ('OK ' + msg if ok else 'FAIL ' + msg))
        report.append(('基线对账', 0 if ok else 1, 0.0))
        if not ok and not a.keep_going:
            sys.exit(1)

    print('\n======== 发布流水账 ========')
    bad = 0
    for name, code, dt in report:
        print(f'  {name}: {"✅" if code == 0 else "❌"} {dt:.1f}s')
        bad += (code != 0)
    print(f'  总耗时 {time.time() - total0:.1f}s')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
