# -*- coding: utf-8 -*-
"""
终末地基建知识库 —— 命令行查询工具

用法：
  python ake.py 建筑 <关键词>          查建筑（名称/ID/描述模糊匹配）
  python ake.py 建筑 --地区 武陵        按地区列建筑
  python ake.py 建筑 --分类 电力设施     按分类列建筑
  python ake.py 蓝图 <关键词>          查占地格数 + 接口布局（搭蓝图用）
  python ake.py 蓝图 --接口 │ --无接口 │ --规格 │ --详细
  python ake.py 基地                   各基地建设区面积、扩建价目、据点建造上限
  python ake.py 基地 <关键词>          查某个建造区/据点
  python ake.py 基地 --详细             展开据点发展等级逐级上限矩阵
  python ake.py 物流                   物流规则总览（传送带/管道吞吐 + 关键常量）
  python ake.py 物流 管道               查物流实体
  python ake.py 物流 --常量             只列全局物流常量
  python ake.py 物流 --蓝图码           蓝图系统规则（码前缀/大小/上限）
  python ake.py 规则                   玩法机制规则（开采/无线传输/管道/区域限制）
  python ake.py 规则 无线              搜规则（附原文证据，可复核）
  python ake.py 物品 <关键词>          查物品及产出/消耗链路
  python ake.py 配方 <关键词>          查机器配方
  python ake.py 建造 <关键词>          查建造配方（造一个建筑要什么材料）
  python ake.py 手工 <关键词>          查手工配方
  python ake.py 数值                   列出所有带机制数值的设施
  python ake.py 地区                   地区概览
  python ake.py 树 <物品名>            追溯物品完整上下游链
  python ake.py 统计                   数据包概览
"""
import json
import os
import sys
import io
import argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

# 三个配方表。items.json 里的 producedBy/consumedBy 混了三种 kind，
# 必须按 kind 查对应表，否则会静默漏掉 169 条建造/手工配方。
RECIPE_TABLES = {
    "machine": ("machine_recipes.json", "机器配方"),
    "build": ("build_recipes.json", "建造配方"),
    "manual": ("manual_recipes.json", "手工配方"),
}

_cache = {}


def J(name):
    if name not in _cache:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            _cache[name] = json.load(f)
    return _cache[name]


def hit(text, kw):
    if not kw:
        return True
    return kw.lower() in str(text).lower()


def hr(ch="─", n=74):
    print(ch * n)


def dw(s):
    """显示宽度：中日韩字符按 2 列算。中文列对齐必须用它，不能用 str.format 的 <。"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def pad(s, width, right=False):
    s = str(s)
    n = max(0, width - dw(s))
    return (" " * n + s) if right else (s + " " * n)


def wrap(s, width=88, indent="    "):
    """按显示宽度折行（中文按 2 列算）。返回多行文本，首行不带缩进。"""
    if not s:
        return []
    s = str(s).replace("\n", " ")
    lines, cur, w = [], "", 0
    for ch in s:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > width:
            lines.append(cur)
            cur, w = "", 0
        cur += ch
        w += cw
    if cur:
        lines.append(cur)
    return [lines[0]] + [indent + ln for ln in lines[1:]]


def p_wrap(s, indent="    ", width=88):
    for ln in wrap(s, width, indent):
        print(indent + ln if ln is not s else ln)


def fmt_mechanics(mm):
    """把 mechanics dict 拍成 '作用范围 80m / 间隔 8 秒 / 攻击力 45375'。"""
    parts = []
    if "rangeMeters" in mm:
        parts.append(f'作用范围 {mm["rangeMeters"]:g}m')
    if "intervalSeconds" in mm:
        parts.append(f'间隔 {mm["intervalSeconds"]:g} 秒')
    if "attack" in mm:
        parts.append(f'攻击力 {mm["attack"]}')
    return " / ".join(parts)


def show_building(b):
    dom = "/".join(b["domainNames"]) if b["domainNames"] else "全地区通用"
    print(f'  [{b["categoryName"]}] {b["name"]}   ({b["id"]})')
    print(f'    地区: {dom}   占地: {b["footprint"]}   ' +
          (f'耗电: {b["powerConsume"]}' if b["needPower"] else '无需通电') +
          f'   协议容量: {b["bandwidth"]}')
    if b.get("hasPlaceLimit"):
        print("    ⚠ 有放置数量上限")
    if b.get("mechanics"):
        print(f'    ★ {fmt_mechanics(b["mechanics"])}')
    if b.get("desc"):
        p_wrap(b["desc"])


def cmd_building(a):
    sel = J("buildings.json")
    if a.地区:
        sel = [b for b in sel if a.地区 in (b["domainNames"] or ["全地区通用"])]
    if a.分类:
        sel = [b for b in sel if a.分类 in b["categoryName"] or a.分类 == b["category"]]
    if a.关键词:
        sel = [b for b in sel if hit(b["name"], a.关键词) or hit(b["id"], a.关键词)
               or hit(b["desc"], a.关键词)]
    if not sel:
        print("无匹配结果。")
        return
    hr()
    print(f"建筑 {len(sel)} 条")
    hr()
    cat = None
    for b in sel:
        if b["categoryName"] != cat and not a.关键词:
            cat = b["categoryName"]
            print(f'\n【{cat}】')
        show_building(b)
    print()


def render_grid(b):
    """把接口坐标画成 ASCII 平面图。
    I = 进料口(传送带)  i = 进料口(管道)
    O = 出料口(传送带)  o = 出料口(管道)  X = 同格多口"""
    fp = (b.get("gridFootprint") or "").split("×")
    if len(fp) != 2:
        return []
    try:
        W, D = int(fp[0]), int(fp[1])
    except ValueError:
        return []
    g = [["·"] * W for _ in range(D)]
    for p in b.get("ports", []):
        x, z = p.get("x"), p.get("z")
        if not isinstance(x, int) or not isinstance(z, int):
            continue
        if not (0 <= x < W and 0 <= z < D):
            continue
        ch = ("i" if p["isPipe"] else "I") if p["kind"] == "input" else ("o" if p["isPipe"] else "O")
        if g[z][x] == "·":
            g[z][x] = ch
        elif g[z][x] != ch:
            g[z][x] = "X"
    return g


def cmd_blueprint(a):
    bp = J("blueprint.json")

    if a.规格:
        hr()
        print("占格规格分组（同尺寸可共用蓝图网格）")
        hr()
        print(f'  {"规格":<8}{"格高":>5}{"面积":>8}{"数量":>7}{"占地合计":>10}')
        for g in bp["footprintGroups"]:
            print(f'  {g["footprint"]:<8}{g["height"]:>5}{str(g["area"])+"格²":>8}'
                  f'{str(g["count"])+"座":>7}{str(g["area"]*g["count"])+"格²":>10}')
        print()
        s = bp["summary"]
        print(f'  合计 {s["total"]} 座建筑，占地 {s["totalArea"]} 格²；'
              f'有接口 {s["withPorts"]} 座，无接口 {s["noPorts"]} 座')
        print()
        return

    sel = bp["buildings"]
    if a.接口:
        sel = [b for b in sel if b["portCount"] > 0]
    if a.无接口:
        sel = [b for b in sel if b["portCount"] == 0]
    if a.关键词:
        sel = [b for b in sel if hit(b["name"], a.关键词) or hit(b["id"], a.关键词)
               or hit(b["gridFootprint"], a.关键词)]
    if not sel:
        print("无匹配结果。")
        return

    hr()
    print(f'占地蓝图 {len(sel)} 条　（单位：格。宽×深=地面占格；格高=可堆叠高度依据）')
    hr()
    shown = sel if a.全部 else sel[:a.限制]
    for b in shown:
        dom = "/".join(b.get("domainNames") or ["全地区通用"])
        print(f'\n  {b["name"]}  [{b["categoryName"]}]  {b["id"]}')
        print(f'    占地 {b["gridFootprint"]} 格 · 面积 {b["gridArea"]} 格² · '
              f'格高 {b["gridHeight"]} · 外圈 {b["gridPerimeter"]} 格 · '
              f'{"正方形" if b["isSquare"] else "非正方形"}（长宽比 {b["aspect"]}）')
        print(f'    地区 {dom}' +
              (f' · 耗电 {b["powerConsume"]}' if b["needPower"] else ' · 无需通电') +
              (' · 有数量上限' if b["hasPlaceLimit"] else '') +
              (' · 支持液体' if b["liquidEnabled"] else ''))
        if b["portCount"]:
            print(f'    接口 {b["portCount"]} 个（{b["portSummary"]}）· '
                  f'进料口: {b["inputEdgeLabel"]} · 出料口: {b["outputEdgeLabel"]}'
                  + ('  ⚠ 进出在同一组边，走线需交错' if b["mixedSides"] else ''))
        else:
            print('    无物流接口（纯占地/装饰）')
        g = render_grid(b)
        if g:
            print()
            w = len(g[0])
            for z, row in enumerate(g):
                print(f'      {z:>2} │ ' + " ".join(row))
            print(f'         └' + "─" * (w * 2 - 1))
            print('         I/i=进料(传送带/管道)  O/o=出料(传送带/管道)  X=同格多口')
            print('         列方向 = x（0 ~ %d）；行号 = z（0 ~ %d）' % (w - 1, len(g) - 1))
        if a.详细:
            for p in b["ports"]:
                print(f'      {p["kind"]:<6} #{p["index"]}  x={p["x"]} y={p["y"]} z={p["z"]}'
                      f'   {p["edgeLabel"]}  {p["medium"]}')
    if len(sel) > len(shown):
        print(f'\n  命中 {len(sel)} 条，仅显示前 {len(shown)} 条（加 --全部 显示全部）')
    print()
    print('  ※ 边名用格坐标（z=0 / z=D-1 / x=0 / x=W-1），只表示"口在这块地的哪条边"，')
    print('    不声称游戏内绝对方位。modelHeight 是模型实际高度，纯视觉，蓝图不要用。')
    print()


def cmd_item(a):
    items = J("items.json")
    sel = [v for k, v in items.items() if hit(v["name"], a.关键词) or hit(k, a.关键词)]
    if not sel:
        print("无匹配结果。")
        return
    hr()
    print(f"物品 {len(sel)} 条")
    hr()
    for v in sel:
        print(f'\n  {v["name"]}  ({v["id"]})  R{v["rarity"]}')
        if v["desc"]:
            p_wrap(v["desc"])
        if v["producedBy"]:
            print("    产出:")
            for p in v["producedBy"]:
                sec = f'  {p["seconds"]}秒' if p.get("seconds") else ""
                print(f'      · {p["machine"]}  x{p["count"]}{sec}   [{p["recipeId"]}]')
        else:
            print("    产出: (原料 / 采集获得，无制造配方)")
        if v["consumedBy"]:
            print("    消耗于:")
            for c in v["consumedBy"]:
                print(f'      · {c["machine"]}  x{c["count"]}   [{c["recipeId"]}]')
    print()


def _show_recipe(r, kind="机器"):
    print(f'\n  [{kind}] {r["id"]}')
    if r.get("machineName"):
        print(f'    设备: {r["machineName"]}')
    if r.get("domainName"):
        print(f'    地区: {r["domainName"]}')
    if r.get("seconds"):
        print(f'    耗时: {r["seconds"]} 秒')
    if r.get("desc"):
        print(f'    说明: {r["desc"]}')
    ing = "  +  ".join(f'{i["name"]} x{i["count"]}' for i in r["ingredients"]) or "(无输入)"
    out = "  +  ".join(f'{o["name"]} x{o["count"]}' for o in r["outcomes"]) or "(无输出)"
    print(f'    {ing}')
    print(f'      ->  {out}')


def _limit(sel, a, label, unit="条"):
    """统一的截断 + 提示。返回 (显示列表, 是否被截断)。"""
    if not a.全部 and len(sel) > a.限制:
        print(f"{label} {len(sel)} {unit}，仅显示前 {a.限制} {unit}（加 --全部 显示全部）")
        return sel[:a.限制]
    return sel


def cmd_recipe(a):
    sel = [r for r in J("machine_recipes.json")
           if hit(r["id"], a.关键词) or hit(r.get("machineName"), a.关键词)
           or any(hit(i["name"], a.关键词) for i in r["ingredients"])
           or any(hit(o["name"], a.关键词) for o in r["outcomes"])]
    if a.设备:
        sel = [r for r in sel if hit(r.get("machineName"), a.设备)]
    if not sel:
        print("无匹配结果。")
        return
    sel = _limit(sel, a, "命中")
    hr()
    print(f"机器配方 {len(sel)} 条")
    hr()
    for r in sel:
        _show_recipe(r)
    print()


def cmd_build(a):
    sel = [r for r in J("build_recipes.json")
           if hit(r["id"], a.关键词) or hit(r.get("name"), a.关键词)
           or any(hit(i["name"], a.关键词) for i in r["ingredients"])]
    if not sel:
        print("无匹配结果。")
        return
    sel = _limit(sel, a, "命中")
    hr()
    print(f"建造配方 {len(sel)} 条")
    hr()
    for r in sel:
        print(f'\n  {r["name"]}  ({r["id"]})  R{r["rarity"]}  解锁等级 {r["usableLevel"]}')
        if r["techDomains"]:
            print(f'    科技树: {"/".join(r["techDomains"])}   [{", ".join(r["groups"])}]')
        ing = "  +  ".join(f'{i["name"]} x{i["count"]}' for i in r["ingredients"]) or "(无)"
        out = "  +  ".join(f'{o["name"]} x{o["count"]}' for o in r["outcomes"])
        print(f'    {ing}')
        print(f'      ->  {out}')
    print()


def cmd_manual(a):
    sel = [r for r in J("manual_recipes.json")
           if hit(r["name"], a.关键词)
           or any(hit(i["name"], a.关键词) for i in r["ingredients"])]
    if a.地区:
        sel = [r for r in sel if a.地区 in r["domainName"]]
    if not sel:
        print("无匹配结果。")
        return
    sel = _limit(sel, a, "命中")
    hr()
    print(f"手工配方 {len(sel)} 条")
    hr()
    for r in sel:
        ing = "  +  ".join(f'{i["name"]} x{i["count"]}' for i in r["ingredients"])
        out = "  +  ".join(f'{o["name"]} x{o["count"]}' for o in r["outcomes"])
        print(f'  [{r["domainName"]}] {r["name"][:20]:<22} {ing[:46]:<48} -> {out}')
    print()


def cmd_mechanics(a):
    ms = J("mechanics.json")
    if a.关键词:
        ms = [m for m in ms if hit(m["name"], a.关键词) or hit(m["desc"], a.关键词)]
    if not ms:
        print("无匹配结果。")
        return
    hr()
    print("带机制数值的设施（数据来源：建筑描述文本）")
    hr()
    for m in ms:
        parts = fmt_mechanics(m["mechanics"]).replace("作用范围 ", "").replace(" 秒", "秒")
        dom = "/".join(m["domainNames"])
        print(f'  {m["name"]:<16} {parts:<22} [{dom}]')
        if a.详细:
            p_wrap(m["desc"], indent="      ")
    print()


def cmd_region(a):
    hr()
    print("地区概览")
    hr()
    for name, v in J("regions.json").items():
        print(f'\n  【{name}】')
        print(f'    建筑 {v["count"]} 个（需通电 {v["powered"]}）'
              f'   手工配方 {v.get("manualRecipes", 0)}'
              f'   建造配方 {v.get("buildRecipes", 0)}')
    print()


def _recipe_index():
    """把三个配方表合成 {recipeId: (配方, 表标签)}。
    items.json 的 kind 字段决定去哪张表找；kind 缺失时按 id 前缀兜底猜。"""
    idx = {}
    for kind, (fname, label) in RECIPE_TABLES.items():
        for r in J(fname):
            idx[r["id"]] = (r, label)
    return idx


def cmd_tree(a):
    """追溯物品的完整上下游链。"""
    items = J("items.json")
    match = [v for k, v in items.items() if hit(v["name"], a.关键词) or hit(k, a.关键词)]
    if not match:
        print("无匹配结果。")
        return
    idx = _recipe_index()
    for v in match[:3]:
        hr()
        print(f'{v["name"]} ({v["id"]})')
        hr()
        if v["desc"]:
            print(f'  {v["desc"]}\n')
        print("  ▼ 产出途径")
        if v["producedBy"]:
            for p in v["producedBy"]:
                sec = f'  耗时 {p["seconds"]}秒' if p.get("seconds") else ""
                print(f'    · {p["machine"]} ×{p["count"]}{sec}')
                ent = idx.get(p["recipeId"])
                if ent:
                    r, label = ent
                    ing = " + ".join(f'{i["name"]}×{i["count"]}' for i in r["ingredients"])
                    print(f'        需要: {ing or "(无)"}   [{label}]')
                else:
                    print(f'        需要: (配方 {p["recipeId"]} 不在库中)')
        else:
            print("    (采集 / 原料)")
        print("\n  ▲ 用途")
        if v["consumedBy"]:
            for c in v["consumedBy"][:20]:
                print(f'    · {c["machine"]} ×{c["count"]}   [{c["recipeId"]}]')
            if len(v["consumedBy"]) > 20:
                print(f'    … 另有 {len(v["consumedBy"]) - 20} 条')
        else:
            print("    (暂无下游配方)")
        print()


def _show_constants(consts, only_group=None):
    last = None
    for c in consts:
        if only_group and c["group"] != only_group:
            continue
        if c["group"] != last:
            print(f'\n  【{c["group"]}】')
            last = c["group"]
        unit = f' {c["unit"]}' if c["unit"] else ""
        print(f'    {c["label"]:<26} {c["value"]}{unit}')
        print(f'      {c["key"]}')


def cmd_logistics(a):
    L = J("logistics.json")

    if getattr(a, "蓝图码", False):
        b = L["blueprintRules"]
        hr("=")
        print("蓝图系统规则（FacBlueprintConst）")
        hr("=")
        print(f'  分享码前缀    {" 或 ".join(b["shareCodePrefix"])}')
        print(f'  码字符集      {b["charSet"]}')
        print(f'  蓝图最大范围  {b["maxLenX"]} × {b["maxLenZ"]} 格')
        print(f'  节点上限      {b["nodeCountLimit"]}')
        print(f'  我的蓝图上限  {b["myBlueprintMax"]}')
        print(f'  赠送上限      {b["giftBlueprintMax"]}')
        print(f'  分享码有效期  {b["shareExpireSeconds"]} 秒'
              f'（{b["shareExpireSeconds"]/86400:.0f} 天）')
        print(f'  名称/描述上限 {b["nameMaxLen"]} / {b["descMaxLen"]} 字')
        print(f'  标签上限      {b["tagMax"]}')
        print()
        print("  ⚠ 码本身是加密串，配置表不含解码规则；表里只有长度与字符集约束。")
        print()
        return

    if getattr(a, "常量", False):
        hr("=")
        print("全局物流常量（FactoryConst）")
        hr("=")
        _show_constants(L["constants"])
        print()
        return

    kw = a.关键词.strip().lower()
    ents = L["entities"]
    if kw:
        ents = [e for e in ents if kw in str(e.get("name") or "").lower()
                or kw in e["id"].lower()
                or kw in str(e.get("type") or "").lower()
                or kw in e["medium"]]

    if not kw:
        hr("=")
        print("物流规则层总览")
        hr("=")
        print("\n  【吞吐速查】")
        for t in L["throughputSummary"]:
            print(f'    {t["name"]:<8} {t["perSecond"]:>5} 个/秒  =  {t["perMinute"]:>6} 个/分钟')
            print(f'      {t["source"]}')
        print("\n  【连接限制（关键常量）】")
        for c in L["constants"]:
            if c["group"] == "连接距离与角度":
                unit = f' {c["unit"]}' if c["unit"] else ""
                print(f'    {c["label"]:<26} {c["value"]}{unit}')
        print("\n  【采矿 / 抽水】")
        for m in L["miners"]:
            print(f'    {m["id"]:<10} {m["unitsPerMinute"]:>6} /min  '
                  f'可采 {"、".join(n for n in m["mineableNames"] if n)}')
        for p in L["pumps"]:
            if p.get("unitsPerMinute") is not None:
                print(f'    {p["id"]:<10} {p["unitsPerMinute"]:>6} /min  {p["kind"]}')

        print("\n  【暗管（地下管道）—— 入口/出口成对配对】")
        for u in L.get("undergroundPipes", []):
            port = (f'{u["inputPortCount"]} 进' if u["role"] == "入口"
                    else f'{u["outputPortCount"]} 出')
            print(f'    {u["id"]:<22} {u["name"]:<12} [{u["role"]}] {u["gridFootprint"]:>6}  {port}')
        print('      最大配对连接长度 300（udPipeConnectMaxLength）')

        print("\n  【_nop_ 免电变体】同一设施的通电版 / 免电版，官方名相同")
        for n in L.get("nopVariants", []):
            same = "同名" if n["sameName"] else "异名"
            print(f'    {n["baseId"]:<22}({n["baseName"]}, 电{n["basePower"]:>2})'
                  f'  ->  {n["nopId"]:<24}(电{n["nopPower"]:>2})  {same}')
        print("      ⚠️ _nop_ 版官方名沿用原版，不要叫成「免电XX」。")
        print()

    hr("-")
    if ents:
        print(f'{"ID":<24}{"名称":<12}{"类型":<16}{"吞吐/min":>9}  端口(进/出)')
        hr("-")
        for e in ents:
            print(f'{e["id"]:<24}{str(e.get("name")):<12}{str(e.get("type")):<16}'
                  f'{e["unitsPerMinute"]:>9}  {e["inputPortCount"]}/{e["outputPortCount"]}'
                  f'  [{e["medium"]}]')
        print()
        print("  端口朝向（0/90/180/270，相对自身）：")
        for e in ents:
            fi = "/".join(str(x) for x in e["inputFacings"]) or "—"
            fo = "/".join(str(x) for x in e["outputFacings"]) or "—"
            print(f'    {str(e.get("name")):<12} 进 {fi:<18} 出 {fo}')
    else:
        print("  没有匹配的物流实体")
    print()
    print("  提示：`ake.py 物流 --常量` 看全部常量，`ake.py 物流 --蓝图码` 看蓝图系统规则。")
    print()


def cmd_base(a):
    """基地面积与建造上限。
    注意：面积/路数是社区实测，配置表里没有 —— 输出里单独标注，别和配置表数据混着引用。"""
    B = J("bases.json")
    kw = (a.关键词 or "").strip().lower()

    if kw:
        zs = [z for z in B["zones"]
              if kw in z["zoneName"].lower() or kw in z["levelId"].lower()
              or kw in z["domainName"].lower()
              or any(kw in s["name"].lower() for s in z.get("settlements") or [])]
        if not zs:
            print(f'没有匹配「{a.关键词}」的建造区。')
            return
        maxby = {r["levelId"]: r for r in (B.get("maxBases") or [])}
        hr("=")
        print(f'建造区 {len(zs)} 条')
        hr("=")
        for z in zs:
            stm = "、".join(s["name"] for s in z.get("settlements") or []) or "—"
            print(f'\n  {z["zoneName"]}  ({z["levelId"]})   据点: {z["domainName"]}')
            print(f'    仓库/据点: {stm}')
            mr = maxby.get(z["levelId"])
            if mr:
                ar, c = (mr["area"] or {}), (mr["caps"] or {})
                print('    ── 以下按满级上限口径 ──')
                if ar:
                    print(f'    {mr["role"]}（{ar["coreName"]}）  {ar["size"]} = {ar["cells"]} 格'
                          f' · 可建 {ar["usableCells"]} 格 · 单边 {ar["slotsPerSide"]} 路存取口'
                          f'{"" if ar["slotMeasured"] else "（推算）"}'
                          f' · {ar["blueprint"]["note"]}')
                if not z["hasBuiltArea"]:
                    print('    ⚠ 这个建造区没有基地；下表的协议容量只约束区内野外设备')
                print(f'    满级建造上限  协议容量 {c.get("bandwidth")}'
                      f' · 防御建筑 {c.get("battleBuildingLimit")} · 滑索 {c.get("travelPoleLimit")}'
                      + ('（已含矿机产出提升）' if c.get("mineOutputUp") else ''))
            if z["hasBuiltArea"]:
                for e in z["expansion"]:
                    tgt = f'→ 区域等级 {e["targetLevel"]}' if e.get("targetLevel") else ""
                    print(f'    区域扩大: {e["name"]:<12}{e["cost"]:>8} {e["currency"]}  {tgt}')
                print(f'    仓库存取线 {z["busCount"]} 档，合计 {z["busCostTotal"]} {z["currency"]}')
                tot = (z["expansionCostTotal"] or 0) + (z["busCostTotal"] or 0)
                print(f'    全解锁合计: {tot} {z["currency"]}')
            else:
                print('    配置表里没有「区域扩大」条目（原因未说明）')
        print()
        return

    hr("=")
    print("基地面积与建造上限")
    hr("=")

    # 头牌：满级基地总览（每片基地一行，全部按最大值取）
    rows = B.get("maxBases") or []
    if rows:
        S = B.get("maxBasesSummary") or {}
        # (表头, 宽度, 是否右对齐)
        COLS = [("基地", 14, False), ("据点", 10, False), ("类型（核心）", 14, False),
                ("建设区（满级）", 20, False), ("存取口", 8, True),
                ("协议容量", 10, True), ("防御/滑索", 12, True), ("全解锁券", 10, True)]

        def prow(cells):
            return "    " + "  ".join(pad(c, w, r) for c, (_, w, r) in zip(cells, COLS))

        print("\n【满级基地总览】（每片基地一行 · 全部按最大值取）")
        print("    口径：据点发展等级取满级、建设区取区域扩大·二之后的边长、")
        print("          协议容量/防御建筑上限/滑索上限取满级那一档。")
        print("    ⚠ 面积没有逐片实测值 —— 这里是把地区实测上限套用到同类型的每片基地，属上限口径。")
        print("    ℹ 每个据点是「1 主 + 3 副」：四号谷地主基地=枢纽区，武陵主基地=武陵城。")
        print("      主基地放协议核心、副基地放次级核心，每片只有一个建设区。")
        print("    ℹ 只有下表这 8 片有基地（配置表里有「区域扩大」条目）；")
        print("      %d 个建造区里其余 %d 个没有基地，协议容量只约束野外设备，不列入下表。"
              % (S.get("zonesTotal", 0), S.get("zonesTotal", 0) - S.get("rows", 0)))
        print()
        print(prow([c[0] for c in COLS]))
        print("    " + "-" * (sum(c[1] for c in COLS) + 2 * (len(COLS) - 1)))
        for r in rows:
            ar, c = r["area"] or {}, (r["caps"] or {})
            bw = str(c.get("bandwidth")) if c.get("bandwidth") is not None else "—"
            if c.get("mineOutputUp"):
                bw += "+矿"
            area_txt = "%s = %d 格" % (ar.get("size", "—"), ar.get("cells", 0)) if ar else "—"
            print(prow([
                r["zoneName"],
                r["domainName"],
                "%s（%s）" % (r["role"], ar.get("coreName", "—") if ar else "—"),
                area_txt,
                str(ar.get("slotsPerSide", "—")) + ("" if ar.get("slotMeasured") else "?"),
                bw,
                "%s/%s" % (c.get("battleBuildingLimit", "—"), c.get("travelPoleLimit", "—")),
                (str(r["unlockCostTotal"]) if r.get("unlockCostTotal") else "—"),
            ]))
        print("    " + "-" * (sum(c[1] for c in COLS) + 2 * (len(COLS) - 1)))
        print(prow(["合计", "2 个据点",
                    "%d 主 + %d 副" % (S.get("mainCount", 0), S.get("subCount", 0)),
                    "%d 格" % S.get("cellsTotal", 0), "",
                    str(S.get("protocolCapacityTotal", 0)), "", "—"]))
        for name, d in (S.get("cellsByDomain") or {}).items():
            print("      %s：%d 主 %d 格 + %d 副 %d 格 = %d 格"
                  % (name, d.get("mainN", 0), d.get("main", 0),
                     d.get("subN", 0), d.get("sub", 0), d.get("total", 0)))
        print("    券种按据点分，两种券不能相加：%s" % "　／　".join("%s %s"
              % (k, v) for k, v in (S.get("unlockCostByCurrency") or {}).items()))
        print("    「全解锁券」= 区域扩大·一/二 + 全部仓库存取线，同一种券累加。")
        print("    存取口带 ? 的是按 (边长-1)/3 推算，未实测。")
        print("    拓展价目明细见下方「扩建价目」一节。")
        print()

    print("\n【各基地建设区域面积（按地区看 · 满级）】")
    print("  ⚠ 这一节是社区实测，不在配置表里；下面几节才是配置表数据。")
    for x in B["areas"]:
        src = "、".join(s["id"] for s in x["sources"])
        print(f'    {pad(x["domainName"] + " " + x["kind"], 16)}{pad(x["size"], 9, True)} '
              f'= {pad(str(x["cells"]) + " 格", 8, True)}   单边 {pad(x["slotsPerSide"], 2, True)} 路存取口'
              f'   [来源 {src}]')
        print(f'      {x["confidence"]}　扣掉{x["coreName"]} 9×9 后可建 {x["usableCells"]} 格')
    print(f'    {B["slotRule"]["formula"]}（1 个存取口占 {B["slotRule"]["slotWidthCells"]} 格宽）')

    print("\n【面积 vs 蓝图上限】")
    for c in B["areaComparisons"]:
        mark = "  ← 正好一张满规格蓝图" if c["exactMatch"] else ""
        print(f'    {pad(c["label"], 16)}{pad(c["size"], 9, True)}   {c["note"]}{mark}')

    print("\n【蓝图系统硬上限】（配置表 FacBlueprintConst）")
    for c in B["blueprintCaps"]:
        print(f'    {pad(c["label"], 20)}{pad(c["value"], 34)}({c["key"]})')

    print("\n【扩建价目】（集成管家，配置表 FactoryPanelStoreTable）")
    print(f'    {pad("建造区", 16)}{pad("据点", 10)}{pad("券", 8)}'
          f'{pad("扩大·一", 10, True)}{pad("扩大·二", 10, True)}{pad("存取线", 8, True)}{pad("全解锁", 10, True)}')
    for z in B["zones"]:
        if not z["hasBuiltArea"]:
            continue
        e1 = z["expansion"][0]["cost"] if z["expansion"] else None
        e2 = z["expansion"][1]["cost"] if len(z["expansion"]) > 1 else None
        tot = (z["expansionCostTotal"] or 0) + (z["busCostTotal"] or 0)
        print(f'    {pad(z["zoneName"], 16)}{pad(z["domainName"], 10)}{pad(z["currency"], 8)}'
              f'{pad(e1 if e1 is not None else "-", 10, True)}'
              f'{pad(e2 if e2 is not None else "-", 10, True)}'
              f'{pad(z["busCount"], 8, True)}{pad(tot, 10, True)}')

    print("\n【据点发展等级 → 建造上限】（配置表 DomainDataTable）")
    print("    格内读法：协议容量  防御建筑上限/滑索上限  （+矿 = 该等级起矿机产出提升）")
    for d in B["domains"]:
        zones = (d["levels"][0]["regions"] if d["levels"] else [])
        print(f'\n    ◆ {d["name"]}　满级 Lv{d["maxLevel"]}　仓库名「{d["storageName"]}」')
        if a.详细:
            head = "".join(pad(z["zoneName"], 12, True) for z in zones)
            print(f'      {pad("Lv", 5)}{pad("升级经验", 10, True)}{pad("资金上限", 11, True)}{head}')
            for l in d["levels"]:
                cells = ""
                for z in zones:
                    r = next((x for x in l["regions"] if x["levelId"] == z["levelId"]), None)
                    if not r:
                        cells += pad("—", 12, True)
                    else:
                        cells += pad(str(r["bandwidth"]) + ("+矿" if r["mineOutputUp"] else ""), 12, True)
                print(f'      {pad(l["level"], 5)}{pad(l["levelUpExp"], 10, True)}'
                      f'{pad(l["moneyLimit"], 11, True)}{cells}')
        else:
            last = d["levels"][-1] if d["levels"] else None
            for z in zones:
                r = next((x for x in last["regions"] if x["levelId"] == z["levelId"]), None) if last else None
                capn = "—" if not r else f'{r["bandwidth"]}'
                extra = "" if not r else (f'  防御 {r["battleBuildingLimit"]} / 滑索 {r["travelPoleLimit"]}')
                star = "" if z["buildable"] else "  *"
                print(f'      {pad(z["zoneName"], 18)}满级协议容量 {pad(capn, 5, True)}{extra}{star}')
            print('      （带 * 的建造区没有基地；它们的协议容量只约束区内野外设备）')
            print('      加 --详细 展开逐级矩阵。')

    print("\n【面积数据来源】")
    for s in B["sources"]:
        print(f'    [{s["id"]}] {s["title"]}　{s["site"]} · {s["author"]} · {s["date"]}')
        print(f'         {s["claim"]}')
        print(f'         {s["url"]}')

    print("\n【数据边界】")
    for b in B["boundaries"]:
        txt = b.replace("<strong>", "").replace("</strong>", "")
        print(f'    · {txt}')
    print()


def _show_ev(ev, indent="      "):
    if not ev:
        return
    print(f"{indent}证据:")
    for e in ev:
        src = e.get("table") or f'文案 {e.get("id")}'
        txt = e.get("text") or (
            f'{e.get("field")} = {e.get("value", "")}' if e.get("field") else "")
        print(f'{indent}  · [{src}] {txt}')


# (键, 标题, 行渲染函数) —— 规则里的各类"名单"表格
_RULE_TABLES = (
    ("purePipelines", "纯管道设备（无传送带接口）", lambda x: f'{x["building"]}  {x["ports"]}'),
    ("mixedBuildings", "混合设备（流体侧仍必须走管）", lambda x: f'{x["building"]}  {x["ports"]}'),
    ("notWireless", "不走无线传输的设备", lambda x: f'{x["building"]}  {x["why"]}'),
)

# (键, 前置标签) —— 规则里的单句补充说明
_RULE_NOTES = (
    ("requirement", "前提"),
    ("sameForPump", ""),
    ("caveat", "⚠ 注意"),
    ("keyCorollary", "关键推论"),
    ("corollary", "推论"),
)


def cmd_rules(a):
    rules = J("rules.json")["rules"]
    kw = a.关键词.strip().lower()
    if kw:
        rules = [r for r in rules
                 if kw in r["title"].lower()
                 or kw in str(r.get("detail") or "").lower()
                 or kw in str(r.get("verdict") or "").lower()
                 or kw in r["id"].lower()]
        if not rules:
            print(f'没有匹配「{a.关键词}」的规则。')
            return

    for r in rules:
        hr("=")
        print(r["title"])
        hr("=")
        for key, label in (("verdict", "结论"), ("detail", None), ("why", None)):
            v = r.get(key)
            if v:
                print(f'  {label + ": " if label else ""}{v}')
                print()
        for key, tag in _RULE_NOTES:
            v = r.get(key)
            if v:
                print(f'  {tag + ": " if tag else "  "}{v}')
                print()
        for p in (r.get("paths") or []):
            print(f'  ▸ 通路：{p["source"]}')
            print(f'      {p["mechanism"]}')
            if p.get("modes"):
                print(f'      模式: {p["modes"]}')
            if p.get("requirement"):
                print(f'      前提: {p["requirement"]}')
            if p.get("config"):
                c = p["config"]
                print(f'      配置 [{c.get("table")}]: '
                      + ", ".join(f"{k}={v}" for k, v in (c.get("fields") or {}).items()))
            _show_ev(p.get("evidence"))
            print()
        for key, title, fmt in _RULE_TABLES:
            rows = r.get(key)
            if rows:
                print(f'  【{title}】')
                for x in rows:
                    print(f'      {fmt(x)}')
                print()
        if r.get("crossRegionTool"):
            t = r["crossRegionTool"]
            print(f'  【跨区域工具：{t["name"]}】最大配对长度 {t["maxLength"]} 米')
            print(f'      {t["why"]}')
            _show_ev(t.get("evidence"))
            print()
        if r.get("regionLimit"):
            print(f'  【附加限制】{r["regionLimit"]["title"]}')
            _show_ev(r["regionLimit"]["evidence"])
            print()
        _show_ev(r.get("evidence"))
        _show_ev(r.get("corollaryEvidence"))
        print()


def cmd_stats(a):
    m = J("meta.json")
    hr("=")
    print("终末地基建知识库")
    hr("=")
    print(f'  游戏版本: {m["gameVersion"]}  (hotfix {m["hotfix"]})')
    print(f'  数据版本: {m["dataVersion"]}')
    print(f'  构建时间: {m["builtAt"]}')
    print(f'  数据来源: {m["source"]}')
    print()
    print("  收录内容:")
    labels = {
        "buildings": "建筑", "machineRecipes": "机器配方", "manualRecipes": "手工配方",
        "buildRecipes": "建造配方", "items": "关联物品", "growCabin": "培养舱配方",
        "manufacture": "制造配方", "mechanicsEntries": "机制数值条目",
        "blueprintEntries": "占地蓝图条目", "footprintGroups": "占格规格种类",
        "portEntries": "物流接口总数",
        "logisticsEntities": "物流实体", "logisticsConstants": "物流常量条目",
        "rules": "玩法规则",
        "bases": "建造区", "baseAreas": "基地面积条目", "domainLevels": "据点最高发展等级",
    }
    for k, v in m["counts"].items():
        print(f'    {labels.get(k, k):<12} {v}')
    print()
    print(f'  ⚠ {m["caveat"]}')
    print()
    print(f'  {m["licenseNote"]}')
    print()


# 子命令表：名字 -> (处理函数, help, 额外参数)
# 额外参数 = (选项字符串, {add_argument 关键字})
COMMANDS = [
    ("建筑", cmd_building, "查询建筑/设施", None),
    ("蓝图", cmd_blueprint, "查占地格数与接口布局（搭蓝图用）",
     [("--接口", {"action": "store_true", "help": "只列有物流接口的建筑"}),
      ("--无接口", {"action": "store_true", "help": "只列无接口的建筑"}),
      ("--规格", {"action": "store_true", "help": "按占格规格分组列出"})]),
    ("物流", cmd_logistics, "物流规则：传送带/管道吞吐、连接常量、蓝图码规则",
     [("--常量", {"action": "store_true", "help": "只列全局物流常量"}),
      ("--蓝图码", {"action": "store_true", "help": "只列蓝图系统规则"})]),
    ("规则", cmd_rules, "玩法机制规则：开采/无线传输/管道/区域限制（附原文证据）", None),
    ("基地", cmd_base, "基地面积、扩建价目、据点发展等级建造上限（--详细 展开逐级矩阵）", None),
    ("物品", cmd_item, "查询物品及配方关联", None),
    ("配方", cmd_recipe, "查询机器生产配方", None),
    ("建造", cmd_build, "查询建造配方（材料需求）", None),
    ("手工", cmd_manual, "查询手工制作配方", None),
    ("数值", cmd_mechanics, "列出带机制数值的设施", None),
    ("地区", cmd_region, "地区概览", None),
    ("树", cmd_tree, "追溯物品上下游链", None),
    ("统计", cmd_stats, "数据包概览", None),
]


def main():
    p = argparse.ArgumentParser(description="终末地基建知识库查询工具")
    sub = p.add_subparsers(dest="cmd")

    for name, fn, help_text, extra in COMMANDS:
        s = sub.add_parser(name, help=help_text)
        s.add_argument("关键词", nargs="?", default="", help="搜索关键词（名称或 ID）")
        s.add_argument("--地区", default="", help="按地区筛选，如 武陵 / 四号谷地")
        s.add_argument("--分类", default="", help="按分类筛选，如 电力设施 / 防御设施")
        s.add_argument("--设备", default="", help="按设备名筛选")
        s.add_argument("--限制", type=int, default=30, help="最多显示条数")
        s.add_argument("--全部", action="store_true", help="显示全部结果")
        s.add_argument("--详细", action="store_true", help="显示详情")
        for flag, kw in (extra or []):
            s.add_argument(flag, **kw)
        s.set_defaults(func=fn)

    a = p.parse_args()
    if not a.cmd:
        p.print_help()
        print("\n提示：先用 `python ake.py 统计` 看数据包内容。")
        print("      搭蓝图用 `python ake.py 蓝图 --规格` 或 `python ake.py 蓝图 精炼炉`。")
        print("      看基地能建多大用 `python ake.py 基地`。")
        print("      查物流规则用 `python ake.py 物流`；查玩法机制用 `python ake.py 规则`。")
        return
    a.func(a)


if __name__ == "__main__":
    main()
