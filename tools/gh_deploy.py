# -*- coding: utf-8 -*-
"""
gh_deploy.py —— 通过 GitHub Git Data API 一次性上传整个 git 索引到远端仓库。

为什么不用 git push：
    本机 github.com 主站被墙（超时），git push 走不通；
    但 api.github.com 可达（实测 0.65s），所以改走 REST API。
    Git Data API 允许一次性提交 37 个文件（blob*37 -> tree -> commit -> ref），
    比逐文件 contents API（37 次请求、37 个 commit）干净得多。

用法：
    python tools/gh_deploy.py                    # 自动读 token 文件（推荐）
    python tools/gh_deploy.py --dry-run          # 预演，不写入
    python tools/gh_deploy.py --message "v111 …" # 指定提交信息
    python tools/gh_deploy.py --token <ghp_...>  # 手动指定（覆盖文件）

token 来源优先级：
    ① 命令行 --token
    ② 环境变量 GH_TOKEN / GITHUB_TOKEN
    ③ 本地 token 文件 %USERPROFILE%\\.workbuddy\\.gh_token（每行一个，取首行）

安全：
    token 不在源码里、不落项目目录、不写日志。token 文件在 ~/.workbuddy/ 下，
    不在任何 git 仓库内，因此不会被跟踪或上传。
"""
import os, sys, json, base64, time, ssl, argparse, shutil, subprocess, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# git 可执行文件：优先 $KB_GIT → PATH → 常见 Windows 安装位置 → 本机便携版兜底。
# （原为硬编码本机绝对路径，他人 clone 后无法运行；此处仅把绝对路径降为最后一档。）
def _find_git():
    env = os.environ.get('KB_GIT')
    if env and os.path.exists(env):
        return env
    w = shutil.which('git')
    if w:
        return w
    for c in (r'C:\Program Files\Git\cmd\git.exe',
              r'C:\Program Files (x86)\Git\cmd\git.exe'):
        if os.path.exists(c):
            return c
    home = os.path.expanduser('~')
    for v in ('1.2.0',):
        c = os.path.join(home, '.workbuddy', 'binaries', 'PortableGit',
                         'versions', v, 'cmd', 'git.exe')
        if os.path.exists(c):
            return c
    return 'git'   # 交给 PATH 解析，跑不通时由调用处报错

GIT = _find_git()
OWNER = 'lovevioletevgn'
REPO = 'endfield-base-bureau'
BRANCH = 'main'
COMMIT_MSG = 'v110 版权隔离：raw 依赖烘焙化 + git 仓库初始化'

TOKEN_FILE = os.path.join(os.path.expanduser('~'), '.workbuddy', '.gh_token')

API = 'https://api.github.com'
CTX = ssl.create_default_context()


def resolve_token(cli_token=None):
    """按优先级取 token：CLI > 环境变量 > token 文件。"""
    if cli_token:
        return cli_token.strip(), '命令行参数'
    for env in ('GH_TOKEN', 'GITHUB_TOKEN'):
        v = os.environ.get(env)
        if v:
            return v.strip(), '环境变量 %s' % env
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding='ascii', errors='ignore') as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith('#'):
                    return s, 'token 文件'
    return None, None


def api(url, method='GET', payload=None, token=None):
    """统一请求入口。返回 (status, parsed_json_or_text)。"""
    data = None
    headers = {
        'Authorization': 'Bearer ' + token,
        'User-Agent': 'endfield-kb-upload',
        'Accept': 'application/vnd.github+json',
    }
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except Exception as e:
        return 'ERR', str(e)


def git(*a):
    r = subprocess.run([GIT, '-C', ROOT] + list(a),
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return ((r.stdout or '') + (r.stderr or '')).strip()


def collect_files():
    """取 git 索引里的文件（已过 .gitignore），返回 [(posix_path, bytes)]。"""
    out = git('ls-files', '-z')
    names = [x for x in out.split('\x00') if x]
    files = []
    for n in names:
        p = os.path.join(ROOT, n)
        if not os.path.isfile(p):
            print('  !! 索引里有但磁盘上不存在:', n)
            continue
        with open(p, 'rb') as f:
            files.append((n.replace('\\', '/'), f.read()))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token', default=None, help='GitHub PAT；省略则自动从环境变量或 ~/.workbuddy/.gh_token 读取')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--message', default=COMMIT_MSG)
    args = ap.parse_args()

    tok, src = resolve_token(args.token)
    print('=' * 66)
    print('GitHub Git Data API 上传')
    print('  目标: %s/%s  分支: %s' % (OWNER, REPO, BRANCH))
    if tok:
        print('  凭据: 来自 %s（%s…，%d 字符）' % (src, tok[:7], len(tok)))
    print('=' * 66)
    if not tok:
        print('✗ 未找到 token。请任选其一：')
        print('   • 建 PAT 后写入 %s' % TOKEN_FILE)
        print('   • 设置环境变量 GH_TOKEN')
        print('   • 加 --token <ghp_...> 参数')
        return 1

    # ---------- 1. 仓库体检 ----------
    s, d = api('%s/repos/%s/%s' % (API, OWNER, REPO), token=tok)
    if s != 200:
        print('✗ 仓库不可访问:', s, d)
        return 1
    print('✓ 仓库可访问 | private=%s | default_branch=%s | size=%s KB'
          % (d.get('private'), d.get('default_branch'), d.get('size')))
    perms = d.get('permissions') or {}
    if not perms.get('push'):
        print('✗ 没有 push 权限')
        return 1
    print('✓ 有 push 权限')

    # ---------- 2. 本地文件盘点 ----------
    files = collect_files()
    total = sum(len(c) for _, c in files)
    print('✓ 待上传 %d 个文件 / %.1f KB' % (len(files), total / 1024))
    bad = [p for p, _ in files if p.startswith('raw/')]
    if bad:
        print('✗ 版权红线：raw/ 被混进来了!', bad)
        return 1
    print('✓ 版权检查：无 raw/ 文件')

    if args.dry_run:
        for p, c in files:
            print('    %8d  %s' % (len(c), p))
        print('\n[dry-run] 未做任何写入。')
        return 0

    # ---------- 3. 取/确认分支状态 ----------
    s, d = api('%s/repos/%s/%s/git/ref/heads/%s' % (API, OWNER, REPO, BRANCH), token=tok)
    is_empty_repo = (s != 200)
    base_sha = None
    if s == 200:
        base_sha = d.get('object', {}).get('sha')
        print('✓ 目标分支已存在，父提交 = %s' % (base_sha or '')[:12])
    else:
        print('· 目标分支尚不存在（空仓库首次提交）')

    # ---------- 3.5 空仓库引导提交 ----------
    # 坑：GitHub 空仓库（没有任何提交）时，Git Data API 的 blobs/trees/commits
    #     一律返回 409 "Git Repository is empty."，必须先有一次提交把仓库激活。
    #     解法：用 contents API 落一个占位文件激活仓库，真正的 37 个文件随后覆盖。
    if is_empty_repo:
        print('\n--- 空仓库引导提交（激活仓库） ---')
        s, d = api('%s/repos/%s/%s/contents/.gitignore' % (API, OWNER, REPO),
                   method='PUT',
                   payload={'message': 'chore: 初始化仓库',
                            'content': base64.b64encode(b'# bootstrap\n').decode('ascii'),
                            'branch': BRANCH},
                   token=tok)
        if s not in (200, 201):
            print('✗ 引导提交失败:', s, d)
            return 1
        commit_sha = d['commit']['sha']
        print('✓ 引导提交 = %s（仓库已激活）' % commit_sha)
        s, d = api('%s/repos/%s/%s/git/ref/heads/%s' % (API, OWNER, REPO, BRANCH), token=tok)
        if s == 200:
            base_sha = d.get('object', {}).get('sha')
        print('✓ 分支 %s 已建立，父提交 = %s' % (BRANCH, (base_sha or '')[:12]))
        is_empty_repo = False

    # ---------- 4. 建 blobs ----------
    print('\n--- 创建 blobs ---')
    t0 = time.time()
    tree_items = []
    for i, (path, content) in enumerate(files, 1):
        payload = {'content': base64.b64encode(content).decode('ascii'),
                   'encoding': 'base64'}
        s, d = api('%s/repos/%s/%s/git/blobs' % (API, OWNER, REPO),
                   method='POST', payload=payload, token=tok)
        if s not in (200, 201):
            print('✗ blob 失败 [%d/%d] %s -> %s %s' % (i, len(files), path, s, d))
            return 1
        tree_items.append({'path': path, 'mode': '100644',
                           'type': 'blob', 'sha': d['sha']})
        print('  [%2d/%2d] %s' % (i, len(files), path))
    print('✓ blobs 完成 (%.1fs)' % (time.time() - t0))

    # ---------- 5. 建 tree ----------
    print('\n--- 创建 tree ---')
    s, d = api('%s/repos/%s/%s/git/trees' % (API, OWNER, REPO),
               method='POST', payload={'tree': tree_items}, token=tok)
    if s not in (200, 201):
        print('✗ tree 失败:', s, d)
        return 1
    tree_sha = d['sha']
    print('✓ tree = %s' % tree_sha)

    # ---------- 6. 建 commit ----------
    print('\n--- 创建 commit ---')
    cpayload = {'message': args.message, 'tree': tree_sha}
    if base_sha:
        cpayload['parents'] = [base_sha]
    s, d = api('%s/repos/%s/%s/git/commits' % (API, OWNER, REPO),
               method='POST', payload=cpayload, token=tok)
    if s not in (200, 201):
        print('✗ commit 失败:', s, d)
        return 1
    commit_sha = d['sha']
    print('✓ commit = %s' % commit_sha)

    # ---------- 7. 建/更新 ref ----------
    print('\n--- 更新分支引用 ---')
    if base_sha:
        s, d = api('%s/repos/%s/%s/git/refs/heads/%s' % (API, OWNER, REPO, BRANCH),
                   method='PATCH',
                   payload={'sha': commit_sha, 'force': False}, token=tok)
    else:
        s, d = api('%s/repos/%s/%s/git/refs' % (API, OWNER, REPO),
                   method='POST',
                   payload={'ref': 'refs/heads/' + BRANCH, 'sha': commit_sha}, token=tok)
    if s not in (200, 201):
        print('✗ ref 失败:', s, d)
        return 1
    print('✓ refs/heads/%s -> %s' % (BRANCH, commit_sha))

    # ---------- 8. 终验 ----------
    print('\n--- 终验 ---')
    s, d = api('%s/repos/%s/%s/git/trees/%s?recursive=1' % (API, OWNER, REPO, tree_sha), token=tok)
    if s == 200:
        n = len([x for x in d.get('tree', []) if x.get('type') == 'blob'])
        print('✓ 远端 tree 内文件数 = %d (本地 %d)' % (n, len(files)))
        ok = (n == len(files))
    else:
        print('? 终验查询失败:', s)
        ok = False
    s, d = api('%s/repos/%s/%s' % (API, OWNER, REPO), token=tok)
    if s == 200:
        print('✓ 仓库 size = %s KB | default_branch = %s' % (d.get('size'), d.get('default_branch')))

    print('\n' + ('=' * 66))
    print('✓ 上传完成' if ok else '⚠️ 上传完成但终验有出入，请人工复查')
    print('  https://github.com/%s/%s' % (OWNER, REPO))
    print('=' * 66)
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
