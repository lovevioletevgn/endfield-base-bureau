# -*- coding: utf-8 -*-
"""
基地 / 据点层 —— 造蓝图要用的"这块地有多大、能放多少东西"。

数据分两类，绝不能混着说：
  【配置表】可从 TableCfg 直接取：
    - 集成管家（FactoryPanelStoreTable）的「区域扩大」「仓库存取线」档位与券价
      ⚠ goodType 在这版表里是数字：1 = 区域扩大，2 = 仓库存取线（旧版是字符串枚举，两种都兼容）
    - 据点发展等级（DomainDataTable）每级给各建造区多少协议容量 / 防御建筑上限 / 滑索上限
    - 蓝图系统硬上限（FacBlueprintConst）：50×50、160 节点、名称 15 字等
    - 建造区的游戏内名称（LevelDescTable.showName）与所属据点（SettlementBasicDataTable）
      ⚠ 这两张表的文本字段同样是 {id,text} 节点，要走 T() 解析
  【社区实测】不在配置表里，只能靠玩家量：
    - 建设区域边长（四号谷地 主 70×70 / 副 40×40；武陵 主 80×80 / 副 50×50）
    - 单边仓库存取口路数（1 路 = 3 格）
  实测数据一律带来源与可信度，页面上单独标注，不与配置表数据混排。

⚠️ 已知边界：建设区域边长不写在任何 TableCfg 里（属于关卡场景数据）。
   areaSourceNote / boundaries 里说明了这一点 —— 别在别处把它说成"配置表数据"。
"""

DOMAIN_ORDER = ["domain_1", "domain_2"]

# 集成管家 goodType：数字（当前版本）与字符串（旧版本）两套都认
GOOD_TYPE = {
    1: "RegionLevelUp", "1": "RegionLevelUp",
    2: "BusPlace", "2": "BusPlace",
    "RegionLevelUp": "RegionLevelUp", "BusPlace": "BusPlace",
}
CURRENCY_NAMES = {
    "item_domain_tundra_coupon": "谷地券",
    "item_domain_jinlong_coupon": "武陵券",
}

# ---------------------------------------------------------------- 社区实测
# 只放"能量到"的观测值。来源编号见 SOURCES。
# 单位：格。slotsPerSide = 单边最多能排几个仓库存取口（1 口 = 3 格宽，见 SLOT_RULE）。
AREA_OBSERVATIONS = [
    {
        "domain": "domain_1", "domainName": "四号谷地",
        "kind": "主基地", "coreName": "协议核心", "coreId": "sp_hub_1",
        "side": 70, "cells": 4900, "slotsPerSide": 23,
        "slotMeasured": True,
        "confidence": "高（两处独立来源一致）",
        "sources": ["A", "B"],
    },
    {
        "domain": "domain_1", "domainName": "四号谷地",
        "kind": "副基地", "coreName": "次级核心", "coreId": "sp_sub_hub_1",
        "side": 40, "cells": 1600, "slotsPerSide": 13,
        "slotMeasured": True,
        "confidence": "高（两处独立来源一致）",
        "sources": ["A", "B"],
    },
    {
        "domain": "domain_2", "domainName": "武陵",
        "kind": "主基地", "coreName": "协议核心", "coreId": "sp_hub_1",
        "side": 80, "cells": 6400, "slotsPerSide": 26,
        "slotMeasured": False,
        "confidence": "中（单来源实测；存取口路数为推算）",
        "sources": ["B"],
    },
    {
        "domain": "domain_2", "domainName": "武陵",
        "kind": "副基地", "coreName": "次级核心", "coreId": "sp_sub_hub_1",
        "side": 50, "cells": 2500, "slotsPerSide": 16,
        "slotMeasured": False,
        "confidence": "中（单来源实测；存取口路数为推算）",
        "sources": ["B"],
    },
]

SOURCES = {
    "A": {
        "id": "A",
        "title": "《明日方舟终末地》四号谷地毕业基建合集",
        "author": "十六_16",
        "site": "17173",
        "date": "2026-01-31",
        "claim": "核心面积 70x70，单边最大 23 个取货口；次级核心面积 40x40，单边最大 13 取货口。",
        "url": "https://news.17173.com/content/01312026/111251217.shtml",
    },
    "B": {
        "id": "B",
        "title": "武陵主副基地满级后的占地面积有多大？和谷地的一样吗？",
        "author": "守望·灰烬",
        "site": "好游快爆 问答",
        "date": "2026-03-02",
        "claim": "（实测）武陵主 80×80=6400 格 / 副 50×50=2500 格；四号谷地主 70×70=4900 格 / 副 40×40=1600 格。",
        "url": "https://m.3839.com/wenda/81/8602081.htm",
    },
    "C": {
        "id": "C",
        "title": "四号谷地基地实拍（枢纽区与副基地的存取线）",
        "author": "博士",
        "site": "游戏内截图",
        "date": "2026-09-21",
        "claim": "（实拍）枢纽区：源桩在一角，与之相连的两条边排满基段、对称的两边没有；副基地：只有一条边排满。",
        "url": "",
    },
    "D": {
        "id": "D",
        "title": "四号谷地一键毕业蓝图分享（含各基地存取线方位）",
        "author": "UP 主（游民星空等多站转载）",
        "site": "游民星空",
        "date": "2026-01",
        "claim": "谷地通道 / 源石研究园 / 供能高地：存取线在上方；枢纽区：上方与右侧（原文注明会随镜头镜像）。"
                 "⚠️ 方位随镜头变化，本库只采信其中「几条边排满」这个视角无关的部分。",
        "url": "https://wap.gamersky.com/gl/Content-2086231.html",
    },
}

# ---------------------------------------------------------------- 谷地存取线布局（实测）
# 四号谷地的仓库存取线是**基地升级后自动铺在基地外侧边缘**的，玩家不用自己摆（武陵才是自己摆），
# 所以配置表里既没有数量上限（档位 actionParams 不含数量），也拿不到坐标
# （FactoryBusStructureTable 的 position / range 全为 0 —— 属关卡场景数据，跟建设区域边长同类）。
#
# 因此这里只收**视角无关**的事实：源桩在一角，与之相连的几条边排满基段。
# 方位（上方 / 右侧）会随镜头旋转而变，不收 —— 沙盘已支持转镜头（LO.viewRot），
# 按"几条边排满"摆就对得上，不需要固定标边。
BUS_NOTE = (
    "四号谷地的仓库存取线由基地升级自动铺在基地外侧边缘，不需要自己摆（武陵才要自己摆）。"
    "配置表里没有数量上限，坐标也拿不到（FactoryBusStructureTable 的 position 全为 0，属关卡场景数据）。"
    "所以这里只记「源桩在一角、与之相连的几条边排满基段」这个视角无关的事实 —— "
    "具体是哪条边随镜头变化，在沙盘里转一下就对得上。"
)
# levelId: (排满的边数, 有无源桩, 来源)
# 主基地（枢纽区）有源桩：基段紧贴源桩、沿相连的两条边排满；
# 副基地**没有源桩** —— 存取线自动铺好一条边，玩家只需要贴放存货口 / 取货口
# （博士 2026-09-21 补充："副基地只用存取线就行"）。
BUS_OBSERVATIONS = {
    "map01_lv001": (2, True, "C"),    # 枢纽区（主基地）：源桩在一角，相连的两条边排满，对称两边空
    "map01_lv002": (1, False, "D"),   # 谷地通道
    "map01_lv005": (1, False, "D"),   # 源石研究园
    "map01_lv007": (1, False, "D"),   # 供能高地
}

SLOT_RULE = {
    "slotWidthCells": 3,
    "formula": "单边可排路数 = (边长 - 1) ÷ 3 向下取整",
    "note": ("1 个仓库存取口占 3 格宽。70 → 23 路、40 → 13 路均为社区实测，与该公式一致；"
             "武陵侧的路数由同一条规律推算，未经实测 —— 页面按「推算」标注。"),
}

BOUNDARY_NOTES = [
    "建设区域的<strong>边长与面积不写在配置表里</strong>（属于关卡场景数据）。下面这张面积表是玩家实测值，"
    "不是从 TableCfg 提取的 —— 与本库其它页的数据来源不同，引用时请分开说明。",
    "实测值对应的是<strong>满级（区域扩大·二 之后）</strong>的面积；扩建前更小，"
    "需要用集成管家里的「区域扩大·一 / 二」两档逐步开放（价目见下表，来自配置表）。",
    "武陵那组只有<strong>单一来源</strong>（问答贴里的实测），比四号谷地那组弱一档 —— "
    "四号谷地的 70×70/40×40 有两处互相独立的来源印证。上机后建议自己量一遍再定稿。",
    "基地只存在于 <strong>8 个建造区</strong>（有集成管家条目的那些）；其余 7 个区没有基地，"
    "配置表给它们的协议容量只约束区内野外设备。"
    "8 个基地的面积按所属地区的实测上限套用 —— <strong>没有逐片实测过</strong>，这是上限口径。",
]

# 哪几个建造区是主基地（放协议核心），其余同据点的是副基地（放次级核心）。
# ⚠️ 这不是从配置表推出来的 —— 是博士 2026-09-20 在游戏里确认的。
#    每个据点：1 个主基地 + 3 个副基地。
MAIN_BASE_ZONES = {
    "map01_lv001",   # 四号谷地·枢纽区
    "map02_lv002",   # 武陵·武陵城
}
MAIN_BASE_NOTE = (
    "<strong>每个据点是「1 主 + 3 副」</strong>：四号谷地主基地是<strong>枢纽区</strong>，"
    "武陵主基地是<strong>武陵城</strong>；同据点其余三片是副基地。"
    "主基地放协议核心、副基地放次级核心，所以主基地用的地区<strong>主基地边长</strong>、"
    "副基地用的地区<strong>副基地边长</strong> —— 每片基地只有一个建设区，不是每片都主副各占一块。"
    "（博士 2026-09-20 游戏内确认）"
)

# 只需要露出的蓝图硬上限（其余键原样保留在 raw）
BLUEPRINT_CAP_LABELS = [
    ("BluePrintXLenMax", "蓝图最大宽度（格）"),
    ("BluePrintZLenMax", "蓝图最大进深（格）"),
    ("BlueprintNodeCountLimit", "单张蓝图节点上限"),
    ("BlueprintNameMaxLen", "蓝图名称最长字数"),
    ("BlueprintDescMaxLen", "蓝图描述最长字数"),
    ("BluePrintTagNumMax", "蓝图标签数上限"),
    ("BluePrintDailyReviewNumMax", "每日审核上限"),
    ("MyBluePrintNumMax", "我的蓝图保存上限"),
    ("GiftBluePrintNumMax", "赠送蓝图上限"),
    ("PendingPlaceNumMax", "待放置蓝图数上限"),
    ("BlueprintShareCodePrefix", "分享码前缀"),
    ("BlueprintCharSet", "分享码字符集"),
    ("SharedBluePrintExpireTime", "分享码有效期"),
]

EXPANSION_LABELS = {
    "RegionLevelUp": "区域扩大（建设区域变大）",
    "BusPlace": "仓库存取线（进/出料口通道）",
}


def _region_names(load, T):
    """建造区（levelId）的中文名 + 所属据点名。两张表的文本字段都是 {id,text} 节点。"""
    names, settlements = {}, {}
    for lid, rec in (load("LevelDescTable") or {}).items():
        nm = T(rec.get("showName"))
        if nm:
            names[lid] = nm
    for sid, rec in (load("SettlementBasicDataTable") or {}).items():
        lid = rec.get("domainLevelId")
        if lid:
            settlements.setdefault(lid, []).append({
                "id": sid,
                "name": T(rec.get("settlementName")) or sid,
                "levels": sorted((rec.get("settlementLevelMap") or {}).keys(),
                                 key=lambda x: int(x) if str(x).isdigit() else 0),
            })
    return names, settlements


def _target_level(item):
    """区域扩大条目里的目标区域等级（actionParams = [regionId, "<目标等级>", "0"]）。"""
    for grp in (item.get("actionParamsList") or []):
        params = grp.get("actionParams") or []
        if len(params) >= 2 and str(params[1]).isdigit():
            return int(params[1])
    return None


# 仓库存取线一族（配置表里的建筑 id）。沙盘要靠这几个做放置校验。
HONGS_IDS = {
    "log_hongs_bus_source": "源桩",
    "log_hongs_bus": "基段",
}


def _grants(item):
    """仓库存取线档位「给几个」—— actionParams = [levelId, 建筑id, "0", "<个数>"]。

    ⚠️ 和区域扩大的 actionParams 结构不同（那个是 [regionId, 目标等级, "0"]），
    所以只认第二项是 log_hongs_* 的条目，别把两类混在一起解析。
    没有 grants 的档位（理论上不该有）返回 None，页面按 0 处理。
    """
    out = []
    for grp in (item.get("actionParamsList") or []):
        params = grp.get("actionParams") or []
        if len(params) >= 4 and str(params[1]) in HONGS_IDS:
            try:
                cnt = int(params[3])
            except (TypeError, ValueError):
                continue
            out.append({"id": params[1], "name": HONGS_IDS[params[1]], "count": cnt})
    return out or None


def build_bases(load, T):
    domain_table = load("DomainDataTable") or {}
    store_table = load("FactoryPanelStoreTable") or {}
    bp_const = load("FacBlueprintConst") or {}
    region_table = load("FactoryRegionTable") or {}

    zone_names, settlements = _region_names(load, T)

    # 建造区 → 据点。FactoryRegionTable 只有 levelId↔regionId，
    # 归属要靠 DomainDataTable 的 levelGroup 回填。
    level_to_domain = {}
    for did, d in domain_table.items():
        for lid in (d.get("levelGroup") or []):
            level_to_domain[lid] = did

    # ------------------------------------------------ 建造区清单
    # 黑盒挑战关、测试关卡没有 levelGroup，直接排除。
    zones = []
    for rid, rec in sorted(region_table.items()):
        lid = rec.get("levelId")
        did = level_to_domain.get(lid)
        if not did:
            continue
        d = domain_table[did]
        zones.append({
            "levelId": lid,
            "regionId": rid,
            "zoneName": zone_names.get(lid, lid),
            "domain": did,
            "domainName": T(d.get("domainName")) or did,
            "settlements": settlements.get(lid, []),
            "hasBuiltArea": False,   # 由下面的管家条目回填
            "expansion": [],
            "bus": [],
        })
    zone_by_level = {z["levelId"]: z for z in zones}

    # ------------------------------------------------ 集成管家条目
    unmatched = []
    for item in sorted(store_table.values(), key=lambda r: str(r.get("id"))):
        lid = item.get("regionId")
        z = zone_by_level.get(lid)
        if not z:
            unmatched.append(item.get("id"))
            continue
        good = GOOD_TYPE.get(item.get("goodType"))
        if not good:
            unmatched.append(item.get("id"))
            continue
        cur = item.get("currencyType")
        row = {
            "id": item.get("id"),
            "name": T(item.get("name")) or item.get("id"),
            "cost": item.get("cost"),
            "currency": CURRENCY_NAMES.get(cur, cur),
            "currencyId": cur,
            "sortId": item.get("sortId"),
            "targetLevel": _target_level(item) if good == "RegionLevelUp" else None,
            "unlockAfter": [p for grp in (item.get("conditionParamsList") or [])
                            for p in (grp.get("conditionParams") or [])] or None,
            # 仓库存取线档位才「给东西」；区域扩大档位的 actionParams 结构不同，不解析
            "grants": _grants(item) if good == "BusPlace" else None,
        }
        if good == "RegionLevelUp":
            z["expansion"].append(row)
            z["hasBuiltArea"] = True
        else:
            z["bus"].append(row)
    for z in zones:
        z["expansion"].sort(key=lambda r: r.get("sortId") or 0)
        z["bus"].sort(key=lambda r: r.get("sortId") or 0)
        z["expansionCostTotal"] = sum(r["cost"] or 0 for r in z["expansion"]) or None
        z["busCostTotal"] = sum(r["cost"] or 0 for r in z["bus"]) or None
        z["busCount"] = len(z["bus"])
        # 满级累计上限：把各档 grants 相加 → {"log_hongs_bus": 25, "log_hongs_bus_source": 2}
        # 沙盘拿它显示「基段 11 / 25」（博士 2026-09-21 要求，对应游戏里的 11/25 计数）
        _cap = {}
        for _row in z["bus"]:
            for _g in (_row.get("grants") or []):
                _cap[_g["id"]] = _cap.get(_g["id"], 0) + _g["count"]
        z["busCap"] = _cap or None
        _bo = BUS_OBSERVATIONS.get(lid)
        z["busLayout"] = ({"edges": _bo[0], "source": _bo[1], "sourceId": _bo[2]} if _bo else None)
        z["currency"] = (z["expansion"][0]["currency"] if z["expansion"]
                         else z["bus"][0]["currency"] if z["bus"] else None)

    expandable = [z for z in zones if z["hasBuiltArea"]]

    # ------------------------------------------------ 据点发展等级 → 建造上限
    domains = []
    for did in DOMAIN_ORDER:
        d = domain_table.get(did)
        if not d:
            continue
        levels = []
        for lv in (d.get("domainDevelopmentLevel") or []):
            effects = lv.get("domainDevelopmentLevelEffect") or {}
            rows = []
            for lid, e in sorted(effects.items(), key=lambda kv: kv[1].get("sortId") or 0):
                z = zone_by_level.get(lid)
                rows.append({
                    "levelId": lid,
                    "zoneName": z["zoneName"] if z else zone_names.get(lid, lid),
                    "bandwidth": e.get("bandwidth"),
                    "battleBuildingLimit": e.get("battleBuildingLimit"),
                    "travelPoleLimit": e.get("travelPoleLimit"),
                    "mineOutputUp": bool(e.get("isMineOutputUp")),
                    "maxBandwidth": bool(e.get("isFinalMaxBandwidth")),
                    "maxBattle": bool(e.get("isFinalMaxBattleBuildingLimit")),
                    "maxPole": bool(e.get("isFinalMaxTravelPoleLimit")),
                    "buildable": bool(z and z["hasBuiltArea"]),
                })
            levels.append({
                "level": lv.get("domainDevelopmentLevel"),
                "levelUpExp": lv.get("levelUpExp"),
                "moneyLimit": lv.get("moneyLimit"),
                "isFinalMaxLevel": bool(lv.get("isFinalMaxLevel")),
                "versionStart": lv.get("versionStart"),
                "regions": rows,
            })
        domains.append({
            "id": did,
            "name": T(d.get("domainName")) or did,
            "storageName": T(d.get("storageName")),
            "baseItemStackCount": d.get("baseItemStackCount"),
            "maxLevel": levels[-1]["level"] if levels else None,
            "levels": levels,
        })

    # ------------------------------------------------ 面积表（实测）
    areas = []
    for ob in AREA_OBSERVATIONS:
        side = ob["side"]
        areas.append({
            "domain": ob["domain"], "domainName": ob["domainName"],
            "kind": ob["kind"], "coreName": ob["coreName"], "coreId": ob["coreId"],
            "side": side,
            "size": "%d×%d" % (side, side),
            "cells": ob["cells"],
            "cellsPerSide": side,
            "slotsPerSide": ob["slotsPerSide"],
            "slotMeasured": ob["slotMeasured"],
            "slotNote": ("单边最多 %d 路存取口（%s），%d×3+1=%d ≤ %d"
                         % (ob["slotsPerSide"],
                            "实测" if ob["slotMeasured"] else "推算",
                            ob["slotsPerSide"], ob["slotsPerSide"] * 3 + 1, side)),
            "coreFootprint": "%s 本体 9×9，占在这块地里" % ob["coreName"],
            "coreCells": 81,
            "usableCells": ob["cells"] - 81,
            "confidence": ob["confidence"],
            "sources": [SOURCES[s] for s in ob["sources"]],
        })

    # ------------------------------------------------ 蓝图硬上限
    caps = []
    for key, label in BLUEPRINT_CAP_LABELS:
        if key not in bp_const:
            continue
        v = bp_const[key]
        if key == "SharedBluePrintExpireTime":
            v = "%d 秒（= %.1f 天）" % (v, v / 86400.0)
        elif key == "BlueprintCharSet":
            v = "%s（不含小写 l）" % v
        caps.append({"key": key, "label": label, "value": v})

    # 面积 vs 蓝图上限的直接结论
    bp_x = bp_const.get("BluePrintXLenMax")
    bp_z = bp_const.get("BluePrintZLenMax")
    comparisons = []
    if bp_x and bp_z:
        for a in areas:
            per_x = a["side"] // bp_x
            per_z = a["side"] // bp_z
            if per_x >= 2:
                note = ("单边可并排 %d 张 %d×%d；整块地最多铺 %d×%d = %d 张"
                        % (per_x, bp_x, bp_z, per_x, per_z, per_x * per_z))
            elif a["side"] == bp_x:
                note = "边长正好 %d —— 一张满规格蓝图刚好铺满" % bp_x
            elif per_x == 1:
                note = ("单边只放得下 1 张 %d×%d，还剩 %d 格边角 —— 一张铺不满整块地"
                        % (bp_x, bp_z, a["side"] - bp_x))
            else:
                note = ("建设区（%d×%d）比蓝图上限（%d×%d）还小 —— "
                        "蓝图边长受这块地限制，上限不是瓶颈"
                        % (a["side"], a["side"], bp_x, bp_z))
            comparisons.append({
                "size": a["size"],
                "label": "%s %s" % (a["domainName"], a["kind"]),
                "perSide": per_x,
                "tiles": per_x * per_z,
                "exactMatch": a["side"] == bp_x,
                "note": note,
            })

    # ------------------------------------------------ 满级快照：每个建造区一行
    # 口径统一为「据点发展等级满级 + 区域扩大·二 + 面积取该地区实测最大值」，
    # 这样每个建造区都能给出一行可比的数字。
    # ⚠ 逐建造区的实测边长没有 —— 这里是把地区级上限套用到每个建造区，见 MAX_BASIS。
    obs_by_domain = {}
    for ob in AREA_OBSERVATIONS:
        obs_by_domain.setdefault(ob["domain"], {})[ob["kind"]] = ob

    def bp_fit(side):
        if not (bp_x and bp_z):
            return None
        per = side // bp_x
        if per >= 1:
            left = side - per * bp_x
            if left == 0:
                note = "一张 %d×%d 正好铺满" % (bp_x, bp_z)
            elif per == 1:
                note = "放得下 1 张 %d×%d，余 %d 格边角" % (bp_x, bp_z, left)
            else:
                note = "可并排 %d 张 %d×%d，余 %d 格" % (per, bp_x, bp_z, left)
            return {"perSide": per, "leftover": left, "exact": left == 0, "note": note}
        return {"perSide": 0, "leftover": side, "exact": False,
                "note": "比蓝图上限小 —— 蓝图边长最多 %d 格" % side}

    def area_block(ob):
        if not ob:
            return None
        side = ob["side"]
        return {
            "kind": ob["kind"],
            "coreName": ob["coreName"],
            "coreId": ob["coreId"],
            "coreCells": 81,
            "side": side,
            "size": "%d×%d" % (side, side),
            "cells": ob["cells"],
            "usableCells": ob["cells"] - 81,
            "slotsPerSide": ob["slotsPerSide"],
            "slotMeasured": ob["slotMeasured"],
            "blueprint": bp_fit(side),
        }

    domain_by_id = {d["id"]: d for d in domains}
    # 只列有基地（建设区域）的建造区：即集成管家里有「区域扩大」条目的那 8 张图。
    # 其余 7 个区（阿伯莉采石场/矿脉源区/清波寨/试验园区/藏剑谷/北部禁区/雪松林）没有基地，
    # 配置表里仍给它们协议容量 —— 那是约束区内野外设备的，与基地无关。
    # （来源：博士 2026-09-20 游戏内确认）
    max_bases = []
    for z in zones:
        if not z["hasBuiltArea"]:
            continue
        dm = domain_by_id.get(z["domain"], {})
        last = (dm.get("levels") or [None])[-1]
        caps_row = None
        if last:
            caps_row = next((r for r in last["regions"] if r["levelId"] == z["levelId"]), None)
        # 每片基地只有一个建设区：主基地用地区「主基地」边长，副基地用地区「副基地」边长。
        role = "主基地" if z["levelId"] in MAIN_BASE_ZONES else "副基地"
        obs = obs_by_domain.get(z["domain"], {})
        area = area_block(obs.get(role))
        total = (z["expansionCostTotal"] or 0) + (z["busCostTotal"] or 0)
        max_bases.append({
            "levelId": z["levelId"],
            "zoneName": z["zoneName"],
            "domainId": z["domain"],
            "domainName": z["domainName"],
            "settlements": [s["name"] for s in z.get("settlements") or []],
            "hasBuiltArea": z["hasBuiltArea"],
            "role": role,
            "maxDevLevel": dm.get("maxLevel"),
            "area": area,
            "cells": area["cells"] if area else None,
            "usableCells": area["usableCells"] if area else None,
            "caps": {
                "bandwidth": caps_row.get("bandwidth") if caps_row else None,
                "battleBuildingLimit": caps_row.get("battleBuildingLimit") if caps_row else None,
                "travelPoleLimit": caps_row.get("travelPoleLimit") if caps_row else None,
                "mineOutputUp": caps_row.get("mineOutputUp") if caps_row else None,
            },
            "expansionCostTotal": z["expansionCostTotal"],
            "busCostTotal": z["busCostTotal"],
            "unlockCostTotal": total or None,
            "busCount": z["busCount"],
            "currency": z["currency"],
        })
    max_bases.sort(key=lambda r: (r["domainName"] != "四号谷地", r["role"] != "主基地", r["levelId"]))
    tot_bw = sum(r["caps"]["bandwidth"] or 0 for r in max_bases)
    tot_cost = {}
    for r in max_bases:
        if r["currency"] and r["unlockCostTotal"]:
            tot_cost[r["currency"]] = tot_cost.get(r["currency"], 0) + r["unlockCostTotal"]
    # 每片基地一个建设区，按据点/主副合计地面格数
    cells_by_domain = {}
    for r in max_bases:
        d = cells_by_domain.setdefault(r["domainName"], {"main": 0, "sub": 0, "mainN": 0, "subN": 0})
        key = "main" if r["role"] == "主基地" else "sub"
        d[key] += r["cells"] or 0
        d[key + "N"] += 1
    for name, d in cells_by_domain.items():
        d["total"] = d["main"] + d["sub"]
    tot_cells = sum(d["total"] for d in cells_by_domain.values())

    return {
        "generatedFrom": [
            "DomainDataTable", "FactoryPanelStoreTable", "FacBlueprintConst",
            "LevelDescTable", "SettlementBasicDataTable", "FactoryRegionTable",
        ],
        "unit": "格（1 格 = 建造网格 1 格，与「占地蓝图」页同口径）",
        "areaSourceNote": (
            "本页分两类数据：<strong>面积（边长 / 格数）与单边存取口路数来自社区实测</strong>，不在配置表内；"
            "<strong>扩建价目、据点发展等级上限、蓝图硬上限来自 TableCfg</strong>，可逐条复核。"
            "引用时请分开说明来源。"
        ),
        "maxBasis": (
            "「满级基地总览」全部按<strong>最大值</strong>取：据点发展等级取满级（四号谷地 Lv12 / 武陵 Lv27）、"
            "建设区取区域扩大·二之后的边长、协议容量/防御建筑上限/滑索上限取满级那一档。"
            "面积的<strong>逐片基地实测值我们没有</strong>，所以是把该地区的实测上限套用到同类型的每片基地 —— "
            "这是<strong>上限口径</strong>，不是每片都实测过。"
        ),
        "baseRoleNote": MAIN_BASE_NOTE,
        "baseOnlyNote": (
            "基地只存在于配置表里带「区域扩大」条目的 <strong>8 个建造区</strong>"
            "（四号谷地：枢纽区 / 谷地通道 / 源石研究园 / 供能高地；武陵：景玉谷 / 武陵城 / 首墩 / 应龙关）。"
            "其余 7 个区没有基地 —— 配置表里给它们的协议容量是约束区内<strong>野外设备</strong>的，与基地无关。"
            "（博士 2026-09-20 游戏内确认）"
        ),
        "maxBases": max_bases,
        "maxBasesSummary": {
            "rows": len(max_bases),
            "zonesTotal": len(zones),
            "mainCount": sum(1 for r in max_bases if r["role"] == "主基地"),
            "subCount": sum(1 for r in max_bases if r["role"] == "副基地"),
            "expandable": sum(1 for r in max_bases if r["hasBuiltArea"]),
            "protocolCapacityTotal": tot_bw,
            "cellsByDomain": cells_by_domain,
            "cellsTotal": tot_cells,
            "unlockCostByCurrency": tot_cost,
        },
        "boundaries": BOUNDARY_NOTES,
        "slotRule": SLOT_RULE,
        # C = 博士实拍（谷地存取线）、D = 毕业蓝图攻略（方位，仅采信"几条边"）—— 别写死成两条
        "sources": [SOURCES[k] for k in ("A", "B", "C", "D") if k in SOURCES],
        "areas": areas,
        "areaComparisons": comparisons,
        "expansionLabels": EXPANSION_LABELS,
        "zones": zones,
        "busObservations": {
            "note": BUS_NOTE,
            "zones": [
                {
                    "levelId": lid,
                    "zoneName": zone_by_level[lid]["zoneName"],
                    "domainName": zone_by_level[lid]["domainName"],
                    "side": next((m["area"]["side"] for m in max_bases
                                  if m["levelId"] == lid), None),
                    "edges": edges,
                    "source": has_src,
                    "sourceId": src,
                }
                for lid, (edges, has_src, src) in BUS_OBSERVATIONS.items() if lid in zone_by_level
            ],
        },
        "expandableZones": expandable,
        "unmatchedStoreIds": unmatched,
        "domains": domains,
        "blueprintCaps": caps,
        "summary": {
            "areaEntries": len(areas),
            "activeZones": len(zones),
            "expandableZones": len(expandable),
            "maxBaseRows": len(max_bases),
            "domains": len(domains),
            "maxDevLevel": max((d["maxLevel"] or 0) for d in domains) if domains else 0,
            "expansionTiers": sum(len(z["expansion"]) for z in expandable),
            "busTiers": sum(len(z["bus"]) for z in zones),
        },
    }
