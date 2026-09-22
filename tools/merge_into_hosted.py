# -*- coding: utf-8 -*-
"""
把 build_html.py 新构建出来的本地单文件版，合并进资料库托管的线上产物，并做硬校验。

为什么需要它：
  线上那份 HTML 被平台注入了锚点（`data-page-node-id` / `data-pnid-children` /
  `<!--pnid:xxx-->` 注释 / `<head>` 里的 `inject.js`），直接上传本地构建产物会把这些**全抹掉**，
  页面评论的定位就失效了。所以必须"拿线上当壳、只换内容"。

合并策略（5 段）：
  ① 线上的前缀（含 `<style ...>` 开标签的注入属性）   —— 用线上
  ② `<style>` 主体（CSS）                            —— 用新产物
  ③ `</style>` 到 `\\nconst TABS = [` 之间（注入属性 + 内联数据包）—— 用线上
  ④ `\\nconst TABS = [` 到 `</script>` 之间（JS 主体） —— 用新产物
  ⑤ `</script>` 之后（`</body></html>`）              —— 用线上（两边应完全相同）

  为什么 ③ 用线上而不是新产物：这段里包着 858 KB 的内联数据包，数据没变就整段沿用，
  省掉一次"重新序列化是否逐字节一致"的赌博。**数据变了就另说**——那时要确认新产物的
  数据包与线上一致，或者干脆接受 ③ 也换成新产物的（`--mid-from new`）。

硬校验（不过就退出码 1、不产出文件）：
  剥掉线上注入后，合并结果必须与新产物**逐字节相等**。这是唯一可靠的验收方式。

用法：
  python3 tools/merge_into_hosted.py --base <线上产物.html> --new <本地构建产物.html> \
      [--out merged.html] [--mid-from base|new]

线上产物的拿法：先开 page 事务拿到 baseVersion，再从
  https://workbuddy-space-static.codebuddy.work/page/<nodeId>/<baseVersion>/<产物相对路径>
下载。
"""
import argparse
import os
import re
import sys

if hasattr(sys.stdout, "buffer"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def strip_injections(s):
    """剥掉平台注入的四类东西，得到"内容层"原文。"""
    s = re.sub(r"<!--pnid:[^>]*-->", "", s)
    s = re.sub(r'<script[^>]*src="/page/page_comm/inject\.js"[^>]*>\s*</script>\s*', "", s)
    s = re.sub(r'\s+data-page-node-id="[^"]*"', "", s)
    s = re.sub(r'\s+data-pnid-children="[^"]*"', "", s)
    return s


def split_parts(s, label):
    """按 5 段切开。分段的锚点必须整份文件唯一，这里都做了断言。"""
    m = re.search(r"<style[^>]*>", s)
    assert m, f"{label}: 找不到 <style>"
    assert len(re.findall(r"<style[^>]*>", s)) == 1, f"{label}: <style> 不唯一"
    me = s.index("</style>", m.end())
    a = s.index("\nconst TABS = [")
    assert s.count("\nconst TABS = [") == 1, f"{label}: 'const TABS = [' 锚点不唯一"
    b = s.index("</script>", a)
    parts = {
        "styleOpen": s[: m.end()],
        "css": s[m.end(): me],
        "mid": s[me: a],
        "js": s[a: b],
        "tail": s[b:],
    }
    # 形状自检：锚点接错时立刻炸，不要静默产出坏文件
    assert parts["css"].startswith("\n:root{"), f"{label}: CSS 段不以 \\n:root{{ 开头"
    assert parts["mid"].startswith("</style>"), f"{label}: mid 段不以 </style> 开头"
    assert parts["js"].startswith("\nconst TABS = ["), f"{label}: JS 段锚点不对"
    assert parts["tail"].startswith("</script>"), f"{label}: tail 段不以 </script> 开头"
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="线上产物（带平台注入）")
    ap.add_argument("--new", required=True, help="本地 build_html.py 的产物")
    ap.add_argument("--out", default="merged.html")
    ap.add_argument("--mid-from", choices=["base", "new"], default="base",
                    help="③ 段用哪边（默认 base；数据包有变动时用 new）")
    args = ap.parse_args()

    base = open(args.base, encoding="utf-8").read()
    new = open(args.new, encoding="utf-8").read()
    B = split_parts(base, "base")
    N = split_parts(new, "new")

    print("段落长度（css / mid / js / tail）：")
    for lbl, P in (("base", B), ("new", N)):
        print("  %-5s %6d %8d %7d %4d" % (lbl, len(P["css"]), len(P["mid"]),
                                          len(P["js"]), len(P["tail"])))

    # 关键前提：
    #  ① 两边 tail 必须一致（都不带注入，纯 </script></body></html>）
    #  ② 剥注入后，base 的 mid 应当等于 new 的 mid（数据包没变、注入是唯一差别）
    #  ③ CSS 与 JS 必须真的变了，否则合并没意义
    assert B["tail"] == N["tail"], "两边 tail 不一致，合并逻辑要重看"
    mid_same = strip_injections(B["mid"]) == N["mid"]
    if not mid_same:
        print("  ⚠️ 剥注入后 base.mid != new.mid —— 中段（数据包/注入）有差异，下面会逐条报")
    assert N["css"] != B["css"] or N["js"] != B["js"] or not mid_same, \
        "新产物与线上没差别，无需合并"

    if args.mid_from == "base":
        mid = B["mid"]
        if not mid_same:
            print("  ⚠️ 你选了 --mid-from base，但中段不一致 —— 线上仍会用旧数据包。")
    else:
        # ⚠️ 细粒度合并：③ 段里「body 骨架 + 平台注入」沿用 base，**只把内联数据包换成 new 的**。
        # 整段用 N["mid"] 会把 body 上那批 data-page-node-id 和 pnid 注释一起抹掉 ——
        # 平台锚点没了，页面评论的定位就废了（2026-09-21 踩过一次：注入从 24 掉到 7）。
        def _split_db(m):
            i = m.index("const DB = {")
            j = m.index("};", i) + 2
            return m[:i], m[i:j], m[j:]

        hb, _db_b, tb = _split_db(B["mid"])
        hn, db_n, tn = _split_db(N["mid"])
        assert tb == tn, "mid 段的 DB 之后结构不一致，细粒度合并要重看"
        assert strip_injections(hb) == hn, \
            "mid 段的 body 骨架除注入外也有差异 —— 说明页面结构变了，需要人工合并"
        mid = hb + db_n + tb
        print("  ③ 段细粒度合并：body 骨架 / 平台注入用 base，内联数据包用 new")

    merged = B["styleOpen"] + N["css"] + mid + N["js"] + B["tail"]

    # ---- 硬校验：剥注入后必须与新产物逐字节相等 ----
    got = strip_injections(merged)
    if got != new:
        print("\n❌ 合并结果剥注入后 != 新产物，不产出文件。")
        import difflib
        d = list(difflib.unified_diff(new.split("\n"), got.split("\n"),
                                      "new", "merged(stripped)", n=1, lineterm=""))
        for l in d[:60]:
            print("   " + l[:170])
        print("   ... 共 %d 行差异" % len(d))
        return 1

    inj = {
        "data-page-node-id": merged.count("data-page-node-id"),
        "pnid 注释": merged.count("pnid:"),
        "inject.js": merged.count("page_comm/inject.js"),
    }
    print("\n✅ 剥注入后与新产物逐字节相等")
    print("   平台注入保留：%s" % "  ".join("%s×%d" % (k, v) for k, v in inj.items()))
    base_inj = base.count("data-page-node-id")
    assert inj["inject.js"] > 0, "注入没保住（inject.js 丢了），别上传"
    # 锚点数量必须与线上基线**完全一致** —— 只判 >0 挡不住"从 24 掉到 7"这种
    assert inj["data-page-node-id"] == base_inj, \
        "data-page-node-id 数量与线上基线不一致（%d vs %d），锚点丢了一批，别上传" % (
            inj["data-page-node-id"], base_inj)

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(merged)
    print("   写出 %s（%d 字节）" % (args.out, os.path.getsize(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
