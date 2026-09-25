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


# ⭐2026-09-25（v162 克隆旁路补强）：按元素顺序把 donor 的平台注入贴回 content。
#   为什么需要：merge 原策略是「base 出骨架、new 出内容」，前提是 body 骨架两边一样。
#   但线上那份可能是**克隆出来的旧快照**（页面名/标题停在旧版本），骨架文字与 new 不同 →
#   原策略会把旧文字保留下来（本次实测：线上 title/h1 还是「知识库」，而 new 已是「规划局」）。
#   正解 = **内容全用 new，只从 base 借注入**：注入是按元素分配的稳定 ID（评论定位用），
#   元素结构两边一致时可按下标一一贴回。
def reattach_injections(content, donor):
    """把 donor 的注入（data-page-node-id / data-pnid-children / <!--pnid--> / inject.js）贴到 content。

    · 标签属性注入：按「带注入标签的出现顺序」与 content 中「标签出现顺序」一一对应贴上。
      两边标签数必须相等，否则 raise（宁可炸，不静默贴错）。
    · inject.js：content 的 <head> 里补一行（donor 有才补）。
    · <!--pnid:xxx--> 注释：贴在 donor 中对应元素内容的开头。
    """
    TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>")

    def attrs_of(attr_str):
        out = {}
        for key in ("data-page-node-id", "data-pnid-children"):
            m = re.search(r'\s%s="([^"]*)"' % key, attr_str)
            if m:
                out[key] = m.group(1)
        return out

    # inject.js 的 <script> 单独处理（末尾补回）→ 比对前先从 donor 里剔除，避免标签数不等
    donor_cmp = re.sub(r'<script[^>]*src="/page/page_comm/inject\.js"[^>]*>\s*</script>\s*', "", donor)
    donor_all = list(TAG_RE.finditer(donor_cmp))
    content_all = list(TAG_RE.finditer(content))

    # 按「标签名序列」对齐：donor 里第 k 个 <div> 对应 content 里第 k 个 <div>。
    # 这样两边共有的元素按下标配对；donor 里带注入的标签必然是 content 里也有的同名元素。
    def name_seq(ms):
        return [m.group(1).lower() for m in ms]
    dn, cn = name_seq(donor_all), name_seq(content_all)
    if dn != cn:
        # 名字序列必须完全一致 —— 这是「结构相同」的强判据
        import difflib
        d = list(difflib.unified_diff(dn, cn, "donor_tags", "content_tags", n=0, lineterm=""))[:30]
        raise AssertionError(
            "注入贴回失败：标签名序列不一致（donor %d 个 / content %d 个）—— 元素结构变了，别硬贴\n  %s"
            % (len(dn), len(cn), "\n  ".join(d)))

    # 从后往前替换，避免下标位移
    out = content
    pairs = [(content_all[i], attrs_of(donor_all[i].group(2)))
             for i in range(len(donor_all))]
    pairs = [(m, a) for m, a in pairs if a]
    for m, a in reversed(pairs):
        add = "".join(' %s="%s"' % (k, v) for k, v in a.items())
        i = m.end() - 1                       # '>' 的位置
        out = out[:i] + add + out[i:]

    # <!--pnid:xxx--> 注释：donor 里它贴在某个标签的**内容开头**，
    # 这里按「该标签在标签序列里的下标」映射到 content 同下标标签的内容开头。
    note_at = {}                       # 标签下标 -> pnid 值
    for i, m in enumerate(donor_all):
        tail = donor_cmp[m.end(): m.end() + 80]
        nm = re.match(r"<!--pnid:([^>]*)-->", tail)
        if nm:
            note_at[i] = nm.group(1)
    if note_at:
        out_tags = list(TAG_RE.finditer(out))
        # 从后往前插，避免位移
        for i in sorted(note_at, reverse=True):
            if i < len(out_tags):
                j = out_tags[i].end()
                out = out[:j] + "<!--pnid:%s-->" % note_at[i] + out[j:]

    # inject.js：content 的 <head> 后补（连它自己的平台注入一起搬，否则会少 1 个锚点）
    if 'page_comm/inject.js' in donor and 'page_comm/inject.js' not in out:
        dm = re.search(r'<script([^>]*src="/page/page_comm/inject\.js"[^>]*)>\s*</script>', donor)
        m = re.search(r"<head\b[^>]*>", out)
        if dm and m:
            i = m.end()
            out = out[:i] + "\n<script%s></script>" % dm.group(1) + out[i:]
    return out


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


def _count_node_ids(s):
    """统计**标签上**的 data-page-node-id（⭐不能用裸 str.count）。

    裸 count 会把**页面正文里**的同名字符串也数进去 —— 实测踩过：v164 的版本说明里
    写了「data-page-node-id 24/24」「把 data-page-node-id 挪到 lang 前」，这两处随
    changelog 进入内联数据，导致统计 24 → 26，锚点校验误报拒收（实际锚点值集合完全相同）。
    判据必须是「出现在 <tag ...> 内部」，且用 [^<>]* 保证不跨标签边界。
    """
    return len(re.findall(r'<[a-zA-Z][^<>]*\sdata-page-node-id="[^"]*"', s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="线上产物（带平台注入）")
    ap.add_argument("--new", required=True, help="本地 build_html.py 的产物")
    ap.add_argument("--out", default="merged.html")
    ap.add_argument("--mid-from", choices=["base", "new"], default="base",
                    help="③ 段用哪边（默认 base；数据包有变动时用 new）")
    ap.add_argument("--allow-skeleton-diff", action="store_true",
                    help="线上快照与本地新产物的**文字**不同（如页面改名）时启用："
                         "改为「内容全用 new（含新标题/新数据包），平台注入从 base 按元素下标贴回」。"
                         "默认关闭 —— 关闭时骨架不一致会直接拒绝（防结构漂移）。")
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
    elif args.allow_skeleton_diff:
        # ⭐2026-09-25（v162 克隆旁路）：**内容全用 new，只从 base 借注入**。
        #   适用场景：线上那份是**克隆出的旧快照**，页面标题/名称停在旧版本，
        #   骨架文字与 new 不同（实测：线上 title/h1 还是「知识库」，new 已是「规划局」）。
        #   老策略「base 出骨架」会把旧文字带回线上 → 等于改名白做。
        #   做法：把 N["mid"] 原样拿来，把 base 的元素级注入按下标贴回。
        mid = reattach_injections(N["mid"], B["mid"])
        print("  ③ 段：内容用 new（含新数据包），base 的平台注入按元素下标贴回")
    else:
        # 细粒度合并：③ 段里「body 骨架 + 平台注入」沿用 base，**只把内联数据包换成 new 的**。
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
            "mid 段的 body 骨架除注入外也有差异 —— 说明页面结构变了，需要人工合并" \
            "（若是线上快照文字过旧，加 --allow-skeleton-diff 走「new 出内容 + 注入贴回」）"
        mid = hb + db_n + tb
        print("  ③ 段细粒度合并：body 骨架 / 平台注入用 base，内联数据包用 new")

    # 前缀段同理：--allow-skeleton-diff 时用 new 的前缀（新标题），注入贴回
    if args.allow_skeleton_diff:
        styleOpen = reattach_injections(N["styleOpen"], B["styleOpen"])
        print("  ① 段：前缀用 new（含新 <title>），base 注入贴回")
    else:
        styleOpen = B["styleOpen"]

    merged = styleOpen + N["css"] + mid + N["js"] + B["tail"]

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
        "data-page-node-id": _count_node_ids(merged),
        "pnid 注释": merged.count("pnid:"),
        "inject.js": merged.count("page_comm/inject.js"),
    }
    print("\n✅ 剥注入后与新产物逐字节相等")
    print("   平台注入保留：%s" % "  ".join("%s×%d" % (k, v) for k, v in inj.items()))
    base_inj = _count_node_ids(base)
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
