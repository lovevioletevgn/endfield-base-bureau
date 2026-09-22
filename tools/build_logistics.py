# -*- coding: utf-8 -*-
"""
物流规则层构建：传送带 / 管道 / 分流汇流 / 连接器 / 阀门 / 总线 + 全局物流常量。

为什么单独一层：
  FactoryBuildingTable 只装「可摆放设施」，传送带、管道这些**不是建筑**，
  而是独立物流实体，写在 Factory*Belt/Pipe/Router/Connecter/Valve 等表里。
  早期版本用 Conveyor/Belt/Pipe 关键词暴力探测表名，全部落空；
  实际命名用的是 Grid（传送带/分流器）与 Liquid（管道）前缀。

吞吐换算依据：
  msPerRound = 走完 1 个物品所需毫秒 → 每分钟 = 60000 / msPerRound
    grid_belt_01  msPerRound=2000 → 30 个/分钟
    log_pipe_01   msPerRound=500  → 120 个/分钟（另有 volume=1）

⚠️ 两个已经踩过的坑，别再犯：
  1. 别用 Conveyor/Belt/Pipe 关键词猜表名 —— 实际前缀是 Grid / Liquid。
  2. `travelPoleNop1Radius = 300` **不是滑索射程**。travel_pole_nop_1 的描述
     白纸黑字写着「可在80m范围内相连」，而 travelPoleNop1VisibleRadius=120。
     那个 300 与 `udPipeConnectMaxLength = 300` 是同一个数 —— 归在 travelPole
     前缀下，实际是**暗管的配对连接长度**。曾据此编造出「免电滑索架射程 300」
     这个不存在的"干货"，已修正。
"""

# (logisticId, 表名, 表内数据键, 介质, 分类)
LOG_ENTITIES = [
    ("grid_belt_01",         "FactoryGridBeltTable",        "beltData",       "belt", "输送干线"),
    ("log_pipe_01",          "FactoryLiquidPipeTable",      "pipeData",       "pipe", "输送干线"),
    ("log_converger",        "FactoryGridRouterTable",      "gridUnitData",   "belt", "分流汇流"),
    ("log_splitter",         "FactoryGridRouterTable",      "gridUnitData",   "belt", "分流汇流"),
    ("log_pipe_converger",   "FactoryLiquidRouterTable",    "liquidUnitData", "pipe", "分流汇流"),
    ("log_pipe_splitter",    "FactoryLiquidRouterTable",    "liquidUnitData", "pipe", "分流汇流"),
    ("log_connector",        "FactoryGridConnecterTable",   "gridUnitData",   "belt", "转向连接"),
    ("log_pipe_connector",   "FactoryLiquidConnectorTable", "liquidUnitData", "pipe", "转向连接"),
    ("log_conditioner",      "FactoryBoxValveTable",        "gridUnitData",   "belt", "阀门限流"),
    ("log_pipe_conditioner", "FactoryFluidValveTable",      "liquidUnitData", "pipe", "阀门限流"),
]

# 暗管（地下管道）：入口/出口成对使用，传送管道中的液体和气体。
# 注意：它们是 FactoryBuildingTable 里的**正经建筑**（不是物流实体表），
#       因为要占地、要配对连接。FactoryUndergroundPipeTable 是空表。
UNDERGROUND_PIPES = [
    ("udpipe_loader_1",   "暗管入口",     "入口"),
    ("udpipe_loader_2",   "多口暗管入口", "入口"),
    ("udpipe_unloader_1", "暗管出口",     "出口"),
    ("udpipe_unloader_2", "多口暗管出口", "出口"),
]

# _nop_ 后缀 = no-power 变体（同款设施的免电版）。
# ⚠️ 关键坑：它**沿用原版的官方名**，不叫「免电XX」。
#    例：travel_pole_nop_1 官方名就是「滑索架」，和 travel_pole_1 同名。
#    别自己造名字（我造过「免电滑索架」，是错的）。
NOP_PAIRS = [
    ("travel_pole_1",     "travel_pole_nop_1"),
    ("storager_1",        "storager_nop_1"),
    ("liquid_storager_1", "liquid_storager_nop_1"),
    ("dumper_1",          "dumper_nop_1"),
    ("squirter_1",        "squirter_nop_1"),
    ("furnance_1",        "furnance_nop_1"),
]

# 常量分组：(组名, [(键, 中文含义, 单位), ...])
CONST_GROUPS = [
    ("连接距离与角度", [
        ("singleConveyorLengthLimit",      "单条传送带最大长度",       "米"),
        ("singleFluidConveyorLengthLimit", "单条管道最大长度",         "米"),
        ("pipeAngleLimit",                 "管道转角限制",             "度"),
        ("maxBuildingCoverGridHeightDiff", "建筑覆盖允许最大高差",     "格"),
    ]),
    ("阀门限流（滑块档位）", [
        ("facBoxValveSpeedSliderMin",     "传送带阀门 最小值", None),
        ("facBoxValveSpeedSliderMax",     "传送带阀门 最大值", None),
        ("facBoxValveSpeedSliderDefault", "传送带阀门 默认值", None),
        ("facBoxValveSpeedSliderStep",    "传送带阀门 步长",   None),
        ("facFluidValveSpeedSliderMin",   "管道阀门 最小值",   None),
        ("facFluidValveSpeedSliderMax",   "管道阀门 最大值",   None),
        ("facFluidValveSpeedSliderDefault","管道阀门 默认值",  None),
        ("facFluidValveSpeedSliderStep",  "管道阀门 步长",     None),
        ("facValveCountSliderMin",        "阀门计数下限",      None),
        ("facValveCountSliderMax",        "阀门计数上限",      None),
    ]),
    ("布置与上限", [
        ("levelFluidRouterCountLimit", "单关卡流体分流器数量上限", "个"),
        ("pillarGenerateMinDistance",  "管道支架自动生成最小间距", "米"),
        ("signNodeCountLimit",         "标记节点上限",             "个"),
        ("manualWorkCountLimit",       "手动制造同时数上限",       "个"),
        ("farmlandSoilCountLimit",     "农田土壤上限",             "块"),
        ("maxFillingBottleCount",      "灌装同时数上限",           "个"),
    ]),
    ("暗管（地下管道）", [
        ("udPipeConnectMaxLength", "暗管最大配对连接长度", "米"),
    ]),
    ("滑索（移动）", [
        ("travelPole1Radius",        "滑索架 连接距离",     "米"),
        ("travelPole2Radius",        "长距滑索架 连接距离", "米"),
        ("travelPole1Speed",         "滑索移动速度",       "米/秒"),
        ("travelPole1VisibleRadius", "滑索架 索道可见距离", "米"),
        ("travelPole2VisibleRadius", "长距滑索架 索道可见距离", "米"),
        ("travelPoleQteTiming",      "滑索 QTE 时机",      "秒"),
    ]),
    # 配置表内部矛盾项：这几个数被归在 travelPole 前缀下，但与建筑描述不符。
    # 单独列出并标注，避免被误当成滑索数值引用。
    ("⚠️ 存疑常量（与建筑描述不符）", [
        ("travelPoleNop1Radius",        "滑索架·免电版 配置值（存疑，见下方说明）", "米"),
        ("travelPoleNop1VisibleRadius", "滑索架·免电版 索道可见距离",             "米"),
    ]),
    ("物流包与取放距离", [
        ("packPickDistance",  "拾取距离", "米"),
        ("packDropDistance",  "投放距离", "米"),
        ("packMergeDistance", "合并距离", "米"),
        ("outOfRangeHeight",  "越界高度", "米"),
    ]),
    ("电力（参考）", [
        ("facBackUpPowerDuration",     "备用电力持续时间", "秒"),
        ("facBackUpPowerCooldownTime", "备用电力冷却",     "秒"),
    ]),
]


def build_logistics(load, T, item_name_map):
    """构造 logistics.json 的内容。

    load(name)  -> dict，读原始表
    T(node)     -> str，中文文本解析
    item_name_map -> {itemId: 中文名}
    """
    cap = load("FactoryItem2LogisticIdTable") or {}

    def per_min(ms):
        return round(60000.0 / ms, 1) if ms else None

    # ---- 物流实体 ----
    entities = []
    for lid, tbl, sub, medium, cat in LOG_ENTITIES:
        table = load(tbl) or {}
        d = table.get(lid)
        if not d:
            continue
        ud = d.get(sub) or {}
        e = {
            "id": lid,
            "name": T(ud.get("name")),
            "type": cap.get(ud.get("itemId", ""), {}).get("type"),
            "medium": "传送带" if medium == "belt" else "管道",
            "category": cat,
            "itemId": ud.get("itemId"),
            "msPerRound": ud.get("msPerRound"),
            "volume": ud.get("volume"),
            "unitsPerMinute": per_min(ud.get("msPerRound")),
            "unitsPerSecond": round(1000.0 / ud["msPerRound"], 4) if ud.get("msPerRound") else None,
        }
        for kind, key in (("input", "inputPorts"), ("output", "outputPorts")):
            plist = []
            for pp in (d.get(key) or []):
                pos = pp.get("position") or {}
                rot = pp.get("rotation") or {}
                plist.append({
                    "facing": rot.get("y"),
                    "x": pos.get("x"), "y": pos.get("y"), "z": pos.get("z"),
                })
            e[kind + "Ports"] = plist
            e[kind + "PortCount"] = len(plist)
            e[kind + "Facings"] = sorted({p["facing"] for p in plist if p["facing"] is not None})
        entities.append(e)

    # ---- 总线（不在 Item2LogisticId 里） ----
    buses = []
    for k, v in (load("FactoryFreeBusTable") or {}).items():
        buses.append({
            "id": k,
            "name": T(v.get("name")),
            "itemId": v.get("itemId"),
            "type": v.get("type"),
            "range": v.get("range"),
        })

    # ---- 全局常量 ----
    C = load("FactoryConst") or {}
    constants = []
    for gname, keys in CONST_GROUPS:
        for key, label, unit in keys:
            if key in C:
                constants.append({
                    "key": key, "label": label, "value": C[key],
                    "unit": unit, "group": gname,
                })

    # ---- 供电设施 ----
    poles = []
    for k, v in (load("FactoryPowerPoleTable") or {}).items():
        poles.append({
            "id": k,
            "autoConnect": v.get("autoConnect"),
            "autoConnectLength": v.get("autoConnectLength"),
            "rangeExtend": v.get("rangeExtend"),
        })
    for k, v in (load("FactorySpecialPowerPoleTable") or {}).items():
        poles.append({"id": k, "special": True})

    # ---- 采矿 ----
    miners = []
    for k, v in (load("FactoryMinerTable") or {}).items():
        miners.append({
            "id": k,
            "msPerRound": v.get("msPerRound"),
            "unitsPerMinute": per_min(v.get("msPerRound")),
            "hasDroneMode": v.get("hasDroneMode"),
            "minePosition": v.get("minePosition"),
            "mineable": [m.get("miningItemId") for m in (v.get("mineable") or [])],
            "mineableNames": [item_name_map.get(m.get("miningItemId"), m.get("miningItemId"))
                              for m in (v.get("mineable") or [])],
        })

    # ---- 泵 / 排液 / 储罐 ----
    pumps = []
    for k, v in (load("FactoryFluidPumpInTable") or {}).items():
        pumps.append({"id": k, "kind": "抽水泵", "msPerRound": v.get("msPerRound"),
                      "unitsPerMinute": per_min(v.get("msPerRound")),
                      "pumpPosition": v.get("pumpPosition")})
    for k, v in (load("FactoryFluidPumpOutTable") or {}).items():
        pumps.append({"id": k, "kind": "排液口", "maximumSuply": v.get("maximumSuply"),
                      "dumperPosition": v.get("dumperPosition")})

    storagers = [{"id": k, "capacity": v.get("capacity")}
                 for k, v in (load("FactoryFluidContainerTable") or {}).items()]

    # ---- 暗管（地下管道）----
    # 数据在 FactoryBuildingTable，不在物流实体表里。
    buildings_tbl = load("FactoryBuildingTable") or {}
    underground = []
    for bid, name, role in UNDERGROUND_PIPES:
        v = buildings_tbl.get(bid)
        if not v:
            continue
        r = v.get("range") or {}
        item = {
            "id": bid,
            "name": T(v.get("name")) or name,
            "role": role,
            "footprint": f'{r.get("width")}×{r.get("depth")}×{r.get("height")}',
            "gridFootprint": f'{r.get("width")}×{r.get("depth")}',
            "needPower": v.get("needPower"),
            "powerConsume": v.get("powerConsume"),
            "desc": T(v.get("desc")),
        }
        for kind, key in (("input", "inputPorts"), ("output", "outputPorts")):
            plist = []
            for pp in (v.get(key) or []):
                tr = pp.get("trans") or {}
                pos = tr.get("position") or {}
                rot = tr.get("rotation") or {}
                plist.append({"facing": rot.get("y"), "isPipe": bool(pp.get("isPipe")),
                              "x": pos.get("x"), "y": pos.get("y"), "z": pos.get("z")})
            item[kind + "Ports"] = plist
            item[kind + "PortCount"] = len(plist)
        underground.append(item)

    # ---- _nop_ 免电变体对照 ----
    # 用途：写攻略时避免把 _nop_ 版叫成「免电XX」——官方名和原版一致。
    nop_variants = []
    for base_id, nop_id in NOP_PAIRS:
        base, nop = buildings_tbl.get(base_id), buildings_tbl.get(nop_id)
        if not base or not nop:
            continue
        nop_variants.append({
            "baseId": base_id,
            "baseName": T(base.get("name")),
            "basePower": base.get("powerConsume"),
            "nopId": nop_id,
            "nopName": T(nop.get("name")),
            "nopPower": nop.get("powerConsume"),
            "sameName": T(base.get("name")) == T(nop.get("name")),
            "note": ("官方名与原版相同，不叫「免电XX」"
                     if T(base.get("name")) == T(nop.get("name"))
                     else "官方名与原版不同"),
        })

    # ---- 蓝图系统规则 ----
    B = load("FacBlueprintConst") or {}
    blueprint_rules = {
        "shareCodePrefix": B.get("BlueprintShareCodePrefix"),
        "charSet": B.get("BlueprintCharSet"),
        "maxLenX": B.get("BluePrintXLenMax"),
        "maxLenZ": B.get("BluePrintZLenMax"),
        "nodeCountLimit": B.get("BlueprintNodeCountLimit"),
        "myBlueprintMax": B.get("MyBluePrintNumMax"),
        "giftBlueprintMax": B.get("GiftBluePrintNumMax"),
        "shareExpireSeconds": B.get("SharedBluePrintExpireTime"),
        "nameMaxLen": B.get("BlueprintNameMaxLen"),
        "descMaxLen": B.get("BlueprintDescMaxLen"),
        "tagMax": B.get("BluePrintTagNumMax"),
        "dailyReviewMax": B.get("BluePrintDailyReviewNumMax"),
    }

    return {
        "meta": {
            "note": "物流规则层。数值为游戏配置表原始值，未做二次假设。",
            "unitNote": "长度单位与游戏内一致；msPerRound 单位为毫秒。",
            "why": ("传送带/管道不是建筑，不在 FactoryBuildingTable 里，"
                    "而是独立的物流实体表（Grid=Liquid 前缀）。早期用 Conveyor/Belt/Pipe "
                    "关键词探测表名全部落空，实际命名用的是 Grid 与 Liquid。"),
        },
        "throughputSummary": [
            {"name": "传送带", "id": "grid_belt_01", "perSecond": 0.5, "perMinute": 30,
             "source": "FactoryGridBeltTable.msPerRound=2000"},
            {"name": "管道", "id": "log_pipe_01", "perSecond": 2.0, "perMinute": 120,
             "volume": 1, "source": "FactoryLiquidPipeTable.msPerRound=500, volume=1"},
        ],
        "entities": entities,
        "undergroundPipes": underground,
        "nopVariants": nop_variants,
        "buses": buses,
        "constants": constants,
        "constantsRaw": C,
        "powerPoles": poles,
        "miners": miners,
        "pumps": pumps,
        "fluidStoragers": storagers,
        "blueprintRules": blueprint_rules,
        "item2logistic": cap,
    }
