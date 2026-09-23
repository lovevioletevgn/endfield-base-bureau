# -*- coding: utf-8 -*-
"""
终末地基建知识库 —— 数据构建脚本 v4
从 AKEDatabase 数据域导出的原始 TableCfg 中提取基建相关内容：
  - 解析文本 ID 指向的中文文本
  - 打地区标签（placeDomains / domainId）
  - 构建配方上下游链路
  - 从建筑描述中提取机制数值（射程、间距、供电范围等）
  - 蓝图数据：占地格数（宽×深×高）、面积、外围轮廓、进/出料口坐标与所在边

v3 新增（蓝图支持）：
  range.width/depth/height 是占格整数 —— 蓝图摆放依据
  modelHeight 是模型实际高度（小数）—— 纯视觉，蓝图不用
  inputPorts/outputPorts 内含每个接口的精确坐标（格）、朝向、是否管道
v4 新增（物流规则）：
  传送带/管道/分流汇流/连接器/阀门 + 全局物流常量 -> logistics.json
  （见 build_logistics.py，注意它们不在 FactoryBuildingTable 里）
输出结构化 JSON 数据包。
"""
import json
import os
import re
import sys
import io
import datetime
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_logistics import build_logistics
from build_rules import build_rules
from build_bases import build_bases

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "raw")
DATA = os.path.join(ROOT, "data")

GAME_VERSION = "1.5.3"
HOTFIX = "10024360-6"
DATA_VERSION = "1.5.3@10024360-6"
SOURCE = "AKEDatabase (https://github.com/NagiYume/AKEDatabase)"
DATA_DOMAIN = "data.akedata.wiki"

# placeDomains / domainId -> 中文地区名
DOMAIN_NAMES = {
    "domain_1": "四号谷地",
    "domain_2": "武陵",
    "domain_3": "塔卫二",
}
# 建造配方的科技树分组 -> 地区
TECHTREE_NAMES = {
    "factech_recipe_tundra": "四号谷地",
    "factech_recipe_jinlong": "武陵",
}
# ⭐v131 分类名对齐游戏官方分组（raw/FactoryQuickBarTypeTable.json，2026-09-24 拉）。
#   旧名（资源采集/基础加工/组件加工/物流辅助/电力设施/仓储物流/防御设施）是 2026-09-21 自造的翻译，
#   游戏内「工业设备」面板的分组与它对不上（博士 2026-09-24 截图指出：仓库存取线基段和源桩应同组）。
#   官方 9 组带 priority 排序：快捷建造100 / 物流99 / 资源开采98 / 仓储存取97 / 基础生产96 /
#   合成制造95 / 电力94 / 功能设备93 / 战斗辅助92（快捷建造是玩家自定义栏，不进产物）。
# ⭐v132 起分组名/组序**动态读 raw 表**（AKEDatabase 更新 → fetch_raw.py → 下面的 load_quickbar()
#   自动跟上）；这份字面量降级为「raw 缺表时的回落快照 + 对账基准」，不再是一等数据源。
QUICKBAR_NAMES_SNAPSHOT = {
    "logistic": "物流",
    "source_machine": "资源开采",
    "basic_machine": "基础生产",
    "assemble_machine": "合成制造",
    "extra_machine": "功能设备",
    "electric_machine": "电力",
    "storage": "仓储存取",
    "battle_machine": "战斗辅助",
    "": "装饰与其他",
}
# 官方面板从上到下的组顺序（priority 降序；「快捷建造」是玩家自定义栏，不算建筑分组）
QUICKBAR_ORDER_SNAPSHOT = ["logistic", "source_machine", "storage", "basic_machine",
                           "assemble_machine", "electric_machine", "extra_machine", "battle_machine"]

TAG_IMAGE = re.compile(r'<image="[^"]*"(?:\s+[^>]*)?>')
TAG_ANY = re.compile(r"<[^>]{0,120}>")

# 原始建筑表，供 resolve_category 回查原版的 quickBarType
BUILDINGS_RAW = {}


def resolve_category(bid, raw_cat):
    """定分类。_nop_ 免电变体在 quickBarType 上是空的（配置表没填），
    直接落到「装饰与其他」会和秋千、玩偶混在一起。但它就是原版的免电版，
    分类应跟原版一致 —— 否则按「功能设备」（v131 前自造名「物流辅助」）筛选时会把免电版漏掉。
    """
    if raw_cat:
        return raw_cat
    if "_nop_" in bid:
        bb = BUILDINGS_RAW.get(bid.replace("_nop_", "_"))
        if bb and bb.get("quickBarType"):
            return bb["quickBarType"]
    return ""

# 从描述里抽取机制数值
NUM_PATTERNS = [
    ("range_m", re.compile(r"(\d+(?:\.\d+)?)\s*m\s*范围内?")),
    ("range_m2", re.compile(r"(\d+(?:\.\d+)?)\s*m\s*内")),
    ("interval_s", re.compile(r"([\d.]+)\s*秒")),
    ("atk", re.compile(r"攻击力[：:]\s*(\d+)")),
]

# 接口所在边。用"格坐标"命名而不是"东南西北"——因为无法证明 z 轴与游戏内的绝对方位对应。
# 蓝图层面真正要的是"口在这块地的哪条边、每个边上有几个口"，方向名字叫什么都无所谓。
EDGE_NAMES = {
    "z0": "z=0 边",
    "zmax": "z=D-1 边",
    "x0": "x=0 边",
    "xmax": "x=W-1 边",
}


def classify_edge(x, z, w, d):
    """判断接口落在占地格的哪条边上（角上的口会同时命中两条边）。

    只描述"在这块占地方框的哪条边"，不声称是游戏内的绝对方位。
    """
    hits = []
    if z == 0:
        hits.append("z0")
    if z == d - 1:
        hits.append("zmax")
    if x == 0:
        hits.append("x0")
    if x == w - 1:
        hits.append("xmax")
    return hits


def parse_ports(b, w, d):
    """解析输入/输出接口，返回带坐标与所在边的结构化列表。"""
    out = []
    for kind, key in (("input", "inputPorts"), ("output", "outputPorts")):
        for p in (b.get(key) or []):
            tr = p.get("trans") or {}
            pos = tr.get("position") or {}
            rot = tr.get("rotation") or {}
            x = pos.get("x", 0)
            z = pos.get("z", 0)
            edges = classify_edge(x, z, w, d)
            out.append({
                "kind": kind,
                "index": p.get("index"),
                "x": x,
                "y": pos.get("y", 0),
                "z": z,
                "facing": rot.get("y"),          # 模型朝向角度，仅供对齐参考
                "isPipe": bool(p.get("isPipe")),  # True=管道口, False=传送带口
                "medium": "管道" if p.get("isPipe") else "传送带",
                "edges": edges,
                "edgeNames": [EDGE_NAMES[e] for e in edges],
                "edgeLabel": "/".join(EDGE_NAMES[e] for e in edges) or "内部",
            })
    return out


def load(name):
    p = os.path.join(RAW, name + ".json")
    if not os.path.exists(p):
        print(f"  [warn] missing {name}")
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ⭐v132 分组名/组序动态化：数据源 = raw/FactoryQuickBarTypeTable.json（AKEDatabase 数据域，
#   fetch_raw.py 清单已登记）。游戏版本更新 → fetch_raw 拉新表 → 这里自动跟上，
#   改动会打印成「组 X 名变化」日志留痕。raw 缺表/解析失败 → 回落 v131 快照并 WARN。
#   对账：动态结果与快照不一致不算错（改名正是要采纳），但快照里的组在上游消失会加粗警告。
def load_quickbar():
    try:
        qbt = load("FactoryQuickBarTypeTable")
        itn = load("I18nTextTable_CN")
        rows = qbt if isinstance(qbt, list) else (qbt.get("DataList") or list(qbt.values()))
        pairs = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("id", ""))
            if not rid or rid == "custom":     # 「快捷建造」是玩家自定义栏，不算建筑分组
                continue
            name = r.get("name") or {}
            nid = name.get("id") if isinstance(name, dict) else name
            nm = itn.get(str(nid))
            if not nm:
                raise ValueError(f"组 {rid} 的 I18n 名缺失（text id={nid}）")
            pairs.append((rid, str(nm), int(r.get("priority", 0))))
        if len(pairs) < 5:
            raise ValueError(f"识别到的组数异常: {len(pairs)}")
        pairs.sort(key=lambda x: -x[2])        # priority 降序 = 游戏面板从上到下
        names = {rid: nm for rid, nm, _ in pairs}
        names[""] = "装饰与其他"
        order = [rid for rid, _, _ in pairs]
        return names, order, None
    except Exception as e:                     # noqa: BLE001 - 任何解析失败都回落快照
        return None, None, str(e)


QB_NAMES_DYN, QB_ORDER_DYN, QB_ERR = load_quickbar()
if QB_NAMES_DYN is not None:
    QUICKBAR_NAMES = QB_NAMES_DYN
    QUICKBAR_ORDER = QB_ORDER_DYN
    QB_MODE = "dynamic"
    for _k, _v in QUICKBAR_NAMES_SNAPSHOT.items():
        if _k and QUICKBAR_NAMES.get(_k) not in (None, _v):
            print(f"  [quickbar] 组 {_k} 名变化: {_v} → {QUICKBAR_NAMES[_k]}（跟随 AKEDatabase 更新）")
    for _k in QUICKBAR_NAMES_SNAPSHOT:
        if _k and _k not in QUICKBAR_NAMES:
            print(f"  ⚠️ [quickbar] 官方组 {_k} 在上游分组表里消失了！请人工核对")
else:
    QUICKBAR_NAMES = dict(QUICKBAR_NAMES_SNAPSHOT)
    QUICKBAR_ORDER = list(QUICKBAR_ORDER_SNAPSHOT)
    QB_MODE = "fallback"
    print(f"⚠️ [quickbar] raw 分组表不可用（{QB_ERR}）—— 分组名/组序回落 v131 快照")


def clean_text(s):
    if not s:
        return ""
    s = TAG_IMAGE.sub("", s)
    s = TAG_ANY.sub("", s)
    s = s.replace("</>", "").replace("\\n", "\n")
    return s.strip()


def extract_mechanics(desc):
    """从描述中抽取可结构化的机制数值。"""
    found = {}
    if not desc:
        return found
    m = NUM_PATTERNS[0][1].search(desc) or NUM_PATTERNS[1][1].search(desc)
    if m:
        try:
            found["rangeMeters"] = float(m.group(1))
        except ValueError:
            pass
    iv = NUM_PATTERNS[2][1].search(desc)
    if iv:
        try:
            found["intervalSeconds"] = float(iv.group(1))
        except ValueError:
            pass
    atk = NUM_PATTERNS[3][1].search(desc)
    if atk:
        found["attack"] = int(atk.group(1))
    return found


def main():
    os.makedirs(DATA, exist_ok=True)
    print("[1/7] 载入原始表 ...")
    text = load("I18nTextTable_CN")
    buildings = load("FactoryBuildingTable")
    # ⚠️ 2026-09-22（博士实机核对后揪出）：furnance_nop_1（精炼炉免电变体）原始表里
    #    powerConsume=5 却**没打 needPower 标志位**——直接 bool(needPower) 会把「缺标志」
    #    当成「免电」，蓝图页/建筑页就错显「无需通电」。全表扫描仅此一台这样
    #    （其余 5 台 nop 变体都是显式 needPower=False · powerConsume=0）。
    #    规整规则：powerConsume>0 一律按耗电处理（标志位缺失 ≠ 不耗电）。
    for _b in buildings.values():
        if isinstance(_b, dict) and (_b.get("powerConsume") or 0) > 0 and not _b.get("needPower"):
            _b["needPower"] = True
    BUILDINGS_RAW.clear()
    BUILDINGS_RAW.update(buildings)
    machine_craft = load("FactoryMachineCraftTable")
    manual_craft = load("FactoryManualCraftTable")
    craft_group = load("FactoryMachineCraftGroupTable")
    hub_craft = load("FactoryHubCraftTable")
    items = load("ItemTable")
    factory_item = load("FactoryItemTable")
    miner_raw = load("FactoryMinerTable")
    pump_raw = load("FactoryFluidPumpInTable")
    grow_formula = load("SpaceshipGrowCabinFormulaTable")
    mfg_formula = load("SpaceshipManufactureFormulaTable")
    print(f"  文本 {len(text)} / 建筑 {len(buildings)} / 机器配方 {len(machine_craft)} / "
          f"手工 {len(manual_craft)} / 物品 {len(items)}")

    def T(node):
        if not node:
            return ""
        if node.get("text"):
            return clean_text(node["text"])
        nid = node.get("id")
        return clean_text(text.get(str(nid), "")) if nid is not None else ""

    # ---------- 物品索引 ----------
    print("[2/7] 物品索引 ...")
    item_name, item_detail = {}, {}
    for iid, it in items.items():
        nm = T(it.get("name")) or iid
        item_name[iid] = nm
        # 跨地区传输用（2026-09-22）：FactoryItemTable.value = 界面上的「单位物品价值」，
        # 「每批数量上限 = 传输总值 ÷ 单位物品价值」；transferDomainIds 非空才可跨地区传。
        _fi = factory_item.get(iid) or {}
        item_detail[iid] = {
            "id": iid,
            "name": nm,
            "rarity": it.get("rarity"),
            "type": it.get("type"),
            "showingType": it.get("showingType"),
            "sortId1": it.get("sortId1"),
            "sortId2": it.get("sortId2"),
            "maxStackCount": it.get("maxStackCount"),
            "value": _fi.get("value"),
            "domains": _fi.get("transferDomainIds") or [],
            "desc": T(it.get("decoDesc")) or T(it.get("desc")),
        }

    def iname(iid):
        return item_name.get(iid, iid)

    # ---------- 物品「相态」（2026-09-21 新增）----------
    # 来源 FactoryItemTable.phaseType：全表实测只有 1 / 2 / 4 三种取值（544 / 11 / 9 条）。
    # 「固态 / 液态 / 气态」这三个词在 I18nTextTable_CN 里都出现过（固态 8 · 液态 18 · 气态 104 次），
    # 所以是官方说法，不是我自己起的名。判据：这一项决定物料走**传送带口**还是**管道口**
    # （见 recipe_groups 里各组的 solid*/fluid* 绑定，已用精炼炉/塑形机/灌装机逐条对上）。
    PHASE_NAME = {1: "固态", 2: "液态", 4: "气态"}
    phase_of = {iid: fi.get("phaseType") for iid, fi in factory_item.items()}

    def with_phase(rows):
        """给 walk_slots 出来的每条 {id,name,count} 补上相态"""
        for r in rows:
            pt = phase_of.get(r.get("id"))
            r["phaseType"] = pt
            r["phase"] = PHASE_NAME.get(pt, "")
        return rows

    # ---------- 配方组的「端口绑定」（2026-09-21 新增）----------
    # FactoryMachineCraftGroupTable 每个配方组写明：这份配方里的固态料/流体料分别可以走哪几个接口。
    # ⚠️ 它是**集合**不是一对一 —— 灌装机 7 个进料口里 0~5 都能接固态料、只有 6 号是管道口，
    #    所以能说"固态料走 0/1/2"，不能说"1 号料进 1 号口"（配方料数根本对不上口数）。
    def bind(rows):
        out = []
        for b in (rows or []):
            out.append({"ports": b.get("bindingPortIndices") or [],
                        "phases": b.get("pipePortPhaseType") or []})
        return out

    recipe_groups = {}
    for gid, g in craft_group.items():
        machines = []
        for cid in (g.get("craftList") or []):
            m = (machine_craft.get(cid) or {}).get("machineId")
            if m and m not in machines:
                machines.append(m)
        recipe_groups[gid] = {
            "id": gid,
            "msPerRound": g.get("msPerRound", 1000),
            "machines": machines,
            "recipes": list(g.get("craftList") or []),
            "solidIn": bind(g.get("ingredientBufferBinding")),
            "fluidIn": bind(g.get("pipeIngredientBufferBinding")),
            "solidOut": bind(g.get("outcomeBufferBinding")),
            "fluidOut": bind(g.get("pipeOutcomeBufferBinding")),
        }

    # ---------- 建筑 ----------
    print("[3/7] 建筑索引 ...")
    building_list, building_map = [], {}
    for bid, b in buildings.items():
        nm = T(b.get("name"))
        if not nm:
            continue
        domains = b.get("placeDomains") or []
        rng = b.get("range") or {}
        desc = T(b.get("desc"))
        cat = resolve_category(bid, b.get("quickBarType", ""))
        cat_nm = QUICKBAR_NAMES.get(cat)
        if cat_nm is None:
            if cat:
                print(f"  ⚠️ [quickbar] {bid}: quickBarType={cat} 不在官方分组表 —— 上游加新组了？"
                      f"分类名暂用原始 id，请把新组加进配色/字标特例（build_html.py）")
                cat_nm = cat
            else:
                cat_nm = "装饰与其他"
        W = rng.get("width")
        D = rng.get("depth")
        H = rng.get("height")
        ports = parse_ports(b, W or 1, D or 1)
        rec = {
            "id": bid,
            "name": nm,
            "category": cat,
            "categoryName": cat_nm,
            "needPower": bool(b.get("needPower")),
            "powerConsume": b.get("powerConsume", 0),
            "bandwidth": b.get("bandwidth", 0),
            "liquidEnabled": bool(b.get("liquidEnabled")),
            "domains": domains,
            "domainNames": [DOMAIN_NAMES.get(d, d) for d in domains],
            "isUniversal": len(domains) == 0,
            "footprint": f'{W}x{D}x{H}',
            "footprintW": W,
            "footprintD": D,
            "footprintH": H,
            # ---- 蓝图专用字段 ----
            "gridFootprint": f"{W}×{D}",           # 地面占格（蓝图核心数据）
            "gridArea": (W * D) if (W and D) else None,  # 占格面积
            "gridHeight": H,                        # 占格高度（可堆叠依据）
            "gridPerimeter": (2 * (W + D)) if (W and D) else None,  # 外圈周长（算传送带用量）
            "isSquare": (W == D) if (W and D) else None,
            "aspect": (round(max(W, D) / min(W, D), 2) if (W and D and min(W, D)) else None),
            "buildSizeClass": (
                "微型" if W and D and W * D <= 4 else
                "小型" if W and D and W * D <= 9 else
                "中型" if W and D and W * D <= 25 else
                "大型" if W and D and W * D <= 40 else
                "超大型" if W and D else None
            ),
            "ports": ports,
            "inputPorts": [p for p in ports if p["kind"] == "input"],
            "outputPorts": [p for p in ports if p["kind"] == "output"],
            "portCount": len(ports),
            "hasBeltPorts": any(not p["isPipe"] for p in ports),
            "hasPipePorts": any(p["isPipe"] for p in ports),
            # 进/出料口各自占了哪些边（含每边几个口）
            "inputEdges": sorted({e for p in ports if p["kind"] == "input" for e in p["edges"]}),
            "outputEdges": sorted({e for p in ports if p["kind"] == "output" for e in p["edges"]}),
            "inputEdgeLabel": " / ".join(sorted({p["edgeLabel"] for p in ports if p["kind"] == "input"})) or "—",
            "outputEdgeLabel": " / ".join(sorted({p["edgeLabel"] for p in ports if p["kind"] == "output"})) or "—",
            # 进出料口的边集合是否完全重叠（角上的口会让边集合天然相交，故不算冲突）
            "mixedSides": bool(
                {e for p in ports if p["kind"] == "input" for e in p["edges"]}
                == {e for p in ports if p["kind"] == "output" for e in p["edges"]}
                and {p["kind"] for p in ports} == {"input", "output"}
            ),
            "limitType": b.get("limitType"),
            "hasPlaceLimit": b.get("limitType") == 1,
            "modelHeight": b.get("modelHeight"),
            "desc": desc,
            "mechanics": extract_mechanics(desc),
            "iconId": b.get("iconOnPanel", ""),
        }
        building_list.append(rec)
        building_map[bid] = rec
    building_list.sort(key=lambda r: (r["category"] or "zzz", r["name"]))

    # ---------- 建造配方 ----------
    print("[4/7] 建造配方 ...")
    build_recipes = []
    for rid, r in hub_craft.items():
        groups = r.get("belongingGroupIds", [])
        tech_domains = [TECHTREE_NAMES.get(g, g) for g in groups]
        build_recipes.append({
            "id": rid,
            "name": building_map.get(rid, {}).get("name", rid),
            "groups": groups,
            "techDomains": tech_domains,
            "rarity": r.get("rarity"),
            "usableLevel": r.get("usableLevel"),
            "ingredients": [{"id": g.get("id"), "name": iname(g.get("id")), "count": g.get("count")}
                            for g in (r.get("ingredients") or [])],
            "outcomes": [{"id": g.get("id"), "name": iname(g.get("id")), "count": g.get("count")}
                         for g in (r.get("outcomes") or [])],
            "sortId": r.get("sortId"),
        })
    build_recipes.sort(key=lambda r: (r.get("sortId") or 0))

    # ---------- 生产配方 ----------
    print("[5/7] 生产配方 ...")
    group_ms = {gid: g.get("msPerRound", 1000) for gid, g in craft_group.items()}

    def walk_slots(slots):
        res = []
        for slot in slots or []:
            group = slot.get("group") if isinstance(slot, dict) else None
            if group:
                for c in group:
                    res.append({"id": c.get("id"), "name": iname(c.get("id")), "count": c.get("count")})
            elif isinstance(slot, dict) and slot.get("id"):
                res.append({"id": slot["id"], "name": iname(slot["id"]), "count": slot.get("count")})
        return res

    craft_list = []
    for cid, c in machine_craft.items():
        grp = c.get("formulaGroupId", "")
        ms = group_ms.get(grp, 1000)
        total = c.get("totalProgress", 0)
        seconds = round(total / 1000.0 * ms / 1000.0, 2) if total else None
        mid = c.get("machineId")
        bld = building_map.get(mid, {})
        craft_list.append({
            "id": cid,
            "machineId": mid,
            "machineName": bld.get("name", mid),
            # 跟随建筑表的分类（building_map 已含 _nop_ 继承逻辑），
            # 保证与「建筑设施」页的分类口径完全一致。
            "machineCategory": bld.get("categoryName") or "其他",
            "group": grp,
            "ingredients": with_phase(walk_slots(c.get("ingredients"))),
            "outcomes": with_phase(walk_slots(c.get("outcomes"))),
            "totalProgress": total,
            "progressRound": c.get("progressRound"),
            "msPerRound": ms,
            "seconds": seconds,
            "sortId": c.get("sortId"),
            "desc": T(c.get("formulaDesc")),
            # ⭐v133 该配方涉及的缓冲物（每条配方都有，317/317）——前端做「扩容反应池同池并行」的
            #   占格依据：同池并行配方的 buffers 物品并集 ≤ 缓存格数（8）。
            "buffers": [{"id": k, "name": iname(k)} for k in (c.get("buffers") or {})],
        })
    craft_list.sort(key=lambda r: (r.get("sortId") or 0, r["id"]))

    # ---------- 手工配方 ----------
    manual_list = []
    for mid, m in manual_craft.items():
        dom = m.get("domainId", "")
        manual_list.append({
            "id": mid,
            "name": T(m.get("name")),
            "domain": dom,
            "domainName": DOMAIN_NAMES.get(dom, dom or "通用"),
            "rarity": m.get("rarity"),
            "showingType": m.get("showingType"),
            "ingredients": [{"id": g.get("id"), "name": iname(g.get("id")), "count": g.get("count")}
                            for g in (m.get("ingredients") or [])],
            "outcomes": [{"id": g.get("id"), "name": iname(g.get("id")), "count": g.get("count")}
                         for g in (m.get("outcomes") or [])],
            "defaultUnlock": m.get("defaultUnlock"),
            "sortId": m.get("sortId"),
        })
    manual_list.sort(key=lambda r: (r["domainName"], r.get("sortId") or 0))

    # ---------- 培养舱 / 制造 ----------
    grow_cabin = sorted([{
        "id": gid,
        "level": g.get("level"),
        "seedItem": {"id": g.get("seedItemId"), "name": iname(g.get("seedItemId")), "count": g.get("seedItemCount")},
        "outcomeItem": {"id": g.get("outcomeItemId"), "name": iname(g.get("outcomeItemId")), "count": g.get("outcomeItemCount")},
        "rarity": g.get("rarity"),
        "totalProgress": g.get("totalProgress"),
        "sortId": g.get("sortId"),
    } for gid, g in grow_formula.items()], key=lambda r: r.get("sortId") or 0)

    manufacture = sorted([{
        "id": mid,
        "level": m.get("level"),
        "outcomeItem": {"id": m.get("outcomeItemId"), "name": iname(m.get("outcomeItemId")), "count": m.get("perCapacity")},
        "rarity": m.get("rarity"),
        "totalProgress": m.get("totalProgress"),
        "sortId": m.get("sortId"),
    } for mid, m in mfg_formula.items()], key=lambda r: r.get("sortId") or 0)

    # ---------- 交叉索引 ----------
    print("[6/7] 交叉索引 ...")
    produced_by, consumed_by = {}, {}
    for c in craft_list:
        for o in c["outcomes"]:
            produced_by.setdefault(o["id"], []).append({
                "recipeId": c["id"], "machine": c["machineName"], "kind": "machine",
                "count": o["count"], "seconds": c["seconds"],
            })
        for i in c["ingredients"]:
            consumed_by.setdefault(i["id"], []).append({
                "recipeId": c["id"], "machine": c["machineName"], "kind": "machine", "count": i["count"],
            })
    for m in manual_list:
        for o in m["outcomes"]:
            produced_by.setdefault(o["id"], []).append({
                "recipeId": m["id"], "machine": "手工制作", "kind": "manual",
                "count": o["count"], "domain": m["domainName"],
            })
        for i in m["ingredients"]:
            consumed_by.setdefault(i["id"], []).append({
                "recipeId": m["id"], "machine": "手工制作", "kind": "manual", "count": i["count"],
            })
    for b in build_recipes:
        for o in b["outcomes"]:
            produced_by.setdefault(o["id"], []).append({
                "recipeId": b["id"], "machine": "建造配方", "kind": "build", "count": o["count"],
                "techDomains": b["techDomains"],
            })

    # 建筑物品（item_port_*）与建筑实体的关联
    for b in building_list:
        key = f"item_port_{b['id']}"
        if key in item_detail:
            b["itemId"] = key
            b["itemName"] = item_detail[key]["name"]

    used = set(produced_by) | set(consumed_by)
    for c in craft_list:
        if c.get("machineId"):
            used.add(c["machineId"])
    for b in building_list:
        if b.get("itemId"):
            used.add(b["itemId"])
    item_index = {}
    for iid in used:
        d = item_detail.get(iid)
        if not d:
            continue
        item_index[iid] = {
            "id": iid, "name": d["name"], "rarity": d["rarity"], "type": d["type"],
            "value": d.get("value"), "domains": d.get("domains") or [],
            "desc": d["desc"],
            "producedBy": produced_by.get(iid, []),
            "consumedBy": consumed_by.get(iid, []),
        }

    # ---------- 地区视图 ----------
    print("[7/7] 地区视图与统计 ...")
    region_view = {}
    for b in building_list:
        tags = b["domainNames"] or ["全地区通用"]
        for t in tags:
            region_view.setdefault(t, {"buildings": [], "count": 0, "powered": 0, "manualRecipes": 0})
            region_view[t]["buildings"].append(b["id"])
            region_view[t]["count"] += 1
            if b["needPower"]:
                region_view[t]["powered"] += 1
    for m in manual_list:
        r = region_view.setdefault(m["domainName"], {"buildings": [], "count": 0, "powered": 0, "manualRecipes": 0})
        r["manualRecipes"] += 1
    for rec in build_recipes:
        for t in rec["techDomains"]:
            r = region_view.setdefault(t, {"buildings": [], "count": 0, "powered": 0, "manualRecipes": 0})
            r["buildRecipes"] = r.get("buildRecipes", 0) + 1

    # 机制数值汇总：把描述里带米数的设施单独抽出来
    mechanics_index = []
    for b in building_list:
        if b["mechanics"]:
            mechanics_index.append({
                "id": b["id"], "name": b["name"], "categoryName": b["categoryName"],
                "mechanics": b["mechanics"], "desc": b["desc"],
                "domainNames": b["domainNames"] or ["全地区通用"],
            })
    mechanics_index.sort(key=lambda r: -r["mechanics"].get("rangeMeters", 0))

    # ---------- 蓝图视图 ----------
    # 目标：给出"这块地能不能放下"和"线怎么接"这两个问题的直接答案
    bp_buildings = []
    for b in building_list:
        if not (b.get("gridFootprint") and b["gridFootprint"] != "None×None"):
            continue
        # ⚠️ 2026-09-22（博士拍板，v93）：剔除储液罐免电版——它与普通储液罐在蓝图页
        #    卡面一字不差（普通版本就不耗电，「免电」显不出来；蓝图表又没导出液体容量/
        #    协议容量），玩家也造不出免电版（无建造配方），这张卡纯属撞卡混淆。
        #    其余 5 台 _nop_ 变体靠供电行可与原版区分，保留。
        #    注意：用 ID 精确点名，不做「卡面撞卡就剔 nop 版」的通用规则，
        #    避免将来新数据撞卡时被静默剔除。
        if b["id"] == "liquid_storager_nop_1":
            continue
        bp_buildings.append({
            "id": b["id"],
            "name": b["name"],
            "categoryName": b["categoryName"],
            "gridFootprint": b["gridFootprint"],
            "gridArea": b["gridArea"],
            "gridHeight": b["gridHeight"],
            "gridPerimeter": b["gridPerimeter"],
            "isSquare": b["isSquare"],
            "aspect": b["aspect"],
            "buildSizeClass": b["buildSizeClass"],
            "needPower": b["needPower"],
            "powerConsume": b["powerConsume"],
            "limitType": b["limitType"],
            "hasPlaceLimit": b["hasPlaceLimit"],
            "liquidEnabled": b["liquidEnabled"],
            "modelHeight": b["modelHeight"],
            "domainNames": b["domainNames"] or ["全地区通用"],
            "portCount": b["portCount"],
            "ports": b["ports"],
            "inputEdgeLabel": b["inputEdgeLabel"],
            "outputEdgeLabel": b["outputEdgeLabel"],
            "inputEdges": b["inputEdges"],
            "outputEdges": b["outputEdges"],
            "mixedSides": b["mixedSides"],
            "hasBeltPorts": b["hasBeltPorts"],
            "hasPipePorts": b["hasPipePorts"],
            "portSummary": (
                f'进{len(b["inputPorts"])}/出{len(b["outputPorts"])}'
                if b["portCount"] else "无接口"
            ),
            # 蓝图排布要点：一句能直接抄的结论
            "layoutNote": (
                "无接口 —— 纯占地/装饰" if not b["portCount"] else
                "进料口：" + (b["inputEdgeLabel"] if b["inputPorts"] else "无")
                + "；出料口：" + (b["outputEdgeLabel"] if b["outputPorts"] else "无")
                + ("（管道）" if b["hasPipePorts"] and not b["hasBeltPorts"] else "")
                + ("（传送带）" if b["hasBeltPorts"] and not b["hasPipePorts"] else "")
                + ("（传送带+管道混合）" if b["hasBeltPorts"] and b["hasPipePorts"] else "")
            ),
        })
    bp_buildings.sort(key=lambda r: (-(r["gridArea"] or 0), r["name"]))

    # 占地规格分组（同尺寸设施聚类，方便共用蓝图网格）
    footprint_groups = {}
    for r in bp_buildings:
        g = footprint_groups.setdefault(r["gridFootprint"], {
            "footprint": r["gridFootprint"],
            "w": r["gridFootprint"].split("×")[0],
            "d": r["gridFootprint"].split("×")[1],
            "height": r["gridHeight"],
            "area": r["gridArea"],
            "count": 0,
            "buildings": [],
        })
        g["count"] += 1
        g["buildings"].append(r["id"])
    footprint_group_list = sorted(
        footprint_groups.values(), key=lambda g: (-g["count"], -(g["area"] or 0)))

    # 接口边分布统计：验证"进料在南、出料在北"这条经验规律
    edge_counter = {"input": {}, "output": {}}
    for r in bp_buildings:
        for p in r["ports"]:
            for e in p["edges"]:
                edge_counter[p["kind"]][e] = edge_counter[p["kind"]].get(e, 0) + 1

    blueprint = {
        "unit": {
            "footprint": "格（整数），width=占地格横向格数，depth=占地格纵向格数，height=占用格高",
            "modelHeight": "模型实际高度（小数，单位米），纯视觉，蓝图排布不要用",
            "coord": "接口坐标以建筑自身占地方框为参照：x 沿 width 方向（0 ~ W-1），z 沿 depth 方向（0 ~ D-1）",
        },
        "edgeConvention": {
            "note": (
                "边名用的是格坐标（x=0 / x=W-1 / z=0 / z=D-1），不是东南西北 —— "
                "配置表里没有证据能把 x/z 轴对应到游戏内的绝对方位，所以不声称方向。"
                "蓝图层面需要的信息（口在哪条边、每条边几个口）不受影响。"
                "角上的接口会同时计入两条边，因此各边计数之和大于接口总数。"
            ),
            "input": edge_counter["input"],
            "output": edge_counter["output"],
            "rule": (
                "经验规律：加工机普遍是「进料口在 z=D-1 边、出料口在 z=0 边」（传送带）。"
                "但这条规律并非全员适用，具体以每座建筑自己的 ports 为准。"
            ),
        },
        "summary": {
            "total": len(bp_buildings),
            "totalArea": sum(r["gridArea"] or 0 for r in bp_buildings),
            "withPorts": sum(1 for r in bp_buildings if r["portCount"]),
            "noPorts": sum(1 for r in bp_buildings if not r["portCount"]),
            "withPlaceLimit": sum(1 for r in bp_buildings if r["hasPlaceLimit"]),
            "largest": bp_buildings[0]["name"] if bp_buildings else None,
        },
        "footprintGroups": footprint_group_list,
        "buildings": bp_buildings,
    }

    # ---------- 物流规则层 ----------
    print("[7.5/7] 物流规则层 ...")
    logistics = build_logistics(load, T, item_name)
    print(f"  物流实体 {len(logistics['entities'])} / 常量 {len(logistics['constants'])} / "
          f"总线 {len(logistics['buses'])} / 采矿 {len(logistics['miners'])}")
    for e in logistics["entities"]:
        e["categoryName"] = "物流"  # 官方分组（FactoryQuickBarTypeTable.logistic），v131 补
        print(f"    {e['id']:<24} {e['name']:<10} {e['type']:<16} {e['unitsPerMinute']}/min")

    # ---------- 玩法机制规则层 ----------
    print("[7.8/7] 玩法机制规则层 ...")
    rules = build_rules()
    print(f"  规则 {rules['meta']['ruleCount']} 条")
    for r in rules["rules"]:
        print(f"    {r['id']:<32} {r['title'][:40]}")

    # ---------- 基地 / 据点层 ----------
    print("[7.9/7] 基地与据点层 ...")
    bases = build_bases(load, T)

    # ★ 等级上限（LevelGradeTable）—— 2026-09-21 深夜补（博士问「协议容量的版本等级限制」）
    #   ⚠️ 基地层有**两套**等级表，覆盖范围不同，别混着引用：
    #     · DomainDataTable（据点发展等级表）→ 库里的 domainLevels / maxBases 用它；
    #     · LevelGradeTable（建造区等级表）→ 下面这张，**逐档**给协议容量 / 防御建筑上限 / 滑索上限。
    #   LevelGradeTable 只有 **8 个真实建造区**（四号谷地 6 + 景玉谷 / 武陵城）；
    #   武陵其余 7 个区（首墩 / 应龙关 / 清波寨 / 试验园区 / 藏剑谷 / 北部禁区 / 雪松林）**不在这张表里**。
    #   查清这一点本身就是这次核查的结论 —— 那些区的上限只能走据点发展等级表。
    _lgt = load("LevelGradeTable") or {}
    # ⚠️ 必须按 bases["zones"] 过滤，不能只 startswith("map") ——
    #    表里还有 map10000_test1 / map10000_test2 这类**测试场景**，一并收进来会污染统计。
    _zname = {}
    for _z in bases.get("zones", []):
        _zname[_z.get("levelId")] = {"zoneName": _z.get("zoneName"), "domainName": _z.get("domainName"),
                                     "hasBuiltArea": _z.get("hasBuiltArea")}
    _zone_grades, _skipped = {}, []
    for _k, _v in _lgt.items():
        if _k not in _zname:
            _skipped.append(_k)
            continue
        _gs = _v.get("grades") or []
        if not _gs:
            continue
        _zone_grades[_k] = {
            "levelId": _k,
            "maxGrade": max((g.get("grade") or 0) for g in _gs),
            "tiers": [{"grade": g.get("grade"), "bandwidth": g.get("bandwidth"),
                       "battleBuildingLimit": g.get("battleBuildingLimit"),
                       "travelPoleLimit": g.get("travelPoleLimit"),
                       "monsterBaseLevel": g.get("monsterBaseLevel"),
                       "prosperity": g.get("prosperity")} for g in _gs],
        }
    for _k, _v in _zone_grades.items():
        _v.update(_zname.get(_k, {}))
    bases["zoneGrades"] = _zone_grades
    bases["zoneGradesSkipped"] = sorted(_skipped)
    bases["zoneGradesNote"] = ("LevelGradeTable（配置表）—— **逐档**给协议容量 / 防御建筑上限 / 滑索上限。"
                               "只覆盖 8 个建造区（四号谷地 6 + 景玉谷 / 武陵城）；武陵其余 7 个区不在这张表里，"
                               "那些区的上限要走 DomainDataTable（据点发展等级）。两套表都来自配置表，但**覆盖范围不同** —— 引用时分清是哪一套。")
    bases["schemaVersion"] = 2
    bases["dataVersion"] = GAME_VERSION
    print("  等级上限（LevelGradeTable）：" + str(len(_zone_grades)) + " 个建造区可用，跳过非建造区 "
          + str(len(_skipped)) + " 条")
    print(f"  建造区 {bases['summary']['activeZones']} / 可扩建 {bases['summary']['expandableZones']} / "
          f"据点 {bases['summary']['domains']} / 面积条目 {bases['summary']['areaEntries']}")
    for z in bases["expandableZones"]:
        print(f"    {z['levelId']:<14} {z['domainName']}·{z['zoneName']:<8} "
              f"扩建 {len(z['expansion'])} 档 / 存取线 {z['busCount']} 档")

    # ---------- 写出 ----------
    def dump(fn, obj):
        p = os.path.join(DATA, fn)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  -> {fn:<26} {round(os.path.getsize(p)/1024, 1)} KB")

    meta = {
        "gameVersion": GAME_VERSION,
        "hotfix": HOTFIX,
        "dataVersion": DATA_VERSION,
        "source": SOURCE,
        "dataDomain": DATA_DOMAIN,
        "builtAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "licenseNote": "游戏数据版权归鹰角网络及相关权利方所有。本项目仅供学习、交流与研究使用。",
        "caveat": "本知识库只收录游戏配置表（TableCfg）中的静态数据。矿脉产率、建设值收益等运行时数值不在配置表内，需游戏内实测。",
        "blueprintNote": "占地格数取 range.width/depth/height（整数格），可直接用于蓝图排布；modelHeight 是模型实际高度（小数/米），仅供视觉参考。接口坐标以建筑自身占地格为参照。",
        "counts": {
            "buildings": len(building_list),
            "machineRecipes": len(craft_list),
            "manualRecipes": len(manual_list),
            "buildRecipes": len(build_recipes),
            "items": len(item_index),
            "growCabin": len(grow_cabin),
            "manufacture": len(manufacture),
            "mechanicsEntries": len(mechanics_index),
            "blueprintEntries": len(bp_buildings),
            "footprintGroups": len(footprint_group_list),
            "portEntries": sum(r["portCount"] for r in bp_buildings),
            "logisticsEntities": len(logistics["entities"]),
            "logisticsConstants": len(logistics["constants"]),
            "undergroundPipes": len(logistics["undergroundPipes"]),
            "rules": rules["meta"]["ruleCount"],
            "bases": bases["summary"]["maxBaseRows"],
            "baseAreas": bases["summary"]["areaEntries"],
            "domainLevels": bases["summary"]["maxDevLevel"],
        },
    }
    # ---------- 配方组自检 + 组装（2026-09-21）----------
    # 口径：组声明的是一份**能力上限**（组内所有配方并集 + 可能预留），不保证每个配方都用得上。
    # 所以只强制「配方需要的 ⊆ 组声明的」；反过来（组多声明）记为 anomaly，不当错误、也不静默丢弃。
    need = {}
    for c in craft_list:
        gid = c.get("group")
        if not gid:
            continue
        d = need.setdefault(gid, {"solidIn": False, "fluidIn": [], "solidOut": False, "fluidOut": []})
        for x in c.get("ingredients") or []:
            if x.get("phase") == "固态":
                d["solidIn"] = True
            else:
                d["fluidIn"].append(x.get("phaseType"))
        for x in c.get("outcomes") or []:
            if x.get("phase") == "固态":
                d["solidOut"] = True
            else:
                d["fluidOut"].append(x.get("phaseType"))

    anomalies, underdeclared = [], []
    for gid, g in recipe_groups.items():
        d = need.get(gid)
        if not d:
            continue
        for side, nsolid, nfluid, sbind, fbind in (
                ("进料", d["solidIn"], d["fluidIn"], g["solidIn"], g["fluidIn"]),
                ("出料", d["solidOut"], d["fluidOut"], g["solidOut"], g["fluidOut"])):
            if nsolid and not sbind:
                underdeclared.append(gid + " " + side + "：有固态料但没声明传送带口")
            if nfluid:
                allowed = [p for b in fbind for p in (b.get("phases") or [])]
                miss = sorted({t for t in nfluid if t not in allowed})
                if not fbind or miss:
                    underdeclared.append(gid + " " + side + "：流体料相态 " + str(miss) + " 未在声明里")
        for mid in g["machines"]:
            bb = building_map.get(mid, {})
            pl = bb.get("ports") or []
            nin = len([p for p in pl if p.get("kind") == "input"])
            nout = len(pl) - nin
            for side, bindings, n in (("进料", g["solidIn"] + g["fluidIn"], nin),
                                      ("出料", g["solidOut"] + g["fluidOut"], nout)):
                for b in bindings:
                    for i in b.get("ports") or []:
                        if not (0 <= i < n):
                            anomalies.append({
                                "group": gid, "machineId": mid, "machineName": bb.get("name", mid),
                                "side": side, "portIndex": i, "actualPorts": n,
                                "reason": "组声明了这个" + side + "口（序号 " + str(i) + "），但该机器同类接口只有 "
                                          + str(n) + " 个（下标 0~" + str(n - 1) + "），而且组内配方也没用到它 —— "
                                          "属配置表里多声明的能力，机器上不存在该接口。",
                            })
    if underdeclared:
        print("  ⚠️ 配方组漏声明（真错误）: " + " | ".join(underdeclared))
    else:
        print("  ✅ 配方组覆盖自检：配方需要的固态 / 流体口，组里全都声明了（0 漏声明）")
    if anomalies:
        print("  ℹ️ 配方组多声明 " + str(len(anomalies)) + " 处（非错误，已记入 recipe_groups.json 的 anomalies）")

    recipe_group_data = {
        "madeFrom": "FactoryMachineCraftGroupTable（28 组）+ FactoryItemTable（相态）",
        "phaseNames": {"1": "固态", "2": "液态", "4": "气态"},
        "phaseSource": "FactoryItemTable.phaseType —— 全表实测只有 1/2/4 三种取值（544/11/9 条）；"
                       "「固态 / 液态 / 气态」这三个词在 I18nTextTable_CN 里都有，属官方说法。",
        "phaseRule": "相态决定走哪种口：固态 → 传送带口（solidIn / solidOut）；液态 · 气态 → 管道口（fluidIn / fluidOut）。"
                     "已用全部 317 条配方回代，需要的口 0 例漏声明。",
        "bindingNote": "solidIn / solidOut = 该组的**固态**料可走的接口序号；fluidIn / fluidOut = **流体**（液态 / 气态）"
                       "料可走的接口序号，phases 是允许的相态码。序号是**同类接口内的下标**（进料口一套、出料口一套，从 0 起），"
                       "与 blueprint.json 里 ports[].index 同一口径 —— 已用精炼炉（4 进 4 出：0/1/2 传送带 + 3 管道）、"
                       "灌装机（7 进：0~5 传送带 + 6 管道）、塑形机（气态走 3 号管道口）、天有洪炉（6 进：0~4 传送带 + 5 管道）逐条对上。",
        "notOneToOne": "⚠️ 这是**可选集合**，不是一对一映射：能说「固态料走 0/1/2」，"
                       "不能说「1 号料进 1 号口」—— 配方料数与接口数根本对不上（灌装机 7 口 / 最多 2 料）。",
        "isUpperBound": "⚠️ 组声明的是**能力上限**（组内配方并集，可能含预留），不保证每个配方都用得上 ——"
                        "别拿它当「这份配方一定占几个口」。强制方向只有一条：配方需要的 ⊆ 组声明的。",
        "anomalies": anomalies,
        "groups": recipe_groups,
    }

    dump("meta.json", meta)
    dump("buildings.json", building_list)
    dump("build_recipes.json", build_recipes)
    dump("machine_recipes.json", craft_list)
    dump("recipe_groups.json", recipe_group_data)

    # ---------- 电力 + 野外开采（2026-09-21 新增）----------
    # ⚠️ 能取证的只有两样：① 每座建筑的**用电** powerConsume（配置表字段）
    #    ② 采集设施的**基础速率**（FactoryMinerTable.msPerRound / FactoryFluidPumpInTable.msPerRound）
    # ⚠️ 取不到、也不编的：**每台热能池发多少电**（建筑表里根本没有发电量字段，
    #    教学文案只定性说「利用源矿或电池提供电能」「电池发电效率高于源矿」）、
    #    **矿脉纯度加成**（运行时数值）。这两条在页面上要标清是"配置表给不了"，别让博士以为漏了。
    # ⚠️ 2026-09-21 修正：**不能只从 FactoryMinerTable 取矿机**！那张表只有 miner_1/2/3，
    #    把 **miner_4 水驱矿机**（采赤铜矿）、gas_pump_1 气体收集泵、pump_2 二型耐酸水泵 全漏了。
    #    博士当场指出「不是还有赤铜矿吗，可以用水驱矿机开采」——他说得对。
    #    正确做法：**遍历建筑表里 quickBarType=资源开采（官方组 source_machine）的全部建筑**，再去矿机表/泵表取速率（取不到就写清没有）。
    miners=[]; pumps=[]; gather=[]
    def rate(ms):
        return round(60000.0/ms, 2) if ms else None
    miner_tab={k:v for k,v in miner_raw.items() if isinstance(v,dict)}
    pump_tab={k:v for k,v in pump_raw.items() if isinstance(v,dict)}
    # ⚠️ 这三台**配置表里没有速率字段**（不在矿机表/泵表里）—— 2026-09-21 联网查到社区数值，标 `rateSource:'社区实测'`。
    #    引用时要说清不是配置表数据。可采集物同理：配置表只有 desc 里的"多达"描述，
    #    具体物品来自 desc + 社区资料（见 WEB_GATHER）。
    WEB_RATE = {
        "miner_4":   {"perMin": 20, "source": "社区实测（与其它矿机一致；且与「1 台水泵 60/分供 3 台、每台耗水 20/分」吻合）"},
        "gas_pump_1":{"perMin": 20, "source": "社区实测（NGA：气体 3 秒 1 个 → 20/分；6 台正好喂满 1 条 120/分 的管道）"},
        "pump_2":    {"perMin": 60, "source": "社区实测（NGA：水泵与耐酸水泵产速都是 60/分）"},
    }
    WEB_GATHER = {
        "miner_4":   [("item_copper_ore", "赤铜矿")],
        "gas_pump_1":[("item_gas_inert", "惰气"), ("item_gas_xiranite", "息壤气")],
        "pump_2":    [("item_liquid_acid", "沉积酸")],
    }
    # 「无线传输」一句话说明（配置表依据：FactoryMinerTable.hasDroneMode / msTransferCD；文案见 I18n 教学条目）
    # ⚠️ 矿机**全都**不靠出料口接带子（博士 2026-09-22 两次指出，第二次纠的就是水驱矿机）：
    #   野外矿点采**固体矿**，而野外铺不了传送带 → 产物只能「自动回仓」或「人工取」。
    #   三种矿机：电驱/二型电驱（无线，配置表 hasDroneMode）+ 水驱（无线，博士实机确认、配置表无该字段）
    #   + 便携源石矿机（不无线，进缓存区、手动取）。
    #   那 3 个传送带出料口是**模型上的口**，默认不用接 —— 页面按无线/缓存两类分开画。
    WIRELESS_NOTE = {
        "miner_1": "⚠️ 这台**不进无线**：`hasDroneMode=false`、`msTransferCD=0`，教学文案写「源矿会存放在**缓存区**……请**手动收取**」。"
                   "所以那 3 个出料口同样用不上 —— 产物进缓存区，人过去取。",
        "miner_2": "⚡ **默认「无线传输模式」**（配置表 `hasDroneMode=true`，每 **10 秒**回传一次）：挖到的矿直接进基地仓库，**图上那 3 个传送带出料口平时不用接**；把模式切成「仓储模式」时才需要从这里取货。",
        "miner_3": "⚡ **默认「无线传输模式」**（配置表 `hasDroneMode=true`，每 **10 秒**回传一次）：挖到的矿直接进基地仓库，**图上那 3 个传送带出料口平时不用接**；把模式切成「仓储模式」时才需要从这里取货。",
        # ⚠️ 版本口径（博士 2026-09-22 纠正 + 联网核实）：水驱矿机是 **1.1「新潮起，故渊离」（武陵工业二期）** 新增的，
        #    不是 1.5。来源：官方 1.1 版本公告（TapTap/GRYPHLINE）「开放武陵工业二期，新增赤铜矿物与水驱矿机采集玩法」。
        #    它**不在 FactoryMinerTable 里**（那张表只有 miner_1/2/3），所以没有 hasDroneMode 字段 —— 别写成"1.5 新增所以表没跟上"。
        "miner_4": "⚡ **产物同样回仓库**（2026-09-22 实机确认；配置表里 `miner_4` **不在矿机表**中，没有 `hasDroneMode` 字段）。"
                   "道理也通：它在**野外矿点**采**固体**赤铜矿，而野外铺不了传送带 —— 那 3 个出料口平时不用接。"
                   "另外它靠**管道进清水**自供能（左边那个管道进料口是真的）。",
        "pump_1": "液体**只能走管道**：这个管道出料口是真的（抽出来直接进管道，不走传送带）。",
        "pump_2": "液体**只能走管道**：这个管道出料口是真的（沉积酸强腐蚀，专走管道）。",
        "gas_pump_1": "气体**只能走管道**：这个管道出料口是真的。",
    }
    # 无线这条结论的来源分级（配置表能取到的就写配置表；取不到的是博士实机确认）
    WIRELESS_SRC = {"miner_2": "配置表", "miner_3": "配置表",
                    "miner_4": "实机确认（配置表里无该字段）", "miner_1": "配置表"}
    WEB_SOURCES = [
        "https://ngabbs.com/read.php?tid=47269226  （NGA：气矿 20/分、水泵/耐酸水泵 60/分、高密度矿每台耗水 20/分、管道上限 120/分）",
        "https://ngabbs.com/read.php?tid=46610915  （NGA：赤铜矿满采 180/分）",
        "https://www.icy-veins.com/arknights-endfield/news/best-way-to-mine-cuprium-ore-in-the-new-wuling-area-in-endfield/  （6 台水驱矿机 / 2 台水泵，每泵供 3 台）",
        "https://game8.co/games/Arknights-Endfield/archives/584823  （赤铜矿只能用**水驱矿机**采；清波寨 8 个矿点）",
        "https://www.biubiu001.com/news/212157.html  （气体采集源共两类：惰气 / 息壤气；气体收集泵无需电力或水源）",
        "https://www.biubiu001.com/news/191794.html  （沉积酸：强腐蚀液体，专为它新增二型耐酸水泵）",
    ]
    for b in building_list:
        if b.get("categoryName") != "资源开采":  # 官方组名（v131 前 self 造名「资源采集」）
            continue
        bid = b["id"]
        m = miner_tab.get(bid); p = pump_tab.get(bid)
        web = WEB_RATE.get(bid)
        pm = rate((m or p or {}).get("msPerRound"))
        src = "配置表" if pm is not None else (web["source"] if web else None)
        if pm is None and web: pm = web["perMin"]
        mi = [{"itemId": x.get("miningItemId"), "name": iname(x.get("miningItemId")),
               "produceRate": x.get("produceRate"), "from": "配置表"} for x in ((m or {}).get("mineable") or [])]
        for iid, nm in (WEB_GATHER.get(bid) or []):
            if not any(x["itemId"] == iid for x in mi):
                mi.append({"itemId": iid, "name": nm or iname(iid), "produceRate": None, "from": "社区实测"})
        row = {
            "id": bid, "name": b.get("name"), "desc": b.get("desc"),
            "needPower": b.get("needPower"), "powerConsume": b.get("powerConsume"),
            "msPerRound": (m or p or {}).get("msPerRound"),
            "perMin": pm, "rateKnown": pm is not None, "rateSource": src,
            "kind": "采矿机" if bid.startswith("miner") else ("气体收集" if bid.startswith("gas") else "抽水 / 抽液"),
            "mineable": mi,
            "inputIsPipe": any((x.get("isPipe") for x in (b.get("ports") or []) if x.get("kind") == "input")),
            # ---------- 「无线传输」字段（2026-09-22 博士问的）----------
            # 博士：「矿机为什么会有出货口啊，矿机是挖完了把矿物无线传回基地仓库」。
            # 事实：矿机在配置表里**确实挂着 3 个传送带出料口**（模型上的口，不是我们画错的），
            #   但 **电驱矿机默认走「无线传输模式」** —— FactoryMinerTable.hasDroneMode=true、msTransferCD=10 秒，
            #   挖到的东西直接回仓库，那 3 个口平时**用不上**（切「仓储模式」才从此处取货）。
            # 两台反例（没有无线字段，产物确实要从口里走）：miner_1 便携源石矿机（手动收取）、miner_4 水驱矿机。
            # 泵类抽的是液体/气体，只能进管道，与"无线传矿物"无关。
            # ⚠️ 配置表能给的只有 miner_1/2/3 的 hasDroneMode；**水驱矿机 miner_4 不在矿机表里**，
            #    按博士 2026-09-22 的实机确认补上（野外采固体矿、铺不了传送带 → 必然自动回仓）。
            #    这里把「配置表没有但实测确认」的明确写成一张白名单，别让它看起来像是配置表读出来的。
            "wireless": bool((m or {}).get("hasDroneMode")) or (bid in ("miner_4",)),
            "wirelessSource": WIRELESS_SRC.get(bid, ""),
            "msTransferCD": (m or {}).get("msTransferCD"),
            "wirelessNote": WIRELESS_NOTE.get(bid, ""),
        }
        if src == "配置表":
            row["note"] = "perMin = 60000 / msPerRound（配置表）；矿脉纯度加成本就不在配置表里"
        elif src:
            row["note"] = ("⚠️ 配置表里**没有这台的开采速率字段**，perMin 来自**社区实测**（不是配置表）：" + (web or {}).get("source", ""))
        else:
            row["note"] = "⚠️ 配置表与社区都未取到速率"
        gather.append(row)
        (miners if row["kind"] == "采矿机" else pumps).append(row)
    # 建筑用电分布（配置表字段，可直接陈述）
    pw = {}
    for b in building_list:
        pc = b.get("powerConsume")
        if pc:
            pw.setdefault(pc, []).append(b["name"])
    power = {
        "consumeFrom": "FactoryBuildingTable.powerConsume —— 每座建筑的用电功率，配置表 ✅ 可直接陈述",
        "consumeDistribution": [{"power": k, "count": len(v), "names": v[:8]} for k, v in sorted(pw.items(), reverse=True)],
        "generateNote": "热能池（power_station_1）是发电设备，「利用源矿或电池提供电能」「电池的发电效率高于源矿」。"
                        "⚠️ **配置表里没有发电量字段**（建筑表只有 needPower / powerConsume）。"
                        "下表是**社区 / 攻略站实测**（多家互相印证），**不是配置表数据**，引用时要说清。",
        # ⚠️ 社区数据，不是配置表 —— 2026-09-21 联网查到，来源见 sources
        "generation": {
            "source": "社区实测（多家攻略站一致），**非配置表**",
            "baseOutput": 200,
            "storageMax": 100000,
            "fuelPower": [
                {"item": "源矿", "power": 50, "seconds": 8},
                {"item": "低容谷地电池", "power": 220, "seconds": 40},
                {"item": "中容谷地电池", "power": 420, "seconds": 40},
                {"item": "高容谷地电池", "power": 1100, "seconds": 40},
                {"item": "低容武陵电池", "power": 1600, "seconds": 40},
                {"item": "中容武陵电池", "power": 3200, "seconds": 40},
            ],
            "howItWorks": "**不是「一台热能池固定发 X 电」**，而是**每消耗 1 份燃料产出多少「功率值」**——"
                          "所以一台热能池的发电功率 = 它烧的那种燃料的功率值（源矿 50 / 中容谷地电池 420 …），"
                          "前提是燃料供给跟得上。协议核心另有 200 基础发电。",
            "warn": "⚠️ 社区数值，未用配置表交叉验证（配置表根本没有这一项）。要当硬约束用，建议在游戏内实测核对。",
            "sources": [
                "https://game8.co/games/Arknights-Endfield/archives/575882",
                "https://endfield.gg/arknights-endfield-power-output-increase/",
                "https://gamerant.com/arknights-endfield-how-increase-power-output-max-electricity-capacity/",
                "https://dotesports.com/arknights-endfield/news/arknights-endfield-power-output",
                "https://gl.ali213.net/html/2026-1/1742509_59.html",
            ],
        },
        "storageNote": "用电功率超过发电功率时会**消耗存电**（协议核心有存电，社区实测上限 10 万）；存电耗尽设备就停转。",
        "evidence": [
            {"id": "-8840808417116672558", "text": "热能池是用于生产电能的设备，可提高当前区域的发电功率，从而支持更多设备同时工作。"
             "所需要消耗的原材料是源矿和电池。使用电池的发电效率高于源矿，可大幅提高发电效率。"},
            {"id": "-2042136389745725134", "text": "电网总发电功率值"},
            {"id": "6242649860971169145", "text": "可以看到当前用电功率已经超过了发电功率。"},
            {"id": "-6818307810595173381", "text": "耗电功率已超过发电功率，将消耗存电，请在集成工业计划中解锁基础发电，放置更多热能池发电"},
            {"id": "-8259303960799921910", "text": "协议核心存电已耗尽，请尽快建设更多热能池"},
            {"id": "403886947236175519", "text": "当前发电功率较高，推荐热能池使用电池发电，提高发电效率降低源矿消耗"},
            {"id": "-8965112660607185056", "text": "通过设备封装获得的电池，可用于发电、设备充能或与据点进行交易。"},
            {"id": "7662932051795625417", "text": "水驱矿机在通入清水后无需通电即可工作；可采集更稀有的矿藏，典型矿物为赤铜矿。"},
            {"id": "367391318879434783", "text": "请放置更多的水驱矿机在赤铜矿上，然后放置更多的水泵或使用管道分流器，供水给水驱矿机吧。"},
        ],
        "cannotGive": ["每台热能池的**发电量字段**（配置表没有；社区数值见 generation，属实测非配置表）",
                       "矿脉纯度 / 矿点品级的开采加成（运行时数值）",
                       "水驱矿机 / 气体收集泵 / 二型耐酸水泵 的开采速率（这三台不在矿机表 / 泵表里，配置表无速率字段）"],
    }
    # ---------- 矿点 / 纯度 / 电池燃料（第 1 层硬校验要用的）----------
    # ⚠️ 配置表里**没有矿点表**（GitHub 上 FactoryNodeTypeToBuildingType / FactoryBuildingTypeToNodeType 都是 0 行；
    #    MapMarkInsTable 只有 34 条篝火类标记）→ 矿点位置与数量属**关卡场景数据**，只能走社区。
    # ⚠️ **纯度**：game8 明确「低纯度 10 矿/分、高纯度 20 矿/分」，靠**地区发展等级**提升。
    #    博士 2026-09-21 定：「按当前版本地区最大值算」→ **取高纯度 20/分**，正好等于配置表算出的 20/分（msPerRound 3000），两个口径自洽。
    #
    # ⚠️⚠️ 2026-09-21 晚**二次核查**（博士问「各地图矿区真的都查干净了吗」），三处修正：
    #   ① **配置表再查一遍**：全量 561 张表里只有 `InteractiveMarkDataTable` 带矿机基座标记
    #      （`int_minerbase_originium` / `_quartz` / `_iron` 三种，**没有赤铜矿基座**），
    #      矿点实例表仍然没有 → 结论不变，位置与数量只能走社区。
    #   ② **补「按地图 / 按建造区」拆分**：以前只有全图总数，排野外段时用不上。
    #      四号谷地那一列有**硬旁证**（TapTap 地图工具实时统计 28 / 12 / 54 / 0，与社区攻略逐项吻合）；
    #      武陵那一列是「总数 − 四号谷地」反推，只有一个来源，引用时要说清。
    #   ③ **修一个真错误 —— 赤铜矿的口径**：以前写成「8 脉 × 每脉 6 点」→ 960/分。
    #      实际清波寨是**2 处集中矿点、共 8 个矿源点**（核心 6 + 偏远 2），**8 就是可放矿机的点数**，
    #      不能再乘每脉点数 → 满采 **160/分**（8 台 × 20/分），之前虚高了 6 倍。
    #      所以新增 `rigs`（可放矿机数区间），容量不再靠「脉数 × 点数」现乘 —— 两种矿的单位本来就不同。
    # ⚠️⚠️ 2026-09-21 晚**三次核查**（博士：「矿源点矿产纯度协议容量什么的版本等级限制再查一遍，
    #    留个接口给以后游戏版本更新用，矿源点每张小地图都列出来」+「赤铜矿理论最大开采值是 510/分」）：
    #   ① **博士给的 510 是对的，我上一版算的 160 是根本性错误** —— 把「清波寨一个区」当成了全图。
    #      赤铜矿实际分布在**武陵的 5 个区域**：清波寨 / 藏剑谷 / 首墩 / 北部禁区 / 试验园区。
    #      （gamewith 日站列了其中 4 个；NGA 实测贴的按区产量把第 5 个区也带出来了。）
    #   ② **1.1 的按区实测**（NGA tid=47257073，2026-07-26，楼主逐个矿点数过）：
    #        160(清波) + 80(藏剑) + 80(首墩) + 60(北部) + 40(试验) = **420/分**
    #      除以 20/分正好是 8 / 4 / 4 / 3 / 2 = **21 个矿源点**；其中 8 与 4 分别被
    #      game8（清波寨 8 个矿点）与 TapTap 地图集（藏剑谷 4 个赤铜矿点）独立证实 → 这条链闭合。
    #   ③ **1.5 全图满采 = 510/分**（游戏内「理论最大开采值」；博士确认 + NGA tid=47560240 印证）。
    #      510 − 420 = **90/分 还没定位到具体区域**（可能 1.5 新增矿点，或某些点从低纯度升到高纯度）。
    #      **不猜也不抹平**：写进 `unaccounted`，页面会明确显示「按区明细与理论值差 90」，等游戏内核对。
    #   ④ **版本接口**：新增 `schemaVersion` / `dataVersion` / `versionLog`，以及 zones[].levelId
    #      —— 以后游戏更新只改这里的数字，页面与工具不动；构建时另有自洽自检（见 ores 定义之后）。
    # ⚠️⚠️⚠️ 2026-09-21 **第四次核查 —— 这次推翻了我自己的核心算法**（博士：「你可以自己查，
    #    最好每个小地图矿点和矿点纯度都列出来搞个表写到知识库里，可以再搞个每个大地区的
    #    可采集矿产最大理论值让我核实」）：
    #
    #   ① **「每脉 2~6 个点」是错的，一个矿脉只放 1 台矿机。**
    #      证据：四号谷地全开产能 NGA 两帖（tid=46073277 / 45696282）+ 游民星空 + sticweb **四方一致**：
    #        源矿 560/分 · 紫晶 240/分 · 蓝铁 1080/分
    #      除以 20/分 = **28 / 12 / 54 个矿点**，与 TapTap 地图工具的「源矿矿脉 28 / 紫晶矿脉 12 / 蓝铁矿脉 54」
    #      **逐项相等** —— 所以「矿脉数」就是「可放矿机的点数」，一对一。
    #      之前那个「脉数 × 每脉 2~6 点」把全图算出 2320~6960/分，**虚高 2~6 倍**。
    #      （「2~6」是游戏里一个矿脉**视觉上有几个矿石簇**，不是能放几台矿机 —— 两回事。）
    #   ② **口径统一为：满采量 = 矿点数 × 20/分**（高纯度档）。所以
    #        源矿 58 点 → **1160/分** · 紫晶 12 点 → **240/分** · 蓝铁 60 点 → **1200/分** · 赤铜见下
    #   ③ **按大地区的最大理论值**（博士要核实的那张表）放在 `mapMax`：
    #        四号谷地 560 / 240 / 1080 —— **四方一致的实测值，可信**
    #        武陵 600 / 0 / 120 —— **推算值**（= 点数 × 20）；NGA 另有人实测「武陵源矿 480/分」（= 24 点），
    #                            与本表 30 点不符，**列成冲突待博士核**
    #   ④ 赤铜矿（1.1 新增）：武陵 5 区 **21 个矿源点** → 1.1 实测 **420/分**；
    #      1.5 游戏内「理论最大开采值」**510/分**，差额 90 未定位（照实登记）。
    #   ⑤ **纯度是分区分级解锁的**（不是全区一起）：四号谷地「采石场 / 研究院」前几级就满纯，
    #      **供能高地要到 11 级**；武陵 **景玉谷 8 级**满纯。本库按博士定的「地区最大值」口径 → 一律按高纯度 20/分。
    ores = {
        "schemaVersion": 3,
        "dataVersion": GAME_VERSION,
        "madeFrom": "配置表无矿点表（已核查 GitHub 全量 561 张表）→ 社区资料",
        # ★ 核心口径：一个矿点 = 1 台矿机；纯度高档 20/分、低档 10/分
        "perNodePerMin": 20,
        "purityRule": {
            "low": {"perMin": 10, "secPerUnit": 6},
            "high": {"perMin": 20, "secPerUnit": 3},
            "how": "矿机出矿速率只由**矿点纯度**决定（与矿机型号无关，型号只影响耗电）。低纯度 6 秒 1 个（10/分）、高纯度 3 秒 1 个（20/分）。",
            "zoneUpgrade": ("**纯度按「区」分级解锁**，不是整张大地图一起提：四号谷地的「阿伯莉采石场 / 源石研究园」前面几级就满纯度，"
                            "「供能高地」要到 **11 级**才满；武陵的「景玉谷」**8 级**满纯度。所以同一版本、不同玩家的矿点纯度可能不同。"),
            "adopted": "high",
            "adoptedWhy": "2026-09-21 定：按当前版本**地区最大值**算 → 用高纯度 20/分（= 配置表 msPerRound 3000 的值，两口径自洽）",
            "configCrossCheck": "配置表 FactoryMinerTable.msPerRound = 3000 → 20/分，正是高纯度档；低纯度（10/分）在配置表里没有对应字段",
        },
        "beds": [
            {"ore": "源矿", "itemId": "item_originium_ore",
             "pointsTotal": 60, "pointsVersion": "1.5",
             "theoreticalMax": {"value": 1100, "version": "1.5",
                                "how": "四号谷地 28×20=560 + 武陵 22×20+10×10=540 = 1100/分（武陵简报截图逐区计数）"},
             "pointsNote": ("官方 FAQ 说全图 58 个矿脉；实测（武陵简报截图 + 四号谷地四方实测）= 28 + 32 = **60 个点**。"
                            "武陵 32 点里有 10 个低纯度点按 10/分计，所以满采是 1100 而不是 60×20=1200。"
                            "与 FAQ 的 58 差 2，可能是口径差异（低纯度点没被 FAQ 计入）。"),
             "byMap": {"四号谷地": 28, "武陵": 32},
             "mapMax": {"四号谷地": 560, "武陵": 540},
             "mapMaxConfidence": {"四号谷地": "实测（NGA 两帖 + 游民星空 + sticweb 四方一致）",
                                  "武陵": "实测（武陵简报截图逐区计数：22 高×20 + 10 低×10 = 540，与 UI 一致）"},
             "zones": [
                 {"zone": "枢纽区", "levelId": "map01_lv001", "points": 6},
                 {"zone": "谷地通道", "levelId": "map01_lv002", "points": 2},
                 {"zone": "阿伯莉采石场", "levelId": "map01_lv003", "points": 2},
                 {"zone": "源石研究园", "levelId": "map01_lv005", "points": 5},
                 {"zone": "矿脉源区", "levelId": "map01_lv006", "points": 7},
                 {"zone": "供能高地", "levelId": "map01_lv007", "points": 6},
                 {"zone": "景玉谷", "levelId": "map02_lv001", "points": 14, "high": 7, "low": 7, "perMin": 210,
                  "note": "武陵出生点区域；7 高 + 7 低（武陵简报截图）"},
                 {"zone": "武陵城", "points": 16, "high": 13, "low": 3, "perMin": 290,
                  "note": "13 高 + 3 低（武陵简报截图）；武陵主城，供电最方便"},
                 {"zone": "试验园区", "levelId": "map02_lv005", "points": 2, "high": 2, "low": 0, "perMin": 40,
                  "note": "2 个高纯度源矿点（武陵简报截图）；该区另有 2 个赤铜矿点"},
             ],
             "zonesCover": "四号谷地+武陵", "zonesCoverAll": True,
             "zonesSum": {"points": 60, "perMin": 1100, "version": "1.5"},
             "zonesNote": "按区明细只覆盖四号谷地 6 个建造区（合计 28 点 = 560/分，与 NGA 实测的「四号谷地源矿 560/分」完全吻合）；武陵 3 区明细来自武陵简报截图（景玉谷 7高7低 / 试验园区 2高 / 武陵城 13高3低）。",
             "regions": "四号谷地（枢纽区 / 谷地通道 / 源石研究园 / 矿脉源区）· 武陵（景玉谷 / 武陵城）"},
            {"ore": "紫晶矿", "itemId": "item_quartz_sand",
             "pointsTotal": 12, "pointsVersion": "1.0",
             "theoreticalMax": {"value": 240, "version": "1.5", "how": "12 个矿点 × 20/分"},
             "byMap": {"四号谷地": 12, "武陵": 0},
             "mapMax": {"四号谷地": 240, "武陵": 0},
             "mapMaxConfidence": {"四号谷地": "实测（四方一致）", "武陵": "实测（武陵没有紫晶矿）"},
             "zones": [
                 {"zone": "枢纽区", "levelId": "map01_lv001", "points": 6},
                 {"zone": "谷地通道", "levelId": "map01_lv002", "points": 2},
                 {"zone": "阿伯莉采石场", "levelId": "map01_lv003", "points": 4},
             ],
             "zonesCover": "四号谷地", "zonesCoverAll": True,
             "zonesSum": {"points": 12, "perMin": 240, "version": "1.0"},
             "zonesNote": "全部 12 点都在四号谷地（= 240/分，与实测吻合）；**武陵没有紫晶矿**（TapTap 地图工具：武陵紫晶矿脉 0）。",
             "regions": "四号谷地（枢纽区 / 谷地通道 / 阿伯莉采石场）"},
            {"ore": "蓝铁矿", "itemId": "item_iron_ore",
             "pointsTotal": 60, "pointsVersion": "1.0",
             "theoreticalMax": {"value": 1200, "version": "1.5", "how": "60 个矿点 × 20/分"},
             "byMap": {"四号谷地": 54, "武陵": 6},
             "mapMax": {"四号谷地": 1080, "武陵": 120},
             "mapMaxConfidence": {"四号谷地": "实测（四方一致）", "武陵": "推算"},
             "zones": [
                 {"zone": "枢纽区", "levelId": "map01_lv001", "points": 18},
                 {"zone": "谷地通道", "levelId": "map01_lv002", "points": 2},
                 {"zone": "源石研究园", "levelId": "map01_lv005", "points": 13},
                 {"zone": "供能高地", "levelId": "map01_lv007", "points": 21},
                 {"zone": "武陵城", "points": 6, "high": 6, "low": 0, "perMin": 120,
                  "note": "6 个高纯度蓝铁矿点（武陵简报截图）= 120/分"},
             ],
             "zonesCover": "四号谷地+武陵", "zonesCoverAll": True,
             "zonesSum": {"points": 60, "perMin": 1200, "version": "1.5"},
             "zonesNote": "四号谷地 54 点 = 1080/分（与实测吻合）；矿脉源区也产蓝铁矿但那一区没有按区数字，未列入。供能高地桥头区要解「离群之狼」支线才进得去。武陵：武陵城 6 高 = 120/分（武陵简报截图）。",
             "regions": "四号谷地（枢纽区 / 源石研究园 / 矿脉源区 / 供能高地）· 武陵（武陵城）"},
            {"ore": "赤铜矿", "itemId": "item_copper_ore",
             "unit": "矿源点（每个点放 1 台水驱矿机）",
             # ✅✅ 2026-09-21 深夜（终版·闭环）：博士给了武陵简报截图，逐区计数（含高低纯度）：
             #    清波寨 8 高 · 首墩 4 高 · 藏剑谷 4 高 · 试验园区 2 高 · 雪松林 4 高 1 低 · 北部禁区 1 高 4 低
             #    = 23 高 + 5 低 = **28 个矿源点**；23×20 + 5×10 = **510/分，与游戏内 UI「理论最大开采值」完全一致**。
             #    （此前口述版「藏剑谷 2 高、雪松林 3 高 2 低」是漏数；以截图为准。）
             #    教训记档：口述容易漏数，截图/系统数值是最终凭证；差额没闭合前不猜、不编分布。
             "pointsTotal": 28, "pointsVersion": "1.5",
             "highPoints": 23, "lowPoints": 5,
             "pointsNote": ("1.5 实测（武陵简报截图逐区计数）：23 个高纯度点 + 5 个低纯度点 = 28 点。"
                            "高纯度 20/分、低纯度 10/分 → 23×20 + 5×10 = **510/分，与游戏内 UI 完全一致，闭环**。"),
             "theoreticalMax": {"value": 510, "version": "1.5",
                                "how": "23 高 × 20 + 5 低 × 10 = 510（武陵简报截图逐区计数，与 UI 一致）",
                                "source": "武陵简报截图；NGA tid=47560240 同值"},
             "byMap": {"四号谷地": 0, "武陵": 28},
             "mapMax": {"四号谷地": 0, "武陵": 510},
             "mapMaxConfidence": {"武陵": "实测闭环 —— 武陵简报截图逐区计数，与游戏内 UI 完全一致"},
             "zones": [
                 {"zone": "清波寨", "levelId": "map02_lv003", "points": 8, "high": 8, "low": 0, "perMin": 160,
                  "note": "2 处集中矿点（核心 6 + 偏远 2）；水驱矿机要水泵供水，水泵的电从武陵城 / 景玉谷拉"},
                 {"zone": "藏剑谷", "levelId": "map02_lv006", "points": 4, "high": 4, "low": 0, "perMin": 80,
                  "note": "4 个高纯度点（武陵简报截图）；此前口述版记 2 个是漏数"},
                 {"zone": "首墩", "levelId": "map02_lv004", "points": 4, "high": 4, "low": 0, "perMin": 80,
                  "note": "有次级核心、好取电；但矿点与水场有高低差，栖云林地那处容易漏"},
                 {"zone": "试验园区", "levelId": "map02_lv005", "points": 2, "high": 2, "low": 0, "perMin": 40,
                  "note": "另产 2 个高纯度源矿点（武陵简报截图）；电要从武陵城拉"},
                 {"zone": "雪松林", "levelId": "map02_lv009", "points": 5, "high": 4, "low": 1, "perMin": 90,
                  "note": "**1.5「雪凇幽梦」新区域**；4 高 + 1 低（武陵简报截图）"},
                 {"zone": "北部禁区", "levelId": "map02_lv008", "points": 5, "high": 1, "low": 4, "perMin": 60,
                  "note": "1 高 + 4 低（武陵简报截图）"},
             ],
             "zonesCover": "武陵", "zonesCoverAll": True,
             "zonesSum": {"points": 28, "perMin": 510, "version": "1.5"},
             "zonesNote": "按区明细 = 武陵简报截图（1.5 实测）；合计 28 点（23 高 + 5 低）= 510/分，与游戏内 UI 完全一致。",
             "regions": "武陵（清波寨 / 藏剑谷 / 首墩 / 试验园区 / 雪松林 / 北部禁区）—— 6 个区，其他地图没有",
             "rig": "水驱矿机（只能用这一种）", "since": "1.1 版本新增"},
        ],
        "bedsSource": ("官方 FAQ + TapTap 地图工具 / 地图集 + NGA 实测贴（tid=46073277 / 45696282 / 47257073 / 47560240）"
                       "+ 游民星空 + sticweb + game8 / gamewith / ofzenandcomputing / wotpack"),
        "capacityHow": ("满采量 = **高纯度点 × 20/分 + 低纯度点 × 10/分**（产量只由纯度决定，与矿机型号无关）。"
                        "**一个矿脉只放 1 台矿机** —— 四号谷地实测 560/240/1080 除以 20 正好等于 28/12/54 个矿点，"
                        "与 TapTap 地图工具的矿脉数逐项相等，所以「矿脉数 = 可放矿机点数」，一对一，**不要再乘每脉点数**。"
                        "（游戏里一个矿脉视觉上有 2~6 个矿石簇，那是外观，不是矿机位。）"),
        "notOre": ("这些**不是矿脉矿点**，不要混进本表："
                   "① 「稀有矿物」（轻/中/重黯石、燎石、武陵石、协议纹石）—— 野外**手动拾取**的武器调谐石，矿机采不了；"
                   "② 「稀有植物 / 植物类素材」（蘑菇、砂叶、荞花等）—— 走采种机 / 种植机，不是矿点；"
                   "③ 惰气 / 息壤气 —— 野外气体节点，走**气体收集泵**，在 `gather` 里不在 `beds` 里。"),
        "versionLog": [
            {"version": "1.0", "note": "三种工业矿：源矿 58 / 紫晶矿 12 / 蓝铁矿 60 个矿点；矿点位置与数量属关卡场景数据，配置表里没有"},
            {"version": "1.1", "note": "新增赤铜矿：武陵 5 个产区共 21 个矿源点，满采 420/分（NGA 实测逐个点数过）；水驱矿机由武陵工业二期解锁"},
            {"version": "1.5", "note": "赤铜矿 28 点（23 高 + 5 低）= 510/分、源矿全图 60 点 = 1100/分，均与游戏内 UI 一致（武陵简报截图逐区计数，闭环）；新增雪凇幽梦地图（雪松林等）"},
        ],
        "sources": [
            "https://nga.178.com/read.php?tid=46073277  （四号谷地全开产能：源石 560 / 紫晶 240 / 蓝铁 1080 每分钟）",
            "https://nga.178.com/read.php?tid=45696282  （建设等级 12 级矿全开：源矿 560、紫晶 240、蓝铁 1080 —— 与上一条独立吻合）",
            "https://www.gamersky.com/handbook/202601/2084810.shtml  （游民星空四号谷地毕业：源矿 560/min、蓝铁 1080/min）",
            "https://sticweb.tw/明日方舟-終末地-基建產能攻略  （四号谷地全开发后：源矿 560 / 紫矿 240 / 蓝矿 1080 每分钟）",
            "https://www.taptap.cn/app-map/detail/232326  （TapTap 地图工具：四号谷地 蓝铁矿脉 54 / 源矿矿脉 28 / 紫晶矿脉 12 / 赤铜矿脉 0 —— 与 560/240/1080÷20 逐项相等）",
            "https://www.taptap.cn/moment/811907979933649050  （TapTap 地图集：藏剑谷新增 4 个赤铜矿点）",
            "https://bbs.nga.cn/read.php?tid=47257073  （赤铜矿 1.1 实测：160清波+80藏剑+80首墩+60北部+40试验 = 420/分）",
            "https://bbs.nga.cn/read.php?tid=47560240  （赤铜矿 1.5 理论值 510/分）",
            "https://bbs.nga.cn/read.php?tid=46367272  （纯度按区分级解锁：景玉谷 8 级满纯、供能高地 11 级满纯；另提到「武陵源矿最大 480」）",
            "https://game8.co/games/Arknights-Endfield/archives/575661  （纯度：低 10/分、高 20/分；由地区发展等级提升）",
            "https://gamewith.jp/akendfield/548565  （日站：赤铜矿可在清波砦 / 首礎 / 実験区域 / 蔵剣谷 采集）",
        ],
    }
    # ★ 自洽自检：三条
    #   ① 按区求和 == zonesSum（总是查）
    #   ② mapMax 各大地图合计 == theoreticalMax（按**同一个版本**比，别跟 pointsTotal 比 —— 那是 1.1 的点数）
    #   ③ 只有当按区明细**覆盖全图**（zonesCoverAll）时，才要求 zonesSum == theoreticalMax；
    #      只覆盖一个大地图的（源矿 / 蓝铁 只有四号谷地明细）差额就是另一个大地图，**不是错**。
    #   前四次算错都出在「没有这道门」，所以宁可写细一点。
    _ore_checks = []
    for _b in ores["beds"]:
        _z = _b.get("zones") or []
        _sum = _b.get("zonesSum") or {}
        _tm = _b.get("theoreticalMax") or {}
        _mm = _b.get("mapMax") or {}
        _ua = (_b.get("unaccounted") or {}).get("perMin")
        _zs = sum((x.get("points") or x.get("beds") or 0) for x in _z)
        if _z and _sum:
            _want = _sum.get("points") if _sum.get("points") is not None else _sum.get("beds")
            if _want is not None and _zs != _want:
                _ore_checks.append(_b["ore"] + " 按区求和 " + str(_zs) + " ≠ zonesSum " + str(_want))
        if _mm and _tm and sum(_mm.values()) != _tm["value"]:
            _d = _tm["value"] - sum(_mm.values())
            if _d != (_ua or 0):
                _ore_checks.append(_b["ore"] + " mapMax 合计 " + str(sum(_mm.values()))
                                   + " ≠ 理论值 " + str(_tm["value"]) + "（差 " + str(_d)
                                   + "，unaccounted=" + str(_ua) + "）")
        if _b.get("zonesCoverAll") and _sum and _tm and _sum.get("perMin") is not None:
            _d = _tm["value"] - _sum["perMin"]
            if _d != (_ua or 0):
                _ore_checks.append(_b["ore"] + " 理论值 " + str(_tm["value"]) + " − 按区 " + str(_sum["perMin"])
                                   + " = " + str(_d) + "，但 unaccounted=" + str(_ua))
    if _ore_checks:
        for _m in _ore_checks:
            print("  ⚠️ 矿点自检：" + _m)
    else:
        print("  ℹ️ 矿点自检通过（按区 / 按地图 / 点数×20 三处都自洽）")
    # 电池燃料按地区分（博士 2026-09-21 定：谷地用谷地电池、武陵用武陵电池）
    fuel_by_region = {
        "四号谷地": [{"item": "低容谷地电池", "power": 220}, {"item": "中容谷地电池", "power": 420}, {"item": "高容谷地电池", "power": 1100}],
        "武陵": [{"item": "低容武陵电池", "power": 1600}, {"item": "中容武陵电池", "power": 3200}],
        "通用": [{"item": "源矿", "power": 50}],
    }
    power["fuelByRegion"] = fuel_by_region
    power["fuelRule"] = ("2026-09-21 定：**谷地用谷地电池、武陵用武陵电池**（源矿作为通用兜底）。"
                         "一台热能池的发电功率 = 它烧的那种燃料的功率值（前提是燃料供给跟得上），"
                         "所以需要的热能池台数 = ceil(缺口 / 电池功率值)。")
    mining_power = {
        "madeFrom": "FactoryBuildingTable（按 quickBarType=资源开采 列全 7 座）+ FactoryMinerTable + FactoryFluidPumpInTable + 社区实测（发电数值 / 三台采集设备的速率与可采物 / 矿点与纯度）",
        "rateSources": WEB_SOURCES,
        "ores": ores,
        "gather": gather, "miners": miners, "pumps": pumps,
        "power": power,
    }
    dump("mining_power.json", mining_power)
    dump("manual_recipes.json", manual_list)
    dump("items.json", item_index)
    dump("grow_cabin.json", grow_cabin)
    dump("manufacture.json", manufacture)
    dump("mechanics.json", mechanics_index)
    dump("regions.json", region_view)
    # v131：分类字典 + 官方面板组顺序（priority 降序）——排序信息从此有数据依据
    dump("categories.json", {
        "source": "FactoryQuickBarTypeTable（游戏内「工业设备」面板官方分组，v131 对齐；v132 起动态读 raw 表）",
        "mode": QB_MODE,
        "names": QUICKBAR_NAMES,
        "order": QUICKBAR_ORDER,
    })
    dump("blueprint.json", blueprint)
    dump("logistics.json", logistics)
    dump("rules.json", rules)
    dump("bases.json", bases)

    print("\n=== 完成 ===")
    for k, v in meta["counts"].items():
        print(f"  {k}: {v}")
    print("  地区: " + ", ".join(f"{k}({v['count']}+{v.get('manualRecipes',0)}手工)" for k, v in region_view.items()))
    print("  占地规格种类: " + ", ".join(
        f"{g['footprint']}×{g['count']}座" for g in footprint_group_list[:8]))

    # ⭐v110 版权隔离：数据包重建后，raw/ 派生字段的烘焙文件一并刷新，
    #    这样没有 raw/ 的机器（云端）也能跑 build_html.py。
    _bake = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bake_raw.py")
    if os.path.exists(os.path.join(ROOT, "raw")) and os.path.exists(_bake):
        print("\n--- 刷新 raw 烘焙 ---")
        rc = subprocess.run([sys.executable, _bake]).returncode
        if rc != 0:
            print("⚠️ 烘焙失败（rc=%d），data/raw_baked.json 可能已过期" % rc)


if __name__ == "__main__":
    main()
