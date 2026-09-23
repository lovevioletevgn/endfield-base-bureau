# -*- coding: utf-8 -*-
"""终末地基建知识库 · 一条龙发布脚本（v94 新增）

用法：
  python tools/release.py                       # 本地验证：build.py → build_html.py → 两个测试
  python tools/release.py --push --token <op票> --message "vXX 说明"
                                                # 上面全部 + dry-run 差异 + 正式推送（push 自带终验）
  python tools/release.py --keep-going          # 某步失败后继续跑后续步骤（默认失败即停）

设计说明：
  - 数据构建（build.py）与页面重建（build_html.py）合计 ~1.2s，永远跑；
  - 测试是发布门禁（test_html 668 断言 + test_layout_events 72 断言），fail>0 或非零退出即终止；
  - 推送复用 push_kb.py（自带差异清单 dry-run 与推送后字节级终验），本脚本不重复实现。
"""
import argparse
import subprocess
import sys
import time
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# ⭐v110：node 路径原为硬编码本机绝对路径（云端/Linux 不成立）。
#   优先 $KB_NODE，其次 PATH 里的 node，再其次常见安装位置，最后回落本机便携版。
import shutil as _sh
NODE = (os.environ.get('KB_NODE')
        or _sh.which('node')
        or next((c for c in (
            r'C:\Program Files\nodejs\node.exe',
            r'C:\Program Files (x86)\nodejs\node.exe',
        ) if os.path.exists(c)), None)
        or os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node',
                        'versions', '22.22.2-3', 'node.exe'))
PY = sys.executable or 'python3'


def run(step, cmd, keep_go=False):
    t0 = time.time()
    print(f'\n=== [{step}] {" ".join(os.path.basename(c) for c in cmd[:1])} ...')
    r = subprocess.run(cmd, cwd=ROOT)
    dt = time.time() - t0
    mark = 'OK' if r.returncode == 0 else 'FAIL'
    print(f'--- [{step}] {mark} {dt:.1f}s')
    if r.returncode != 0 and not keep_go:
        print(f'!!! {step} 失败，终止（--keep-going 可忽略失败继续）')
        sys.exit(r.returncode or 1)
    return r.returncode, dt


def main():
    ap = argparse.ArgumentParser(description='一条龙：构建 → 测试 →（可选）推送')
    ap.add_argument('--push', action='store_true', help='测试通过后推送到线上')
    ap.add_argument('--token', help='open platform op_ 票（--push 时必填）')
    ap.add_argument('--message', help='推送提交说明（--push 时必填，建议 50 字内）')
    ap.add_argument('--skip-test', action='store_true', help='跳过测试门禁（应急用，慎）')
    ap.add_argument('--keep-going', action='store_true', help='某步失败后继续跑后续步骤')
    a = ap.parse_args()

    total0 = time.time()
    steps = [
        ('数据构建', [PY, os.path.join(HERE, 'build.py')]),
        ('页面重建', [PY, os.path.join(HERE, 'build_html.py')]),
    ]
    if not a.skip_test:
        steps += [
            ('页面回归(668)', [NODE, os.path.join(HERE, 'test_html.js')]),
            ('布局事件回归(72)', [NODE, os.path.join(HERE, 'test_layout_events.js')]),
        ]
    if a.push:
        if not (a.token and a.message):
            print('!!! --push 需要 --token 与 --message')
            sys.exit(2)
        steps.append(('推送线上', [PY, os.path.join(HERE, 'push_kb.py'),
                                  '--token', a.token, '--message', a.message]))

    report = []
    for name, cmd in steps:
        code, dt = run(name, cmd, keep_go=a.keep_going)
        report.append((name, code, dt))

    print('\n======== 发布流水账 ========')
    bad = 0
    for name, code, dt in report:
        print(f'  {name}: {"✅" if code == 0 else "❌"} {dt:.1f}s')
        bad += (code != 0)
    print(f'  总耗时 {time.time() - total0:.1f}s')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
