# -*- coding: utf-8 -*-
"""
把 data/ 下的 JSON 数据包内联进单文件 HTML，生成可双击打开的本地查询界面。
"""
import json
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "终末地基建查询.html")

FILES = [
    "meta.json", "buildings.json", "build_recipes.json", "machine_recipes.json",
    "manual_recipes.json", "items.json", "grow_cabin.json", "manufacture.json",
    "mechanics.json", "regions.json", "categories.json", "blueprint.json",
    "logistics.json", "rules.json", "bases.json", "recipe_groups.json", "mining_power.json",
]

bundle = {}
for f in FILES:
    p = os.path.join(DATA, f)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            bundle[f.replace(".json", "")] = json.load(fh)

# ⭐ 2026-09-21（博士反馈：「装什么东西显示不出来」）：瓶装液体 / 气罐类物品在配置表里
#    全是同一个名字 + 同一句描述（赤铜耐压罐 ×21），区别只在 id 后缀。
#    但配方表能反推：灌装配方的「液/气态输入」就是内容物；拆解配方反向印证；空容器也由此标记。
#    → 构建期给 items 加 content 字段（"装：水蒸气（气态）" / "空罐（可灌装）"），页面直接显示、可搜索。
_mrec = bundle.get("machine_recipes")
if isinstance(_mrec, dict):
    _mrec = _mrec.get("recipes") or list(_mrec.values())[0]
_content = {}
for _r in (_mrec or []):
    _rid = str(_r.get("id", ""))
    _ing = _r.get("ingredients") or []
    _out = _r.get("outcomes") or []
    _liq = [i for i in _ing if i.get("phaseType") in (2, 4)]
    _sol = [i for i in _ing if i.get("phaseType") == 1]
    if _r.get("machineName") == "灌装机" or _rid.startswith("filling_"):
        if _liq and _out:
            _c = "装：" + _liq[0]["name"] + "（" + str(_liq[0].get("phase") or "") + "）"
            for _o in _out:
                _content.setdefault(_o["id"], _c)
            for _s2 in _sol:
                _content.setdefault(_s2["id"], "空容器（可灌装）")
for _r in (_mrec or []):
    _rid = str(_r.get("id", ""))
    if not _rid.startswith("dismantler_"):
        continue
    _ing = _r.get("ingredients") or []
    _out = _r.get("outcomes") or []
    _liq = [o for o in _out if o.get("phaseType") in (2, 4)]
    _sol = [o for o in _out if o.get("phaseType") == 1]
    if _ing and _liq and _sol:
        _content.setdefault(_ing[0]["id"], "装：" + _liq[0]["name"] + "（" + str(_liq[0].get("phase") or "") + "）")
_n = 0
for _iid, _c in _content.items():
    if _iid in bundle.get("items", {}):
        bundle["items"][_iid]["content"] = _c
        _n += 1
print("content 字段注入", _n, "个物品")

# ⭐ v95 数据瘦身（博士：「数据会越来越多」）：注入层裁剪 —— data/*.json 保持完整底账不动，
#    只在打包进页面 DB 前丢掉**页面与测试均零引用**的字段。2026-09-22 五重验证：
#    直接引用 / 「input」+「Ports」类动态拼接 / Object.keys 遍历 / for-in 遍历 / test_html.js
#    断言引用 —— 五项全为 0。页面消费的接口数据来自 blueprint 的 ports（build.py 加工的精简版），
#    buildings 里的原始明细属于数据底账，页面上是死重。回滚 = 删掉这段。
_TRIM = {
    "buildings": ("inputPorts", "outputPorts", "inputEdges", "outputEdges", "edgeNames"),
    "blueprint_buildings": ("inputEdges", "outputEdges", "edgeNames"),
}
_ntrim = 0
for _k in ("buildings", "blueprint"):
    _arr = bundle.get(_k)
    if isinstance(_arr, dict):
        _arr = _arr.get("buildings")
    if not isinstance(_arr, list):
        continue
    _fields = _TRIM["buildings" if _k == "buildings" else "blueprint_buildings"]
    for _it in _arr:
        if isinstance(_it, dict):
            for _f in _fields:
                if _it.pop(_f, None) is not None:
                    _ntrim += 1
print("注入层裁剪死字段", _ntrim, "处（buildings/blueprint 的接口原始明细）")

# ⭐ v103 气体散布机（博士 2026-09-23：游戏里环境圈可见、圈色随通入的气体变）：
#    数据链两张表：FactoryVaporizerTable（rangeExtend 外扩格数 + 四种气体的消耗与 GenEnv 映射）
#    + FactoryEnvDisplayTable（GenEnv → 特效资源名里的颜色词）。
#    此前本地漏拉了 Vaporizer 表，2026-09-23 从数据域补拉（已存 raw/ 并记 _download_log）。
#    注入走 content 字段同一通道：只喂页面 DB，底账仍由 build.py 管。
_vap_p = os.path.join(ROOT, "raw", "FactoryVaporizerTable.json")
_env_p = os.path.join(ROOT, "raw", "FactoryEnvDisplayTable.json")
_bp = bundle.get("blueprint")
_bp_arr = _bp.get("buildings") if isinstance(_bp, dict) else None

# ⭐v110 版权隔离（博士 2026-09-23「版权风险最低的」）：
#    build_html.py 对 raw/ 的依赖全部收敛到 tools/bake_raw.py 的烘焙产物 data/raw_baked.json。
#    raw/ 是游戏解包 TableCfg，不上云、不进 git；云端/无 raw 的机器靠烘焙文件构建。
#    优先级：raw_baked.json（存在即用，不再读 raw）> raw/ 实时加工（本地兜底）> 跳过（两者皆无）。
_BAKED_P = os.path.join(DATA, "raw_baked.json")
_baked = None
if os.path.exists(_BAKED_P):
    with open(_BAKED_P, encoding="utf-8") as fh:
        _baked = json.load(fh)

if _baked and isinstance(_bp_arr, list):
    # ---- 路径 A：烘焙直用 ----
    _v1 = {"rangeExtend": _baked.get("vaporizer", {}).get("rangeExtend") or {}}
    _ngas = 0
    for _b in _bp_arr:
        if _b.get("id") == "vaporizer_1":
            _b["vaporizer"] = _baked.get("vaporizer") or {}
            _ngas = len(_b["vaporizer"].get("gasGroups") or [])
    _bp["envDisplay"] = _baked.get("envDisplay") or []
    bundle["recipeEnv"] = _baked.get("recipeEnv") or {}
    print("vaporizer 注入(烘焙): rangeExtend", json.dumps(_v1.get("rangeExtend")),
          "· 气体", _ngas, "种 · envDisplay", len(_bp["envDisplay"]),
          "条 · recipeEnv", len(bundle["recipeEnv"]), "条（环境依赖配方）")
elif isinstance(_bp_arr, list) and os.path.exists(_vap_p) and os.path.exists(_env_p):
    # ---- 路径 B：raw 实时加工（本地兜底，无烘焙文件时）----
    with open(_vap_p, encoding="utf-8") as fh:
        _vtab = json.load(fh)
    with open(_env_p, encoding="utf-8") as fh:
        _etab = json.load(fh)
    _env_list = []
    for _gid in sorted(_etab, key=lambda x: int(x)):
        _e = _etab[_gid]
        _eff = str(_e.get("EnvEffect", ""))
        _c = _eff.split("scope_")[1].split("_")[0] if "scope_" in _eff else "gray"
        _env_list.append({"id": int(_gid), "color": _c, "icon": str(_e.get("EnvIconAtlas", ""))})
    _GAS_NAMES = {"item_gas_inert": "惰气", "item_gas_water": "水蒸气",
                  "item_gas_acid": "酸气", "item_gas_xiranite": "息壤气"}
    _v1 = _vtab.get("vaporizer_1") or {}
    _ngas = 0
    for _b in _bp_arr:
        if _b.get("id") == "vaporizer_1":
            _b["vaporizer"] = {
                "rangeExtend": _v1.get("rangeExtend") or {},
                "gasGroups": [
                    {"item": g.get("consumeItem"),
                     "name": _GAS_NAMES.get(g.get("consumeItem"), str(g.get("consumeItem"))),
                     "rate": g.get("consumeRate"), "cap": g.get("consumeRateUpperLimit"),
                     "env": g.get("genEnv")}
                    for g in (_v1.get("groups") or [])
                ],
            }
            _ngas = len(_b["vaporizer"]["gasGroups"])
    _bp["envDisplay"] = _env_list
    # ⭐v104 环境依赖透明化：data/machine_recipes.json 打包时裁掉了 gasEnv 字段，
    #   这里从 raw 配方表补一份「配方 id → GenEnv」映射（仅非零的 5 条）进 DB.recipeEnv，
    #   供产线报告（哪些机器要摆进环境圈）与配方页标签使用。
    _mct_p = os.path.join(ROOT, "raw", "FactoryMachineCraftTable.json")
    _recipe_env = {}
    if os.path.exists(_mct_p):
        with open(_mct_p, encoding="utf-8") as fh:
            _mct = json.load(fh)
        for _rid, _r in _mct.items():
            _ge = _r.get("gasEnv") or 0
            if _ge:
                _recipe_env[_rid] = _ge
    bundle["recipeEnv"] = _recipe_env
    print("vaporizer 注入(raw): rangeExtend", json.dumps(_v1.get("rangeExtend")),
          "· 气体", _ngas, "种 · envDisplay", len(_env_list), "条 · recipeEnv", len(_recipe_env), "条（环境依赖配方）")
else:
    bundle["recipeEnv"] = {}
    print("⚠️ 无 raw/ 也无 data/raw_baked.json —— 环境圈与出货数据将为空，请跑 tools/bake_raw.py")

# ⭐v148 供电范围（博士 2026-09-24：「画布里供电桩也不显示供电范围，放的时候怎么确定设备在不在供电范围里」）：
#    FactoryPowerPoleTable 的 rangeExtend 与气体散布机**同字段、同口径**（外扩 N 格）：
#    供电桩/息壤供电桩（本体 2×2）±5 → 12×12；中继器/息壤中继器 ±2 → 7×7。
#    之前「配置表没有射程」的结论是错的 —— 当时只查了建筑表，没查这张杆件表。注入到蓝图建筑 powerPole 字段。
_pole_p = os.path.join(ROOT, "raw", "FactoryPowerPoleTable.json")
_n_pole = 0
if os.path.exists(_pole_p) and isinstance(_bp_arr, list):
    with open(_pole_p, encoding="utf-8") as fh:
        _ptab = json.load(fh)
    for _b in _bp_arr:
        _pp = _ptab.get(_b.get("id") or "")
        if _pp:
            _b["powerPole"] = {"rangeExtend": _pp.get("rangeExtend") or {},
                               "autoConnectLength": _pp.get("autoConnectLength")}
            _n_pole += 1
    print("powerPole 注入: %d 座（供电桩/息壤供电桩 12×12、中继器/息壤中继器 7×7 + 配线长）" % _n_pole)

# ⭐v109 协议核心出货（博士 2026-09-23：「游戏里的协议核心出货口可以点击选择物品出货」）：
#    数据在 FactoryItemTable —— deliverItemTypeList 非空 = 这件物品可以走协议核心出货，
#    值 [3,1] 的 1 / [3,2] 的 2 是**目标域序号**（1=四号谷地 domain_1、2=武陵 domain_2），
#    与 FactoryConst.domain2SpHubId(=map02_lv002_sp_hub_1) 对得上：一域一台协议核心。
#    实测 281 条可出货（与 deliver 物品数的 subType 分布一致）；其中 19 件不在 data/items.json
#    里（掉落物 / 测试件），名字从 raw/I18nTextTable_CN.json 按 name.id 反查补上，缺的退 id。
#    ⚠️ FactoryHubCraftTable 是「造建筑」配方，跟出货无关，别拿它当数据源（2026-09-23 已排除）。
_hub_domain = {"1": "domain_1", "2": "domain_2"}
_fit_p = os.path.join(ROOT, "raw", "FactoryItemTable.json")
_itn_p = os.path.join(ROOT, "raw", "I18nTextTable_CN.json")
_hub_items = {}
if _baked:  # ⭐v110：烘焙优先（见上），raw 全在本地不参与云端构建
    _hub_items = _baked.get("hubItems") or {}
    print("协议核心出货注入(烘焙):", len(_hub_items), "件可出货物品")
elif os.path.exists(_fit_p):
    with open(_fit_p, encoding="utf-8") as fh:
        _fit = json.load(fh)
    _itn = {}
    if os.path.exists(_itn_p):
        with open(_itn_p, encoding="utf-8") as fh:
            _itn = json.load(fh)
    _itab_p = os.path.join(ROOT, "raw", "ItemTable.json")
    _itab = {}
    if os.path.exists(_itab_p):
        with open(_itab_p, encoding="utf-8") as fh:
            _itab = json.load(fh)
    _items_db = bundle.get("items") or {}
    _noname = 0
    for _iid, _iv in _fit.items():
        _dl = _iv.get("deliverItemTypeList") or []
        if not _dl:
            continue
        _doms = []
        for _v in _dl:
            _d = _hub_domain.get(str(_v))
            if _d and _d not in _doms:
                _doms.append(_d)
        if not _doms:
            continue
        _nm = (_items_db.get(_iid) or {}).get("name")
        if not _nm:
            _nid = ((_itab.get(_iid) or {}).get("name") or {}).get("id")
            _nm = _itn.get(str(_nid)) if _nid is not None else None
            if not _nm:
                _nm = _iid
                _noname += 1
        _hub_items[_iid] = {
            "name": _nm,
            "rarity": ((_items_db.get(_iid) or {}).get("rarity")
                       or (_itab.get(_iid) or {}).get("rarity") or 1),
            "domains": _doms,
        }
    print("协议核心出货注入:", len(_hub_items), "件可出货物品 · 名字待补", _noname, "件")
bundle["hubItems"] = _hub_items
# 域 → 协议核心建筑 id（页面据此判「这台核心出什么」）；次级核心只进料不出货，不列。
bundle["hubDomainMachine"] = ( (_baked.get("hubDomainMachine") if _baked else None)
                              or {"domain_1": "sp_hub_1", "domain_2": "sp_hub_1"} )

payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"), indent=0)

# 把 payload 拆成多行。
# 起因：原本整份数据压成一行，最长一行 69 万字符。真实浏览器没问题，
# 但内嵌 webview（含本应用的预览面板）遇到这种超长单行会解析失败，
# 表现是页面只剩静态骨架、tab 和内容全空。
# 用 indent=0 让每个数组元素/对象成员独占一行：JSON 依然合法、体积只涨约 1%，
# 但最长行从 69 万降到几千，不会再触发上限。
payload = "\n".join(l.strip() for l in payload.split("\n"))

# ⚠️ 三引号必须是 raw（r"""），别改回普通 """。
#    这是**防御性**的，理由说清楚：
#    - 现状：模板里的 JS 代码只有 3 处反斜杠（/https?:\/\/\S+/ 里的 \/ 和 \S）。普通三引号下
#      Python 会把它们当"无效转义"、原样保留，产物字节不变，但每次都报 SyntaxWarning。
#    - 真正的危险：以后再往 JS 里写 \n / \b / \d 这类**有效**转义时，普通三引号会当场把它们
#      变成真换行 / 退格符 —— 前者让字符串断行、后者静默改变正则语义，产物直接坏掉。
#      早先为此改用过 String.fromCharCode(10) 绕开，现在用 raw 字符串根治。
#    - 数据不受影响：模板里的数据是 __PAYLOAD__ 占位符、运行时才替换，
#      所以数据里那 75 处 \n（游戏文案里的换行）跟这个三引号没关系。
#    改模板注意两点：内容里不能出现连续三个双引号；结尾不能是反斜杠。
#
#    输出用 newline="\n"（LF）：线上托管产物是纯 LF，不写死的话 Windows 会转成 CRLF，
#    跟线上比对时到处是假差异。
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta content="width=device-width, initial-scale=1.0" name="viewport">
<title>终末地基建知识库 · 1.5.3</title>
<style>
:root{
  --bg:#FAFAF7; --panel:#FFFFFF; --line:#E4E2D9; --line2:#D3D1C7;
  --ink:#23231F; --ink2:#5E5D55; --ink3:#8A897F;
  --accent:#0F6E56; --accent-bg:#E1F5EE; --accent-line:#B8E2D4;
  --warn:#9A5B1E; --warn-bg:#FBF0E0;
  --chip:#F2F1EA;
  --radius:8px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--bg); color:var(--ink);
  font-family:-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;
  font-size:14px; line-height:1.6; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 60px}

/* ---- header ---- */
header{border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:50}
.hd{max-width:1180px;margin:0 auto;padding:16px 20px 0}
.hd-top{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
h1{font-size:19px;font-weight:650;letter-spacing:.2px}
.ver{font-size:12px;color:var(--ink3);font-variant-numeric:tabular-nums}
.hd-meta{font-size:11.5px;color:var(--ink3);margin-top:3px}
nav{display:flex;gap:2px;margin-top:14px;overflow-x:auto}
nav button{
  background:none;border:none;border-bottom:2px solid transparent;
  padding:9px 15px;font-size:13.5px;color:var(--ink2);cursor:pointer;
  font-family:inherit;white-space:nowrap;border-radius:6px 6px 0 0;transition:.12s;
}
nav button:hover{background:var(--chip);color:var(--ink)}
nav button.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}

/* ---- 布局试摆（交互画布） ---- */
.lo-wrap{position:relative}
/* 画布区：格子放大后画布会超过容器宽度，这里兜一层横向滚动 */
.lo-stage{min-width:0;max-width:100%;overflow:auto}
.lo-bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
/* ⭐v144 建筑清单 = 画布左侧的浮层侧栏。**绝对定位脱离文档流** → 无论收起还是展开，
   画布的位置与宽度都完全不变（曾试过 flex 定宽栏：展开时把画布推右 260px，博士当即否掉 ——「画布又被挪了」）。
   宽度由 LpalFit() 按 #out 左边的实际空白自适应（上限 246，收起见 CSS 的 34）。 */
.lo-pal{position:absolute;top:0;right:100%;margin-right:12px;width:246px;
  max-height:620px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:8px;background:var(--panel)}
.lo-pal.folded{width:34px;padding:6px 0;overflow:hidden;
  background:var(--accent-bg);border-color:var(--accent-line)}
.lo-pal.folded .lo-pal-tab{writing-mode:vertical-rl;letter-spacing:3px;width:100%;padding:12px 0;
  border:none;background:none;cursor:pointer;font-family:inherit;font-size:12px;
  font-weight:600;color:var(--accent)}
/* ⭐v145 多基地页签：一个地区 4 片基地各一个页签，点着切换；一次只渲染当前这片（与单画布同量级）。
   同屏看不到别片布局的短板由页签上的**摘要**补偿。 */
.lo-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 0}
.lo-tab{display:flex;flex-direction:column;align-items:flex-start;gap:1px;padding:5px 10px;
  border:1px solid var(--line2);border-radius:8px;background:var(--panel);cursor:pointer;
  font-family:inherit;font-size:12px;color:var(--ink2);text-align:left;line-height:1.45}
.lo-tab:hover{background:var(--chip)}
.lo-tab.on{background:var(--accent-bg);border-color:var(--accent-line);color:var(--accent);font-weight:600}
.lo-tabsm{font-size:10.5px;color:var(--ink3);font-weight:400}
/* ⭐v145 容量超上限：标红（容量比面积更早到顶，超了就是建不了） */
.lo-tabover{color:#C0392B;font-weight:600}
.lo-tab.on .lo-tabsm{color:var(--accent)}
.lo-btn{display:flex;align-items:center;gap:8px;width:100%;text-align:left;background:none;border:1px solid transparent;border-radius:6px;padding:5px 8px;cursor:pointer;font-family:inherit;font-size:12.5px;color:var(--ink)}
.lo-btn:hover{background:var(--chip)}
.lo-btn.sel{background:var(--accent-bg);border-color:var(--accent-line);color:var(--accent);font-weight:600}
.lo-tag{font-size:10.5px;color:var(--ink3);white-space:nowrap}
.lo-size{padding:5px 12px;border:1px solid var(--line2);border-radius:20px;background:var(--panel);color:var(--ink2);cursor:pointer;font-family:inherit;font-size:12.5px}
.lo-size.on{background:var(--accent-bg);border-color:var(--accent-line);color:var(--accent);font-weight:600}
/* 网格间距 = 格子边长的 CSS 变量 --locell（由 renderLayout 按当前档位写入），
   和 JS 里的 LOCELL 是同一个数 —— 两处不一致就会出现「图标压在格线外」的错位。 */
/* 画布外套一层：给「谷地预设存取线」那条外缘带子留位置。
   ⚠️ .lo-stage 是滚动容器，**上/左方向的溢出滚不到**（会被直接裁掉），所以必须靠 padding 把空间让出来。 */
.lo-canv{display:inline-block}
.lo-canvas{position:relative;background:#FBFAF6;border:1px solid var(--line);border-radius:8px;overflow:visible;cursor:crosshair;background-image:linear-gradient(#E7E5DC 1px,transparent 1px),linear-gradient(90deg,#E7E5DC 1px,transparent 1px);background-size:var(--locell,20px) var(--locell,20px)}
/* ⚠️ 上面必须是 overflow:visible：谷地预设存取线整条画在画布框**外面**（贴外缘、不占格），
   一旦 overflow:hidden 就整条被裁 —— 和当年「接口标记看不见」是同一个坑。 */
/* 谷地预设存取线（四号谷地：基地升级后自动铺在基地外侧边缘，玩家不用摆）。
   颜色沿用数据里的分类色：仓储存取 #A9C7C2；源桩用核心结构的 #C98A5E —— 与基地面积页那张示意图一致。 */
.lo-pre{position:absolute;background:#A9C7C2;border:1px solid #7FA8A2;border-radius:2px;pointer-events:none;z-index:0}
.lo-pre-h{background-image:repeating-linear-gradient(90deg,rgba(255,255,255,.5) 0 1px,transparent 1px var(--locell,20px))}
.lo-pre-v{background-image:repeating-linear-gradient(180deg,rgba(255,255,255,.5) 0 1px,transparent 1px var(--locell,20px))}
.lo-pre-src{background:#C98A5E;background-image:none;border-color:#9C6742}
/* ⭐v103→v104 气体散布机环境圈：半透明方形色块 + 同色格线。颜色/浓度经 CSS 变量从 JS 传
   （--envbg 填充 / --envline 线框与格线 / --envop 浓度 —— 白圈(湿润)单独给高浓度，不然在浅画布上看不见）。
   pointer-events:none —— 不挡点击 / 框选 / 摆放（游戏里范围圈也不挡）。z-index:0 与预设线同层，在建筑（DOM 在后）之下。 */
.lo-pwr{position:absolute;pointer-events:none;z-index:0;border-radius:2px;
  background:#B9A8E8;border:1px dashed #7F77DD;opacity:.16}
.lo-pwr-pre{opacity:.24;border-style:solid;z-index:5}
.lo-env{position:absolute;pointer-events:none;z-index:0;border-radius:2px;opacity:var(--envop,.17);
  background-color:var(--envbg,#3D9FD8);
  box-shadow:inset 0 0 0 1px var(--envline,#1B6E9E);
  background-image:linear-gradient(var(--envline,#1B6E9E) 1px,transparent 1px),linear-gradient(90deg,var(--envline,#1B6E9E) 1px,transparent 1px);
  background-size:var(--locell,20px) var(--locell,20px);background-position:-1px -1px}
/* ⭐v104 就地选气条：点选散布机后浮在机器正上方（博士：「想要点机器就地选」）。
   跟随画布坐标（随格子大小/移动/撤销一起重渲染）；z-index 压过建筑层，只占一行高度。 */
.lo-gasbar{position:absolute;z-index:5;display:flex;align-items:center;gap:4px;
  background:#FFFDF9;border:1px solid var(--line2);border-radius:6px;padding:3px 6px;
  box-shadow:0 1px 4px rgba(60,50,30,.18);pointer-events:auto;white-space:nowrap}
.lo-gasbar b{font-size:11px;color:var(--ink2)}
.lo-gasbar button{width:18px;height:18px;border-radius:4px;border:1.5px solid;cursor:pointer;padding:0}
.lo-gasbar button.on{outline:2px solid var(--accent);outline-offset:1px}
/* ⭐v109 协议核心出货：出料口格**内侧**的指向箭头（博士：「内部空白面积大，选货在内部给个
   机器口对应的箭头」）。贴在口格靠里一侧、朝外指；点它开物品清单。hitbox 撑到 16px。 */
.lo-dlv{position:absolute;z-index:4;width:12px;height:12px;transform:translate(-50%,-50%);
  display:flex;align-items:center;justify-content:center;cursor:pointer;border-radius:3px;
  color:#C0561F;background:rgba(255,253,249,.9);box-shadow:0 0 0 1px rgba(192,86,31,.5)}
.lo-dlv:hover{background:#FFF1E6;box-shadow:0 0 0 1px var(--accent),0 0 0 3px rgba(192,86,31,.18)}
.lo-dlv svg{width:9px;height:9px;display:block}
.lo-dlv.set{color:#0F6E56;background:rgba(233,248,241,.92);box-shadow:0 0 0 1px rgba(15,110,86,.5)}
.lo-dlv.set:hover{box-shadow:0 0 0 1px #0F6E56,0 0 0 3px rgba(15,110,86,.18)}
/* 选中的出货物品名：贴箭头旁边，小字、不挡格 */
.lo-dlvt{position:absolute;z-index:4;transform:translate(-50%,-50%);pointer-events:none;
  font-size:10px;line-height:1.1;padding:1px 3px;border-radius:3px;white-space:nowrap;
  color:#0F5B47;background:rgba(233,248,241,.94);box-shadow:0 0 0 1px rgba(15,110,86,.28);max-width:96px;
  overflow:hidden;text-overflow:ellipsis}
/* 出货物品清单浮层：点箭头弹出，浮在机器上方 */
.lo-dlvpop{position:absolute;z-index:9;width:230px;max-height:262px;overflow:auto;
  background:#FFFDF9;border:1px solid var(--line2);border-radius:8px;padding:6px;
  box-shadow:0 4px 14px rgba(60,50,30,.22)}
.lo-dlvpop .hd{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--ink2);
  padding:1px 2px 5px;border-bottom:1px solid var(--line2);margin-bottom:5px;position:sticky;top:-6px;
  background:#FFFDF9;border-radius:6px 6px 0 0}
.lo-dlvpop .hd b{color:var(--ink)}
.lo-dlvpop .hd .x{margin-left:auto;cursor:pointer;color:var(--ink3);padding:0 3px;font-size:13px;line-height:1}
.lo-dlvpop .hd .x:hover{color:var(--ink)}
.lo-dlvpop .it{display:flex;align-items:center;gap:6px;padding:3px 5px;border-radius:5px;
  cursor:pointer;font-size:12px}
.lo-dlvpop .it:hover{background:var(--accent-bg)}
.lo-dlvpop .it.on{background:#E9F8F1;box-shadow:inset 0 0 0 1px rgba(15,110,86,.32)}
.lo-dlvpop .it .rr{font-size:10px;color:#C9A227;letter-spacing:-1px;flex:none;width:34px}
.lo-dlvpop .it .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ⭐v139 准入口合规标红：孤立的准入口（四周没有同类带/管衔接）= 没放在传送带/管道上 */
/* ⭐v140 标红加强：纯红粗描边 + 左上角「!」角标 —— 之前用橙红，与准入口本身的橙色描边撞车看不清 */
.lo-cell.vbad{box-shadow:inset 0 0 0 3px #E01B24, 0 0 0 2px #E01B24;z-index:3}
.lo-cell.vbad::before{content:'!';position:absolute;left:0;top:0;width:11px;height:11px;
  background:#E01B24;color:#fff;font-size:9px;font-weight:700;line-height:11px;text-align:center;
  border-radius:0 0 6px 0;z-index:4}
/* ⭐v135 机器选择浮层（点机器就地选）：复用出货浮层样式，但内容更高，给个高度上限 */
.lo-macpop{width:auto;max-height:430px;overflow:auto}
/* ⭐v134 反应池缓存格：物品卡（星级 + 名字 + 相态角标）——视觉与协议核心出货清单同一套语言 */
.lo-ccells{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.lo-ccell{position:relative;width:80px;height:46px;border:1px solid #B4B2A9;border-radius:6px;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  padding:3px 4px 2px;box-sizing:border-box;background:#fff;overflow:hidden}
.lo-ccell.empty{opacity:.38;font-size:11px;color:#888780}
.lo-ccell.over{border-color:#C0561F;box-shadow:inset 0 0 0 1px rgba(192,86,31,.3)}
.lo-ccell .rr{font-size:9px;color:#C9A227;letter-spacing:-1px;line-height:1}
.lo-ccell .nm{font-size:11px;line-height:1.15;text-align:center;word-break:break-all;max-height:26px;overflow:hidden}
.lo-ccell .ph{position:absolute;right:2px;top:2px;color:#fff;font-size:9px;border-radius:3px;
  padding:0 3px;line-height:1.35}
.lo-dlvpop .it .cc{color:var(--ink3);font-size:10px}
.lo-dlvpop .it .ck{color:#0F6E56;flex:none;font-size:11px}
.lo-dlvpop .em{font-size:11.5px;color:var(--ink3);padding:6px 4px}
/* ⭐v126 选货浮层筛选工具条：搜索框 + 稀有度 chip + 计数（博士「东西几百个太多了」） */
.lo-dlvpop .ft{display:flex;align-items:center;gap:4px;flex-wrap:wrap;padding:0 2px 5px;
  border-bottom:1px solid var(--line2);margin-bottom:5px}
.lo-dlvpop .ft .dlvq{flex:1;min-width:0;font-size:11.5px;padding:2px 6px;
  border:1px solid var(--line2);border-radius:5px;background:#FFF;color:var(--ink)}
.lo-dlvpop .ft input:focus{outline:none;border-color:#0F6E56}
.lo-dlvpop .ft .cbtn{font-size:10.5px;padding:1px 6px;border-radius:9px;flex:none;
  border:1px solid var(--line2);background:#FFF;color:var(--ink2);cursor:pointer}
.lo-dlvpop .ft .cbtn.on{background:#0F6E56;border-color:#0F6E56;color:#FFF}
.lo-dlvpop .ft .ct{font-size:10.5px;color:var(--ink3);flex:none;margin-left:auto;white-space:nowrap}
.lo-dlvpop .lo-dlvplist{display:block}
/* 配方选择块（选中生产设施时出现在左栏顶部） */
.lo-rp{border:1px solid var(--accent-line);background:var(--accent-bg);border-radius:8px;padding:8px;margin-bottom:8px}
.lo-rp select{width:100%}
/* 评价函数 / 方案并排比较（2026-09-21 晚 · 路线图 ①②） */
.lo-score{border:1px solid var(--line2);background:var(--panel);border-radius:8px;padding:8px;margin:8px 0 4px}
.lo-scv{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;margin:2px 0 6px}
.lo-scn{font-size:26px;font-weight:700;color:var(--accent);line-height:1}
.lo-scs{font-size:12px;color:var(--ink3)}
.lo-bar-o{display:inline-block;width:56px;height:7px;background:var(--line2);border-radius:4px;vertical-align:middle;margin-left:6px;overflow:hidden}
.lo-bar-i{display:block;height:7px;border-radius:4px}
.lo-cmp{border:1px solid var(--line2);background:var(--panel);border-radius:8px;padding:8px;margin-top:10px}
.lo-tb{width:100%;border-collapse:collapse;font-size:11.5px}
.lo-tb td{border:1px solid var(--line2);padding:3px 6px;vertical-align:top}
.lo-td-h{color:var(--ink3);white-space:nowrap}
.lo-best{color:var(--accent)}
.lo-x{background:none;border:none;color:var(--ink3);cursor:pointer;font-family:inherit;font-size:12px;padding:0 3px;margin-left:4px}
.lo-x:hover{color:#C0392B}
/* 设施上标出的产出物品名（选了配方才有）—— 布局图上一眼看出这台在做什么 */
.lo-prod{font-size:calc(var(--locell,20px) * .5);font-weight:600;color:#8A5A2B;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
/* 接口按配方分「走 / 不走」：走的加亮圈，不走的淡下去 */
.lo-port.off{opacity:.28}
.lo-port.use{box-shadow:0 0 0 1px #fff,0 0 0 2.5px #2E8B9E}
/* 产线闭环（排布器）的输入控件与报告 */
.lo-num{width:76px;padding:5px 8px;border:1px solid var(--line2);border-radius:6px;background:var(--panel);color:var(--ink);font-family:inherit;font-size:12.5px}
/* ⑥-1 收货物选择网格（2026-09-22 博士：「像游戏里那样给我个传输物品的选择器」）——
   候选卡片（稀有度色条 + 名 + 数字）点选切换；选中态沿用 .lo-btn.sel 的 accent 范式，主题自适应 */
.lo-pickgrid{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 4px}
.lo-pickcard{position:relative;min-width:150px;border:1px solid var(--line2);border-left-width:4px;border-radius:8px;background:var(--panel);padding:5px 10px 6px;cursor:pointer;font-family:inherit;text-align:left;transition:.12s;color:var(--ink)}
.lo-pickcard:hover{background:var(--chip)}
.lo-pickcard.on{border-color:var(--accent-line);background:var(--accent-bg)}
.lo-pickck{position:absolute;top:3px;right:8px;font-size:12px;font-weight:700;color:var(--accent);display:none}
.lo-pickcard.on .lo-pickck{display:inline}
.lo-picknm{display:block;font-size:13px;font-weight:650;color:var(--ink);padding-right:14px}
.lo-pickcard.on .lo-picknm{color:var(--accent)}
.lo-pickmeta{display:block;font-size:11px;color:var(--ink2);margin-top:2px;line-height:1.5}
/* ⭐v82 全库折叠区：滚动容器 + 折叠摘要（游戏里就是一份长列表，全平铺会把面板撑爆） */
.lo-pickscroll{max-height:300px;overflow-y:auto;margin-top:4px;padding-right:2px}
.lo-pickfold summary{user-select:none;line-height:1.6}
.lo-plan{border-color:var(--line2);background:var(--panel)}
.lo-plan .c-sub span{white-space:normal}
.lo-cell{position:absolute;border:1.5px solid var(--accent);background:rgba(15,110,86,.10);border-radius:3px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--accent);overflow:visible}
/* ⚠️ 上面必须是 overflow:visible，别改回 hidden。
   接口标记是压在**格线上**的（一半在建筑里、一半挑出去），一旦父级 clip，标记会被裁成贴着边框的
   一两条细线 —— 就是 2026-09-21 博士报的「物品进出口看不见」。名字自己带省略号，不靠父级裁。 */
/* 字形/名字字号跟着格子等比走：14px 格时就是原来的 13px / 8px，放大格子后不会显得空。 */
.lo-glyph{font-size:calc(var(--locell,20px) * .93);line-height:1;font-weight:600}
.lo-name{font-size:calc(var(--locell,20px) * .57);color:var(--ink2);font-weight:400;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
/* 接口标记：贴在建筑**内侧**、紧挨边框画（不是压格线）。
   为什么要贴内侧：压格线时标记有一半伸到邻格里，一旦邻格放了传送带/管道就会互相压字（博士 2026-09-21 指出）。
   贴内侧后标记外沿离自己的边框只有 0.5px、离邻格还有 2.5px 以上，任何情况下都不会重叠。
   颜色/形状不变：青=进料、橙=出料；方=传送带口、圆=管道口。 */
.lo-port{position:absolute;width:7px;height:7px;border-radius:1px;transform:translate(-50%,-50%);box-shadow:0 0 0 1px #fff;z-index:3}
.lo-port.pipe{border-radius:50%}
/* 已接：正对外侧那格放着同类物流件（传送带口↔传送带、管道口↔管道） */
.lo-port.on{box-shadow:0 0 0 1px #fff,0 0 0 3px rgba(15,110,86,.32)}
/* 物流件（1×1 可摆放件）：带系=方角青，管系=圆角紫 */
.lo-cell.lgb{border-color:#2E8B9E;background:rgba(46,139,158,.16);color:#186C7D;z-index:1}
.lo-cell.lgp{border-color:#7B62C9;background:rgba(123,98,201,.16);color:#5A46A6;z-index:2}
/* 物流件的接口图（进/出边 + 功能字形或流向箭头）自己画成 SVG，铺满格内 */
.lo-cell > svg{position:absolute;left:0;top:0;width:100%;height:100%;display:block;overflow:visible}
/* 选中态（框选/单选共用）：暖色描边，和默认的墨绿区分开 */
.lo-cell.sel{border-color:var(--warn);background:rgba(154,91,30,.13);color:var(--warn);box-shadow:0 0 0 2px rgba(154,91,30,.22)}
/* 存取线未连接：跟游戏一样标红（博士 2026-09-21 实拍：游戏把没连上的预览块变红并提示）。
   写在 .sel 之后 —— 未连接比"选中"更该被看见。 */
.lo-cell.bad{border:2px dashed #C0392B;background:repeating-linear-gradient(45deg,rgba(192,57,43,.16) 0 6px,rgba(192,57,43,.36) 6px 12px);color:#8E2418}
/* ⚠️ 选中态（.sel）是橙色，未连接（.bad）必须是与之拉开距离的斜纹红 ——
   博士曾把"刚摆完还在选中态"的橙色误读成"没接上的红"。别把两者改成相近的颜色。 */
/* 局部锁定（路线图 ⑤-1）：锁 =「这台我满意了，别动它」。
   双线铁灰描边 + 右上角小锁，和选中（橙）/未连接（红）都区分得开。 */
.lo-cell.lock{border-style:double;border-width:3px;border-color:#4A5560;box-shadow:0 0 0 1px rgba(74,85,96,.22)}
.lo-cell.lock::after{content:'🔒';position:absolute;right:1px;top:0;line-height:1;pointer-events:none;font-size:calc(var(--locell,20px) * .45)}
.lo-sel{padding:3px 8px;border:1px solid var(--line2);border-radius:6px;background:var(--panel);color:var(--ink);font-family:inherit;font-size:12px;max-width:160px}
/* 谷地存取线示意图：粗条 = 自动铺设的存取线，角上的方块 = 源桩 */
.bus-bar{fill:#A9C7C2}
.bus-src{fill:#C98A5E}
/* 框选拖拽中的橡皮筋矩形 */
.lo-band{position:absolute;border:1.5px dashed var(--warn);background:rgba(154,91,30,.08);border-radius:3px;pointer-events:none}
.lo-sep{width:1px;height:18px;background:var(--line2);margin:0 2px}
.lo-size.off{opacity:.45}
.lo-msg{color:var(--warn);font-weight:550}
.lo-msg:empty{display:none}
/* 左栏顶部：说明默认列了哪几类 */
.lo-ph{font-size:11.5px;color:var(--ink3);padding:1px 2px 8px;line-height:1.65;border-bottom:1px solid var(--line);margin-bottom:6px}
.lo-ph b{color:var(--ink2)}
.lo-reset{background:none;border:none;color:var(--accent);cursor:pointer;font-family:inherit;font-size:11.5px;padding:0 2px;text-decoration:underline}
/* 接口 / 物流件图例 */
.lo-legend{display:flex;gap:14px;flex-wrap:wrap;align-items:center;font-size:11.5px;color:var(--ink3);margin:0 0 10px}
.lo-legend span{display:inline-flex;align-items:center;gap:4px}
.lo-legend i{display:inline-block;width:8px;height:8px;border-radius:1px}
.lo-legend i.pipe{border-radius:50%}
.lo-legend i.inp{background:#186C7D}
.lo-legend i.outp{background:#C0561F}
.lo-legend i.bg{background:#2E8B9E}
.lo-legend i.pg{background:#7B62C9;border-radius:50%}

/* ---- controls ---- */
.bar{display:flex;gap:10px;margin:22px 0 16px;flex-wrap:wrap;align-items:center}
input[type=search],select{
  font-family:inherit;font-size:13.5px;padding:9px 13px;border:1px solid var(--line2);
  border-radius:var(--radius);background:var(--panel);color:var(--ink);outline:none;
}
input[type=search]{flex:1;min-width:220px}
input[type=search]:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}
.count{font-size:12.5px;color:var(--ink3);margin-left:auto;font-variant-numeric:tabular-nums}

/* ---- cards ---- */
.list{display:flex;flex-direction:column;gap:9px}
.card{
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:14px 16px;cursor:pointer;transition:.12s;
}
.card:hover{border-color:var(--accent-line);box-shadow:0 1px 6px rgba(15,110,86,.07)}
.card.open{border-color:var(--accent-line);box-shadow:0 2px 12px rgba(15,110,86,.09)}
.c-top{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.c-name{font-size:15px;font-weight:600}
.c-id{font-size:11.5px;color:var(--ink3);font-family:ui-monospace,Consolas,monospace}
.c-cat{
  font-size:11px;padding:2px 8px;border-radius:20px;background:var(--chip);
  color:var(--ink2);white-space:nowrap;
}
.c-cat.acc{background:var(--accent-bg);color:var(--accent)}
.spacer{flex:1}
.c-sub{font-size:12.5px;color:var(--ink2);margin-top:6px;display:flex;gap:14px;flex-wrap:wrap}
.c-desc{font-size:12.5px;color:var(--ink2);margin-top:8px;white-space:pre-wrap;line-height:1.7}
.star{
  font-size:12.5px;margin-top:8px;padding:7px 11px;background:var(--accent-bg);
  border-left:2.5px solid var(--accent);border-radius:0 5px 5px 0;color:var(--accent);
  font-weight:550;
}
.flag{font-size:11px;padding:2px 8px;border-radius:20px;background:var(--warn-bg);color:var(--warn);white-space:nowrap}

/* detail */
.detail{margin-top:14px;padding-top:13px;border-top:1px dashed var(--line)}
.d-sec{margin-top:12px}
.d-sec:first-child{margin-top:0}
.d-h{
  font-size:11.5px;color:var(--ink3);letter-spacing:.6px;margin-bottom:7px;
  text-transform:uppercase;font-weight:600;
}
.row{display:flex;gap:9px;align-items:baseline;padding:5px 0;font-size:12.5px;flex-wrap:wrap}
.row+.row{border-top:1px solid #F2F1EA}
.tag{font-size:11px;padding:2px 7px;border-radius:4px;background:var(--chip);color:var(--ink2);white-space:nowrap}
.tag.acc{background:var(--accent-bg);color:var(--accent)}
.arrow{color:var(--ink3);font-size:12px}
.formula{
  display:flex;gap:10px;align-items:center;flex-wrap:wrap;
  background:#FBFAF6;border:1px solid var(--line);border-radius:6px;padding:9px 12px;margin-top:6px;
}
.chain{font-size:12.5px;color:var(--ink2)}
.chain b{color:var(--ink);font-weight:600}
.empty{text-align:center;padding:50px 20px;color:var(--ink3);font-size:13.5px}

/* ---- 占地蓝图 ---- */
pre.grid{
  background:#FBFAF6;border:1px solid var(--line);border-radius:6px;
  padding:12px 14px;margin-top:7px;overflow-x:auto;
  font-family:ui-monospace,Consolas,"Cascadia Mono",monospace;
  font-size:12px;line-height:1.55;color:var(--ink);white-space:pre;
}
code{
  font-family:ui-monospace,Consolas,monospace;font-size:11.5px;
  background:var(--chip);padding:1px 5px;border-radius:3px;color:#7A4A12;
}

/* ---- 物流规则 ---- */
.lg-caps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:6px}
.lg-cap{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
.lg-cap-n{font-size:12.5px;color:var(--ink2);font-weight:600}
.lg-cap-v{font-size:24px;font-weight:650;color:var(--accent);line-height:1.25;font-variant-numeric:tabular-nums}
.lg-cap-v span{font-size:12px;font-weight:400;color:var(--ink3)}
.lg-cap-v2{font-size:12.5px;color:var(--ink2);font-variant-numeric:tabular-nums}
.lg-cap-s{font-size:11px;color:var(--ink3);margin-top:6px;font-family:ui-monospace,Consolas,monospace}
/* 概览卡（大数字 + 小标签），玩法规则页顶部用 */
.lg-capn{font-size:26px;font-weight:650;color:var(--accent);line-height:1.25;font-variant-numeric:tabular-nums}
.lg-capl{font-size:12.5px;color:var(--ink2);margin-top:2px}
.lg-ent{border-bottom:1px solid var(--line);padding:11px 2px}
.lg-ent:last-child{border-bottom:none}
.lg-ent-a{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.lg-ent-a b{font-size:14px;font-weight:600}
.lg-tag{font-size:11px;padding:1px 7px;border-radius:10px;background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-line)}
.lg-tag.pipe{background:#E8F0FB;color:#2B5B9E;border-color:#C4D8F2}
.lg-cat{font-size:11.5px;color:var(--ink3)}
.lg-ent-b{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2);margin-top:5px;font-variant-numeric:tabular-nums}
.lg-ent-b b{color:var(--ink);font-weight:600}
.lg-tb{width:100%;border-collapse:collapse;margin-top:7px;font-size:12.5px}
.lg-tb th{
  text-align:left;font-weight:600;color:var(--ink3);font-size:11.5px;
  padding:6px 8px;border-bottom:1px solid var(--line2);white-space:nowrap;
}
.lg-tb td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.lg-tb tr:last-child td{border-bottom:none}
.lg-tb .r{text-align:right;font-variant-numeric:tabular-nums}
.lg-tb td.u{color:var(--ink3);font-size:11.5px}
.lg-tb tbody tr:hover{background:#FBFAF6}
.lg-tb .same{color:var(--warn)}
.lg-tb td code{font-size:11px}

/* ---- 玩法规则 ---- */
.rl-note{margin:14px 0 18px;padding:12px 14px;background:#FFFDF5;border:1px solid var(--line2);
  border-left:3px solid var(--warn);border-radius:6px;font-size:12.5px;line-height:1.85;color:var(--ink2)}
.rl-card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:16px}
.rl-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:10px}
.rl-title{font-size:14.5px;font-weight:600;color:var(--ink);flex:1;min-width:220px}
.rl-tag{font-size:11px;padding:2.5px 8px;border-radius:4px;font-weight:600;white-space:nowrap;
  background:#EAF3EC;color:#2C6B45;border:1px solid #C9E2D2}
.rl-tag.warn{background:#FFF3E4;color:#9A5A12;border-color:#F0D6AE}
.rl-verdict{font-size:11.5px;padding:2.5px 9px;border-radius:11px;white-space:nowrap;
  background:#EAF3EC;color:#2C6B45;border:1px solid #C9E2D2}
.rl-verdict.warn{background:#FFF3E4;color:#9A5A12;border-color:#F0D6AE}
.rl-detail{font-size:12.5px;line-height:1.9;color:var(--ink2);margin:7px 0}
.rl-caveat{margin:9px 0;padding:9px 12px;background:#FFF8F0;border-left:3px solid #D99B4A;
  border-radius:5px;font-size:12px;line-height:1.85;color:#8A5A20}
.rl-sub{margin:16px 0 6px;font-size:12.5px;font-weight:600;color:var(--ink);
  padding-left:8px;border-left:3px solid var(--accent)}
.rl-cfg{margin:8px 0;padding:9px 12px;background:#FAF9F5;border:1px solid var(--line);border-radius:6px;font-size:12px;line-height:1.8;color:var(--ink2)}
.rl-ev{margin:10px 0 4px;border:1px solid var(--line);border-radius:6px;background:#FCFBF8}
.rl-ev>summary{cursor:pointer;padding:8px 12px;font-size:12px;color:var(--ink3);font-weight:600;list-style:none}
.rl-ev>summary::-webkit-details-marker{display:none}
.rl-ev>summary:before{content:'▸ ';color:var(--accent)}
.rl-ev[open]>summary:before{content:'▾ '}
.rl-evbody{padding:2px 12px 10px}
/* v101：布局试摆帮助块折叠 —— 整块黄区默认收起，summary 常显标题行 */
details.lo-help>summary{cursor:pointer;user-select:none;list-style:none;margin:-2px 0 4px}
details.lo-help>summary::-webkit-details-marker{display:none}
details.lo-help>summary:before{content:'▸ ';color:var(--accent)}
details.lo-help[open]>summary:before{content:'▾ '}
.rl-evrow{display:flex;gap:10px;align-items:flex-start;padding:5px 0;border-top:1px dashed var(--line2);font-size:12px;line-height:1.75;color:var(--ink2)}
.rl-src{flex:0 0 auto;font-family:ui-monospace,Consolas,monospace;font-size:10.5px;color:#6B7A8F;
  background:#EFF2F6;padding:1.5px 6px;border-radius:3px;white-space:nowrap;margin-top:1px}

/* overview */
.ov-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}
.ov-card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:15px 17px}
.ov-num{font-size:26px;font-weight:650;color:var(--accent);font-variant-numeric:tabular-nums;line-height:1.25}
.ov-lbl{font-size:12.5px;color:var(--ink2);margin-top:2px}
.note{
  background:var(--warn-bg);border:1px solid #EFDCC2;border-left:3px solid var(--warn);
  border-radius:0 var(--radius) var(--radius) 0;padding:13px 16px;font-size:12.5px;
  color:#6E4315;margin-bottom:18px;line-height:1.75;
}
.note b{color:var(--warn)}
footer{font-size:11.5px;color:var(--ink3);margin-top:36px;padding-top:18px;border-top:1px solid var(--line);line-height:1.8}
@media(max-width:640px){
  .wrap{padding:0 14px 40px}
  .hd{padding:14px 14px 0}
  h1{font-size:17px}
  .c-sub{gap:10px}
  nav button{padding:9px 11px;font-size:13px}
}
</style>
</head>
<body>
<header>
  <div class="hd">
    <div class="hd-top">
      <h1>终末地基建知识库</h1>
      <span class="ver" id="ver"></span>
    </div>
    <div class="hd-meta" id="hdmeta"></div>
    <nav id="nav"></nav>
  </div>
</header>

<div class="wrap">
  <div class="bar">
    <input id="q" placeholder="搜索名称、ID、描述…" type="search">
    <select id="f1"></select>
    <select id="f2" style="display:none"></select>
    <span class="count" id="cnt"></span>
  </div>
  <div id="out"></div>
  <footer id="foot"></footer>
</div>

<script>
const DB = __PAYLOAD__;

const TABS = [
  {k:'building', label:'建筑设施'},
  {k:'rules',    label:'玩法规则'},
  {k:'blueprint',label:'占地蓝图'},
  {k:'layout',  label:'布局试摆'},
  {k:'base',     label:'基地面积'},
  {k:'logistics',label:'物流规则'},
  {k:'mechanics',label:'机制数值'},
  {k:'recipe',   label:'生产配方'},
  {k:'build',    label:'建造配方'},
  {k:'manual',   label:'手工配方'},
  {k:'item',     label:'物品链路'},
  {k:'overview', label:'数据概览'},
];
let tab='building', kw='', f1='', f2='', openSet=new Set();

const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const domOf=b=>(b.domainNames&&b.domainNames.length)?b.domainNames.join('/'):'全地区通用';

/* ---------- 初始化头尾 ---------- */
$('#ver').textContent = DB.meta.gameVersion + ' · ' + DB.meta.dataVersion.split('@')[1];
$('#hdmeta').textContent = '游戏 '+DB.meta.gameVersion+'　|　数据域 '+DB.meta.dataDomain+'　|　构建 '+DB.meta.builtAt;
$('#foot').innerHTML =
  '数据来源：<a href="'+esc(DB.meta.source.match(/https?:\/\/\S+/)?.[0]||'#')+'" style="color:var(--accent)">AKEDatabase</a>'+
  '（'+esc(DB.meta.dataDomain)+'）<br>'+
  esc(DB.meta.licenseNote)+'<br>'+
  '<span style="color:#9A5B1E">⚠ '+esc(DB.meta.caveat)+'</span>';

/* ---------- 渲染 ---------- */
function navHtml(){
  return TABS.map(t=>`<button data-k="${t.k}" class="${t.k===tab?'on':''}">${t.label}</button>`).join('');
}
$('#nav').innerHTML = navHtml();
$('#nav').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b) return;
  tab=b.dataset.k; kw=''; f1=''; f2=''; openSet.clear();
  $('#q').value='';
  $('#nav').innerHTML=navHtml(); render();
});

/* ---------- 筛选项：一律从数据里推导，不写死 ----------
   写死过一次就翻过车（配方页列了 8 个分类，实际只有 3 个有数据；
   角色页漏了「四号谷地」）。宁可运行时算，也不要维护一份会和数据脱节的白名单。 */
function uniq(arr){
  const seen=new Set(), out=[];
  arr.forEach(v=>{ if(v&&!seen.has(v)){ seen.add(v); out.push(v); } });
  return out.sort((a,b)=>String(a).localeCompare(String(b),'zh'));
}
function opt(vals, emptyLabel){
  return ['<option value="">'+emptyLabel+'</option>']
    .concat(vals.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`)).join('');
}
/* 试摆的分类下拉只列「选得出东西」的分类 —— 拉黑清单（LO_SKIP_IDS）可能整类清空
   （博士 2026-09-21 把「功能设备」（v131 前旧名「物流辅助」）下的洒水机/给水器/滑索架/便捷存取站/留言信标全部点名去掉），
   留一个空选项只会让人点进去看到「没有匹配的分类」。回归测试也要求每个筛选项都有结果。 */
function loCatOptions(){
  return uniq(DB.blueprint.buildings
    .filter(b=>LO_SKIP_IDS.indexOf(b.id)<0 && !(LO_HIDE_NOP&&LO_IS_NOP(b)))
    .map(b=>b.categoryName));
}
function f1Html(){
  if(tab==='building')
    /* v132 下拉也按官方组序（CAT_ORDER），与列表卡片一致 */
    return opt(uniq(DB.buildings.map(b=>b.categoryName))
      .sort((a,b)=>(CAT_ORDER[a]!=null?CAT_ORDER[a]:99)-(CAT_ORDER[b]!=null?CAT_ORDER[b]:99)), '全部分类');
  if(tab==='blueprint')
    return opt(['有接口','无接口','有传送带口','有管道口','有数量上限']
      .concat(uniq(DB.blueprint.buildings.flatMap(b=>b.domainNames||[]))), '全部筛选');
  if(tab==='base')
    return opt(uniq(DB.bases.zones.map(z=>z.domainName)), '全部据点');
  if(tab==='layout')
    return opt(loCatOptions().concat(['物流件']), '默认：核心·生产·电力·仓储·物流件');
  if(tab==='logistics')
    return opt(uniq(DB.logistics.constants.map(c=>c.group))
      .concat(uniq(DB.logistics.entities.map(e=>e.category))), '全部筛选');
  if(tab==='rules')
    return opt(uniq((DB.rules?DB.rules.rules:[]).map(ruleGroup)), '全部规则');
  if(tab==='recipe')
    return opt(uniq(DB.machine_recipes.map(r=>r.machineCategory).filter(Boolean)), '按设备分类');
  if(tab==='manual')
    return opt(uniq(DB.manual_recipes.map(r=>r.domainName)), '全部地区');
  if(tab==='item')
    return opt(uniq(Object.values(DB.items).map(v=>'R'+v.rarity))
      .sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})), '全部稀有度');
  return '';
}
function refreshFilters(){
  const h=f1Html();
  const s=$('#f1');
  s.style.display=h?'':'none';
  s.innerHTML=h;
  if(h) s.value=f1;
}

function mechLabel(mm){
  const p=[];
  if(mm.rangeMeters!=null)   p.push('作用范围 '+mm.rangeMeters+'m');
  if(mm.intervalSeconds!=null)p.push('间隔 '+mm.intervalSeconds+' 秒');
  if(mm.attack!=null)        p.push('攻击力 '+mm.attack);
  return p.join(' / ');
}

function renderBuilding(){
  const arr=DB.buildings.filter(b=>{
    if(f1 && b.categoryName!==f1) return false;
    if(kw){
      const s=kw.toLowerCase();
      if(!(b.name.toLowerCase().includes(s)||b.id.toLowerCase().includes(s)||
           (b.desc||'').toLowerCase().includes(s))) return false;
    }
    return true;
  });
  /* v131 官方组排序：组间按 CAT_ORDER（= FactoryQuickBarTypeTable.priority 面板序），组内保持
     配置表原序（Array.sort 稳定）。核心结构（协议核心/次级核心，面板「快捷建造」组）排最前。 */
  arr.sort((a,b)=>(CAT_ORDER[a.categoryName]!=null?CAT_ORDER[a.categoryName]:99)
                -(CAT_ORDER[b.categoryName]!=null?CAT_ORDER[b.categoryName]:99));
  if(!arr.length) return `<div class="empty">没有匹配的建筑</div>`;
  return `<div class="list">`+arr.map(b=>{
    const o=openSet.has('b:'+b.id);
    return `<div class="card ${o?'open':''}" data-id="b:${esc(b.id)}">
      <div class="c-top">
        <span class="c-name">${esc(b.name)}</span>
        <span class="c-id">${esc(b.id)}</span>
        <span class="spacer"></span>
        <span class="c-cat ${b.domains.length?'acc':''}">${esc(domOf(b))}</span>
        <span class="c-cat">${esc(b.categoryName)}</span>
        ${b.hasPlaceLimit?'<span class="flag">有数量上限</span>':''}
      </div>
      <div class="c-sub">
        <span>占地 ${esc(b.footprint)}</span>
        <span>${b.needPower?'耗电 '+b.powerConsume:'无需通电'}</span>
        <span>协议容量 ${b.bandwidth}</span>
      </div>
      ${b.mechanics&&Object.keys(b.mechanics).length?`<div class="star">★ ${esc(mechLabel(b.mechanics))}</div>`:''}
      ${o?`
      <div class="detail">
        ${b.desc?`<div class="d-sec"><div class="d-h">游戏内描述</div><div class="c-desc">${esc(b.desc)}</div></div>`:''}
        <div class="d-sec"><div class="d-h">属性</div>
          <div class="row"><span class="tag">分类 ID</span><span>${esc(b.category||'—')}</span></div>
          <div class="row"><span class="tag">占地 宽×深×高</span><span>${esc(b.footprint)}</span></div>
          <div class="row"><span class="tag">耗电 / 协议容量</span><span>${b.needPower?b.powerConsume:'—'} / ${b.bandwidth}</span></div>
          <div class="row"><span class="tag">协议容量说明</span><span>在集成核心区域外放置设备会消耗本地区协议容量，达到上限后无法再放置新设备</span></div>
          <div class="row"><span class="tag">液体接口</span><span>${b.liquidEnabled?'有':'无'}</span></div>
          <div class="row"><span class="tag">放置限制</span><span>${b.hasPlaceLimit?'有数量上限':'无'}</span></div>
        </div>
      </div>`:''}
    </div>`;
  }).join('')+`</div>`;
}

/* ---------- 玩法规则 ---------- */
function ruleGroup(r){
  if(r.id==='rule_core_area_definition'||r.id==='rule_belt_core_only') return '区域规则';
  if(r.id==='rule_mining_outside_core') return '开采规则';
  return '运输规则';
}
function evHtml(ev){
  if(!ev||!ev.length) return '';
  return `<details class="rl-ev"><summary>证据 ${ev.length} 条（点开复核）</summary><div class="rl-evbody">`+
    ev.map(e=>{
      const src = e.table ? `<span class="rl-src">${esc(e.table)}</span>` : `<span class="rl-src">文案 ${esc(String(e.id))}</span>`;
      const txt = e.text || (e.field?`${e.field} = ${esc(String(e.value===undefined?'':e.value))}`:'');
      return `<div class="rl-evrow">${src}<span>${esc(txt)}</span></div>`;
    }).join('')+`</div></details>`;
}
function renderRules(){
  const R = DB.rules;
  if(!R) return `<div class="empty">缺少 rules.json</div>`;
  const rules=(R.rules||[]).filter(r=>{
    if(f1 && ruleGroup(r)!==f1) return false;
    if(kw){ const s=(r.title+' '+(r.detail||'')+' '+(r.verdict||'')).toLowerCase(); if(s.indexOf(kw.toLowerCase())<0) return false; }
    return true;
  });
  const H=[];
  const all=R.rules||[];
  const verified=all.filter(r=>/成立/.test(r.verdict||'')).length;
  const evCount=all.reduce((n,r)=>n+((r.evidence||[]).length),0);
  H.push(`<div class="lg-caps">
    <div class="lg-cap"><div class="lg-capn">${all.length}</div><div class="lg-capl">机制规则</div></div>
    <div class="lg-cap"><div class="lg-capn">${verified}</div><div class="lg-capl">数据证实成立</div></div>
    <div class="lg-cap"><div class="lg-capn">${evCount}</div><div class="lg-capl">原文证据条目</div></div>
  </div>`);
  H.push(`<div class="rl-note">本页只收录<strong>能从配置表字段或游戏内文案逐条取证</strong>的规则。
   每条规则下方「证据」可展开，直接看原始表名与文案 ID。<br>
   <strong>读法：</strong>文案（I18nTextTable_CN）是规则正文，配置表是数值与端口构成。两者对不上时以文案为准并标注存疑。</div>`);

  rules.forEach(r=>{
    const v = r.verdict||'';
    const good = /成立|基本成立/.test(v);
    H.push(`<div class="rl-card">
      <div class="rl-head">
        <span class="rl-tag ${good?'ok':'warn'}">${esc(ruleGroup(r))}</span>
        <span class="rl-title">${esc(r.title)}</span>
        <span class="rl-verdict ${good?'ok':'warn'}">${esc(v)}</span>
      </div>`);
    if(r.detail) H.push(`<div class="rl-detail">${esc(r.detail)}</div>`);
    if(r.why)    H.push(`<div class="rl-detail">${esc(r.why)}</div>`);
    if(r.caveat) H.push(`<div class="rl-caveat"><strong>⚠ 注意：</strong>${esc(r.caveat)}</div>`);
    if(r.corollary) H.push(`<div class="rl-detail"><strong>推论：</strong>${esc(r.corollary)}</div>`);
    if(r.keyCorollary) H.push(`<div class="rl-detail"><strong>关键推论：</strong>${esc(r.keyCorollary)}</div>`);
    if(r.requirement) H.push(`<div class="rl-detail"><strong>前提：</strong>${esc(r.requirement)}</div>`);
    if(r.sameForPump) H.push(`<div class="rl-detail">${esc(r.sameForPump)}</div>`);
    if(r.notWireless&&r.notWireless.length){
      H.push(`<div class="rl-sub">不走无线传输的设备（反例）</div><table class="lg-tb"><tbody>`+
        r.notWireless.map(x=>`<tr><td class="same">${esc(x.building)}</td><td>${esc(x.why)}</td></tr>`).join('')+
        `</tbody></table>`);
    }
    if(r.paths&&r.paths.length){
      r.paths.forEach(p=>{
        H.push(`<div class="rl-sub">通路：${esc(p.source)}</div>
          <div class="rl-detail">${esc(p.mechanism)}</div>
          ${p.modes?`<div class="rl-detail"><strong>模式：</strong>${esc(p.modes)}</div>`:''}
          ${p.requirement?`<div class="rl-detail"><strong>前提：</strong>${esc(p.requirement)}</div>`:''}
          ${p.config?`<div class="rl-cfg"><span class="rl-src">${esc(p.config.table)}</span>${esc(p.config.note||'')}
            ${p.config.fields?`<table class="lg-tb"><tbody>`+Object.keys(p.config.fields).map(k=>`<tr><td class="same">${esc(k)}</td><td>${esc(String(p.config.fields[k]))}</td></tr>`).join('')+`</tbody></table>`:''}
          </div>`:''}
          ${evHtml(p.evidence)}`);
      });
    }
    if(r.purePipelines&&r.purePipelines.length){
      H.push(`<div class="rl-sub">纯管道设备（无任何传送带接口）</div><table class="lg-tb"><thead><tr><th>设备</th><th>端口</th></tr></thead><tbody>`+
        r.purePipelines.map(x=>`<tr><td class="same">${esc(x.building)}</td><td>${esc(x.ports)}</td></tr>`).join('')+
        `</tbody></table>`);
    }
    if(r.mixedBuildings&&r.mixedBuildings.length){
      H.push(`<div class="rl-sub">混合设备（带口 + 管口并存，流体侧仍必须走管）</div><table class="lg-tb"><thead><tr><th>设备</th><th>端口</th></tr></thead><tbody>`+
        r.mixedBuildings.map(x=>`<tr><td class="same">${esc(x.building)}</td><td>${esc(x.ports)}</td></tr>`).join('')+
        `</tbody></table>`);
    }
    if(r.crossRegionTool){
      const t=r.crossRegionTool;
      H.push(`<div class="rl-sub">跨区域工具：${esc(t.name)}</div>
        <div class="rl-detail">${esc(t.why)}　最大配对长度 <strong>${t.maxLength}</strong> 米</div>
        ${evHtml(t.evidence)}`);
    }
    if(r.regionLimit){
      H.push(`<div class="rl-sub">附加限制：${esc(r.regionLimit.title)}</div>${evHtml(r.regionLimit.evidence)}`);
    }
    if(r.corollaryEvidence) H.push(evHtml(r.corollaryEvidence));
    H.push(evHtml(r.evidence));
    H.push(`</div>`);
  });
  if(!rules.length) H.push(`<div class="empty">没有匹配的规则</div>`);
  return H.join('');
}

/* ---------- 物流规则 ---------- */
function renderLogistics(){
  const L = DB.logistics;
  if(!L) return `<div class="empty">缺少 logistics.json</div>`;

  // --- 吞吐速查 ---
  const tp = (L.throughputSummary||[]).map(t=>`
    <div class="lg-cap">
      <div class="lg-cap-n">${esc(t.name)}</div>
      <div class="lg-cap-v">${t.perSecond} <span>个/秒</span></div>
      <div class="lg-cap-v2">= ${t.perMinute} 个/分钟</div>
      <div class="lg-cap-s">${esc(t.source)}</div>
    </div>`).join('');

  // --- 物流实体表 ---
  let ents = L.entities||[];
  // f1 可能是实体分类，也可能是常量组名 —— 后者不该动实体表
  const ENT_CATS = uniq((L.entities||[]).map(e=>e.category));
  const isConstGroup = uniq((L.constants||[]).map(c=>c.group)).includes(f1);
  if(f1==='传送带') ents=ents.filter(e=>e.medium==='传送带');
  else if(f1==='管道') ents=ents.filter(e=>e.medium==='管道');
  else if(f1==='暗管（地下管道）') ents=[];   // 暗管不在物流实体表，走下面的专门表格
  else if(isConstGroup) ents=[];              // 选的是常量组，实体表不参与
  else if(f1){ ents=ents.filter(e=>ENT_CATS.includes(f1)&&e.category===f1); }
  if(kw){
    const s=kw.toLowerCase();
    ents=ents.filter(e=>String(e.name||'').toLowerCase().includes(s)||
      e.id.toLowerCase().includes(s)||String(e.type||'').toLowerCase().includes(s));
  }
  const entRows = ents.map(e=>{
    const fx = a=>(a||[]).map(v=>v+'°').join('/');
    return `<div class="lg-ent">
      <div class="lg-ent-a">
        <b>${esc(e.name||e.id)}</b>
        <code>${esc(e.id)}</code>
        <span class="lg-tag ${e.medium==='管道'?'pipe':''}">${esc(e.medium)}</span>
        <span class="lg-cat">${esc(e.category)}</span>
      </div>
      <div class="lg-ent-b">
        <span>吞吐 <b>${e.unitsPerMinute}</b> /min</span>
        <span>进料口 ${e.inputPortCount}（朝向 ${fx(e.inputFacings)}）</span>
        <span>出料口 ${e.outputPortCount}（朝向 ${fx(e.outputFacings)}）</span>
        ${e.volume!=null?`<span>容量 ${e.volume}</span>`:''}
      </div>
    </div>`;
  }).join('') || (isConstGroup
      ? '<div class="empty" style="padding:22px">当前选的是常量分组，实体表不适用 —— 下方「物流常量」已筛出对应条目</div>'
      : '<div class="empty">没有匹配的物流实体</div>');

  // --- 常量分组 ---
  let cons = L.constants||[];
  // f1 既可能是常量组名，也可能是物流实体分类 —— 按数据判断，别维护白名单
  // ⚠️ ENT_CATS 上面（实体表段落）已用 const 声明过，这里只能复用，不能重复声明。
  // 同一作用域重复 const 是 SyntaxError，会让整个 <script> 作废 → 页面全白。
  const CONS_GROUPS = uniq(cons.map(c=>c.group));
  if(CONS_GROUPS.includes(f1))      cons=cons.filter(c=>c.group===f1);
  else if(ENT_CATS.includes(f1))    cons=[];   // 选的是实体分类，常量不参与
  if(kw){
    const s=kw.toLowerCase();
    cons=cons.filter(c=>String(c.label).toLowerCase().includes(s)||c.key.toLowerCase().includes(s));
  }
  const groups={};
  cons.forEach(c=>{ (groups[c.group]=groups[c.group]||[]).push(c); });
  const consEmpty = ENT_CATS.includes(f1) && !CONS_GROUPS.includes(f1)
    ? '<div class="empty" style="padding:22px">当前选的是物流实体分类，常量表不适用 —— 上方实体表已筛出对应条目</div>'
    : '<div class="empty">没有匹配的常量</div>';
  const consHtml = Object.keys(groups).map(g=>`
    <div class="d-sec">
      <div class="d-h">${esc(g)}</div>
      ${g.indexOf('存疑')>=0?`
      <div class="note" style="background:#FBF0E0;border-color:#E8D5B0;margin-bottom:6px">
        <b>这一组是配置表内部矛盾项，别直接引用。</b><br>
        <code>travelPoleNop1Radius = 300</code> 看着像滑索射程，但
        <code>travel_pole_nop_1</code> 的建筑描述<b>白纸黑字写着「可在80m范围内相连」</b>，
        同款的 <code>travel_pole_1</code> 也是 80m（<code>travelPole1Radius=80</code>）。<br>
        而这 300 与 <code>udPipeConnectMaxLength = 300</code> 是<b>同一个数</b>——它被归在
        <code>travelPole</code> 前缀下，实际是<b>暗管的配对连接长度</b>。<br>
        <b>滑索用 80 / 110；300 是暗管的。</b>
      </div>`:''}
      <table class="lg-tb">
        <thead><tr><th>常量</th><th>含义</th><th class="r">值</th><th>单位</th></tr></thead>
        <tbody>${groups[g].map(c=>`<tr>
          <td><code>${esc(c.key)}</code></td>
          <td>${esc(c.label)}</td>
          <td class="r"><b>${c.value}</b></td>
          <td class="u">${esc(c.unit||'—')}</td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`).join('') || consEmpty;

  // --- 蓝图系统规则 ---
  const br = L.blueprintRules||{};
  const brHtml = `
    <div class="d-sec"><div class="d-h">蓝图系统规则（FacBlueprintConst）</div>
      <div class="row"><span class="tag">分享码前缀</span><span>${(br.shareCodePrefix||[]).map(x=>'<code>'+esc(x)+'</code>').join(' 或 ')}</span></div>
      <div class="row"><span class="tag">码字符集</span><span><code>${esc(br.charSet||'—')}</code></span></div>
      <div class="row"><span class="tag">蓝图最大范围</span><span>${br.maxLenX} × ${br.maxLenZ} 格</span></div>
      <div class="row"><span class="tag">单蓝图节点上限</span><span>${br.nodeCountLimit}</span></div>
      <div class="row"><span class="tag">我的蓝图上限</span><span>${br.myBlueprintMax}</span></div>
      <div class="row"><span class="tag">赠送蓝图上限</span><span>${br.giftBlueprintMax}</span></div>
      <div class="row"><span class="tag">分享码有效期</span><span>${br.shareExpireSeconds} 秒（${(br.shareExpireSeconds/86400).toFixed(0)} 天）</span></div>
      <div class="row"><span class="tag">名称 / 描述长度上限</span><span>${br.nameMaxLen} / ${br.descMaxLen} 字</span></div>
      <div class="row"><span class="tag">标签数上限</span><span>${br.tagMax}</span></div>
    </div>`;

  // --- 供电杆线长 ---
  const poleRows = (L.powerPoles||[]).map(p=>p.special?'':`
    <tr><td><code>${esc(p.id)}</code></td>
    <td>${p.autoConnect?'自动连接':'手动连接'}</td>
    <td class="r"><b>${p.autoConnectLength}</b></td>
    <td>${p.rangeExtend?`${p.rangeExtend.x}/${p.rangeExtend.y}/${p.rangeExtend.z}`:'—'}</td></tr>`).join('');
  const polesHtml = poleRows.trim()?`
    <div class="d-sec"><div class="d-h">供电设施（线长 / 覆盖扩展）</div>
      <table class="lg-tb">
        <thead><tr><th>ID</th><th>连接方式</th><th class="r">自动连接长度</th><th>覆盖扩展 x/y/z</th></tr></thead>
        <tbody>${poleRows}</tbody>
      </table></div>`:'';

  // --- 采矿/抽水/储液 ---
  const mineRows = (L.miners||[]).map(m=>`
    <tr><td><code>${esc(m.id)}</code></td>
    <td class="r"><b>${m.unitsPerMinute}</b></td>
    <td>${m.msPerRound}</td>
    <td>${(m.mineableNames||[]).filter(Boolean).join('、')||'—'}</td>
    <td>${m.hasDroneMode?'支持无人机':'—'}</td></tr>`).join('');
  const pumpRows = (L.pumps||[]).map(p=>`
    <tr><td><code>${esc(p.id)}</code></td><td>${esc(p.kind)}</td>
    <td class="r">${p.unitsPerMinute!=null?'<b>'+p.unitsPerMinute+'</b>':'—'}</td>
    <td>${p.maximumSuply!=null?p.maximumSuply:'—'}</td></tr>`).join('');
  const stRows = (L.fluidStoragers||[]).map(s=>`
    <tr><td><code>${esc(s.id)}</code></td><td class="r"><b>${s.capacity}</b></td></tr>`).join('');
  const rateHtml = `
    <div class="d-sec"><div class="d-h">采矿机产出速率</div>
      <table class="lg-tb"><thead><tr><th>ID</th><th class="r">产出 /min</th><th>msPerRound</th><th>可采矿种</th><th>无人机</th></tr></thead>
      <tbody>${mineRows}</tbody></table></div>
    ${pumpRows?`<div class="d-sec"><div class="d-h">流体泵 / 排液口</div>
      <table class="lg-tb"><thead><tr><th>ID</th><th>类型</th><th class="r">速率 /min</th><th>最大供给</th></tr></thead>
      <tbody>${pumpRows}</tbody></table></div>`:''}
    ${stRows?`<div class="d-sec"><div class="d-h">液体储罐容量</div>
      <table class="lg-tb"><thead><tr><th>ID</th><th class="r">容量</th></tr></thead>
      <tbody>${stRows}</tbody></table></div>`:''}`;

  // --- 暗管（地下管道）---
  const upRows = (L.undergroundPipes||[]).map(u=>`
    <tr>
      <td><b>${esc(u.name)}</b><br><code>${esc(u.id)}</code></td>
      <td>${esc(u.role)}</td>
      <td class="r">${esc(u.gridFootprint)}</td>
      <td class="r">${u.role==='入口'?u.inputPortCount+' 进':u.outputPortCount+' 出'}</td>
      <td class="u">${u.needPower?'耗电':'免电'}</td>
    </tr>`).join('');
  const upHtml = (L.undergroundPipes||[]).length?`
    <div class="d-sec"><div class="d-h">暗管（地下管道）—— 入口/出口成对配对</div>
      <table class="lg-tb">
        <thead><tr><th>名称</th><th>角色</th><th class="r">占地</th><th class="r">接口</th><th>供电</th></tr></thead>
        <tbody>${upRows}</tbody>
      </table>
      <div class="c-sub" style="margin-top:8px">
        <span>入口与出口<b>成对连接</b>，传输管道中的货物</span>
        <span>最大配对连接长度 <b>300</b></span>
      </div>
    </div>`:'';

  // --- _nop_ 命名警告 ---
  const nopRows = (L.nopVariants||[]).map(n=>`
    <tr>
      <td><code>${esc(n.baseId)}</code></td><td>${esc(n.baseName)}</td>
      <td class="r">${n.basePower}</td>
      <td><code>${esc(n.nopId)}</code></td><td>${esc(n.nopName)}</td>
      <td class="r">${n.nopPower}</td>
      <td>${n.sameName?'<b class="same">同名</b>':'异名'}</td>
    </tr>`).join('');
  const nopHtml = (L.nopVariants||[]).length?`
    <div class="d-sec"><div class="d-h">⚠️ _nop_ 后缀 = 免电变体，但<b>官方名沿用原版</b></div>
      <table class="lg-tb">
        <thead><tr><th>原版 ID</th><th>官方名</th><th class="r">耗电</th>
        <th>免电版 ID</th><th>官方名</th><th class="r">耗电</th><th>是否同名</th></tr></thead>
        <tbody>${nopRows}</tbody>
      </table>
      <div class="note" style="margin-top:9px;background:#FBF0E0;border-color:#E8D5B0">
        <b>别自己造名字。</b> <code>_nop_</code> 是 no-power 变体，但它的官方名<b>和原版完全一样</b>——
        例：<code>travel_pole_nop_1</code> 的官方名就是「<b>滑索架</b>」，不叫「免电滑索架」。
        写攻略时用官方名；需要区分时可加后缀说明，但不要把它当成正式名称。
      </div>
    </div>`:'';

  return `
  <div class="note" style="margin-bottom:14px">
    <b>📡 物流规则层</b><br>
    传送带 / 管道在游戏里是<b>独立于建筑表的物流实体</b>，本页数值直接取自配置表
    <code>FactoryGridBeltTable</code>、<code>FactoryLiquidPipeTable</code>、<code>FactoryGridRouterTable</code> 等，
    未做二次假设。<br>
    <b>吞吐换算</b>：<code>msPerRound</code> 毫秒走 1 个 → 每分钟 = 60000 / msPerRound。<br>
    <span style="color:#9A5B1E">⚠ 仍缺：传送带/管道<b>在蓝图里占几格</b>（表里没有独立占格字段，它们按路径逐格铺设）、以及<b>吞吐实测校验</b>（数值来自配置，未经游戏内实测比对）。</span>
  </div>

  <div class="d-sec" style="margin-bottom:16px">
    <div class="d-h">吞吐速查</div>
    <div class="lg-caps">${tp}</div>
  </div>

  <div class="d-sec">
    <div class="d-h">物流实体（传送带 / 管道 / 分流汇流 / 连接 / 阀门）</div>
    ${entRows || '<div class="empty">当前筛选下无物流实体（暗管见下方专表）</div>'}
  </div>

  ${upHtml}
  ${nopHtml}

  <div class="d-sec"><div class="d-h">物流常量</div></div>
  ${consHtml}
  ${brHtml}
  ${polesHtml}
  ${rateHtml}`;
}

/* ---------- 占地蓝图 ---------- */
/* 占地平面示意改成 SVG 俯视图（对齐游戏蓝图预览那种网格观感）。
   不用游戏贴图：蓝图码解不开、贴图有版权，而且要保持单文件离线可用 ——
   所以照 zmd-bp-tool / IndustrialPlanner 那些第三方工具的路子自己画矢量：
   网格 + 建筑外框 + 分类配色字标 + 接口方块/圆点 + 朝外的接口引线。
   颜色只表达 进/出、传送带/管道 与 分类；边名仍是格坐标，不声称游戏内绝对方位。 */
/* 配置表里「协议核心 / 次级核心」的 quickBarType 是空字符串，build.py 的兜底映射把它们归进了
   「装饰与其他」，界面上就显示成「饰」。它们不是装饰 —— 博士 2026-09-21 指出。
   这里在数据载入后统一改分类：之后所有按 categoryName 走的逻辑（分类字标 / 配色 / 两个分类
   下拉 / 试摆左栏筛选）一次性全对，不用逐处打补丁。
   ⚠️ 改 build.py 或重跑构建都不影响这里 —— 页面数据是构建时内联进 HTML 的，只能在这儿改。
   （同样是兜底分类的 liquid_recycle_gate_1 / liquid_clean_gate_1 / power_port_1 是野外固定件，
     不进试摆，分类保持原样。） */
/* ⭐v136（博士 2026-09-24：「都说了只要扩容反应池了，我要只显示反应池，反应池的数据是扩容反应池的就行」）：
   界面上**只呈现一个「反应池」**，它的数据（占地 6×5 / 100 电 / 8 缓存格 / 3 条并行）就是扩容反应池
   mix_pool_2 的；基础反应池 mix_pool_1 从沙盘清单移除（LO_SKIP_IDS，见下），不作独立条目出现。 */
const POOL_DISPLAY_NAME={'mix_pool_2':'反应池'};
/* ⭐v136 尺寸覆盖（以游戏实测为准，与 build.py SIZE_OVERRIDE 同源）：扩容反应池实占 **5×5**。
   配置表 range=6×5 / 模板名 06x05 判为口径偏差；gridFootprint 是尺寸唯一出口（Lfp 解析它），
   覆盖这一处 → 摆放 / 渲染 / 接口坐标 / 占地文案 全一致。 */
const SIZE_OVERRIDE={'mix_pool_2':'5×5'};
const _POOL_BASE_PORTS=((((DB.buildings||[]).filter(function(x){return x.id==='mix_pool_1';})[0])||{}).ports)||null;
const CORE_STRUCT_IDS={'sp_hub_1':1,'sp_sub_hub_1':1};
[DB.buildings,DB.blueprint.buildings,DB.mechanics].forEach(function(arr){
  (arr||[]).forEach(function(b){
    if(b&&CORE_STRUCT_IDS[b.id]) b.categoryName='核心结构';
    if(b&&POOL_DISPLAY_NAME[b.id]) b.name=POOL_DISPLAY_NAME[b.id];   /* ⭐v136 只呈现「反应池」，数据=扩容池 */
    if(b&&SIZE_OVERRIDE[b.id]) b.gridFootprint=SIZE_OVERRIDE[b.id];   /* ⭐v136 扩容池实占 5×5 */
    /* ⭐v136 端口覆盖：扩容池实机端口 = 基础池那套（每边各 2：带 2 进 2 出 / 管 2 进 2 出，共 8 个）。
       配置表按 6 格宽写成了「4 带进 + 4 带出 + 2 管进 + 2 管出」（12 个，管道出口 x=5 在 5×5 上越界），
       博士 2026-09-24 实机核实为每边各 2 —— 以游戏为准，整组沿用基础池坐标。 */
    if(b&&b.id==='mix_pool_2'&&_POOL_BASE_PORTS) b.ports=JSON.parse(JSON.stringify(_POOL_BASE_PORTS));
    /* 端口绑定同步：端口数组换成 8 个后，扩容池配方组的绑定索引也要换成基础池那套（[0,1]/[2,3]），
       否则旧绑定 [4,5] 会越界（test_html「接口序号越界」断言会红）。 */
    if(b&&b.id==='mix_pool_2'){
      const _grp=(DB.recipe_groups||{}).groups||{};
      const _a=_grp['group_mix_pool_1_liquid'], _b2=_grp['group_mix_pool_2_liquid'];
      if(_a&&_b2){ ['solidIn','fluidIn','solidOut','fluidOut'].forEach(function(k){
        if(_a[k]) _b2[k]=JSON.parse(JSON.stringify(_a[k])); }); }
    }
  });
});

/* v132 分类三表（CAT_COLOR/CAT_GLYPH/CAT_ORDER）由构建时动态生成（由构建时 gen_cat_tables() 注入）：
   名单源 = data/categories.json（AKEDatabase FactoryQuickBarTypeTable，build.py 动态读 raw 表，
   游戏版本更新 → fetch_raw.py → 重跑构建即自动跟上），并兜底收集数据里实际出现过的全部
   categoryName —— 上游加新组时自动获得灰底 + 名字首字字标，前端永不查空。
   v131 改名对照留档：资源采集→资源开采、基础加工→基础生产、组件加工→合成制造、
   物流辅助→功能设备、仓储物流→仓储存取、防御设施→战斗辅助。 */
/*__CAT_TABLES__*/
function catColor(b){ return CAT_COLOR[b.categoryName]||CAT_COLOR['装饰与其他']; }
function catGlyph(b){ return CAT_GLYPH[b.categoryName]||CAT_GLYPH['装饰与其他']; }
/* 物流件的色 / 字形按介质分：传送带系青、管道系紫；功能件用「汇/分/桥/阀」，纯带子留箭头 */
function lgColor(b){ return b.lgMedium==='管道'?'#7B62C9':'#2E8B9E'; }
function lgGlyph(b){
  if(b.lgType==='Belt'||b.lgType==='Pipe') return '▶';
  if(String(b.name).indexOf('汇流')>=0) return '汇';
  if(String(b.name).indexOf('分流')>=0) return '分';
  if(String(b.name).indexOf('桥')>=0) return '桥';
  if(String(b.name).indexOf('准入口')>=0) return '阀';
  return '运';
}
function loPieceGlyph(b){ return b&&b.isLogi?lgGlyph(b):catGlyph(b); }

/* ---------- 物流件的「进/出边」怎么算 ----------
   配置表（FactoryGridRouterTable / FactoryGridConnecterTable / FactoryBoxValveTable）里每个接口带
   rotation.y ∈ {0,90,180,270}。它**不是朝向本身，而是物料的流向**：
       rotation.y  0=下(+z)  90=右(+x)  180=上(-z)  270=左(-x)     （画布术语）
   规则：**进料口在流向的反侧，出料口在流向那一侧**。

   验证（别再来回猜，这套是回代过的）：
     汇流器   进{90,180,270} / 出{180}  → 进「左/下/右」、出「上」 = 3 进 1 出 ✓
     分流器   进{180} / 出{90,180,270}  → 进「下」、出「右/上/左」 = 1 进 3 出 ✓
     物品准入口 进{180} / 出{180}       → 进「下」、出「上」 = 直线穿过 ✓
     物流桥   全四向进出               → 四条边都双向 ✓
   再拿**全部 267 个建筑接口**回代：266 个吻合，唯一例外是 3×1 的仓库存取口 ——
   1 格厚的建筑 z=0 与 z=D-1 是同一条线、几何退化，位置法只能取 z 边。

   画布术语（右/下/左/上）只是本沙盘的记号，**不声称游戏内绝对方位**（同「接口边名用格坐标」的规矩）。 */
const LOGI_FLOW={0:'b', 90:'r', 180:'t', 270:'l'};    // rotation.y → 流向
const LOGI_OPP={t:'b', b:'t', l:'r', r:'l'};
const LOGI_STEP={r:'b', b:'l', l:'t', t:'r'};         // 与画布顺时针旋转同向（0°=右）
const LGNAME={t:'上', b:'下', l:'左', r:'右'};
/* ⭐v109 协议核心出货箭头：画在出料口**内侧一格**（⭐v124 自口格内移，口格留白给物流
   交互）、**朝外指**（口朝哪边就指哪边，视觉上对应它的口）。
   用 Lo 的 u/d/l/r 那套方向命名（LportDir 的返回值），不是 LOGI 的 t/b/l/r。 */
const LO_DLVARROW={
  r:'<svg viewBox="0 0 12 12"><path d="M1 6h7M6 3l3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  l:'<svg viewBox="0 0 12 12"><path d="M11 6H4M6 3L3 6l3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  d:'<svg viewBox="0 0 12 12"><path d="M6 1v7M3 6l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  u:'<svg viewBox="0 0 12 12"><path d="M6 11V4M3 6l3-3 3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
function lgRotSteps(rot){ return ((Math.round(rot/90)%4)+4)%4; }
function lgSides(list, rot, isInput){
  const k=lgRotSteps(rot), out=[];
  (list||[]).forEach(th=>{
    let d=LOGI_FLOW[((th%360)+360)%360];
    if(!d) return;
    if(isInput) d=LOGI_OPP[d];
    for(let i=0;i<k;i++) d=LOGI_STEP[d];
    if(out.indexOf(d)<0) out.push(d);
  });
  return out;
}
function lgPortSides(b, rot){
  if(b.lgInFacings&&b.lgInFacings.length){
    return {in:lgSides(b.lgInFacings,rot,true), out:lgSides(b.lgOutFacings,rot,false)};
  }
  /* 传送带 / 管道在配置表里没有接口数组：按「一格一段、穿过」处理 —— 进在尾、出在头 */
  let f='r'; for(let i=0;i<lgRotSteps(rot);i++) f=LOGI_STEP[f];
  return {in:[LOGI_OPP[f]], out:[f]};
}
function lgSideNames(b, rot, which){
  const a=(which==='in'?lgPortSides(b,rot).in:lgPortSides(b,rot).out);
  return a.length?a.map(d=>LGNAME[d]).join('/'):'—';
}
/* 9×9 的格内坐标系（.lo-cell 的 padding box），中心 4.5 */
const LG_BAR={ t:[2,0,5,2], b:[2,7,5,2], l:[0,2,2,5], r:[7,2,2,5] };
const LG_HALF={ t:[[2,0,2.5,2],[4.5,0,2.5,2]], b:[[2,7,2.5,2],[4.5,7,2.5,2]],
                l:[[0,2,2,2.5],[0,4.5,2,2.5]], r:[[7,2,2,2.5],[7,4.5,2,2.5]] };
const LG_IN='#186C7D', LG_OUT='#C0561F';
/* 把一件物流件画成 SVG：边上贴进/出色条（青=进 橙=出，双向边画成半青半橙），
   中心放功能字形；传送带/管道改放一个流向箭头（并配一进一出两条色条）。 */
function lgSvg(b, rot, inSide){
  const ps=lgPortSides(b, rot), role={};
  /* ⭐v106（博士 2026-09-23 游戏截图「一格拐弯画不了」）：带/管的**进色条**要用真实拓扑
     （renderLayout 用 flowIn 由邻居反推的 inSide）——弯头格 rot 单值推的「进=出的反向」
     与真实进边不同轴，旧版色条画上边、弧却从左边绕，自相矛盾。
     功能件（汇/分/桥/阀）是多边进出，单进边覆盖不适用，保持按配置表画。 */
  const inOverride=(b.lgType==='Belt'||b.lgType==='Pipe')&&inSide;
  (inOverride?[inSide]:ps.in).forEach(d=>{ role[d]=role[d]||{}; role[d].i=1; });
  ps.out.forEach(d=>{ role[d]=role[d]||{}; role[d].o=1; });
  let s='';
  ['t','b','l','r'].forEach(d=>{
    const r=role[d]; if(!r) return;
    const rect=(q,c)=>`<rect x="${q[0]}" y="${q[1]}" width="${q[2]}" height="${q[3]}" rx="0.7" fill="${c}"/>`;
    if(r.i&&r.o){
      s+=rect(LG_HALF[d][0],LG_IN)+rect(LG_HALF[d][1],LG_OUT);
    } else {
      s+=rect(LG_BAR[d], r.i?LG_IN:LG_OUT);
    }
  });
  if(b.lgType==='Belt'||b.lgType==='Pipe'){
    /* ⭐ 2026-09-21（博士反馈：拐弯箭头不直观）：知道进边时，弯道格画成 L 形圆弧带
       （进边中点 → 圆角 → 出边中点 + 出口小箭头），和游戏里的弯道一个观感；
       直线格 / 线头（不知道进边）保持原来的直箭头。 */
    const outD=(ps.out&&ps.out[0])||'r';
    const perp=(inSide==='t'||inSide==='b') ? (outD==='l'||outD==='r')
             : (inSide==='l'||inSide==='r') ? (outD==='t'||outD==='b') : false;
    if(inSide && inSide!==outD && perp){
      const P={t:[4.5,0], b:[4.5,9], l:[0,4.5], r:[9,4.5]};
      const ip=P[inSide], op=P[outD];
      const corner=(inSide==='t'||inSide==='b')?[op[0],ip[1]]:[ip[0],op[1]];
      const DEG={r:0, b:90, l:180, t:270};
      s+=`<path d="M${ip[0]} ${ip[1]} Q${corner[0]} ${corner[1]} ${op[0]} ${op[1]}"`
        +` fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`
        +`<g transform="rotate(${(DEG[outD]-90)} 4.5 4.5)">`
        +`<path d="M4.5 8.6 L3.1 6.7 L5.9 6.7 Z" fill="currentColor"/></g>`;
    } else {
      s+=`<g transform="rotate(${lgRotSteps(rot)*90} 4.5 4.5)" fill="none" stroke="currentColor"`
        +` stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">`
        +`<path d="M1.7 4.5 L7.1 4.5"/><path d="M4.6 2.5 L7.1 4.5 L4.6 6.5"/></g>`;
    }
  } else {
    s+=`<text x="4.5" y="6.6" font-size="5.6" font-weight="700" text-anchor="middle"`
      +` fill="currentColor">${esc(lgGlyph(b))}</text>`;
  }
  return `<svg viewBox="0 0 9 9" aria-hidden="true">${s}</svg>`;
}
/* 采集类建筑的「无线传输」信息（2026-09-22 博士问的）：
   矿机在配置表里确实挂着 3 个传送带出料口，但**电驱矿机默认是「无线传输模式」**（hasDroneMode / 10 秒一次），
   产物直接回仓库 —— 所以那 3 个口平时不用接带子。展示层必须把这件事画/写出来，
   否则「矿机顶着 3 个出货口」会让人以为要拉带子（博士原话：矿机挖完是无线传回仓库的）。 */
function gatherInfo(id){
  return ((DB.mining_power||{}).gather||[]).filter(g=>g.id===id)[0]||null;
}
function mdBold(s){
  return String(s||'').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>');
}
function footprintSvg(b){
  const pp=b.gridFootprint.split('×');
  const W=pp[0]|0, D=pp[1]|0;
  if(!W||!D) return '';
  const gi=gatherInfo(b.id), wi=!!(gi&&gi.wireless);
  const isMiner=!!(gi&&gi.kind==='采矿机');   /* 矿机的传送带出料口一律不画（见下面的说明） */
  const CELL=46, PAD=32;
  const Wd=PAD*2+W*CELL, Hd=PAD*2+D*CELL;
  const gx=i=>PAD+i*CELL, gy=i=>PAD+i*CELL;
  const cx=i=>gx(i)+CELL/2, cz=i=>gy(i)+CELL/2;
  const C_IN_B='var(--accent)', C_IN_P='#7FCDB6',
        C_OUT_B='var(--warn)', C_OUT_P='#E8C79A', C_X='#B3261E',
        C_WIFI='#C9A227',   /* 无线回传口（矿机）：金色，与「出料口」的橙分开 */
        C_CACHE='#6E8AA8';  /* 便携源石矿机的缓存区口：灰蓝（也不接带子，但要人手动取） */
  const cells={};
  (b.ports||[]).forEach(pt=>{
    if(pt.z<0||pt.z>=D||pt.x<0||pt.x>=W) return;
    /* ⭐⭐ 矿机的**传送带出料口不画**（博士 2026-09-22 两次指出，并问「那这样 4 还用吗，玩家都是用无线传输的」）：
       配置表里矿机确实记着 3 个传送带出料口，但**两种模式都用不上** ——
       默认「无线传输模式」产物直接回仓库；切「仓储模式」也只是进缓存区、**手动取出**（文案原文：
       「切换到仓储模式后，会和源石矿机一样不会将矿物送回仓库，必须从缓存区手动取出」）。
       换句话说这 3 个口对玩家**没有任何用途** —— 画出来只会让人以为要接带子。
       数据层仍保留 `ports`（那是配置表事实），只是示意图不画；改画建筑内的「⇡ 无线回传」徽标。
       水驱矿机的**管道进料口**（清水）是真口，照常画。 */
    if(isMiner && pt.kind==='output' && !pt.isPipe) return;
    const k=pt.x+','+pt.z;
    if(!cells[k]) cells[k]={x:pt.x,z:pt.z,kind:{},n:0};
    cells[k].n++;
    const kk=(pt.kind==='input'?'in':'out')+(pt.isPipe?'P':'B');
    cells[k].kind[kk]=(cells[k].kind[kk]||0)+1;
  });
  let s='';
  s+='<svg viewBox="0 0 '+Wd+' '+Hd+'" width="100%" style="max-width:720px;display:block" role="img" aria-label="'+esc(b.name)+' 占地平面示意">';
  s+='<rect x="0" y="0" width="'+Wd+'" height="'+Hd+'" rx="8" fill="#FBFAF6"/>';
  let i;
  for(i=0;i<=W;i++) s+='<line x1="'+gx(i)+'" y1="'+gy(0)+'" x2="'+gx(i)+'" y2="'+gy(D)+'" stroke="#E7E5DC"/>';
  for(i=0;i<=D;i++) s+='<line x1="'+gx(0)+'" y1="'+gy(i)+'" x2="'+gx(W)+'" y2="'+gy(i)+'" stroke="#E7E5DC"/>';
  s+='<rect x="'+gx(0)+'" y="'+gy(0)+'" width="'+(W*CELL)+'" height="'+(D*CELL)+'" rx="4" fill="'+catColor(b)+'" fill-opacity="0.12" stroke="var(--accent)" stroke-width="2"/>';
  for(i=0;i<W;i++) s+='<text x="'+cx(i)+'" y="'+(gy(0)-11)+'" text-anchor="middle" font-size="11" fill="var(--ink3)">'+i+'</text>';
  for(i=0;i<D;i++) s+='<text x="'+(gx(0)-14)+'" y="'+(cz(i)+4)+'" text-anchor="end" font-size="11" fill="var(--ink3)">'+i+'</text>';
  if(W>=3&&D>=3){
    s+='<text x="'+cx((W-1)/2)+'" y="'+(cz((D-1)/2)-10)+'" text-anchor="middle" font-size="20" font-weight="600" fill="'+catColor(b)+'">'+catGlyph(b)+'</text>';
    s+='<text x="'+cx((W-1)/2)+'" y="'+(cz((D-1)/2)+6)+'" text-anchor="middle" font-size="12" font-weight="600" fill="var(--ink)">'+esc(b.name)+'</text>';
    s+='<text x="'+cx((W-1)/2)+'" y="'+(cz((D-1)/2)+22)+'" text-anchor="middle" font-size="10.5" fill="var(--ink3)">'+W+'×'+D+' · '+(b.gridArea||(W*D))+'格² · 格高'+b.gridHeight+'</text>';
    /* 矿机：把「产物怎么走」直接标在建筑上（比画 3 个用不上的出料口清楚得多） */
    if(isMiner){
      const bx=gx(W)-7, by=gy(0)+15;
      s+='<text x="'+bx+'" y="'+by+'" text-anchor="end" font-size="11.5" font-weight="700" fill="'+(wi?C_WIFI:C_CACHE)+'">'
        +(wi?'⇡ 无线回传仓库':'⇥ 缓存区 · 手动收取')+'</text>';
    }
  } else {
    s+='<text x="'+cx((W-1)/2)+'" y="'+(cz((D-1)/2)+4)+'" text-anchor="middle" font-size="'+(W===1?'14':'16')+'" font-weight="600" fill="'+catColor(b)+'">'+catGlyph(b)+'</text>';
  }
  Object.keys(cells).forEach(k=>{
    const c=cells[k], X=cx(c.x), Z=cz(c.z);
    const ks=Object.keys(c.kind);
    let fill, txt, circle=false, stroke='', wifi=false;
    if(ks.length>1){ fill=C_X; txt='×'; }
    else{
      const key=ks[0], isIn=key.indexOf('in')===0, isP=key.indexOf('P')>=0;
      if(isIn&&isP){ fill=C_IN_P; txt='i'; circle=true; stroke='var(--accent)'; }
      else if(isIn){ fill=C_IN_B; txt='I'; }
      else if(isP){ fill=C_OUT_P; txt='o'; circle=true; stroke='var(--warn)'; }
      else { fill=C_OUT_B; txt='O'; }
    }
    const edges=[];
    if(c.z===0)edges.push([0,-1]);
    if(c.z===D-1)edges.push([0,1]);
    if(c.x===0)edges.push([-1,0]);
    if(c.x===W-1)edges.push([1,0]);
    const col=circle?stroke:fill;
    edges.slice(0,1).forEach(v=>{
      s+='<line x1="'+(X+v[0]*13)+'" y1="'+(Z+v[1]*13)+'" x2="'+(X+v[0]*25)+'" y2="'+(Z+v[1]*25)
        +'" stroke="'+col+'" stroke-width="3"'+(circle?' stroke-dasharray="4 3"':'')+'/>';
    });
    if(circle){
      s+='<circle cx="'+X+'" cy="'+Z+'" r="11" fill="'+fill+'" stroke="'+stroke+'" stroke-width="2"/>';
      s+='<text x="'+X+'" y="'+(Z+4)+'" text-anchor="middle" font-size="12" font-weight="600" fill="var(--ink)">'+txt+'</text>';
    }else if(wifi){
      /* 无线回传口：金色虚线方框 + ⇡（不是让你接带子的意思） */
      s+='<rect x="'+(X-12)+'" y="'+(Z-12)+'" width="24" height="24" rx="3" fill="'+fill+'" stroke="#FFFFFF" stroke-width="2" stroke-dasharray="4 3"/>';
      s+='<text x="'+X+'" y="'+(Z+5)+'" text-anchor="middle" font-size="14" font-weight="700" fill="#FFFFFF">'+txt+'</text>';
    }else{
      s+='<rect x="'+(X-12)+'" y="'+(Z-12)+'" width="24" height="24" rx="3" fill="'+fill+'"/>';
      s+='<text x="'+X+'" y="'+(Z+4)+'" text-anchor="middle" font-size="12" font-weight="600" fill="#FFFFFF">'+txt+'</text>';
    }
    const cnt=ks.length===1?c.kind[ks[0]]:c.n;
    if(cnt>1) s+='<text x="'+(X+14)+'" y="'+(Z-13)+'" font-size="10" fill="var(--ink3)">×'+cnt+'</text>';
  });
  s+='</svg>';
  return s;
}

function gridHtml(b){
  const svg=footprintSvg(b);
  const pp=b.gridFootprint.split('×');
  const W=pp[0]|0, D=pp[1]|0;
  const gi=gatherInfo(b.id);
  if(!svg) return '';
  return `<div class="d-sec"><div class="d-h">占地平面示意（${W}×${D} 格 · 俯视图）</div>
    <div style="margin-top:8px">${svg}</div>
    <div class="c-sub" style="margin-top:10px">
      <span>横轴 = x（0 ~ ${W-1}）</span>
      <span>纵轴 = z（0 为第一行）</span>
      <span>外圈短线 = 口朝哪条边外</span>
    </div>
    <div class="c-sub">
      <span><b style="color:var(--accent)">■</b> I = 进料口（传送带）</span>
      <span><b style="color:#7FCDB6">●</b> i = 进料口（管道）</span>
      <span><b style="color:var(--warn)">■</b> O = 出料口（传送带）</span>
      <span><b style="color:#E8C79A">●</b> o = 出料口（管道）</span>
      ${gi&&gi.wireless?`<span><b style="color:#C9A227">⇡ 无线回传仓库</b> = 产物直接进仓库（<b>不用接带子</b>）</span>`:''}
      ${gi&&!gi.wireless&&gi.kind==='采矿机'?`<span><b style="color:#6E8AA8">⇥ 缓存区 · 手动收取</b> = 产物进缓存区（<b>也不接带子</b>）</span>`:''}
      <span><b style="color:#B3261E">■</b> × = 同格多口</span>
    </div>
    ${gi&&gi.kind==='采矿机'?`<div class="c-sub" style="margin-top:6px"><span style="color:var(--ink3)">⚠️ 配置表里这台还记着 <b>3 个传送带出料口</b>，但<b>两种模式都用不上</b>（默认无线回传；切「仓储模式」也只是进缓存区、要手动取出）——
      所以示意图<b>不画它们</b>（数据仍保留在 <code>ports</code> 里）。水驱矿机左边那个<b>管道进料口</b>（清水）是真的，照常画。</span></div>`:''}
    ${gi?`<div class="c-sub" style="margin-top:8px"><span style="color:#8A5A2B">${mdBold(gi.wirelessNote)}${gi.wirelessSource?('　<span class="c-id">（来源：'+esc(gi.wirelessSource)+'）</span>'):''}</span></div>`:''}
  </div>`;
}

function renderBlueprint(){
  let arr=DB.blueprint.buildings;
  if(f1){
    if(f1==='有接口')        arr=arr.filter(b=>b.portCount>0);
    else if(f1==='无接口')   arr=arr.filter(b=>b.portCount===0);
    else if(f1==='有传送带口')arr=arr.filter(b=>b.hasBeltPorts);
    else if(f1==='有管道口') arr=arr.filter(b=>b.hasPipePorts);
    else if(f1==='有数量上限')arr=arr.filter(b=>b.hasPlaceLimit);
    else                     arr=arr.filter(b=>(b.domainNames||[]).includes(f1));
  }
  if(kw){
    const s=kw.toLowerCase();
    arr=arr.filter(b=>b.name.toLowerCase().includes(s)||b.id.toLowerCase().includes(s)||
      (b.gridFootprint||'').includes(s));
  }
  if(!arr.length) return `<div class="empty">没有匹配的设施</div>`;
  return `<div class="note" style="margin-bottom:14px">
    <b>蓝图用法</b><br>
    占地 = <b>宽 × 深</b>（整数格，蓝图摆放依据）；高度 = 占用格高（可堆叠依据）。
    <code>modelHeight</code> 是模型实际高度（米），<b>纯视觉，不要用于蓝图</b>。<br>
    边名用格坐标（<code>z=0</code> / <code>z=D-1</code> / <code>x=0</code> / <code>x=W-1</code>），
    只表示"口在这块地的哪条边"，<b>不声称游戏内绝对方位</b>。<br>
    角上的口会同时命中两条边。经验规律：加工机多为「进料在 <code>z=D-1</code> 边、出料在 <code>z=0</code> 边」，
    但并非全员适用，<b>以每座自己的示意为准</b>。<br>
    <b>⚠️ 矿机的出料口一律不画</b>（博士 2026-09-22 指出并追问「那这样 4 还用吗，玩家都是用无线传输的」）：
    配置表里矿机记着 3 个传送带出料口，但<b>两种模式都用不上</b> —— 默认<b>无线回传仓库</b>
    （电驱 / 二型电驱 / 水驱矿机；水驱是博士实机确认），切「仓储模式」也只是进<b>缓存区、手动取出</b>。
    所以示意图直接在建筑上标 <b>⇡ 无线回传仓库</b>（或便携源石矿机的 <b>⇥ 缓存区 · 手动收取</b>），
    不再画那 3 个用不上的口（数据仍保留在 <code>ports</code>）；水驱矿机的<b>管道进料口</b>是真的，照常画。
  </div><div class="list">`+arr.map(b=>{
    const o=openSet.has('p:'+b.id);
    return `<div class="card ${o?'open':''}" data-id="p:${esc(b.id)}">
      <div class="c-top">
        <span class="c-name">${esc(b.name)}</span>
        <span class="c-id">${esc(b.id)}</span>
        <span class="spacer"></span>
        <span class="c-cat ${(b.domainNames||[])[0]!=='全地区通用'?'acc':''}">${esc((b.domainNames||['全地区通用']).join('/'))}</span>
        <span class="c-cat">${esc(b.categoryName)}</span>
        ${b.hasPlaceLimit?'<span class="flag">有数量上限</span>':''}
      </div>
      <div class="c-sub">
        <span><b>占地 ${esc(b.gridFootprint)}</b> 格</span>
        <span>面积 ${b.gridArea} 格²</span>
        <span>格高 ${b.gridHeight}</span>
        <span>外圈 ${b.gridPerimeter} 格</span>
        <span>${b.isSquare?'正方形':'非正方形'}</span>
      </div>
      <div class="c-sub">
        <span>接口 ${b.portCount} 个（${esc(b.portSummary)}）</span>
        <span>${b.needPower?'耗电 '+b.powerConsume:'无需通电'}</span>
        ${b.liquidEnabled?'<span>支持液体</span>':''}
      </div>
      <div class="star">★ ${esc(b.layoutNote)}</div>
      ${o?`
      <div class="detail">
        ${b.portCount?gridHtml(b):'<div class="d-sec"><div class="empty">该设施没有物流接口</div></div>'}
        <div class="d-sec"><div class="d-h">蓝图属性</div>
          <div class="row"><span class="tag">占地方格 宽×深</span><span>${esc(b.gridFootprint)}</span></div>
          <div class="row"><span class="tag">占格高度</span><span>${b.gridHeight} 格</span></div>
          <div class="row"><span class="tag">模型高度（勿用于蓝图）</span><span>${b.modelHeight!=null?b.modelHeight+' m':'—'}</span></div>
          <div class="row"><span class="tag">占格面积 / 外圈周长</span><span>${b.gridArea} 格² / ${b.gridPerimeter} 格</span></div>
          <div class="row"><span class="tag">长宽比 / 尺寸档</span><span>${b.aspect||'—'} / ${esc(b.buildSizeClass||'—')}</span></div>
          <div class="row"><span class="tag">放置限制</span><span>${b.hasPlaceLimit?'有数量上限':'无'}</span></div>
          <div class="row"><span class="tag">进料口所在边</span><span>${esc(b.inputEdgeLabel)}</span></div>
          <div class="row"><span class="tag">出料口所在边</span><span>${esc(b.outputEdgeLabel)}</span></div>
          <div class="row"><span class="tag">进出是否同边</span><span>${b.mixedSides?'同一组边（走线需交错安排）':'不同边（可对向直连）'}</span></div>
        </div>
        ${b.portCount?`<div class="d-sec"><div class="d-h">接口明细（格坐标）</div>
          ${b.ports.map(p=>`<div class="row">
            <span class="tag ${p.kind==='input'?'acc':''}">${p.kind==='input'?'进':'出'} #${p.index}</span>
            <span>x=${p.x} y=${p.y} z=${p.z}</span>
            <span>${esc(p.edgeLabel)}</span>
            <span>${esc(p.medium)}</span>
          </div>`).join('')}
        </div>`:''}
      </div>`:''}
    </div>`;
  }).join('')+`</div>`;
}

/* ---------- 基地面积 / 建造上限 ----------
   这一页的数据来源和别页不一样：面积是社区实测、不是配置表。
   页面上必须把两类数据分开标注，别混着说。 */
function baseCards(){
  return DB.bases.areas.map(a=>`<div class="card">
      <div class="c-top">
        <span class="c-name">${esc(a.domainName)} · ${esc(a.kind)}</span>
        <span class="c-id">${esc(a.coreId)}</span>
        <span class="spacer"></span>
        <span class="c-cat acc">${esc(a.size)} = ${a.cells} 格</span>
      </div>
      <div class="c-sub">
        <span>建设区边长 <b>${a.side}</b> 格</span>
        <span>单边最多 <b>${a.slotsPerSide}</b> 路存取口</span>
        <span>扣掉 ${esc(a.coreName)} 9×9 → 可建 ${a.usableCells} 格</span>
      </div>
      <div class="c-sub">
        <span>可信度：${esc(a.confidence)}</span>
      </div>
      <div class="c-sub">
        <span>来源：${a.sources.map(s=>esc(s.id)+'· '+esc(s.site)+' · '+esc(s.author)+'（'+esc(s.date)+'）').join('　')}</span>
      </div>
    </div>`).join('');
}

function baseExpansionTable(){
  const zs=DB.bases.zones.filter(z=>z.hasBuiltArea&&(!f1||z.domainName===f1));
  if(!zs.length) return `<div class="empty">没有匹配的建造区</div>`;
  return `<div style="overflow-x:auto"><table class="lg-tb">
    <thead><tr>
      <th>建造区</th><th>所属据点</th><th>据点</th>
      <th class="r">区域扩大·一</th><th class="r">区域扩大·二</th>
      <th class="r">存取线档数</th><th class="r">全解锁合计</th>
    </tr></thead>
    <tbody>${zs.map(z=>{
      const e1=z.expansion[0]||{}, e2=z.expansion[1]||{};
      const total=(z.expansionCostTotal||0)+(z.busCostTotal||0);
      return `<tr>
        <td><b>${esc(z.zoneName)}</b> <span class="c-id">${esc(z.levelId)}</span></td>
        <td>${esc(z.domainName)}</td>
        <td>${esc(z.currency||'—')}</td>
        <td class="r">${e1.cost!=null?e1.cost:'—'}</td>
        <td class="r">${e2.cost!=null?e2.cost:'—'}</td>
        <td class="r">${z.busCount}</td>
        <td class="r">${total?total:'—'}</td>
      </tr>`;}).join('')}</tbody>
  </table></div>`;
}

function baseDevTables(){
  const ds=DB.bases.domains.filter(d=>!f1||d.name===f1);
  return ds.map(d=>{
    const zones=(d.levels[0]&&d.levels[0].regions)||[];
    return `<div class="d-h" style="margin-top:16px">${esc(d.name)}　据点发展等级 → 建造上限（满级 Lv${d.maxLevel}）</div>
    <div style="overflow-x:auto"><table class="lg-tb">
      <thead><tr>
        <th class="r">等级</th><th class="r">升级经验</th><th class="r">资金上限</th>
        ${zones.map(z=>`<th class="r">${esc(z.zoneName)}${z.buildable?'':' *'}</th>`).join('')}
      </tr></thead>
      <tbody>${d.levels.map(l=>`<tr>
        <td class="r"><b>${l.level}</b></td>
        <td class="r">${l.levelUpExp!=null?l.levelUpExp:'—'}</td>
        <td class="r">${l.moneyLimit!=null?l.moneyLimit:'—'}</td>
        ${zones.map(z=>{
          const r=(l.regions||[]).find(x=>x.levelId===z.levelId);
          if(!r) return '<td class="r">—</td>';
          return `<td class="r"><b>${r.bandwidth}</b> <span class="c-id">${r.battleBuildingLimit}/${r.travelPoleLimit}${r.mineOutputUp?'+矿':''}</span></td>`;
        }).join('')}
      </tr>`).join('')}</tbody>
    </table></div>`;}).join('');
}

/* 满级基地总览：每片基地一行（每个据点 1 主 + 3 副），全部按最大值取 */
function maxBaseTable(){
  const rows=DB.bases.maxBases||[];
  if(!rows.length) return `<div class="empty">没有基地数据</div>`;
  const cell=a=>{
    if(!a) return '<span class="c-id">—</span>';
    const bp=a.blueprint?`<br><span class="c-id">${esc(a.blueprint.note)}${a.slotMeasured?'':' · 路数推算'}</span>`:'';
    return `<b>${esc(a.size)} = ${a.cells} 格</b>`
      + `<br><span class="c-id">可建 ${a.usableCells} 格（扣掉核心 9×9）</span>${bp}`;
  };
  return `<div style="overflow-x:auto"><table class="lg-tb">
    <thead><tr>
      <th>基地</th><th>据点</th>
      <th>类型（核心）</th>
      <th class="r">建设区面积（满级）</th>
      <th class="r">单边存取口</th>
      <th class="r">满级<br>协议容量</th>
      <th class="r">防御建筑<br>/ 滑索</th>
      <th class="r">全解锁券</th>
    </tr></thead>
    <tbody>${rows.map(r=>{
      const a=r.area, c=r.caps||{};
      const isMain=r.role==='主基地';
      return `<tr>
        <td><b>${esc(r.zoneName)}</b> <span class="c-id">${esc(r.levelId)}</span></td>
        <td>${esc(r.domainName)}<br><span class="c-id">满级 Lv${r.maxDevLevel!=null?r.maxDevLevel:'—'}</span></td>
        <td><span class="c-cat ${isMain?'acc':''}">${esc(r.role)}</span>
            <br><span class="c-id">${esc(a?a.coreName:'—')}</span></td>
        <td class="r">${cell(a)}</td>
        <td class="r">${a?a.slotsPerSide:'—'}</td>
        <td class="r"><b>${c.bandwidth!=null?c.bandwidth:'—'}</b></td>
        <td class="r">${c.battleBuildingLimit!=null?c.battleBuildingLimit:'—'} / ${c.travelPoleLimit!=null?c.travelPoleLimit:'—'}${c.mineOutputUp?' <span class="c-id">+矿</span>':''}</td>
        <td class="r">${r.unlockCostTotal?r.unlockCostTotal+'<br><span class="c-id">'+esc(r.currency||'')+'</span>':'<span class="c-id">—</span>'}</td>
      </tr>`;}).join('')}</tbody>
  </table></div>`;
}

/* 谷地存取线示意图（实测）：只画「几条边排满」—— 方位随镜头旋转而变，
   沙盘已经能转镜头（LO.viewRot），按"几条边"摆就对得上，不需要固定标边。 */
function busSvgOne(z){
  const side=z.side||40;
  const S=Math.max(70,Math.round(side*1.5)), t=Math.max(5,Math.round(S*0.10));
  /* 游戏里的真实关系（博士 2026-09-21 实拍）：源桩自己占一角、和基段同宽，基段紧贴着它往两个方向延伸；
     副基地没有源桩，自动铺好的一条边横贯整个上边缘，直接用就行。源桩必须与基段条严丝合缝，不能凸出。 */
  const hasSrc=!!z.source;
  const src=t, o=hasSrc?src:0;
  let bars='';
  if(hasSrc){
    bars='<rect x="'+o+'" y="0" width="'+(S-o)+'" height="'+t+'" class="bus-bar"/>'    // 上边：紧贴源桩右侧
        +'<rect x="0" y="'+o+'" width="'+t+'" height="'+(S-o)+'" class="bus-bar"/>';   // 左边：紧贴源桩下方
  }else{
    bars='<rect x="0" y="0" width="'+S+'" height="'+t+'" class="bus-bar"/>';           // 副基地：整条上边
  }
  const srcRect=hasSrc?'<rect x="0" y="0" width="'+src+'" height="'+src+'" class="bus-src"/>':'';
  return '<svg viewBox="0 0 '+S+' '+S+'" width="'+S+'" height="'+S+'" '
    +'style="border:1px solid var(--line2);background:#FBFAF6;border-radius:4px;vertical-align:top">'
    +bars+srcRect
    +'</svg>';
}
function renderBase(){
  const B=DB.bases;
  const S=B.maxBasesSummary||{};
  const cost=Object.entries(S.unlockCostByCurrency||{}).map(([k,v])=>esc(k)+' '+v).join('　／　');
  const cellLine=Object.entries(S.cellsByDomain||{}).map(([k,v])=>
    esc(k)+' '+v.mainN+' 主 '+v.main+' 格 + '+v.subN+' 副 '+v.sub+' 格 = <b>'+v.total+' 格</b>').join('　／　');
  const bo=B.busObservations||{};
  const busSvg=((bo.zones||[]).length)?`
    <div class="d-sec" style="margin-top:16px"><div class="d-h">谷地存取线铺在基地哪几条边（实测 · 视角无关）</div>
      <div class="note" style="margin-bottom:10px">${esc(bo.note||'')}</div>
      <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start">
        ${bo.zones.map(z=>`<div style="text-align:center">
          ${busSvgOne(z)}
          <div style="font-size:12.5px;margin-top:5px">${esc(z.zoneName)}</div>
          <div class="c-sub" style="justify-content:center">${z.edges>=2?'源桩一角 · 相连两条边排满':'一条边自动铺满 · 贴放存取口即可'}</div>
        </div>`).join('')}
      </div>
      <div class="c-sub" style="margin-top:8px">
        <span>粗条 = 自动铺设的存取线</span>
        <span>角上的方块 = 源桩（只有枢纽区有，基段紧贴它延伸）</span>
        <span>副基地不用摆任何东西，自动铺好一条边，直接贴放存货口 / 取货口</span>
        <span>只记「几条边」—— 具体是哪条边随镜头变，在沙盘里按「旋转视角」转一下就对得上</span>
      </div>
    </div>`:'';
  return `<div class="note">
      <b>📐 基地面积与建造上限</b><br>${B.areaSourceNote}
    </div>
    <div class="d-sec" style="margin-top:16px"><div class="d-h">满级基地总览（每片基地一行 · 全部按最大值取）</div>
      <div class="note" style="margin-bottom:10px">${B.maxBasis}</div>
      <div class="note" style="margin-bottom:10px">${B.baseRoleNote}</div>
      <div class="note" style="margin-bottom:10px">${B.baseOnlyNote}</div>
      <div class="c-sub" style="margin-bottom:8px">
        <span>共 <b>${S.rows}</b> 片基地（${S.zonesTotal} 个建造区里只有这些有基地）</span>
        <span>主基地 <b>${S.mainCount}</b> 片 · 副基地 <b>${S.subCount}</b> 片</span>
        <span>满级协议容量合计 <b>${S.protocolCapacityTotal}</b></span>
        <span>地面格数合计 <b>${S.cellsTotal}</b> 格</span>
      </div>
      <div class="c-sub" style="margin-bottom:8px"><span>${cellLine}</span></div>
      <div class="c-sub" style="margin-bottom:8px"><span>全解锁券合计：${cost}（两种券，不能相加）</span></div>
      ${maxBaseTable()}
      <div class="c-sub" style="margin-top:8px">
        <span>「全解锁券」= 区域扩大·一/二 + 全部仓库存取线，同券累加</span>
        <span>「可建」= 扣掉核心本体 9×9 之后的地面格数</span>
      </div>
    </div>
    <div class="d-sec" style="margin-top:18px"><div class="d-h">各基地建设区域面积（按地区看 · 满级）</div>
      <div class="list">${baseCards()}</div>
    </div>
    <div class="note" style="margin-top:12px">
      <b>边长 ↔ 存取口路数</b>　${esc(B.slotRule.formula)}<br>${esc(B.slotRule.note)}
    </div>
    <div class="d-sec" style="margin-top:18px"><div class="d-h">面积 vs 蓝图上限</div>
      <div class="note" style="margin-bottom:10px">
        一张蓝图最大 <b>50×50 格 / 160 个节点</b>（配置表硬上限）。所以：
        武陵副基地（50×50）正好能被一张满规格蓝图铺满；
        四号谷地主基地（70×70）与武陵主基地（80×80）边长都超过 50，一张铺不满，得拼。
      </div>
      ${B.areaComparisons.map(c=>`<div class="row">
        <span class="tag">${esc(c.label)}</span><span>${esc(c.size)}</span>
        <span>${esc(c.note)}</span>
        ${c.exactMatch?'<span class="c-cat acc">正好一张蓝图</span>':''}
      </div>`).join('')}
    </div>
    <div class="d-sec" style="margin-top:18px"><div class="d-h">蓝图系统硬上限（配置表 FacBlueprintConst）</div>
      ${B.blueprintCaps.map(c=>`<div class="row">
        <span class="tag">${esc(c.label)}</span><span><b>${esc(c.value)}</b></span>
        <span class="c-id">${esc(c.key)}</span>
      </div>`).join('')}
    </div>
    <div class="d-sec" style="margin-top:18px"><div class="d-h">扩建价目（配置表 FactoryPanelStoreTable）</div>
      <div class="note" style="margin-bottom:10px">
        在集成管家里买。只列配置表里有扩建条目的建造区；
        「全解锁合计」= 区域扩大两档 + 全部仓库存取线（同一种券累加）。
      </div>
      ${baseExpansionTable()}
    </div>
    <div class="d-sec" style="margin-top:18px"><div class="d-h">据点发展等级 → 建造上限（配置表 DomainDataTable）</div>
      <div class="note" style="margin-bottom:10px">
        格内读法：<b>协议容量</b> <span class="c-id">防御建筑上限 / 滑索上限</span>；
        标 <b>+矿</b> 表示该等级起矿机产出提升。<br>
        列名带 <b>*</b> 的建造区<strong>没有基地</strong>（配置表里没有「区域扩大」条目）——
        表里的协议容量只约束该区的<strong>野外设备</strong>，与基地无关。
        有基地的只有上表那 8 个。
      </div>
      ${baseDevTables()}
    </div>
    <div class="d-sec" style="margin-top:18px"><div class="d-h">面积数据来源（社区实测，可逐条复核）</div>
      ${B.sources.map(s=>`<div class="row">
        <span class="tag acc">${esc(s.id)}</span>
        <span>${esc(s.title)}</span>
        <span>${esc(s.site)} · ${esc(s.author)} · ${esc(s.date)}</span>
      </div>
      <div class="row"><span class="tag"></span><span>${esc(s.claim)}</span></div>`).join('')}
    </div>
    <div class="note" style="margin-top:18px"><b>⚠ 数据边界（这些别当成配置表数据）</b></div>
    ${B.boundaries.map(b=>`<div class="row"><span class="tag">边界</span><span>${b}</span></div>`).join('')}
      ${busSvg}
  `;
}

/* ---------- 布局试摆：交互画布 ----------
   只在页面里摆占地，不做产线连线（连线数据不在配置表）。
   左栏选建筑 → 画布点击摆放；单击已放建筑选中、双击移除；
   空白处拖拽框选一批，拖动选中项整体移动；
   选中后 R 原地转 90°、Del 删除、Ctrl+D 复制、Ctrl+Z / Ctrl+Y 撤销重做。
   坐标靠 getBoundingClientRect 反算 —— 真实浏览器可用；vm 回归不触发事件，
   但 Lput/Lrot/Ldel/Lundo/Ldup 都是纯函数，回归脚本直接调它们做断言。 */
/* 格子边长（px）。2026-09-21 博士反馈「格子太小、物流件的流向箭头看不清」，
   默认值从 14 提到 20，并在工具栏加了 14/20/26/32 四档可以随时调。
   这个数同时决定：画布像素尺寸、鼠标坐标反算（Lxy）、框选橡皮筋、拖动预览位置，
   以及 .lo-canvas 的背景网格间距（经 CSS 变量 --locell 传过去）—— 改一处就得同步另一处。 */
let LOCELL=20;
let LO=null, LODRAG=null;
/* 物流件（传送带 / 管道 / 汇流分流 / 物流桥 / 阀门）不在 blueprint.buildings 里，
   它们来自 logistics.entities。这里包一层「和建筑同形」的外壳，
   让摆放 / 旋转 / 拖动 / 复制 / 删除 / 撤销整套逻辑原样复用，不用另开一条分支。 */
function Llogi(){ return (DB.logistics&&DB.logistics.entities)||[]; }
function LO_LG(e){
  return {id:e.id,name:e.name,categoryName:'物流件',gridFootprint:'1×1',gridArea:1,gridHeight:0,
    portCount:0,ports:[],isLogi:true,lgType:e.type,lgMedium:e.medium,
    lgInFacings:e.inputFacings||[],lgOutFacings:e.outputFacings||[],
    lgPerMin:e.unitsPerMinute,lgPerSec:e.unitsPerSecond};
}
function byBp(id){
  const b=DB.blueprint.buildings.find(x=>x.id===id);
  if(b) return b;
  const e=Llogi().find(x=>x.id===id);
  return e?LO_LG(e):null;
}
/* ⭐v104 气体散布机：范围/气体来自 FactoryVaporizerTable（rangeExtend + gasGroups）。
   ENV_HEX 按**游戏 UI 实拍**校准（博士 2026-09-23 截图「本设备可生成的环境一览」）：
   稳定=青蓝 / 湿润=白 / 酸性=橙黄 / 息壤=翠绿。
   ⚠️ v103 曾按特效资源名 P_fxfac_vaporizer_scope_<色>_ 的颜色词猜色，把稳定/湿润对反了 ——
   资源名是内部命名（white/blue 指特效白模/模板），**不是**显示色；仍保留在 envDisplay.color 里做溯源。
   键直接用 GenEnv 1-4（博士问「哪来的第五种」：gray 只是查不到时的防御性兜底，游戏只有 4 种环境）。 */
const ENV_HEX={1:'#3D9FD8',2:'#F4F7F8',3:'#E7AC3F',4:'#43B06E',gray:'#B4B2A9'};
const ENV_EDGE={1:'#1B6E9E',2:'#93A8B4',3:'#96660F',4:'#1F7040',gray:'#5F5E5A'};
const ENV_NAME={1:'稳定',2:'湿润',3:'酸性',4:'息壤'};
/* 白圈（湿润）在浅色画布上几乎隐形 —— 给它专属的不透明度，其余维持轻透 */
const ENV_OP={1:0.17,2:0.45,3:0.17,4:0.17,gray:0.17};
function vaporizerOf(b){ return (b&&b.vaporizer)||null; }
/* ⭐v148 供电范围：FactoryPowerPoleTable 的 rangeExtend 与气体散布机**同字段、同口径**（外扩 N 格）。
   供电桩/息壤供电桩（本体 2×2）±5 → 12×12；中继器/息壤中继器 ±2 → 7×7（y 是高度，水平范围只看 x/z）。 */
function powerPoleOf(b){ return (b&&b.powerPole)||null; }
function envColorOf(env){ return ENV_HEX[env]||ENV_HEX.gray; }
function envEdgeOf(env){ return ENV_EDGE[env]||ENV_EDGE.gray; }
function envOpOf(env){ return ENV_OP[env]||ENV_OP.gray; }
function envGasName(env){ const b=byBp('vaporizer_1'); const g=b&&b.vaporizer&&((b.vaporizer.gasGroups||[]).find(x=>x.env===env)); return g?g.name:('环境 '+env); }
/* 环境圈边长（格）：占地 外扩*2；返回 [宽, 深, 外扩] */
function vaporizerSide(b){ const vp=vaporizerOf(b); const ext=(vp&&vp.rangeExtend&&vp.rangeExtend.x)||0; const fp=Lfp(b); return [fp[0]+ext*2, fp[1]+ext*2, ext]; }
/* ⭐v109 协议核心出货（博士 2026-09-23：「游戏里的协议核心出货口可以点击选择物品出货」+
   「内部空白面积大，选货能不能在内部给个机器口对应的箭头什么的」）。
   数据来自构建期注入的 DB.hubItems（raw/FactoryItemTable.deliverItemTypeList 非空者，
   key = 物品 id，value = {name, rarity, domains}）；domains 里的域决定**哪台核心**能出它。
   一个基地同时只有一台协议核心，所以「本核心可出货清单」= 该核心所属域的物品。
   域怎么定：核心摆在哪个基地 → 基地的 domainName 反查 DB.bases.domains（四号谷地/武陵）。 */
function hubIsHub(b){ return !!b&&b.id==='sp_hub_1'; }
/* 当前摆放里那台协议核心（一台核心 = 一个基地，取第一台即可） */
function hubObj(){ const L=Linit(); return L.objs.filter(o=>{ const b=byBp(o.id); return hubIsHub(b); })[0]||null; }
/* 这台核心属于哪个域：基地（L.base 是 levelId）→ 地区名 → 域 id。
   ⚠️ 必须用页面自己的 Lbases()（8 条基地、带 levelId），不能用 DB.bases.areas ——
   areas 只有 4 条且**没有 levelId**（v109 首版踩过，武陵基地永远匹配不上，测试抓到）。
   没选基地时退回出货方向下拉的出发地。 */
function hubDomainOf(o){
  const L=Linit();
  const base=(Lbases()||[]).filter(x=>x.levelId===L.base)[0]||null;
  const dn=base&&base.domainName;
  const doms=(DB.bases&&DB.bases.domains)||[];
  const hit=doms.filter(d=>d.name===dn)[0];
  if(hit) return hit.id;
  return LshipFromId?LshipFromId():'domain_1';
}
function hubDomainName(id){ const d=((DB.bases&&DB.bases.domains)||[]).filter(x=>x.id===id)[0]; return d?d.name:String(id||''); }
/* 该核心可出货物品（按稀有度降序、同名相邻；只在需要时算，几十条量级） */
function hubCands(domId){
  const out=[];
  const all=DB.hubItems||{};
  Object.keys(all).forEach(iid=>{
    const v=all[iid];
    /* ⭐v127：ct = 灌装物标注（构建期 content 字段，「装：水蒸气（气态）」/「空容器（可灌装）」）。
       瓶罐类物品在配置表里全是同一个名字（紫晶质瓶 ×10+），只有 content 能分清装了什么。 */
    if((v.domains||[]).indexOf(domId)>=0) out.push({id:iid, name:v.name||iid, rarity:v.rarity||1,
      ct:(DB.items&&DB.items[iid]&&DB.items[iid].content)||''});
  });
  out.sort((a,b)=> (b.rarity-a.rarity)||(a.name<b.name?-1:a.name>b.name?1:0));
  return out;
}
/* ⭐ 只允许**出料口**（input 口是进料的，出货挂在 output 口上）。
   也顺手把 hasPlaceLimit 之类不相关的口排除掉 —— 核心只有传送带口，无需过滤介质。 */
function hubPicksOf(o){ const L=Linit(); return (L.hubPicks&&L.hubPicks[o.uid])||{}; }
function hubPickGet(o,idx){ const m=hubPicksOf(o); return m[idx]||''; }
function hubPickSet(uid,idx,itemId){
  const L=Linit(); if(!L.hubPicks) L.hubPicks={};
  if(!L.hubPicks[uid]) L.hubPicks[uid]={};
  if(itemId) L.hubPicks[uid][idx]=itemId; else delete L.hubPicks[uid][idx];
}
function hubPickItem(o,idx){ const iid=hubPickGet(o,idx); return iid?((DB.hubItems||{})[iid]||null):null; }
/* 稀有度 → 星串（列表里用，纯字符不给字号列表加样式负担） */
function hubStars(r){ r=Math.max(1,Math.min(6,r|0)); return '★'.repeat(r); }
/* 打开某台核心的出料口选货清单 */
/* ⭐v123（博士「鼠标一移动到机器口上就只能选择物品」）：手里拿着东西时点出货箭头
   不再弹选货浮层 —— 手拿物流件时 mousedown 已分流去「口格拉线」（见 LonMouseDown），
   但 mouseup 后 click 照样派发到箭头的 onclick，不拦会把刚起手的线头顶出浮层。
   ⭐v125（博士「又选不了货了」）：守卫收窄为只拦物流件 —— Lput 摆放成功后 pick 不清
   （连续摆放交互），摆完核心手里还拿着核心，v123 的 if(L.pick) 把手拿建筑点箭头选货
   也拦死了；选货是核心属性操作，手拿建筑不冲突。 */
function LdlvOpen(uid,idx){
  const L=Linit();
  if(L.pick&&L.pick.isLogi) return;
  /* ⭐v126：q=搜索词、rare=稀有度筛选（0=全部）。⭐v127：jar=只看瓶罐（0/1）。
     每次新开浮层重置，LdlvPick 后的 render 会保留（连续配货时筛选不丢）。
     旧数据态没这些字段时读取侧用 || 兜底。 */
  L.dlvPop={uid:uid, idx:idx, q:'', rare:0, jar:0}; render();
}
function LdlvClose(){ const L=Linit(); L.dlvPop=null; render(); }
/* ⭐v135「点机器就地选」（博士 2026-09-24：「我要在这里选，要做到以后能逐步完善到其他基建都能在这里选」）：
   单击沙盘上的机器 → 机器正上方弹出该机器的**选择浮层**（游戏同款交互）。
   浮层内容按机器类型分派（RmacPanelOf）——新增基建只需在分派里加一个分支。
   与协议核心出货浮层（dlvPop）同一套定位/样式语言。 */
function LmacOpen(uid){ const L=Linit(); L.macPop={uid:uid}; render(); }
function LmacClose(){ const L=Linit(); L.macPop=null; render(); }
function LmacHasPanel(uid){
  const L=Linit(); const o=L.objs.filter(x=>x.uid===uid)[0];
  return !!(o&&RmacPanelOf(byBp(o.id), o));
}
/* ⭐v135 「就地选」总分派：按建筑类型返回该机器的选择面板 HTML（null = 这台没得选）。
   ⬇️ 以后支持新基建，在这里加分支即可。 */
function RmacPanelOf(b, o){
  if(!b) return null;
  if(RisPool(b)) return RmacPoolHtml(b, o);              /* 反应池 / 扩容池：缓存格 + 输出产物槽 */
  if(b.lgType==='BoxValve'||b.lgType==='FluidValve') return RmacValveHtml(b, o);   /* ⭐v138 准入口 */
  if(Rof(b.id).length) return RmacRecipeHtml(b, o);      /* 其他有配方的机器：配方选择 */
  return null;
}
/* ⭐v138 准入口面板（博士：「准入口可以选择准入物品…像上面反应池和协议核心那样在画布中选择」+
   「准入口还可以进行限速」）：
   · 限速档位 = 6/分一档；**传送带最高 30、管道最高 60**（社区/攻略核实；管速本身 120，准入口限不到 120）
   · 准入物品 = 允许通过的材料（多选；被拦的料会堵线，所以默认「不限」）
   · 计算口径：过滤**不影响**排布器（一条依赖一条线，不混线）；**限速影响**——该段上限 = min(线速, 限速)。 */
const VALVE_MAX={'log_conditioner':30,'log_pipe_conditioner':60};
function RmacValveHtml(b, o){
  const max=VALVE_MAX[b.id]||30, cur=+o.vRate||0;
  const rOpts=[0]; for(let r=6;r<=max;r+=6) rOpts.push(r);
  const allItems=Object.keys(DB.items||{}).sort((x,y)=>String((DB.items[x]||{}).name).localeCompare(String((DB.items[y]||{}).name),'zh'));
  const sel=o.vItems||[];
  return `
      <div class="c-sub" style="margin-top:2px"><span>类型：<b>${esc(b.name)}</b>（${esc(b.lgMedium)}·1×1）· 必须放在${esc(b.lgMedium)}上、顺着物流方向</span></div>
      <div class="c-sub" style="margin-top:6px"><span><b>限速</b>（6/分一档${max===30?'，传送带最高 30':'，管道最高 60'}）</span></div>
      <select class="lo-sel" style="width:100%;margin-top:4px" onchange="LsetValveRate('${o.uid}', this.value)">
        ${rOpts.map(r=>`<option value="${r}"${cur===r?' selected':''}>${r?r+'/分':'不限（= 线速上限）'}</option>`).join('')}
      </select>
      <div class="c-sub" style="margin-top:8px"><span><b>准入物品</b>（只允许这些通过；<b>不选 = 不限</b>。被拦的料会堵住后面 —— 混线才需要它）</span></div>
      <select multiple size="6" class="lo-sel" style="width:100%;margin-top:4px"
        onchange="LsetValveItems('${o.uid}', Array.prototype.map.call(this.selectedOptions,function(x){return x.value;}))">
        ${allItems.map(id=>`<option value="${esc(id)}"${sel.indexOf(id)>=0?' selected':''}>${esc((DB.items[id]||{}).name||id)}</option>`).join('')}
      </select>
      <div class="c-sub" style="margin-top:6px"><span class="c-id">共 ${allItems.length} 件可选 · 已选 ${sel.length} 件${sel.length?'：'+sel.map(id=>esc((DB.items[id]||{}).name||id)).join('、'):''}</span></div>
      <div class="c-sub" style="margin-top:6px"><span class="c-id">对排布器计算的影响：准入过滤<b>不影响</b>（一条依赖一条线，不混线）；限速<b>影响</b> —— 该段实际上限 = min(线速, 限速)，限到 12/分就是这条线的天花板。</span></div>`;
}
function LsetValveRate(uid, r){
  const L=Linit(), o=L.objs.filter(x=>x.uid===uid)[0];
  if(!o) return;
  Lpush(); o.vRate=+r||0;
  L.msg='准入口限速已设为 '+(o.vRate?o.vRate+'/分':'不限（= 线速上限）');
  render();
}
function LsetValveItems(uid, ids){
  const L=Linit(), o=L.objs.filter(x=>x.uid===uid)[0];
  if(!o) return;
  Lpush(); o.vItems=(ids||[]).slice();
  L.msg='准入物品已设为 '+(o.vItems.length?o.vItems.length+' 件':'不限');
  render();
}
/* 反应池面板（单机版；左栏那份已撤，就地选是唯一入口） */
function RmacPoolHtml(b, o){
  const slots=POOL_SLOT_MAX[b.id], rl=RpoolOf(o);
  const cells=RpoolCells(rl), over=cells.length>POOL_CELLS;
  const PH={'固态':['#8A8778','固'],'液态':['#2E8B9E','液'],'气态':['#7BA05B','气']};
  const cellBox=(c,i)=>{
    if(!c) return `<span class="lo-ccell empty">空</span>`;
    const ph=PH[c.phase]||['#8A8778','?'], overOne=over&&i>=POOL_CELLS;
    return `<span class="lo-ccell${overOne?' over':''}"
      title="${esc(c.name)} · R${c.rarity} · ${esc(c.phase)}${overOne?'（超出 '+POOL_CELLS+' 格）':''}">
      <span class="rr">${'★'.repeat(Math.max(1,Math.min(6,c.rarity|0)))}</span>
      <span class="nm">${esc(c.name)}</span>
      <span class="ph" style="background:${ph[0]}">${ph[1]}</span></span>`;
  };
  return `
      <div class="c-sub" style="margin-top:2px"><span><b>缓存格</b>：占了 <b style="color:${over?RW_COL.bad:'inherit'}">${cells.length}</b>/${POOL_CELLS}（按已选反应的进料 + 出料去重推演）</span></div>
      <div class="lo-ccells">
        ${Array.from({length:Math.max(POOL_CELLS,cells.length)},(_,i)=>cellBox(cells[i],i)).join('')}
      </div>
      ${over?`<div class="c-sub" style="margin-top:4px"><span style="color:${RW_COL.bad}">⚠️ 超过 ${POOL_CELLS} 格 —— 游戏里这些料塞不进一栋，删掉一条反应或分成两栋</span></div>`:''}
      <div class="c-sub" style="margin-top:8px"><span><b>输出产物</b>（每个槽一条反应；同一条反应重复选不会提速，要提产请加栋数）</span></div>
      <div style="display:flex;flex-direction:column;gap:4px;margin-top:4px">
        ${Array.from({length:slots},(_,i)=>{
          const rid=rl[i]||'', rr=rid?RbyId(rid):null, rt=rr?Rrate(rr):null;
          return `<div style="display:flex;align-items:center;gap:5px">
            <span class="lo-tag" style="flex:none">槽 ${i+1}</span>
            <select class="lo-sel" style="flex:1;min-width:0" onchange="LsetPoolSlot(${i}, this.value, '${o.uid}')">
              <option value=""${rid?'':' selected'}>— 空 —</option>
              ${Rof(b.id).map(r=>`<option value="${esc(r.id)}"${rid===r.id?' selected':''}>${esc(Rsummary(r))}</option>`).join('')}
            </select>
            <span class="c-id" style="white-space:nowrap">${rt?('出 '+rt.out.map(x=>esc(x.name)+' '+x.perMin+'/分').join('、')):'—'}</span>
          </div>`; }).join('')}
      </div>
      <div class="c-sub" style="margin-top:6px"><span class="c-id">缓存格是静态推演（该栋各反应的料去重），不代表游戏内实时时序；同池并行的栋数口径见产线闭环报告。</span></div>`;
}
/* 通用配方面板（单机版）——「以后其他基建都能在这里选」的通用形态 */
function RmacRecipeHtml(b, o){
  const rs=Rof(b.id);
  const rec=o.r?RbyId(o.r):null, rt=rec?Rrate(rec):null;
  return `
      <div class="c-sub" style="margin-top:2px"><span>可选 <b>${rs.length}</b> 条配方</span></div>
      <select class="lo-sel" style="width:100%;margin-top:4px" onchange="LsetRecipe(this.value, '${o.uid}')">
        <option value=""${o.r?'':' selected'}>— 未指定 —</option>
        ${rs.map(r=>`<option value="${esc(r.id)}"${o.r===r.id?' selected':''}>${esc(Rsummary(r))}</option>`).join('')}
      </select>
      ${rt?`<div class="c-sub" style="margin-top:6px"><span>单台产能 <b>${rt.out.map(x=>esc(x.name)+' '+x.perMin+'/分').join('、')}</b> · ${rt.seconds} 秒/轮 · ${rt.roundsPerMin} 轮/分</span></div>`:''}`;
}
/* ⭐v126 选货浮层搜索 + 稀有度筛选（博士「东西几百个太多了」——281 件翻不动）：
   oninput / 点 chip 只走轻量 DOM 过滤（LdlvRefilter），**不走 render** —— render
   重建整个画布 DOM，输入框每敲一个字就丢焦点。状态存 L.dlvPop（q/rare/jar），选中
   物品后的 render 用同状态服务端过滤重绘，筛选跨 render 保持。
   ⭐v127（博士「你这里全是一样的瓶罐」）：搜索口径扩到灌装物标注 ct —— 「紫晶质瓶」
   同名 ×10+ 只有 content 能分清，搜「息壤」要能命中「装：息壤液」的那瓶。 */
function LdlvRefilter(){
  const L=Linit(), pop=L.dlvPop; if(!pop) return;
  const root=document.querySelector('.lo-dlvpop'); if(!root||!root.querySelector) return;
  const q=String(pop.q||'').trim().toLowerCase(), rr=pop.rare||0, jr=pop.jar||0;
  const list=root.querySelector('.lo-dlvplist');
  if(!list) return;
  const its=list.querySelectorAll('.it');
  let n=0;
  for(let i=0;i<its.length;i++){
    const el=its[i];
    const _nm=String(el.getAttribute('data-nm')||''), _ct=String(el.getAttribute('data-ct')||'');
    const okQ=!q||(_nm+' '+_ct).toLowerCase().indexOf(q)>=0;
    const okR=!rr||String(el.getAttribute('data-rr')||'')===String(rr);
    const okJ=!jr||el.getAttribute('data-jar')==='1';
    const show=okQ&&okR&&okJ;
    el.style.display=show?'':'none';
    if(show) n++;
  }
  const ct=root.querySelector('.ft .ct');
  if(ct) ct.textContent=n+' / '+its.length+' 件';
  const btns=root.querySelectorAll('.ft .cbtn');
  for(let i=0;i<btns.length;i++){
    const b=btns[i];
    const r=b.getAttribute('data-r');
    if(r!=null) b.className='cbtn'+((String(rr)===r)?' on':'');
    else if(b.getAttribute('data-j')!=null) b.className='cbtn'+((jr?' on':''));
  }
}
function LdlvSetQ(v){ const L=Linit(); if(!L.dlvPop) return; L.dlvPop.q=v; LdlvRefilter(); }
function LdlvSetR(v){ const L=Linit(); if(!L.dlvPop) return; L.dlvPop.rare=(parseInt(v,10)||0); LdlvRefilter(); }
function LdlvSetJ(v){ const L=Linit(); if(!L.dlvPop) return; L.dlvPop.jar=v?1:0; LdlvRefilter(); }
/* ⭐v127 瓶罐判定：名字含瓶/罐（药品瓶、罐头）**或**有灌装物标注（气罐/灌装瓶）。
   单用名字会漏 content 系（部分耐压罐命名不含罐字时），单用 content 会漏药品瓶。 */
function LdlvIsJar(it){ return !!(it&&(String(it.name).indexOf('瓶')>=0||String(it.name).indexOf('罐')>=0||it.ct)); }
function LdlvPick(uid,idx,itemId){
  const L=Linit();
  const cur=L.hubPicks&&L.hubPicks[uid]?L.hubPicks[uid][idx]:'';
  const same=cur===itemId;                            // 再点同一件 = 取消
  hubPickSet(uid,idx, same?'':itemId);
  const it=itemId?((DB.hubItems||{})[itemId]||{}):null;
  L.msg=same?('出料口 #'+idx+' 已取消出货物品')
            :('出料口 #'+idx+' → '+((it&&it.name)||itemId));
  render();
}
/* 走向命名：本页把 0° 定义成 +x（画布向右），顺时针每 90° 一档。
   这纯粹是本画布内部的走向记号 —— 配置表没把 x/z 轴对应到游戏内绝对方位（同「接口边名」的说明），
   所以不声称这是游戏里的朝向。 */
function LdirName(rot){ return ({0:'右',90:'下',180:'左',270:'上'})[((rot%360)+360)%360]||'右'; }
function LrotFrom(a,b){
  if(b[0]>a[0]) return 0;
  if(b[1]>a[1]) return 90;
  if(b[0]<a[0]) return 180;
  return 270;
}
function LfreeIn(list,x,y){
  for(let i=0;i<list.length;i++){
    const q=list[i];
    if(x<q.x+q.w&&x+1>q.x&&y<q.y+q.d&&y+1>q.y) return false;
  }
  return true;
}
/* 接口朝外的方向：取该接口格压在占地方框的哪条边上。
   角上的接口两条边都算，这里固定取 z 边（配置表里进料口压倒性多在 z=D-1 边）。
   ⚠ 只对 rot=0 的原始接口坐标有效 —— 旋转后的坐标请用 LportDirRot。 */
function LportDir(q,W,D){
  const onX=(q.x===0||q.x===W-1), onZ=(q.z===0||q.z===D-1);
  if(onX&&!onZ) return q.x===0?'l':'r';
  if(onZ) return q.z===0?'u':'d';
  return '';
}
/* ⭐v122：接口朝向跟着 rot 转，不再对旋转后的格子重新贴边猜。
   事故（博士实测截图「旋转个方向进出货口就不齐了」）：旧代码对 LportXY 转完的坐标
   再调 LportDir —— 角上的口两条边都压、固定取 z 边，rot=0 时进料口数据恰好在 z 边
   所以猜对；机器一转，口的位置被转到了 x 边，贴边猜仍返回 z 边方向 → 朝向全错，
   「口外那一格」算错，端点吸附 / 从口拉线 / 自动布线全都不齐。
   修法：rot=0 时对**原始**坐标判一次 base 朝向（口径与旧逻辑完全一致，rot=0 行为不变），
   之后方向按顺时针步进转 n 次 —— 'd'→'l'→'u'→'r'→'d'，与 LportXY 的 (x,z)->(D-1-z,x)
   是同一套旋转（底边中点转到左边中点，'d' 的口转完朝 'l'）。
   顺带考察过配置表 facing 字段：同座精炼炉左墙管道进口与右墙管道出口 facing 都是 90，
   说明它是模型局部参数、不是「朝外方向」，不可靠，不采用。 */
const LOGI_PORT_STEP={d:'l', l:'u', u:'r', r:'d'};
function LportDirRot(p,rot,w0,d0){
  let dir=LportDir(p,w0,d0);
  const n=((rot/90)%4+4)%4;
  for(let k=0;k<n;k++) dir=LOGI_PORT_STEP[dir]||dir;
  return dir;
}
/* 某个接口外侧那一格有没有同类物流件 —— 有就是「接上了」
   ⭐v152：idx 已按「格 × 介质」双索引（'p:x,y'/'b:x,y'），键位天然介质对齐 */
function LlogiAt(idx,x,y,isPipe){
  const o=idx[(isPipe?'p':'b')+':'+x+','+y];
  if(!o) return false;
  const b=byBp(o.id);
  return !!b&&!!b.isLogi&&((!!isPipe)===(b.lgMedium==='管道'));
}
function Linit(){
  if(!LO) LO={size:50,pick:null,pickRot:0,objs:[],sel:[],undo:[],redo:[],seq:0,msg:'',lastT:0,lastUid:'',showPort:true,showGas:true,showPwr:true,zone:'',viewRot:0,base:'',plan:null,plans:[],tgt:'item_iron_cmpt',rate:10,selfLoop:false,shipIn:false,tv:0,tvHours:1,mt:[],shipPick:'',shipCands:[],shipDmap:null,shipRawSet:null,
    /* ⭐⑥-3 收货方向（2026-09-22 博士：两地对称互传，现在用谷地→武陵；下拉为未来新地区留口） */
    shipFrom:'domain_1', shipTo:'domain_2', pickShow:false,
      /* ⭐v144 建筑清单默认收起（博士：那 45 项的大块一直摊在画布上方，换基建很麻烦） */
      palOpen:false,
    /* ⭐v109 协议核心出货：{uid:{口index:物品id}} + 当前打开的选货浮层 {uid,idx} */
    hubPicks:{}, dlvPop:null,
    /* ⭐v145 多基地：基地级字段（LO_BASE_KEYS）按基地各存一份 —— 上面那几个同名字段
       会被 LbaseHook() 用访问器接管，读写都落到 bases[当前基地] 上。 */
    bases:{}};
  LbaseHook();
  return LO;
}
/* ⭐v145 多基地状态（Wave 1）
   问题：单画布状态字段在页面里有 142 处引用，逐个改成「按基地取」等于全量重构。
   做法：把这 8 个字段改成访问器，读写自动落到 bases[L.base||''] 上 ——
        调用点一行不动，而「切基地」只要改 L.base 指针就完成了保存/恢复。
   哪些是基地级：画布尺寸、摆放内容、选中、镜头角度、产线方案与快照、协议核心出货口、选货浮层。
   哪些**不是**（全局）：base 是活跃指针；undo/redo 是**操作历史**（否则「撤销切基地」跨不回上一个基地，
   既有测试正是这个语义）；pick/pickRot 是手里拿着的件；显示开关与产线目标参数跨基地共享。 */
const LO_BASE_KEYS=['size','objs','sel','viewRot','plan','plans','hubPicks','dlvPop'];
/* 取「当前活跃基地」的存储位；首次访问某基地时按它的建设区边长开一张干净画布 */
function LbaseSlot(){
  const L=LO, k=L.base||'';
  let st=L.bases[k];
  if(!st){
    const r=Lbases().filter(x=>x.levelId===k)[0];
    st=L.bases[k]={size:(r&&r.side)||50, objs:[], sel:[], viewRot:0,
                   plan:null, plans:[], hubPicks:{}, dlvPop:null};
  }
  return st;
}
function LbaseHook(){
  LO_BASE_KEYS.forEach(k=>{
    Object.defineProperty(LO, k, {
      configurable:true, enumerable:true,
      get(){ return LbaseSlot()[k]; },
      set(v){ LbaseSlot()[k]=v; }
    });
  });
}
/* 占地规格：rot 为 90/270 时宽进深互换（与游戏内旋转一致） */
function Lfp(b){
  const fp=String(b.gridFootprint||'').split('×');
  return [fp[0]|0, fp[1]|0];
}
function Ldims(b,rot){
  const fp=Lfp(b);
  return (rot===90||rot===270) ? {w:fp[1],d:fp[0]} : {w:fp[0],d:fp[1]};
}
/* 接口格坐标按 rot 顺时针旋转： (x,z) -> (d-1-z, x)，同时宽深互换 */
function LportXY(p,rot,w0,d0){
  let x=p.x, z=p.z, W=w0, D=d0;
  const n=(rot/90)%4;
  for(let k=0;k<n;k++){
    const nx=D-1-z, nz=x;
    x=nx; z=nz;
    const t=W; W=D; D=t;
  }
  return {x:x,z:z};
}
function Lmk(b,x,y,rot){
  const L=Linit(); L.seq++;
  const dm=Ldims(b,rot);
  const o={uid:'o'+L.seq, id:b.id, x:x, y:y, rot:rot, w:dm.w, d:dm.d};
  /* ⭐v103：散布机落位默认通惰气（GenEnv 1，白圈）—— 有个可见的默认态，选中后可切 */
  if(vaporizerOf(b)) o.gas=1;
  return o;
}
/* ---- 撤销 / 重做：整块快照（尺寸 + 摆放），最简单也最不容易错（单页几十座量级） ---- */
function Lsnap(){ const L=Linit(); return JSON.stringify({size:L.size, base:L.base, objs:L.objs}); }
function Lpush(){
  const L=Linit();
  L.undo.push(Lsnap());
  if(L.undo.length>80) L.undo.shift();
  L.redo.length=0;
}
function Lapply(s){
  const L=Linit(), d=JSON.parse(s);
  /* ⭐v145 顺序要紧：基地级字段是访问器，先写 size 会落到**当前**基地上；
     必须先切 base 指针，再把快照的尺寸/内容写进那个基地（否则「撤销切基地」会把尺寸写错格子）。 */
  L.base=d.base||''; L.size=d.size; L.objs=d.objs;
  L.sel=L.sel.filter(u=>L.objs.some(o=>o.uid===u));
}
function Lundo(){
  const L=Linit();
  if(!L.undo.length){ L.msg='没有可撤销的操作'; render(); return; }
  L.redo.push(Lsnap()); Lapply(L.undo.pop()); L.msg='已撤销'; render();
}
function Lredo(){
  const L=Linit();
  if(!L.redo.length){ L.msg='没有可重做的操作'; render(); return; }
  L.undo.push(Lsnap()); Lapply(L.redo.pop()); L.msg='已重做'; render();
}
function LselObjs(){ const L=Linit(); return L.objs.filter(o=>L.sel.indexOf(o.uid)>=0); }
/* ---------- 局部锁定（路线图 ⑤-1，2026-09-22）----------
   锁 =「这台我满意了，别动它」。两层含义：
   ① 交互保护：拖动 / 删除 / 旋转 / 复制 一律跳过锁定件 —— 手调好的东西不会被误操作带走；
   ② 重排约束：「重排其余」把锁定件当固定件，其余机器重新分层摆位并绕开它们，管线整条重铺。
   ⚠️ 锁定只对**机器**有意义：管线是排布器算出来的产物，重排时一定重铺（按钮会提示）。 */
function LlockSel(on){
  const L=Linit();
  const sel=LselObjs();
  if(!sel.length){ L.msg='先选中要'+(on?'锁定':'解锁')+'的件（单击选中 / 空白处拖拽框选）'; render(); return; }
  const ch=sel.filter(o=>(!!o.lock)===!on);
  if(!ch.length){ L.msg='选中的 '+sel.length+' 个件本来就是「'+(on?'已锁定':'未锁定')+'」的'; render(); return; }
  Lpush();
  ch.forEach(o=>{ if(on) o.lock=true; else delete o.lock; });
  L.msg=(on?'已锁定 ':'已解锁 ')+ch.length+' 个件'
    +(on?'（锁定后：拖不动 / 删不掉 / 转不了；「重排其余」时位置不动）':'');
  render();
}
function LunlockAll(){
  const L=Linit();
  const n=L.objs.filter(o=>o.lock).length;
  if(!n){ L.msg='当前没有锁定的件'; render(); return; }
  Lpush();
  L.objs.forEach(o=>{ delete o.lock; });
  L.msg='已解锁全部 '+n+' 个件（可撤销）'; render();
}
/* 能不能放：界内 + 不与 ign 之外的建筑重叠 */
function Lfree(x,y,w,d,ign){
  const L=Linit();
  if(x<0||y<0||x+w>L.size||y+d>L.size) return false;
  for(let i=0;i<L.objs.length;i++){
    const o=L.objs[i];
    if(ign&&ign.indexOf(o.uid)>=0) continue;
    if(x<o.x+o.w&&x+w>o.x&&y<o.y+o.d&&y+d>o.y) return false;
  }
  return true;
}
/* ⭐v148 供电范围层开关 */
function LtogglePwr(){ const L=Linit(); L.showPwr=!L.showPwr; render(); }
/* ⭐v148 待放置供电范围预览：手拿供电桩/中继器悬在画布上时，光标处浮出范围预览（不 re-render）。
   博士：「放的时候怎么确定设备在不在供电范围里」—— 这就是答案。放下（pick 清空）或离开画布即消失。 */
let LpwrPreEl=null;
function LpwrPreMove(e){
  if(typeof tab==='undefined'||tab!=='layout'){ if(LpwrPreEl){LpwrPreEl.remove();LpwrPreEl=null;} return; }
  const L=Linit();
  const pp=powerPoleOf(L.pick);
  const c=pp?document.querySelector('.lo-canvas'):null;
  if(!c||!LOCELL){ if(LpwrPreEl){LpwrPreEl.remove();LpwrPreEl=null;} return; }
  const p=Lxy(e,c);
  const ext=(pp.rangeExtend&&pp.rangeExtend.x)||0;
  const fp=Lfp(L.pick);
  const w=(fp[0]+ext*2)*LOCELL, h=(fp[1]+ext*2)*LOCELL;
  const cx=Math.floor(p.fx), cy=Math.floor(p.fy);
  if(!LpwrPreEl){ LpwrPreEl=document.createElement('div'); LpwrPreEl.className='lo-pwr lo-pwr-pre'; c.appendChild(LpwrPreEl); }
  LpwrPreEl.style.left=((cx-Math.floor(fp[0]/2)-ext)*LOCELL)+'px';
  LpwrPreEl.style.top=((cy-Math.floor(fp[1]/2)-ext)*LOCELL)+'px';
  LpwrPreEl.style.width=w+'px';
  LpwrPreEl.style.height=h+'px';
  LpwrPreEl.style.display='block';
}
if(typeof document!=='undefined'&&document&&typeof document.addEventListener==='function'){
  document.addEventListener('mousemove',LpwrPreMove);
}
function Lpick(id){
  const L0=Linit(); L0.palOpen=false;   /* ⭐v144 选完建筑自动收起清单（画布让位） */
  const L=Linit(); L.pick=byBp(id);
  L.msg=L.pick&&L.pick.isLogi?'物流件：在空白格按住拖动可一次铺一排；R 换走向':''; render();
}
/* 把上方分类下拉切到指定分类（'' = 回到默认清单）；下拉要跟着同步，否则重渲染会把它拨回去 */
function Lonly(v){
  f1=v;
  const s=$('#f1');
  if(s) s.value=v;
  Linit().msg='';
  render();
}
/* 视角旋转：像游戏里那样转镜头。纯视图操作 —— 摆放数据不动，连点四次回到原位，
   所以不进撤销栈。画布是正方形，旋转 90° 不改变包围盒，鼠标坐标由 Lxy 逆变换兜住。 */
function LrotView(){
  const L=Linit();
  L.viewRot=((L.viewRot||0)+90)%360;
  L.msg='视角已旋转到 '+L.viewRot+'°（只转镜头，摆放不动；连点四次回原位）';
  render();
}
/* 切换「按哪个建造区的存取线上限来算」—— 只影响计数显示，不动摆放 */
function Lzone(v){
  const L=Linit();
  L.zone=v;
  L.msg='存取线上限改为按「'+v+'」的满级档位算';
  render();
}
/* 只改格子边长，不动已摆的东西 —— 所以不进撤销栈，也不清空摆放 */
function Lcell(n){
  const L=Linit();
  if(n===LOCELL){ render(); return; }
  LOCELL=n;
  L.msg='格子边长改为 '+n+'px';
  render();
}
function Lsize(n){
  const L=Linit(); Lpush();
  const wasBase=!!L.base;
  /* ⭐v145 注意顺序：画布尺寸是**基地级**访问器字段，赋值落到「当前基地」的存储上 ——
     必须先切回自由模式（L.base=''）再写尺寸，否则会把新尺寸写进刚离开的那片基地。 */
  L.base=''; L.size=n; L.objs=[]; L.sel=[]; L.pick=null;
  L.msg='画布改为 '+n+'×'+n+'，原有摆放已清空（可撤销）'+(wasBase?'；并回到自由模式（不限地区）':'');
  render();
}
function Lclear(){
  const L=Linit();
  if(!L.objs.length){ L.msg='画布本来就是空的'; render(); return; }
  Lpush(); L.objs=[]; L.sel=[]; L.msg='已清空（可撤销）'; render();
}
/* ⭐ 2026-09-21（博士反馈「放不上去」）：游戏里分/汇流器可以「替换」线上的普通物流段 ——
   手里拿分/汇流器、点（或拖到）一个「介质匹配的传送带/管道格」→ 删掉那段、放分/汇流器。
   机器与其他建筑依然拒绝（汇流器不能压机器）。命中并替换返回 true。 */
function LreplaceCell(x,y){
  const L=Linit();
  if(!L.pick||!L.pick.isLogi) return false;
  const pk=L.pick;
  /* ⭐ 2026-09-21（博士：物流桥和准入口犯了同样的毛病）——两类行为不同：
     串接类（分/汇流器、准入口）→ **替换**线上普通段；桥类（物流桥/管道桥）→ **叠加**（原线保留，立体跨线）。 */
  const kind=(pk.lgType==='Router'||pk.lgType==='FluidRepeater'||pk.lgType==='BoxValve'||pk.lgType==='FluidValve') ? 'replace'
           : (pk.lgType==='Connector'||pk.lgType==='FluidConnector') ? 'overlay' : null;
  if(!kind) return false;
  const occ=L.objs.find(o=>x>=o.x&&x<o.x+o.w&&y>=o.y&&y<o.y+o.d);
  if(!occ) return false;
  if(occ.lock) return false;   /* ⑤-1 局部锁定：锁定的段不许被替换 / 叠桥 */
  const ob=byBp(occ.id);
  if(!ob||!ob.isLogi||(ob.lgType!=='Belt'&&ob.lgType!=='Pipe')||ob.lgMedium!==pk.lgMedium) return false;
  /* ⭐v138 串接类必须「顺着物流方向」：转角格（该格进向 ≠ 出向）不能放 ——
     博士核实：「转角格不能放的原因是没有沿着物流方向建造」。 */
  if(kind==='replace' && (pk.lgType==='BoxValve'||pk.lgType==='FluidValve')){
    /* ⭐v140 合规判定走唯一出处 LvalveBad（该格现在是带子 occ，用它的流向判） */
    const _why=LvalveBad(x, y, pk.lgMedium);
    if(_why){
      L.msg=pk.name+'：'+_why+' —— 换一格顺着物流方向的直线段';
      render(); return true;
    }
  }
  Lpush();
  if(kind==='replace') L.objs=L.objs.filter(o=>o!==occ&&o.uid!==occ.uid);
  /* ⭐v140 朝向：串接件沿用原格流向，但**准入口的 rot 基准差 90°**（传送带 rot0=流向右 /
     准入口 rot0=下进上出）→ 必须映射，否则竖着放会变横（博士截图 1）。 */
  const o=Lmk(pk,x,y,kind==='replace'?LtwinRot(pk,occ.rot):L.pickRot);
  o.planRole='link';
  L.objs.push(o); L.sel=[o.uid];
  L.msg= kind==='replace' ? ('已把该格物流段替换成 '+pk.name) : (pk.name+' 已叠上（跨线，原线保留）');
  render();
  return true;
}
/* ⭐v138（博士 2026-09-24：「准入口只可以放在传送带和管道上」）：这类件**只能叠在同类带/管上**，
   不许放空格 —— 串接类（分/汇流器、准入口）替换线上普通段，桥类叠加。判定沿用 LreplaceCell 的 kind。 */
const LO_ONLINE_TYPES={'BoxValve':1,'FluidValve':1};
function LisOnLine(b){ return !!(b&&b.isLogi&&LO_ONLINE_TYPES[b.lgType]); }
/* ⭐v140 物流件的「rot ↔ 方向」明文映射：**传送带/管道** rot=0 表示「流向右」，90=下、180=左、270=上
   （与 LdirName 一致）。⚠️ 但**准入口**的 rot 基准不同（测试锁定：rot=0 时「下进上出」）——
   两者差 90°，换件时必须做映射，否则竖着放会变成横的（博士 2026-09-24 截图 1）。 */
function LrotDir(rot){ return ({0:'r',90:'d',180:'l',270:'u'})[((rot%360)+360)%360]||'r'; }
function LtwinRot(pk, rot){
  return (pk.lgType==='BoxValve'||pk.lgType==='FluidValve') ? (((rot+90)%360)+360)%360 : rot;
}
/* ⭐v140 准入口合规判定（**唯一出处**：放置校验 + 渲染标红共用，避免两处口径不一致）：
   合规 = 这一格顺着物流方向 —— ①四邻有同类介质的带/管；②若存在上游（邻居流向指向我），
   我的流向必须与它一致；③没有上游时至少要有下游（我流向的那格接得上）。
   返回 null = 合规；否则返回不合规原因文案。 */
function LvalveBad(x, y, med){
  const objs=Linit().objs;
  const cellAt=(cx,cy)=>objs.filter(z=>cx>=z.x&&cx<z.x+(z.w||1)&&cy>=z.y&&cy<z.y+(z.d||1))[0];
  const nbOf=(dx,dy)=>{ const q=cellAt(x+dx,y+dy); if(!q) return null;
    const qb=byBp(q.id);
    return (qb&&qb.isLogi&&qb.lgMedium===med&&(qb.lgType==='Belt'||qb.lgType==='Pipe'))?q:null; };
  const me=cellAt(x,y);
  const _meB=me?byBp(me.id):null;
  /* ⭐v141 关键修正：**阀门类的 rot 基准差 90°** —— 读方向前必须先转回传送带语义，
     否则竖直段上会被读成横向、误判成拐角（博士截图 3：竖直带中间放准入口也标红）。 */
  const _meRot=(me&&_meB&&LisOnLine(_meB))?(((me.rot-90)%360)+360)%360:(me?me.rot:0);
  const myDir=me?LrotDir(_meRot):'r';
  const UP=[[0,-1,'d'],[0,1,'u'],[-1,0,'r'],[1,0,'l']];      /* [dx,dy, 该邻居「指向我」时应有的流向] */
  let up=null, anyNb=false;
  UP.forEach(u=>{ const q=nbOf(u[0],u[1]); if(!q) return; anyNb=true;
    if(LrotDir(q.rot)===u[2]) up=u[2]; });
  const DD={r:[1,0],l:[-1,0],u:[0,-1],d:[0,1]}, dv=DD[myDir];
  const down=nbOf(dv[0],dv[1]);
  if(!anyNb) return '四周没有'+med+'衔接（空放，没放在'+med+'上）';
  if(up && up!==myDir) return '这一格是拐角（进向≠出向，没有顺着物流方向）';
  if(up && !down) return '这一格是' + med + '的末端/断头（顺着流向没有接下去的' + med + '，放这里会把线截断）';
  if(!up && !down) return '这一格和'+med+'接不上（我的流向那侧没有'+med+'）';
  return null;
}
/* ⭐v141 阀门朝向重算：把选中/移动过的阀门 rot 按**新位置所在的线段流向**重设 ——
   拖到别的线上时 rot 不会自己更新，会一直被标红/朝向不对（博士截图 2）。 */
function LvalveResync(uids){
  const L=Linit();
  const toBelt={r:0,d:90,l:180,u:270};
  (uids||[]).forEach(u=>{
    const o=L.objs.filter(q=>q.uid===u)[0]; if(!o) return;
    const b=byBp(o.id); if(!b||!LisOnLine(b)) return;
    const med=b.lgMedium;
    const nbOf=(dx,dy)=>{
      const q=L.objs.filter(z=>z.x===o.x+dx&&z.y===o.y+dy&&(z.w||1)===1&&(z.d||1)===1)[0];
      if(!q) return null; const qb=byBp(q.id);
      return (qb&&qb.isLogi&&qb.lgMedium===med&&(qb.lgType==='Belt'||qb.lgType==='Pipe'))?q:null; };
    let dir=null;
    [[0,-1,'d'],[0,1,'u'],[-1,0,'r'],[1,0,'l']].forEach(u2=>{
      const q=nbOf(u2[0],u2[1]); if(q&&LrotDir(q.rot)===u2[2]) dir=u2[2]; });
    if(!dir){
      const DD={r:[1,0],d:[0,1],l:[-1,0],u:[0,-1]};
      Object.keys(DD).forEach(k=>{ if(!dir&&nbOf(DD[k][0],DD[k][1])) dir=k; });
    }
    if(dir) o.rot=LtwinRot(b, toBelt[dir]);
  });
}
function Lput(x,y){
  const L=Linit();
  if(!L.pick) return;
  const b=L.pick, dm=Ldims(b,L.pickRot);
  if(!dm.w||!dm.d) return;
  if(LisOnLine(b)){
    if(LreplaceCell(x,y)) return;
    L.msg=b.name+'：必须放在同类型的'+(b.lgMedium==='管道'?'管道':'传送带')+'上，且要顺着物流方向（转角格不行）';
    render(); return;
  }
  if(!Lfree(x,y,dm.w,dm.d,null)){
    if(LreplaceCell(x,y)) return;
    L.msg='这里放不下：越界或与已放建筑重叠'; render(); return;
  }
  Lpush();
  const o=Lmk(b,x,y,L.pickRot);
  L.objs.push(o); L.sel=[o.uid]; L.msg='';
  render();
}
/* 物流件连铺：空白格按下即起手，拖动沿直线把这一排铺满（横还是竖由拖拽主轴决定）。
   整段手势只压一次撤销栈（按下时 Lpush），拖动过程中来回改的是同一批格子。 */
/* ⭐ 2026-09-21（博士截图反馈）：拉线升级成游戏的手感 ——
   ① L 形拐弯：拖拽主轴先走、再转第二轴，弯头格的朝向自动衔接（渲染层按 rot 画，弯道箭头自动拐）；
   ② 端点吸附：起手/落点压在机器上时，自动吸到该机「输出口/输入口」外一格（口外那格 = 游戏里
      「出口旁边那格开始拉」；机器占格本身画布上被机器占着，带子贴着机器铺，视觉一致）。 */
/* ⭐v107（博士图2「想要红箭头那种」）：拐弯先走哪条轴**跟手势**——
   轨迹里第一个偏移过 1 格的点，它的主轴就是第一轴（先往上拖就先铺竖段）；
   旧版按总位移大小（|dx|>=|dy| 先横），博士想先竖后横时被强行画成镜像。
   轨迹退化/斜拖同帧双轴时回退旧判定（构造 LODRAG 没 hist 的旧调用方同样回退）。 */
function LlayAxis(st){
  const fb=Math.abs(st.ex-st.sx)>=Math.abs(st.ey-st.sy)?'h':'v';
  if(!st.hist) return fb;
  for(let i=0;i<st.hist.length;i++){
    const ax=Math.abs(st.hist[i][0]-st.sx), ay=Math.abs(st.hist[i][1]-st.sy);
    if(ax>=1||ay>=1) return ax===ay?fb:(ax>ay?'h':'v');
  }
  return fb;
}
function LlayPath(st){
  const dx=st.ex-st.sx, dy=st.ey-st.sy;
  const horizFirst=st.hf!=='v';
  const cells=[];
  const push=(x,y)=>{ const last=cells[cells.length-1];
    if(last&&last[0]===x&&last[1]===y) return;
    cells.push([x,y]); };
  if(horizFirst){
    const sx2=dx>=0?1:-1;
    for(let x=st.sx;;x+=sx2){ push(x,st.sy); if(x===st.ex) break; }
    const sy2=dy>=0?1:-1;
    for(let y=st.sy;;y+=sy2){ push(st.ex,y); if(y===st.ey) break; }
  }else{
    const sy2=dy>=0?1:-1;
    for(let y=st.sy;;y+=sy2){ push(st.sx,y); if(y===st.ey) break; }
    const sx2=dx>=0?1:-1;
    for(let x=st.sx;;x+=sx2){ push(x,st.ey); if(x===st.ex) break; }
  }
  return {cells:cells, horiz:horizFirst};
}
/* 端点吸附：格子上压着机器时，返回该机「输出口/输入口」外一格的坐标；空地返回 null（原格直用） */
function LsnapEnd(x,y,which){
  const L=Linit();
  const hit=L.objs.filter(o=>x>=o.x&&x<o.x+o.w&&y>=o.y&&y<o.y+o.d && o.planRole!=='link');
  for(let hi=0;hi<hit.length;hi++){
    const o=hit[hi], b=byBp(o.id);
    if(!b||!b.ports||!b.ports.length) continue;
    const kind=which==='out'?'output':'input';
    const cands=(b.ports||[]).filter(p=>p.kind===kind);
    if(!cands.length) continue;
    const fp=Lfp(b);   /* ⭐v122：LportXY 要的是未旋转宽深（原误传旋转后的 o.w,o.d，非正方形建筑会错位） */
    let best=null, bd=1e9, bp0=null;
    cands.forEach(p=>{
      const q=LportXY(p,o.rot,fp[0],fp[1]);
      const d=Math.abs(o.x+q.x-x)+Math.abs(o.y+q.z-y);
      if(d<bd){ bd=d; best=q; bp0=p; }
    });
    if(!best) continue;
    const dir=LportDirRot(bp0,o.rot,fp[0],fp[1]);   /* ⭐v122：朝向跟 rot 转（原来贴边猜，旋转后全错） */
    if(!dir) continue;
    const DVEC={r:[1,0], l:[-1,0], d:[0,1], u:[0,-1]};
    const v=DVEC[dir];
    return {x:o.x+best.x+v[0], y:o.y+best.z+v[1], dir:dir};
  }
  return null;
}
/* 起点吸附：从机器口那一格起手（游戏里就是从「红圈」口上拉带子）——
   起手格只有机器、外侧格是空的 → 把起点移到口外那一格（LsnapEnd 已给了「口外一格」的语义）。
   ⭐v108：v107 只在起手格**空着**时才让 LlayTo 里的 LsnapEnd 生效 —— 但机器占着格子时
   起手格命中机器，LonMouseDown 的 `if(Lfree(lx,ly,1,1,null))` 直接失败，压根进不了连铺，
   「从红圈起手」在试摆器里根本做不到。这里加一个「纯探测」入口：只判断能不能吸、吸到哪，
   **不改 LODRAG**（调用方 LsnapStart 返回值决定要不要起手，避免探测阶段污染拖拽态）。
   返回 {x,y} = 口外那一格；不成立返回 null。 */
function LsnapStart(x,y){
  const L=Linit();
  const sn=LsnapEnd(x,y,'out');
  if(!sn) return null;
  if(!LfreeIn(L.objs,sn.x,sn.y)) return null;
  return sn;
}
function LlayTo(ex,ey){
  const L=Linit(), st=LODRAG;
  if(!st||st.mode!=='lay'||!L.pick) return;
  st.hist=st.hist||[]; st.hist.push([ex,ey]);   /* ⭐v107 记录鼠标轨迹（格级），拐弯第一轴跟手势 */
  st.ex=ex; st.ey=ey;
  /* 端点吸附：压在机器上 → 吸到口外一格（起点=输出口、终点=输入口） */
  let sx=st.sx, sy=st.sy, ex2=ex, ey2=ey;
  const sSnap=LsnapEnd(st.sx, st.sy, 'out');
  if(sSnap){ sx=sSnap.x; sy=sSnap.y; }
  const eSnap=LsnapEnd(ex, ey, 'in');
  if(eSnap){ ex2=eSnap.x; ey2=eSnap.y; }
  const ln=LlayPath({sx:sx, sy:sy, ex:ex2, ey:ey2, hf:LlayAxis(st)});
  /* 先把本手势上一帧铺的格摘掉，再整体重铺 —— 逐格 push 会让判定把自己的格子当障碍 */
  if(st.uids&&st.uids.length) L.objs=L.objs.filter(o=>st.uids.indexOf(o.uid)<0);
  const base=L.objs.slice(), added=[];
  /* ⭐v136 相交自动建桥（博士 2026-09-24：「游戏里两条传送带相交后会自动建物流桥，试摆里没有」）：
     连铺时目标格被**同类介质的普通带/管**占着 → 不再跳过，而是在那格叠一座桥
     （传送带 → log_connector 物流桥；管道 → log_pipe_connector 管道桥）—— 与游戏同款行为。
     其他占用（建筑 / 分汇流器 / 已有桥 / 异类介质）仍按原样跳过。 */
  const _myMed=L.pick.lgMedium;
  const _bridgeId=(_myMed==='管道')?'log_pipe_connector':'log_connector';
  const _occAt=(arr,x,y)=>arr.filter(o=>x>=o.x&&x<o.x+(o.w||1)&&y>=o.y&&y<o.y+(o.d||1))[0];
  ln.cells.forEach((c,i)=>{
    const nxt=ln.cells[i+1];
    /* 每格朝下一格；末格沿用前一格走向（游戏里拉带子收尾也是这个手感） */
    const rot=nxt?LrotFrom(c,nxt):(i>0?LrotFrom(ln.cells[i-1],c):L.pickRot);
    const occ=_occAt(base,c[0],c[1])||_occAt(added,c[0],c[1]);
    if(occ){
      const ob=byBp(occ.id);
      if(ob&&ob.isLogi&&(ob.lgType==='Belt'||ob.lgType==='Pipe')&&ob.lgMedium===_myMed
         &&(occ.w||1)===1&&(occ.d||1)===1){   /* 只有 1×1 的普通带/管才叠桥；建筑一律跳过 */
        const cb=byBp(_bridgeId);
        if(cb&&!_occAt(added,c[0],c[1])) added.push(Lmk(cb,c[0],c[1],rot));
        L.msg='已在相交处叠了一座'+(cb?cb.name:'桥')+'（原线保留）';
      }
      return;                       /* 桥已处理 / 非同类 → 该格不再铺 */
    }
    if(!LfreeIn(added,c[0],c[1])) return;   /* 自己重叠的格跳过 */
    added.push(Lmk(L.pick,c[0],c[1],rot));
  });
  /* ⭐v128（博士 2026-09-24「连续放传送带时，在上一条传送带的末尾拐弯放置，
     末尾那格不会自动变成拐弯」）：链尾自动拧转。弯头渲染靠 flowIn 拓扑反推
     （邻居指向我才有进边）——「从旧带末尾拐出去」时旧尾格没有任何邻居指向它，
     推断必然失效，永远画直条。游戏口径是新带衔接旧链尾时旧尾格自动变弯头：
     扫描新路径首格四邻，同类介质的普通带/管段 P 满足——
     ① P 出向不指首格（已衔接的不动）；
     ② 首格出向不指 P（首格流入 P 的不拧，否则拧成互指死循环）；
     ③ P 出向的下一格是空格（真链尾——下一格压着机器口/分流器/别的带都算已有承接，
        拧了会破坏既有衔接；中间段拧了会把链拧断）——
     才把 P.rot 拧向首格，v106 的渲染推断随即自动把 P 画成弯头。
     幂等：拧过一次 P 出向已指首格，后续帧判定①不再命中，拖动重铺不会反复拧；
     撤销：整段手势的快照在起手前压栈（LonMouseDown 的 Lpush），拧转与铺带
     同一次 Ctrl+Z 还原。只处理起点侧；终点侧（新带流入旧带）flowIn 自动衔接。 */
  if(added.length){
    const pickB=byBp(L.pick.id);
    const pickPipe=!!pickB&&pickB.lgMedium==='管道';
    const f0=added[0];
    const V2={r:[1,0], b:[0,1], l:[-1,0], t:[0,-1]};
    const outV=(b,rot)=>{ const q=(lgPortSides(b,rot).out||[])[0]; return q?(V2[q]||null):null; };
    const lgAt={}, occ={};
    /* occ 按**占地逐格**展开（3×3 机器压着的 9 格都算承接）—— 只记左上角会让
       「出向下一格压在机器肚子里」漏判，把已接进机器的带子拧走（v128 首轮实测踩过） */
    const occMark=q=>{ const b=byBp(q.id); const fp=b?Lfp(b):[1,1];
      for(let dx=0;dx<fp[0];dx++) for(let dy=0;dy<fp[1];dy++) occ[(q.x+dx)+','+(q.y+dy)]=q; };
    L.objs.forEach(q=>{ const b=byBp(q.id); occMark(q); if(b&&b.isLogi) lgAt[q.x+','+q.y]=q; });
    added.forEach(q=>{ occMark(q); });   /* 本帧要铺上的格子也算承接方 */
    [[1,0],[-1,0],[0,1],[0,-1]].forEach(v=>{
      const P=lgAt[(f0.x+v[0])+','+(f0.y+v[1])];
      if(!P||L.objs.indexOf(P)<0) return;        /* 必须是已有旧带（不含本手势自己的格子） */
      const b=byBp(P.id);
      if(!b||!b.isLogi||(b.lgType!=='Belt'&&b.lgType!=='Pipe')||(b.lgMedium==='管道')!==pickPipe) return;
      const pov=outV(b,P.rot); if(!pov) return;
      if(P.x+pov[0]===f0.x&&P.y+pov[1]===f0.y) return;            /* ① 已指向首格 */
      const fov=outV(pickB,f0.rot);
      if(fov&&f0.x+fov[0]===P.x&&f0.y+fov[1]===P.y) return;       /* ② 首格流入 P */
      if(occ[(P.x+pov[0])+','+(P.y+pov[1])]) return;              /* ③ 出向下格非空=有承接 */
      P.rot=LrotFrom([P.x,P.y],[f0.x,f0.y]);
    });
  }
  st.uids=added.map(o=>o.uid);
  if(!added.length){ L.msg='这条线上没有可放的空格'; render(); return; }
  added.forEach(o=>L.objs.push(o));
  L.msg='已铺 '+added.length+' 格（'+(ln.horiz?'横向':'纵向')+'）';
  render();
}
function LtogglePort(){
  const L=Linit(); L.showPort=!L.showPort;
  L.msg=L.showPort?'已显示建筑接口':'已隐藏建筑接口（不影响摆放）'; render();
}
/* ⭐v103：环境圈整层开关 + 改选中散布机通入的气体（圈色按 EnvDisplay 映射跟着变） */
function LtoggleGas(){
  const L=Linit(); L.showGas=!L.showGas;
  L.msg=L.showGas?'已显示气体散布机环境圈':'已隐藏环境圈（不影响摆放）'; render();
}
function LgasSet(v){
  const L=Linit();
  const sel=LselObjs().filter(o=>vaporizerOf(byBp(o.id)));
  if(!sel.length){ L.msg='先在画布上选中气体散布机，再选通入的气体'; render(); return; }
  Lpush();
  sel.forEach(o=>{ o.gas=v; });
  L.msg='已把选中的 '+sel.length+' 台散布机切到「'+envGasName(v)+'」（'+(ENV_NAME[v]||('环境'+v))+'环境 · 青蓝/白/橙黄/翠绿圈色按游戏校准）';
  render();
}
/* 旋转：有选中就整体转（绕选区外接矩形中心，像游戏里那样刚体转），
   没选中就把左栏待放置的朝向转一下 */
function Lrot(){
  const L=Linit();
  const selAll=LselObjs(), sel=selAll.filter(o=>!o.lock);   /* ⑤-1：锁定件不参与旋转 */
  if(!sel.length){
    if(selAll.length){ L.msg='选中的 '+selAll.length+' 个件是锁定状态，先解锁再旋转'; render(); return; }
    if(!L.pick){ L.msg='先在左栏选一座建筑，或选中已放的建筑'; render(); return; }
    L.pickRot=(L.pickRot+90)%360;
    L.msg='待放置朝向：'+L.pickRot+'°'; render(); return;
  }
  const minX=Math.min.apply(null,sel.map(o=>o.x)),
        minY=Math.min.apply(null,sel.map(o=>o.y)),
        maxX=Math.max.apply(null,sel.map(o=>o.x+o.w)),
        maxY=Math.max.apply(null,sel.map(o=>o.y+o.d));
  /* 全用 2 倍坐标做整数运算，避免半格；最后取整 */
  const gx2=minX+maxX, gy2=minY+maxY;
  /* 只把「真正要转的」排掉，锁定件留在原地 —— 若把它们也当忽略，转过来会压住它们 */
  const ign=sel.map(o=>o.uid);
  const moved=sel.map(o=>{
    const nr=(o.rot+90)%360, dm=Ldims(byBp(o.id),nr);
    const ox2=2*o.x+o.w, oy2=2*o.y+o.d;
    return {o:o, nr:nr, w:dm.w, d:dm.d,
      x:Math.round((gx2-(oy2-gy2)-dm.w)/2),
      y:Math.round((gy2+(ox2-gx2)-dm.d)/2)};
  });
  for(let i=0;i<moved.length;i++){
    const m=moved[i];
    if(!Lfree(m.x,m.y,m.w,m.d,ign)){ L.msg='旋转后会越界或压到别的建筑，已取消'; render(); return; }
  }
  Lpush();
  moved.forEach(m=>{ m.o.x=m.x; m.o.y=m.y; m.o.rot=m.nr; m.o.w=m.w; m.o.d=m.d; });
  const skipN=(selAll.length-sel.length);
  L.msg='已旋转 90°（'+moved.length+' 座）'+(skipN?('；'+skipN+' 座锁定中，跳过了'):'');
  render();
}
function Ldel(uid){
  const L=Linit();
  const targets=uid?[uid]:L.sel.slice();
  if(!targets.length){ L.msg='先选中要删的建筑（单击选中 / 空白处拖拽框选）'; render(); return; }
  /* ⑤-1 局部锁定：锁定件跳过（全锁住就整条拒绝）—— 双击删除也走这里 */
  const byUid=u=>L.objs.filter(o=>o.uid===u)[0];
  const lkd=targets.filter(u=>{ const o=byUid(u); return !!o&&!!o.lock; });
  const del=targets.filter(u=>lkd.indexOf(u)<0);
  if(!del.length){ L.msg='选中的 '+lkd.length+' 个件是锁定状态，先解锁再删（工具栏「解锁选中」）'; render(); return; }
  Lpush();
  L.objs=L.objs.filter(o=>del.indexOf(o.uid)<0);
  L.sel=L.sel.filter(u=>del.indexOf(u)<0);
  L.msg='已删除 '+del.length+' 座'+(lkd.length?('；'+lkd.length+' 座锁定中，跳过了'):''); render();
}
/* 复制：整体往右挪一个选区宽，右边放不下就往下，再不行就报错（游戏里也是这个逻辑） */
function Ldup(){
  const L=Linit();
  const selAll=LselObjs(), sel=selAll.filter(o=>!o.lock);   /* ⑤-1：锁定件不参与复制 */
  if(!sel.length){
    L.msg=selAll.length?'选中的都是锁定件，先解锁再复制':'先选中要复制的建筑'; render(); return;
  }
  const minX=Math.min.apply(null,sel.map(o=>o.x)),
        minY=Math.min.apply(null,sel.map(o=>o.y)),
        maxX=Math.max.apply(null,sel.map(o=>o.x+o.w)),
        maxY=Math.max.apply(null,sel.map(o=>o.y+o.d));
  const gw=maxX-minX, gd=maxY-minY;
  const tries=[[gw,0],[0,gd],[gw,gd]];
  for(let i=0;i<tries.length;i++){
    const dx=tries[i][0], dy=tries[i][1];
    let ok=dx||dy;
    for(let j=0;j<sel.length&&ok;j++){
      const o=sel[j];
      if(!Lfree(o.x+dx,o.y+dy,o.w,o.d,null)) ok=false;
    }
    if(!ok) continue;
    Lpush();
    const news=sel.map(o=>{
      const b=byBp(o.id);
      const c=Lmk(b,o.x+dx,o.y+dy,o.rot);
      L.objs.push(c); return c;
    });
    L.sel=news.map(o=>o.uid);
    L.msg='已复制 '+news.length+' 座'; render(); return;
  }
  L.msg='旁边放不下副本，先腾点空间'; render();
}
/* 单击/框选后的高亮：直接改 DOM，避免重建（重建会让双击的第二个 click 落到新节点上） */
function LpaintSel(c){
  const L=Linit();
  const nodes=c.querySelectorAll('.lo-cell');
  for(let i=0;i<nodes.length;i++){
    const n=nodes[i], on=L.sel.indexOf(n.dataset.uid)>=0;
    if(on) n.classList.add('sel'); else n.classList.remove('sel');
  }
}
/* 框选命中：矩形（格坐标，右下开区间）与建筑外接框有交集就选中 */
function LselIn(x1,y1,x2,y2){
  const L=Linit();
  L.sel=L.objs.filter(o=>o.x<x2&&o.x+o.w>x1&&o.y<y2&&o.y+o.d>y1).map(o=>o.uid);
  return L.sel.length;
}
function Lxy(e,c){
  const r=c.getBoundingClientRect();
  /* 视角旋转后包围盒仍是正方形（40/50/70/80 的平方），尺寸不变；
     但视口坐标要按当前角度逆旋转回画布坐标，否则点哪儿都偏 */
  const W=r.width, half=W/2;
  let dx=e.clientX-r.left-half, dy=e.clientY-r.top-half;
  const deg=(LO&&LO.viewRot)?LO.viewRot:0;
  if(deg){
    const th=deg*Math.PI/180, co=Math.cos(th), si=Math.sin(th);
    const x=dx*co+dy*si, y=-dx*si+dy*co;
    dx=x; dy=y;
  }
  return {fx:(dx+half)/LOCELL, fy:(dy+half)/LOCELL};
}
/* ⭐v109：点是否落在某台机器的**某个口**上（用于「口上点击=拉线 / 拖动=移机器」的分流）。
   判定用「口的那个格」+ 该口的朝向：点在口格上即算命中（画布上口就画在那格里）。
   返回 {o,b,p,dir,ox,oy} = 机器、建筑、口、口朝向、口外那一格；没命中返回 null。 */
function LhitPort(o,fx,fy){
  const b=byBp(o.id);
  if(!b||!b.ports||!b.ports.length) return null;
  const cx=Math.floor(fx), cy=Math.floor(fy);
  const fp=Lfp(b);   /* ⭐v122：未旋转宽深（原误传 o.w,o.d） */
  for(let i=0;i<b.ports.length;i++){
    const p=b.ports[i];
    const q=LportXY(p,o.rot,fp[0],fp[1]);
    const gx=o.x+q.x, gy=o.y+q.z;
    if(gx!==cx||gy!==cy) continue;
    const dir=LportDirRot(p,o.rot,fp[0],fp[1]);   /* ⭐v122：朝向跟 rot 转 */
    if(!dir) continue;
    const DV={r:[1,0], l:[-1,0], d:[0,1], u:[0,-1]}[dir];
    return {o:o, b:b, p:p, dir:dir, ox:gx+DV[0], oy:gy+DV[1]};
  }
  return null;
}
function LonMouseDown(e){
  if(tab!=='layout'||e.button!==0) return;
  /* ⭐v104 就地选气条浮在画布内（.lo-gasbar）：点它的按钮不能被当成「点画布摆放」——
     否则手里拿着散布机时点色块会**再放一座**（博士 2026-09-23 实测），还顺带清掉选中。
     这里直接放行，让按钮自己的 onclick=LgasSet 接手。 */
  if(e.target.closest&&e.target.closest('.lo-gasbar')) return;
  /* ⭐v109 协议核心出货：内部箭头（.lo-dlv）与选货浮层（.lo-dlvpop）自成一套点击 ——
     放行给它们自己的 onclick，否则点箭头会被当成「点画布 → 清选中 / 摆新件」。
     点画布别处则顺手关掉浮层（浮层外点击 = 收起）。
     ⭐v123（博士「手拿传送带一移到口上就只能选货」）：箭头压在口格上，v109 的无条件
     放行把 v108「从口格拉线」挡死了。改为**手拿物流件时不放行** —— 往下走到 portpend
     分支（原地松手=拉线、拖动=移机器）；空手点箭头仍放行开选货浮层（click 链由
     LdlvOpen 的「手里有东西不开」守卫兜底）。 */
  if(e.target.closest&&e.target.closest('.lo-dlv')&&!(Linit().pick&&Linit().pick.isLogi)) return;
  if(e.target.closest&&e.target.closest('.lo-dlvpop')) return;
  if(Linit().dlvPop) Linit().dlvPop=null;
  const c=e.target.closest('.lo-canvas'); if(!c) return;
  e.preventDefault();
  const L=Linit(), p=Lxy(e,c);
  const cellEl=e.target.closest('.lo-cell');
  const hit=cellEl?L.objs.filter(o=>o.uid===cellEl.dataset.uid)[0]:null;
  L.msg='';
  if(hit){
    /* ⭐ 点已有实体：pick 是分/汇流器且点的是同类介质普通段 → 替换（游戏同款）；
       其余仍走选中/移动。 */
    if(LreplaceCell(hit.x,hit.y)) return;
    if(L.sel.indexOf(hit.uid)<0) L.sel=e.shiftKey?L.sel.concat([hit.uid]):[hit.uid];
    else if(e.shiftKey) L.sel=L.sel.filter(u=>u!==hit.uid);
    LpaintSel(c);
    /* ⑤-1 局部锁定：锁定件不参与拖动 —— 整组拖动时把它们从拖动集合里摘掉；
       全是锁定件就只做选中、不起拖（也顺带挡掉双击删除）。 */
    const dragSel=L.sel.filter(u=>{ const q=L.objs.filter(x=>x.uid===u)[0]; return !!q&&!q.lock; });
    if(!dragSel.length){ LODRAG=null; L.msg='选中的是锁定件，动不了（工具栏「解锁选中」或按 L 解锁）'; render(); return; }
    /* ⭐v109（博士 2026-09-23「点机器口机器会被拖动」）：手拿物流件、按在**该机的口格**上 →
       先只选中、进「待决态」不起拖。原地松手 = 从口外起手连铺；拖过 4px 才转成移动机器。
       旧版命中机器就直接进 move，v108 的「口外起手」分支在后面永远走不到 —— 想从口红圈拉线，
       一动就把机器拖走了。 */
    const pkPortPend=L.pick&&L.pick.isLogi&&LhitPort(hit,p.fx,p.fy);
    if(pkPortPend){
      LODRAG={mode:'portpend', uid:hit.uid, fx:p.fx, fy:p.fy, sel:dragSel,
        from:L.objs.map(o=>({uid:o.uid,x:o.x,y:o.y})), moved:false, dx:0, dy:0};
      L.msg='按在出料口上：原地松手=从这里拉线，拖动=移动机器';
      return;
    }
    LODRAG={mode:'move', uid:hit.uid, fx:p.fx, fy:p.fy, sel:dragSel,
      from:L.objs.map(o=>({uid:o.uid,x:o.x,y:o.y})), moved:false, dx:0, dy:0};
    return;
  }
  L.sel=[];
  LpaintSel(c);
  /* 手里拿着物流件、按在空白格上 → 起手连铺，不走框选 */
  if(L.pick&&L.pick.isLogi){
    const lx=Math.floor(p.fx), ly=Math.floor(p.fy);
    /* ⭐v108（博士图：「游戏里是从红圈里开始拉」）：起手格压在机器上、但出口外侧格空着
       → 从**口外那一格**起手（在机器的「红圈」口上拉带子，游戏手感）。
       先只探测、不动状态；确认能起手才 Lpush（整段手势只压一次撤销栈）。 */
    const free=Lfree(lx,ly,1,1,null);
    const sn=free?null:LsnapStart(lx,ly);
    if(free||sn){
      const sx0=sn?sn.x:lx, sy0=sn?sn.y:ly;
      Lpush();
      LODRAG={mode:'lay', sx:sx0, sy:sy0, ex:sx0, ey:sy0, uids:[], hist:[[sx0,sy0]]};
      LlayTo(sx0,sy0);
      return;
    }
    LODRAG=null;                       /* 探测阶段留下的临时拖拽态丢掉，走原逻辑 */
    if(LreplaceCell(lx,ly)) return;    /* 分/汇流器点在同类介质物流段上 → 替换（游戏同款） */
  }
  LODRAG={mode:'band', fx:p.fx, fy:p.fy, x:p.fx, y:p.fy, moved:false, band:null};
}
function LonMouseMove(e){
  if(!LODRAG||tab!=='layout') return;
  const c=document.querySelector('.lo-canvas'); if(!c) return;
  const p=Lxy(e,c), st=LODRAG;
  if(st.mode==='band'){
    st.x=p.fx; st.y=p.fy;
    const dx=p.fx-st.fx, dy=p.fy-st.fy;
    if(!st.moved&&Math.abs(dx)*LOCELL<4&&Math.abs(dy)*LOCELL<4) return;
    st.moved=true;
    if(!st.band){ st.band=document.createElement('div'); st.band.className='lo-band'; c.appendChild(st.band); }
    st.band.style.left=(Math.min(st.fx,st.x)*LOCELL)+'px';
    st.band.style.top=(Math.min(st.fy,st.y)*LOCELL)+'px';
    st.band.style.width=(Math.abs(dx)*LOCELL)+'px';
    st.band.style.height=(Math.abs(dy)*LOCELL)+'px';
    return;
  }
  if(st.mode==='lay'){
    const lx=Math.floor(p.fx), ly=Math.floor(p.fy);
    if(lx!==st.ex||ly!==st.ey) LlayTo(lx,ly);
    return;
  }
  /* ⭐v109 待决态：手拿物流件按在口上 —— 还没动就是「还没决定」，动过阈值才转成移机器 */
  if(st.mode==='portpend'){
    const dx0=p.fx-st.fx, dy0=p.fy-st.fy;
    if(Math.abs(dx0)*LOCELL<4&&Math.abs(dy0)*LOCELL<4) return;
    st.mode='move';   /* 拖了就按移机器走，后面这段逻辑复用 */
  }
  const ddx=Math.round(p.fx-st.fx), ddy=Math.round(p.fy-st.fy);
  if(!st.moved&&Math.abs(p.fx-st.fx)*LOCELL<4&&Math.abs(p.fy-st.fy)*LOCELL<4) return;
  st.moved=true; st.dx=ddx; st.dy=ddy;
  const L=Linit();
  st.sel.forEach(u=>{
    const f=st.from.filter(q=>q.uid===u)[0];
    const el=c.querySelector('[data-uid="'+u+'"]');
    if(!f||!el) return;
    el.style.left=((f.x+ddx)*LOCELL)+'px';
    el.style.top=((f.y+ddy)*LOCELL)+'px';
  });
}
function LonMouseUp(){
  if(!LODRAG) return;
  const st=LODRAG; LODRAG=null;
  if(tab!=='layout') return;
  const L=Linit();
  if(st.mode==='lay'){
    /* ⭐ 2026-09-21（博士「拖拽到传送带上还是不行」）：拖拽的**落点**压在同类介质物流段上时，
       松手 = 把该格替换成分/汇流器（游戏同款）—— 拖动过程只预览、不破坏已有线。 */
    if(L.pick && LreplaceCell(st.ex, st.ey)){ render(); return; }
    L.sel=(st.uids||[]).slice();
    L.msg=(st.uids&&st.uids.length)
      ? ('已铺 '+st.uids.length+' 格物流件（Ctrl+Z 可撤销这一步）')
      : '没铺上：格子上已经有建筑或物流件';
    render(); return;
  }
  if(st.mode==='band'){
    if(st.band&&st.band.parentNode) st.band.parentNode.removeChild(st.band);
    if(st.moved){
      const x1=Math.floor(Math.min(st.fx,st.x)), y1=Math.floor(Math.min(st.fy,st.y));
      const x2=Math.ceil(Math.max(st.fx,st.x)), y2=Math.ceil(Math.max(st.fy,st.y));
      LselIn(x1,y1,x2,y2);
      L.msg=L.sel.length?('框选 '+L.sel.length+' 座'):'框选范围内没有建筑';
    } else if(L.pick){
      /* 没拖动 = 单击空白：按待放置建筑摆一座（自带越界/重叠判定） */
      Lput(Math.floor(st.fx),Math.floor(st.fy));
      return;
    }
    render(); return;
  }
  /* ⭐v109 待决态原地松手 = 从口外起手拉线（博士「游戏里是从红圈里开始拉」）：
     点口不再拖走机器，而是从这里开始铺。 */
  if(st.mode==='portpend'){
    const lx=Math.floor(st.fx), ly=Math.floor(st.fy);
    const sn=LsnapStart(lx,ly);
    if(!sn){ L.msg='这个口的外侧没有空格，放不下物流件'; render(); return; }
    Lpush();
    LODRAG={mode:'lay', sx:sn.x, sy:sn.y, ex:sn.x, ey:sn.y, uids:[], hist:[[sn.x,sn.y]]};
    LlayTo(sn.x,sn.y);
    L.msg='从口外 ('+sn.x+','+sn.y+') 起手拉线，拖到终点松手';
    render(); return;
  }
  if(st.moved&&(st.dx||st.dy)){
    let ok=true;
    for(let i=0;i<st.sel.length&&ok;i++){
      const u=st.sel[i];
      const o=L.objs.filter(q=>q.uid===u)[0];
      const f=st.from.filter(q=>q.uid===u)[0];
      if(!o||!f) continue;
      if(!Lfree(f.x+st.dx,f.y+st.dy,o.w,o.d,st.sel)) ok=false;
    }
    if(ok){
      Lpush();
      st.sel.forEach(u=>{
        const o=L.objs.filter(q=>q.uid===u)[0];
        const f=st.from.filter(q=>q.uid===u)[0];
        if(o&&f){ o.x=f.x+st.dx; o.y=f.y+st.dy; }
      });
      LvalveResync(st.sel);   /* ⭐v141 移动到新线路上 → 阀门朝向跟着重算 */
      L.msg='已移动 '+st.sel.length+' 座（'+st.dx+', '+st.dy+'）';
    } else {
      /* ⭐ 2026-09-21（博士「拖到传送带上放不上」）：拖的是分/汇流器（Router/FluidRepeater 单选）
         且落点格恰好是「同类介质的普通物流段」→ 替换该格：删段、分/汇流器移过去。 */
      if(st.sel.length===1){
        const o=L.objs.filter(q=>q.uid===st.sel[0])[0];
        const f=st.from.filter(q=>q.uid===st.sel[0])[0];
        const mb=o?byBp(o.id):null;
        const mKind=(mb&&mb.isLogi)
          ? ((mb.lgType==='Router'||mb.lgType==='FluidRepeater'||mb.lgType==='BoxValve'||mb.lgType==='FluidValve') ? 'replace'
           : (mb.lgType==='Connector'||mb.lgType==='FluidConnector') ? 'overlay' : null)
          : null;
        if(o&&f&&mKind){
          const nx=f.x+st.dx, ny=f.y+st.dy;
          const occ=L.objs.find(q=>q!==o&&nx>=q.x&&nx<q.x+q.w&&ny>=q.y&&ny<q.y+q.d);
          const ob=occ?byBp(occ.id):null;
          if(occ&&occ.x===nx&&occ.y===ny&&occ.w===1&&occ.d===1&&ob&&ob.isLogi
             &&(ob.lgType==='Belt'||ob.lgType==='Pipe')&&ob.lgMedium===mb.lgMedium){
            Lpush();
            if(mKind==='replace') L.objs=L.objs.filter(q=>q!==occ);   /* 串接类：删段换上 */
            o.x=nx; o.y=ny;                                            /* 桥类：叠上（原线保留） */
            L.msg= mKind==='replace' ? ('已把该格物流段替换成 '+mb.name) : (mb.name+' 已叠上（跨线，原线保留）');
            render(); return;
          }
        }
      }
      L.msg='移动后会越界或压到别的建筑，已还原';
    }
  } else if(st.uid){
    /* 自己判双击：不用原生 dblclick —— 中间只要重建过 DOM，原生双击就哑了 */
    const t=Date.now();
    if(t-L.lastT<420&&L.lastUid===st.uid){ Ldel(st.uid); return; }
    L.lastT=t; L.lastUid=st.uid;
    /* ⭐v135 单击机器 = 选中 + 就地弹出选择浮层（这台有得选才弹；拖动/双击不受影响） */
    const _o=L.objs.filter(q=>q.uid===st.uid)[0];
    if(_o&&RmacPanelOf(byBp(_o.id), _o)) L.macPop={uid:st.uid};
  }
  render();
}
function LonKeyDown(e){
  if(tab!=='layout') return;
  const t=e.target, tag=(t&&t.tagName)?String(t.tagName).toLowerCase():'';
  if(tag==='input'||tag==='select'||tag==='textarea') return;
  const k=e.key, mod=e.ctrlKey||e.metaKey;
  if(mod&&(k==='z'||k==='Z')){ e.preventDefault(); if(e.shiftKey) Lredo(); else Lundo(); return; }
  if(mod&&(k==='y'||k==='Y')){ e.preventDefault(); Lredo(); return; }
  if(mod&&(k==='d'||k==='D')){ e.preventDefault(); Ldup(); return; }
  if(k==='r'||k==='R'){ e.preventDefault(); Lrot(); return; }
  /* ⑤-1 局部锁定：L 键 = 锁定 / 解锁选中（选中里有未锁的就锁，全锁了就解） */
  if(k==='l'||k==='L'){
    e.preventDefault();
    const L=Linit(), sel=LselObjs();
    LlockSel(sel.filter(o=>!o.lock).length>0);
    return;
  }
  if(k==='Delete'||k==='Backspace'){ e.preventDefault(); Ldel(); return; }
  if(k==='Escape'){ Linit().sel=[]; Linit().msg=''; render(); }
}
/* 布局试摆默认只列「能进基地产线」的基建（v131 起分类名 = 游戏内「工业设备」面板官方分组名）：
     仓储存取 + 基础生产 + 合成制造 + 电力（+ 功能设备 —— 现在 9 件全在拉黑清单，默认清单里是
     0 件，但保留在放行名单里，将来把某件从 LO_SKIP_IDS 放回来就立即生效）
   另外放行「核心结构」—— 协议核心 / 次级核心。它们在配置表里 quickBarType 为空、被兜底归进
   「装饰与其他」（界面上显示成「饰」），但 9×9 占地 + 20 个接口，基地布局绕不开，所以按 ID
   单独放行（不按名称匹配，免得踩中文名变动的坑）。分类本身已在数据载入时改成「核心结构」，
   见前面的 CORE_STRUCT_IDS 段。
   ⚠️ 这里曾经把「产物排出口 liquid_recycle_gate_1 / 污水接入口 liquid_clean_gate_1」也一并放行 ——
   它们是武陵净水节点上的野外固定闸口（allowPlayerMove=false、canDelete=false），不在基地里，
   博士 2026-09-21 在游戏里找不到、核查后移除。
   默认不列：资源开采（矿机/水泵只能放野外矿点）、战斗辅助、装饰（玩偶/立牌/田块等）。
   要单独看某一类，用上方的分类下拉直接选。 */
const LO_KEEP_CATS=['仓储存取','基础生产','合成制造','电力','功能设备'];
const LO_KEEP_IDS=['sp_hub_1','sp_sub_hub_1'];
/* 沙盘里一概不提供的建筑（按 ID 拉黑，含多地区同名变体）：
     中继器 power_pole_2 / 息壤中继器 power_pole_3 —— 博士 2026-09-21 要求去掉。
     洒水机 squirter / 给水器 dumper / 滑索架 travel_pole（含长距滑索架 travel_pole_2）
     / 便捷存取站 carrier_1 / 留言信标 marker_1 —— 博士 2026-09-21 要求不出现在试摆里。
   拉黑对「默认清单」和「分类下拉单独看」都生效；要放回来，把 ID 从这里删掉即可。 */
const LO_SKIP_IDS=['power_pole_2','power_pole_3',
  'mix_pool_1',                         /* ⭐v136 基础反应池不作独立条目 —— 界面上的「反应池」= 扩容池（博士只用扩容） */
  'squirter_1','squirter_nop_1',        /* 洒水机 */
  'dumper_1','dumper_nop_1',            /* 给水器 */
  'travel_pole_1','travel_pole_nop_1',  /* 滑索架 */
  'travel_pole_2',                      /* 长距滑索架（同类，博士 2026-09-21 一并去掉） */
  'carrier_1','marker_1'];            /* 便捷存取站 / 留言信标（博士 2026-09-21） */
/* 免电变体（id 带 _nop_，如 storager_nop_1）不在试摆里列 —— 博士 2026-09-21：同名只留正常版。
   要放回来，把下面改成 false 即可。 */
const LO_HIDE_NOP=true;
const LO_IS_NOP=b=>String(b.id).indexOf('_nop_')>=0;
/* ---------- 基地 / 地区：武陵与四号谷地的存取线是两套规则，别混着算 ----------
   博士 2026-09-21：「布局试摆我看不见四号谷地的预设存取线，能把武陵和四号谷地分开讨论吗」。
   两地差别（依据：data/bases.json 的 busObservations、zones[].busCap）：
     · 四号谷地：存取线由基地升级后**自动铺在基地外侧边缘**，玩家不用摆；配置表档位里也没有数量。
     · 武陵：源桩 + 基段**要自己摆**，有满级上限（源桩 2 / 基段 12·25），没接上的件游戏里会标红。
   所以沙盘按「基地」分模式：
     · 选谷地 → 左栏不给源桩 / 基段；也不判「贴靠」（预设线坐标属关卡场景数据，配置表里是 0，判不了）。
     · 选武陵 → 原样：自己摆 + 上限 + 标红。
     · 自由模式（不选基地）→ 沿用武陵那套，只是不带地区名。
   ⚠️ 谷地预设线**暂不画**（博士 2026-09-21 定的：等他在游戏里给截图再按实测收录）。
      将来画的时候按「只做可视参考、不占格、不挡摆放」的口径叠在画布最外圈。 */
const LO_BUS_IDS=['log_hongs_bus_source','log_hongs_bus'];
const LO_PRESET_BUS_REGIONS=['四号谷地'];
function Lbases(){
  return ((DB.bases&&DB.bases.maxBases)||[]).map(r=>({
    levelId:r.levelId, zoneName:r.zoneName, domainName:r.domainName,
    role:r.role, side:(r.area&&r.area.side)||0,
    /* ⭐v145 页签摘要要显示「占地 / 可用格」——usableCells 已扣协议核心本体 */
    usableCells:(r.area&&r.area.usableCells)||0,
    /* ⭐v145 协议容量上限（逐基地不同：谷地主 200 / 谷地通道 100 / 武陵主 350 …）——
       容量常比面积更早到顶（枢纽区容量只够 100 台、面积能摆 192 台），摘要把占用与上限都摆出来 */
    capBw:(r.caps&&r.caps.bandwidth)||0
  })).filter(r=>!!r.side);
}
function LbaseRow(){ const L=Linit(); return Lbases().filter(r=>r.levelId===L.base)[0]||null; }
/* 当前地区名；'' = 自由模式（不限地区） */
function Lregion(){ const r=LbaseRow(); return r?r.domainName:''; }
/* 谷地：存取线是预设自动铺的 —— 玩家不摆源桩/基段，贴靠也判不了 */
function LisPresetBus(){ return LO_PRESET_BUS_REGIONS.indexOf(Lregion())>=0; }
/* 当前基地对应的「谷地存取线实测档」（bases.json 的 busObservations.zones，按 levelId 索引） */
function LbusZone(){
  const L=Linit();
  const z=(((DB.bases||{}).busObservations||{}).zones)||[];
  return z.filter(r=>r.levelId===L.base)[0]||null;
}
/* ---------- ⭐⑥-3 收货方向：从 / 到（2026-09-22 博士定）----------
   两地对称互传（规则原文：「各地区仓库互相独立，可以从其他地区的仓库传输物品到本地区仓库」），
   现在实际用的是 四号谷地 → 武陵；方向做成**下拉**、地区清单从 DB.bases.domains 动态读，
   以后新地区开放（domain_3…）不用改代码。 */
function Ldomains(){ return ((DB.bases&&DB.bases.domains)||[]); }
function LdomainName(id){ const d=Ldomains().filter(x=>x.id===id)[0]; return d?d.name:String(id); }
function LshipFromId(){ const L=Linit(); return L.shipFrom||'domain_1'; }
function LshipToId(){ const L=Linit(); return L.shipTo||'domain_2'; }
function LshipFromName(){ return LdomainName(LshipFromId()); }
function LshipToName(){ return LdomainName(LshipToId()); }
/* 改方向：选自己=无操作提示、选另一端=换向（两地对称互传的唯一入口）；出发地变 → 「出发地能产」清单变 → 旧收货选择作废；有产线就重算（开关即重算同款） */
function LshipDirV(which, id){
  const L=Linit();
  const fid=LshipFromId(), tid=LshipToId();
  const self=(which==='from')?fid:tid, other=(which==='from')?tid:fid;
  if(id===self){ L.msg='收货方向没变（仍是「'+LshipFromName()+' → '+LshipToName()+'」）'; render(); return; }
  let swap=false;
  if(id===other){
    /* 单端下拉选了另一端 → 解释为**换向**（交换两端）。两地现状下中间态必然同端，
       不这么解释「武陵→谷地」就永远配不出来 —— 对称互传（⑥-3 拍板）必须在 UI 上可达。 */
    L.shipFrom=tid; L.shipTo=fid; swap=true;
  }else{
    if(which==='from') L.shipFrom=id; else L.shipTo=id;
  }
  L.shipPick='';
  L.msg='跨地区收货方向'+(swap?'已换向':'改为')+'「'+LshipFromName()+' → '+LshipToName()+'」'+(L.plan&&L.plan.res?'，已按新方向重算':'');
  if(L.plan&&L.plan.res) LawRun(L.tgt, L.rate); else render();
}
/* ---------- 谷地预设存取线：贴在**画布外缘**的带子 ----------
   博士 2026-09-21 定的口径：「就是贴在画布外缘，不占基地格子」——
   所以整条带子画在画布框**外面**（负偏移），一格都不占，也不参与碰撞与撤销。
   摆法按基地面积页那张示意图（博士 2026-09-21 确认「就按这张示意图画」）：
     · 枢纽区   源桩占左上角 + 与之相连的上、左两条边铺满（busObservations.edges=2, source=true）
     · 三个副基地 一条边铺满、没有源桩（edges=1, source=false）
   ⚠️ 这是**示意图的摆法**，不是游戏内实测的绝对方位 —— 具体哪条边随镜头变，
      要跟游戏里对齐就用工具栏的「旋转视角」。别把它写成"实测方位"。 */
function LpresetBand(z,C,S){
  if(!z) return '';
  const W=S*C, t='四号谷地 · 预设仓库存取线（基地升级后自动铺，玩家不用摆）';
  let h='';
  if(z.source) h+='<i class="lo-pre lo-pre-src" style="left:'+(-C)+'px;top:'+(-C)+'px;width:'+C+'px;height:'+C+'px"'
    +' title="'+t+' · 源桩（占一角，基段紧贴它延伸）"></i>';
  h+='<i class="lo-pre lo-pre-h" style="left:0px;top:'+(-C)+'px;width:'+W+'px;height:'+C+'px"'
    +' title="'+t+' · 画布上边缘"></i>';
  if((z.edges||1)>=2) h+='<i class="lo-pre lo-pre-v" style="left:'+(-C)+'px;top:0px;width:'+C+'px;height:'+W+'px"'
    +' title="'+t+' · 画布左边缘（与上边缘相连）"></i>';
  return h;
}
/* 切基地：设画布边长 + 切地区模式。边长没变就保留摆放；变了就照换尺寸的规矩清空（可撤销）。 */
function LbaseSet(id){
  const L=Linit();
  const r=Lbases().filter(x=>x.levelId===id)[0];
  if(!r){ L.base=''; L.msg='已回到自由模式（不限地区）'; render(); return; }
  /* ⭐v145 多基地：切基地 = 只换指针。每个基地的摆放内容各存一份（bases[levelId]），
     切回来原样还在；不再「尺寸变了就清空」。画布边长由该基地自己的存储提供
     （首次访问时按 r.side 开画布），所以这里不写 L.size。 */
  if(L.base===r.levelId){ L.msg='当前就是「'+r.zoneName+'」'; render(); return; }
  Lpush();
  L.base=r.levelId;
  L.pick=null;
  /* ⭐⑥-3：切基地 → 收货方向「到」自动跟随当前基地所在地区（货要进**这片产线所在地区**的仓库才有用）；
     「从」若被顶成同一个地区，就自动换成另一片（两地区现状；未来 >2 地区时保持原选择即可）。 */
  const doms=Ldomains();
  const toDom=doms.filter(d=>d.name===r.domainName)[0];
  if(toDom && L.shipTo!==toDom.id){
    L.shipTo=toDom.id; L.shipPick='';
    if(L.shipFrom===L.shipTo){
      const other=doms.filter(d=>d.id!==L.shipTo)[0];
      if(other) L.shipFrom=other.id;
    }
  }
  L.msg='已切到 '+r.domainName+'·'+r.zoneName+'（'+r.role+' '+r.side+'×'+r.side+'）'
    +'，这片基地的摆放已恢复（各基地内容各存一份、互不影响）'
    +(LisPresetBus()?' —— 谷地：存取线由基地自动铺，左栏不再给源桩 / 基段'
                    :' —— 武陵：源桩 / 基段要自己摆，没接上会标红')
    +(toDom?'；收货方向已对齐「'+LshipFromName()+' → '+LshipToName()+'」':'');
  render();
}
/* ========== 生产配方：选物品 + 产能配比（2026-09-21）==========
   数据来源（都在配置表里，不是估的）：
     · DB.machine_recipes  317 条，靠 machineId ↔ 建筑 id 挂到设施上
     · DB.recipe_groups   28 个配方组，给「固态料 / 流体料分别能走哪几个接口」+ 相态
       ⚠️ 键名是 recipe_groups（下划线），不是 recipeGroups —— 构建脚本按文件名去 .json 生成键。
   相态判据：FactoryItemTable.phaseType（1 固态 / 2 液态 / 4 气态）→ 固态走传送带口、液态气态走管道口。
   ⚠️ 三条口径别记错（都写在 recipe_groups.json 里）：
     ① **不是一对一映射**：能说「固态料走 0/1/2」，不能说「1 号料进 1 号口」（灌装机 7 口 / 最多 2 料）。
     ② 组声明的是**能力上限**（组内并集，可能含预留），不保证每个配方都用得上；
        强制方向只有「配方需要的 ⊆ 组声明的」——已用 317 条配方全量回代，0 漏声明。
     ③ 已知 2 处「组多声明」记在 recipe_groups.json 的 anomalies（天有洪炉的流体产出口），别当解析错误。
   下面这组函数是**纯函数、不碰 DOM** —— 博士 2026-09-21 要求「产能配比在后台按最优计算，
   为以后全生产基地产线最精简 / 产能最大化基建摆放做准备」，所以它们是给以后排布器用的地基。 */
function RbyId(id){ return (DB.machine_recipes||[]).filter(r=>r.id===id)[0]||null; }
function Rof(machineId){
  return (DB.machine_recipes||[]).filter(r=>r.machineId===machineId)
    .sort((a,b)=>((a.sortId||0)-(b.sortId||0))||(a.id<b.id?-1:a.id>b.id?1:0));
}
function Rgroup(r){ return r?((((DB.recipe_groups||{}).groups)||{})[r.group]||null):null; }
/* ⭐v134 反应池面板（博士 2026-09-24：「布局试摆里反应池也要像游戏里那样显示缓存槽和选择输出产物」）。
   游戏事实（v133 三重核实）：一栋池子有 N 个缓存格、可同时跑多条**不同**配方（同一条不叠加提速）；
   扩容池（mix_pool_2）8 格 / 最多同时 3 条反应；基础池（mix_pool_1）格少（社区口径「以前只有 5 个口」）。
   数据依据：FactoryMachineCraftTable.buffers = 每条反应涉及的缓冲物（= 占格）。
   沙盘侧：池子机器用 o.rl（反应数组，≤ 上限）而不是 o.r（单配方）。 */
const POOL_SLOT_MAX={'mix_pool_1':2, 'mix_pool_2':3};   /* 池子 id → 同时反应数上限 */
const POOL_CELLS=8;                                      /* 缓存格数（实机口径：全解锁 8 格） */
function RisPool(b){ return !!(b&&POOL_SLOT_MAX[b.id]); }
function RpoolOf(o){ if(o&&o.rl&&o.rl.length) return o.rl.filter(Boolean); return (o&&o.r)?[o.r]:[]; }
/* 缓存格推演：把该栋已选各条反应的进料 + 出料去重 → 每格一件料（静态推演，非游戏内实时时序） */
function RpoolCells(rl){
  const cells=[];
  (rl||[]).forEach(rid=>{ const r=RbyId(rid); if(!r) return;
    (r.ingredients||[]).concat(r.outcomes||[]).forEach(x=>{
      if(!cells.some(c=>c.id===x.id)) cells.push({id:x.id, name:x.name, phase:x.phase,
        rarity:((DB.items||{})[x.id]||{}).rarity||1}); }); });
  return cells;
}
function RphaseName(t){ return (((DB.recipe_groups||{}).phaseNames)||{})[String(t)]||('相态'+t); }
/* 每分钟轮数：配方的 seconds 是「一轮多少秒」→ 一分钟 60/seconds 轮 */
function Rrounds(r){ return (r&&r.seconds)?(60/r.seconds):0; }
/* 这份配方走哪几个口（组级能力，同类接口内的下标） */
function RportSets(r){
  const g=Rgroup(r)||{};
  const flat=bs=>{ const s=[];
    (bs||[]).forEach(b=>(b.ports||[]).forEach(i=>{ if(s.indexOf(i)<0) s.push(i); }));
    return s.sort((a,b)=>a-b); };
  return {beltIn:flat(g.solidIn), pipeIn:flat(g.fluidIn),
          beltOut:flat(g.solidOut), pipeOut:flat(g.fluidOut)};
}
/* 产能：每种料的每分钟量 + 固态 / 流体分别汇总。
   传送带 30 个/分、管道 120 个/分（配置表 msPerRound 推出来的，见物流页），用来算要几条带。 */
const R_BELT_PER_MIN=30, R_PIPE_PER_MIN=120;
function Rrate(r){
  if(!r) return null;
  const k=Rrounds(r);
  const mk=rows=>(rows||[]).map(x=>({id:x.id, name:x.name, phase:x.phase||'',
    perMin:Math.round((x.count||0)*k*1000)/1000}));
  const ins=mk(r.ingredients), outs=mk(r.outcomes);
  const sum=(arr,fluid)=>arr.filter(x=>fluid?(x.phase!=='固态'):(x.phase==='固态'))
                            .reduce((s,x)=>s+x.perMin,0);
  const ps=RportSets(r);
  return {
    id:r.id, seconds:r.seconds, roundsPerMin:Math.round(k*1000)/1000,
    in:ins, out:outs,
    solidIn:Math.round(sum(ins,false)*1000)/1000, fluidIn:Math.round(sum(ins,true)*1000)/1000,
    solidOut:Math.round(sum(outs,false)*1000)/1000, fluidOut:Math.round(sum(outs,true)*1000)/1000,
    ports:ps,
  };
}
/* 要几条带 / 几条管（向上取整；0 就不需要） */
function Rcarriers(perMin,isPipe){ return (!perMin||perMin<=0)?0:Math.ceil(perMin/(isPipe?R_PIPE_PER_MIN:R_BELT_PER_MIN)); }
/* 给目标产出速率反推机器台数与各料需求 —— 排布器的入口。targetPerMin 不传就按单台算。 */
function Rplan(recipeId,targetPerMin){
  const r=RbyId(recipeId); if(!r) return null;
  const rt=Rrate(r); if(!rt) return null;
  const main=rt.out[0];
  if(!main||!main.perMin) return null;
  const n=(targetPerMin&&targetPerMin>0)?Math.ceil(targetPerMin/main.perMin):1;
  const need=rt.in.map(x=>({id:x.id, name:x.name, phase:x.phase,
    perMin:Math.round(x.perMin*n*1000)/1000, machines:Math.round(x.perMin?n:0)}));
  return {recipeId:recipeId, machines:n, perMachinePerMin:main.perMin, out:main, need:need,
    carriersIn:Rcarriers(rt.solidIn*n,false)+Rcarriers(rt.fluidIn*n,true),
    carriersOut:Rcarriers(rt.solidOut*n,false)+Rcarriers(rt.fluidOut*n,true)};
}
/* 一句配方摘要（tooltip 与计数区共用，避免两处口径不一致） */
function Rsummary(r){
  if(!r) return '';
  const rt=Rrate(r), ps=rt.ports;
  const io=rows=>rows.map(x=>x.name+(x.count>1?'×'+x.count:'')).join(' + ');
  const pn=a=>a.length?a.join('/'):'—';
  return io(r.ingredients)+' → '+io(r.outcomes)
    +' · '+rt.seconds+' 秒/轮 · 每分钟 '+rt.roundsPerMin+' 轮'
    +' · 产出 '+(rt.out.map(x=>x.name+' '+x.perMin+'/分').join('、')||'—')
    +' · 进料口：传送带 '+pn(ps.beltIn)+' / 管道 '+pn(ps.pipeIn)
    +' · 出料口：传送带 '+pn(ps.beltOut)+' / 管道 '+pn(ps.pipeOut);
}
/* 选中对象里「能选配方」的那批 —— 按第一台选中设施的机种算，同机种一起改（批量） */
function Rtargets(){
  const L=Linit();
  const sel=LselObjs();
  if(!sel.length) return [];
  const first=byBp(sel[0].id);
  if(!first||!Rof(first.id).length) return [];
  return sel.filter(o=>o.id===first.id);
}
/* 给选中的设施设配方（'' = 清掉）。批量：只动与第一台同机种的那些。 */
function LsetRecipe(rid, uid){
  const L=Linit();
  /* ⭐v135 uid 传入 = 只改这一台（浮层就地选）；不传 = 原来的「选中同机种批量改」 */
  const list=uid ? [L.objs.filter(o=>o.uid===uid)[0]].filter(Boolean) : Rtargets();
  if(!list.length){ L.msg='先选中一台生产设施（能选配方的只有有配方的那 18 台）'; render(); return; }
  Lpush();
  list.forEach(o=>{ if(rid) o.r=rid; else delete o.r; });
  const r=rid?RbyId(rid):null;
  const b=byBp(list[0].id);
  L.msg=(r?('「'+b.name+'」×'+list.length+' 已设为：'+Rsummary(r)):(b.name+'×'+list.length+' 的配方已清掉'));
  render();
}
/* ⭐v134 给选中的池子设第 i 条反应（'' = 清空该槽）。同机种批量套用，与单配方口径一致。 */
function LsetPoolSlot(i, rid, uid){
  const L=Linit();
  const list=uid ? [L.objs.filter(o=>o.uid===uid)[0]].filter(Boolean) : Rtargets();
  if(!list.length){ L.msg='先选中一台反应池（基础池 / 扩容池）'; render(); return; }
  const b=byBp(list[0].id);
  if(!RisPool(b)){ L.msg=b.name+' 不是反应池 —— 它用普通配方下拉'; render(); return; }
  Lpush();
  list.forEach(o=>{
    const rl=RpoolOf(o);
    if(rid) rl[i]=rid; else rl.splice(i,1);
    o.rl=rl.filter((x,j,a)=>x&&a.indexOf(x)===j);   /* 去重 + 去空（同一条反应选了两次只算一次） */
    delete o.r;
  });
  const cells=RpoolCells(RpoolOf(list[0]));
  L.msg='「'+b.name+'」×'+list.length+' 已设 '+RpoolOf(list[0]).length+'/'+POOL_SLOT_MAX[b.id]+' 条反应 · 缓存格占 '
    +cells.length+'/'+POOL_CELLS+(cells.length>POOL_CELLS?' —— ⚠️ 超格了，游戏里这些料塞不进一栋，删掉一条或换两栋':'');
  render();
}
/* 选中设施的配方摘要（给计数区用） */
function RselectedInfo(){
  const list=Rtargets();
  if(!list.length) return null;
  const b=byBp(list[0].id);
  const ids=[];
  list.forEach(o=>{ if(o.r&&ids.indexOf(o.r)<0) ids.push(o.r); });
  return {building:b, count:list.length, recipes:Rof(b.id), chosen:ids,
          first:list[0], isPool:RisPool(b),
          recipe:ids.length===1?RbyId(ids[0]):null};
}
/* ========== 产线闭环 · 排布器 v1（2026-09-21）==========
   博士：「做排布器，先做一次产线闭环」+「连连线也自动」+「按有启动料算，
   产线如何启动时告诉我要在哪个机器塞什么启动料」。
   流程：目标物品 + 目标速率 → 展开配方树 → 按深度分层摆机器 → 自动连传送带/管道 → 出报告。
   ⚠️ 三个真问题（都已在数据里查实，不是假设）：
     ① **配方图里有环**（全图去重 25 组）。例：赤铜耐压罐 ← 塑形机 ← 赤铜块 + 惰气；
        而惰气 ← 拆解机 ← 赤铜耐压罐。但拆解机配方是「1 罐进、1 罐 + 1 惰气出」——
        **罐子没被消耗，它只是载体** → 不是死循环，是「**需要一颗种子**」：塞 1 个罐子就能自持。
        处理：能换配方就避环（赤铜块改走精炼炉那条），避不开就标 seed 并输出**启动清单**。
     ② **200 个物品能机器产、其中 40 个有多份配方** → 必须自己选。评分：先避开环，再取单台产出最高的（台数最少）。
     ③ **原料 = 没有机器配方的物品**（蓝铁矿 / 赤铜矿 / 清水 / 惰气…）——野外采集或外部输入，基地里不摆。
   ⚠️ v1 **不做**（写清楚，别当成有）：最优布局搜索、带拥堵与吞吐校验、
      **多条并行带的自动并联**（一条依赖只连一条线，需要并联会在报告里点名）、绕线避让优化。 */
const RW_BELT=30, RW_PIPE=120;
function RwMade(regionName){
  /* itemId → 能产出它的配方列表（按地区过滤缓存）。
     ⭐⑥-3 对称互传（2026-09-22 博士）：「出发地能产」要按**出发地的机器**算 ——
     天有洪炉（息壤/重息壤/膨地啪的唯一产地）是武陵限定，谷地集成工业产不了它们，
     所以从谷地出发就不能传这三件（游戏口径：本地区集成工业可生产的任意一种物品）。
     不传 regionName = 不过滤（评分/展开/老路径全都不受影响，缓存键分开）。 */
  const key=regionName||'*';
  if(!RwMade._c) RwMade._c={};
  if(RwMade._c[key]) return RwMade._c[key];
  const m={};
  const _bmap={};
  (DB.buildings||[]).forEach(b=>{ _bmap[b.id]=b; });
  (DB.machine_recipes||[]).forEach(r=>{
    if(regionName){
      const b=_bmap[r.machineId];
      if(b && !b.isUniversal && (b.domainNames||[]).indexOf(regionName)<0) return;
    }
    (r.outcomes||[]).forEach(o=>{(m[o.id]=m[o.id]||[]).push(r);});
  });
  RwMade._c[key]=m; return m;
}
function RwItemName(id){ return ((DB.items||{})[id]||{}).name||id; }
/* 物品相态（固态 → 传送带；液态/气态 → 管道）。
   ⚠️ 必须查得到：配方树里的**中间节点也要有相态**，否则连线时会按"固态"去走传送带口，
   液态料就接不上（2026-09-21 实测踩到：清水的连接报"传送带口不够"）。 */
function RwPhaseOf(id){
  if(!RwPhaseOf._c){
    const m={};
    (DB.machine_recipes||[]).forEach(r=>{
      (r.ingredients||[]).concat(r.outcomes||[]).forEach(x=>{ if(x.phase) m[x.id]=x.phase; });
    });
    RwPhaseOf._c=m;
  }
  return RwPhaseOf._c[id]||'';
}
function RwFluid(phase){ return !!phase && phase!=='固态'; }
/* 单台每分钟「产出该物品」的量（取该物品在产物里的那一项；317 条里多数只有 1 个产物，
   但拆解机那种是「罐子进、罐子+惰气出」，必须按目标物品那一项算，不能取 outcomes[0]） */
function RwPerMin(r, iid){
  if(!r||!r.seconds) return 0;
  const outs=r.outcomes||[];
  const o=iid?outs.filter(x=>x.id===iid)[0]:null;
  const use=o||outs[0];
  return use?(use.count*60/r.seconds):0;
}
/* 「载体」料：原料 id 也出现在产物里 → 只是过一遍，净消耗 0（拆解机的罐子就是这种） */
function RwCarrierIds(r){
  const outs={}; (r.outcomes||[]).forEach(o=>{ outs[o.id]=o.count; });
  const c=[]; (r.ingredients||[]).forEach(i=>{ if(outs[i.id]!==undefined) c.push(i.id); });
  return c;
}
/* 「分离配方」：原料里有自己产的这个物品 —— 那是拆解/提纯，不是"造"。
   造东西必须用**不吃自己**的配方（拆解机能拆出惰气，但它不叫"造惰气"）。 */
function RwIsSplit(r, iid){ return (r.ingredients||[]).some(i=>i.id===iid); }
/* ⚠️ 「回收配方」——2026-09-21 的关键修正，一步判定：某个原料是**用本物品做出来的**。
   典型：拆解机 ← 装水的赤铜罐，而装水罐是灌装机用「空罐（就是本物品）」灌出来的
   → 那条拆解机配方是**回收**，不是"造空罐"。把它当生产配方会选错路线。
   ⚠️ 为什么必须用 id 判：空罐 `item_copper_jar` 和装水罐 `item_gasjar_copper_gas_water`
      **名字都显示成「赤铜耐压罐」，但是两个不同物品**。按名字判会全错。 */
function RwIsRecycle(r, iid){
  const carriers=RwCarrierIds(r);
  return (r.ingredients||[]).some(i=>{
    if(carriers.indexOf(i.id)>=0) return false;
    return (RwMade()[i.id]||[]).some(r2=>(r2.ingredients||[]).some(j=>j.id===iid));
  });
}
/* 只有回收路线的物品，直接当「需外部输入」，不再往里钻 ——
   否则会拖出一串「灌装机 ↔ 拆解机」来回倒（惰气就是这种：唯一做法是拆装惰气的罐子）。 */
const RW_STOP_AT_RECYCLE=true;
/* 链深上限：超过就当「外部输入 / 外购」，并写明原因。
   为什么需要它：像**清水**这种其实是在野外用抽水泵抽的（配置表里没有"泵能抽什么"的字段 —— 那依赖地形，
   属关卡场景数据），但配方表里它有「提纯机 ← 惰性壤晶废液 ← 液化息壤 ← 天有洪炉 ← …」一条巨链。
   不限深的话，10/分 赤铜耐压罐会展开成 90 台机器。限深后清水→提纯机只展开到 3 层，规模可控，
   而且报告里会明确写「按外部输入处理」，不会悄悄少算。 */
const RW_MAX_DEPTH=3;
/* 规模闸门：展开超过这么多台就不生成，改成报告里说明原因（免得画布上堆一坨垃圾） */
const RW_MAX_MACHINES=60;
/* ⭐⭐ ⑥-4 建筑专属限摆（2026-09-22 博士拍板 + 查证）：
   配置表 buildings.json 的 hasPlaceLimit 字段**不含「科技解锁型限摆」数据域** —— 天有洪炉在
   1.5.3 配置表里 hasPlaceLimit=false，但游戏里息壤工业科技满级也只许摆 **12 台**（武陵合计；
   1.2 工业计划从 8 抬到 12，3DM/TapTap/NGA/1.4 蓝图攻略四源印证）。这类是运行时系统数值
   （同矿脉产率），配置表拿不到，手工维护本表；版本更新抬上限时改这里。
   口径：**报警不拦截** —— 超限产线照常生成（对分期建造/降速规划仍有参考价值），msg 点名超限。 */
const RW_PLACE_LIMITS={
  xiranite_oven_1:{ n:12, name:'天有洪炉', why:'息壤工业科技满级（1.2 工业计划起 8 → 12，武陵合计）' }
};
/* 按机器蓝图对台数求和再对表 —— 单目标/多目标（RexplodeFinal 共享段）两条路径的 res.machines 都适用 */
function RwPlaceLimitWarn(res){
  const out=[], cnt={};
  (res.machines||[]).forEach(n=>{ if(n.machineId) cnt[n.machineId]=(cnt[n.machineId]||0)+(n.machines||0); });
  Object.keys(RW_PLACE_LIMITS).forEach(mid=>{
    const lim=RW_PLACE_LIMITS[mid], got=cnt[mid]||0;
    if(got>lim.n) out.push(lim.name+' 超限：这条链要 '+got+' 台，游戏里 '+lim.why+'最多 '+lim.n+' 台 —— 降低速率或用跨地区收货补上游料');
  });
  return out;
}
/* 【一句话】递归估「做这件料要绕多远」——给 Rexplode 的 pick() 排序，选子树代价最低的配方。
   —— 0 = 已经是原料；越大越难得；绕回路径给大惩罚（RW_COST_CYCLE）。
   —— 这一条是 06:0x 那版翻车的直接原因：只看"这一步有没有回头"会选到高产出但绕圈的配方。 */
const RW_COST_CYCLE=500, RW_COST_CARRIER=2, RW_COST_DEPTH=5, RW_COST_BUDGET=4000;
function RwCost(iid, path, depth, budget){
  budget=budget||{n:0};
  if(budget.n++>RW_COST_BUDGET) return 50;
  if(path.indexOf(iid)>=0) return RW_COST_CYCLE;
  if(depth>=RW_COST_DEPTH) return 8;
  const cands=(RwMade()[iid]||[]).filter(r=>!RwIsSplit(r,iid));
  if(!cands.length) return 0;                      /* 没有「造」的配方 → 当原料/需外部给 */
  let best=1e9;
  cands.forEach(r=>{
    const carriers=RwCarrierIds(r);
    let c=1;
    (r.ingredients||[]).forEach(i=>{
      c += (carriers.indexOf(i.id)>=0) ? RW_COST_CARRIER : RwCost(i.id, path.concat([iid]), depth+1, budget);
    });
    if(c<best) best=c;
  });
  return best;
}
/* ⭐⭐ ⑥-1 跨地区供货（2026-09-22，博士：只用「四号谷地 → 武陵」超库存传输）
   口径（全部来自配置表 / 文案，见 DB.rules 里的 rule_domain_transfer）：
     · 出发地 = 四号谷地（domain_1），可传「本地区集成工业可生产的任意一种物品」；
     · 超库存传输**不扣出发地库存**、目的地直接获得 → 出发地只需要「有产能」就行，
       所以判定依据是 **RwMade() 里有没有本地区的机器配方**，不是仓库里有没有货；
     · 目的地收货侧：那件料只要在 `DB.items[.domains]` 里（= FactoryItemTable.transferDomainIds 非空）
       就**能送到**，所以收货侧按「能送到」处理 —— 纯函数，不读全局开关，opts 传进来方便测试。 */
function RwCanShip(iid, made){
  const m = made || RwMade();
  return !!(m[iid] && m[iid].length);
}
function RwCanReceive(iid){
  const d=(DB.items||{})[iid];
  return !!(d && (d.domains||[]).length);
}
/* 【一句话】把目标物品的配方树递归展开成一张机器图（节点=机器、边=物流）。
   纯函数（selfLoop 走 opt 传进来，不读全局，方便测试）。
   opt.selfLoop=true = 「闭环自持」开关：
     只有回收路线的物品**照样往里展开**，靠 载体 / 链上绕回 形成闭环，
     并把启动时要塞的东西记进 seeds —— 博士 2026-09-21 要的就是这个。
   默认 false = 那种料按「外部输入」处理（链短、好摆）。 */
function Rexplode(targetId, perMin, opt){
  /* 【分节总览】递归展开主循环（从叶子回溯，不是自顶向下）：
       ① 解析 opt（selfLoop / shipInList / seeds / region）—— 见下面 ⭐⑥-1/2/3
       ② 对每个节点：`pick()` 选配方（三级降级）→ `RwCost` 排序 → 递归子料
       ③ memo 去重：同料只建一套（多目标时挂幽灵边 ref 回指）
       ④ 收尾交 `RexplodeFinal` 做需求汇总 / 台数重算 / 层级重排（单目标直接跳过）
     本函数只建「图」，不做布局 —— 摆位是 LawPlan、布线是 RwRoute。 */
  opt=opt||{};
  const selfLoop=!!opt.selfLoop;
  /* ⭐⑥-1：跨地区收货清单 —— 这些料不从野外采、也不在本地做，改由**别的地区传过来**。
     只为「能送到」的料建（RwCanReceive），送不到的照样按原来的原料处理。
     ⚠️ 参数名用 shipInList，别用 shipIn —— 那是 Linit() 里的**布尔开关**，同名会炸。 */
  const shipIn={};
  const shipInList=(opt.shipInList && typeof opt.shipInList.forEach==='function')?opt.shipInList:[];
  shipInList.forEach(x=>{ const iid=(typeof x==='string')?x:(x&&x.itemId);
    if(iid && RwCanReceive(iid)) shipIn[iid]=1; });
  /* ⭐⑥-2 多目标共享中间产物（2026-09-22）：opt.seeds = [{itemId,perMin},…] 时按「一图多目标」展开 ——
     同一件中间料只建**一套**机器（memo 去重：需求合并、台数按合并需求重算、层级沉到最深消费者下面），
     每个消费者挂一条「幽灵边」（ref 回指共享节点），路由层按幽灵边逐条连线 / 分流。
     ⚠️ 不传 seeds 就是单目标老路径，一行都不多跑（601 项回归逐字节依赖它）。 */
  const seedList=(opt.seeds&&opt.seeds.length)?opt.seeds.map(s=>({itemId:s.itemId, perMin:+s.perMin||0})):null;
  const useDedup=!!seedList;
  const seedArr=seedList||[{itemId:targetId, perMin:perMin}];
  const memo={}, allEdges=[], softEdges=[], allReal=[];
  /* ⭐⑥-3：opt.region = 按「这个地区有哪些机器」过滤配方（选点分析用）；
     不传 = 不过滤（老路径一字不变）。opt.shipFromName = 收货文案里的出发地地区名。 */
  const _made0=RwMade(opt.region||'');
  const made={};
  /* 跨地区收货的料在本地「没有配方」→ pick 返回 null → 自动落进原料分支。
     这里只是让 RwCost 的选路也看不见它们（否则它还会往里算子树代价）。 */
  Object.keys(_made0).forEach(k=>{ if(!shipIn[k]) made[k]=_made0[k]; });
  const seeds=[], warns=[], raw=[], externals=[];
  const r3=x=>Math.round(x*1000)/1000;
  function pick(iid, path){
    const all=made[iid]||[];
    if(!all.length) return null;
    /* ① 首选「不吃自己 且 不是回收」的生产配方 */
    let cand=all.filter(r=>!RwIsSplit(r,iid) && !RwIsRecycle(r,iid));
    let recycled=false;
    if(!cand.length){
      /* ② 没有纯生产配方：只剩回收路线。
         默认 → 当外部输入（别往里钻）；
         开了「闭环自持」→ 钻进去，让 载体/绕回 变成启动料。 */
      if(RW_STOP_AT_RECYCLE && !selfLoop) return {external:true};
      cand=all.filter(r=>!RwIsSplit(r,iid));
      recycled=true;
      if(!cand.length){ cand=all.slice(); }        /* ③ 最后才退回载体/拆分路线 */
    }
    /* 比子树代价（能不能便宜地做到原料），再比单台产出（台数最少） */
    const cost=r=>{
      const carriers=RwCarrierIds(r), b={n:0};
      return (r.ingredients||[]).reduce((s,i)=>s+((carriers.indexOf(i.id)>=0)
        ? RW_COST_CARRIER : RwCost(i.id, path.concat([iid]), 1, b)), 1);
    };
    /* ⭐v136 B（对标调研：同物品多配方按「单位原料成本 + 电力」比，局部改进不引入 LP）：
       ①**单位**原料成本 = 每轮原料成本 ÷ 本轮产出该物品的数量（产出 2 个的，单个成本折半）
       ②**每轮耗电** = 该配方所属机器的单台耗电 ÷ 每分钟轮数（不同机种换算到同一「每轮」口径）
       ③单台产出（台数最少）
       三层**分层比较**，不引入加权魔法数字 —— 原料优先、耗电其次、产出垫底，
       行为可解释：同样的料谁便宜选谁，一样便宜省电，都省则台数少。 */
    const unitCost=r=>{
      const oc=(r.outcomes||[]).filter(x=>x.id===iid).reduce((s2,x)=>s2+(x.count||0),0)||1;
      return cost(r)/oc;
    };
    const powerPerRound=r=>{
      const b=byBp(r.machineId), pc=b?((+b.powerConsume)||0):0;
      const rounds=(r.seconds>0)?(60/r.seconds):1;
      return pc/Math.max(0.001,rounds);
    };
    cand.sort((a,b)=>(unitCost(a)-unitCost(b)) || (powerPerRound(a)-powerPerRound(b))
                    || (RwPerMin(b,iid)-RwPerMin(a,iid)));
    return {r:cand[0], recycled:recycled};
  }
  function build(iid, demand, depth, path){
    const n={itemId:iid, name:RwItemName(iid), phase:RwPhaseOf(iid), demand:r3(demand), depth:depth,
             recipeId:null, machineId:null, machineName:'', machines:0, perMachine:0, actualOut:0,
             children:[], raw:false, seed:false, carrier:false, external:false, recycled:false, note:''};
    const ch=pick(iid, path);
    if(!ch){
      n.raw=true; n.seed=true;
      if(shipIn[iid]){ n.shipIn=true; n.note='跨地区收货：由出发地（'+(opt.shipFromName||'四号谷地')+'）超库存传输过来，本地不建产线'; }
      if(raw.indexOf(iid)<0) raw.push(iid); return n;
    }
    if(ch.external){
      n.raw=true; n.seed=true; n.external=true;
      n.note='唯一做法是回收路线 → 按「需外部输入」处理：启动时给一次，之后靠循环自持';
      /* ⭐v136（对标调研 D 项）：以前这条只写在节点 note 上，报告警告区**不出声** —— 属于静默降级。
         现在明确报出来：这是「绕不开的循环」，工具不会替你展开，需要玩家开局给一次料或开闭环自持。 */
      warns.push(n.name+'：只能走回收路线（绕不开的循环）—— 工具不会自动展开它，按「外部输入」处理。'
        +'处理办法：开局给一次料让它自持，或打开「闭环自持」让工具算启动清单');
      if(raw.indexOf(iid)<0) raw.push(iid);
      if(externals.indexOf(iid)<0) externals.push(iid);
      return n;
    }
    const r=ch.r;
    n.recycled=!!ch.recycled;
    /* ⭐⑥-2：这件料已经建过一套 → 不再建第二套，返回「幽灵边」节点（ref 回指共享节点；
       需求/台数/层级由 RexplodeFinal 按合并口径统一重算，路由层把幽灵边当一条普通依赖连） */
    if(useDedup && memo[iid]){
      return {itemId:iid, name:n.name, phase:n.phase, demand:r3(demand), depth:depth,
        recipeId:memo[iid].recipeId, machineId:memo[iid].machineId, machineName:memo[iid].machineName,
        machines:memo[iid].machines, ghost:true, ref:memo[iid],
        pname:(path.length?RwItemName(path[path.length-1]):'')};
    }
    if(useDedup){ memo[iid]=n; allReal.push(n); }
    /* 链深到顶还想往下做的：按外部输入处理（清水就是这种——实际靠野外抽水泵，不是自己造） */
    if(depth>=RW_MAX_DEPTH && (made[iid]||[]).length){
      n.raw=true; n.seed=true; n.external=true;
      n.note='链深已达 '+RW_MAX_DEPTH+' 层上限 → 按「外部输入 / 外购」处理（这类料通常是野外采集，如清水）';
      warns.push(n.name+'：链深到 '+RW_MAX_DEPTH+' 层上限就不再往下展开，按外部输入算（通常没问题：这类料多在野外采集）');
      if(raw.indexOf(iid)<0) raw.push(iid);
      if(externals.indexOf(iid)<0) externals.push(iid);
      return n;
    }
    const pm=RwPerMin(r, iid);
    n.recipeId=r.id; n.machineId=r.machineId; n.machineName=r.machineName;
    n.perMachine=r3(pm); n.machines=Math.max(1, Math.ceil(demand/(pm||1)));
    n.actualOut=r3(n.machines*pm);
    /* ⚠️⑥-2：多目标路径的这条警告挪到 RexplodeFinal（台数按合并需求重算后再判才有意义） */
    if(!useDedup && n.actualOut>r3(demand)+1e-6) warns.push(n.name+'：按整台算，实际产出 '+n.actualOut+'/分，比需要的 '+n.demand+'/分 多 '+r3(n.actualOut-n.demand));
    const oc=(r.outcomes.filter(x=>x.id===iid)[0]||r.outcomes[0]||{}).count||1;
    /* ⭐C6-b 阶段1（2026-09-25，博士拍板）：**配方副产物入图**。
       背景：`outcomes` 原先只用来取主产物的 count，第二产出（污水 / 壤晶废液 / 沉积酸…）
       在产线图里**完全不存在** → 排布器看不见、不摆、不算，而社区实例里引发全基地断电的
       正是这类东西（赤铜精炼的污水）。C6-a 体检只能事后扫配方兜底；C6-b 让它们进图。
       口径：副产物量 = 本机实际产出 × (副产物count / 主产物count)（同一轮反应的比例）。
       位置：挂 `n.byproducts`（**不进 children / 不进 walk 树**）→ 图结构、布局、走线一字不动，
       纯数据层新增。阶段 2 再据它补销毁支线（软门禁）。
       ⚠️ 载体（原料 id 也在产物里）不算副产物 —— 那只是过一遍，净消耗 0。 */
    n.byproducts=(r.outcomes||[]).filter(o=>o.id!==iid && !(RwCarrierIds(r).indexOf(o.id)>=0))
      .map(o=>({itemId:o.id, name:o.name||RwItemName(o.id), phase:o.phase||RwPhaseOf(o.id),
        perMin:r3(n.actualOut*((o.count||0)/oc)), count:o.count||0, fromRecipe:r.id,
        fromMachine:n.machineName, byproduct:true}));
    const carriers=RwCarrierIds(r);
    (r.ingredients||[]).forEach(i=>{
      const tot=r3(n.actualOut*(i.count/oc));
      if(carriers.indexOf(i.id)>=0){
        const c={itemId:i.id, name:i.name, phase:i.phase, carrier:true, demand:0, need:i.count,
          note:'载体：净消耗 0，但启动时要先塞 '+i.count+' 个'};
        n.children.push(c);
        softEdges.push({p:n, node:c, cnt:i.count, oc:oc, kind:'carrier'});
        seeds.push({itemId:i.id, name:i.name, count:i.count, machineName:n.machineName,
          machineId:n.machineId, reason:'载体（净消耗 0）'});
        return;
      }
      if(path.indexOf(i.id)>=0 && made[i.id]){
        const c={itemId:i.id, name:i.name, phase:i.phase, seed:true, demand:tot,
          note:'链上绕回自己（需启动料 / 或用回收路线）'};
        n.children.push(c);
        softEdges.push({p:n, node:c, cnt:i.count, oc:oc, kind:'loop'});
        seeds.push({itemId:i.id, name:i.name, count:i.count, machineName:n.machineName,
          machineId:n.machineId, reason:'链上绕回'});
        return;
      }
      const c=build(i.id, tot, depth+1, path.concat([iid]));
      /* ⭐⑥-2：所有「消费边」统一包成幽灵边（**含首次创建的共享节点**）——
         否则首个消费者的边是实体子节点、其余是幽灵边，两套口径会让路由/记账打架。
         子节点本体永远只经由 ghost.ref 被引用；单目标路径（useDedup=false）不走这里。 */
      if(useDedup && c.recipeId && !c.ghost){
        const g={itemId:c.itemId, name:c.name, phase:c.phase, demand:tot, depth:c.depth,
          recipeId:c.recipeId, machineId:c.machineId, machineName:c.machineName,
          machines:c.machines, ghost:true, ref:c, pname:RwItemName(iid)};
        n.children.push(g);
        allEdges.push({to:c, from:n, ghost:g, cnt:i.count, oc:oc});
        return;
      }
      n.children.push(c);
      /* ⭐⑥-2：机器子节点记一条边（幽灵边 ref 回指共享节点；需求由 RexplodeFinal 沿边统一摊）。
         原料/绕回子节点记软边 —— 父节点台数重算后它们的 demand 要跟着最终 actualOut 刷新。 */
      if(c.recipeId) allEdges.push({to:(c.ghost?c.ref:c), from:n, ghost:(c.ghost?c:null), cnt:i.count, oc:oc});
      else softEdges.push({p:n, node:c, cnt:i.count, oc:oc, kind:'raw'});
    });
    return n;
  }
  const rootObjs=[];
  seedArr.forEach(s=>{
    const rn=build(s.itemId, s.perMin, 0, []);
    allEdges.push({to:(rn.ghost?rn.ref:rn), seed:true, perMin:s.perMin, ghost:(rn.ghost?rn:null)});
    rootObjs.push(rn);
  });
  /* ⭐⑥-2：多目标路径先「需求汇总 → 台数重算 → 层级重排」，再收集节点（单目标跳过，老路径一字不变） */
  if(useDedup) RexplodeFinal(allReal, allEdges, softEdges, warns);
  const nodes=[], machines=[]; const seenD=new Set();
  const walk=function(n){
    if(n.ghost){ walk(n.ref); return; }
    if(seenD.has(n)) return; seenD.add(n);
    nodes.push(n); if(n.machines) machines.push(n);
    (n.children||[]).forEach(walk);
  };
  rootObjs.forEach(walk);
  /* ⭐v133 扩容反应池同池并行合并（改物理池子数，不动需求/产出；单/多目标两条路径都过这里） */
  RwPoolUpgrade(nodes);          /* 同组 ≥2 条配方 → 基础池整组升扩容池（单配方保持基础池） */
  const poolMerge=RwPoolMerge(nodes);
  /* 合并后 machines=0 的节点（已并入主体池子）从机器清单剔除 —— 清单只留真实要摆的机器 */
  for(let mi=machines.length-1;mi>=0;mi--){ if(!machines[mi].machines) machines.splice(mi,1); }
  const shipIns=nodes.filter(n=>n.shipIn);
  const tgts=seedArr.map(s=>({id:s.itemId, name:RwItemName(s.itemId), perMin:s.perMin}));
  /* ⭐C6-b 阶段1：副产物汇总（每台机器的 recipes 副产物 + 按台数折算的速率）——
     供报告层与阶段 2 的销毁支线规划用。**不进 nodes / machines** → 布局零影响。 */
  const byproducts=[];
  nodes.forEach(n=>{
    if(!n.byproducts || !n.byproducts.length) return;
    n.byproducts.forEach(b=>byproducts.push(Object.assign({}, b, {
      machineId:n.machineId, machines:n.machines, node:n
    })));
  });
  return {root:rootObjs[0], nodes:nodes, machines:machines, raw:raw, externals:externals, seeds:seeds, warns:warns,
          shipIn:shipIns, byproducts:byproducts,
          target:targetId, targetName:RwItemName(targetId), perMin:perMin,
          targets:(seedArr.length>1?tgts:null),
          shared:(useDedup?allReal.filter(n=>n.sharedTo&&Object.keys(n.sharedTo).length):[]),
          poolMerge:poolMerge,
          totalMachines:machines.reduce((s,n)=>s+n.machines,0)};
}
/* ⭐v133 扩容反应池「同池并行」（博士 2026-09-24 实机 + 官方文案 + 社区实测三重核实）：
   官方文案：「拥有更多的端口并可同时进行更多的化学反应」；实机口径：一栋 8 个缓存格，
   最多同时跑 3 条不同反应；NGA 实测补充：多条**不同**配方同池并行、各跑各的额定速度，
   **同一条配方不能并行提速**（速度不叠加）。因此我们按「一条配方一栋」算会多算池子
   （典型：息壤→液化息壤→壤晶废液→壤晶 三段反应，游戏里 1 栋扩容池、我们原本算 3 栋）。
   合并口径：同池并行配方的 buffers 物品并集 ≤ RW_POOL_SLOTS → 栋数 = 组内 max(n_i)
   （每栋对其中每条配方各贡献 1 份产能）；并集超限 → 贪心分组、组间栋数相加。
   ⚠️ 只改「物理池子数」：各配方的需求 / 产出 / 下游传播一律不动（产出不变，与实机一致）。
   范围：只处理扩容反应池（RW_POOL_FACILITY）；基础反应池保持现状（博士 2026-09-24 定）。 */
const RW_POOL_SLOTS=8;
const RW_POOL_FACILITY='mix_pool_2';
/* ⭐v133 池子变体升级：默认选基础反应池（更便宜更小）；只有当**同组出现 ≥2 条不同配方**
   （展开完才知道）时才有「同池并行」收益 —— 那时把该组节点整组换成扩容池变体
   （唯一能塞下多条并行的池子），再交给 RwPoolMerge 合并。
   单配方仍用基础池：扩容池 100 电 / 6×5 占地 vs 基础池 50 电 / 5×5，无并行收益时纯亏。 */
function RwPoolUpgrade(nodes){
  /* 池子节点：mix_pool_1（基础池）/ mix_pool_2（扩容池）都算「反应池类」。
     ⚠️ 同一反应在两个池子上各有变体，且 **group 名不同**（group_mix_pool_1_liquid vs
     group_mix_pool_2_liquid）—— 「是不是同一条反应」要用原料/产物签名（sig）判，
     不能用 group 名或 recipeId（_1 / _2 后缀不同）。 */
  const isPool=r=>r&&(r.machineId==='mix_pool_1'||r.machineId===RW_POOL_FACILITY);
  const sig=r=>JSON.stringify((r.ingredients||[]).map(x=>x.id+'x'+x.count).join('+')+' > '+
                              (r.outcomes||[]).map(x=>x.id+'x'+x.count).join('+'));
  const pool=nodes.filter(n=>isPool(RbyId(n.recipeId)));
  if(pool.length<2) return 0;
  const kinds={};
  pool.forEach(n=>{ const r=RbyId(n.recipeId); if(r) kinds[sig(r)]=1; });
  if(Object.keys(kinds).length<2) return 0;      /* 只有一种反应 → 无并行收益，保持基础池 */
  const exp=Rof(RW_POOL_FACILITY);
  let upgraded=0;
  pool.forEach(n=>{
    const r0=RbyId(n.recipeId);
    if(!r0||r0.machineId===RW_POOL_FACILITY) return;      /* 已是扩容池变体 */
    const twin=exp.filter(x=>sig(x)===sig(r0))[0];
    if(!twin) return;                                     /* 找不到孪生变体就保持原样（防呆） */
    n.recipeId=twin.id; n.machineId=twin.machineId; n.machineName=twin.machineName;
    const pm=RwPerMin(twin, n.itemId);
    n.perMachine=Math.round(pm*1000)/1000;
    n.machines=Math.max(1, Math.ceil(n.demand/(pm||1)));   /* 产能同 → 与升级前一致 */
    upgraded++;
  });
  return upgraded;
}
function RwPoolMerge(nodes){
  const pool=nodes.filter(n=>n.machineId===RW_POOL_FACILITY && n.machines>0);
  if(pool.length<2) return null;
  const bset=n=>{ const r=RbyId(n.recipeId); return ((r&&r.buffers)||[]).map(b=>b.id); };
  const groups=[];
  pool.slice().sort((a,b)=>b.machines-a.machines).forEach(n=>{
    const s=bset(n);
    let target=null;
    for(const g of groups){
      const u=g.set.concat(s.filter(x=>g.set.indexOf(x)<0));
      if(u.length<=RW_POOL_SLOTS){ target=g; g.set=u; break; }
    }
    if(!target){ target={set:s.slice(), members:[]}; groups.push(target); }
    target.members.push(n);
  });
  const out=[];
  groups.forEach(g=>{
    const total=Math.max.apply(null, g.members.map(m=>m.machines));
    const lead=g.members[0];
    const saved=g.members.reduce((s,m)=>s+m.machines,0)-total;
    lead.machines=total;
    lead.poolMerge={count:total, members:g.members.map(m=>m.name), slots:g.set.length, saved:saved};
    g.members.slice(1).forEach(m=>{ m.machines=0; m.poolWith=lead.name; });
    if(saved>0) out.push(lead.poolMerge);
  });
  return out.length?out:null;
}
/* 【一句话】多目标图的收尾结算：需求沿边摊开 → 台数重算 → 层级重排 → 生成告警。
   ⭐⑥-2 配套（2026-09-22）：多目标 DAG 的「需求汇总 → 台数重算 → 层级重排」。
   输入 build 期收集的 allEdges（机器→机器的边，含种子边与幽灵边）与 softEdges（原料/绕回/载体边）。
   Kahn：需求沿边自上而下摊（父 actualOut × 配比），某节点的**全部入边**都定了才轮到它 ——
   多父合流自动求和；台数 = ceil(合并需求 / 单台速率)；「按整台算多产出」的警告在这里统一生成。
   层级：最长路松弛（DAG 必停）—— 共享节点沉到**最深消费者**下面，出料向上自然分流。 */
function RexplodeFinal(allReal, allEdges, softEdges, warns){
  const r3=x=>Math.round(x*1000)/1000;
  const pend=new Map(), outs=new Map();
  allReal.forEach(n=>{ pend.set(n,0); outs.set(n,[]); });
  const machEdges=allEdges.filter(e=>!e.seed);
  const seedEdges=allEdges.filter(e=>e.seed);
  /* ⚠️ 种子边也要计入 pend（否则根节点 pend 被种子边的 -1 减成负数，
     `===0` 的就绪过滤会把根挡在队列外 → 整张图永远停在 build 期旧值 —— 首跑实测踩中） */
  allEdges.forEach(e=>{ pend.set(e.to,(pend.get(e.to)||0)+1); });
  machEdges.forEach(e=>{ if(e.from&&outs.get(e.from)) outs.get(e.from).push(e); });
  seedEdges.forEach(e=>{ e.demand=r3(e.perMin); pend.set(e.to,(pend.get(e.to)||0)-1); });
  const q=allReal.filter(n=>(pend.get(n)||0)<=0);
  const done=new Set();
  while(q.length){
    const n=q.shift();
    if(done.has(n)) continue; done.add(n);
    const D=allEdges.reduce((s,e)=>s+((e.to===n&&e.demand!=null)?e.demand:0),0);
    n.demand=r3(D);
    if(n.external || !n.recipeId){
      /* ⭐⭐ 2026-09-22 全库扫描抓到的计算 bug：外部输入节点（链深到顶按 external 处理的，
         如清水链顶的息壤/赫铜溶液）perMachine=0、machineId=null，落到下面的
         ceil(demand/1) 会凭空算出 demand 台「空气机器」（息壤 10/分 → 10 台），
         混进 res.machines 后 LawPlan 里 byBp(null) 静默丢、msg 还按虚数报「机器 37 台」。
         这类节点本来就没有机器：demand 照记（原料需求口径读它），台数恒 0。
         单目标路径不走 RexplodeFinal（external 本来就 machines=0），所以 668 项回归没炸过 —— 多目标(⑥-2)专属坑。 */
      n.machines=0; n.actualOut=0;
    }else{
      n.machines=Math.max(1, Math.ceil(n.demand/(n.perMachine||1)));
      n.actualOut=r3(n.machines*n.perMachine);
      if(n.actualOut>r3(n.demand)+1e-6) warns.push(n.name+'：按整台算，实际产出 '+n.actualOut+'/分，比需要的 '+n.demand+'/分 多 '+r3(n.actualOut-n.demand));
    }
    (outs.get(n)||[]).forEach(e=>{
      e.demand=r3(n.actualOut*(e.cnt/e.oc));
      if(e.ghost){
        e.ghost.demand=e.demand;
        /* sharedTo 记在**共享节点**（e.to）头上：谁在用它、各用多少 —— 报告的「共用中间料」段读它 */
        if(e.ghost.pname){ const t=e.to; t.sharedTo=t.sharedTo||{};
          t.sharedTo[e.ghost.pname]=r3((t.sharedTo[e.ghost.pname]||0)+e.demand); }
      }
      const t=e.to; pend.set(t,(pend.get(t)||0)-1); if((pend.get(t)||0)===0) q.push(t);
    });
  }
  /* 原料/绕回子节点的需求跟着最终 actualOut 刷新（载体 need 不变：启动塞料按配方算） */
  softEdges.forEach(se=>{ if(se.kind!=='carrier') se.node.demand=r3(se.p.actualOut*(se.cnt/se.oc)); });
  /* 层级：最长路松弛 —— 共享节点必须沉到它最深的消费者下面，线才都往上走 */
  const dep=new Map(); allReal.forEach(n=>dep.set(n,0));
  let changed=true, guard=0;
  while(changed && guard++<2000){
    changed=false;
    machEdges.forEach(e=>{
      if(!e.from) return;
      const nd=dep.get(e.from)+1;
      if(nd>dep.get(e.to)){ dep.set(e.to, nd); changed=true; }
    });
  }
  allReal.forEach(n=>{ n.depth=dep.get(n); });
  /* 幽灵边镜像最终值（depLines 估算 / 报告要读） */
  allEdges.forEach(e=>{ if(e.ghost){ e.ghost.machines=e.to.machines; e.ghost.actualOut=e.to.actualOut; e.ghost.depth=e.to.depth; } });
}

/* ---------- 摆位：按深度分层 ----------
   机器一律 rot=0 → 进料口在**下边**(z=D-1)、出料口在**上边**(z=0)，物料自下而上。
   depth 越小越接近成品 → 放在**上面**（y 小）；depth 大 = 原料侧 → 放在下面。
   层与层之间留 RW_CORR 行空行当走线通道（管线只在这段里横穿，不压机器）。 */
/* 树节点 → 稳定 key（⑤-1 局部锁定用它把画布上的机器对回配方树节点）。
   ⚠️ 不能存节点引用：撤销快照是 JSON.stringify(objs)，带引用会成环、直接抛错。 */
function Rpkey(n){ return n.depth+'|'+n.itemId+'|'+n.recipeId+'|'+n.machineId; }
/* 方案打分（口径与 LawRun 内的一致：连通依赖数 > 堵 > 手动连 > 总线长；
   ⚠️ ⑤-3 起「手动连」权重 = 400，必须压过线长差 —— 见 LawRun 里的口径说明）——抽出来给「重排其余」复用 */
function LawPick(rt){
  const loads=rt.loads||[];
  const ok=loads.filter(x=>x.state!=='none'&&x.state!=='jam').length;
  const manual=rt.warns.filter(w=>w.indexOf('手动连')>=0).length;
  const jam=loads.filter(x=>x.state==='jam').length;
  return {ok:ok, manual:manual, jam:jam, belts:rt.belts.length,
    v:ok*1000 - jam*500 - manual*400 - rt.belts.length};
}
const RW_GAP_X=4, RW_CORR=5, RW_MARGIN=1;
/* ⭐ v99「按层级换行」收尾：层内折行的行间通道（2026-09-22）。
   旧行为：折行行距直接复用层间通道 corr（自适应最高 14）—— 但那是给「跨层走线主干道」
   的高度，层内行与行之间本不需要这么宽。实测（探针）：超限大链（28 炉，80 画布）
   corr 打满 14 时三层折行总高 153 > 79，第一梯队 8 组候选全「放不下」。
   层间 corr 一格不动（走线主通道的高度是 30/分 9 条连不上换来的）。
   v99 行距 = h + rgCap：rgCap 缺省 = corr —— **不爆的工况与旧行为逐格一致**（零回归风险，
   赤铜块@10 / 液化息壤@10 的 wide 扩搜组都靠宽行距拿低手动连，压行距会退化，探针抓过）；
   爆（over）才 -2 递归降级，下限 RW_ROWGAP=3。探针定标：24/28 炉超限链降到 3 后摆下
   （手动连 1~2 条、零堵塞），成功 msg 仍点名超限 —— 「报警不拦截」口径的延伸。 */
const RW_ROWGAP=3;
/* ⭐ 路线图 ③「两档方案 + 按分择优」：紧凑档（间 2 / 通道 3 / 按列对齐）在小产线明显更优，
   但大产线会让汇流器找位退化（实测 copper_jar@30 分数 63→7）。
   所以两档都摆一遍，按「连通段数 > 手动连数 > 总线长」择优 —— 谁分高用谁。 */
const RW_GAP_X_T=2, RW_CORR_T=3;
/* 【一句话】把机器图摆到画布上：按 depth 分层（上游在下、下游在上），
   并做**列对齐**（按下游消费关系排序 x，让走线从"绕"变"直上直下"）。
   opts.fixed = 局部锁定（已固定的机器当障碍）；rowGap 不传时与老行为逐格一致。 */
function LawPlan(res, size, corr, opts){
  opts=opts||{};
  corr=corr||RW_CORR;
  const gapX=opts.gapX||RW_GAP_X;
  const doAlign=opts.align===true;   /* 默认不对齐（旧行为）；紧凑档显式开 */
  /* ⭐ ⑤-1「局部锁定」（2026-09-22）：opts.fixed = 已固定的机器外接框 [{x,y,w,d}]。
     布局时把它们当**障碍物**（不重排、只避让）——新机器撞上就让行往下走。
     只在 down 模式生效（那套 rows 逐行占位天然支持绕障）；
     ⚠️ fixed 为空时**一行都不多跑**，保证老的布局行为逐字节不变（520 条回归靠这个）。 */
  const FX=opts.fixed||[];
  /* v99：折行行间通道 —— 缺省 = corr（旧行为），纵向爆时由函数尾递归降级（见函数尾） */
  const rgCap=(opts.rowGap!==undefined)?opts.rowGap:corr;
  const md={};
  res.machines.forEach(n=>{ (md[n.depth]=md[n.depth]||[]).push(n); });
  const depths=Object.keys(md).map(Number).sort((a,b)=>a-b);
  const objs=[], bands=[];
  let cy=RW_MARGIN, rowH=0, x=RW_MARGIN;
  /* g 缺省 = 层间换行，用层间通道 corr；层内折行显式传 rgCap（行间通道，v99） */
  const newRow=(g)=>{ cy+=rowH+(g===undefined?corr:g); x=RW_MARGIN; rowH=0; };
  /* ⭐ 路线图 ③「按列对齐」（2026-09-21）：逐层排布时，深层机器按「消费它产出的下游机器
     的 x 中心均值」排序 —— 喂同一下游的机器聚到那台机器正下方，走线从"绕"变"直上直下"。
     depth 从小到大 = 从成品到原料，消费者一定先排好。同 itemId 排序键相同 → 天然相邻。 */
  const xCenter={};   /* itemId -> 该组机器的 x 中心 */
  const xStart={};    /* itemId -> 该组机器的 x 起点（down 模式对齐下游用） */
  const cons={};      /* itemId(原料) -> [itemId(下游成品)] 去重 */
  res.machines.forEach(p=>{ (p.children||[]).forEach(c=>{
    if(!c.recipeId) return;
    const arr=(cons[c.itemId]=cons[c.itemId]||[]);
    if(arr.indexOf(p.itemId)<0) arr.push(p.itemId);
  }); });
  const alignKey=n=>{
    const cs=cons[n.itemId];
    if(!cs||!cs.length) return 1e9;
    let sum=0, hit=0;
    cs.forEach(id=>{ if(xCenter[id]!==undefined){ sum+=xCenter[id]; hit++; } });
    return hit?sum/hit:1e9;
  };
  const order={};
  depths.forEach(d=>{
    const y0=cy;
    if(doAlign && d>0) md[d].sort((a,b)=>alignKey(a)-alignKey(b) || (a.machineId<b.machineId?-1:1));
    /* ⭐ 路线图 ③ 二梯队「局部交换」：允许指定层内两台机器互换位置（排序后交换），
       搜索框架用它做「相邻交换」重铺——分数更高就留。 */
    if(opts.swap && opts.swap.depth===d){
      const arr=md[d], si=opts.swap.i, sj=opts.swap.j;
      if(si<arr.length&&sj<arr.length){ const t=arr[si]; arr[si]=arr[sj]; arr[sj]=t; }
    }
    order[d]=md[d].slice();
    /* ⭐⭐ 路线图 ③ 最后一块「层内主动换行」（down 模式，2026-09-22）：
       上游比下游宽时（如 12 台块机 vs 6 台罐机），按「消费它的下游机器」分组，
       组的 x 起点**对齐其下游机器**；与该行已有内容冲突就下沉一行 —— 自动交错分行，
       消灭「右半边机器下方没有下游、只能远程接线」的几何问题。 */
    /* 有固定件时 d=0 层也要走这条（成品层同样得绕开锁定的机器） */
    if(opts.mode==='down' && (d>0 || FX.length)){
      const rows=[];              /* 已占：{y, h, x1, x2}（y..y+h-1 全高，v100：跨组行距错相防重叠） */
      /* ⑤-1：固定件按行铺进 rows —— 后面每台机器落位时自然避开它们 */
      if(FX.length) FX.forEach(r=>{ rows.push({y:r.y, h:r.d, x1:r.x, x2:r.x+r.w}); });
      let maxBottom=cy;
      md[d].forEach(n=>{
        const b=byBp(n.machineId); if(!b) return;
        const fp=Lfp(b), w=fp[0]||1, h=fp[1]||1;
        const dstId=(cons[n.itemId]||[])[0];
        const wantX=(dstId!=null&&xStart[dstId]!=null)?xStart[dstId]:RW_MARGIN;
        /* ⭐③ 收尾「按层级换行」（2026-09-22）：组内机器从 wantX 等距横排，**到右墙折行**
           （回到 wantX、行下移继续摆）—— 旧行为是 break 直接丢机器：赤铜耐压罐@30 实摆 18/30
           台、报告零警告（丢的机器连手动连都不算，产能悄悄不达标）。冲突失败同理换行重试
           （组内基线行下移），4 次仍放不下才放弃该台。 */
        let col=0, baseRow=0, misses=0;
        for(let k2=0;k2<n.machines;k2++){
          let wx=wantX+col*(w+gapX);
          if(wx+w>size-RW_MARGIN){ col=0; baseRow++; wx=wantX; }   /* 折行：回组起点、行下移 */
          let py=null;
          for(let row=baseRow;row<48;row++){
            /* v99：组内行距用 rgCap —— 旧值 h+corr（最高 14）是纵向溢出根因：
               28 台炉折 4 行 × 19 = 76 格，单层就吃掉大半个画布（探针实测）。 */
            const y=cy+row*(h+rgCap);
            let clash=false;
            for(let ri=0;ri<rows.length;ri++){
              const r=rows[ri];
              /* v100：y 向区间相交判定（旧 r.y===y 只查起点行，跨组行距错相时盲区漏判
                 —— 分离芯@70 实锤：炉(h3,行距9)摆 62..64，提纯机(h5,行距11)算出 y=64≠62
                 误判空闲摆下，y=64 行重叠。区间相交 + x 向带 gap = 完备 AABB。 */
              if(y<r.y+r.h && y+h>r.y && !(wx+w+gapX<=r.x1 || wx>=r.x2+gapX)){ clash=true; break; }
            }
            if(!clash){ py=y; rows.push({y:y, h:h, x1:wx, x2:wx+w}); break; }
          }
          if(py===null){ if(++misses>4) continue; col=0; baseRow+=2; k2--; continue; }
          col++;
          objs.push({node:n, b:b, x:wx, y:py, w:w, d:h, k:k2});
          if(py+h>maxBottom) maxBottom=py+h;
        }
        xStart[n.itemId]=wantX;
        /* xCenter 保持旧口径（组起点中心 wantX+w/2）：它喂的是深层的 alignKey 排序，
           每行都锚定 wantX，参考点就是组起点 —— 改均值会改变不折行工况的排序（赤铜块@10 退化实测）。 */
        xCenter[n.itemId]=wantX+w/2;
      });
      bands.push({depth:d, y0:cy, y1:maxBottom});
      cy=maxBottom+corr; rowH=0; x=RW_MARGIN;
      return;
    }
    md[d].forEach(n=>{
      const b=byBp(n.machineId); if(!b) return;
      const fp=Lfp(b), w=fp[0]||1, h=fp[1]||1;
      const x0=x;
      for(let k=0;k<n.machines;k++){
        if(x+w>size-RW_MARGIN) newRow(rgCap);   /* 层内折行：行间走 rgCap，层间换行仍走 corr */
        objs.push({node:n, b:b, x:x, y:cy, w:w, d:h, k:k});
        x+=w+gapX; if(h>rowH) rowH=h;
      }
      xCenter[n.itemId]=(x0+(x-gapX)+w)/2;
      xStart[n.itemId]=x0;
    });
    bands.push({depth:d, y0:y0, y1:cy+rowH});
    newRow();
  });
  const over=objs.filter(o=>o.y+o.d>size-RW_MARGIN);
  /* ⭐ v99 行间降级：折行行距从 min(corr, RW_ROWGAP_HI) 起步（小链走线与旧行为一致），
     纵向爆就 -2 递归降级，下限 RW_ROWGAP。LawPlan 是纯函数，重摆无副作用；
     LawPlan 便宜（毫秒级摆格子），贵的是 RwRoute —— 降级只发生在爆掉的候选上，不白跑。 */
  if(over.length && rgCap>RW_ROWGAP){
    const o2=Object.assign({}, opts, {rowGap: Math.max(RW_ROWGAP, rgCap-2)});
    return LawPlan(res, size, corr, o2);
  }
  return {objs:objs, bands:bands, height:cy, over:over, order:order, rowGap:rgCap};
}
/* ⭐⭐ C6-b 阶段 2（2026-09-25）：把销毁支线（池子/热能池）**捡空位摆到画布上**。
   【为什么单独摆、不并进 LawPlan】
   LawPlan 排的是「产线机器」，它的分层/对齐/折行逻辑都服务于产线几何；
   销毁池与产线**没有物料依赖关系**（旁路溢流），硬塞进分层会打乱产线布局。
   所以：先让 LawPlan 把产线排好，再在**剩余空位**里贴边找地方 —— 产线优先，池子见缝插针。

   【找位策略】从画布**右下角往左上**逐行扫（产线从顶部往下排，底部/右侧通常最空），
   每个建筑要求整块 footprint 全空（避开机器、已铺线、已摆的池子）。
   ⚠️ 找不到位 → 记进 `unplaced`，由调用方决定是否软门禁拒绝（不硬塞、不重叠）。

   返回 {objs:[…], unplaced:[…]}：objs 里每项带 {b, x, y, w, d, sink, kind, forItem}。 */
function RplaceSinks(sinkPlan, size, busyFn, margin){
  const out=[], unplaced=[];
  if(!sinkPlan || !sinkPlan.sinks || !sinkPlan.sinks.length) return {objs:out, unplaced:unplaced};
  const mg=(margin==null)?RW_MARGIN:margin;
  const occ={};   /* 本次已占格（含新摆的池子） */
  const free=(x,y,w,d)=>{
    for(let yy=y;yy<y+d;yy++) for(let xx=x;xx<x+w;xx++){
      if(xx<mg||yy<mg||xx>=size-mg||yy>=size-mg) return false;
      if(busyFn(xx,yy)) return false;
      if(occ[xx+','+yy]) return false;
    }
    return true;
  };
  /* 逐个建筑找位（大件优先，减少碎片） */
  const items=[];
  sinkPlan.sinks.forEach(s=>{ (new Array(s.count)).fill(0).forEach(()=>items.push(s)); });
  items.sort((a,b)=>{ const ba=byBp(a.buildingId), bb=byBp(b.buildingId);
    const fa=ba?Lfp(ba):[1,1], fb=bb?Lfp(bb):[1,1];
    return (fb[0]*fb[1])-(fa[0]*fa[1]); });
  items.forEach(s=>{
    const b=byBp(s.buildingId); if(!b){ unplaced.push({sink:s, why:'建筑表缺 '+s.buildingId}); return; }
    const fp=Lfp(b), w=fp[0]||1, d=fp[1]||1;
    let placed=null;
    /* 从右下角往左上扫（y 从大到小、x 从大到小） */
    for(let y=size-mg-d; y>=mg && !placed; y--){
      for(let x=size-mg-w; x>=mg; x--){
        if(free(x,y,w,d)){ placed={x:x, y:y, w:w, d:d}; break; }
      }
    }
    if(!placed){ unplaced.push({sink:s, why:'画布没有 '+w+'×'+d+' 的整块空位了'}); return; }
    for(let yy=placed.y;yy<placed.y+d;yy++) for(let xx=placed.x;xx<placed.x+w;xx++) occ[xx+','+yy]=1;
    out.push({b:b, x:placed.x, y:placed.y, w:w, d:d, sink:s, kind:s.kind, forItem:s.forItem});
  });
  return {objs:out, unplaced:unplaced};
}
/* ---------- 连线：格内 L 形走线（先竖后横 或 先横后竖），全程避开已有东西 ----------
   起点 = 上游出料口朝外那格（机器上边再上一格）；终点 = 下游进料口朝外那格（机器下边再下一格）。
   只做 1 个拐弯；两条候选路径都撞就记 warn，不硬塞（v1 不做绕线寻优）。 */
function RwRotTo(a,b){ return LrotFrom([a.x,a.y],[b.x,b.y]); }
/* ---------- 汇流器 / 分流器的方向（配置表 rotation.y 解出来的，见 §四）----------
   汇流器 log_converger：3 进（下 / 左 / 右）→ 1 出（上）
   分流器 log_splitter：1 进（下）→ 3 出（上 / 左 / 右）
   画布方向：x 右、y 下 → 「下」= (0,+1)、「上」= (0,-1)、「左」= (-1,0)、「右」= (+1,0)。
   ⚠️ 物料自下而上：上游机器在下面、下游在上面，所以汇流器放在**两者之间的通道里**正好
      「从下面收料、往上面出料」。 */
const RW_MERGE_ID='log_converger', RW_MERGE_FANIN=3;
/* ⚠️ 只有在「能省下足够多条线」时才值得上汇流器：
   每个汇流器要多两段走线（进它、出它），少并几条的话失败点反而变多。
   实测 4 台并成 2 条（省 2 条）不如直接连；12 台并成 6 条（省 6 条）才明显划算。 */
const RW_MERGE_MIN_SAVE=4;
/* 【一句话】布线总控：把摆好的机器连成产线——多点对多点连接、传送带/管道分流，
   内部调 RwFindSplit/RwFindMerge 找分流汇流点、RwPath 算具体路径。
   分支多（8 种介质 × 多源多汇 × 已有线避让），但无深层嵌套；293 行是全项目最长函数。 */
/* ⭐v153 外部接入失败的点名文案（纯 if/else —— 三元嵌套进双层模板里会绊语法检查） */
function RfeedWhyTxt(f){
  if(f.why==='port') return '没有空闲进料管口';
  if(f.why==='edge') return '画布边缘没有空闲格';
  if(f.s) return '走线过不去（接入点 ('+f.s.x+','+f.s.y+') → 端口外侧 ('+f.t.x+','+f.t.y+')）';
  return '走线过不去';
}
/* ⭐v154 外部接入的双模式显示文案（直连 / 暗管对）—— 文案拼装在顶层做，模板里只插值 */
function RfeedModeTxt(f){
  if(f.mode==='udpipe'){
    const org=f.directLen==null?'（直连原本铺不成）':('直连需 '+f.directLen+' 格，');
    return '<b>暗管对</b>：入口 ('+f.entry.x+','+f.entry.y+') ↔ 出口 ('+f.exit.x+','+f.exit.y+') · 出口→机器 '+f.cells+' 格'+(f.saved>0?('（'+org+'省 '+f.saved+' 格）'):('（'+org+'占地持平）'));
  }
  return '接入点 <b>('+f.edge.x+','+f.edge.y+')</b>';
}
function RwRoute(placed, res, size, corr, extraBusy){
  /* 【分节总览】阶段一（连什么）：挑端口 → 定汇流分组 → 预留端点 → 自动摆分流器；
                 阶段二（怎么连）：统一走线（RwPath 寻路 + 桥格）→ 吞吐体检 → stats 落账。
     下方 `==========` 注释即两阶段分界，函数内已有 27 条分节注释，无需再补。 */
  const busy={};      /* 已被占的格：机器 + 已铺的线 + 汇流器 */
  placed.forEach(o=>{ for(let j=0;j<o.d;j++) for(let i=0;i<o.w;i++) busy[(o.x+i)+','+(o.y+j)]=1; });
  /* ⭐ ⑤-1「重排其余」用：把**不归排布器管的散件**（手摆的机器 / 手拉的线）也算障碍，
     新线不会从它们身上压过去。不传就是老行为，一行都不多跑。 */
  if(extraBusy) extraBusy.forEach(o=>{ for(let j=0;j<o.d;j++) for(let i=0;i<o.w;i++) busy[(o.x+i)+','+(o.y+j)]=1; });
  const belts=[], warns=[], links=[];
  const byNode={};
  placed.forEach(o=>{ (byNode[o.node.itemId]=byNode[o.node.itemId]||[]).push(o); });
  const used={};
  const uidOf=o=>o.x+','+o.y;
  const K=(x,y)=>x+','+y;
  const outOf=p=>({x:p.gx+(p.dir==='l'?-1:p.dir==='r'?1:0),
                   y:p.gy+(p.dir==='u'?-1:p.dir==='d'?1:0)});
  const free=pt=>pt.x>=0&&pt.y>=0&&pt.x<size&&pt.y<size&&!busy[K(pt.x,pt.y)];

  const deps=[];
  res.machines.forEach(parent=>{ (parent.children||[]).forEach(child=>{
    if(child.recipeId) deps.push([parent,child]);
  }); });
  deps.sort((a,b)=>(RwFluid(b[1].phase)?1:0)-(RwFluid(a[1].phase)?1:0));
  /* 记账：每对依赖实际铺成了几条成品线（阶段二里累加）—— 用来判「堵不堵」。
     key 是树上的 child 节点对象，必须用 Map（普通对象会把对象键压成 '[object Object]'）。 */
  const linked=new Map();
  /* ⭐ ⑤-2（2026-09-22）：汇流/分流器的**实际摆放数**与**被丢掉的线数**。
     以前分流器只摆一个、第 4 台下游起既不接线也不报告（静默丢）—— 现在两个分支都逐条点数，
     `dropN` 不为零就必须在报告里点名，测试也守着这条。 */
  let spN=0, mgN=0, dropN=0;

  /* ========== 阶段一：连什么 —— 挑端口 / 定汇流分组 / 预留端点 ========== */
  const reserved={};
  const jobs=[];          /* 段：{s,t,isP,parent,child}` */
  deps.forEach(pair=>{
    const parent=pair[0], child=pair[1];
    const ps=placed.filter(o=>o.node===parent);
    if(!ps.length) return;
    const cs=byNode[child.itemId]||[];
    if(!cs.length) return;
    const isP=RwFluid(child.phase);
    const N=cs.length, M=ps.length;
    const cntPorts=(b,kind)=>((b.ports||[]).filter(p=>p.kind===kind&&(!!p.isPipe)===isP).length);
    const outCap=cntPorts(cs[0].b,'output'), inCap=cntPorts(ps[0].b,'input');
    /* 载具上限：一条线最多扛多少 → 干线数 T = max(下游台数, 总流量/上限)
       —— 下游每台至少要有一条自己的线，所以 T 不能小于 M。 */
    const cap=isP?RW_PIPE:RW_BELT;
    /* 这条依赖「至少要几条并行线」—— 由载具上限决定（传送带 30/分、管道 120/分）。
       ⚠️ 2026-09-21 补（路线图 ②a）：以前这里只算出来**提醒一句**，线还是只连一条
       → 高产能段实际会堵。现在 np 直接抬到 linesNeed，**真并联**铺出来。 */
    const linesNeed=RwLines(child.demand, isP);
    /* ⚠️ 这两个数**必须声明在块外**：下面的 `else if(outNeed>…)` 要用。
       曾经写成 `if(!useMerge){ const outNeed=…; }` —— 测试全绿（沙箱把 const 换成 var 掩盖了块级作用域），
       真机一跑 LawRun 就 `outNeed is not defined`，**整个排布器点不动**（2026-09-22 真机复现）。
       现在测试里加了「原始代码（const/let 版）冒烟」这道门禁守着。 */
    const outNeed=Math.ceil(M/N), inNeed=Math.ceil(N/M);
    const T0=Math.max(M, linesNeed, Math.ceil(child.demand/(cap||1)));
    /* ⭐⭐ ⑤-3（2026-09-22）汇流器判定两处修正（都是实测踩出来的）：
       ① **fanin = 3**：把 N 条并成 T 条要求 T ≥ ceil(N/3)。原来 T 只按「下游台数 / 载具上限」算 ——
          于是「8 台上游、2 台下游、需求只要 2 条线」时 T=2 < ceil(8/3)=3 → 判"并不了" → 直接连 8 条，
          而下游 2 台加起来只有 6 个管口 → **4 条线根本插不进**，只能手动连（实测 液化息壤@10）。
          现在只要并线，就把 T 抬到 ceil(N/3)（多出的干线无害：下游多接一条而已），并用 M×inCap 兜上限。
       ② **下游口不够时，并线不是"划不划算"而是"必须"**：inNeed > inCap 说明不并就插不进，
          这时即便只省 1 条也要并（原来死守 RW_MERGE_MIN_SAVE = 4，判"不值当" → 直接连 → 一半的线连不上）。 */
    const mustMerge=(inNeed>inCap);
    /* ⚠️ T 的抬升**只在"必须并"时才做**：可选并线时把 T 硬抬到 ceil(N/3) 会让本来不必并的链去并，
       实测「实验铜骨骼@10」（inNeed 4 ≤ inCap 6，并线只是"省 6 条"）因此从全连通倒退成 2 条手动连。
       可选场景仍守老口径（T0 本身要够分出 ceil(N/3) 组才值得并）。 */
    const Tmerge=mustMerge?Math.max(T0, Math.ceil(N/RW_MERGE_FANIN)):T0;
    const mergeSaves=N-Tmerge;
    const canMerge=(N>Tmerge && mergeSaves>0
      && (mustMerge || (mergeSaves>=RW_MERGE_MIN_SAVE && T0>=Math.ceil(N/RW_MERGE_FANIN)))
      && Tmerge<=M*Math.max(1,inCap));
    const useMerge=canMerge;
    const T=useMerge?Tmerge:T0;
    const np=useMerge?Math.max(T,linesNeed):Math.max(N,M,linesNeed);
    if(N>1||M>1) warns.push(parent.name+' ← '+child.name+'：上游 '+N+' 台 / 下游 '+M+' 台，'
      +(useMerge?('用 '+(N-T)+' 个汇流器并成 '+T+' 条干线'):('直接连 '+np+' 条')));
    if(!useMerge){
      /* ⚠️ 口径（⑤-2 修正）：分流器 1 进 3 出 —— 要喂 outNeed 台下游，需要的是 **ceil(outNeed/3) 个分流器**
         （每个只占上游 1 个出料口），不是「缺几个出料口」。原来按 outNeed-outCap 报，实测量级也不对。 */
      if(outNeed>outCap) warns.push(parent.name+' ← '+child.name+'：上游每台要 '+outNeed+' 个'+(isP?'管道':'传送带')+'出料口，但只有 '+outCap+' 个 → 需要 '+Math.ceil(outNeed/3)+' 个**分流器**（1 进 3 出，每个占上游 1 个出料口）');
      if(inNeed>inCap) warns.push(parent.name+' ← '+child.name+'：下游每台要 '+inNeed+' 个'+(isP?'管道':'传送带')+'进料口，但只有 '+inCap+' 个 → 需要 '+(inNeed-inCap)+' 个**汇流器**');
    }
    const portCands=(o,kind)=>{
      const b=o.b, fp=Lfp(b), out=[];
      (b.ports||[]).filter(p=>p.kind===kind && (!!p.isPipe)===isP).forEach(p=>{
        const q=LportXY(p,o.rot,fp[0],fp[1]);
        if(q.x<0||q.x>=o.w||q.z<0||q.z>=o.d) return;
        const key=uidOf(o)+kind+p.index+(isP?'P':'B');
        if(used[key]) return;
        out.push({key:key, gx:o.x+q.x, gy:o.y+q.z, dir:LportDirRot(p,o.rot,fp[0],fp[1])});   /* ⭐v122：朝向跟 rot 转（原来贴边猜，旋转机器后布线全歪） */
      });
      return out;
    };
    /* 下游每台机器挑进料口：**按需要挑够几个**（inNeed = 上游台数/下游台数）。
       ⚠️ 只挑一个的话，多条线会挤同一个口 —— 第 2 条就撞上"端点已预留"而失败（实测 4 条只连 2 条）。
       ⚠️ 2026-09-21 补：真并联后线数可能**多于台数**（np > N），进料口也要按 np 分摊。 */
    const inNeedN=Math.ceil(Math.max(N,np)/M);
    const dstPick=ps.map(o=>{
      const ics=portCands(o,'input').filter(c=>{
        const t=outOf(c); return !busy[K(t.x,t.y)] && !reserved[K(t.x,t.y)];
      });
      return ics.slice(0, inNeedN).map(c=>{ used[c.key]=1; return {o:o, p:c}; });
    });
    if(useMerge){
      /* 把 N 台上游分成 T 组（每组 ≤3，好用一个汇流器并掉），第 g 组喂 dstPick[g%M] */
      /* ⭐ 路线图 ③「就近分组」（2026-09-21）：上游机器与下游汇流点都按 x 排序后，
         组 g 取离第 g 个汇流点最近的 sz 台 —— 消灭"右半边机器横跨 20 格去够左边汇流器"的长干线
         （实测 copper_jar@30 的 6 条失败干线全部来自树序切组的远组）。 */
      /* cs 的元素就是 placed 实体（自带 x/w），直接取中心 —— 别再反查 node */
      const csX=o=>o.x+o.w/2;
      const csSorted=cs.slice().sort((a,b)=>csX(a)-csX(b));
      const dstOrder=ps.slice().sort((a,b)=>(a.x+a.w/2)-(b.x+b.w/2));
      const taken=new Array(csSorted.length).fill(false);
      const base=Math.floor(N/T), rem=N%T, groups=[];
      for(let g=0;g<T;g++){
        const sz=base+(g<rem?1:0);
        const dO=dstOrder[g%dstOrder.length];
        const dx0=dO?(dO.x+dO.w/2):0;
        const idx=csSorted.map((n,i)=>i).filter(i=>!taken[i])
          .sort((a,b)=>Math.abs(csX(csSorted[a])-dx0)-Math.abs(csX(csSorted[b])-dx0))
          .slice(0,sz);
        idx.forEach(i=>taken[i]=true);
        groups.push(idx.map(i=>csSorted[i]));
      }
      groups.forEach((grp,g)=>{
        const dst=dstPick[g%M]&&dstPick[g%M][0];
        if(!dst){ warns.push(parent.name+' ← '+child.name+'：下游进料口都占着，第 '+(g+1)+' 组请手动连'); return; }
        const tPt=outOf(dst.p);
        if(grp.length<2){
          /* 单台一组：直接连 */
          const src=grp[0], ocs=portCands(src,'output');
          const pick=ocs.filter(c=>free(outOf(c)))[0];
          if(!pick){ warns.push(parent.name+' ← '+child.name+'：端口/端点被占了，请手动连'); return; }
          used[pick.key]=1;
          reserved[K(outOf(pick).x,outOf(pick).y)]=1; reserved[K(tPt.x,tPt.y)]=1;
          jobs.push({s:outOf(pick), t:tPt, isP:isP, parent:parent, child:child, tInto:{x:dst.p.gx, y:dst.p.gy}});
          return;
        }
        /* 多台一组：在「下游机器正下方的通道」里找个空位放汇流器 */
        const cell=RwFindMerge(size, dst.o, grp.length, busy, corr);
        if(!cell){ warns.push(parent.name+' ← '+child.name+'：通道里放不下汇流器，这 '+(grp.length)+' 台请手动并线'); 
          /* 退化：直接连（能连几条算几条） */
          grp.forEach(src=>{
            const ocs=portCands(src,'output'), pick=ocs.filter(c=>free(outOf(c)))[0];
            if(!pick||!free(tPt)) return;
            used[pick.key]=1; reserved[K(outOf(pick).x,outOf(pick).y)]=1; reserved[K(tPt.x,tPt.y)]=1;
            jobs.push({s:outOf(pick), t:tPt, isP:isP, parent:parent, child:child, tInto:{x:dst.p.gx, y:dst.p.gy}});
          });
          return;
        }
        busy[K(cell.x,cell.y)]=1;
        belts.push({x:cell.x, y:cell.y, rot:0, isPipe:isP, logiId:RW_MERGE_ID, merge:true});
        mgN++;
        const ins=[{x:cell.x,y:cell.y+1},{x:cell.x-1,y:cell.y},{x:cell.x+1,y:cell.y}];
        const outs={x:cell.x, y:cell.y-1};
        reserved[K(outs.x,outs.y)]=1;
        const d0=dropN;
        grp.forEach((src,gi)=>{
          const ip=ins[gi%ins.length];
          if(busy[K(ip.x,ip.y)]||reserved[K(ip.x,ip.y)]){ dropN++; return; }   /* ⑤-2：不再静默丢 */
          const ocs=portCands(src,'output'), pick=ocs.filter(c=>free(outOf(c)))[0];
          if(!pick){ dropN++; return; }
          used[pick.key]=1;
          reserved[K(outOf(pick).x,outOf(pick).y)]=1; reserved[K(ip.x,ip.y)]=1;
          jobs.push({s:outOf(pick), t:ip, isP:isP, parent:parent, child:child, intoMerge:true, tInto:cell});
        });
        reserved[K(tPt.x,tPt.y)]=1;
        jobs.push({s:outs, t:tPt, isP:isP, parent:parent, child:child, fromMerge:true, mergeCell:cell, tInto:{x:dst.p.gx, y:dst.p.gy}});
        if(dropN-d0) warns.push(parent.name+' ← '+child.name+'：有 '+(dropN-d0)+' 台上游并进汇流器的线没连上（端口/通道被占），请手动连');
      });
    }else if(outNeed>outCap && M>N){
      /* ---------- 自动摆分流器（2026-09-21 补 · ⑤-2 扩容 2026-09-22）----------
         用在「上游出料口不够、一台要喂多台下游」：把一台上游的线经**分流器（1 进 3 出）**分给下游。
         摆放与汇流器对称：**汇流器在下游机器下方收料，分流器在上游机器上方放料**。
         ⚠️ ⑤-2 实测抓到的坑：一台分流器只有 **3 个出料格**（上/左/右），旧版**只摆一个** ——
            第 4 台下游起既不接线、也不进 warn（**静默丢**）。实测「工业爆炸物@5」1 台粉碎机要喂 5 台下游，
            只连上 3 台，而报告里写着「手动连 0 条」，看着像全连上了。
         现在：**每 3 台下游摆一个分流器**（并列，每个各从上游的一个空闲出料口取料，1 台机器有 3 个出料口
            就够喂 3 组）；摆不下 / 出料口不够 → `dropN` 计数并**逐条点名**，绝不静默丢。 */
      const FT=3;                       /* 分流器 1 进 3 出 */
      const dS=dropN;                   /* 本对依赖里被丢掉的线数（出口按增量报） */
      warns.push(parent.name+' ← '+child.name+'：上游每台只有 '+outCap+' 个'+(isP?'管道':'传送带')
        +'出料口，但要喂 '+outNeed+' 台下游 → 自动摆**分流器**（⚠️ 1 进 3 出是 round-robin 轮询均分，不是按需分配——下游速率差异大时实际吞吐受轮询节奏约束）');
      cs.forEach((src,si)=>{
        const targets=[];
        for(let k=0;k<outNeed;k++){
          const arr=dstPick[(si*outNeed+k)%M];
          if(arr&&arr[0]&&targets.indexOf(arr[0])<0) targets.push(arr[0]);
        }
        if(!targets.length) return;
        if(targets.length===1){
          const ocs=portCands(src,'output'), pick=ocs.filter(c=>free(outOf(c)))[0];
          if(!pick){ dropN++; return; }
          used[pick.key]=1;
          reserved[K(outOf(pick).x,outOf(pick).y)]=1;
          reserved[K(outOf(targets[0].p).x,outOf(targets[0].p).y)]=1;
          jobs.push({s:outOf(pick), t:outOf(targets[0].p), isP:isP, parent:parent, child:child, tInto:{x:targets[0].p.gx, y:targets[0].p.gy}});
          return;
        }
        /* 每 3 台下游一个分流器 —— 一个不够就并排摆第二个 */
        for(let g=0; g<targets.length; g+=FT){
          const grp=targets.slice(g,g+FT);
          const cell=RwFindSplit(size, src, busy, corr);
          if(!cell){ dropN+=grp.length; continue; }
          const inCell={x:cell.x, y:cell.y+1};
          if(busy[K(inCell.x,inCell.y)]||reserved[K(inCell.x,inCell.y)]){ dropN+=grp.length; continue; }
          /* 先挑上游出料口：挑不到就别留一个孤零零的分流器 */
          const ocs=portCands(src,'output'), pick=ocs.filter(c=>free(outOf(c)))[0];
          if(!pick){ dropN+=grp.length; continue; }
          busy[K(cell.x,cell.y)]=1;
          belts.push({x:cell.x, y:cell.y, rot:0, isPipe:isP, logiId:'log_splitter', split:true});
          spN++;
          const outCells=[{x:cell.x,y:cell.y-1},{x:cell.x-1,y:cell.y},{x:cell.x+1,y:cell.y}];
          used[pick.key]=1; reserved[K(outOf(pick).x,outOf(pick).y)]=1; reserved[K(inCell.x,inCell.y)]=1;
          jobs.push({s:outOf(pick), t:inCell, isP:isP, parent:parent, child:child, intoSplit:true, tInto:cell});
          grp.forEach((d,ti)=>{
            const oc=outCells[ti%outCells.length];
            if(busy[K(oc.x,oc.y)]||reserved[K(oc.x,oc.y)]){ dropN++; return; }
            reserved[K(oc.x,oc.y)]=1; reserved[K(outOf(d.p).x,outOf(d.p).y)]=1;
            jobs.push({s:oc, t:outOf(d.p), isP:isP, parent:parent, child:child, fromSplit:true, tInto:{x:d.p.gx, y:d.p.gy}});
          });
        }
      });
      if(dropN-dS) warns.push(parent.name+' ← '+child.name+'：**还有 '+(dropN-dS)+' 台下游没连上**'
        +'（分流器摆不下 / 上游出料口不够）—— 请手动连，或把上游机器多做几台');
    }else{
      for(let i=0;i<np;i++){
        const dst=dstPick[i%M] && dstPick[i%M][Math.floor(i/M)%dstPick[i%M].length];
        if(!dst){ warns.push(parent.name+' ← '+child.name+'：第 '+(i+1)+' 条的下游进料口占着，请手动连'); continue; }
        const src=cs[i%N], ocs=portCands(src,'output');
        const pick=ocs.filter(c=>free(outOf(c)))[0];
        if(!pick){ warns.push(parent.name+' ← '+child.name+'：第 '+(i+1)+' 条的端口/端点被占了，请手动连'); continue; }
        used[pick.key]=1;
        reserved[K(outOf(pick).x,outOf(pick).y)]=1; reserved[K(outOf(dst.p).x,outOf(dst.p).y)]=1;
        jobs.push({s:outOf(pick), t:outOf(dst.p), isP:isP, parent:parent, child:child, tInto:{x:dst.p.gx, y:dst.p.gy}});
      }
    }
  });

  /* ⭐v151 外部流体接入口（博士 2026-09-24 定稿）—————————————————————————————————
     背景：野外的液体/气体原料（清水、气体、溶液…）在 `Rexplode` 里被标成 `external`（machines=0），
     原来画布上**不摆也不连** —— 报告只写一句「建议外部供应」，产线在画布上是**断的**。
     博士的实际用法：他用**暗管**把野外流体拉到**画布旁边**（画布外，不在画布内），
     所以排布器只要**在画布边缘占一格当接入点**，从那一格铺管道接到用料机器的进料管口。
     → 报告给出接入点坐标，博士照着把暗管出口贴在画布外面那一格的外侧。
     ⚠️ **画布外那段归博士，排布器一概不管**（也管不了：库里没有矿点逐点坐标）。
     ⚠️ 没有 external 流体时**一行都不多跑** —— 老行为逐字节不变（回归锁靠这个）。
     ⚠️ 放在阶段一之后、阶段二之前：这样能直接复用 `used`（端口占用）/`reserved`（端点格）/
        `busy`（已占格）三张表，不必另起一套状态。 */
  const feeds=[];
  const feedFail=[];                    /* 没铺出来的外部接入（不静默丢：报告与回归测试都点名）。
                                           ⚠️ 口径与「手动连」分开：那是内部产线连通率的回归口径
                                           （⑤-3），外部接入是 v151 新增功能，各自盯各自的。 */
  const feedUsed={};                    /* 已分配的接入点（主选格），避免两条线抢同一格；
                                           备选格不占名 —— 走线阶段谁先铺谁得，重试时按 busy/feedUsed 现查 */
  /* 画布四条边全部格子，按「离 (cx,cy) 的曼哈顿距离」从近到远 —— 外部接入点从这里挑 */
  const edgePick=(cx,cy)=>{
    const es=[];
    for(let x0=0;x0<size;x0++){ es.push({x:x0, y:0}); es.push({x:x0, y:size-1}); }
    for(let y0=1;y0<size-1;y0++){ es.push({x:0, y:y0}); es.push({x:size-1, y:y0}); }
    es.sort((a1,b1)=>(Math.abs(a1.x-cx)+Math.abs(a1.y-cy))-(Math.abs(b1.x-cx)+Math.abs(b1.y-cy)));
    return es;
  };
  if((res.externals||[]).length){
    res.externals.forEach(iid=>{
      if((byNode[iid]||[]).length) return;                 /* 画布上有人自己产它 → 不需要外部接入 */
      if(!RwFluid(RwPhaseOf(iid))) return;                 /* 只处理流体：固体走无线，不需要管子 */
      const users=[];                                      /* 谁在用它（external 节点挂在机器的 children 上） */
      res.machines.forEach(m=>{
        (m.children||[]).forEach(c=>{ if(!c.recipeId && c.itemId===iid) users.push({m:m, d:c.demand}); });
      });
      if(!users.length) return;
      /* ⭐每台消费机器各拉**一条**边缘进管 —— 博士 2026-09-24 截图实锤：他实际玩法就是拉很多根
         水管分别供给多台设备（上一版把「画个管道」误读成「一个流体只接一条」，已纠正）。
         拥塞对策（曾经 8 池 × 2 流体 = 16 条管子堵掉 4 条的教训，靠下面三条解决而不是靠砍线）：
         ① 接入点候选 = **整条四边**按「离这台机器的距离」排序 —— 只取中心 ±4 时 16 根管子
            会把格子抢光，被迫退到对面边 → 横穿画布的长线必堵；
         ② 同一流体的多台机器按「离边缘距离」从近到远分配，紧挨的机器自然拿到相邻格、沿边排开；
         ③ 走线失败时换备选接入点重试（走线循环里的 edgeAlts），不急着报「请手动连」。 */
      const edgeDistOf=e=>{
        const os=placed.filter(o=>o.node===e.m);
        return os.length ? Math.min.apply(null, os.map(o=>
          Math.min(o.x, o.y, size-1-(o.x+o.w-1), size-1-(o.y+o.d-1)))) : 1e9;
      };
      users.sort((a1,b1)=>edgeDistOf(a1)-edgeDistOf(b1));
      users.forEach(u=>{
        const m=u.m;
        const insts=placed.filter(o=>o.node===m);
        /* 单台需求 = 节点总需求 ÷ 实体数 —— 每根管子只背自己那台机器的量，报告不虚报 */
        const dI=insts.length>1 ? Math.round(u.d/insts.length*100)/100 : u.d;
        insts.forEach(o=>{
          /* ① 这台机器**空闲的进料管口**（口径与阶段一 portCands 一致：kind=input + isPipe） */
          const b=o.b, fp=Lfp(b), cands=[];
          (b.ports||[]).filter(p=>p.kind==='input' && p.isPipe).forEach(p=>{
            const q=LportXY(p,o.rot,fp[0],fp[1]);
            if(q.x<0||q.x>=o.w||q.z<0||q.z>=o.d) return;
            const key=uidOf(o)+'input'+p.index+'P';
            if(used[key]) return;
            /* ⚠️ **dir 必须带上**（与阶段一 portCands 逐字段对齐）：`outOf()` 靠 `p.dir` 算
               「端口外侧那一格」；漏掉它 dir=undefined → 偏移量算成 0 → 外侧格退化成**端口自身格**，
               而那一格恒是机器本体 → busy 恒真 → 该机器所有进料口统统判「无空闲」。
               v151 实测踩过：8 台反应池 × 2 个外部流体 = 16 条全假失败，报「没有空闲进料管口」。 */
            const c={key:key, gx:o.x+q.x, gy:o.y+q.z, dir:LportDirRot(p,o.rot,fp[0],fp[1])};
            const tp=outOf(c);
            if(tp.x<0||tp.y<0||tp.x>=size||tp.y>=size) return;
            if(busy[K(tp.x,tp.y)]||reserved[K(tp.x,tp.y)]) return;
            cands.push(c);
          });
          const pick=cands[0];
          if(!pick){
            feedFail.push({item:RwItemName(iid), to:m.machineName, why:'port'});
            warns.push('外部接入：'+m.machineName+'（'+RwItemName(iid)+'）没有空闲进料管口，画布内这一段请自己补管'); return;
          }
          /* ② 接入点 = 画布四条边里离这台机器最近、且空闲的一格（管道最短）。
             ⭐ 候选 = **整条四边**按曼哈顿距离排序，不是只取中心 ±4 —— 16 根管子会把 ±4 的
                格子抢光，后面被迫退到对面边 → 横穿画布的长线必堵（v151 实测教训）。
                同一台机器的多个流体、紧挨着的多台机器，按排序天然拿到相邻格、沿边排开。
             ⭐ 另留 eAlts（接下来的几个空闲格）给走线失败时换格重试 —— 重试发生在走线阶段
                （那时内部线路已铺完，哪个格子真空闲才见分晓）。 */
          const cx=Math.max(0,Math.min(size-1,Math.round(o.x+o.w/2)));
          const cy=Math.max(0,Math.min(size-1,Math.round(o.y+o.d/2)));
          const freeE=edgePick(cx,cy).filter(e=>!busy[K(e.x,e.y)]&&!feedUsed[K(e.x,e.y)]&&!reserved[K(e.x,e.y)]);
          if(!freeE.length){
            feedFail.push({item:RwItemName(iid), to:m.machineName, why:'edge'});
            warns.push('外部接入：'+m.machineName+' 找不到空闲的画布边缘格，'+RwItemName(iid)+' 画布内这一段请自己补管'); return;
          }
          const s=freeE[0], eAlts=freeE.slice(1,25);
          used[pick.key]=1; feedUsed[K(s.x,s.y)]=1;
          /* ⚠️ 端口外侧格**不进 reserved**：提前预留会挤压内部走线的路径空间 —— 实测把
             赤铜块@10 的「手动连」从 ≤2 顶到 3（16 个预留格正好压在池子旁边的通道上）。
             feed 线本来就排到最后铺，届时外侧格若真被内部线占了，走线循环里会
             **换端口重试**（portAlts），比提前占坑更稳。 */
          const t=outOf(pick);
          /* ⚠️ 方向必须对齐走线循环的口径（links 语义 = **from 供给方 → to 消费方**）：
             **parent = 消费它的那台机器**、**child = 画布外的暗管（虚拟供给方）**。
             反着写报告里会显示成「机器 → 画布外」，方向颠倒（踩过一次）。 */
          /* feeds 只收**铺成功的**条目：先造引用挂到 job 上，走线铺成后才入 feeds ——
             失败的进 feedFail（不静默丢），报告层不用再过滤 */
          const feedRef={item:RwItemName(iid), itemId:iid, machine:m.name, machineName:m.machineName,
            edge:{x:s.x, y:s.y}, need:dI};
          jobs.push({s:s, t:t, isP:true, feed:true, edge:{x:s.x,y:s.y},
            tInto:{x:pick.gx, y:pick.gy},
            edgeAlts:eAlts, feedRef:feedRef, mc:{x:cx, y:cy},
            portAlts:cands.slice(1,5),
            parent:m,
            child:{name:RwItemName(iid), demand:dI, machineName:'画布外（暗管接入）', itemId:iid}});
        });
      });
    });
  }

  /* ========== 阶段二：统一走线（不许穿过别人的端点格） ==========
     ⭐ 路线图 ③「由短到长铺」：短段先占近路，长段后铺绕远 —— 总线长更短。 */
  jobs.sort((a2,b2)=>((a2.feed?1:0)-(b2.feed?1:0))               /* ⭐v151 外部接入**最后铺** ——
      必须让内部连线先占路：feed 线若参与正常排序会挤掉既有路径，实测把「P3 准入口限速」那条回归锁
      直接顶红（路径变了 → 准入口不再落在原路径上）。排在最后 = 老产线走线逐字节不变。 */
                    ||((a2.isP?0:1)-(b2.isP?0:1))                 /* 流体（管道）优先：被带子截断就没路可绕 */
                    ||((Math.abs(a2.s.x-a2.t.x)+Math.abs(a2.s.y-a2.t.y))
                      -(Math.abs(b2.s.x-b2.t.x)+Math.abs(b2.s.y-b2.t.y))));
  const axis={};   /* 已铺线格的轴向（'h' 横 / 'v' 竖）—— 桥接穿越的判定依据 */
  const cellMed={};/* ⭐v152 已铺线格的介质（true=管）—— 管×带交叉不放假桥的判定依据（博士 2026-09-24 游戏实锤：3D 里管在上层、带在下层，交叉天然合法无需桥；只有同介质交叉才要桥） */
  /* ⭐v154 暗管入口/出口对（博士 2026-09-25 实机规则：一对一定向绑定、同建筑同物料、
     可旋转、地下虚拟管流速同普通管道）：直连 ≥12 格或直连失败时评估「入口 3×3 贴画布边
     （input 口朝画布外）+ 出口 3×3 近机器（output 口外侧格起地面短管）」——
     占地(18格)+短管 < 直连管格 才采用；短 feed 不评估（直连行为零变化）。 */
  const udBldgs=[];      /* 摆下的入口/出口建筑（LawRun 落盘成 objs，planRole='udpipe'） */
  let udPairN=0;         /* 配对编号（tooltip/报告用） */
  const udFootFree=(ox,oy,w,d)=>{ for(let yy=oy;yy<oy+d;yy++) for(let xx=ox;xx<ox+w;xx++){
      if(xx<0||yy<0||xx>=size||yy>=size) return false;
      if(busy[K(xx,yy)]||reserved[K(xx,yy)]) return false; } return true; };
  /* 出口找位：围绕机器端口外侧格 t 逐环找 3×3 空位 + 朝向，output 口外侧格 s2 → RwPath(s2,t) 最短者。
     只在引号外的括号计数——RwPath 调用有上限（4 朝向 × 5 环 × 每环第一个合格格），不会拖慢铺线。 */
  const udExitFor=(t, block)=>{
    const ub=byBp('udpipe_unloader_1'); if(!ub) return null;
    const fp=Lfp(ub), op=(ub.ports||[]).filter(p=>p.kind==='output')[0];
    if(!op) return null;
    let best=null;
    for(let rot=0;rot<360;rot+=90){
      const dm=Ldims(ub,rot);
      const q=LportXY(op,rot,fp[0],fp[1]);
      const dir=LportDirRot(op,rot,fp[0],fp[1]);
      const dx=dir==='l'?-1:dir==='r'?1:0, dy=dir==='u'?-1:dir==='d'?1:0;
      for(let r=0;r<=5;r++){
        for(let ddx=-r;ddx<=r;ddx++){
          for(let ddy=-r;ddy<=r;ddy++){
            if(Math.max(Math.abs(ddx),Math.abs(ddy))!==r) continue;
            const s2={x:t.x+ddx, y:t.y+ddy};
            if(s2.x<0||s2.y<0||s2.x>=size||s2.y>=size) continue;
            if(busy[K(s2.x,s2.y)]||reserved[K(s2.x,s2.y)]) continue;
            const ox=s2.x-q.x-dx, oy=s2.y-q.z-dy;
            if(!udFootFree(ox,oy,dm.w,dm.d)) continue;
            const manh=Math.abs(ddx)+Math.abs(ddy);
            if(best && manh>=best.manh) continue;          /* 曼哈顿是路径长下界，不可能更短 */
            const sp=RwPath(s2, t, busy, size, block, axis);
            if(!sp) continue;
            best={sp:sp, s2:s2, rot:rot, ox:ox, oy:oy, manh:manh};
          }
        }
        if(best) break;                                    /* 近环有解就不再扩环（朝向间用 manh 剪枝，不提前 break） */
      }
    }
    return best;
  };
  /* 入口找位：input 口朝画布外（外侧格出界），贴边滑动取离出口最近者 */
  const udEntryFor=(uPos, block)=>{
    const lb=byBp('udpipe_loader_1'); if(!lb) return null;
    const fp=Lfp(lb), ip=(lb.ports||[]).filter(p=>p.kind==='input')[0];
    if(!ip) return null;
    let best=null;
    for(let rot=0;rot<360;rot+=90){
      const dm=Ldims(lb,rot);
      const q=LportXY(ip,rot,fp[0],fp[1]);
      const dir=LportDirRot(ip,rot,fp[0],fp[1]);
      const dx=dir==='l'?-1:dir==='r'?1:0, dy=dir==='u'?-1:dir==='d'?1:0;
      for(let slide=0; slide<size; slide++){
        const ox=dir==='l'?-q.x:(dir==='r'?size-1-q.x:slide);
        const oy=dir==='u'?-q.z:(dir==='d'?size-1-q.z:slide);
        const px=ox+q.x+dx, py=oy+q.z+dy;
        if(px>=0&&px<size&&py>=0&&py<size) continue;       /* 口没朝界外，这个朝向不对 */
        if(ox<0||oy<0||ox+dm.w>size||oy+dm.d>size) continue;
        if(!udFootFree(ox,oy,dm.w,dm.d)) continue;
        const dist=Math.abs(ox-uPos.x)+Math.abs(oy-uPos.y);
        if(!best || dist<best.dist) best={x:ox, y:oy, rot:rot, dist:dist};
      }
    }
    return best;
  };
  /* 单根 feed 的暗管对评估：成功返回 {loader, unloader, shortPath, shortLen, saved, foot}，失败 null */
  const udTryPair=(j, path, block)=>{
    const directLen=path?path.length:1e9;
    const t=j.t;
    const ex=udExitFor(t, block);
    if(!ex) return null;
    const en=udEntryFor({x:ex.ox, y:ex.oy}, block);
    if(!en) return null;
    const foot=18;                                          /* 两座 3×3 = 18 格 */
    if(foot+ex.sp.length>=directLen) return null;           /* 不比直连省，不折腾 */
    return {loader:{id:'udpipe_loader_1', x:en.x, y:en.y, rot:en.rot},
            unloader:{id:'udpipe_unloader_1', x:ex.ox, y:ex.oy, rot:ex.rot},
            shortPath:ex.sp, shortLen:ex.sp.length,
            directLen:directLen>=1e9?null:directLen,
            saved:(directLen>=1e9?null:directLen-foot-ex.sp.length), foot:foot};
  };
  jobs.forEach(j=>{
    let s=j.s; let t=j.t;
    const mine=k=>k===K(s.x,s.y)||k===K(t.x,t.y);
    const block=(x,y)=>!!reserved[K(x,y)]&&!mine(K(x,y));
    let path=RwPath(s, t, busy, size, block, axis);
    if(!path && j.feed && j.edgeAlts && j.edgeAlts.length){
      /* ⭐v151 外部接入的换格重试：feed 线排到最后铺，此时内部线已定形 —— 首选接入点走不通
         就挨个试备选格（挑格时已按距离排好序），全部失败才往下走。 */
      for(let ai=0; ai<j.edgeAlts.length && !path; ai++){
        const a2=j.edgeAlts[ai], ak=K(a2.x,a2.y);
        if(busy[ak]||reserved[ak]||(feedUsed[ak]&&ak!==K(s.x,s.y))) continue;
        const p2=RwPath(a2, t, busy, size, block, axis);
        if(p2){ path=p2; s=a2; if(j.feedRef) j.feedRef.edge={x:a2.x, y:a2.y}; }
      }
    }
    if(!path && j.feed && j.portAlts && j.portAlts.length){
      /* ⭐换端口重试：首选口的「外侧格」被内部线占了 —— RwPath 对终点占用是硬失败（ok(t)），
         换接入点救不了，只能换一个外侧格还空着的进料口，并在机器旁就近重挑接入点。 */
      for(const pa of j.portAlts){
        if(used[pa.key]) continue;
        const tk=outOf(pa);
        if(tk.x<0||tk.y<0||tk.x>=size||tk.y>=size) continue;
        if(busy[K(tk.x,tk.y)]||reserved[K(tk.x,tk.y)]) continue;
        const es=edgePick(j.mc.x, j.mc.y).filter(e=>!busy[K(e.x,e.y)]&&!feedUsed[K(e.x,e.y)]&&!reserved[K(e.x,e.y)]);
        for(const ss of es.slice(0,8)){
          const mine3=k=>k===K(ss.x,ss.y)||k===K(tk.x,tk.y);
          const block3=(x,y)=>!!reserved[K(x,y)]&&!mine3(K(x,y));
          const p3=RwPath(ss, tk, busy, size, block3, axis);
          if(p3){ used[pa.key]=1; feedUsed[K(ss.x,ss.y)]=1; path=p3; s=ss; t=tk; j.tInto={x:pa.gx, y:pa.gy};
            if(j.feedRef) j.feedRef.edge={x:ss.x, y:ss.y}; break; }
        }
        if(path) break;
      }
    }
    /* ⭐v154 暗管对评估：直连失败，或直连 ≥12 格（18 格固定开销的临界）时——
       「入口贴边 + 出口近机器 + 地下直连」总占地更省才采用；短 feed 一律维持直连（零变化）。 */
    if(j.feed && (!path || path.length>=12)){
      const up=udTryPair(j, path, block);
      if(up){
        udBldgs.push({id:up.loader.id, x:up.loader.x, y:up.loader.y, rot:up.loader.rot, pairId:'udp'+(udPairN++)});
        udBldgs.push({id:up.unloader.id, x:up.unloader.x, y:up.unloader.y, rot:up.unloader.rot, pairId:'udp'+(udPairN-1)});
        up.loaderCells=[];
        for(let yy=up.loader.y; yy<up.loader.y+3; yy++) for(let xx=up.loader.x; xx<up.loader.x+3; xx++){ busy[K(xx,yy)]=1; up.loaderCells.push(K(xx,yy)); }
        for(let yy=up.unloader.y; yy<up.unloader.y+3; yy++) for(let xx=up.unloader.x; xx<up.unloader.x+3; xx++){ busy[K(xx,yy)]=1; }
        path=up.shortPath; s=up.shortPath[0];
        if(j.feedRef){ j.feedRef.mode='udpipe'; j.feedRef.entry={x:up.loader.x, y:up.loader.y};
          j.feedRef.exit={x:up.unloader.x, y:up.unloader.y}; j.feedRef.cells=up.shortLen;
          j.feedRef.directLen=up.directLen>=1e9?null:up.directLen; j.feedRef.saved=up.saved;
          delete j.feedRef.edge; }
      }
    }
    if(!path){
      if(j.feed){
        /* ⭐口径分离：外部接入失败**不进**「手动连」计数（那是 ⑤-3 内部连通率的回归口径），
           进 feedFail 正式点名 —— 博士自己拉暗管时，画布内补这一小段本就在他的操作流里。 */
        feedFail.push({item:j.child.name, to:j.parent.machineName, s:{x:s.x,y:s.y}, t:{x:t.x,y:t.y}, why:'path'});
        warns.push('外部接入：'+j.parent.machineName+' 要的'+j.child.name+'没铺出边缘进管（画布内这段被产线占满了）——'
          +'暗管出口可贴在 ('+s.x+','+s.y+') 外侧，画布内这一小段自己补管');
      }else{
        warns.push(j.parent.name+' ← '+j.child.name+'：走线过不去（端口/走线都被占了），这一段请手动连'
          +'（'+s.x+','+s.y+' → '+t.x+','+t.y+'）');
      }
      return;
    }
    path.forEach((c,k)=>{
      const kk=K(c.x,c.y);
      const isBr=!!axis[kk];
      /* ⭐v151 末端朝向修复（博士截图实锤「进出口的弯道又不对了」）：最后一格的 path[k+1]
         是 undefined → RwRotTo(t,t) 落到 LrotFrom 的 return 270 →
         **每条自动线的终点格箭头恒朝上**，与真实流向对撞（上游 ↓ 它 ↑）。
         修法：job 带 tInto（流向最终进入的那格 = 机器端口格 / 汇分流体本体），rot 指向 tInto
         —— 弯头、色条、flowNext 全部跟着正确。
         ⚠️ axis 轴向**必须保持旧口径**（终点格按 t 算 = 恒 'v'）：axis 只喂 RwPath 的桥接
         判定，改它会让后续线的可穿越集变化 —— 实测 feed 线失败 2 → 4（桥接绕路全变）。
         渲染（rot/flowNext）与寻路（axis）在这里解耦。 */
      const nx=path[k+1]||j.tInto||t;
      const axc=path[k+1]||t;
      const myAx=(axc.x-c.x!==0)?'h':'v';
      if(!axis[kk]) axis[kk]=myAx;
      busy[kk]=1;
      if(isBr){
        /* ⭐v152：交叉落件**分介质**（博士 2026-09-24 游戏实锤：3D 里管道在上层、传送带在下层
           —— 管×带交叉直接叠加，不放桥；同介质交叉才占同一层，要物流桥/管道桥立体跨线）。
           桥格/叠加格都对后续寻路关闭（一格最多一带一管，第三条线绕路）。 */
        delete axis[kk];
        if(cellMed[kk]===j.isP){
          /* 同介质：原线保留，上面叠物流桥 / 管道桥 */
          belts.push({x:c.x, y:c.y, rot:RwRotTo(c,nx), isPipe:j.isP,
            logiId:(j.isP?'log_pipe_connector':'log_connector'), bridge:true});
        }else{
          /* 异介质（管×带）：两层各放各的，渲染层管在上、带在下 */
          belts.push({x:c.x, y:c.y, rot:RwRotTo(c,nx), isPipe:j.isP});
        }
      }else{
        belts.push({x:c.x, y:c.y, rot:RwRotTo(c,nx), isPipe:j.isP});
        cellMed[kk]=j.isP;
      }
    });
    /* 汇流器 / 分流器那几条只算一次成品线，别重复计数 */
    if(j.feed && j.feedRef) feeds.push(j.feedRef);   /* ⭐v151 外部接入：铺成了才进 feeds（失败的在 feedFail 里点名） */
    if(!j.intoMerge && !j.intoSplit){
      linked.set(j.child, (linked.get(j.child)||0)+1);
      links.push({item:j.child.name, perMin:j.child.demand, from:j.child.machineName,
        to:j.parent.machineName, isPipe:j.isP, cells:path.length,
        /* ⭐v143 P3：存路径格（'x,y' 列表）—— 报告用它把画布上的准入口按格匹配到依赖 */
        path:path.map(c=>c.x+','+c.y), lines:RwLines(j.child.demand, j.isP),
        viaMerge:!!j.fromMerge, viaSplit:!!j.fromSplit,
        fmode:(j.feedRef&&j.feedRef.mode==='udpipe')?'udpipe':'direct'});
    }
  });
  /* ---------- 吞吐体检（路线图 ②a）：每条依赖「要几条线 / 实际连了几条 / 单线负荷」----------
     判定口径：单线负荷 = 需求 ÷ 实际线数。
       > 载具上限（带 30/分 · 管 120/分）→ **会堵**（这条线上料过不去，机器会饿）
       ≥ 90% 上限 → **紧**（没余量，需求再加一点就堵）
       否则 → 通畅。 */
  const loads=deps.map(pair=>{
    const parent=pair[0], child=pair[1];
    const isP=RwFluid(child.phase), cap=isP?RW_PIPE:RW_BELT;
    const n=linked.get(child)||0;
    const per=n?(Math.round(child.demand/n*1000)/1000):0;
    return {item:child.name, from:child.machineName, to:parent.machineName, isPipe:isP,
      demand:child.demand, lines:n, need:RwLines(child.demand,isP), perLine:per, cap:cap,
      state:(!n?'none':(per>cap+1e-6?'jam':(per>cap*0.9?'tight':'ok')))};
  });
  /* stats（⑤-2）：汇流/分流器实际摆了几个、有几条线被丢下 —— 报告与回归测试都看这几个数 */
  return {belts:belts, warns:warns, links:links, loads:loads, feeds:feeds, feedFail:feedFail,
          bldgs:udBldgs,
          stats:{split:spN, merge:mgN, dropped:dropN}};
}
function RwFindSplit(size, src, busy, corr){
  const K=(x,y)=>x+','+y;
  const need=[[0,0],[0,1],[-1,0],[1,0],[0,-1]];   /* 本体 + 下进料 + 左/右出料 + 上出料 */
  const y1=src.y-1, y0=Math.max(1, y1-(corr||5));
  for(let y=y1;y>=y0;y--){
    for(let dx=0;dx<size;dx++){
      for(const sx of (dx===0?[0,-1,1]:[dx,-dx])){
        const x=src.x+sx;
        if(x<1||x>=size-1) continue;
        let ok=true;
        for(const n of need){ if(busy[K(x+n[0],y+n[1])]){ ok=false; break; } }
        if(ok) return {x:x, y:y};
      }
    }
  }
  return null;
}
/* 在下游机器正下方的通道里找一个能放汇流器的空位（它下面收料、往上面出料） */
function RwFindMerge(size, dst, fanin, busy, corr){
  const K=(x,y)=>x+','+y;
  const need=[[0,0],[0,1],[-1,0],[1,0],[0,-1]];   /* 本体 + 下/左/右进料口 + 上出料口 */
  const y0=dst.y+dst.d, y1=Math.min(size-1, y0+(corr||5));
  for(let y=y0;y<=y1;y++){
    for(let dx=0;dx<size;dx++){
      for(const sx of (dx===0?[0,-1,1]:[dx,-dx])){
        const x=dst.x+sx;
        if(x<1||x>=size-1) continue;
        let ok=true;
        for(const n of need){ if(busy[K(x+n[0],y+n[1])]){ ok=false; break; } }
        if(ok && y>=1) return {x:x, y:y};
      }
    }
  }
  return null;
}
function RwLines(perMin, isPipe){ return (!perMin||perMin<=0)?0:Math.ceil(perMin/(isPipe?RW_PIPE:RW_BELT)); }
function RwProbe(s, t, busy, size, reserved){
  const K=(x,y)=>x+','+y;
  const mine=k=>k===K(s.x,s.y)||k===K(t.x,t.y);
  return RwPath(s, t, busy, size, (x,y)=>!!reserved[K(x,y)]&&!mine(K(x,y)));
}
/* 【一句话】★ 全项目最硬的一段 —— **带转向代价与桥接的手写 Dijkstra 最短路**（非调库）。
   状态 = (x, y, 方向, 是否在桥上)：带方向因为转向有代价（TURN=2），带桥因为踩桥有代价（BRIDGE=4）；
   代价 直行 1 / 转向 +2 / 踩桥 +4，末尾 +0.0001 做稳定排序防同代价抖动。
   ⭐ 路线图 ③「桥接器」（2026-09-21，参照 IndustrialPlanner 的 Connector 规则）：
     已铺线格不再一律是墙 —— 允许「正交直穿」：我方走向与被穿线的轴向正交、且穿过时不转弯，
     该格铺**物流桥 / 管道桥**（cost +4，比绕远路便宜时自动启用）。同向重叠依然禁止（会互相顶）。
     状态含 onBridge：桥上只能直行、且下一格必须落回空地 —— 一格桥只跨一条线。 */
function RwPath(s, t, busy, size, block, axis){
  const K=(x,y)=>x+','+y;
  const axOf=(x,y)=>(axis&&axis[K(x,y)])||null;
  const blocked=(x,y)=>!!busy[K(x,y)]||(block?!!block(x,y):false);
  const ok=(x,y)=>x>=0&&y>=0&&x<size&&y<size&&!blocked(x,y);
  if(s.x===t.x&&s.y===t.y) return [s];
  if(!ok(t.x,t.y)) return null;
  const dirs=[[0,-1],[0,1],[-1,0],[1,0]];
  const TURN=2, BRIDGE=4;
  const key=(x,y,d,b)=>x+','+y+','+d+','+b;
  const dist={}, prev={};
  const heap=[], hpush=n=>{ heap.push(n); let i=heap.length-1;
    while(i>0){ const p=(i-1)>>1; if(heap[p].c<=heap[i].c) break;
      const tmp=heap[p]; heap[p]=heap[i]; heap[i]=tmp; i=p; } };
  const hpop=()=>{ const top=heap[0], last=heap.pop();
    if(heap.length){ heap[0]=last; let i=0;
      for(;;){ const l=i*2+1, r=l+1; let m=i;
        if(l<heap.length&&heap[l].c<heap[m].c) m=l;
        if(r<heap.length&&heap[r].c<heap[m].c) m=r;
        if(m===i) break; const tmp=heap[m]; heap[m]=heap[i]; heap[i]=tmp; i=m; } }
    return top; };
  dist[key(s.x,s.y,-1,0)]=0;
  hpush({c:0,x:s.x,y:s.y,d:-1,b:0});
  let hitD=null, hitB=0;
  while(heap.length){
    const cur=hpop();
    const ck=key(cur.x,cur.y,cur.d,cur.b);
    if(dist[ck]!==undefined && dist[ck]<cur.c-1e-9) continue;
    if(cur.x===t.x&&cur.y===t.y){ hitD=cur.d; hitB=cur.b; break; }
    for(let i=0;i<4;i++){
      const nx=cur.x+dirs[i][0], ny=cur.y+dirs[i][1];
      if(nx<0||ny<0||nx>=size||ny>=size) continue;
      let nb=0, step;
      if(ok(nx,ny)){
        step=1+((cur.d>=0&&i!==cur.d)?TURN:0);
      }else if(axis && !block(nx,ny) && !cur.b){
        const a=axOf(nx,ny);
        const cross=(a==='h'&&i<=1)||(a==='v'&&i>=2);
        if(!cross) continue;
        step=1+((cur.d>=0&&i!==cur.d)?TURN:0)+BRIDGE; nb=1;
      } else continue;
      const nc=cur.c+step+(i===cur.d?0:0.0001);
      const k2=key(nx,ny,i,nb);
      if(dist[k2]!==undefined && dist[k2]<=nc) continue;
      dist[k2]=nc; prev[k2]=ck;
      hpush({c:nc,x:nx,y:ny,d:i,b:nb});
    }
  }
  if(hitD===null) return null;
  const out=[]; let ck=key(t.x,t.y,hitD,hitB);
  while(ck){ const p=ck.split(','); out.push({x:+p[0], y:+p[1]}); ck=prev[ck]; }
  out.reverse();
  return out;
}
/* ---------- 一键跑完整条闭环（会清空画布，可撤销）----------
   【一句话】总控 + 优化器：两趟展开配方树 → 枚举布局参数 → 摆+铺+打分 → 择优落盘。
   【分节】
     [1] 入参校验 / 目标与速率            → 早退
     [2] 两趟展开（跨地区收货两遍走）      → res（配方树）
     [3] 限摆与通道高度自适应              → depLines
     [4] 打分口径 pickScore（局部函数）
     [5] 参数网格候选（含 wide 换行档）     → cands
     [6] 第一轮：全候选摆+铺+打分          → best
     [7] 失败驱动的三段补搜：
          (a) 宽间距扩搜  (b) 相邻交换爬山（≤24 次）  (c) 通道高度爬升
     [8] 落盘：写 L.objs / L.plan / L.msg → render()
   ⚠️ 第 7 节三段共享 best/tried 状态且顺序敏感；抽成独立函数要传 6 个上下文，
      签名比函数体还长 → **刻意不抽**（详见 排布器算法地图.md 第五节）。 */
function LawRun(targetId, perMin){
  /* ── [1] 入参校验 / 目标与速率 ───────────────────────── */
  const L=Linit();
  if(!targetId){ L.msg='先选一个目标物品'; render(); return; }
  perMin=+perMin||0;
  if(perMin<=0){ L.msg='目标速率要大于 0'; render(); return; }
  L.tgt=targetId; L.rate=perMin;
  /* ── [2] 两趟展开（跨地区收货两遍走）───────────────── */
  /* ⭐⑥-1 跨地区收货（博士 2026-09-22：「只用从四号谷地向武陵超库存传输」）
     做法是**两趟展开**：第一趟按老口径展开，拿到它认出来的「原料」清单；
     第二趟把其中**能被跨地区传输**的（FactoryItemTable.transferDomainIds 非空，243 件）
     挑出**一种**标成「收货」（一条路线一次只能传一种 —— 见下面单选注释），其余回退本地自产
     —— 这样「哪些算原料」由配方树自己决定，我不用另立一份口径、也不会漏。
     收货只改变「原材料从哪来」，机器台数与配方一字不动 → 老的口径与评分全都不受影响。 */
  /* ⭐⑥-2 多目标（2026-09-22）：工具栏「＋ 目标」加的额外目标（L.mt）与主目标合成一图展开 ——
     共享的中间料只建一套，路由层按幽灵边逐条连线 / 分流。
     ⚠️ mt 为空时 ex=null，两次 Rexplode 的参数与老路径一字不差（601 项回归依赖）。 */
  const mt=(L.mt||[]).filter(x=>x&&x.id);
  if(mt.some(x=>!(+x.rate>0))){ L.msg='「＋ 目标」里还有没填速率的行（速率要大于 0）'; render(); return; }
  const ex=mt.length?{seeds:[{itemId:targetId, perMin:perMin}].concat(
    mt.map(x=>({itemId:x.id, perMin:+x.rate||0})))}:null;
  const opt0={selfLoop:!!L.selfLoop}, opt1={selfLoop:!!L.selfLoop, shipFromName:LshipFromName()};
  if(ex){ opt0.seeds=ex.seeds; opt1.seeds=ex.seeds; }
  const res0=Rexplode(targetId, perMin, opt0);
  /* ⭐⑥-1 单选（2026-09-22 博士指出 + 三源核实）：一条传输路线**一次只能传一种物品** ——
     协议管理里 Edit → 选一种物品 → 启动；换物品 = 停止重设、计时重置回 1 小时（GameRant/GameWith/Game8 一致）。
     所以「能传的自动全收」只在链里恰有 1 种可传原料时成立；≥2 种时必须**挑一种**走传输，
     其余回退**本地自产**（产线照建）。默认挑「需求最大的那一种」（最值得省的产能），报告里可换选。 */
  let shipList=[];
  if(L.shipIn && res0){
    /* ⭐v81：候选计算收口到 LshipPanel（链上全物品都能选、原料叶优先排前；报告与面板共用同一份状态）。
       ⚠️ 老坑备忘：res.raw 是**物品 id 串数组**不是节点对象（2026-09-22 踩过：当对象用 → eff=undefined → 收货清单空）。 */
    LshipPanel(res0);
    if(L.shipPick) shipList=[L.shipPick];
  } else if(!L.shipIn){ L.shipCands=[]; }
  opt1.shipInList=shipList;
  const res=Rexplode(targetId, perMin, opt1);
  if(!res.machines.length){ L.msg='「'+res.targetName+'」没有机器配方，排不了产线'; render(); return; }
  if(res.totalMachines>RW_MAX_MACHINES){
    L.msg='这条链展开要 '+res.totalMachines+' 台机器（超过上限 '+RW_MAX_MACHINES+'），先不生成 —— '
      +'多半是把野外采集的料也自己做了。把速率调小，或换一个更靠上游的目标物品试试'
      +(res.externals.length?('；这条链里已按外部输入处理的：'+res.externals.map(RwItemName).join('、')):'');
    render(); return;
  }
  /* ⭐⭐ C6-b 阶段 2 门禁（2026-09-25，博士拍板「软门禁」）：
     在**生成阶段**拦住「无去路物品」—— 这是 C6 从体检升级为硬约束的那一步。
     ⚠️ 必做成门禁而非扣分项（红线）：扣分项会让排布器在「补 sink」与「换贵配方」间权衡，
        而 sink 成本照常计入 → 账本骗自己（详见 RflowSinkPlan 头部注释）。
     软门禁 = 补不上时**拒绝出方案 + 明确报原因**，不静默作废。
     开销：无必爆项时 RflowSinkPlan 立刻返回 → 老路径行为一字不变。 */
  const sinkGate=RflowSinkGate(res);
  if(sinkGate){ L.msg=sinkGate; render(); return; }
  const sinkPlan=RflowSinkPlan(res);
  /* ── [3] 限摆与通道高度自适应 ───────────────────────── */
  /* 层间通道高度**按并联线数自适应**：固定 5 行在产能高的时候会被线挤死（实测 30/分 有 9 条连不上）。
     线越多 → 通道越高。上限 14 行，免得画布塞不下。
     ⚠️ 2026-09-21 补：线数口径要跟 RwRoute 的真并联一致（那里 np 会抬到 RwLines(demand)）。 */
  const depLines=res.machines.reduce((s,n)=>s+(n.children||[]).reduce((t,c)=>
    t+(c.recipeId?Math.max(c.machines||1, n.machines||1, RwLines(c.demand, RwFluid(c.phase))):0),0),0);
  /* ⭐⭐ 路线图 ③ 二梯队「参数搜索 + 局部交换」（2026-09-21）：
     第一梯队证实"启发式一步到位"不可靠（紧凑档在大产线灾难性劣化），所以直接上搜索：
     ① 参数网格：间 {4,3,2} × 按列对齐 {关,开} × 通道基础 {5,3} = 12 组，全部摆+铺+打分；
     ② 失败驱动的局部交换：最优组若还有「手动连」，对它的每层相邻机器对做交换重铺
        （同 itemId 的不换——换同料机器没意义），分数更高就留，最多试 24 对；
     ③ 择优口径不变：连通段 > 手动连 > 总线长。大产线（>15 台）砍掉交换、网格减半控时长。 */
  /* ── [4] 打分口径 pickScore（局部函数）───────────────── */
  /* ⭐⭐ ⑤-3（2026-09-22）打分口径修正：**「手动连」的权重从 100 提到 400**。
     实测（实验铜骨骼@10）：全连通的方案（间8/通道13/down，手动连 0、线 753 格）反而**输给**
     还有 2 条手动连的紧凑方案（线 454 格）—— 因为 2×100 的罚分盖不过 300 格线长差。
     这是口径反了：**少一条线是玩家得动手补的功能缺陷，多铺些格子只是效率问题**。
     改权重后"能全连通"压过"线短"，线长只在同等连通度之间做区分。 */
  const pickScore=(pl,rt)=>{
    const loads=rt.loads||[];
    const ok=loads.filter(x=>x.state!=='none'&&x.state!=='jam').length;
    const manual=rt.warns.filter(w=>w.indexOf('手动连')>=0).length;
    const jam=loads.filter(x=>x.state==='jam').length;
    return {ok:ok, manual:manual, jam:jam, belts:rt.belts.length,
      v:ok*1000 - jam*500 - manual*400 - rt.belts.length};
  };
  const small=res.totalMachines<=15;
  /* ── [5] 参数网格候选（含 wide 换行档）──────────────── */
  const cands=[];
  /* 宽度不匹配检测：某层台数 > 其下游层台数 × 1.3 → 加「层内主动换行」候选（down 模式） */
  const cntByDepth={};
  res.machines.forEach(n=>{ cntByDepth[n.depth]=(cntByDepth[n.depth]||0)+(n.machines||0); });
  const dks=Object.keys(cntByDepth).map(Number).sort((a,b)=>a-b);
  let wide=false;
  for(let wi=1;wi<dks.length;wi++){
    if(cntByDepth[dks[wi]] > (cntByDepth[dks[wi-1]]||0)*1.6){ wide=true; break; }
  }
  (small?[4,3,2]:[4,3,2]).forEach(gx=>{
    (small?[false,true]:[false,true]).forEach(al=>{
      (small?[5,3]:[Math.min(5, depLines)]).forEach(cb=>{
        cands.push({gapX:gx, align:al, corrBase:cb, swap:null});
      });
    });
  });
  /* down 候选收窄：只 gapX 4/2 各一组（大产线单组 ~300ms，控制总时长） */
  if(wide){
    const cbD=small?5:Math.min(5, depLines);
    [4,2].forEach(gx=>{ cands.push({gapX:gx, align:false, corrBase:cbD, swap:null, mode:'down'}); });
    if(small) cands.push({gapX:3, align:false, corrBase:cbD, swap:null, mode:'down'});
  }
  /* ── [6] 第一轮：全候选摆+铺+打分 → best ────────────── */
  let best=null, tried=0, overAll=true;
  cands.forEach(c=>{
    const corr=Math.max(c.corrBase, Math.min(14, Math.ceil(depLines/2)+2));
    const pl=LawPlan(res, L.size, corr, {gapX:c.gapX, align:c.align, mode:c.mode});
    if(pl.over.length) return;
    overAll=false;
    const rt=RwRoute(pl.objs, res, L.size, corr);
    const sc=pickScore(pl, rt);
    tried++;
    if(!best || sc.v>best.sc.v) best={c:c, sc:sc, plan:pl, route:rt, corr:corr};
  });
  if(overAll || !best){
    /* ⑥-4：拒绝生成时也要点名限摆 —— 天有洪炉 >12 台的链单层宽超任何画布（12×(5+间) ≈ 108 列），
       实际上「超限」几乎必然伴随「放不下」；只报放不下玩家会以为是布局器菜，其实是游戏限摆。 */
    const limW=RwPlaceLimitWarn(res);
    L.msg='画布 '+L.size+'×'+L.size+' 放不下这条产线（试了 '+cands.length+' 组参数都越界），先把画布调大或把目标速率调小'
        +(limW.length?('；⚠ '+limW.join('；')):''); render(); return;
  }
  /* ── [7] 失败驱动的三段补搜 ─────────────────────────── */
  /* ── [7a] 宽间距扩搜（手动连 > 0 才跑）────────────── */
  /* ⭐⭐ ⑤-3（2026-09-22）失败驱动的「宽间距扩搜」：
     实测 壤晶废液@10 / 清水@10 / 赤铜块@10 / 实验铜骨骼@10 的手动连，**只要把机器间距从 2~4 拉到 8 就全清零** ——
     间距大了，机器之间那条竖缝才够几条线并排走。宽间距会让小产线的总线长变长（线长在评分里是次要项），
     所以**只在最优方案还有手动连时才补跑这几组**：平时一分钱不花，失败时才多花 1~2 秒。 */
  const corrAuto=Math.min(14, Math.ceil(depLines/2)+2);
  let wideTried=0;
  if(best.sc.manual>0){
    const wideC=[];
    [4,6,8].forEach(gx=>{
      [corrAuto+2, Math.min(20, corrAuto+6)].forEach(cb=>{
        wideC.push({gapX:gx, align:false, corrBase:cb, swap:null, mode:'down'});
      });
    });
    wideC.push({gapX:8, align:false, corrBase:corrAuto, swap:null});
    wideC.forEach(c=>{
      const corr=Math.max(c.corrBase, corrAuto);
      const pl=LawPlan(res, L.size, corr, {gapX:c.gapX, align:c.align, mode:c.mode});
      if(pl.over.length) return;
      const rt=RwRoute(pl.objs, res, L.size, corr);
      const sc=pickScore(pl, rt);
      tried++; wideTried++;
      if(sc.v>best.sc.v) best={c:c, sc:sc, plan:pl, route:rt, corr:corr};
    });
  }
  /* ── [7b] 相邻交换爬山（≤24 次；仅小产线）─────────── */
  /* 失败驱动的局部交换 */
  let swaps=0;
  if(small && best.sc.manual>0 && best.plan.order){
    Object.keys(best.plan.order).forEach(d=>{
      const arr=best.plan.order[d];
      for(let i2=0;i2+1<arr.length && swaps<24;i2++){
        if(arr[i2].itemId===arr[i2+1].itemId) continue;
        const c2={gapX:best.c.gapX, align:best.c.align, corrBase:best.c.corrBase,
                  swap:{depth:+d, i:i2, j:i2+1}};
        const corr2=Math.max(c2.corrBase, Math.min(14, Math.ceil(depLines/2)+2));
        const pl2=LawPlan(res, L.size, corr2, {gapX:c2.gapX, align:c2.align, swap:c2.swap, mode:c2.mode});
        if(pl2.over.length) continue;
        const rt2=RwRoute(pl2.objs, res, L.size, corr2);
        const sc2=pickScore(pl2, rt2);
        tried++; swaps++;
        if(sc2.v>best.sc.v) best={c:c2, sc:sc2, plan:pl2, route:rt2, corr:corr2};
      }
    });
  }
  /* ── [7c] 通道高度爬升（手动连 > 0 时 +2 重铺）────── */
  /* 失败驱动爬升：最优组仍有手动连时，通道加高 2 行再铺一遍（通道挤是常见失败因） */
  if(best.sc.manual>0){
    const corrUp=Math.min(14, best.corr+2);
    if(corrUp>best.corr){
      const plUp=LawPlan(res, L.size, corrUp, {gapX:best.c.gapX, align:best.c.align, swap:best.c.swap, mode:best.c.mode});
      if(!plUp.over.length){
        const rtUp=RwRoute(plUp.objs, res, L.size, corrUp);
        const scUp=pickScore(plUp, rtUp);
        tried++;
        if(scUp.v>best.sc.v){ best={c:{gapX:best.c.gapX, align:best.c.align, corrBase:corrUp, swap:best.c.swap}, sc:scUp, plan:plUp, route:rtUp, corr:corrUp}; }
      }
    }
  }
  /* ── [8] 落盘：写 L.objs / L.plan / L.msg → render() ── */
  const plan=best.plan, route=best.route, corr=best.corr;
  const st0=route && route.stats;
  const pickNote='参数搜索 '+tried+' 组'+(wideTried?('（含宽间距扩搜 '+wideTried+' 组）'):'')+(swaps?('（含相邻交换 '+swaps+' 次）'):'')
    +' —— 用了 间'+best.c.gapX+'/通道'+corr+(best.c.mode==='down'?'/分层对齐':'/对齐'+(best.c.align?'开':'关'))
    +'（连通 '+best.sc.ok+' 段 · 手动连 '+best.sc.manual+' · 线 '+best.sc.belts+' 格'
    +(st0&&(st0.merge||st0.split)?(' · 汇流 '+st0.merge+' / 分流 '+st0.split):'')+'）';
  const rt=route;
  /* ⭐⭐ C6-b 阶段 2 软门禁最后一环（博士 2026-09-25 拍板）：
     **摆位预检必须先于 Lpush** —— 否则「摆不下就拒绝」会把画布留成半清空的坏状态。
     这里用 plan.objs + rt.belts + rt.bldgs 先算一遍占用，模拟摆池子；
     放不下就干净利落地 return（画布一字未动），放得下再进落盘。
     ⚠️ 之所以要在落盘前预检而不是落盘后回滚：Lpush 之后 L.objs 已被清空重写，
        此时 return 会留下「已 push 但没内容」的无法撤销状态。 */
  if(sinkPlan.sinks.length){
    const preOcc=[];
    plan.objs.forEach(o=>preOcc.push({x:o.x,y:o.y,w:o.w,d:o.d}));
    (rt.bldgs||[]).forEach(b=>{ const bb=byBp(b.id); if(bb){ const f=Lfp(bb); preOcc.push({x:b.x,y:b.y,w:f[0],d:f[1]}); } });
    const beltSet={}; rt.belts.forEach(bl=>{ beltSet[bl.x+','+bl.y]=1; });
    const preSink=RplaceSinks(sinkPlan, L.size, function(x,y){
      if(beltSet[x+','+y]) return true;
      for(let i=0;i<preOcc.length;i++){ const o=preOcc[i];
        if(x>=o.x&&x<o.x+o.w&&y>=o.y&&y<o.y+o.d) return true; }
      return false;
    });
    if(preSink.unplaced.length){
      L.msg='这条产线有物品没有去路，需要摆销毁建筑，但画布上放不下：'
        +preSink.unplaced.map(u=>u.sink.forItem+'（'+(u.sink.name||u.sink.buildingId)+' ×'+u.sink.count
          +'，'+u.why+'）').join('；')
        +'。先把画布调大、降低速率，或清掉画布上一些东西再试。';
      render(); return;
    }
  }
  Lpush();
  L.objs=[]; L.sel=[]; L.pick=null;
  plan.objs.forEach(o=>{
    const obj=Lmk(o.b, o.x, o.y, 0);
    obj.r=o.node.recipeId;                 /* 复用上一轮的「设施选配方」：格子上会标产出物品 */
    obj.prod=o.node.name;                  /* 产物名按**树节点**给 —— 拆解机的 outcomes[0] 是罐子，但它在产惰气 */
    obj.planRole='machine';
    obj.pkey=Rpkey(o.node);                /* ⑤-1：记住来自哪个树节点，「重排其余」按它对回台数 */
    L.objs.push(obj);
  });
  rt.belts.forEach(bl=>{
    /* bl.logiId 有值说明这是排布器自动摆的**汇流器 / 分流器**，不是普通带子 */
    const pb=byBp(bl.logiId || (bl.isPipe?'log_pipe_01':'grid_belt_01'));
    if(!pb) return;
    const obj=Lmk(pb, bl.x, bl.y, bl.rot);
    obj.planRole='link';
    if(bl.merge) obj.planRole='merge';
    if(bl.split) obj.planRole='split';
    L.objs.push(obj);
  });
  (rt.bldgs||[]).forEach(b=>{
    /* ⭐v154 暗管入口/出口对：作为普通建筑落盘（ports 渲染/接口统计全自动生效） */
    const obj=Lmk(byBp(b.id), b.x, b.y, b.rot);
    obj.planRole='udpipe'; obj.pairId=b.pairId;
    L.objs.push(obj);
  });
  /* ⭐⭐ C6-b 阶段 2：销毁支线落盘（池子 / 热能池）。
     摆位在**产线 + 走线 + 暗管全部定形之后** → 只捡剩余空位，不挤产线。
     （放不下已在 Lpush 之前预检拦掉，这里必然能摆下。）
     开销：无必爆项时 sinkPlan.sinks 为空 → 一行都不多跑（老路径零影响）。 */
  const sinkPlaced=RplaceSinks(sinkPlan, L.size, function(x,y){
    for(let i=0;i<L.objs.length;i++){ const o=L.objs[i];
      if(x>=o.x&&x<o.x+o.w&&y>=o.y&&y<o.y+o.d) return true; }
    for(let i=0;i<rt.belts.length;i++){ const bl=rt.belts[i];
      if(bl.x===x&&bl.y===y) return true; }
    return false;
  });
  sinkPlaced.objs.forEach(s=>{
    const obj=Lmk(s.b, s.x, s.y, 0);
    obj.planRole='sink'; obj.prod=s.kind==='heat'?'热能池（烧电池）':'扩容反应池（销毁）';
    obj.sinkFor=s.forItem;
    L.objs.push(obj);
  });
  L.plan={res:res, plan:plan, route:rt, rawNeed:rawNeedOf(res), sinkPlan:sinkPlan, sinkPlaced:sinkPlaced};
  const limWarns=RwPlaceLimitWarn(res);   /* ⑥-4：建筑专属限摆（天有洪炉 ≤12 台）—— 报警不拦截 */
  const sinkNote=sinkPlan.sinks.length?('；♻️ 销毁支线：'+sinkPlan.reasons.join('；')
    +(sinkPlaced.unplaced.length?('；⚠ '+sinkPlaced.unplaced.length+' 个销毁建筑没找到空位（见报告）'):'')):'';
  L.msg='产线已生成：'+(res.targets?res.targets.map(t=>t.name+' '+t.perMin+'/分').join(' ＋ ')
    :res.targetName+' '+perMin+'/分')+' —— 机器 '+res.totalMachines+' 台 + 管线 '+rt.belts.length+' 格'
        +(pickNote?('；'+pickNote):'')
        +sinkNote
        +(limWarns.length?('；⚠ '+limWarns.join('；')):'')
        +(rt.warns.length?('；'+rt.warns.length+' 条提醒见下方'):'');
  render();
}
/* 原料需求汇总（排布器的报告、评价函数都要用，抽出来免得两处口径不一致） */
function rawNeedOf(res){
  const m={};
  (res.nodes||[]).forEach(n=>{ if(n.raw) m[n.itemId]=(m[n.itemId]||0)+(n.demand||0); });
  return m;
}
/* 清掉上次生成的产线（只清 planRole 标记过的） */
function LawClear(){
  const L=Linit();
  const n=L.objs.filter(o=>o.planRole).length;
  if(!n){ L.msg='画布上没有排布器生成的产线'; render(); return; }
  Lpush();
  L.objs=L.objs.filter(o=>!o.planRole); L.sel=[]; L.plan=null;
  L.msg='已清掉排布器生成的 '+n+' 个件（可撤销）'; render();
}
/* ⭐ ⑤-1「重排其余」（2026-09-22，博士：锁住满意的机器，只重排其余）
   锁定件原地不动（当固定件 / 障碍），其余机器重新分层摆位并绕开它们，管线整条重铺。
   ⚠️ 台数口径：把每个树节点的台数**减去已锁台数**再交给 LawPlan，锁定件自己拼回摆放列表 ——
      机器总数守恒、产量不变。RwRoute 拿的是**原始 res**（依赖与总台数没变，线才连得对）。 */
function Lreroll(){
  const L=Linit(), P=L.plan;
  if(!P||!L.objs.some(o=>o.planRole==='machine')){
    L.msg='先「生成产线」，再锁定里面满意的机器，然后点这里重排其余'; render(); return;
  }
  const locks=L.objs.filter(o=>o.lock&&o.planRole==='machine');
  if(!locks.length){
    L.msg='还没有锁定的机器 —— 选中满意的几台点「锁定选中」（或按 L），重排时它们的原位就不动';
    render(); return;
  }
  const lockN={};
  locks.forEach(o=>{ if(o.pkey) lockN[o.pkey]=(lockN[o.pkey]||0)+1; });
  const nodeOf={};
  P.res.machines.forEach(n=>{ nodeOf[Rpkey(n)]=n; });
  const res2=Object.assign({}, P.res, {machines:P.res.machines.map(n=>{
    const left=Math.max(0,(n.machines||0)-(lockN[Rpkey(n)]||0));
    return left===(n.machines||0)?n:Object.assign({}, n, {machines:left});
  })});
  /* 不归排布器管的散件（手摆的机器 / 手拉的线）：留着不动，同时当障碍 —— 免得新东西压上去 */
  const loose=L.objs.filter(o=>!o.planRole);
  const FXR=locks.map(o=>({x:o.x,y:o.y,w:o.w,d:o.d})).concat(loose.map(o=>({x:o.x,y:o.y,w:o.w,d:o.d})));
  const fixedItems=locks.map(o=>{
    const b=byBp(o.id);
    const nd=(o.pkey&&nodeOf[o.pkey])||null;
    return {node:nd||{itemId:'',name:o.prod||'',phase:'固态',depth:9,recipeId:o.r||null,machineId:o.id,machines:1,children:[]},
            b:b, x:o.x, y:o.y, w:o.w, d:o.d, k:0};
  });
  const depLines=P.res.machines.reduce((s,n)=>s+(n.children||[]).reduce((t,c)=>
    t+(c.recipeId?Math.max(c.machines||1, n.machines||1, RwLines(c.demand, RwFluid(c.phase))):0),0),0);
  const autoCorr=Math.min(14, Math.ceil(depLines/2)+2);
  const cands=[];
  [4,2,3].forEach(gx=>{ const cb=Math.max(5, autoCorr); cands.push([gx, cb, 'down']); });
  cands.push([4, Math.min(14, autoCorr+2), 'down']);   /* 通道再加高一档（通道挤是常见失败因） */
  let best=null, tried=0, overN=0;
  cands.forEach(c=>{
    const pl=LawPlan(res2, L.size, c[1], {gapX:c[0], align:false, mode:'down', fixed:FXR});
    if(pl.over.length){ overN++; return; }
    const all=fixedItems.concat(pl.objs);
    const rt=RwRoute(all, P.res, L.size, c[1], loose);
    const sc=LawPick(rt);
    tried++;
    if(!best||sc.v>best.sc.v) best={c:c, plan:pl, all:all, route:rt, sc:sc};
  });
  /* ⭐ ⑤-3：与 LawRun 同口径的「失败驱动宽间距扩搜」（只在还有手动连时才补跑） */
  let wideTried=0;
  if(best && best.sc.manual>0){
    const wideC=[[6, autoCorr], [8, autoCorr], [8, Math.min(20, autoCorr+4)], [6, Math.min(20, autoCorr+4)]];
    wideC.forEach(c=>{
      const pl=LawPlan(res2, L.size, c[1], {gapX:c[0], align:false, mode:'down', fixed:FXR});
      if(pl.over.length){ overN++; return; }
      const all=fixedItems.concat(pl.objs);
      const rt=RwRoute(all, P.res, L.size, c[1], loose);
      const sc=LawPick(rt);
      tried++; wideTried++;
      if(sc.v>best.sc.v) best={c:c, plan:pl, all:all, route:rt, sc:sc};
    });
  }
  if(!best){
    L.msg='放不下：锁定件占着的位置腾不开其余机器（试了 '+cands.length+' 组'+(overN?('，其中 '+overN+' 组直接越界'):'')
      +'）—— 解锁几台、或把画布调大一点再试'; render(); return;
  }
  const newM=best.plan.objs.length;
  Lpush();
  const keep=locks.slice();
  best.plan.objs.forEach(o=>{
    const obj=Lmk(o.b, o.x, o.y, 0);
    obj.r=o.node.recipeId; obj.prod=o.node.name; obj.planRole='machine'; obj.pkey=Rpkey(o.node);
    keep.push(obj);
  });
  best.route.belts.forEach(bl=>{
    const pb=byBp(bl.logiId || (bl.isPipe?'log_pipe_01':'grid_belt_01'));
    if(!pb) return;
    const obj=Lmk(pb, bl.x, bl.y, bl.rot);
    obj.planRole='link';
    if(bl.merge) obj.planRole='merge';
    if(bl.split) obj.planRole='split';
    keep.push(obj);
  });
  L.objs=loose.concat(keep);
  /* ⭐ C6-b 阶段 2：重排会重置 L.objs（best.all 只含机器）→ **销毁支线必须重摆**，
     否则「重排其余」一次就把池子悄悄弄丢了，而报告还写着「已在画布上标出」（假成功）。
     重排不改变 res（依赖与台数不变）→ sinkPlan 可原样复用，只需在新布局上重新找位。 */
  const rerollSink=(P.sinkPlan||RflowSinkPlan(P.res));
  if(rerollSink.sinks.length){
    const rs=RplaceSinks(rerollSink, L.size, function(x,y){
      for(let i=0;i<L.objs.length;i++){ const o=L.objs[i];
        if(x>=o.x&&x<o.x+o.w&&y>=o.y&&y<o.y+o.d) return true; }
      for(let i=0;i<best.route.belts.length;i++){ const bl=best.route.belts[i];
        if(bl.x===x&&bl.y===y) return true; }
      return false;
    });
    rs.objs.forEach(s=>{
      const obj=Lmk(s.b, s.x, s.y, 0);
      obj.planRole='sink'; obj.prod=s.kind==='heat'?'热能池（烧电池）':'扩容反应池（销毁）';
      obj.sinkFor=s.forItem;
      L.objs.push(obj);
    });
  }
  L.sel=locks.map(o=>o.uid);
  /* 评价函数看的是「整套布局」→ 把锁定件 + 新摆件合并后的那份交给它 */
  L.plan={res:P.res, plan:{objs:best.all, bands:best.plan.bands, height:best.plan.height, over:[], order:{}},
          route:best.route, rawNeed:P.rawNeed, sinkPlan:rerollSink};
  const stR=best.route.stats;
  L.msg='重排完成：锁定 '+locks.length+' 台（位置不动）· 重摆 '+newM+' 台 · 管线 '+best.route.belts.length+' 格 —— '
    +'间'+best.c[0]+'/通道'+best.c[1]+'（连通 '+best.sc.ok+' 段 · 手动连 '+best.sc.manual+' · 试了 '+tried+' 组'
    +(wideTried?('，含宽间距扩搜 '+wideTried+' 组'):'')
    +(stR&&(stR.merge||stR.split)?(' · 汇流 '+stR.merge+' / 分流 '+stR.split):'')+'）'
    +(loose.length?('；画布上另有 '+loose.length+' 个手摆件留在原地，已被当障碍避开'):'')
    +(best.route.warns.length?('；'+best.route.warns.length+' 条提醒见下方'):'');
  render();
}
/* 目标物品 / 速率的选择 —— 不进撤销栈，也不重渲染速率框（重渲染会让输入框失焦） */
function Ltgt(v){ const L=Linit(); L.tgt=v; L.msg='排产目标改为「'+RwItemName(v)+'」';
  /* ⭐v82（博士截图：换了目标，选货网格还挂着旧链的蓝铁矿/蓝铁块）：候选是按目标链算的，
     换目标必须重算。LshipPanel 里「旧选中不在新候选里就回退默认原料叶」会顺手把 shipPick 纠正过来；
     链没换过（新旧目标共用一条链）时重算结果一致，多跑一趟 Rexplode 无感。 */
  if(L.shipIn) LshipPanel(null);
  render(); }
function Lrate(v){ const L=Linit(); L.rate=Math.max(1, +v||1); }
/* ⭐⑥-2 多目标（2026-09-22）：「＋ 目标」行 —— 多个目标共享的中间料只建一套再分流 */
function LmtAdd(){ const L=Linit(); if(!L.mt) L.mt=[];
  if(L.mt.length>=3){ L.msg='额外目标最多 3 行（加主目标一共 4 条链），再多报告看不过来'; render(); return; }
  L.mt.push({id:'', rate:10}); render(); }
function LmtDel(i){ const L=Linit(); if(L.mt&&L.mt[i]!=null) L.mt.splice(i,1); render(); }
function LmtTgt(i,v){ const L=Linit(); if(L.mt&&L.mt[i]) L.mt[i].id=v; render(); }
function LmtRate(i,v){ const L=Linit(); if(L.mt&&L.mt[i]) L.mt[i].rate=Math.max(0,+v||0); }
/* 「闭环自持」开关：只有回收路线的料（惰气那种）是「自己循环 + 给启动料」还是「按外部输入」 */
function LselfLoop(){
  const L=Linit();
  L.selfLoop=!L.selfLoop;
  L.msg=L.selfLoop
    ? '闭环自持：开 —— 环里的料（如惰气）会自己循环，报告里会写清「在哪台机器先塞什么」'
    : '闭环自持：关 —— 环里的料按「外部输入」处理（链更短、更好摆）';
  render();
}
/* ⭐⑥-1「跨地区收货」（2026-09-22，博士：只用四号谷地 → 武陵超库存传输）
   开了之后：这条链里的**原料**能由别的地区传过来的，就不在本地建产线，按「收货」处理。
   判定 = 「这个料能不能被超库存传输」（FactoryItemTable.transferDomainIds 非空）——
   出发地（四号谷地）那边可传「本地区集成工业可生产的任意一种物品」，
   而能传的物品清单是全库打通的（243 件，两地区通用）。
   ⭐ 单选修正（2026-09-22 博士指出 + 三源核实）：一条路线**一次只能传一种物品** ——
   链里可传原料 ≥2 种时，只挑一种走传输（默认需求最大的），其余回退本地自产。 */
/* ⭐⭐ v81（博士：「我要在布局试摆里选怎么还是看不到啊，怎么就能选源矿和蓝铁矿，其他一堆东西都能传啊」）
   两处产品级修正：
   ① 候选不再限定原料叶 —— 链上**任何**能被传输的物品都能选（含半成品/中间件）。
      引擎本来就支持：shipIn 物品在 Rexplode 里被剔除出 made → pick 返回 null → 落 raw 并标 shipIn
      （见展开器 2426-2431），选中半成品 = 它的整棵上游子树不用建。排除目标本身（含 ＋ 目标）——
      传目标等于整条链消失，没有意义。
   ② 开关打开**立刻**能选 —— 之前选货网格只在报告里（要先点「生成产线」），博士在布局试摆开开关
      什么都看不到。现在 LshipIn 开时若无产线，只做**轻量展开**算候选（Rexplode 一趟，毫秒级，
      不摆机器、不动画布），选货条直接显示在产线面板开关下方；选好再点「生成产线」即可。
      有产线时开/关照旧整条重算（v80 的开关即重算语义不变）。 */
function LshipPanel(res0){
  const L=Linit();
  if(!L.shipIn){ L.shipCands=[]; L.shipDmap=null; L.shipRawSet=null; L.shipChain=null; return; }
  if(!res0){
    if(!(L.tgt && (+L.rate>0))){ L.shipCands=[]; L.shipDmap=null; L.shipRawSet=null; L.shipChain=null; return; }
    res0=Rexplode(L.tgt, +L.rate, {selfLoop:!!L.selfLoop});
  }
  /* 需求与原料叶判定都取**收货前**的第一趟口径 —— 不管选中谁，卡片上的数字永远稳定不跳 */
  const dmap={}, rawSet={}, chainSet={};
  (res0.nodes||[]).forEach(n=>{
    dmap[n.itemId]=Math.max(dmap[n.itemId]||0, n.demand||0);
    if(n.raw) rawSet[n.itemId]=1;
    chainSet[n.itemId]=1;
  });
  const tgtSet={}; tgtSet[L.tgt]=1;
  (L.mt||[]).forEach(x=>{ if(x&&x.id) tgtSet[x.id]=1; });
  /* ⭐v82（博士：「怎么还是只有两种，我要所有能传的东西，不行上网查」）：
     Game8 / GameWith 三源核实 —— 游戏里协议管理的候选 = **出发地（四号谷地）集成工业能产出的全部物品**
     （解锁过就行、仓库里有没有都行；只能传出发地能产的，武陵特产的西岚矿就不行）。
     所以候选 = 链上可传（这条链用得上的，排前面）∪ 全库「有机器配方且能送到」的物品（RwMade ∩ RwCanReceive）。
     链上的野外原料叶（源矿/蓝铁矿——矿机产出也算地区产能，游戏里能传但它们没有机器配方）单独补进来。
     排序：链缺的原料(0) → 链上的半成品(1) → 其他可传物品(2)；前两组按需求降序，第三组按名称。
     第三组在网格里收进**折叠区**（162 件全平铺会把面板撑爆），带搜索框。 */
  const seen={}; const uniq=[];
  const add=iid=>{ if(iid && !seen[iid] && !tgtSet[iid]){ seen[iid]=1; uniq.push(iid); } };
  Object.keys(dmap).forEach(iid=>{ if(RwCanReceive(iid)) add(iid); });
  Object.keys(RwMade(LshipFromName())).forEach(iid=>{ if(RwCanReceive(iid)) add(iid); });
  const grp=iid=> rawSet[iid]?0:(chainSet[iid]?1:2);
  const cands=uniq.sort((a,b)=>(grp(a)-grp(b))
    || (grp(a)===2 ? RwItemName(a).localeCompare(RwItemName(b),'zh-Hans-CN') : ((dmap[b]||0)-(dmap[a]||0))));
  L.shipCands=cands; L.shipDmap=dmap; L.shipRawSet=rawSet; L.shipChain=chainSet;
  /* 默认挑需求最大的**原料叶**（v79 口径：最值得省的产能）；换过选且仍有效就尊重已选 */
  if(cands.length){ if(cands.indexOf(L.shipPick)<0) L.shipPick=cands[0]; }
  else L.shipPick='';
}
/* 选货网格的**共享渲染**：报告「跨地区收货」段与产线面板的收货选货条都调它，保证两处长一个样。
   withTitle=true（面板用）恒带标题 —— 面板里没有报告那层上下文；
   withTitle=false（报告用）维持 v80 行为：单候选只出一张选中卡、≥2 候选才带标题。
   ⭐v82：链上候选平铺在前，全库可传物品收进折叠区（details + 搜索框 + 滚动容器）
   —— 游戏里就是一份可传物品长列表，全平铺会把面板撑爆。
   ⭐v88（博士，二次澄清：「点开跨区域传输时我就看见这个下拉表就行」）：**平铺区取消**——
   链上原料/半成品不再单独立在外面，全部收进「全部可传物品」折叠下拉（链上的排最前）；
   summary 常显当前选中，收起时也知道选了谁。 */
function LpickGridHtml(withTitle){
  const L=Linit();
  const _cs=L.shipCands||[];
  if(!L.shipIn || !_cs.length) return '';
  const _RC={1:'#9AA0A6',2:'#5BA85A',3:'#3D7EBB',4:'#8E5BB8',5:'#D0931F',6:'#C0392B'};
  /* r1 是 Rreport 闭包里的局部工具，顶层函数够不着 —— 这里自己来一份（同精度：一位小数） */
  const _r1=x=>Math.round(x*10)/10;
  const _dm=L.shipDmap||{};
  const _raw=L.shipRawSet||{};
  const _chain=L.shipChain||{};
  const _card=c=>{
    const _v=RshipVal(c), _r=(DB.items[c]||{}).rarity||1, _isRaw=!!_raw[c], _inChain=!!_chain[c];
    /* ⭐v89（博士：「瓶罐里装的什么我看不到」）：构建期已按灌装/拆解配方反推出 content 字段
       （"装：水蒸气（气态）"/"空容器（可灌装）"），选货卡上显示——同名瓶罐变体一眼可分。 */
    const _ct=(DB.items[c]||{}).content;
    return `<button type="button" class="lo-pickcard${(L.shipPick===c)?' on':''}" style="border-left-color:${(_RC[_r]||_RC[1])}" onclick="LshipPick('${c}')">`
      +`<span class="lo-pickck">✓</span><span class="lo-picknm">${esc(RwItemName(c))}</span>`
      +`<span class="lo-pickmeta">${_ct?`<b style="color:#B26A00">${esc(_ct)}</b> · `:''}${_inChain?(_isRaw?'':'<b style="color:#185FA5">半成品</b> · ')+'需要 <b>'+_r1(_dm[c]||0)+'</b>/分 · ':'单位价值 <b>'+_v.value+'</b> · '}`
      +(_v.perBatch!=null?`每小时可传 <b>${_v.perHour}</b> 个${(_v.hours!=1?`（每批 ${_v.perBatch} 个 · ${_v.hours} 小时/批）`:'（整批到货）')}`:'填传输总值后给每小时可传数')
      +`</span></button>`;
  };
  const _grp=iid=> _raw[iid]?0:(_chain[iid]?1:2);
  /* 折叠区 = 全部可传物品（_cs 已按 链缺原料(0) → 链上半成品(1) → 其他(2) 排好，链上的自然在最前） */
  const _all=_cs;
  /* 标题：面板用恒带；报告用按总数判（>1 才带，单候选免标题） */
  const _title=withTitle
    ? `<span><b style="color:#185FA5">走传输的是哪种</b>（<b>一条路线一次只能传一种</b>） <span class="lo-tag">点卡片切换</span></span>`
    : (_all.length>1?`<span><b style="color:#185FA5">走传输的是哪种</b>（<b>一条路线一次只能传一种</b>；游戏里换物品 = 停止重设、计时重置回 1 小时） <span class="lo-tag">点卡片切换</span></span>`:'');
  const _pickNm=L.shipPick?('｜当前选：<b style="color:#185FA5">'+esc(RwItemName(L.shipPick))+'</b>'):'';
  const _fold=`
        <details class="lo-pickfold" style="margin-top:4px">
          <summary style="cursor:pointer;font-size:12px;color:var(--ink2)">全部可传物品（${_all.length} 件 —— 出发地能产且能送到的都在这，链缺的原料排最前）${_pickNm} 点开搜索选择</summary>
          <div style="margin:4px 0"><input class="lo-num" style="width:200px" type="text" placeholder="搜物品名…" oninput="LpickFilter(this.value)"></div>
          <div class="lo-pickgrid lo-pickscroll">${_all.map(_card).join('')}</div>
        </details>`;
  return `<div class="c-sub" style="margin-top:6px;display:block">${_title}${_fold}
        <span style="font-size:11.5px;color:var(--ink3)">${withTitle?'排在最前的是这条链缺的<b>原料</b>，往后的<b>半成品</b>也能传 —— 传它，它上游就全都不用建了。':'没选中的回退<b>本地自产</b>（产线照建、矿机照配）；选了这条链用不上的东西就只进仓库'}</span></div>`;
}
/* v82：折叠区搜索 —— 直接过滤卡片 display，不重渲染（input 高频触发） */
function LpickFilter(q){
  q=(q||'').trim();
  const els=document.querySelectorAll('.lo-pickscroll .lo-pickcard');
  for(let i=0;i<els.length;i++){
    const t=els[i].textContent||'';
    els[i].style.display = (!q || t.indexOf(q)>=0) ? '' : 'none';
  }
}
function LshipIn(){
  const L=Linit();
  L.shipIn=!L.shipIn;
  // 满级口径（博士 2026-09-22：只要超库存传输、按满级状态）—— 开关打开时若传输总值还空着，自动预填满级 1500（仍可手改）
  if(L.shipIn && !(+L.tv>0)) L.tv=1500;
  /* ⭐v80（博士发来游戏截图揪出）：关掉开关要**清掉单选状态**——shipCands/shipPick 留着的话，
     报告还挂着旧收货版的选择网格，看着像没关掉。v81 连 shipDmap/shipRawSet 一起清。 */
  if(!L.shipIn){ L.shipCands=[]; L.shipPick=''; L.shipDmap=null; L.shipRawSet=null; L.shipChain=null; }
  L.msg=L.shipIn
    ? '跨地区收货：开 —— 游戏口径（Game8/GameWith 核实）：出发地「'+LshipFromName()+'」能产的全部物品都能传，解锁过产能就行、仓库有没有无所谓；这条链缺的原料和半成品排在最前面，全量可传清单收在折叠区里可搜索；选中谁，本地就不建谁和它的上游；方向「从/到」可在下面换，选货条在开关下面，选好再点「生成产线」；传输总值已按满级预填 1500（可在报告里改）'
    : '跨地区收货：关 —— 原料一律按野外采集 / 本地自产处理';
  /* ⭐v80：开关即重算 —— 之前只 render()，画布和报告还是**旧 plan**（收货段纹丝不动），
     要手动再点「生成产线」开关才真的生效，用起来就像个假开关。有 plan 时直接重跑，与 LshipPick 同款。
     ⭐v81（博士：「我要在布局试摆里选怎么还是看不到啊」）：**还没有产线时**也立刻能选 ——
     轻量展开算候选（不摆机器、不动画布），选货条显示在产线面板开关下方，选好再生成。 */
  if(L.plan && L.tgt && (+L.rate>0)){ LawRun(L.tgt, L.rate); }
  else if(L.shipIn){
    LshipPanel(null); render();
    /* 开关点完网格要自己送到眼前 —— sticky 导航会盖住顶部，用 block:'center'。
       requestAnimationFrame 在测试沙箱 / 老 webview 里没有 → 同步回退（行为一致，只是不等一帧）。 */
    var _raf=(typeof requestAnimationFrame==='function')?requestAnimationFrame:function(f){ f(); };
    _raf(function(){ const el=document.querySelector('.lo-pickgrid');
      if(el && el.scrollIntoView) el.scrollIntoView({block:'center'}); });
  }
  else { render(); }
}
/* ⑥-1 换选「走传输的是哪一种」：游戏里换物品 = 停止重设、计时重置回 1 小时（报告里有提醒），
   这里重跑一遍把另一种回退本地自产。
   ⭐v81：加 plan 守卫 —— 面板选货条让「还没生成产线」也能先选（博士：选好再生成），
   此时点卡片只换选 + 刷新选货条，**不**悄悄把产线生成出来（那会覆盖博士手摆的画布）。
   有产线时照旧整条重算（v79/v80 语义不变）。 */
function LshipPick(v){
  const L=Linit();
  L.shipPick=v;
  if(L.plan && L.tgt && (+L.rate>0)) LawRun(L.tgt, L.rate);
  else render();
}
/* 跨地区收货（⑥-1）：单件物品的「一批能装多少 / 供货速率」反推
   · 每批数量上限 = 传输总值 ÷ 单位物品价值（文案 1845235994830423548）
   · 传输总值：配置表里**没有**每档的具体数值（DomainDataTable 的建设等级效果只有
     bandwidth / battleBuildingLimit / travelPoleLimit / isMineOutputUp）——
     所以只能用博士从界面上读到的数反推；没填就按档位未知、只用数值口径说明。
   · 间隔：FactoryConst.domainTransportIntervalTime = 3600（客户端常量，单位以游戏内为准）。 */
const RW_TRANSFER_INTERVAL_S = 3600;
function RshipVal(itemId, tvOverride, hoursOverride){
  const L=(typeof Linit==='function')?Linit():{};
  const value=((DB.items||{})[itemId]||{}).value;
  const tv=+((tvOverride!=null?tvOverride:L.tv)||0);
  const hours=+((hoursOverride!=null?hoursOverride:L.tvHours)||(RW_TRANSFER_INTERVAL_S/3600))||1;
  const perBatch=tv&&value?Math.floor(tv/value):null;
  return {value:(value==null?null:value), tv:(tv||null), hours:Math.round(hours*10)/10,
          perBatch:perBatch,
          perHour:(perBatch!=null?(Math.round(perBatch/hours*10)/10):null),
          perMin:(perBatch!=null?(Math.round(perBatch/hours/60*10)/10):null)};
/*  ⚠️ perMin 里的 /60 不能丢：hours 是「每批间隔小时数」，perMin 要的是「个/分」——
     3000 个/批、1 小时一批 = 50 个/分。少了这一刀就是虚高 60 倍，
     「比需求低要标红」的警告会永不触发（真机回归抓出来的）。
     ⭐v90（博士：「每小时一次性传多少，不是每分钟传多少」）：显示层一律用 perHour 主显
     （perBatch/hours，无 /60）——到货是整批一小时的节奏，不是流式速率；perMin 只留作
     与「个/分」计的产线需求做喂不饱判定的内部换算，不再上卡。 */
}
/* 传输总值输入（博士从协议管理界面读到的实际值）——不进撤销栈 */
function Ltv(v){ const L=Linit(); L.tv=Math.max(0, +v||0); render(); }
function LtvH(v){ const L=Linit(); L.tvHours=Math.max(0.1, +v||1); render(); }
/* ⭐⑥-3「从/到」方向下拉（2026-09-22 博士）：地区清单动态读 DB.bases.domains ——
   以后新地区（domain_3…）开放，这里自动多出选项，不用改代码。面板与报告两处共用。 */
function LshipDirHtml(){
  const opts=sel=>Ldomains().map(d=>`<option value="${esc(d.id)}"${d.id===sel?' selected':''}>${esc(d.name)}</option>`).join('');
  return `<div class="lo-bar" style="margin:4px 0 0"><span>收货方向：</span>`
    +`<span>从</span><select class="lo-sel" onchange="LshipDirV('from',this.value)">`+opts(LshipFromId())+`</select>`
    +`<span>到</span><select class="lo-sel" onchange="LshipDirV('to',this.value)">`+opts(LshipToId())+`</select>`
    +`<span class="lo-tag">出发地能产的才能传 · 每方向每批只传一种</span></div>`;
}
/* ========== ⭐⑥-3 跨基地选点（2026-09-22 博士拍板：v1 建议器；两地对称互传）==========
   问题：N 个目标（主 + ＋目标，≤4）放哪个地区的基地「更省」。
   数据依据（全部在库，不造数）：
     · 矿脉按地区（mining_power.ores.beds.mapMax）：紫晶只在谷地(240)、赤铜只在武陵(510)、
       蓝铁谷地富(1080 vs 120)、源矿两边都有(560/540)
     · 机器地区限定（buildings.domainNames）：天有洪炉等 9 座武陵限定 → 相关链谷地建不了（硬否决）
     · 跨地区传输（rule_domain_transfer）：每方向每批只传 1 种、上限 = 传输总值 ÷ 单价（满级 1500）、
       间隔 1h；两地对称 —— 每个方向各是独立一条协议
   口径①（地区合计，2026-09-22 博士定）：同地区多目标要同一种收货物 → 喂不饱判定按
     「地区合计需求」对每批可到货量反推，不是各基地各算各的（区内基地共享一个地区仓库）
   口径②（取货段）：地区仓库取货口（unloader_1「仓库取货口」3×1×3）→ 各基地产线要建模；
     占格与单边路数有数据（slotRule：(边长-1)÷3 向下取整 → 谷地 23/13 实测、武陵 26/16 推算），
     单口吞吐无单列数据 → 明说不能算，不造数。
   ⚠️ v1 只出建议不摆画布：现有单链公式（台数/收货反推/摆位）不受粒度影响，一行不用改。 */
function RxlTargets(){
  const L=Linit(); const t=[];
  if(L.tgt && +L.rate>0) t.push({id:L.tgt, rate:+L.rate});
  (L.mt||[]).forEach(x=>{ if(x && x.id && +x.rate>0) t.push({id:x.id, rate:+x.rate}); });
  return t;
}
function RxlBMap(){
  if(RxlBMap._c) return RxlBMap._c;
  const m={}; (DB.buildings||[]).forEach(b=>{ m[b.id]=b; });
  RxlBMap._c=m; return m;
}
/* 矿类原料叶在某地区的满采上限（/分）。非矿 → null（矿点数据只覆盖 ores.beds 里那几样） */
function RxlOreCap(itemId, regionName){
  const beds=((DB.mining_power||{}).ores||{}).beds||[];
  const b=beds.filter(x=>x.itemId===itemId)[0];
  if(!b) return null;
  const mm=b.mapMax||{};
  return {name:b.ore, cap:(mm[regionName]==null?0:mm[regionName])};
}
/* 单片基地单边取货口路数上限：bases.json slotRule 公式 = (边长-1)÷3 向下取整。
   谷地 70→23 / 40→13 是社区实测，武陵 80→26 / 50→16 由同一条公式推算（页面按「推算」标注）。 */
function RxlSlots(side){ return Math.floor(((side||0)-1)/3); }
/* 单目标 × 地区 适配分析（收货前展开；regionName='' = 不限地区）。带缓存。 */
function RxlAnalyze(iid, perMin, regionName){
  RxlAnalyze._c=RxlAnalyze._c||{};
  const key=iid+'@'+perMin+'@'+(regionName||'');
  if(RxlAnalyze._c[key]) return RxlAnalyze._c[key];
  const bmap=RxlBMap();
  const res=Rexplode(iid, perMin, {region:regionName});
  const out={id:iid, name:RwItemName(iid), rate:perMin, region:(regionName||''),
    totalMachines:res.totalMachines||0, blocked:[], ores:{}, recvNeed:{}, other:[],
    manual:[], area:0, areaEst:0, nodeSet:{}, ok:true};
  (res.machines||[]).forEach(n=>{
    out.nodeSet[n.itemId]=1;
    const b=bmap[n.machineId];
    if(!b) return;
    out.area+=(b.gridArea||0)*(n.machines||1);
    if(regionName && !b.isUniversal && (b.domainNames||[]).indexOf(regionName)<0)
      out.blocked.push('「'+b.name+'」是'+(b.domainNames||[]).join('/')+'限定 —— '+(regionName||'当地')+'建不了');
  });
  /* 占地估算：机器格数 × 2.2（通道/间距系数，按 v63~v66 实测产线量级校准）—— 报告里明标「估算」 */
  out.areaEst=Math.round(out.area*2.2);
  (res.nodes||[]).forEach(n=>{
    if(!n.raw) return;
    /* external（外部供给）不再一刀切跳过：可跨地区传且**对面能产**的 → 记进收货候选
       （如罐@谷地要的息壤液 80/分 —— 天有洪炉武陵限定，谷地只能靠收货）；
       不可传的（野外交付这类）选点不管 */
    if(n.external && !RwCanReceive(n.itemId)){
      /* 不可传的外部供给（息壤液这类：聚合池/拆解自筹，本工具没建模其产线）→ 不算矿缺口、
         也不算收货候选（根本传不过来），但**要点名** —— 不然报告会漏说一大块原料 */
      const ex=out.manual.filter(x=>x.itemId===n.itemId)[0];
      if(ex) ex.demand+=(n.demand||0);
      else out.manual.push({itemId:n.itemId, name:RwItemName(n.itemId), demand:(n.demand||0)});
      return;
    }
    const oc=RxlOreCap(n.itemId, regionName);
    if(oc){
      const o=out.ores[n.itemId]||(out.ores[n.itemId]={name:oc.name, need:0, cap:oc.cap});
      o.need+=(n.demand||0);
    }else{
      /* 非矿原料叶：另一地区能产且可传 → 收货候选（如谷地建的链要息壤）；
         谁都产不了（清水这类野外交付）→ other，选点不管 */
      let other=false;
      if(RwCanReceive(n.itemId)){
        const doms=Ldomains();
        for(let k=0;k<doms.length;k++){
          if(doms[k].name===regionName) continue;
          if((RwMade(doms[k].name)[n.itemId]||[]).length){ other=true; break; }
        }
      }
      if(other) out.recvNeed[n.itemId]=(out.recvNeed[n.itemId]||0)+(n.demand||0);
      else out.other.push(n.itemId);
    }
  });
  if(!out.totalMachines)
    out.blocked.push('这个物品在'+(regionName||'当地')+'没有机器配方（可能只有另一地区能产）');
  out.ok=out.blocked.length===0;
  RxlAnalyze._c[key]=out;
  return out;
}
/* 一片地区的收货压力（口径①在这里算）：把落到该地区各目标的缺口并起来，
   同方向（都从对面地区收）只能传一种 → 种数 >1 记冲突；恰 1 种 → 合计需求对每批可到货量反推 */
function RxlRegionShip(targets, assign, regionName){
  const doms=Ldomains(); const otherName='';
  let other=null;
  doms.forEach(d=>{ if(d.name!==regionName && (!other)) other=d.name; });
  /* ⚠️ 两地区现状下 other 取对面；未来 >2 地区时这里要升级成「按方向逐条算」 */
  const items={};
  targets.forEach((t,ix)=>{
    if(assign[ix]!==regionName) return;
    const a=RxlAnalyze(t.id, t.rate, regionName);
    Object.keys(a.ores||{}).forEach(k=>{
      const o=a.ores[k];
      if(o.need>o.cap) items[k]=(items[k]||0)+(o.need-o.cap);
    });
    Object.keys(a.recvNeed||{}).forEach(k=>{ items[k]=(items[k]||0)+a.recvNeed[k]; });
  });
  const tv=(+Linit().tv>0)?+Linit().tv:1500;
  const hours=(+Linit().tvHours>0)?+Linit().tvHours:1;
  const keys=Object.keys(items);
  const rows=keys.map(k=>{
    const value=(DB.items[k]&&DB.items[k].value)!=null?DB.items[k].value:null;
    const perBatch=(value&&value>0)?Math.floor(tv/value):null;
    const perMin=(perBatch!=null)?Math.round(perBatch/hours/60*10)/10:null;
    const perHour=(perBatch!=null)?Math.round(perBatch/hours*10)/10:null;
    return {itemId:k, name:RwItemName(k), need:Math.round(items[k]*10)/10, value:value,
      perBatch:perBatch, perMin:perMin, perHour:perHour, hours:Math.round(hours*10)/10,
      starved:(perMin!=null && items[k]>perMin)};
  });
  return {otherName:other||'对面地区', items:items, rows:rows,
    conflict:Math.max(0, keys.length-1)};
}
/* N 目标 × 2 活跃地区（从/到下拉里那两个）穷举分配，按成本择优。
   成本（全部可解释，报告逐行给理由）：硬否决 > 同方向多种收货物冲突 > 口径①喂不饱 >
   分开两地的目标对重复建共享料 > 矿缺口量。 */
function RxlBest(targets){
  const regions=[LshipFromName(), LshipToName()];
  const an={};
  const A=(t, r)=>{ const k=t.id+'@'+t.rate+'@'+r; if(!an[k]) an[k]=RxlAnalyze(t.id, t.rate, r); return an[k]; };
  const N=targets.length, combos=[];
  for(let m=0;m<(1<<N);m++){
    const assign=[]; for(let i=0;i<N;i++) assign.push((m>>i)&1 ? regions[1] : regions[0]);
    let invalid=null, cost=0, notes=[];
    for(let i=0;i<N;i++){
      const a=A(targets[i], assign[i]);
      if(!a.ok){ invalid=targets[i].name+' 不能放 '+assign[i]+'（'+a.blocked[0]+'）'; break; }
    }
    if(invalid){ combos.push({assign:assign, invalid:invalid, cost:Infinity}); continue; }
    /* 1) 每片地区的收货压力（口径① + 同方向单种） */
    let conflicts=0, starved=0;
    regions.forEach(r=>{
      const s=RxlRegionShip(targets, assign, r);
      conflicts+=s.conflict;
      s.rows.forEach(x=>{ if(x.starved) starved++; });
    });
    /* 2) 分开两地的目标对：共享的中间料要各建一套（同区放 v76 只建一套） */
    let dup=0, dupNames=[];
    for(let i=0;i<N;i++) for(let j=i+1;j<N;j++){
      if(assign[i]===assign[j]) continue;
      const ai=A(targets[i], assign[i]), aj=A(targets[j], assign[j]);
      const shared=Object.keys(ai.nodeSet).filter(k=>aj.nodeSet[k]);
      dup+=shared.length;
      if(shared.length) dupNames.push(targets[i].name+'×'+targets[j].name+'：'+shared.map(RwItemName).join('、'));
    }
    /* 3) 矿缺口量（要靠传输补的原料 /分 合计） */
    let gap=0;
    regions.forEach(r=>{
      const s=RxlRegionShip(targets, assign, r);
      Object.keys(s.items).forEach(k=>{ gap+=s.items[k]; });
    });
    cost=conflicts*1000 + starved*300 + dup*10 + Math.round(gap);
    combos.push({assign:assign, cost:cost, conflicts:conflicts, starved:starved,
      dup:dup, dupNames:dupNames, gap:Math.round(gap*10)/10, invalid:null});
  }
  combos.sort((a,b)=>a.cost-b.cost);
  return {regions:regions, combos:combos, best:combos[0]};
}
/* 面板「选点建议」开关（v1：只出建议，不摆画布） */
function LpickToggle(){ const L=Linit(); L.pickShow=!L.pickShow; render(); }
/* ⭐v144 建筑清单折叠开关 */
function LpalToggle(){ const L=Linit(); L.palOpen=!L.palOpen; render(); }
/* ⭐v144 清单宽度自适应：清单 absolute 挂在画布左侧，所以「左边有多少空白就用多宽」。
   上限 246；空白不足 130 时改为贴画布左缘浮起（画布依然不动，选完建筑自动收起就露出来）。 */
function LpalFit(){
  /* ⚠️ 两个测试沙箱（node:vm）的 mock 能力不一样：test_html.js 的 window 没有 addEventListener、
     元素没有 getBoundingClientRect；test_layout_events.js 连 document.getElementById 都不是函数。
     所以这里逐项做能力探测，探测不到就静默跳过 —— 真实浏览器才量布局。
     回归断言只认模板字符串，不依赖本函数。 */
  if(!document || typeof document.querySelector!=='function' || typeof document.getElementById!=='function') return;
  const pal=document.querySelector('.lo-pal');
  if(!pal || !pal.style || typeof pal.getBoundingClientRect!=='function') return;
  pal.style.left=''; pal.style.right=''; pal.style.marginRight=''; pal.style.width=''; pal.style.maxWidth='';
  if(pal.classList.contains('folded')) return;      /* 收起态宽度交给 CSS（34px 竖条） */
  const out=document.getElementById('out');
  if(!out || typeof out.getBoundingClientRect!=='function') return;
  const avail=out.getBoundingClientRect().left;
  const room=avail-16;            /* 留 16px 呼吸位 */
  const MINW=200;                 /* 清单可读下限：低于这个宽度，说明文字/建筑名会挤成一条 */
  if(room>=MINW){                 /* 左侧空白够 → 整个落在空白里，一点不压画布 */
    const w=Math.round(Math.min(246,room));
    pal.style.width=w+'px'; pal.style.maxWidth=w+'px';
  }else{                          /* 空白不够 → 保持可读宽度，尽量贴左；最多压住画布左缘几十像素（画布仍不动） */
    /* 贴视口左缘：lo-wrap 左缘 = avail，所以 left=-avail 就等于「从屏幕最左开始」，
       左侧那截页面空白照样用得上 —— 这样压住画布的宽度最小（1450 视口下仅 26px）。 */
    pal.style.left=Math.round(-avail)+'px';
    pal.style.right='auto'; pal.style.marginRight='0';
    pal.style.width=MINW+'px'; pal.style.maxWidth=MINW+'px';
  }
}
/* 窗口变宽/变窄时，左侧空白跟着变 —— 重算一次（此时不 re-render，画布更不会动） */
if(typeof window!=='undefined' && window && window.addEventListener){   /* 沙箱没有这个方法，别炸 */
  window.addEventListener('resize', ()=>{ if(typeof tab!=='undefined' && tab==='layout') LpalFit(); });
}
/* v144 从清单里点选建筑 = 拿起 + 自动收起清单（画布让位）。程序化 Lpick 不受影响。 */
function LpickFromList(id){ Lpick(id); Linit().palOpen=false; render(); }
/* 单目标 × 单地区的一行对比文案（RxlHtml 用） */
function RxlRowHtml(t, r, picked){
  const a=RxlAnalyze(t.id, t.rate, r);
  const mark=picked?'<b style="color:#185FA5">✔ 推荐</b>':'';
  let body='';
  if(!a.ok){
    body=a.blocked.map(x=>'<div class="c-sub" style="margin-top:1px"><span style="color:'+RW_COL.bad+'">✗ '+esc(x)+'</span></div>').join('');
  }else{
    const ores=Object.keys(a.ores).map(k=>{
      const o=a.ores[k];
      const cap=(o.cap>0? o.cap+'/分' : '<b>没有矿点</b>');
      const fit=o.need<=o.cap
        ? '本地够（上限 '+cap+'）'
        : '缺 '+Math.round((o.need-o.cap)*10)/10+'/分（上限 '+cap+'）→ 要收货';
      return '<span>· '+esc(o.name)+' 需 '+Math.round(o.need*10)/10+'/分：'+fit+'</span>';
    }).join('');
    const recv=Object.keys(a.recvNeed).map(k=>'<span>· '+esc(RwItemName(k))+' 需 '+Math.round(a.recvNeed[k]*10)/10+'/分：当地不能产 → 走收货</span>').join('');
    const manual=(a.manual||[]).map(m=>'<span>· '+esc(m.name)+' 需 '+Math.round(m.demand*10)/10+'/分：<b style="color:'+RW_COL.warn+'">不能跨地区传输</b> —— 产线未建模（聚合池/拆解自筹），要放这里就得本地想办法</span>').join('');
    const other=(a.other||[]).length?'<span>· 野外交付：'+esc(a.other.map(RwItemName).join('、'))+'</span>':'';
    /* 落位档位：占地估算 vs 该地区各基地可用格（数据：bases.json maxBases[].area.usableCells） */
    const bases=(DB.bases.maxBases||[]).filter(x=>x.domainName===r&&(x.area&&x.area.usableCells));
    bases.sort((x,y)=>x.area.usableCells-y.area.usableCells);
    const fitB=bases.filter(x=>x.area.usableCells>=a.areaEst)[0];
    const tier=fitB
      ? '建议「'+esc(fitB.zoneName)+'·'+esc(fitB.role)+'」（可用 '+fitB.area.usableCells+' 格）'
      : '超出该地区最大基地可用格（'+(bases.length?bases[bases.length-1].area.usableCells:'-')+'）→ 要拆分或两地分摊';
    body='<div class="c-sub" style="margin-top:1px"><span>'+(ores||'<span>· 矿类原料：无</span>')+'</span></div>'
      +(recv?'<div class="c-sub" style="margin-top:1px"><span>'+recv+'</span></div>':'')
      +(manual?'<div class="c-sub" style="margin-top:1px"><span>'+manual+'</span></div>':'')
      +(other?'<div class="c-sub" style="margin-top:1px"><span>'+other+'</span></div>':'')
      +'<div class="c-sub" style="margin-top:1px"><span>· 机器 <b>'+a.totalMachines+'</b> 台 · 占地约 <b>'+a.areaEst+'</b> 格（机器格数×2.2 估算，非实测）→ '+tier+'</span></div>';
  }
  return '<div class="c-sub" style="margin-top:3px"><span><b>'+esc(a.name)+'</b> @'+t.rate+'/分 放<b>'+esc(r)+'</b> '+mark+'</span></div>'+body;
}
/* 选点建议整段渲染（报告与面板共用；不依赖已生成的产线 —— 轻量展开，毫秒级） */
function RxlHtml(){
  const ts=RxlTargets();
  const W=RW_COL.warn, B=RW_COL.bad;
  if(!ts.length) return '<div class="c-sub" style="margin-top:6px"><span class="c-id">跨基地选点（⑥-3）：先选目标物品（或用「＋ 目标」加几个），这里才给得出「哪个成品放哪片基地更省」的建议。</span></div>';
  const best=RxlBest(ts);
  const b=best.best;
  let head='';
  if(!b || b.cost===Infinity){
    head='<div class="c-sub" style="margin-top:2px"><span style="color:'+B+'">所有分配组合都不可行 —— 每个目标的硬否决理由：</span></div>'
      +ts.map(t=>'<div class="c-sub" style="margin-top:1px"><span>· <b>'+esc((t.name||RwItemName(t.id)))+'</b>：'
        +best.regions.map(r=>{
          const a=RxlAnalyze(t.id,t.rate,r);
          return esc(r)+'：'+(a.ok?'可行':a.blocked.join('；'));
        }).join('　')+'</span></div>').join('');
  }else{
    head='<div class="c-sub" style="margin-top:2px"><span>推荐分配（'+(1<<ts.length)+' 种组合穷举，成本口径：硬否决 &gt; 同方向多种收货物 &gt; 口径①喂不饱 &gt; 分两地重复建共享料 &gt; 矿缺口量）：'
      +ts.map((t,ix)=>'<b>'+esc((t.name||RwItemName(t.id)))+'</b> → <b style="color:#185FA5">'+esc(b.assign[ix])+'</b>').join(' · ')
      +'</span></div>'
      +(b.conflicts?'<div class="c-sub" style="margin-top:1px"><span style="color:'+W+'">⚠ 有 '+b.conflicts+' 处「同一方向要收多种料」—— 每方向每批只能传一种，多出的要本地自产或改分配</span></div>':'')
      +(b.dupNames&&b.dupNames.length?'<div class="c-sub" style="margin-top:1px"><span style="color:'+W+'">⚠ 分开两地的目标对要重复建的共享料：'+esc(b.dupNames.join('；'))+'</span></div>':'');
  }
  const cmp=ts.map(t=>best.regions.map(r=>RxlRowHtml(t, r, b&&b.assign&&b.assign[ts.indexOf(t)]===r)).join('')).join('');
  /* 口径①：地区合计收货压力（同区多基地收同一种料 → 按地区合计反推，不是各基地各算各的） */
  const ship=(b&&b.assign)?best.regions.map(r=>{
    const s=RxlRegionShip(ts, b.assign, r);
    if(!s.rows.length) return '<div class="c-sub" style="margin-top:2px"><span>· <b>'+esc(r)+'</b>：无需跨地区收货（矿与原料本地都够）</span></div>';
    return '<div class="c-sub" style="margin-top:2px"><span>· <b>'+esc(r)+'</b>（从 '+esc(s.otherName)+' 收）：'
      +s.rows.map(x=>'<b>'+esc(x.name)+'</b> 合计需 <b>'+x.need+'</b>/分 · 单价 '+x.value
        +(x.perBatch!=null?(' · 每小时可传 <b>'+x.perHour+'</b> 个（每批 '+x.perBatch+' 个 · '+x.hours+' 小时/批）'
          +(x.starved?('　<b style="color:'+B+'">喂不饱 —— 地区合计需求超过一条传输线的供货速率，得本地自产一部分</b>'):('　✅ 够'))):'　<span class="c-id">传输总值没填/单价缺失，不给数字</span>')).join('；')
      +'</span></div>';
  }).join(''):'';
  const shipSeg='<div class="c-sub" style="margin-top:4px"><span><b style="color:#185FA5">口径① · 地区合计收货压力</b> —— 同地区多基地收同一种料，按<b>地区合计需求</b>反推（区内基地共用一个地区仓库）</span></div>'+ship;
  /* 口径②：地区仓库取货口 → 各基地产线（占格/路数有数据；吞吐无单列数据 → 明说，不造数） */
  const doms=Ldomains();
  const pick=(b&&b.assign)?best.regions.map(r=>{
    const dom=doms.filter(d=>d.name===r)[0];
    const used=ts.filter((t,ix)=>b.assign[ix]===r).map(t=>esc((t.name||RwItemName(t.id)))).join('、');
    const bases=(DB.bases.maxBases||[]).filter(x=>x.domainName===r&&(x.area&&x.area.side));
    const measured=(r==='四号谷地');
    return '<div class="c-sub" style="margin-top:2px"><span>· <b>'+esc((dom&&dom.storageName)||r+'仓库')+'</b> 供：'+(used||'（无目标落在此地）')+'</span></div>'
      +'<div class="c-sub" style="margin-top:1px"><span>　'+bases.map(x=>'· '+esc(x.zoneName)+'（'+esc(x.role)+' '+x.area.side+'×'+x.area.side+'）单边取货口 ≤ <b>'+RxlSlots(x.area.side)+'</b> 路'+(measured?'（实测）':'（按公式 (边长-1)÷3 推算）')).join('　')+'</span></div>';
  }).join(''):'';
  const pickSeg='<div class="c-sub" style="margin-top:4px"><span><b style="color:#185FA5">口径② · 地区仓库取货口 → 各基地</b> —— 取货口「仓库取货口」占地 <b>3×1×3</b>，贴仓库存取线放</span></div>'
    +pick
    +'<div class="c-sub" style="margin-top:1px"><span class="c-id">⚠ 单口/整线的取货<b>吞吐配置表里没有单列数据</b> —— 这里只给占格与路数上限，喂不喂得动产线要实测，本工具不编数字。画布内产线照旧摆，「仓库 → 取货口 → 产线」这一段不在画布里。</span></div>';
  return '<div class="c-sub" style="margin-top:8px"><span><b style="color:#185FA5">跨基地选点（⑥-3）—— 哪个成品放哪片基地更省</b> <span class="lo-tag">两地联动：同时只在至多两个地区运行</span></span></div>'
    +head+'<div style="margin-top:4px">'+cmp+'</div>'+shipSeg+pickSeg
    +'<div class="c-sub" style="margin-top:2px"><span class="c-id">v1 只出建议不摆画布：按建议切到对应基地、逐条点「生成产线」即可（现有单链公式不受影响）。</span></div>';
}
/* 可排产的物品清单（有机器配方的），按名字排 */
function RwTargets(){
  const m=RwMade(), out=[];
  /* ⭐v146 同名物品区分（博士 2026-09-24：目标下拉里「赤铜瓶（灌装机）」重复了 12 条）：
     根因不是重复 —— 是 12 个不同的物品 id 都叫「赤铜瓶」（灌装机把不同液体/气体灌进瓶里，
     灌水/酸液/息壤气各是独立物品），只显示物品名自然分不出来。
     修法：同名多 id 时，从该配方原料里挑「非容器本身」的那个名字缀上 ——「赤铜瓶·水（灌装机）」。 */
  const nameCnt={};
  Object.keys(m).forEach(id=>{ if((DB.items||{})[id]){ const n=RwItemName(id); nameCnt[n]=(nameCnt[n]||0)+1; } });
  Object.keys(m).forEach(id=>{
    if(!(DB.items||{})[id]) return;
    const r=m[id][0];
    const base=RwItemName(id);
    let name=base;
    if(nameCnt[base]>1){
      const ing=(r.ingredients||[]).map(x=>RwItemName(x.id)).filter(n=>n&&n!==base);
      if(ing.length) name=base+'·'+ing[0];
    }
    out.push({id:id, name:name, machine:r.machineName, ways:m[id].length});
  });
  out.sort((a,b)=>a.name<b.name?-1:a.name>b.name?1:0);
  return out;
}
/* ========== 电力 与 野外开采（2026-09-21）==========
   用电：FactoryBuildingTable.powerConsume —— **配置表字段，可直接陈述**。
   ⚠️ 每台热能池发多少电 **配置表里没有**（建筑表只有 needPower / powerConsume，没有发电量），
      教学文案也只定性说「热能池利用源矿或电池提供电能」「电池的发电效率高于源矿」。
      → 所以这里**只报用电**，发电/存电只能实测。见 DB.mining_power.power 里的 evidence（文案原文可复核）。
   开采：FactoryMinerTable.msPerRound → 20/分；FactoryFluidPumpInTable → 60/分。同样是**基础速率**，
      矿脉纯度加成属运行时，配置表没有。 */
function Rpower(objs){
  const list=objs||Linit().objs;
  const byCat={};
  let total=0, n=0;
  list.forEach(o=>{
    const b=byBp(o.id); if(!b) return;
    const pc=+b.powerConsume||0;
    if(pc>0){ total+=pc; n++; byCat[b.categoryName]=(byCat[b.categoryName]||0)+pc; }
  });
  return {total:total, devices:n, byCat:byCat};
}
/* 这个原料能不能野外采到、基础速率多少（能就报出来，不能就返回 null）
   ⚠️ 2026-09-21 修正：**必须查 DB.mining_power.gather（7 座采集建筑的全集）**，
      不能只看 miners（那只有矿机表里的 3 台）—— 会漏掉 **水驱矿机（采赤铜矿）**、
      气体收集泵（采惰气）、二型耐酸水泵。博士当场指出过这个漏项。
   ⚠️ 水驱矿机等 3 台**配置表里没有开采速率字段**，perMin 会是 null —— 这时要如实说"速率配置表无"。 */
function RmineRate(itemId){
  const mp=DB.mining_power||{};
  const list=(mp.gather&&mp.gather.length)?mp.gather:(mp.miners||[]);
  for(let i=0;i<list.length;i++){
    const m=list[i];
    const hit=(m.mineable||[]).filter(x=>x.itemId===itemId)[0];
    if(hit) return {kind:m.kind, name:m.name, perMin:m.perMin, rateKnown:!!m.rateKnown};
  }
  /* 没有精确对应时：按 desc 文案兜底 —— ⚠️ **只认「开采〈X〉」这句话里的名字**。
     不能整句 indexOf：水驱矿机的 desc 里还有「可使用**清水**完成自供能」，那是它的**燃料**不是产物，
     整句匹配会把清水错判成"水驱矿机开采的"（2026-09-21 实测踩到）。 */
  const nm=RwItemName(itemId);
  for(let i=0;i<list.length;i++){
    const m=list[i];
    const mt=String(m.desc||'').match(/开采([^，。；]+?)(?:等多|等|的)/);
    if(mt && mt[1].indexOf(nm)>=0 && m.kind!=='抽水 / 抽液'){
      return {kind:m.kind, name:m.name, perMin:m.perMin, rateKnown:!!m.rateKnown, byDesc:true};
    }
  }
  /* 兜底：流体原料 → 找一台**速率已知**的泵（pump_1 水泵 60/分）；气体优先气体收集泵 */
  const pumps=mp.pumps||[];
  const ph=RwPhaseOf(itemId);
  if(ph && ph!=='固态'){
    const gp=pumps.filter(x=>x.rateKnown)[0] || pumps[0];
    if(gp) return {kind:gp.kind, name:gp.name, perMin:gp.perMin, rateKnown:!!gp.rateKnown, fluid:true};
  }
  return null;
}
/* ========== 第 1 层：约束硬校验（2026-09-21）==========
   ① 协议容量 —— 配置表 ✅（bandwidth 累加 vs 建造区上限，上限在 bases.json 的 caps）
   ② 发电 —— 用电是配置表 ✅；**发电量是社区数值**。
      博士 2026-09-21 定：**谷地用谷地电池、武陵用武陵电池**；一台热能池发电功率 = 燃料功率值。
   ③ 野外采集上限 —— 矿点属关卡场景数据（配置表无），用社区矿脉数 × 每脉点数 × 纯度速率算**区间**。 */
/* ⭐v145 修 bug：协议容量以前恒算成 0 —— byBp() 读的是「占地蓝图」注入版，注入层把 bandwidth 裁掉了
   （实测 byBp('furnance_1') 没有该字段，而 DB.buildings 里是 2）→ 页面「📶 协议容量」长期显示 0/200，
   超限也永不报警。这里建一张 id→bandwidth 索引，从 DB.buildings 取，别再走 byBp。 */
let LO_BW_IDX=null;
function LbwOf(id){
  if(!LO_BW_IDX){
    LO_BW_IDX={};
    ((DB&&DB.buildings)||[]).forEach(b=>{ LO_BW_IDX[b.id]=+b.bandwidth||0; });
  }
  return LO_BW_IDX[id]||0;
}
function Rbandwidth(objs){
  const L=Linit();
  let use=0;
  (objs||L.objs).forEach(o=>{ use+=LbwOf(o.id); });
  const row=(((DB.bases||{}).maxBases)||[]).filter(r=>r.levelId===L.base)[0];
  const cap=(row&&row.caps)?row.caps.bandwidth:null;
  return {use:use, cap:cap, over:(cap!=null&&use>cap), zone:row?row.zoneName:null};
}
function Rtheories(usePower, regionName){
  const mp=DB.mining_power||{}, gen=(mp.power||{}).generation||{};
  const base=+(gen.baseOutput||200);
  const byReg=(mp.power||{}).fuelByRegion||{};
  const fuels=byReg[regionName]||byReg['通用']||[];
  const gap=Math.max(0, (+usePower||0)-base);
  return {base:base, gap:gap, fuels:fuels.map(f=>({item:f.item, power:f.power, count: gap>0?Math.ceil(gap/f.power):0}))};
}
/* 矿石满采上限（按矿种）。三种数据形态要分开对待：
     · 矿脉类（源矿 / 紫晶矿 / 蓝铁矿）：可放矿机数 = 矿脉数 × 每脉 2~6 点 → 给区间
     · 矿源点类（赤铜矿）：**点数就是可放矿机台数**，不乘每脉点数；另有游戏内「理论最大开采值」
   ⚠️ 2026-09-21 晚三次核查：上一版把赤铜矿写成「清波寨 8 个点」= 160/分，**把清波寨一个区当成了全图**。
      实际赤铜矿在**武陵的 5 个区、共 21 个矿源点**（1.1 实测 420/分），
      1.5 的游戏内理论最大开采值是 **510/分** —— 差额 90 还没定位到区域，照实标出来、不抹平。
   `dataVersion` / `versionLog` 是**版本接口**：游戏更新只改数据，这里的代码不用动。 */
/* 矿石满采上限（按矿种）。
   ⭐ 2026-09-21 第四次核查后，口径**只剩一条**：满采量 = 矿点数 × 20/分（高纯度）。
      一个矿脉只放 1 台矿机 —— 四号谷地实测 560/240/1080 除以 20 正好是 28/12/54 个矿点，
      与 TapTap 地图工具的矿脉数逐项相等。（游戏里一个矿脉视觉上有 2~6 个矿石簇，那是外观、不是矿机位；
      早期按「脉数 × 每脉 2~6 点」算出来的 2320~6960/分**虚高 2~6 倍**。）
   `theoreticalMax` 是**游戏内**的「理论最大开采值」（博士可核），有它就用它。
   `mapMax` 是按**大地区**（四号谷地 / 武陵）的最大理论值 —— 博士要核对的那张表。 */
function RoreCapacity(){
  const mp=DB.mining_power||{}, ores=mp.ores||{}, per=ores.perNodePerMin||20;
  return (ores.beds||[]).map(b=>{
    const pts=b.pointsTotal||0, tm=b.theoreticalMax||null;
    const max=tm?tm.value:pts*per;
    return {ore:b.ore, itemId:b.itemId, unit:b.unit||'矿点', isPoint:!!b.unit,
            points:pts, perNode:per, lo:max, hi:max, fixed:true,
            theoreticalMax:tm, byMap:b.byMap||{}, mapMax:b.mapMax||{},
            mapMaxConfidence:b.mapMaxConfidence||{},
            zones:b.zones||[], zonesSum:b.zonesSum||null, zonesNote:b.zonesNote||'',
            zonesCover:b.zonesCover||'', zonesCoverAll:!!b.zonesCoverAll,
            unaccounted:b.unaccounted||null, rig:b.rig||'', since:b.since||'', regions:b.regions||''};
  });
}
/* 数据版本信息（版本接口） */
function RoreMeta(){
  const o=(DB.mining_power||{}).ores||{};
  return {schemaVersion:o.schemaVersion||1, dataVersion:o.dataVersion||DB.meta.gameVersion,
          gameVersion:DB.meta.gameVersion, builtAt:DB.meta.builtAt,
          versionLog:o.versionLog||[], purityRule:o.purityRule||{}, notOre:o.notOre||'',
          capacityHow:o.capacityHow||''};
}
/* 某个矿「按小地图」的明细（报告里用） */
/* 某个矿「按小地图」的明细（报告里用） */
function RoreZoneRows(c){
  if(!c.zones.length) return '';
  const rows=c.zones.map(z=>{
    const n=(z.points!=null?z.points:z.beds);
    const pm=z.perMin?('　'+z.perMin+'/分'):('　'+(n*c.perNode)+'/分');
    const hl=(z.high!=null)?('　<span class="c-id">'+z.high+' 高纯度'+(z.low?(' + '+z.low+' 低纯度'):'')+'</span>'):'';
    return '　· '+esc(z.zone)+(z.levelId?(' <span class="c-id">'+esc(z.levelId)+'</span>'):'')
      +'：<b>'+n+'</b> 点'+pm+hl+(z.note?('<br><span class="c-id">　　'+esc(z.note)+'</span>'):'');
  }).join('<br>');
  const zs=c.zonesSum||{};
  const sum='　'+esc(c.zonesCover||'')+'小计 <b>'+(zs.points!=null?zs.points:zs.beds)+'</b> 点'
    +(zs.perMin?(' = '+zs.perMin+'/分'):'')+(zs.version?('（'+esc(zs.version)+' 实测）'):'');
  const un=c.unaccounted
    ? ('<br>　<b style="color:'+RW_COL.warn+'">⚠️ 与 '+esc((c.theoreticalMax||{}).version||'更高版本')
       +' 的理论值差 <b>'+c.unaccounted.perMin+'/分</b>，还没定位到是哪个区哪几个点</b>'
       +'<br><span class="c-id">　　'+esc(c.unaccounted.note)+'</span>')
    : '';
  return '<div class="c-sub" style="margin-top:2px;padding-left:10px"><span>'
    +'<b>按小地图</b>：<br>'+rows+'<br>'+sum
    +(c.zonesNote?('<br><span class="c-id">　'+esc(c.zonesNote)+'</span>'):'')+un+'</span></div>';
}
/* ⚙️ 原料侧闭环（路线图 ④）：把「这条产线需要多少原料」推成野外侧的具体动作 ——
     要几台矿机 · 哪个区的矿点够 · 水驱矿机的供水够不够。
   ⚠️ 只能算到这一层：**没有矿点逐点坐标**，所以排不了野外段的实际摆放与跨区运输（暗管 ≤300m）——
      这正是路线图 ④ 里那条「[卡数据] 矿点逐点坐标」。能答的是「够不够、要几台、水够不够」。
   数据来源：矿点/每点产量 20/分（本页按地区最大值口径）；水驱矿机耗水 20/分·台、水泵 60/分、1 泵最多带 3 台
   —— 这三条是社区实测，写在 mining_power.gather 的 note 里。 */
function RrawLoop(P, rawNeed){
  const caps=RoreCapacity();
  const WRIG_WATER=20, PUMP_OUT=60, PUMP_MAX_RIG=3;
  /* ⚠️ ⑥-1：跨地区收货的料**本地不再采**，这一段必须把它摘出去 ——
     否则报告会同时写着「赤铜矿（跨地区收货）」和「赤铜矿 需 20/分 → 要 1 台矿机」，自相矛盾。 */
  const shipSet={};
  (P.res.shipIn||[]).forEach(s=>{ if(s&&s.itemId) shipSet[s.itemId]=1; });
  const items=(P.res.raw||[]).map(id=>{
    const c=caps.filter(x=>x.itemId===id)[0];
    const need=Math.round((rawNeed[id]||0)*10)/10;
    return {id:id, name:RwItemName(id), need:need, cap:c||null};
  }).filter(x=>x.need>0 && !shipSet[x.id]);
  const shipped=(P.res.raw||[]).filter(id=>shipSet[id] && (rawNeed[id]||0)>0);
  if(!items.length && !shipped.length) return '';
  const rows=items.map(it=>{
    const c=it.cap;
    if(!c) return '· '+esc(it.name)+' 需 <b>'+it.need+'</b>/分　<span class="c-id">本库没有它的矿点数据（多半是野外液体 / 气体节点，或本来就要外部输入）</span>';
    const rigs=Math.ceil(it.need/c.perNode);
    const zs=c.zones.slice().sort((a,b)=>((b.points||0)-(a.points||0)));
    let line='· '+esc(it.name)+' 需 <b>'+it.need+'</b>/分 → 要 <b>'+rigs+'</b> 台矿机'
      +'（'+c.perNode+'/分·台，'+esc(c.rig||'电驱矿机')+'）';
    if(c.isPoint){
      /* ⭐ ④ 里「能做的那一半」：供水与供电的**配比清单**（博士 2026-09-22 给的口径：
         1 台水泵最多带 3 台水驱矿机满效率）。走线本身做不了（无线回仓、野外不是网格、没有地形数据），
         但「几台泵 / 怎么分 / 几条管 / 要不要通电」全是纯计算，直接给。 */
      const water=rigs*WRIG_WATER, pumps=Math.ceil(rigs/PUMP_MAX_RIG);
      const tail=rigs%PUMP_MAX_RIG;   /* 最后一台泵实际带几台（0 = 正好整除） */
      line+='<br><span class="c-id">　　· 水驱矿机每台耗水 '+WRIG_WATER+'/分 → 共 <b>'+water+'</b>/分，需 <b>'+pumps
        +'</b> 台水泵（'+PUMP_OUT+'/分·台）</span>'
        /* ⚠️ 只有 1 台泵时别写成「前 0 台各带 3 台」（真机跑出来过这行文案） */
        +'<br><span class="c-id">　　· 分管：<b>1 台水泵最多带 '+PUMP_MAX_RIG+' 台水驱矿机满效率</b>（每台 '+WRIG_WATER
        +'/分，泵出 '+PUMP_OUT+'/分）—— '+(rigs<=PUMP_MAX_RIG
          ? ('这 1 台泵带 '+rigs+' 台（还能再带 '+(PUMP_MAX_RIG-rigs)+' 台）')
          : (tail ? ('前 '+(pumps-1)+' 台各带 '+PUMP_MAX_RIG+' 台、最后一台带 '+tail+' 台')
                  : (pumps+' 台各带 '+PUMP_MAX_RIG+' 台')))
        +'；每台泵 '+PUMP_OUT+'/分 &lt; 管道上限 '+RW_PIPE+'/分 → <b>每台泵 1 条管道就够</b>（不用并联）</span>'
        +'<br><span class="c-id">　　· 供电：<b>水泵要通电</b>（10 电/台 → 共 '+pumps*10
        +' 电，野外要么把电拉过来、要么就近放供电桩）；<b>水驱矿机靠清水自供能、不耗电</b></span>';
    }
    line+='<br><span class="c-id">　　· 可选区（'+esc(c.zonesCover||'')+'）：'+zs.map(z=>esc(z.zone)).join(' / ')+'</span>'
      +'<br><span class="c-id">　　· 各区点数：'+zs.map(z=>(z.points!=null?z.points:z.beds)+' 点').join(' / ')
      +'　合计 <b>'+c.points+'</b> 点'+(c.points<rigs
        ?(' —— <b style="color:'+RW_COL.bad+'">不够，差 '+(rigs-c.points)+' 台</b>'):' —— 够')
      +(c.points>rigs?('（占 '+Math.round(rigs/Math.max(1,c.points)*100)+'%，还有余量）'):'')+'</span>';
    return line;
  }).join('<br>');
  const shipRow=shipped.length
    ? '<div class="c-sub" style="margin-top:2px"><span class="c-id">· '+shipped.map(id=>esc(RwItemName(id))).join('、')
      +' 走的是<b>跨地区收货</b>（见上）—— 本地不摆矿机、不占野外矿点，这一段不给它算配比</span></div>'
    : '';
  return '<div class="c-sub" style="margin-top:8px"><span><b>⚙️ 原料侧闭环</b> <span class="lo-tag">路线图 ④</span>'
    +' —— 原料需求 → 野外摆几台矿机 / 哪个区够 / 水够不够</span></div>'
    +shipRow
    +(items.length?('<div class="c-sub" style="margin-top:2px"><span>'+rows+'</span></div>'):'')
    +'<div class="c-sub" style="margin-top:2px"><span class="c-id">⚠️ <b>只算到「要几台 / 哪个区够 / 水与电够不够」这一层；野外段的实际摆放与走线，本工具不做</b>'
    +'（博士 2026-09-22 追问「那这样 ④ 还用做吗」，答案：不用按原样做）。两条原因：<br>'
    +'　　① <b>野外没有需要连的线</b> —— 三种矿机的产物都是<b>无线回传仓库</b>（水驱 / 电驱 / 二型电驱）'
    +'或<b>缓存区手动取</b>（便携源石矿机），每个矿点独立放一台就完事，没有连线 / 避让 / 优化可言；<br>'
    +'　　② <b>野外不是网格</b>，配置表里也没有地形与障碍（只有单段线长上限：供电桩 <code>autoConnectLength</code> 30m / 中继器 80m）'
    +'—— 真实的水管怎么绕、电从哪拉，只能看那一片地形长什么样。<br>'
    +'　　⇒ 路线图 ④ 的「矿点逐点坐标」「供水管网走线」在本工具里<b>标为不做</b>（不是遗漏）；'
    +'能做的<b>配比清单</b>（几台泵 / 怎么分 / 几条管 / 要不要通电）已在上面给出。</span></div>';
}
/* 全矿种的「按小地图」总览表（页面说明区用） */
/* 全矿种的「按小地图」总览表：矿点数 + 每点满纯度产量 */
function oreZoneTable(){
  const caps=RoreCapacity(), idx={}, order=[];
  caps.forEach(c=>c.zones.forEach(z=>{
    if(!idx[z.zone]){ idx[z.zone]={zone:z.zone, levelId:z.levelId, items:{}}; order.push(z.zone); }
    idx[z.zone].items[c.ore]=(z.points!=null?z.points:z.beds);
  }));
  const pref=['枢纽区','谷地通道','阿伯莉采石场','源石研究园','矿脉源区','供能高地',
              '景玉谷','武陵城','清波寨','首墩','试验园区','藏剑谷','应龙关','北部禁区','雪松林'];
  order.sort((a,b)=>((pref.indexOf(a)<0?99:pref.indexOf(a))-(pref.indexOf(b)<0?99:pref.indexOf(b))));
  const ores=caps.map(c=>c.ore);
  const cell=(z,k)=>{
    const v=z.items[k];
    if(v==null) return '<span class="c-id">—</span>';
    const c=caps.filter(x=>x.ore===k)[0];
    return '<b>'+v+'</b> 点　<span class="c-id">'+(v*(c?c.perNode:20))+'/分</span>';
  };
  return '<table class="lo-tb"><tr><td class="lo-td-h">小地图</td><td class="lo-td-h">区域</td>'
    +ores.map(o=>'<td class="lo-td-h">'+esc(o)+'<br><span class="c-id">点数 / 满纯度产量</span></td>').join('')+'</tr>'
    +order.map(zn=>{
      const z=idx[zn];
      return '<tr><td class="c-id">'+esc(z.levelId||'—')+'</td><td class="lo-td-h">'+esc(zn)+'</td>'
        +ores.map(o=>'<td>'+cell(z,o)+'</td>').join('')+'</tr>';
    }).join('')
    +'<tr><td class="lo-td-h">合计</td><td class="lo-td-h">—</td>'
    +caps.map(c=>'<td><b>'+(c.points)+'</b> 点　<span class="c-id">'+(c.hi)+'/分</span></td>').join('')
    +'</tr></table>';
}
/* 每个大地区的最大理论值
   ✅ 两列都是实测（2026-09-21 闭环）：四号谷地 = NGA 两帖 + 游民星空 + sticweb 四方一致（560/240/1080），
      除以 20 正好是本表的点数；武陵 = 博士武陵简报截图逐区计数（540/0/120/510），
      赤铜矿 23 高×20 + 5 低×10 = 510，与游戏内 UI「理论最大开采值」完全一致。 */
function oreMapMaxTable(){
  const caps=RoreCapacity(), maps=['四号谷地','武陵'];
  const head='<tr><td class="lo-td-h">矿种</td>'
    +maps.map(m=>'<td class="lo-td-h">'+m+'</td>').join('')
    +'<td class="lo-td-h">全图</td><td class="lo-td-h">可信度</td></tr>';
  const rows=caps.map(c=>{
    const parts=maps.map(m=>{
      const v=(c.mapMax||{})[m];
      const n=(c.byMap||{})[m];
      if(v==null) return '<td class="c-id">—</td>';
      return '<td><b>'+v+'</b>/分'+(n?'　<span class="c-id">'+n+' 点</span>':'')
        +((c.mapMaxConfidence||{})[m]?('<br><span class="c-id">'+esc(c.mapMaxConfidence[m])+'</span>'):'')+'</td>';
    }).join('');
    return '<tr><td class="lo-td-h">'+esc(c.ore)+'</td>'+parts
      +'<td><b>'+c.hi+'</b>/分</td>'
      +'<td class="c-id">'+(c.unaccounted?('<b style="color:'+RW_COL.warn+'">1.5 理论值 '+c.theoreticalMax.value
        +'，与按区差 '+c.unaccounted.perMin+'</b>'):'—')+'</td></tr>';
  }).join('');
  return '<table class="lo-tb">'+head+rows+'</table>';
}
function RoreCapOf(itemId){ return RoreCapacity().filter(x=>x.itemId===itemId)[0]||null; }
/* ========== 第 1 层的尾巴（2026-09-21 晚 · 路线图 ②b / ②c）==========
   路线图 ② 剩的三条，数据来源分开写清：
     · **防御建筑上限 / 滑索上限** —— **配置表** DB.bases.maxBases[].caps
       （battleBuildingLimit / travelPoleLimit），跟协议容量同一张表、同一套「按当前建造区取」的口径。
     · **存电** —— **社区实测**（DB.mining_power.power.generation.storageMax = 100000），配置表里没有这一项。
   ⚠️ 滑索架（travel_pole_1 / travel_pole_2 / travel_pole_nop_1）现在在 LO_SKIP_IDS 里
      —— 博士 2026-09-21 要求它不出现在试摆清单里，所以沙盘上一般摆不出滑索，这一项通常是 0。
      校验照样算：将来把它放回清单、或从别处带进来，这一行会立刻起作用（不写死 0）。 */
const RW_DEF_CAT='战斗辅助';
const RW_TRAVEL_IDS=['travel_pole_1','travel_pole_nop_1','travel_pole_2'];
function RlimitChecks(objs){
  const L=Linit();
  const list=objs||L.objs;
  const row=(((DB.bases||{}).maxBases)||[]).filter(r=>r.levelId===L.base)[0];
  const caps=(row&&row.caps)||null;
  let def=0, trav=0;
  list.forEach(o=>{
    const b=byBp(o.id); if(!b) return;
    if(b.categoryName===RW_DEF_CAT) def++;
    if(RW_TRAVEL_IDS.indexOf(o.id)>=0) trav++;
  });
  const defCap=caps?caps.battleBuildingLimit:null, travCap=caps?caps.travelPoleLimit:null;
  return {def:def, defCap:defCap, trav:trav, travCap:travCap, zone:row?row.zoneName:null,
          defOver:(defCap!=null&&def>defCap), travOver:(travCap!=null&&trav>travCap)};
}
/* 存电：协议核心自带 baseOutput（200）基础发电，**用电超过它的部分就是靠存电顶**。
   storageMax 是社区实测上限（10 万）。所以能给一个可算的结论：纯靠存电还能撑多久。
   ⚠️ 存电是「缓冲」不是「电源」—— 撑的时间只是让你有时间补发电，不能当长期方案。 */
function Rstorage(usePower){
  const gen=(((DB.mining_power||{}).power||{}).generation)||{};
  const base=+(gen.baseOutput||200), cap=+(gen.storageMax||0);
  const gap=Math.max(0, (+usePower||0)-base);
  return {base:base, cap:cap, gap:gap,
          minutes:(gap>0&&cap>0)?(Math.round(cap/gap*10)/10):0,
          source:'社区实测（非配置表）'};
}
/* 画布上摆了几台热能池（发电侧）—— 用来跟「需要几台」对一下 */
function RstationCount(objs){
  const list=objs||Linit().objs;
  return list.filter(o=>{ const b=byBp(o.id); return !!b&&b.id==='power_station_1'; }).length;
}
/* ========== 评价函数（路线图 ① · 2026-09-21 晚）==========
   为什么先做它：**没有分数，「这版比那版好」就是拍脑袋** ——
   后面的对齐、局部搜索、多方案枚举，全都要靠它择优。

   成本项（各 0~1，越高越好）—— 统一用「理论下界 ÷ 实测」这个比值：
     紧凑度  行数         下界 = Σ各层最高机器深 + (层数 − 1) × RW_CORR
     台数效率 设备台数      下界 = Σ 需求 ÷ 单台产能（实数，不含整台凑整）
     走线效率 物流格数      下界 = Σ 每段「上游机器 ↔ 下游机器」的曼哈顿距离
     集散效率 汇流/分流器数  下界 = 0（能一个不摆最好）
     料耗效率 产出富余      下界 = 0（整台凑整躲不掉，越少越好）

   约束罚分（都是硬指标，命中就扣）：
     原料超全图采集上限 −25 · 超防御建筑上限 −15 · 超滑索上限 −10
     （协议容量不在其列 —— 它只约束集成核心区域**外**的野外设备，基地内不受限，2026-09-24 撤）
     · 走线连不上，每条 −3 · 单线会堵，每条 −3

   ⚠️ 权重是**约定**，不是游戏真理。写成常量就是为了让排序口径固定、可复现、也可以调。
   ⚠️ 它拿的是**当前画布**（含你手动加的机器）算用电 / 容量 / 上限，不是生成那一刻的快照。 */
const RW_W={tight:0.20, machines:0.20, wire:0.30, hub:0.15, waste:0.15};
function Rscore(res, plan, route, rawNeed){
  const objs=Linit().objs;
  const clamp=x=>x<0?0:(x>1?1:x);
  const r2=x=>Math.round(x*100)/100;
  /* 1. 紧凑度 */
  const dmax={};
  (plan.objs||[]).forEach(o=>{ const d=o.node.depth; dmax[d]=Math.max(dmax[d]||0, o.d); });
  const dks=Object.keys(dmax);
  const hBest=dks.reduce((s,d)=>s+dmax[d],0)+Math.max(0,dks.length-1)*RW_CORR;
  const hNow=Math.max(1, plan.height||1);
  /* 2. 台数效率 */
  let mNow=0, mBest=0;
  (res.machines||[]).forEach(n=>{ mNow+=n.machines||0; mBest+=(n.perMachine>0?(n.demand/n.perMachine):0); });
  /* 3. 走线效率：每段上下游中心的最小曼哈顿距离之和 = 理论最短走线 */
  const byNode=new Map();
  (plan.objs||[]).forEach(o=>{ const a=byNode.get(o.node)||[]; a.push(o); byNode.set(o.node,a); });
  const ctr=o=>({x:o.x+o.w/2, y:o.y+o.d/2});
  let wBest=0, segs=0;
  (res.machines||[]).forEach(parent=>(parent.children||[]).forEach(child=>{
    if(!child.recipeId) return;
    const us=byNode.get(child)||[], ds=byNode.get(parent)||[];
    if(!us.length||!ds.length) return;
    let best=1e9;
    us.forEach(a=>ds.forEach(b=>{ const p=ctr(a), q=ctr(b);
      const d=Math.abs(p.x-q.x)+Math.abs(p.y-q.y); if(d<best) best=d; }));
    if(best<1e9){ wBest+=best; segs++; }
  }));
  const wNow=Math.max(0,(route.belts||[]).length);
  const hubN=(route.belts||[]).filter(b=>b.merge||b.split).length;
  let demand=0, out=0;
  (res.machines||[]).forEach(n=>{ demand+=n.demand||0; out+=n.actualOut||0; });
  /* 4. 约束量（硬指标） */
  const pw=Rpower(objs), bw=Rbandwidth(objs), th=Rtheories(pw.total, Lregion());
  const lim=RlimitChecks(objs), st=Rstorage(pw.total);
  const loads=route.loads||[];
  const jam=loads.filter(x=>x.state==='jam').length;
  const tightN=loads.filter(x=>x.state==='tight').length;
  const broke=(route.warns||[]).filter(x=>x.indexOf('手动连')>=0||x.indexOf('走线过不去')>=0).length;
  let rawUse=0, oreOver=0;
  Object.keys(rawNeed||{}).forEach(k=>{
    rawUse+=(rawNeed[k]||0);
    const c=RoreCapOf(k);
    if(c&&rawNeed[k]>c.hi) oreOver+=(rawNeed[k]-c.hi);
  });
  const parts=[
    {k:'紧凑度', w:RW_W.tight, now:hNow, best:r2(hBest), unit:'行', v:clamp(hBest/hNow)},
    {k:'台数效率', w:RW_W.machines, now:mNow, best:r2(mBest), unit:'台', v:clamp(mBest/Math.max(1,mNow))},
    {k:'走线效率', w:RW_W.wire, now:wNow, best:r2(wBest), unit:'格', v:clamp(wBest/Math.max(1,wNow))},
    {k:'集散效率', w:RW_W.hub, now:hubN, best:0, unit:'个', v:clamp(1-hubN/Math.max(1,mNow))},
    {k:'料耗效率', w:RW_W.waste, now:r2(out-demand), best:0, unit:'/分富余', v:clamp(out>0?(demand/out):1)},
  ];
  const pens=[];
  /* ⭐v145 撤项（2026-09-24 博士游戏内确认）：协议容量**只约束集成核心区域外的野外设备**
     （本页建筑详情与基地面积页都这么写），基地内不受限 → 不再对「超协议容量」扣分。
     原惩罚：超协议容量 −30。Rbandwidth 函数保留（将来野外排布要用）。 */
  if(oreOver>0) pens.push({t:'原料超全图采集上限 +'+r2(oreOver)+'/分', p:25});
  if(lim.defOver) pens.push({t:'防御建筑超上限 '+lim.def+'/'+lim.defCap, p:15});
  if(lim.travOver) pens.push({t:'滑索超上限 '+lim.trav+'/'+lim.travCap, p:10});
  if(broke) pens.push({t:'走线连不上 '+broke+' 条', p:3*broke});
  if(jam) pens.push({t:'单线会堵 '+jam+' 条', p:3*jam});
  let base=0; parts.forEach(x=>{ base+=x.w*x.v; });
  const raw100=Math.round(base*100);
  let pen=0; pens.forEach(x=>{ pen+=x.p; });
  const score=Math.max(0, raw100-pen);
  const feasible=!(bw.over||oreOver>0||lim.defOver||lim.travOver);
  return {
    score:score, raw:raw100, penalty:pen, feasible:feasible,
    grade:score>=85?'优':(score>=70?'良':(score>=55?'可用':'待改')),
    parts:parts, pens:pens,
    m:{rows:hNow, rowsBest:r2(hBest), machines:mNow, machinesBest:r2(mBest),
       belts:wNow, beltsBest:r2(wBest), segs:segs, hubs:hubN,
       cells:(plan.objs||[]).reduce((s,o)=>s+o.w*o.d,0), placed:objs.length,
       power:pw.total, bwUse:bw.use, bwCap:bw.cap, bwZone:bw.zone,
       rawUse:r2(rawUse), rawKinds:Object.keys(rawNeed||{}).length,
       storCap:st.cap, storGap:st.gap, storMin:st.minutes,
       thBase:th.base, thFuels:th.fuels, thStationNeed:(th.fuels.length?th.fuels[0].count:0),
       defN:lim.def, defCap:lim.defCap, travN:lim.trav, travCap:lim.travCap,
       jam:jam, tight:tightN, loads:loads},
  };
}
/* 分数条（只做视觉，颜色跟着分档走；不参与任何判定） */
function Rbar(v){
  const p=Math.max(0,Math.min(100,Math.round(v*100)));
  const col=p>=80?RW_COL.ok:(p>=60?RW_COL.mid:(p>=40?RW_COL.warn:RW_COL.bad));
  return '<span class="lo-bar-o"><span class="lo-bar-i" style="width:'+p+'%;background:'+col+'"></span></span>';
}
const RW_COL={ok:'#2E7D5B', mid:'#186C7D', warn:'#B8860B', bad:'#C0392B'};
/* 存当前方案（只存分数快照，不存布局 —— 布局要靠画布上的 objs 才还原得出来） */
function LsavePlan(){
  const L=Linit(), P=L.plan;
  if(!P||!L.objs.some(o=>o.planRole)){ L.msg='先生成一条产线，再存方案'; render(); return; }
  const sc=Rscore(P.res, P.plan, P.route, P.rawNeed||rawNeedOf(P.res));
  L.plans=L.plans||[];
  L.plans.push({name:P.res.targetName+' '+P.res.perMin+'/分', sc:sc});
  while(L.plans.length>5) L.plans.shift();
  L.msg='已存方案「'+P.res.targetName+' '+P.res.perMin+'/分」（第 '+L.plans.length+' 套，最多留 5 套）—— 改完参数再生成一条，分数会自动并排比';
  render();
}
function LdelPlan(i){ const L=Linit(); (L.plans||[]).splice(i,1); L.msg='已删掉第 '+(i+1)+' 套方案'; render(); }
function LclearPlans(){ const L=Linit(); const n=(L.plans||[]).length; L.plans=[]; L.msg='已清掉 '+n+' 套存下来的方案'; render(); }
/* 多方案并排比较（路线图 ① 的后半句）—— 同一套口径列在一起，谁分高一眼看得出 */
function planCompareHTML(){
  const L=Linit(), ps=L.plans||[];
  if(!ps.length) return '';
  const best=ps.reduce((a,b)=>((b.sc.score>a.sc.score)?b:a), ps[0]);
  const row=(lbl,fn)=>`<tr><td class="lo-td-h">${lbl}</td>${ps.map(p=>`<td>${fn(p)}</td>`).join('')}</tr>`;
  return `<div class="lo-cmp">
    <div class="lo-ph">📊 <b>方案并排比较</b> —— ${ps.length} 套（同一套口径；分高的一列加粗）
      <button class="lo-reset" onclick="LclearPlans()">清空</button></div>
    <table class="lo-tb">
      <tr><td class="lo-td-h">方案</td>${ps.map((p,i)=>`<td>${esc(p.name)}<button class="lo-x" onclick="LdelPlan(${i})" title="删掉这一套">×</button></td>`).join('')}</tr>
      ${row('总分', p=>`<b class="${p===best?'lo-best':''}">${p.sc.score}</b> / 100 ${p.sc.feasible?'':'<span style="color:'+RW_COL.bad+'">硬伤</span>'}`)}
      ${row('评价', p=>`<span class="${p===best?'lo-best':''}">${esc(p.sc.grade)}</span>（基础 ${p.sc.raw} − 罚 ${p.sc.penalty}）`)}
      ${row('行数 / 下界', p=>`${p.sc.m.rows} / ${p.sc.m.rowsBest}`)}
      ${row('机器台数', p=>`${p.sc.m.machines}（理想 ${p.sc.m.machinesBest}）`)}
      ${row('物流格数', p=>`${p.sc.m.belts}（下界 ${p.sc.m.beltsBest}）`)}
      ${row('汇流/分流器', p=>p.sc.m.hubs)}
      ${row('占用格数', p=>p.sc.m.cells)}
      ${row('用电', p=>p.sc.m.power)}
      ${/* ⭐v145 撤项：协议容量只约束集成核心区域外的野外设备，不约束基地内 → 方案比较表不再列此项 */''}
      ${row('原料消耗', p=>`${p.sc.m.rawUse}/分（${p.sc.m.rawKinds} 种）`)}
      ${row('会堵的段', p=>p.sc.m.jam?('<span style="color:'+RW_COL.bad+'">'+p.sc.m.jam+'</span>'):'0')}
      ${row('主要扣分', p=>(p.sc.pens.length?esc(p.sc.pens.map(x=>x.t).join('、')):'（无）'))}
    </table>
  </div>`;
}
/* 产线报告（① 评价函数 + ② 吞吐体检 + 第 1 层约束校验）—— 抽成函数，渲染层只管调用 */
/* ⭐C6「物品必须有去路」去路体检（2026-09-24 博士拍板「加」）—————————————————————————
   为什么要有它：游戏里物品有硬顶（社区口径「库存 50 + 在制 1」），某物品净产出 > 0 且没有去路时
   **必然**满仓（只是时间问题，不是概率问题）→ 满仓后在制格卡死 → 该机停机 →
   沿产线**反向逐级堵死** → 整条支线停产；而且会跨线连锁
   （社区实例：赤铜块爆仓 → 污水断供 → 电池线停转 → 断电 → 全基地停摆）。
   → 「最优排布」必须把「有没有去路」当**硬约束**：C1 管「产得够」，C6 管「排得出去」，
     没有 C6 则 C1 只在时间零点成立（详见 docs/最优排布-设计规格.md 的 C6）。
   ⚠️ 为什么必须**独立扫配方**、不能只看产线图：`Rexplode.build()` 只递归 `ingredients`，
      配方的**副产物根本不进产线图**（317 条配方里 84 条是双产出，其中 11 条产污水）——
      而漏掉的恰好是最致命的那些。副产物 = 没有下游的净产出，是爆仓第一来源。
   本函数**只读不写**：不改图结构 / 布局 / 路由 → 对既有回归锁零影响（C6-a 体检档）。 */
function RflowAudit(res){
  const r3=x=>Math.round(x*1000)/1000;
  const out={items:[], targets:[], ok:true};
  if(!res||!res.machines) return out;
  /* 主产物数量口径与 build()/RwPerMin 一致（别用 outcomes[0] 硬猜） */
  const ocOf=(r,iid)=>{ const o=(r.outcomes||[]).filter(x=>x.id===iid)[0]||(r.outcomes||[])[0]||{}; return o.count||1; };
  const made={}, used={};                     /* itemId -> {rate, by:[机器名], byp:有无副产物来源} */
  const add=(bag,id,rate,who,byp)=>{
    const e=bag[id]=bag[id]||{rate:0,by:[],byp:false};
    e.rate+=rate; if(byp) e.byp=true;
    if(who&&e.by.indexOf(who)<0) e.by.push(who);
  };
  res.machines.forEach(n=>{
    const r=RbyId(n.recipeId); if(!r||!(n.actualOut>0)) return;
    const oc=ocOf(r,n.itemId);
    (r.outcomes||[]).forEach(o=>{
      add(made, o.id, n.actualOut*(o.count/oc), n.machineName, o.id!==n.itemId);
    });
    const carriers=RwCarrierIds(r);
    (r.ingredients||[]).forEach(i=>{
      /* 载体（原料 id 也出现在产物里）净消耗 0 → 不是去路，别拿它抵账（拆解机的罐子/瓶子就是这种） */
      if(carriers.indexOf(i.id)>=0) return;
      add(used, i.id, n.actualOut*(i.count/oc), n.machineName, false);
    });
  });
  const tgs={};
  (((res.targets&&res.targets.length)?res.targets:[{id:res.target}])||[]).forEach(t=>{ if(t&&t.id) tgs[t.id]=1; });
  Object.keys(made).forEach(id=>{
    const m=made[id];
    const o=r3(m.rate), u=r3((used[id]||{}).rate||0), ov=r3(o-u);
    if(ov<=1e-6) return;                      /* 产出的都被下游吃掉了 → 有去路 */
    const nm=RwItemName(id);
    const row={id:id, name:nm, out:o, used:u, over:ov, by:m.by,
               consumers:((used[id]||{}).by)||[], fromByproduct:!!m.byp,
               isTarget:!!tgs[id], isBattery:/电池/.test(nm)};
    if(row.isTarget) out.targets.push(row);   /* 目标产物：靠卖货/收走，单列不算必爆 */
    else { out.items.push(row); out.ok=false; }
  });
  out.items.sort((a,b)=>b.over-a.over);
  out.targets.sort((a,b)=>b.over-a.over);
  return out;
}
/* ⭐⭐ C6-b 阶段 2（2026-09-25，博士拍板「有现成消费者就接、否则销毁 + 软门禁」）：
   **把每个「无去路」物品接上去路** —— 这是 C6 从「体检」升级为「门禁」的那一步。

   【为什么必须是门禁，不能是扣分项】（博士 2026-09-24 晚定的红线）
   C6 若做成扣分项 → 排布器会在「补 sink」与「选更贵的无副产物配方」之间权衡，
   而 sink 成本（用电/占地/线长）**照常计入不豁免**（规格 §2.2）→ 账本才不骗自己。
   做成门禁 = 生成阶段就要求每个物品都有去路，产不出「第一天能跑、第三天停产」的方案。

   【去路优先级】（博士 2026-09-25 拍板）
     ① 图里已有机器吃它（且吃得完）→ 不需要 sink（RflowAudit 已按 used 扣掉）
     ② 图里有机器吃它但**吃不掉全部** → 剩余部分走 ③（溢流销毁）
     ③ 电池 → 热能池 power_station_1（唯一「销毁即发电」）
     ④ 其余 → 扩容反应池 mix_pool_2 + 2 条垫子配方（芽针饮品/锦草饮品）

   【池数口径】`ceil(净溢出 / 30)`：社区口径单池约 30/分（待游戏内核实）。
     实测重息壤要 12 个池子 —— **一个池子远远不够**，必须按量算。
     ⚠️ 池子数量直接影响用电评分（扩容池 100 电/个）→ 装了池子的方案在用电层变差，
        这是**有意为之的真实成本**（规格 §2.2）。

   【为什么「销毁线是旁路」让这件事可行】
   多口暗管输出优先：机器有多个出口时走**负载较轻**的那条。出口 a 直连主路、出口 b 接池子
   → 主路没满走 a，主路满了自动溢到 b。所以排布器**不需要拉一条常供线**给池子，
   只要把池子摆好 + 垫子接好，游戏侧自己会溢流。
   ⚠️ 但**旁路线仍要铺**（博士 2026-09-25 选「摆池子+垫子+连旁路」）——
      因为它告诉玩家「从哪台机器引过来」，否则玩家不知道该接谁。

   【软门禁口径】（博士 2026-09-25 拍板）
   补不上（建筑不存在 / 总池数超上限）→ **拒绝出方案 + 明确报原因**，不静默作废。
   ⚠️ 池子自身是故障点（社区多次报告会无声卡死）→ 报告必须如实告知，不假装万无一失。

   本函数**纯函数只读**：不改 res，只返回规划结果，由 LawRun 决定怎么落盘。 */
const RW_SINK_POOL_CAP=30;        /* 单池销毁速率上限（/分，社区口径） */
const RW_SINK_MAX_POOLS=16;       /* 单条产线最多自动摆的池数（防病态方案把画布铺满） */
const RW_SINK_POOL_ID='mix_pool_2';   /* 扩容反应池（唯一能塞多条并行配方的池子） */
const RW_SINK_HEAT_ID='power_station_1';  /* 热能池（烧电池） */
/* ⭐ 微量溢出阈值（博士 2026-09-25 拍板）：净溢出 ≤ 该值 → **只提醒不拦截**。
   为什么需要：机器必须**整台**摆，于是「产 15 / 用 10」这种取整差普遍存在。
   实测 102 个可排目标里 47 个有净溢出，其中 50 项 ≤20/分 —— 大多是取整噪声，
   若无阈值则几乎所有链都要挂池子，方案会明显变重、且与玩家的实际体验不符
   （玩家会调速率或让那台机器吃不饱，而不是真去销毁 5/分）。
   ⚠️ 阈值不是忽略：≤阈值的项仍进 `minor` 并在报告里如实列出（博士要求「只提醒」）。 */
const RW_SINK_MINOR=5;
/* 垫子配方：故意接 2 条**不接输出**的配方让其永久堵塞 → 池内 ≥2 条不同配方
   同时堵塞才触发清空（单条堵着什么都不做）。
   ⚠️ **不做硬编码**：垫子的具体选型依赖玩家手上的原料，且「接配方」是游戏内设置池子反应、
      不是摆建筑 —— 排布器硬编码一批配方 id 会引入无法自证的假设。
      这里只给**判定条件**与**选型原则**，报告里如实说明；具体选哪两条由玩家定。
   社区做法示例（数据手册已收录）：芽针饮品 / 锦草饮品这类低成本配方。 */
const RW_SINK_PAD_RULE='需 2 条**不同且不接输出**的配方常驻池内（低成本、原料易得为宜，社区常用芽针/锦草饮品）';
function RflowSinkPlan(res){
  const r3=x=>Math.round(x*1000)/1000;
  const audit=RflowAudit(res);
  const out={sinks:[], padRule:RW_SINK_PAD_RULE, reasons:[], minor:[], unmet:[], poolTotal:0, heatTotal:0, ok:true};
  if(!audit.items.length){ out.note='每个物品都有去路，不需要销毁支线'; return out; }
  /* 逐项定去路 —— audit.items 已排除「目标产物」与「被下游吃光」的物品 */
  audit.items.forEach(it=>{
    const nm=it.name, over=r3(it.over);
    /* ⭐ 微量溢出（≤阈值）：只提醒不拦截 —— 多半是整台取整噪声，不值得为它挂一个池子 */
    if(over<=RW_SINK_MINOR){
      out.minor.push({item:nm, itemId:it.id, over:over, fromByproduct:!!it.fromByproduct,
        why:'微量净溢出（≤'+RW_SINK_MINOR+'/分），多半是机器整台取整造成的 —— 只提醒，不强制销毁'
          +'（游戏里可微调速率或让它自然积在缓冲里）'});
      return;
    }
    if(it.isBattery){
      /* ② 电池 → 热能池 */
      if(!byBp(RW_SINK_HEAT_ID)){
        out.unmet.push({item:nm, over:over, why:'建筑表里找不到热能池（'+RW_SINK_HEAT_ID+'）'});
        return;
      }
      const n=Math.max(1, Math.ceil(over/60));   /* 热能池按台数烧（无明确速率口径，按 1 台起步） */
      out.sinks.push({buildingId:RW_SINK_HEAT_ID, name:'热能池', count:n, kind:'heat',
        forItem:nm, itemId:it.id, over:over,
        why:'电池可以溢流烧进热能池 —— 唯一「销毁即发电」的去路'});
      out.heatTotal+=n;
      out.reasons.push(nm+' '+over+'/分 → 热能池 ×'+n+'（销毁即发电，不浪费）');
      return;
    }
    /* ③ 其余 → 扩容反应池 */
    if(!byBp(RW_SINK_POOL_ID)){
      out.unmet.push({item:nm, over:over, why:'建筑表里找不到扩容反应池（'+RW_SINK_POOL_ID+'）'});
      return;
    }
    const n=Math.max(1, Math.ceil(over/RW_SINK_POOL_CAP));
    out.sinks.push({buildingId:RW_SINK_POOL_ID, name:'扩容反应池', count:n, kind:'pool',
      forItem:nm, itemId:it.id, over:over,
      why:'溢流进扩容反应池销毁（需 2 条配方同时堵塞才触发清空 → 常驻 2 条垫子配方）'});
    out.poolTotal+=n;
    out.reasons.push(nm+' '+over+'/分 → 扩容反应池 ×'+n
      +'（'+RW_SINK_POOL_CAP+'/分×'+n+' 覆盖）'
      +(it.fromByproduct?'　⭐配方副产物，不接销毁线会一直堆':''));
  });
  /* 池数上限：超了就走软门禁（不硬塞，免得把画布铺满还假装成功） */
  if(out.poolTotal>RW_SINK_MAX_POOLS){
    out.unmet.push({item:'（合计）', over:null,
      why:'需要的销毁池合计 '+out.poolTotal+' 个，超过上限 '+RW_SINK_MAX_POOLS
        +' —— 这条链的副产物量太大，建议降速或分批建'});
  }
  out.ok=!out.unmet.length;
  return out;
}
/* C6-b 阶段 2 的门禁判定（LawRun 用）：返回 null = 放行；返回字符串 = 拒绝原因（软门禁） */
function RflowSinkGate(res){
  const sp=RflowSinkPlan(res);
  if(sp.ok) return null;
  return '这条产线有物品没有去路，且自动补销毁支线补不上：'
    +sp.unmet.map(u=>u.item+(u.over!=null?('（'+u.over+'/分）'):'')+' —— '+u.why).join('；')
    +'。C6 要求每个物品都有去路，所以先不生成 —— 先降速、换上游目标，或手动补一条销毁线。';
}
/* C6 体检的报告区块（渲染与判定分开：判定是纯函数，好写回归锁） */
function RflowAuditHtml(P){
  const r1=x=>Math.round(x*10)/10;
  const A=RflowAudit(P.res);
  const SP=(P&&P.sinkPlan)||RflowSinkPlan(P.res);   /* 阶段 2：用已算好的 sink 规划（没有就现算） */
  const bad=RW_COL.bad, okc=RW_COL.ok, warn=RW_COL.warn;
  const hard=A.items.filter(r=>r.over>RW_SINK_MINOR);   /* 需要真去路的 */
  const soft=A.items.filter(r=>r.over<=RW_SINK_MINOR);  /* 微量溢出，只提醒 */
  const n=hard.length;
  let h='<div class="c-sub" style="margin-top:8px"><span><b>♻️ 去路体检（C6）</b> '
      +'<span class="lo-tag">爆仓销毁 · 2026-09-24 加 · C6-b 门禁 2026-09-25</span> ';
  h+= n ? ('<b style="color:'+okc+'">'+n+' 项净产出没有下游'
          +(SP.sinks.length?' —— 已自动补销毁支线 ✓':'')+'</b>')
        : ('<b style="color:'+okc+'">每个物品都有去路 ✓ 不会爆仓停产</b>');
  if(soft.length) h+='　<span class="c-id">另有 '+soft.length+' 项微量溢出（≤'+RW_SINK_MINOR+'/分，取整噪声）—— 只提醒</span>';
  h+='</span></div>';
  /* ⭐ 阶段 2 新增：销毁支线方案（摆了什么、为什么、⚠️ 池子会无声卡死） */
  if(SP.sinks.length){
    h+='<div class="c-sub" style="margin-top:4px"><span><b style="color:'+okc+'">♻️ 销毁支线已自动补上</b>'
      +'（'+SP.sinks.reduce((s,x)=>s+x.count,0)+' 座建筑，已在画布上标出）</span></div>';
    SP.reasons.forEach(r=>{
      h+='<div class="c-sub" style="margin-top:2px"><span>· '+esc(r)+'</span></div>'; });
    h+='<div class="c-sub" style="margin-top:2px"><span class="c-id">垫子配方：'+esc(SP.padRule)
      +'。（接法是游戏内给池子设反应，排布器只摆池子。）</span></div>';
    h+='<div class="c-sub" style="margin-top:2px"><span style="color:'+warn+'">⚠️ <b>池子本身是故障点</b>：'
      +'社区多次报告扩容反应池会因交叉反应判定而<b>无声卡死</b>（入料满却不出货），需重摆 + 重设输出才恢复。'
      +'不能把它当绝对可靠的安全阀 —— 上线后记得抽查。</span></div>';
    h+='<div class="c-sub" style="margin-top:2px"><span class="c-id">成本口径：销毁支线的<b>用电 / 占地 / 线长'
      +'一律照常计入，不豁免</b>（扩容池 100 电/座）—— 装了池子的方案在用电层会因此变差，这是<b>有意为之的真实成本</b>。</span></div>';
  }
  hard.forEach(r=>{
    const way = r.isBattery
      ? '去路：<b>溢流进热能池烧掉</b> —— 唯一「不浪费」的路子（销毁的同时发电）'
      : '去路：<b>溢流进扩容反应池</b>销毁（注意：需 <b>2 条配方同时堵塞</b>才触发清空，'
        +'单条堵着它什么都不做 → 得常驻 2 条「垫子」配方）';
    const cap = (!r.isBattery && r.over>30)
      ? ('　<b style="color:'+bad+'">'+r1(r.over)+'/分 &gt; 社区口径单池约 30/分，一个池子吃不下 —— 要么并几个，要么从源头减量</b>')
      : '';
    h+='<div class="c-sub" style="margin-top:2px"><span>· <b>'+esc(r.name)+'</b> 净溢出 '
      +'<b style="color:'+bad+'">'+r1(r.over)+'/分</b>'
      +'<span class="c-id">（产出 '+r1(r.out)+' − 下游用掉 '+r1(r.used)+'）</span>'
      +(r.by.length?('　来源：'+esc(r.by.join('、'))):'')
      +(r.fromByproduct?'　<span class="c-id">配方副产物 —— 不接销毁线就会一直堆</span>':'')
      +'<br>　　'+way+cap+'</span></div>';
  });
  soft.forEach(r=>{
    h+='<div class="c-sub" style="margin-top:2px"><span class="c-id">· '+esc(r.name)+' 微量净溢出 '
      +r1(r.over)+'/分（≤'+RW_SINK_MINOR+'，取整噪声）—— 未强制补销毁，可微调速率或让它积在缓冲里</span></div>';
  });
  A.targets.forEach(r=>{
    h+='<div class="c-sub" style="margin-top:2px"><span>· <b>'+esc(r.name)+'</b> 产出 '+r1(r.out)+'/分 '
      +'<span class="c-id">（这是你要的目标产物，没有下游 —— 靠<b>卖货到据点</b>或手动取走；'
      +'放着不管一样会满仓，但这是预期行为，不算必爆项）</span></span></div>';
  });
  h+='<div class="c-sub" style="margin-top:2px"><span class="c-id">判定口径：'
    +'对每个物品算「实际产出 − 下游需求」，净溢出 &gt; '+RW_SINK_MINOR+'/分 就是必爆项（≤ 该值的只提醒）。'
    +'<b>副产物是这里的主要检出对象</b> —— 317 条配方里 84 条是双产出（其中 11 条产污水），'
    +'本体检扫<b>每台机器所选配方的全部产出</b>。'
    +'⭐ <b>C6-b 起副产物已正式入图</b>（<code>res.byproducts</code>），排布器看得见、也会补去路了。'
    +'⚠️ <b>协议储存箱不是去路</b>（只缓冲不销毁，自己满了后面照样堵）；'
    +'PAC 离线 7 天关物流是逃生阀，也不是去路。'
    +'机制出处：<code>docs/数据手册-玩法与物流.md</code>「♻️ 爆仓与物品销毁」节。</span></div>';
  h+='<div class="c-sub" style="margin-top:2px"><span class="c-id">'
    +'<b>C6 是门禁不是扣分项</b>：补不上销毁支线的方案会被<b>拒绝生成并报原因</b>，'
    +'不会产出一个「第一天能跑、第三天停产」的布局。</span></div>';
  return h;
}
function Rreport(P, pw, bw, th, lim, st, rawNeed, sc){
  const r1=x=>Math.round(x*10)/10;
  const wAll=P.res.warns.concat(P.route.warns);
  const loads=P.route.loads||[];
  /* ⭐v143 P3 准入口限速联动（博士 2026-09-24：「看看这对排布器计算有什么影响」）：
     线上装了准入口且设了限速 → 该段上限 = min(线速, 限速)，原 cap 判定会**低估堵塞**。
     实现：扫描画布上的准入口（x,y → 限速），按格匹配每条依赖的路径，
     命中就**就地修正**该条 loads 的 cap/state，并在报告里点名。每次渲染重算（准入口随时可加可改）。 */
  const _valves={};
  (Linit().objs||[]).forEach(o=>{ const b=byBp(o.id);
    if(b&&(b.lgType==='BoxValve'||b.lgType==='FluidValve')&&+o.vRate>0) _valves[o.x+','+o.y]=+o.vRate; });
  const _vNotes=[];
  if(Object.keys(_valves).length && P.route.links){
    P.route.links.forEach(lk=>{
      if(!lk.path||!lk.path.length) return;
      let v=null;
      lk.path.forEach(k=>{ if(_valves[k]!=null) v=(v==null)?_valves[k]:Math.min(v,_valves[k]); });
      if(v==null) return;
      const ld=(loads||[]).find(x=>x.item===lk.item&&x.from===lk.from&&x.to===lk.to&&x.isPipe===lk.isPipe);
      if(!ld||ld.cap<=v) return;
      ld.cap=v; ld.valveLimited=v;
      ld.state=(!ld.lines?'none':(ld.per>v+1e-6?'jam':(ld.per>v*0.9?'tight':'ok')));
      _vNotes.push(esc(lk.item)+'（'+esc(lk.from)+' → '+esc(lk.to)+'）被准入口限到 <b>'+v+'/分</b>'
        +(ld.state==='jam'?' —— <b style="color:'+RW_COL.bad+'">这条线会堵（负荷 '+_r1(ld.per)+'/分 超上限）</b>'
          :(ld.state==='tight'?' —— 接近上限':'')));
    });
  }
  const valveLine=_vNotes.length?`
      <div class="c-sub" style="margin-top:2px"><span><b>准入口限速</b> <span class="lo-tag">v143 · 计算联动</span>：${_vNotes.join('；')}</span></div>`:'';
  const jam=loads.filter(x=>x.state==='jam').length;
  const tight=loads.filter(x=>x.state==='tight').length;
  const stations=RstationCount(Linit().objs);
  const lstate={'jam':'<b style="color:'+RW_COL.bad+'">会堵</b>', 'tight':'<b style="color:'+RW_COL.warn+'">紧</b>',
                'ok':'<b style="color:'+RW_COL.ok+'">通畅</b>', 'none':'<b style="color:'+RW_COL.bad+'">没连上</b>'};
  /* ⭐v136（对标调研 A 项）台数口径：理论分数台数（需求 ÷ 单台产能，求和）→ 实际整台（ceil）
     → 多出来的部分主要来自哪几台。以前只给总数，玩家看不出「为什么凭空多一台」。 */
  const _mach=P.res.machines||[];
  const _frac=_mach.reduce((s2,n)=>s2+((n.perMachine>0)?(n.demand/n.perMachine):0),0);
  const _ceil=_mach.reduce((s2,n)=>s2+(n.machines||0),0);
  const _over=_mach.map(n=>({n:n, ex:(n.perMachine>0)?(n.machines-n.demand/n.perMachine):0}))
                   .filter(x=>x.ex>1e-9).sort((a,b)=>b.ex-a.ex);
  const _r1=x=>Math.round(x*10)/10;
  const machLine=`
      <div class="c-sub" style="margin-top:2px"><span><b>台数口径</b> <span class="lo-tag">v136</span>：理论 <b>${_r1(_frac)}</b> 台（各台需求 ÷ 单台产能，求和）→ 实际摆 <b>${_ceil}</b> 台${_over.length?(` —— 取整多 <b>${_r1(_ceil-_frac)}</b> 台，主要在：${_over.slice(0,4).map(x=>esc(x.n.name)+'+'+_r1(x.ex)).join('、')}${_over.length>4?(' 等 '+_over.length+' 台'):''}`):' —— 没有取整损耗'}
        <span class="c-id">　（机器只能整台摆：需求 1.2 台 = 摆 2 台，多出的产能就是余量；同池并行省下的栋数见上一行）</span></span></div>`;
  return `
      <div class="c-sub" style="margin-top:6px">
        <span>${P.res.targets
          ?('目标 '+P.res.targets.map(t=>'<b>'+esc(t.name)+'</b> '+t.perMin+'/分').join(' ＋ '))
          :('目标 <b>'+esc(P.res.targetName)+'</b> '+P.res.perMin+'/分')} · 机器 <b>${P.res.totalMachines}</b> 台（${P.res.machines.length} 种）· 管线 <b>${P.route.belts.length}</b> 格 · 占 <b>${P.plan.height}</b> 行</span>
      </div>${machLine}${valveLine}
      ${P.res.poolMerge?`
      <div class="c-sub" style="margin-top:2px"><span><b>扩容反应池同池并行</b> <span class="lo-tag">v133 · 官方文案+实机核实</span>：${P.res.poolMerge.map(g=>'一栋跑 <b>'+g.members.length+'</b> 条反应（'+g.members.map(esc).join('、')+'）· 占 '+g.slots+'/'+RW_POOL_SLOTS+' 格'+(g.saved?('，比一条一栋省 <b>'+g.saved+'</b> 栋'):'')).join('；')}　<span class="c-id">同池并行不提速：每条反应各跑各的额定速度</span></span></div>`:''}
      ${sc?`
      <div class="lo-score">
        <div class="lo-ph">🧮 <b>评价函数</b> <span class="lo-tag">路线图 ① · 2026-09-21</span> —— 这一版布局的分数</div>
        <div class="lo-scv">
          <span class="lo-scn">${sc.score}</span><span class="lo-scs">/ 100 · ${esc(sc.grade)}</span>
          <span class="lo-tag">基础 ${sc.raw} − 罚分 ${sc.penalty}</span>
          ${sc.feasible?'<span class="lo-tag">约束全过 ✓</span>':('<span class="lo-tag" style="color:'+RW_COL.bad+'">有硬伤</span>')}
        </div>
        <table class="lo-tb">
          <tr><td class="lo-td-h">分项（权重）</td><td class="lo-td-h">实测</td><td class="lo-td-h">理论下界</td><td class="lo-td-h">得分</td></tr>
          ${sc.parts.map(x=>`<tr><td class="lo-td-h">${x.k}（${Math.round(x.w*100)}%）</td><td>${x.now}${x.unit}</td><td>${x.best}${x.unit}</td><td>${Math.round(x.v*100)}${Rbar(x.v)}</td></tr>`).join('')}
        </table>
        ${sc.pens.length?`<div class="c-sub" style="margin-top:4px"><span><b style="color:${RW_COL.bad}">扣分项</b>：${sc.pens.map(x=>esc(x.t)+'（−'+x.p+'）').join(' · ')}</span></div>`
          :'<div class="c-sub" style="margin-top:4px"><span class="c-id">没有命中任何罚分项。</span></div>'}
        <div class="c-sub" style="margin-top:2px"><span class="c-id">口径：成本项一律用「理论下界 ÷ 实测」（下界见上表）；权重写成常量 RW_W，可调；用电 / 协议容量 / 上限按<b>当前画布</b>算。</span></div>
      </div>`:''}
      <div class="c-sub" style="margin-top:4px"><span><b>原料</b>（基地不摆，从野外采集 / 仓库来）：${P.res.raw.length?P.res.raw.map(x=>{
        if((P.res.shipIn||[]).some(s=>s.itemId===x)) return esc(RwItemName(x))+'（<b>跨地区收货</b>，见下）';
        const mr=RmineRate(x);
        if(!mr) return esc(RwItemName(x));
        return esc(RwItemName(x))+'（'+esc(mr.name)+(mr.perMin!=null?(mr.perMin+'/分'+(mr.fluid?'，前提是节点抽得到':'')):'：<b>速率配置表里没有</b>')+'）';
      }).join('、'):'（无）'}</span></div>
      ${(P.res.shared&&P.res.shared.length)?`
      <div class="c-sub" style="margin-top:6px"><span><b style="color:#185FA5">共用中间料 —— 只建一套，再分流给各目标</b> <span class="lo-tag">路线图 ⑥-2 · 2026-09-22</span></span></div>
      ${P.res.shared.map(s=>`
      <div class="c-sub" style="margin-top:2px"><span>${esc(s.name)}：<b>${s.machines}</b> 台（合并需求 ${s.demand}/分 · 按整台实出 ${s.actualOut}/分）→ ${Object.keys(s.sharedTo).map(k=>esc(k)+' '+Math.round(s.sharedTo[k]*1000)/1000+'/分').join('、')}</span></div>`).join('')}
      `:''}
      ${(function(){
        /* ⭐v104 环境依赖透明化（博士 2026-09-23「气体环境会影响生产，会不会影响最优计算」）：
           排布器的配方选择按子树代价排序，**天然选中省料的环境版配方**（实测息壤粉链/富集气链全中）——
           即产线从第一天起就隐式依赖环境，但不摆散布机这些机器在游戏里不工作，方案静默失效。
           这里扫实际选中的配方把它点名。数据 DB.recipeEnv（build 注入层从 FactoryMachineCraftTable.gasEnv 补）。 */
        const envDefs={
          1:{n:'稳定', g:'惰气', c:envColorOf(1)},
          2:{n:'湿润', g:'水蒸气', c:envColorOf(2)},
          3:{n:'酸性', g:'酸气', c:envColorOf(3)},
          4:{n:'息壤', g:'息壤气', c:envColorOf(4)}};
        const byEnv={};
        (P.res.nodes||[]).forEach(nd=>{
          const ge=nd.recipeId&&(DB.recipeEnv||{})[nd.recipeId];
          if(!ge) return;
          const d=envDefs[ge]||{n:'环境'+ge, g:'', c:'#B4B2A9'};
          const key=ge+'|'+nd.recipeId;
          (byEnv[key]=byEnv[key]||{ge:ge, env:d, recipeId:nd.recipeId, recipe:RbyId(nd.recipeId), machines:0});
          byEnv[key].machines+=nd.machines;
        });
        const rows=Object.keys(byEnv).map(k=>byEnv[k]);
        if(!rows.length) return '';
        const uniqEnv=[...new Set(rows.map(r=>r.ge))];
        return `<div class="c-sub" style="margin-top:6px"><span><b style="color:#1B6E9E">💨 环境依赖 —— 这些机器要摆进气体散布机的环境圈才会开工</b> <span class="lo-tag">v104 · 2026-09-23</span></span></div>
        ${rows.map(r=>`<div class="c-sub" style="margin-top:2px"><span>· <i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${r.env.c};border:1px solid ${envEdgeOf(r.ge)};vertical-align:-1px"></i> <b>${esc(r.recipe?(r.recipe.machineName||''):'')}</b> ×<b>${r.machines}</b> 台 —— 配方「${esc(r.recipe?(r.recipe.outcomes||[]).map(x=>x.name).join('+'):'')}」需要 <b>${esc(r.env.n)}环境</b>（通${esc(r.env.g)}，最低 6 单位/分）</span></div>`).join('')}
        <div class="c-sub" style="margin-top:2px"><span class="c-id">口径：这些配方按「有环境」的<b>省料版</b>算（这是排布器一直以来的最优口径${uniqEnv.indexOf(1)>=0?'，本链涉及稳定环境':''}）—— 机器<b>完全处于</b>散布机 13×13 圈内才生效，一台的圈可罩多台；散布机免电。没摆散布机时这些机器不会开工（提纯机/洪炉可在游戏里换回费料的普通配方顶替，但料与台数会变，报告不再准确）。</span></div>`;
      })()}
      ${(Linit().shipIn&&(Linit().shipCands||[]).length)?`
      <div class="c-sub" style="margin-top:6px"><span><b style="color:#185FA5">跨地区收货 —— 这批料不在本地做，从「${esc(LshipFromName())}」超库存传输过来</b> <span class="lo-tag">路线图 ⑥-1 · 2026-09-22</span></span></div>
      ${(P.res.shipIn||[]).map(s=>{
        const v=RshipVal(s.itemId), d=r1(s.demand);
        const sup=v.perBatch!=null
          ? (' → 每小时可传 <b>'+v.perHour+'</b> 个（每批 '+v.perBatch+' 个 · '+v.hours+' 小时/批）'
             // 传输是有速率上限的，所以它也可能喂不饱这条链 —— 这里必须点出来，别让人以为"收货=无限"
             +(v.perMin!=null&&v.perMin<d?('　<b style="color:'+RW_COL.warn+'">按每小时折算 '+v.perHour+' 个 &lt; 需求 '+Math.round(d*60)+' 个，收货喂不饱这条链 —— 得拉高档位或多配几条别的来源</b>'):''))
          : '　<span class="c-id">还没填传输总值 → 把下面那个框里的数填上，这里才给得出每小时可传多少（不填就不瞎编数字）</span>';
        return `<div class="c-sub" style="margin-top:2px"><span>· <b>${esc(s.name)}</b> 需要 <b>${d}</b>/分 · 单位物品价值 <b>${v.value}</b> · 每批间隔 <b>${v.hours}</b> 小时${sup}</span></div>`;
      }).join('')}
      ${/* ⭐v82：选中了链外的物品 —— 这条链的收货明细一行都没有，必须讲清楚「货只进仓库、产线不变」，
             不然博士会以为收货开关没生效。 */
        (Linit().shipPick && !(P.res.shipIn||[]).some(s=>s.itemId===Linit().shipPick))?`
      <div class="c-sub" style="margin-top:4px"><span style="color:${RW_COL.warn}">选中的「<b>${esc(RwItemName(Linit().shipPick))}</b>」<b>不在这条产线的链上</b> —— 传过来的货<b>只进仓库</b>，这条链没有任何地方用它（产线与机器都不变）。要它参与生产就改选链上的物品，或把排产目标换成用它做原料的东西。</span></div>`:''}
      ${/* ⭐⑥-1 v80 起网格替掉原生 select（博士：「像游戏里那样给我个传输物品的选择器」）；v81 收口到共享渲染
             LpickGridHtml(false)——报告与产线面板的选货条长一个样，候选/需求数字也同源（L.shipCands/L.shipDmap）。 */
        LpickGridHtml(false)}
      <div class="c-sub" style="margin-top:2px"><span class="c-id">口径：超库存传输**不扣${esc(LshipFromName())}的库存**（那边只要有产能就永远给得出来），唯一的闸门是每批的<b>传输总值</b> —— 一批<b>只能传一种物品</b>，数量上限 = 传输总值 ÷ 单位物品价值（物品表 <code>value</code>）。每批要等一个传输间隔到货，到货后出发地会再取一次货。</span></div>
      <div class="c-sub" style="margin-top:2px"><span class="c-id">⚠️ 这里给的是<b>按档位反推</b>的参考值：把你在协议管理界面看到的<b>传输总值</b>填进下面的框，数量与供货速率会按你的实际档位重算。实机档位参考（社区实测，配置表里没有）：谷地建设 <b>11 级 = 1200</b>、<b>12 级满级 = 1500</b> —— 另注意：从 11 级升到 12 级后协议<b>不会自动</b>从「库存传输」切成「超库存传输」，要手动改一次。本工具按<b>满级口径</b>：开收货时自动按 1500 预填（框里可改）。</span></div>
      ${LshipDirHtml()}
      <div class="lo-bar" style="margin-top:6px"><span>传输总值（你界面上的数）：</span><input class="lo-num" type="number" min="0" step="1" value="${(Linit().tv)||''}" placeholder="满级 1500（开收货时自动预填）" oninput="Ltv(this.value)"><span>每批间隔（小时）：</span><input class="lo-num" type="number" min="0.1" step="0.1" value="${Linit().tvHours||1}" oninput="LtvH(this.value)"></div>`:''}
      ${P.res.externals.length?`<div class="c-sub" style="margin-top:4px"><span><b>按「外部输入」处理</b>（${P.res.externals.map(x=>esc(RwItemName(x))).join('、')}）—— 这些自己做的代价太深或只有回收路线，<b>建议外部供应 / 野外采集</b>；要展开就调大上限或换个目标物品</span></div>`:''}
      ${/* ⭐⑥-3 跨基地选点（2026-09-22）：多个目标放哪片地区更省 —— 报告里常驻一段（不依赖收货开关） */
        RxlHtml()}
      ${P.res.seeds.length?`
      <div class="c-sub" style="margin-top:6px"><span><b style="color:#8A5A2B">启动料 —— 链上有环，先把这些塞进去才转得起来</b></span></div>
      ${P.res.seeds.map(s=>`<div class="c-sub" style="margin-top:2px"><span>· 在「<b>${esc(s.machineName)}</b>」里先塞 <b>${s.count}</b> 个「<b>${esc(s.name)}</b>」（${esc(s.reason)}）</span></div>`).join('')}`:''}
      ${P.route.links.length?`
      <div class="c-sub" style="margin-top:6px"><span><b>已连管线</b> ${P.route.links.length} 条</span></div>
      ${P.route.links.map(k=>`<div class="c-sub" style="margin-top:2px"><span>· ${esc(k.item)} ${k.perMin}/分：${esc(k.from)} → ${esc(k.to)} · ${k.isPipe?'管道':'传送带'} ${k.cells} 格</span></div>`).join('')}`:''}
      ${/* ⭐v153 报告层：外部暗管接入清单（feeds + feedFail = 应铺总数，不静默丢）。
           feeds[].edge 是**换格/换端口重试后的最终接入点**（走线循环里同步更新）；
           feedFail 的 why：port=没空闲管口 / edge=边缘没空格 / path=走线过不去（带坐标）。 */
        ''}
      ${(P.route.feeds&&P.route.feeds.length)?`
      <div class="c-sub" style="margin-top:6px"><span><b>外部暗管接入</b> <span class="lo-tag">v151/v154 · 直连或暗管对</span> —— ${P.route.feeds.length} 根进管，暗管在画布外接这些点</span></div>
      ${P.route.feeds.map(f=>`<div class="c-sub" style="margin-top:2px"><span>· ${esc(f.item)} <b>${f.need}</b>/分 → ${esc(f.machineName)} · ${RfeedModeTxt(f)}</span></div>`).join('')}`:''}
      ${(P.route.feedFail&&P.route.feedFail.length)?`
      <div class="c-sub" style="margin-top:4px"><span><b style="color:${RW_COL.warn}">没铺成的外部接入 ${P.route.feedFail.length} 条</b> —— 画布内这一段自己拉管接上（按下面坐标）</span></div>
      ${P.route.feedFail.map(f=>`<div class="c-sub" style="margin-top:2px"><span>· ${esc(f.item)} → ${esc(f.to)}：${RfeedWhyTxt(f)}</span></div>`).join('')}`:''}
      ${loads.length?`
      <div class="c-sub" style="margin-top:6px"><span><b>吞吐体检</b> <span class="lo-tag">路线图 ②a · 真并联</span> —— 每条依赖要几条线 / 实际连了几条 / 单线负荷${jam?('　<b style="color:'+RW_COL.bad+'">'+jam+' 段会堵</b>'):''}${tight?('　<b style="color:'+RW_COL.warn+'">'+tight+' 段没余量</b>'):''}</span></div>
      ${loads.map(k=>`<div class="c-sub" style="margin-top:2px"><span>· ${esc(k.item)} ${k.demand}/分：${esc(k.from)} → ${esc(k.to)} · ${k.isPipe?'管道':'传送带'} <b>${k.lines}</b> 条（上限算下来要 ${k.need} 条）· 单线 <b>${k.perLine}</b>/${k.cap} 个每分 → ${lstate[k.state]||''}</span></div>`).join('')}
      <div class="c-sub" style="margin-top:2px"><span class="c-id">判定：单线负荷 &gt; 载具上限（带 30/分 · 管 120/分）会堵；≥ 90% 算「紧」（加一点需求就堵）。线数不够时是端口/走线被占了 —— 原因见下面的提醒。</span></div>`:''}
      ${RflowAuditHtml(P)}
      ${wAll.length?`<div class="c-sub" style="margin-top:6px"><span><b style="color:${RW_COL.warn}">提醒 ${wAll.length} 条</b></span></div>
      ${wAll.map(x=>`<div class="c-sub" style="margin-top:2px"><span>· ${esc(x)}</span></div>`).join('')}`:''}
      <div class="c-sub" style="margin-top:8px"><span><b>⚠️ 约束校验</b>（硬校验；协议容量 · 建造上限 · 用电取配置表，发电量 · 矿点数 · 存电取社区实测）</span></div>
      ${''/* ⭐v145 撤项：协议容量不约束基地内设备（只约束集成核心区域外的野外设备）→ 报告不再列此项 */}
      <div class="c-sub" style="margin-top:2px"><span>· <b>发电</b>：这条产线用电 <b>${pw.total}</b> 电；协议核心自带 <b>${th.base}</b> 基础发电${th.gap>0?(' → 缺口 <b>'+th.gap+'</b>，需要热能池：'+th.fuels.map(f=>esc(f.item)+' <b>'+f.count+'</b> 台（'+f.power+'/台）').join(' · ')):' → <b>不用额外发电</b>'}${th.fuels.length?` <span class="c-id">（按地区选燃料：${esc(Lregion()||'通用')}）</span>`:''}${stations?`　<span class="c-id">画布上已摆热能池 ${stations} 台</span>`:''}</span></div>
      <div class="c-sub" style="margin-top:2px"><span>· <b>存电</b> <span class="lo-tag">路线图 ②c · 已纳入</span>：上限 <b>${st.cap.toLocaleString?st.cap.toLocaleString('en-US'):st.cap}</b>（社区实测）${st.gap>0?('　当前缺口 <b>'+st.gap+'</b> 电 → 纯靠存电能撑 <b>'+st.minutes+'</b> 分钟（约 '+r1(st.minutes/60)+' 小时），撑完设备就停；这是缓冲不是电源，得补发电'):'　当前用电没超基础发电，存电不动 ✓'}</span></div>
      <div class="c-sub" style="margin-top:2px"><span>· <b>防御建筑上限</b> <span class="lo-tag">路线图 ②b</span>：${lim.defCap!=null?('<b>'+lim.def+'</b> / '+lim.defCap+'（'+esc(lim.zone||'')+'）'+(lim.defOver?' —— <b style="color:'+RW_COL.bad+'">超了 '+(lim.def-lim.defCap)+'</b>':' —— 在限内 ✓')):'（自由模式没指定基地，没有上限可对）'}<span class="c-id">　按分类「战斗辅助」计</span></span></div>
      <div class="c-sub" style="margin-top:2px"><span>· <b>滑索上限</b> <span class="lo-tag">路线图 ②b</span>：<b>基地画布里不涉及</b> —— 滑索架只放野外，不摆进基地（博士 2026-09-21 定，所以左栏也不提供）。本建造区的上限是 <b>${lim.travCap!=null?lim.travCap:'—'}</b>（配置表 <code>travelPoleLimit</code>），那个数服务的是**野外滑索架**，不是基地内的产线。<span class="c-id">沙盘上滑索数恒为 0，所以这一项永远显示 0 / 上限 —— 不是没做校验，是本来就不该在基地里数。</span></span></div>
      <div class="c-sub" style="margin-top:2px"><span>· <b>等级上限（逐档）</b> <span class="lo-tag">配置表 LevelGradeTable</span>：${(()=>{
        const z=((DB.bases||{}).zoneGrades||{})[Linit().base||''];
        if(!z) return '<span class="c-id">本建造区不在 LevelGradeTable 里 —— 这张表只覆盖 8 个区（四号谷地 6 + 景玉谷 / 武陵城）；武陵其余 7 个区的上限要看据点发展等级表（DomainDataTable）</span>';
        const f=z.tiers[0], l=z.tiers[z.tiers.length-1];
        return esc(z.zoneName||z.levelId)+' 共 <b>'+z.maxGrade+'</b> 档 · 协议容量 '+f.bandwidth+' → <b>'+l.bandwidth+'</b> · 防御建筑 '+f.battleBuildingLimit+' → <b>'+l.battleBuildingLimit+'</b> · 滑索 '+f.travelPoleLimit+' → <b>'+l.travelPoleLimit+'</b>　<span class="c-id">（第 1 档 → 满级第 '+l.grade+' 档；与协议容量那一行同源，都是配置表）</span>';
      })()}</span></div>
      <div class="c-sub" style="margin-top:2px"><span>· <b>原料野外上限</b>：${P.res.raw.length?P.res.raw.map(x=>{
        // 跨地区收货的料**本地不采**，野外那些矿脉的上限对它没有意义 —— 照旧渲染会写出
        // 「需 X/分，全图上限 a~b」甚至「超出上限，做不到」，那是把传输来的货当本地矿算，会误导。
        if((P.res.shipIn||[]).some(s=>s.itemId===x)) return esc(RwItemName(x))+'（跨地区收货，<b>本地不采</b>，不计野外上限）';
        const c=RoreCapOf(x), nd=Math.round((rawNeed[x]||0)*10)/10;
        if(!c) return esc(RwItemName(x))+' 需 '+nd+'/分（无野外数据）';
        const cap=c.theoreticalMax
          ? ('上限 <b>'+c.hi+'/分</b>（'+esc(c.theoreticalMax.version||'')+' 游戏内「理论最大开采值」）')
          : ('全图上限 <b>'+c.lo+'~'+c.hi+'/分</b>（'+c.beds+' 脉 × 每脉 '+c.nodesPerBed[0]+'~'+c.nodesPerBed[1]+' 点 × '+c.perMin+'/分）');
        const mk=Object.keys(c.byMap||{});
        const mapTxt=mk.length?('　按地图：'+mk.map(m=>esc(m)+' '+(c.byMap[m]||0)).join(' / ')+'（数字是矿脉数 / 矿源点数）'):'';
        return esc(RwItemName(x))+' 需 <b>'+nd+'</b>/分，'+cap
          +(nd>c.hi?' —— <b style="color:'+RW_COL.bad+'">超出上限，做不到</b>':(nd>c.lo?' —— ⚠️ 高于下限，得把矿点都铺满':' —— 在上限内 ✓'))
          +'<span class="c-id">'+mapTxt+'</span>';
      }).join('　·　'):'（无）'}</span></div>
      ${P.res.raw.map(x=>{ if((P.res.shipIn||[]).some(s=>s.itemId===x)) return ''; const c=RoreCapOf(x); return c?RoreZoneRows(c):''; }).join('')}
      ${RrawLoop(P, rawNeed)}
      <div class="c-sub" style="margin-top:2px"><span class="c-id">⚠️ 发电量（源矿 50 / 谷地电池 220·420·1100 / 武陵电池 1600·3200）与矿点数量、存电上限（10 万）**都是社区实测，不是配置表**；纯度按<b>地区最大值</b>（高纯度 20/分）算。协议容量 / 防御建筑上限 / 滑索上限是<b>配置表</b>（bases.json 的 caps）。<br>矿石总量（博士武陵简报截图逐区计数 + 四号谷地 NGA / 游民星空 / sticweb / TapTap 多方实测）：<b>源矿 60 / 紫晶矿 12 / 蓝铁矿 60 / 赤铜矿 28 个矿点</b>（一个矿脉 = 1 台矿机，别乘每脉点数；高纯度 20/分、低纯度 10/分）。<br>按大地区：<b>四号谷地 源矿 560 · 紫晶 240 · 蓝铁 1080</b>（实测，多方一致）、<b>武陵 源矿 540 · 蓝铁 120 · 赤铜 510</b>（博士截图逐区计数，与游戏内 UI 全部一致 —— 闭环）。<br>「稀有矿物」（黯石 / 燎石 / 武陵石 / 协议纹石）是野外<b>手动拾取</b>的调谐石，不是矿脉，不在本表。</span></div>
      ${planCompareHTML()}
    `;
}
/* ---------- 仓库存取线的放置规则 ----------
   配置表 I18n 原文：
     · 源桩 log_hongs_bus_source：「作为仓库存取线的起始点，可以在集成核心区域自由放置。」
     · 基段 log_hongs_bus：「需要和仓库存取线源桩或其他生效的仓库存取线基段相连。」
     · 存货口 loader_1 / 取货口 unloader_1：「只能贴靠仓库存取线放置。」
   「相连」的口径由博士 2026-09-21 游戏内实拍确认：两条边**有接触**就算 —— 可横向并排、
   可 L 形拐弯、错开一两格也行，不要求整边对齐。游戏里没连上的块会变红并提示
   「没有与仓库存取线源桩或其他运作中基段相连」。沙盘照做：允许摆，但标红 + 给提示。
   ⚠️ 别改成「整边对齐」—— 我第一版就是那么理解的，被博士实拍纠正了。 */
const HONGS_SRC='log_hongs_bus_source', HONGS_BUS='log_hongs_bus', HONGS_PORTS=['loader_1','unloader_1'];
function LhongsRule(id){
  if(id===HONGS_SRC) return '起始点，可自由放置';
  if(id===HONGS_BUS) return '需与源桩或其他基段「边接触」才算相连';
  if(HONGS_PORTS.indexOf(id)>=0) return '只能贴靠仓库存取线放置';
  return '';
}
/* 两个占地矩形是否「边接触」：共边且这条边上至少有 1 格重叠（只对角相邻不算） */
function Ltouch(a,b){
  const adjY=(a.y+a.d===b.y)||(b.y+b.d===a.y);
  const adjX=(a.x+a.w===b.x)||(b.x+b.w===a.x);
  if(!adjY&&!adjX) return false;
  const ovX=Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x);
  const ovY=Math.min(a.y+a.d,b.y+b.d)-Math.max(a.y,b.y);
  return (adjY&&ovX>0)||(adjX&&ovY>0);
}
/* 从源桩出发按「边接触」做连通，返回没接上的存取线件：{uid: 提示文案}
   基段必须能一路接到某个源桩（文案里「生效的基段」= 链上能到源桩的那批）；
   存货口 / 取货口必须挨着源桩或已生效的基段。 */
function LhongsBad(objs,preset){
  const bad={};
  /* 谷地（preset=true）：存取线由基地自动铺，预设线位置拿不到 → 不判「贴靠」，
     否则存货口 / 取货口会被全数误标红（看着像坏了）。武陵与自由模式照旧。 */
  if(preset) return bad;
  const srcs=objs.filter(o=>o.id===HONGS_SRC);
  const buses=objs.filter(o=>o.id===HONGS_BUS);
  const ports=objs.filter(o=>HONGS_PORTS.indexOf(o.id)>=0);
  if(!buses.length&&!ports.length) return bad;
  const seen={}, queue=srcs.slice();
  srcs.forEach(o=>{ seen[o.uid]=1; });
  while(queue.length){
    const cur=queue.shift();
    objs.forEach(o=>{
      if(seen[o.uid]||o.id!==HONGS_BUS) return;
      if(Ltouch(cur,o)){ seen[o.uid]=1; queue.push(o); }
    });
  }
  buses.forEach(o=>{ if(!seen[o.uid]) bad[o.uid]='没有与仓库存取线源桩或其他运作中基段相连'; });
  const good=srcs.concat(buses.filter(o=>seen[o.uid]));
  ports.forEach(o=>{ if(!good.some(g=>Ltouch(o,g))) bad[o.uid]='必须贴靠仓库存取线放置'; });
  return bad;
}
function loAllowed(b){
  if(b.isLogi) return true;          /* 物流件（传送带/管道等）默认就列出来 */
  if(LO_SKIP_IDS.indexOf(b.id)>=0) return false;
  return LO_KEEP_CATS.indexOf(b.categoryName)>=0 || LO_KEEP_IDS.indexOf(b.id)>=0;
}
function renderLayout(){
  const L=Linit(), CELL=LOCELL;
  /* 默认只列产线相关的官方组（仓储/基础生产/合成制造/电力）+ 核心结构 + 物流件；上方分类下拉选了具体分类时，就只列那一类。
     拉黑名单（中继器等）两条路都不给。 */
  /* 免电变体在这里先剔掉，下面的 arr 和分类计数都以它为准 —— 同一座设施只留正常版（博士 2026-09-21）。
     选了谷地的基地时，再把源桩 / 基段剔掉：谷地这两样由基地自动铺，左栏不给（博士 2026-09-21）。 */
  const presetBus=LisPresetBus();
  const all=DB.blueprint.buildings.concat(Llogi().map(LO_LG))
    .filter(b=>!(LO_HIDE_NOP&&LO_IS_NOP(b)))
    .filter(b=>!(presetBus&&LO_BUS_IDS.indexOf(b.id)>=0));
  const arr=f1?all.filter(b=>b.categoryName===f1&&LO_SKIP_IDS.indexOf(b.id)<0):all.filter(loAllowed);
  const totalCells=L.size*L.size;
  const used=L.objs.reduce((s,o)=>s+o.w*o.d,0);
  const pal=arr.map(b=>{
    const sel=L.pick&&L.pick.id===b.id;
    const dm=Ldims(b,sel?L.pickRot:0);
    const tail=b.isLogi
      ? (b.lgPerMin?b.lgPerMin+' 个/分':esc(b.lgMedium))
      : (dm.w+'×'+dm.d);
    const tip=b.isLogi
      ? ` title="${esc(b.name)} · ${esc(b.lgMedium)} · 吞吐 ${b.lgPerMin} 个/分钟"`
      : ` title="${esc(b.name)} · ${esc(b.categoryName)} · 占地 ${dm.w}×${dm.d} · 接口 ${b.portCount} 个 · ${b.needPower?'耗电 '+b.powerConsume:'无需通电'} · id: ${esc(b.id)}${LhongsRule(b.id)?' · 放置规则：'+LhongsRule(b.id):''}"`;
    return `<button class="lo-btn ${sel?'sel':''}" onclick="LpickFromList('${b.id}')"${tip}>
      <span style="width:18px;text-align:center;color:${b.isLogi?lgColor(b):catColor(b)};font-weight:700">${loPieceGlyph(b)}</span>
      <span style="flex:1">${esc(b.name)}</span>
      <span class="lo-tag">${tail}</span>
    </button>`;
  }).join('');
  const sizeBtns=[40,50,70,80].map(n=>`<button class="lo-size ${L.size===n&&!L.base?'on':''}" onclick="Lsize(${n})" title="自由模式：只设边长，不带地区规则（选过基地的话会退出基地选择）">${n}×${n}</button>`).join('');
  /* 「基地」下拉 = 两个地区的分界线：选一片基地就设画布边长 + 切该地区的存取线规则
     （武陵要自己摆、有上限、没接上标红；谷地由基地自动铺、左栏不给源桩/基段、不判贴靠）。
     博士 2026-09-21：「把武陵和四号谷地分开讨论」。 */
  const bases=Lbases();
  const baseSel=`<select class="lo-sel" onchange="LbaseSet(this.value)" title="选一片基地 = 设画布边长 + 切该地区的存取线规则">
      <option value=""${L.base?'':' selected'}>自由模式（不限地区）</option>
      ${['四号谷地','武陵'].map(d=>'<optgroup label="'+d+'">'+bases.filter(r=>r.domainName===d)
        .map(r=>`<option value="${r.levelId}"${L.base===r.levelId?' selected':''}>${esc(r.zoneName)} · ${esc(r.role)} ${r.side}×${r.side}</option>`).join('')
        +'</optgroup>').join('')}
    </select>`;
  const curRow=LbaseRow();
  const baseTag=curRow
    ? `<span class="lo-tag">当前：${esc(curRow.domainName)}·${esc(curRow.zoneName)}${presetBus?' · 存取线由基地自动铺':' · 存取线自己摆'}</span>`
    : `<span class="lo-tag">当前：自由模式（不限地区）</span>`;
  /* ⭐v145 多基地页签（博士 2026-09-24：一键最优排布要能看到这个地区的每张画布）
     只列**当前基地所在地区**的基地；摘要读各基地已存的那份内容（bases[levelId]），
     所以没被切过的基地也照样报得出「机器 0 · 占地 0/Y」。 */
  const baseTabs=(()=>{
    if(!curRow) return '';                       /* 自由模式不出页签 */
    const zone=bases.filter(x=>x.domainName===curRow.domainName);
    if(zone.length<2) return '';
    return '<div class="lo-tabs">'+zone.map(b=>{
      const st=L.bases[b.levelId]||{}, bs=st.objs||[];
      /* ⚠️ 不能用 planRole 判机器 —— 那是排布器生成的件才带的标记，手动摆的没有（v145 实测抓出：摆了 3 台仍显示 0）。
         正解：非物流件即建筑。 */
      const mach=bs.filter(o=>{ const bp=byBp(o.id); return bp&&!bp.isLogi; }).length;
      const used=bs.reduce((a,o)=>a+(o.w||0)*(o.d||0),0);
      /* ⭐v145 曾在此显示协议容量占用，2026-09-24 博士游戏内确认「核心区无限制」后撤回：
         协议容量只约束集成核心区域**外**的野外设备，基地内不受限，显示已用/上限会误导。 */
      const hasPlan=!!(st.plan&&st.plan.res);
      return `<button class="lo-tab ${b.levelId===L.base?'on':''}" onclick="LbaseSet('${b.levelId}')"
        title="切到 ${esc(b.zoneName)}（${esc(b.role)} ${b.side}×${b.side}）—— 每片基地的摆放各存一份，切回来原样还在"
        ><span>${esc(b.zoneName)} · ${esc(b.role)} ${b.side}×${b.side}</span>
        <span class="lo-tabsm">机器 ${mach} · 占地 ${used}/${b.usableCells||'?'}${hasPlan?' · 已出产线':''}</span></button>`;
    }).join('')+'</div>';
  })();
  /* 格子边长档位：14 是原默认值，20 是现在的默认（物流件的流向箭头在 14px 格上只有几像素，看不清） */
  const cellBtns=[14,20,26,32].map(n=>`<button class="lo-size ${LOCELL===n?'on':''}" onclick="Lcell(${n})">${n}px</button>`).join('');
  /* 物流件占格索引：给接口做「外侧有没有接上」的判定 + 流向拓扑。
     ⭐v152：物流件按「格 × 介质」双索引 —— 3D 里管道在上层、传送带在下层，一格可同时有管+带
     （管×带交叉不再放桥，博士 2026-09-24 游戏实锤）。索引键 'p:x,y' / 'b:x,y'；
     flowNext 同样按介质分表 —— 叠加格里两层的流向互不干扰，各层各推各的进边。 */
  const lgi={};
  L.objs.forEach(o=>{ const b=byBp(o.id); if(b&&b.isLogi) lgi[(b.lgMedium==='管道'?'p':'b')+':'+o.x+','+o.y]=o; });
  /* ⭐ 流向表：每个带/管格的「下一格」—— 用来反推每格的进边（弯道渲染要用）。
     ⭐v142：**准入口（箱阀/管阀）也必须进表** —— 它是串接在线上的件，被它替换掉的那格原来是带子，
     下游的弯头格靠「邻居指向我」反推进边；只认带/管的话准入口就成了空气，
     于是「放在转折格旁边」时转折格反推不到上游 → 被画成直线（博士 2026-09-24 实测三报之一）。 */
  const flowNext={};
  Object.values(lgi).forEach(o=>{
    const b=byBp(o.id);
    if(!b) return;
    const fk=(b.lgMedium==='管道'?'p':'b')+':'+o.x+','+o.y;
    if(b.lgType==='Connector'||b.lgType==='FluidConnector'){
      /* ⭐v151 续：桥也进流向表（出向按 rot —— RwRotTo 给的就是真实下游方向）。
         桥后那格的进边靠「桥指向我」反推，桥不在表里则那格推不出进边 → 画成直条
         （实测赤铜块@10 的 (13,24) 终点格，上游恰好是桥）。 */
      const v={0:[1,0], 90:[0,1], 180:[-1,0], 270:[0,-1]}[o.rot];
      if(v) flowNext[fk]=[o.x+v[0], o.y+v[1]];
      return;
    }
    if(b.lgType!=='Belt'&&b.lgType!=='Pipe'&&b.lgType!=='BoxValve'&&b.lgType!=='FluidValve') return;
    const out=(lgPortSides(b,o.rot).out||[])[0];
    const v={r:[1,0], b:[0,1], l:[-1,0], t:[0,-1]}[out];
    if(v) flowNext[fk]=[o.x+v[0], o.y+v[1]];
  });
  /* ⭐v107 出料口外格索引：机器某 output 口的外侧格 → {from:带子的进边方向, pipe:是否管道口}。
     孤格带/管夹在两台对角机器之间时没有带子邻居，flowIn 只查带子会推不出进边
     （博士图1「还是不行」）—— 现在机器口也算拓扑。from = 口朝向的反侧（机器在那边）。 */
  const portOut={};
  /* ⭐v151 续2：feed 起点格（外部暗管接入点）的进边 —— 料从画布外垂直插进这格，
     它压在哪条边、进边就是朝外那侧；角落取「≠ 第一段走向」的外侧（第一段朝内走时
     外侧恰为反向，同式成立）。没有这条，feed 起点永远画直条（博士 2026-09-24
     截图红框三连：「这些是不是要接外部暗管啊，也没有弯」—— 就是它们）。 */
  const feedStart={};
  if(L.plan&&L.plan.route) L.plan.route.links.forEach(l=>{
    if(l.from!=='画布外（暗管接入）'||l.fmode==='udpipe') return;   /* ⭐v154：暗管对 feed 的起点在出口旁，不是边缘格 */
    const ps=Array.isArray(l.path)?l.path:[];
    if(!ps.length) return;
    const p0=ps[0].split(',').map(Number), p1=ps.length>1?ps[1].split(',').map(Number):null;
    const sx=p0[0], sy=p0[1], S=L.size;
    const outs=[];
    if(sy===0) outs.push('t');
    if(sy===S-1) outs.push('b');
    if(sx===0) outs.push('l');
    if(sx===S-1) outs.push('r');
    if(!outs.length) return;
    const d0=p1?(p1[0]>sx?'r':p1[0]<sx?'l':p1[1]>sy?'b':'t'):null;
    feedStart[sx+','+sy]=(d0&&outs.find(o=>o!==d0))||outs[0];
  });
  const flowIn=(x,y,isPipe)=>{
    const NB={t:[0,-1], b:[0,1], l:[-1,0], r:[1,0]};
    const pm=po=>po&&(po.pipe===undefined||!!po.pipe===!!isPipe);
    /* ⭐v152：流向表/物流件索引都按介质分键 —— 叠加格里管、带两层各推各的进边，互不可见 */
    const FK=(px,py)=>(isPipe?'p':'b')+':'+px+','+py;
    for(const d in NB){
      const nx=x+NB[d][0], ny=y+NB[d][1];
      const nxt=flowNext[FK(nx,ny)];
      if(nxt&&nxt[0]===x&&nxt[1]===y) return d;
      /* ⭐v151 续：桥格双向穿行 —— 桥的 rot/flowNext 只保留**最后一次**穿行的方向，先从另一轴
         穿过桥的线，其下游格靠「桥指向我」推不出进边（实测赤铜耐压罐@10 的 (6,4)：上游 (6,5)
         是桥、rot=180 被后穿的横向线覆盖，本线纵向 (6,5)→(6,4)）。桥四侧皆可进出（lgPortSides），
         真正穿过桥的线在桥另一侧同轴必有格子指回桥 —— 用这条「连续性」补判，不盲目按轴放行
         （否则恰好停在桥旁的无关格会误得进边）。介质对齐由 FK 键位天然保证
         （带桥在 'b:' 表、管桥在 'p:' 表，只查自己那层）。 */
      const nbo=lgi[FK(nx,ny)], nbb=nbo&&byBp(nbo.id);
      if(nbb&&(nbb.lgType==='Connector'||nbb.lgType==='FluidConnector')){
        const b2=flowNext[FK(nx+NB[d][0],ny+NB[d][1])];
        if(b2&&b2[0]===nx&&b2[1]===ny) return d;
      }
    }
    for(const d in NB){
      const po=portOut[(x+NB[d][0])+','+(y+NB[d][1])];
      if(pm(po)) return po.from;
    }
    /* ⭐v151 续：这格**自己**就是机器出料口 / 汇流器·分流器出格的外侧格 ——
       料从本体那侧流入本格（线起点格的进边）。没有这条，出口第一格永远画成直条
       （博士 2026-09-24 截图「入口弯头好了，出口没有」）。 */
    const self=portOut[x+','+y];
    if(pm(self)) return self.from;
    /* ⭐v151 续2：feed 起点自查 —— 暗管从画布外这一侧插进来（见 feedStart 表注释） */
    const fs=feedStart[x+','+y];
    if(fs) return fs;
    return null;
  };
  /* ================================================================
     画布渲染段（flowIn ~ 画布 DOM 拼装）。按渲染层次从上到下阅读：
       [a] 接口统计 pAll/pOn     —— 接口图例的计数口径
       [b] 存取线校验 badMap     —— 未接上的件（画布标红）+ 计数/上限
       [c] 环境范围层 envLayer   —— 散布机 13×13 方形半透明色块（⭐v103）
       [d] 浮层 gasBar / dlvPop  —— 就地选气条（⭐v104）/ 核心出货清单（⭐v109）
       [e] 格子渲染 cells        —— 每个建筑一个 .lo-cell（本段最长）
       [f] 物流汇总 longest      —— 传送带/管道计数与最长连通段
     各层只读 L.objs / DB，渲染顺序即 DOM 顺序；除 cells 外都是「先算字符串、最后统一拼」。
     ================================================================ */
  /* ---- [a] 接口统计（和下面的逐个渲染同口径：越界的不算、朝向跟 rot 转 ⭐v122） ---- */
  let pAll=0, pOn=0;
  L.objs.forEach(o=>{
    const b=byBp(o.id);
    /* ⭐v151 续：汇流器/分流器（Router）的**出格**也进 portOut —— 干线起点格的进边靠它反推，
       否则「出口没有弯头」（博士 2026-09-24 截图：汇流干线出来第一格画成直条）。
       from = 本体相对出格的方向；汇流器 1 出（上）、分流器 3 出（上/左/右）。
       ⚠️ 不填 pipe（通配）：objs 元素转存时 isPipe 字段丢了（keys=uid|id|x|y|rot|w|d|planRole），
       管道汇流器回落 lgMedium='传送带' 会匹配不上；而汇流器与所连线永远同介质（RwRoute 保证），
       通配无误伤。 */
    if(b&&b.isLogi&&b.lgType==='Router'){
      const OPPT={t:'b', b:'t', l:'r', r:'l'};
      (lgPortSides(b,o.rot).out||[]).forEach(sd=>{
        const v={r:[1,0], b:[0,1], l:[-1,0], t:[0,-1]}[sd];
        if(!v) return;
        const kx=o.x+v[0], ky=o.y+v[1];
        if(kx<0||ky<0) return;
        portOut[kx+','+ky]={from:OPPT[sd]};
      });
      return;
    }
    if(!b||b.isLogi) return;
    const fp=Lfp(b);
    (b.ports||[]).forEach(p=>{
      /* ⭐v154：暗管入口的 input 口接的是**画布外暗管**（博士自己拉），画布内永远「没接」——
         不计入接口统计，否则「接口已接 N/M」永远凭空少几个、看着像漏接。 */
      if(b.id.indexOf('udpipe_loader')===0 && p.kind==='input') return;
      const q=LportXY(p,o.rot,fp[0],fp[1]);
      if(q.x<0||q.x>=o.w||q.z<0||q.z>=o.d) return;
      const dir=LportDirRot(p,o.rot,fp[0],fp[1]);   /* ⭐v122：朝向跟 rot 转（原贴边猜，旋转后统计与色条全错） */
      const dx=dir==='l'?-1:dir==='r'?1:0, dz=dir==='u'?-1:dir==='d'?1:0;
      pAll++;
      /* ⚠️ 两套方向命名在这汇合：LportDir 给 u/d（上下），色条/flowIn 体系用 t/b —— 必须转译，
         否则 LOGI_OPP['u'] 是 undefined，机器口反推的进边整条丢失（探针 2026-09-23 实锤）。 */
      if(dir&&p.kind==='output') portOut[(o.x+q.x+dx)+','+(o.y+q.z+dz)]={from:LOGI_OPP[dir==='u'?'t':dir==='d'?'b':dir], pipe:!!p.isPipe};
      if(dir&&LlogiAt(lgi,o.x+q.x+dx,o.y+q.z+dz,p.isPipe)) pOn++;
    });
  });
  /* ---- [b] 存取线校验：哪些件没接上（画布上标红），以及计数 / 上限 ---- */
  const badMap=LhongsBad(L.objs,presetBus);
  const busZones=((DB.bases&&DB.bases.zones)||[]).filter(z=>z.busCap);
  const curZone=busZones.filter(z=>z.levelId===L.zone)[0]||busZones[0]||null;
  const hongsCap=curZone?curZone.busCap:null;
  const nSrc=L.objs.filter(o=>o.id===HONGS_SRC).length;
  const nBus=L.objs.filter(o=>o.id===HONGS_BUS).length;
  const nBad=Object.keys(badMap).length;
  const pw=Rpower(L.objs);      /* ⚡ 用电：配置表 powerConsume 求和 */
  /* 谷地：把预设存取线画到画布**外缘**（整条在画布框外面 —— 不占格、不挡摆放，只做可视参考） */
  const presZone=LbusZone();
  const presetBand=presetBus?LpresetBand(presZone,CELL,L.size):'';
  /* ---- [c] 环境范围层：每台散布机一块方形半透明色块 ---- ⭐v103
     占地外扩 rangeExtend.x（配置表 5 → 13×13）。
     DOM 顺序放在 cells 之前 = 建筑层之下；pointer-events:none 不挡框选；超界部分裁到画布内。 */
  const envLayer=L.showGas?L.objs.map(o=>{
    const b=byBp(o.id);
    const vp=vaporizerOf(b);
    if(!vp) return '';
    const ext=(vp.rangeExtend&&vp.rangeExtend.x)||0;
    const x1=Math.max(0,o.x-ext), y1=Math.max(0,o.y-ext);
    const x2=Math.min(L.size,o.x+o.w+ext), y2=Math.min(L.size,o.y+o.d+ext);
    if(x2<=x1||y2<=y1) return '';
    const _ge=o.gas||1;
    return `<div class="lo-env" style="left:${x1*CELL}px;top:${y1*CELL}px;width:${(x2-x1)*CELL}px;height:${(y2-y1)*CELL}px;--envbg:${envColorOf(_ge)};--envline:${envEdgeOf(_ge)};--envop:${envOpOf(_ge)}"></div>`;
  }).join(''):'';
  /* ---- 供电范围层：供电桩/中继器的配电覆盖（照环境圈同款画法）---- ⭐v148 */
  const pwrLayer=L.showPwr?L.objs.map(o=>{
    const b=byBp(o.id);
    const pp=powerPoleOf(b);
    if(!pp) return '';
    const ext=(pp.rangeExtend&&pp.rangeExtend.x)||0;
    const x1=Math.max(0,o.x-ext), y1=Math.max(0,o.y-ext);
    const x2=Math.min(L.size,o.x+o.w+ext), y2=Math.min(L.size,o.y+o.d+ext);
    if(x2<=x1||y2<=y1) return '';
    return `<div class="lo-pwr" style="left:${x1*CELL}px;top:${y1*CELL}px;width:${(x2-x1)*CELL}px;height:${(y2-y1)*CELL}px"></div>`;
  }).join(''):'';
  /* ---- [d] 浮层：就地选气条 + 核心出货清单 ---- */
  /* ⭐v104 就地选气条（博士：「想要点机器就地选」）：选中散布机时浮在机器正上方 ——
     色块 = 四种气体（即四种环境，圈色同款），点一下 LgasSet 批量换气；当前气描高亮圈。
     与环境圈层开关解耦：圈藏了也能换气（换的是对象属性，不是图层）。 */
  const gasBar=(function(){
    const vsel=LselObjs().filter(o=>vaporizerOf(byBp(o.id)));
    if(!vsel.length) return '';
    const vb=byBp(vsel[0].id);
    const gs=(vb.vaporizer.gasGroups||[]);
    if(!gs.length) return '';
    const cur=vsel[0].gas||1;
    const same=vsel.every(o=>(o.gas||1)===cur);
    /* 锚点：选中散布机的包围盒左上角；条放机器上方，贴 0 不出画布顶 */
    const bx=Math.min.apply(null,vsel.map(o=>o.x))*CELL;
    const by=Math.max(0,Math.min.apply(null,vsel.map(o=>o.y))*CELL-28);
    const tip=vsel.length>1?('作用于选中的 '+vsel.length+' 台散布机'):'点色块换通入的气体（圈色跟着变）';
    return `<div class="lo-gasbar" style="left:${bx}px;top:${by}px" title="${tip}">
      <b>💨${vsel.length>1?('×'+vsel.length):''}</b>
      ${gs.map(g=>`<button class="${same&&cur===g.env?'on':''}" style="background:${envColorOf(g.env)};border-color:${envEdgeOf(g.env)}"
        onclick="LgasSet(${g.env})" title="通入「${esc(g.name)}」→ ${ENV_NAME[g.env]||g.env}环境（最低 ${g.rate} 单位/分 · 官方面板口径）"></button>`).join('')}
    </div>`;
  })();
  /* ⭐v109 协议核心出货清单浮层：点出料口的内部箭头弹出，浮在该口正上方。
     清单 = 该核心所属域的可出货物品（DB.hubItems 按 domains 过滤），按稀有度降序。
     ⭐v126：加搜索框 + 稀有度 chip（博士「东西几百个太多了」）。服务端过滤只渲染
     匹配项（render 路径保持筛选），oninput/点 chip 走 LdlvRefilter 轻量 DOM 过滤
     （不 render，防输入框丢焦点）。条目带 data-nm/data-rr 供 DOM 过滤。 */
  /* ⭐v135 机器选择浮层（点机器弹出；定位与样式沿用协议核心出货浮层那套） */
  const macPop=(function(){
    if(!L.macPop) return '';
    const o=L.objs.filter(x=>x.uid===L.macPop.uid)[0]; if(!o) return '';
    const b=byBp(o.id); if(!b) return '';
    const html=RmacPanelOf(b, o); if(!html) return '';
    /* ⭐v136：宽 440 → 缓存格 4 个一行；位置优先放机器**下方**（别盖住机器本体），
       下方放不下（机器贴着画布底）才翻到上方。 */
    const W=440, H_EST=370;
    const _lo=4, _hi=Math.max(4, L.size*CELL-W-6);
    const cx=Math.min(_hi, Math.max(_lo, o.x*CELL+o.w*CELL/2-W/2));
    const below=(o.y+o.d)*CELL+8;
    const cy=(below+H_EST<=L.size*CELL) ? below : Math.max(4, o.y*CELL-8-H_EST);
    return `<div class="lo-dlvpop lo-macpop" style="left:${cx}px;top:${cy}px;width:${W}px" onclick="event.stopPropagation()">
        <div class="hd"><b>${esc(b.name)}</b> <span class="c-id">${esc(b.id)}</span>
          <span class="x" onclick="LmacClose()" title="关闭">×</span></div>
        ${html}</div>`;
  })();
  const dlvPop=(function(){
    if(!L.dlvPop) return '';
    const o=L.objs.filter(x=>x.uid===L.dlvPop.uid)[0];
    if(!o) return '';
    const b=byBp(o.id); if(!hubIsHub(b)) return '';
    const dom=hubDomainOf(o), cands=hubCands(dom);
    const cur=hubPickGet(o,L.dlvPop.idx);
    const _q=String(L.dlvPop.q||'').trim().toLowerCase(), _r=L.dlvPop.rare||0, _j=L.dlvPop.jar||0;
    /* ⭐v127 搜索口径 = 名字 + 灌装物标注（搜「息壤」命中「紫晶质瓶·装：息壤液」） */
    const shown=cands.filter(it=>(!_q||(String(it.name)+' '+(it.ct||'')).toLowerCase().indexOf(_q)>=0)
      &&(!_r||it.rarity===_r)&&(!_j||LdlvIsJar(it)));
    const _lo=4, _hi=Math.max(4,L.size*CELL-234);
    const cx=Math.min(_hi, Math.max(_lo, o.x*CELL+o.w*CELL/2-115));
    const cy=Math.max(4, o.y*CELL-8);
    const rrs=[]; cands.forEach(it=>{ if(rrs.indexOf(it.rarity)<0) rrs.push(it.rarity); });
    rrs.sort((a,b)=>b-a);
    const chips=`<button class="cbtn${!_r?' on':''}" data-r="0" onclick="LdlvSetR(0)">全部</button>`
      +rrs.map(r=>`<button class="cbtn${_r===r?' on':''}" data-r="${r}" onclick="LdlvSetR(${r})">R${r}</button>`).join('')
      +`<button class="cbtn${_j?' on':''}" data-j="1" onclick="LdlvSetJ(${_j?0:1})"
          title="只看瓶罐装的物品（灌装瓶 / 气罐 / 药品瓶 · 罐头）">瓶罐</button>`;
    const body=shown.length
      ? shown.map(it=>`<div class="it ${cur===it.id?'on':''}" data-nm="${esc(it.name)}" data-rr="${it.rarity}"
            data-ct="${esc(it.ct||'')}" data-jar="${LdlvIsJar(it)?1:0}"
            onclick="LdlvPick('${o.uid}',${L.dlvPop.idx},'${it.id}')"
            title="${esc(it.name)} · R${it.rarity}${it.ct?' · '+esc(it.ct):''}">
            <span class="rr">${hubStars(it.rarity)}</span><span class="nm">${esc(it.name)}${it.ct?` <span class="cc">${esc(it.ct)}</span>`:''}</span>
            <span class="ck">${cur===it.id?'✓':''}</span></div>`).join('')
      : '<div class="em">没有匹配的物品 —— 换个关键词或点「全部」试试。</div>';
    return `<div class="lo-dlvpop" style="left:${cx}px;top:${cy}px" onclick="event.stopPropagation()">
        <div class="hd"><b>出料口 #${L.dlvPop.idx} 出货物品</b>
          <span class="c-id">${esc(hubDomainName(dom))}</span>
          <span class="x" onclick="LdlvClose()" title="关闭">×</span></div>
        <div class="ft"><input class="dlvq" value="${esc(L.dlvPop.q||'')}" placeholder="搜物品名…"
            oninput="LdlvSetQ(this.value)" title="按名字筛选，输入即搜">${chips}
          <span class="ct">${shown.length} / ${cands.length} 件</span></div>
        ${cur?`<div class="it on" onclick="LdlvPick('${o.uid}',${L.dlvPop.idx},'${cur}')" title="取消这件出货">
            <span class="rr"></span><span class="nm">（取消出货）</span><span class="ck"></span></div>`:''}
        <div class="lo-dlvplist">${body}</div>
      </div>`;
  })();
  /* ---- [e] 格子渲染：每个建筑一个 .lo-cell（本段最长，逐件生成 SVG + tooltip） ---- */
  const cells=L.objs.map(o=>{
    const b=byBp(o.id);
    const px=o.x*CELL, py=o.y*CELL, w=o.w*CELL, d=o.d*CELL;
    const on=L.sel.indexOf(o.uid)>=0;
    /* 物流件：1×1，接口方向由 lgSvg 自己画（边上的进/出色条 + 中心功能字形或流向箭头）。
       不再用「1 格上接口坐标退化」那套说法 —— rotation.y 解出来的是流向，可以逐边画准。 */
    if(b.isLogi){
      /* ⭐v106：弯头格 tooltip 的「进」也按真实拓扑（flowIn），与色条/弯道弧同一口径 */
      const _fin=(b.lgType==='Belt'||b.lgType==='Pipe')?flowIn(o.x,o.y,b.lgMedium==='管道'):null;
      /* ⭐v139 准入口合规校验（博士：「不是说只能放在传送带上吗，怎么没标红」）：
         准入口放好后是**替换**掉原来的带/管（那格只剩准入口），所以判据看**衔接**——
         四邻里有没有同类介质的带/管。孤立（一个都没有）= 没放在带/管上 → 标红警示。
         这样无论它是新放的、旧画布留下的、还是从方案/撤销栈恢复的，都会被标出来。 */
      let _vbad=false, _vwhy='';
      if(b.lgType==='BoxValve'||b.lgType==='FluidValve'){
        /* ⭐v140 标红与放置校验共用同一判定（LvalveBad），口径永远一致 */
        const _why=LvalveBad(o.x, o.y, b.lgMedium);
        _vbad=!!_why;
        if(_vbad) _vwhy='【⚠️ 位置不合规：'+b.name+'必须放在'+(b.lgMedium==='管道'?'管道':'传送带')+'上，且要顺着物流方向 —— '
          +_why+'，请挪到直线段上】';
      }
      const ttl=esc(b.name)+' · 走向 '+o.rot+'°（'+LdirName(o.rot)+'） · '+esc(b.lgMedium)
        +' '+b.lgPerMin+' 个/分钟'
        +' · 接口：进 '+(_fin?LGNAME[_fin]:lgSideNames(b,o.rot,'in'))+' / 出 '+lgSideNames(b,o.rot,'out');
      return `<div class="lo-cell ${b.lgMedium==='管道'?'lgp':'lgb'} ${on?'sel':''}${o.lock?' lock':''}${_vbad?' vbad':''}" data-uid="${o.uid}"
          style="left:${px}px;top:${py}px;width:${w-2}px;height:${d-2}px"
          title="${o.lock?'【已锁定】':''}${_vwhy}${ttl}"
        >${lgSvg(b,o.rot,flowIn(o.x,o.y,b.lgMedium==='管道'))}</div>`;
    }
    const fp=Lfp(b);
    /* 这台设施选了配方吗？选了就把产出物品标在格子上、并给接口分「走 / 不走」 */
    const _rl=RpoolOf(o);
    const rec=_rl.length?RbyId(_rl[0]):(o.r?RbyId(o.r):null);
    const rp=rec?RportSets(rec):null;
    const prod=o.prod||(_rl.length>1?('同池 '+_rl.length+' 条反应'):((rec&&rec.outcomes&&rec.outcomes[0])?rec.outcomes[0].name:''));
    /* ⭐v103：散布机 tooltip 前缀 —— 通入的气体 + 环境范围（数据 FactoryVaporizerTable） */
    const vp=vaporizerOf(b);
    const vpTtl=vp?('【环境圈：'+esc(envGasName(o.gas||1))+' · 环境 '+vaporizerSide(b)[0]+'×'+vaporizerSide(b)[1]+' 格（外扩 '+vaporizerSide(b)[2]+'）】'):'';
    let ports='';
    (b.ports||[]).forEach(p=>{
      const q=LportXY(p,o.rot,fp[0],fp[1]);
      if(q.x<0||q.x>=o.w||q.z<0||q.z>=o.d) return;
      /* 标记贴在建筑**内侧**、紧挨自己的边框（不再压格线）——
         压格线时有一半伸进邻格，邻格一放传送带就互相压字。这里用 padding box 坐标系：
         内框尺寸 = 占地格数×14 - 5（两侧 1.5px 边框 + 2px 的格间隙），marker 半径 3.5，
         再留 0.5px 空隙 → 中心距内沿 4px。 */
      const dir=LportDirRot(p,o.rot,fp[0],fp[1]);   /* ⭐v122：朝向跟 rot 转（标记贴边 + on 判定 + tooltip 都靠它，原贴边猜旋转后全错） */
      const dx=dir==='l'?-1:dir==='r'?1:0, dz=dir==='u'?-1:dir==='d'?1:0;
      const INW=o.w*CELL-5, IND=o.d*CELL-5, E=4;
      const pcx=dx?(dx>0?INW-E:E):(q.x*CELL+CELL/2-1.5);
      const pcy=dz?(dz>0?IND-E:E):(q.z*CELL+CELL/2-1.5);
      const col=p.kind==='input'?'#186C7D':'#C0561F';
      /* ⭐v154：暗管入口的 input 口接画布外暗管（博士自己拉），恒视为已接（亮灯），不误导 */
      const lk=(!!dir&&LlogiAt(lgi,o.x+q.x+dx,o.y+q.z+dz,p.isPipe))
        ||(b.id.indexOf('udpipe_loader')===0&&p.kind==='input');
      /* 物料流向：进料口从该边的对侧进来，出料口朝该边出去 */
      const f=dir?(p.kind==='input'?({u:'d',d:'u',l:'r',r:'l'})[dir]:dir):'';
      /* 按配方标「走 / 不走」：走的是该相态那套口（组级能力，不是一对一，见 recipe_groups.json） */
      let pu='';
      if(rp){
        const arr=p.kind==='input'?(p.isPipe?rp.pipeIn:rp.beltIn):(p.isPipe?rp.pipeOut:rp.beltOut);
        pu=arr.indexOf(p.index)>=0?'use':'off';
      }
      const ttl=esc(b.name)+' · '+(p.kind==='input'?'进料口':'出料口')+' #'+p.index
        +' · '+esc(p.medium||'')+' · '+(p.isPipe?'圆形口(管道)':'方形口(传送带)')
        +' · 在'+({u:'上',d:'下',l:'左',r:'右'})[dir]+'边'
        +' · 物料向'+(f?({u:'上',d:'下',l:'左',r:'右'})[f]:'—')+(p.kind==='input'?'进入':'离开')
        +' · '+(lk?'外侧已接同类物流件':'外侧还没有接')
        +(rp?(' · 本配方：'+(pu==='use'?('走这里（'+(p.isPipe?'流体料':'固态料')+'）'):'不走这个口')):'');
      ports+=`<div class="lo-port ${p.isPipe?'pipe':''} ${lk?'on':''} ${pu}" style="left:${pcx}px;top:${pcy}px;background:${col}" title="${ttl}"></div>`;
      /* ⭐v109 协议核心出货：可点的指向箭头 + 选货清单；选了货变绿、旁边标名字。
         ⭐v124（博士截图红圈「把选择物品的模块移到里面，外侧像其他基建一样是货品进出口」）：
         箭头不再压在口格上 —— 口格留白给物流交互（手拿件点口=拉线、空手点口=选中/拖动，
         与其他基建同款）。选货入口挪到核心**内侧一格**、仍朝外指对应它的口；
         名字标签跟在箭头内侧。坐标教训（v109 两版踩坑：边缘列没有余量可推）在这里
         反而成了正解 —— 内移整格是唯一任何格尺寸都不越界的放法。 */
      if(hubIsHub(b)&&p.kind==='output'){
        const gcx=q.x*CELL+CELL/2 - dx*CELL, gcy=q.z*CELL+CELL/2 - dz*CELL;
        const it=hubPickItem(o,p.index);
        const px2=gcx - dx*13, py2=gcy - dz*13;
        ports+=`<div class="lo-dlv${it?' set':''}" style="left:${gcx}px;top:${gcy}px"
            title="${esc(b.name)} 出料口 #${p.index}（口内侧）—— 点这里选这件货${it?('（当前：'+esc(it.name)+'，再点同类可取消）'):''}"
            onclick="LdlvOpen('${o.uid}',${p.index})">${LO_DLVARROW[dir]||''}</div>`;
        if(it) ports+=`<div class="lo-dlvt" style="left:${px2}px;top:${py2}px" title="${esc(it.name)}">${esc(it.name)}</div>`;
      }
    });
    return `<div class="lo-cell ${on?'sel':''}${badMap[o.uid]?' bad':''}${o.lock?' lock':''}" data-uid="${o.uid}" title="${o.lock?'【已锁定】':''}${vpTtl}${esc(badMap[o.uid]||(rec?Rsummary(rec):''))}" style="left:${px}px;top:${py}px;width:${w-2}px;height:${d-2}px">
        <span class="lo-glyph">${catGlyph(b)}</span>
        ${prod&&w>=60?`<span class="lo-prod">${esc(prod)}</span>`:''}
        ${w>=60?`<span class="lo-name">${esc(b.name)}</span>`:''}
        ${L.showPort?ports:''}
      </div>`;
  }).join('');
  const dm=L.pick?Ldims(L.pick,L.pickRot):null;
  /* ---- [f] 物流件汇总 + 传送带最长连通段 ---- */
  const lgs=L.objs.filter(o=>{ const b=byBp(o.id); return !!b&&!!b.isLogi; });
  const isPipePiece=o=>{ const b=byBp(o.id); return b&&b.lgMedium==='管道'; };
  const pipeN=lgs.filter(isPipePiece).length, beltN=lgs.length-pipeN;
  const funcN=lgs.filter(o=>{ const b=byBp(o.id); return b.lgType!=='Belt'&&b.lgType!=='Pipe'; }).length;
  const longest=(function(){
    const m={}, seen={};
    lgs.forEach(o=>{ const b=byBp(o.id); m[o.x+','+o.y]=b.lgMedium; });
    let best=0;
    Object.keys(m).forEach(k=>{
      if(seen[k]) return;
      const med=m[k]; let n=0; const stack=[k]; seen[k]=1;
      while(stack.length){
        const cur=stack.pop(); n++;
        const pr=cur.split(','), x=+pr[0], y=+pr[1];
        [[1,0],[-1,0],[0,1],[0,-1]].forEach(dd=>{
          const kk=(x+dd[0])+','+(y+dd[1]);
          if(m[kk]===med&&!seen[kk]){ seen[kk]=1; stack.push(kk); }
        });
      }
      if(n>best) best=n;
    });
    return best;
  })();
  /* 左栏顶部：说清默认列了哪几类、共多少项（数字从数据算，不写死） */
  /* v131 左栏分组按游戏「工业设备」面板官方组序（与 CAT_ORDER 同源）：快捷建造（=核心结构）→
     物流（=物流件）→ 资源开采（默认不列）→ 仓储存取 → 基础生产 → 合成制造 → 电力 →
     功能设备 → 战斗辅助（默认不列）。组名直接用官方组名。 */
  const grp=[['核心结构',null],['物流件',['物流件']],['仓储存取',['仓储存取']],['基础生产',['基础生产']],
             ['合成制造',['合成制造']],['电力',['电力']],['功能设备',['功能设备']]];
  const cnt=g=>(g[1]?all.filter(b=>g[1].indexOf(b.categoryName)>=0)
                     :all.filter(b=>LO_KEEP_IDS.indexOf(b.id)>=0))
                    .filter(b=>LO_SKIP_IDS.indexOf(b.id)<0).length;
  /* 选中的生产设施：左栏顶部给它一个配方下拉（同机种可批量套用）。
     配方数据来自 DB.machine_recipes（machineId ↔ 建筑 id），产能由 Rrate 现算。 */
  const rInfo=RselectedInfo();
  const rRt=(rInfo&&rInfo.recipe)?Rrate(rInfo.recipe):null;
  const rCarrier=rt=>{
    if(!rt) return '';
    const b=Rcarriers(rt.solidIn,false), p=Rcarriers(rt.fluidIn,true);
    const parts=[];
    if(b) parts.push('传送带 '+b+' 条（固态 '+rt.solidIn+'/分 ÷ 30）');
    if(p) parts.push('管道 '+p+' 条（流体 '+rt.fluidIn+'/分 ÷ 120）');
    return parts.length?parts.join(' · '):'这配方不用外接料';
  };
  /* ---- [1] 配方块：池子 → 反应池面板（缓存格 + 输出产物槽）；其他机器 → 单配方下拉 ---- */
  const poolPanel=(rInfo&&rInfo.isPool)?(function(){
    const slots=POOL_SLOT_MAX[rInfo.building.id], rl=RpoolOf(rInfo.first);
    const cells=RpoolCells(rl), over=cells.length>POOL_CELLS;
    const PH={'固态':['#8A8778','固'],'液态':['#2E8B9E','液'],'气态':['#7BA05B','气']};
    const cellBox=(c,i)=>{
      if(!c) return `<span class="lo-ccell empty">空</span>`;
      const ph=PH[c.phase]||['#8A8778','?'], overOne=over&&i>=POOL_CELLS;
      return `<span class="lo-ccell${overOne?' over':''}"
        title="${esc(c.name)} · R${c.rarity} · ${esc(c.phase)}${overOne?'（超出 '+POOL_CELLS+' 格）':''}">
        <span class="rr">${'★'.repeat(Math.max(1,Math.min(6,c.rarity|0)))}</span>
        <span class="nm">${esc(c.name)}</span>
        <span class="ph" style="background:${ph[0]}">${ph[1]}</span></span>`;
    };
    return `
    <div class="lo-rp">
      <div class="lo-ph">⚗️ 反应池 · <b>${esc(rInfo.building.name)}</b> <span class="lo-tag">v134 · 对齐游戏面板</span> — 缓存格 <b>${POOL_CELLS}</b> 个 · 可同时跑 <b>${slots}</b> 条反应${rInfo.count>1?(' · 会同时改选中的 '+rInfo.count+' 台同机种'):''}</div>
      <div class="c-sub" style="margin-top:6px"><span><b>缓存格</b>：占了 <b style="color:${over?RW_COL.bad:'inherit'}">${cells.length}</b>/${POOL_CELLS}（按已选反应的进料 + 出料去重推演）</span></div>
      <div class="lo-ccells">
        ${Array.from({length:Math.max(POOL_CELLS,cells.length)},(_,i)=>cellBox(cells[i],i)).join('')}
      </div>
      ${over?`<div class="c-sub" style="margin-top:4px"><span style="color:${RW_COL.bad}">⚠️ 超过 ${POOL_CELLS} 格 —— 游戏里这些料塞不进一栋，删掉一条反应或分成两栋</span></div>`:''}
      <div class="c-sub" style="margin-top:8px"><span><b>输出产物</b>（每个槽一条反应；同一条反应重复选不会提速 —— 要提产请加栋数）</span></div>
      <div style="display:flex;flex-direction:column;gap:4px;margin-top:4px">
        ${Array.from({length:slots},(_,i)=>{
          const rid=rl[i]||'', rr=rid?RbyId(rid):null, rt=rr?Rrate(rr):null;
          return `<div style="display:flex;align-items:center;gap:6px">
            <span class="lo-tag" style="flex:none">槽 ${i+1}</span>
            <select class="lo-sel" style="flex:1" onchange="LsetPoolSlot(${i}, this.value)">
              <option value=""${rid?'':' selected'}>— 空 —</option>
              ${rInfo.recipes.map(r=>`<option value="${esc(r.id)}"${rid===r.id?' selected':''}>${esc(Rsummary(r))}</option>`).join('')}
            </select>
            <span class="c-id" style="white-space:nowrap">${rt?('出 '+rt.out.map(x=>esc(x.name)+' '+x.perMin+'/分').join('、')):'—'}</span>
          </div>`; }).join('')}
      </div>
      <div class="c-sub" style="margin-top:6px"><span class="c-id">缓存格是**静态推演**（该栋各反应的料去重），不代表游戏内实时时序；同池并行的栋数口径见产线闭环报告。</span></div>
    </div>`;
  })():'';
  /* ⭐v135：池子的选择入口已改到「画布上点机器就地选」（LmacOpen）——左栏不再重复给（v104 同款：
     双入口语义混乱）。下面这份 poolPanel 仅作占位不再渲染。 */
  const recipeBlock=(rInfo&&rInfo.recipes.length)?(false?poolPanel:`
    <div class="lo-rp">
      <div class="lo-ph">🧾 配方 · <b>${esc(rInfo.building.name)}</b> — 可选 ${rInfo.recipes.length} 条${rInfo.count>1?' · 会同时改选中的 '+rInfo.count+' 台同机种':''}</div>
      <select class="lo-sel" onchange="LsetRecipe(this.value)">
        <option value=""${rInfo.chosen.length?'':' selected'}>— 未指定 —</option>
        ${rInfo.recipes.map(r=>`<option value="${esc(r.id)}"${rInfo.chosen.indexOf(r.id)>=0?' selected':''}>${esc(r.outcomes.map(x=>x.name).join('+'))} ← ${esc(r.ingredients.map(x=>x.name+(x.count>1?'×'+x.count:'')).join('+'))}</option>`).join('')}
      </select>
      ${(rInfo.chosen.length===1&&rRt)?`
        <div class="c-sub" style="margin-top:6px"><span>${esc(Rsummary(rInfo.recipe))}</span></div>
        <div class="c-sub" style="margin-top:4px"><span>单台产能 <b>${rRt.out.map(x=>esc(x.name)+' '+x.perMin+'/分').join('、')}</b> · 耗时 ${rRt.seconds} 秒/轮 · ${rRt.roundsPerMin} 轮/分</span></div>
        <div class="c-sub" style="margin-top:4px"><span>单台进料要：${esc(rCarrier(rRt))}</span></div>
        <div class="c-sub" style="margin-top:4px"><span class="c-id">接口序号是<b>同类接口内的下标</b>，且只是「这几种料可以走哪几个口」的<b>集合</b>，不是一对一 —— 详见页面说明。</span></div>`:''}
      ${rInfo.chosen.length>1?`<div class="c-sub" style="margin-top:6px"><span class="c-id">选中的这几台配方不一致（共 ${rInfo.chosen.length} 种）；下拉里选一条会统一改。</span></div>`:''}
    </div>`):'';
  /* ⭐v103 左栏气体选择块 → ⭐v104 改为**画布就地选**（博士：「想要点机器就地选」）：
     选中散布机时浮动条直接出现在机器正上方，左栏这份入口撤掉（双入口语义混乱）。
     范围/速率的完整说明挪进帮助手册💨区块。 */
  /* ---------- 产线闭环（排布器 v1）的输入块 + 报告 ---------- */
  const tgts=RwTargets();
  const tgtSel=`<select class="lo-sel" onchange="Ltgt(this.value)">
      ${L.tgt?'':'<option value="">— 选目标物品 —</option>'}
      ${tgts.map(t=>`<option value="${esc(t.id)}"${L.tgt===t.id?' selected':''}>${esc(t.name)}（${esc(t.machine)}${t.ways>1?' · '+t.ways+' 种做法':''}）</option>`).join('')}
    </select>`;
  const P=L.plan;
  /* ⑤-1 局部锁定：数一下锁了多少件（标题栏 / 按钮上的计数都用同一份） */
  const lockN=L.objs.filter(o=>o.lock).length;
  const lockMach=L.objs.filter(o=>o.lock&&o.planRole==='machine').length;
  const wAll=(P&&L.objs.some(o=>o.planRole))?P.res.warns.concat(P.route.warns):[];
  /* 第 1 层约束校验要用的量（提前算，报告里用） */
  const bw=Rbandwidth(L.objs);
  const th=Rtheories(pw.total, Lregion());
  const lim=RlimitChecks(L.objs);
  const st=Rstorage(pw.total);
  /* 原料需求直接用生成时算好的那份（口径见 rawNeedOf），不在这里重算一遍 */
  const rawNeed=(P&&P.rawNeed)?P.rawNeed:{};
  /* 评价函数按**当前画布**算：手动加/删了机器，分数也跟着变 */
  const sc=(P&&P.plan)?Rscore(P.res, P.plan, P.route, rawNeed):null;
    const planReport=(P&&L.objs.some(o=>o.planRole))?Rreport(P,pw,bw,th,lim,st,rawNeed,sc):'';
    /* ================================================================
       本函数（rCarrier）是左栏「配方 + 产线闭环」的整块 HTML 拼装。
       368 行、几乎全是模板字符串，改前先看下面四个路标定位：
         [1] 配方块 recipeBlock        —— 单台机器的配方下拉 + 产能读数
         [2] 产线闭环块 planBlock      —— 目标物品/速率/各开关按钮
         [3] 图例 legend / gasLegend   —— 接口图例 + 环境圈图例
         [4] 帮助手册 lo-help          —— 176 行静态说明文本（最长的一块，纯文档）
       顺序即渲染顺序；各块之间只通过上面这几个 const 传递，无交叉依赖。
       ================================================================ */
    /* ---- [2] 产线闭环块：目标物品 / 速率 / 各开关按钮 ---- */
    const planBlock=`<div class="lo-rp lo-plan">
      <div class="lo-ph">🏭 <b>产线闭环（排布器 v2）</b> <span class="lo-tag">2026-09-21</span> <span class="lo-tag">评价函数 v1</span> <span class="lo-tag">吞吐体检 v1</span> —— 选目标物品 + 速率，一键展开配方树 · 摆机器 · 连管线 · 打分</div>
      <div class="lo-bar" style="margin:8px 0 0">
        <span>目标物品：</span>${tgtSel}
        <span>速率：</span><input class="lo-num" type="number" min="1" step="1" value="${L.rate||10}" oninput="Lrate(this.value)"><span class="lo-tag">个/分钟</span>
        <button class="lo-size on" onclick="LawRun(Linit().tgt, Linit().rate)">生成产线</button>
        <button class="lo-size" onclick="LmtAdd()" title="⑥-2 多目标：再加一个目标物品一起展开 —— 多个目标共享的中间料只建一套，再分流给各条链">＋ 目标</button>
        <button class="lo-size ${L.selfLoop?'on':''}" onclick="LselfLoop()" title="开：环里的料（惰气那种）自己循环，报告给出「在哪台机器塞什么启动料」；关：那种料按外部输入处理">闭环自持：${L.selfLoop?'开':'关'}</button>
        <button class="lo-size ${L.shipIn?'on':''}" onclick="LshipIn()" title="开：出发地（方向见下方从/到下拉，默认四号谷地）集成工业能产的全部物品都能传（游戏口径：解锁过产能就行、仓库有没有无所谓）；这条链缺的原料/半成品排在最前，全量可传清单在折叠区里可搜索；选中谁，本地就不建谁和它的上游；关：原料一律按野外采集 / 本地自产">跨地区收货：${L.shipIn?'开':'关'}</button>
        <button class="lo-size ${L.pickShow?'on':''}" onclick="LpickToggle()" title="⑥-3 跨基地选点：多个目标放哪个地区更省 —— 按矿脉分布/机器限定/收货压力穷举分配，含口径①地区合计收货反推与口径②取货口建模；只出建议不摆画布">选点建议</button>
        <button class="lo-size ${lockMach?'on':'off'}" onclick="Lreroll()" title="锁定件原地不动，其余机器重新分层摆位并绕开它们（管线会整条重铺）。锁定用工具栏的「锁定选中」">重排其余${lockMach?('（锁 '+lockMach+' 台）'):''}</button>
        <button class="lo-size" onclick="LawClear()">清掉产线</button>
        <button class="lo-size" onclick="LsavePlan()" title="把这一版的分数存下来；改个参数再生成一条，两套会自动并排比">存方案比一比</button>
      </div>
      ${/* ⭐v81（博士：「我要在布局试摆里选怎么还是看不到啊」）：选货条提到产线面板里 ——
             开关一开立刻能选（没生成产线也显示，用的是轻量展开的候选），不用先跑报告再往下翻。
             报告的「跨地区收货」段在展示时面板让位（同一份候选不该出现两个网格，报告那份还带 tv 输入框更全）。 */
        /* ⭐v82 简化：有产线（L.plan && L.plan.res）时选货网格一律归报告 —— v82 起报告收货段
           不再要求 P.res.shipIn 非空（链外选中也要给提示和网格），面板条件若只看 shipIn 行数
           会跟报告同时出网格 → 双份。 */
        ((L.shipIn && (L.shipCands||[]).length && !(L.plan && L.plan.res)) ? LpickGridHtml(true) : '')}
        ${/* ⭐⑥-3：收货开着时，方向「从/到」下拉紧跟开关行（博士 2026-09-22：为未来新地区留口） */
          (L.shipIn ? LshipDirHtml() : '')}
        ${(L.pickShow ? RxlHtml() : '')}
      ${(L.mt||[]).map((x,i)=>`
      <div class="lo-bar" style="margin:4px 0 0">
        <span>＋目标${i+2}：</span>
        <select class="lo-sel" onchange="LmtTgt(${i},this.value)">
          ${x.id?'':'<option value="">— 选目标物品 —</option>'}
          ${tgts.map(t=>`<option value="${esc(t.id)}"${x.id===t.id?' selected':''}>${esc(t.name)}（${esc(t.machine)}${t.ways>1?' · '+t.ways+' 种做法':''}）</option>`).join('')}
        </select>
        <span>速率：</span><input class="lo-num" type="number" min="1" step="1" value="${x.rate||10}" oninput="LmtRate(${i},this.value)"><span class="lo-tag">个/分钟</span>
        <button class="lo-size" onclick="LmtDel(${i})">✕ 移除</button>
      </div>`).join('')}
      ${planReport}
    </div>`;
  const palHead=f1
    ? `<div class="lo-ph">只显示「${esc(f1)}」共 ${arr.length} ${f1==='物流件'?'件':'座'}
         <button class="lo-reset" onclick="Lonly('')">回到默认清单</button></div>`
    : `<div class="lo-ph">默认只列 ${grp.map(g=>`<b>${g[0]} ${cnt(g)}</b>`).join(' · ')}，共 ${arr.length} 项。<br>
         资源开采（矿机/水泵只能放野外矿点）、战斗辅助、装饰不列；中继器（含息壤中继器）、洒水机 / 给水器 / 滑索架、便捷存取站 / 留言信标，
         以及配置表里与正常版同名的<b>免电变体</b>（id 带 <code>_nop_</code>）同样不列 —— 要单独看某一类，用上方分类下拉选。
         ${presetBus?'<br><b>当前选了四号谷地的基地</b>：谷地的存取线由基地自动铺，所以源桩 / 基段这里不列（要自己摆就切到武陵的基地）。':''}</div>`;
  /* ---- [3] 图例：接口图例 + 环境圈图例 ---- */
  const legend=L.showPort?`<div class="lo-legend">
      <span><i class="inp"></i>进料口</span>
      <span><i class="outp"></i>出料口</span>
      <span>■ 方形=传送带口 · ● 圆形=管道口</span>
      <span>标记画在建筑<b>内侧</b>贴边 → 不会和邻格的传送带/管道压在一起</span>
      <span><i class="bg"></i>传送带件</span>
      <span><i class="pg"></i>管道件</span>
      <span>物流件四边的小色条 = 它的进/出边（青进橙出，半青半橙=双向）</span>
      <span>接口外圈亮绿 = 外侧那格已放同类物流件</span>
      <span>选了配方后：该配方要走的接口加一圈<b>深青环</b>，不走的口<b>淡化</b>（组级能力，非一对一）</span>
      <span>格子上多出的褐色小字 = 这台在<b>产出什么物品</b></span>
      <span>🔒 双线铁灰 = <b>已锁定</b>（拖不动 / 删不掉 / 转不了）</span>
    </div>`:'';
  /* ⭐v103→v104 环境圈图例：四色按游戏 UI 校准（稳定青蓝/湿润白/酸性橙黄/息壤翠绿）；
     通气 6 单位/分 = 官方面板「最低需求」实锤；机器须**完全**处于圈内才生效（官方文本）。 */
  const gasLegend=L.showGas?`<div class="lo-legend">
      <span>💨 半透明色块 = <b>气体散布机环境圈</b>（占地 3×3 外扩 5 → <b>13×13</b>，配置表 <code>FactoryVaporizerTable.rangeExtend</code>）</span>
      ${(DB.blueprint.envDisplay||[]).map(e=>`<span><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${envColorOf(e.id)};border:1px solid ${envEdgeOf(e.id)};vertical-align:-1px"></i> ${esc(envGasName(e.id))} → ${ENV_NAME[e.id]||('环境'+e.id)}环境</span>`).join('')}
      <span>多台重叠自然加深 · 色块不挡点击 · 圈色按游戏 UI 校准（近似色）</span>
      <span>机器须<b>完全处于圈内</b>才受影响 · 一台的圈可同时罩多台 · 通气最低 <b>6 单位/分</b>（官方面板）</span>
    </div>`:'';
  /* ---- [4] 帮助手册：176 行静态说明文本（本函数最长的一块，纯文档、无逻辑）----
     查功能说明、快捷键、口径解释，直接往下翻到这里；改 UI 逻辑不用看这一段。 */
  return `<details class="note lo-help" style="margin-bottom:12px">
      <summary><b>🖱 布局试摆（占地沙盘 + 接口 + 物流件）</b> —— 操作手册与数据附录 <span class="lo-tag">点开 / 收起</span></summary>
      <div style="margin-bottom:4px"><span class="lo-tag">接口标记 v3 · 2026-09-21</span> <span class="lo-tag">基地 / 地区分开 v1 · 2026-09-21</span> <span class="lo-tag">谷地预设线 v1 · 2026-09-21</span> <span class="lo-tag">评价函数 v1 · 2026-09-21 晚</span> <span class="lo-tag">约束补齐 v1 · 2026-09-21 晚</span> <span class="lo-tag">局部锁定 v1 · 2026-09-22</span> <span class="lo-tag">分流器多摆 v1 · 2026-09-22</span> <span class="lo-tag">连通率 v1 · 2026-09-22</span></div>
      <b>选基地就在工具栏最左边的「基地」下拉里</b> —— 8 片基地（四号谷地 4 + 武陵 4），
      选中会同时设好画布边长、并切到<b>该地区的存取线规则</b>；右边的 40/50/70/80 是<b>自由模式</b>，
      只设边长、不带地区规则。当前是哪种模式，看下拉右边那枚标签。<br>
      <b>格子太小、物流件上的流向箭头看不清？</b>工具栏的「格子」可切 <b>14 / 20 / 26 / 32 px</b>，
      默认 <b>20px</b>（比原来的 14px 大一圈）。物件、图标、网格线一起等比放大，已摆好的东西不会动；
      放到超出容器宽度时，画布区可以横向滚动。<br>
      左栏点选建筑 → 画布点击摆放（吸附网格）；<b>单击</b>已放建筑选中、<b>双击</b>移除；
      在<b>空白处拖拽</b>框选一片，拖动选中项可整体移动。
      选中后 <code>R</code> 原地转 90°（接口跟着转，能看出进料/出料换边）、<code>Del</code> 删除、
      <code>Ctrl+D</code> 复制、<code>Ctrl+Z</code> 撤销、<code>Ctrl+Y</code> 重做。<br>
      <b>🔒 局部锁定</b> <span class="lo-tag">路线图 ⑤-1 · 2026-09-22</span>：选中满意的件 → 工具栏「<b>锁定选中</b>」（或按 <code>L</code>），
      它会变成<b>双线铁灰 + 右上角小锁</b>：<b>拖不动、删不掉、转不了、也不参与复制</b>，双击同样不会误删。
      排布器那一栏的「<b>重排其余</b>」把这些锁定的机器当<b>固定件</b>（位置一格不动），
      其余机器重新分层摆位并<b>绕开</b>它们，管线整条重铺 —— 手调好的那几台再也不怕被下一次生成冲掉。
      想全放开就点「解锁全部」。<br>
      <b>物品进出口</b>：进料口青、出料口橙；<b>方形=传送带口，圆形=管道口</b>。
      标记贴在建筑<b>内侧</b>紧挨边框（不再是压格线跨出去一半）——
      所以邻格就算放了传送带/管道也不会互相压字；贴边位置本身就说明「口在这条边上」。
      鼠标悬停能看到是进/出、第几号、哪条边、以及<b>物料往哪边流</b>。
      接口外圈<b>亮绿</b> = 正对外侧那格已经放了同类物流件（接上了）。<br>
      <span class="lo-tag">看不到标记的话：先按 Ctrl+F5 强刷一次（旧版本页面没有这层标记）；</span>
      工具栏的「接口」按钮也能把它整块收起/放回。<br>
      <b>💨 气体散布机 · 环境圈</b> <span class="lo-tag">v104 · 2026-09-23</span><br>
      摆下气体散布机后，画布上它周围那块<b>半透明方形</b>就是环境范围 —— 占地 3×3 外扩 5 格 = <b>13×13</b>
      （配置表 <code>FactoryVaporizerTable.rangeExtend</code>；形状与游戏一致是<b>方形</b>，博士 2026-09-23 实测）。
      <b>点机器就地换气</b>：单击选中散布机 → 机器正上方浮出四个色块按钮，点一下即换通入的气体（圈色跟着变；
      框选多台一起换）—— v103 的左栏入口已并入这里。四种气体对应四种环境（游戏「本设备可生成的环境一览」实拍校准）：
      <b>惰气 → 稳定（青蓝）/ 水蒸气 → 湿润（白）/ 酸气 → 酸性（橙黄）/ 息壤气 → 息壤（翠绿）</b>
      （GenEnv 来自 <code>FactoryEnvDisplayTable</code>；v103 曾按特效资源名猜色把稳定/湿润对反，v104 按博士截图纠正）。
      多台的圈重叠会自然加深（湿润的白圈单独加了浓度，浅画布上也能看清）；色块<b>不挡点击 / 框选 / 摆放</b>；
      工具栏「环境圈」按钮可整层收起（收起不影响换气）。散布机持续吃气：最低 <b>6 单位/分</b>（官方面板「最低需求」口径）·
      储气上限 30。<br>
      <b>环境影响生产</b>（v104 起，报告会点名）：机器须<b>完全处于圈内</b>才受影响，一台的圈可同时罩多台；
      部分配方要在特定环境才生效 —— <b>气态反应炉</b>的气态灼铜（酸性）/ 实验息壤铜气（稳定）整组依赖环境，
      <b>提纯机</b>省料版（分离芯 2→1）与<b>天有洪炉</b>气液模式（富集碳 2 → 普通碳 1）没环境时游戏里跑不起来，
      产线报告的「💨 环境依赖」段会列出这些机器与所需气体；配方页这 5 条配方也标了「💨 需 XX 环境」。<br>
      <b>物流件</b>：左栏「物流件」一栏是配置表里的 10 件 1×1 件 —— 传送带、管道、汇流器、分流器、
      管道汇流器、管道分流器、物流桥、管道桥、物品准入口、管道准入口。
      每件在自己的四条边上画出<b>进/出</b>：<b>青条=进、橙条=出</b>，半青半橙=这条边双向。
      所以 <b>汇流器</b>是「左/下/右进、上出」，<b>分流器</b>是「下进、右/上/左出」，
      <b>物品准入口</b>是「下进上出」，<b>物流桥</b>四条边都双向；传送带/管道画一个流向箭头。<br>
      方向来自配置表每个接口的 <code>rotation.y</code>（那是<b>物料流向</b>，进料口在流向的反侧），
      已用全部 267 个建筑接口回代校验（266 个吻合，唯一例外是 3×1 的仓库存取口 —— 1 格厚时
      z=0 与 z=D-1 是同一条线，几何退化）。**方位只说画布的上/下/左/右，不声称游戏内的绝对方位。**<br>
      点选一件后<b>在空白格按住拖动</b>，沿拖拽主轴（横或竖）一次铺满一排；<code>R</code> 换走向。
      压到建筑或已有物流件的格子会自动跳过。<br>
      左栏默认只列 <b>仓储存取 / 基础生产 / 合成制造 / 电力 / 核心结构 / 物流件</b>，资源开采、战斗辅助、装饰不占位置。
      下面的计数区会给出物流件件数、传送带最长连通多少格、接口接上了几个，以及存取线的连接情况。<br>
      <b>仓库存取线</b>（源桩 / 基段 / 存货口 / 取货口）：配置表写明基段「需要和仓库存取线源桩或其他<b>生效的</b>基段相连」，
      存货口与取货口「只能贴靠仓库存取线放置」。这里照游戏的实际判定来 —— <b>两条边有接触就算相连</b>
      （可以横向并排、可以 L 形拐弯、错开一两格也行，不要求对齐）；没接上的件会在画布上<b style="color:#C0392B">标红</b>，
      和游戏里那块变红的预览是一个意思。计数区还能按建造区显示基段 / 源桩的满级上限。<br>
      <b>两个地区的仓库存取线规则完全不同，沙盘已经分开处理</b>（在「基地」里选一片就会切过去）：<br>
      · <b>四号谷地</b> —— 存取线由基地升级后<b>自动铺在基地外侧边缘</b>，玩家<b>不用摆</b>。
      所以选谷地时左栏<b>不给源桩 / 基段</b>，存货口 · 取货口也<b>不判「贴靠」</b>（判不了：预设线的坐标属关卡场景数据，
      配置表 <code>FactoryBusStructureTable</code> 里那 4 条记录的坐标全是 0）。
      配置表里谷地的存取线档位也确实没写数量，跟"不用自己摆"对得上。<br>
      &nbsp;&nbsp;<b>预设线已经画到画布上了</b>：画布<b>外缘</b>那条青色带子（源桩是角上的褐色方块）就是它 ——
      <b>整条在画布框外面，一格都不占、不挡摆放、也不进撤销栈</b>。
      摆法照基地面积页那张示意图：枢纽区 = 源桩占左上角 + 上边 / 左边铺满，副基地 = 左上一条边。
      ⚠️ <b>这是示意图的摆法，不是游戏内实测的绝对方位</b>（真实坐标属关卡场景数据，配置表里全是 0）——
      要跟游戏里对齐就用「旋转视角」转镜头，将来拿到实测截图 / 坐标再按实测修正。<br>
      · <b>武陵</b> —— 源桩 + 基段<b>要自己摆</b>，有满级上限（源桩 <b>2</b> / 基段 <b>12</b>·<b>25</b>，按建造区档位解锁），
      没接上的件<b style="color:#C0392B">标红</b>。这一套只管武陵，别套到谷地头上。<br>
      <b>生产配方：选中一台生产设施，左栏顶部就会出现配方下拉</b> <span class="lo-tag">配方 v1 · 2026-09-21</span><br>
      配置表里 <b>317 条机器配方</b>靠 <code>machineId</code> 挂到设施上，<b>18 台生产设施</b>有配方
      （灌装机 81 条 · 拆解机 75 条 · 精炼炉 28 条 … 数量差别很大，下拉里按 <code>sortId</code> 排）。
      选一条之后：格子上多出一行<b>褐色小字 = 产出物品</b>，悬停给出完整配方；
      该配方要走的接口加一圈<b>深青环</b>、不走的口<b>淡化</b>。<br>
      ⚠️ <b>接口标注是「集合」不是一对一</b>：配置表说的是「这份配方的<b>固态料</b>可以走 0/1/2 号传送带口、
      <b>流体料</b>走 3 号管道口」—— 能说"走哪几个口"，<b>不能说"1 号料进 1 号口"</b>，
      因为配方料数和接口数根本对不上（灌装机 7 个进料口、每份配方最多 2 种料）。
      判据链：<code>FactoryItemTable.phaseType</code>（1 固态 / 2 液态 / 4 气态）→ 固态走传送带口、液态气态走管道口，
      已用<b>全部 317 条配方</b>回代验证，需要的口 0 例漏声明。<br>
      另：配置表里有 <b>2 处「组多声明」</b>（天有洪炉两组的流体产出口序号 5 实际不存在）——
      已记在 <code>recipe_groups.json</code> 的 <code>anomalies</code> 里，属配置表自身的不一致，<b>不是解析错误</b>。<br>
      <b>产能与配比</b>：选中共 1 条配方时给出单台产能（每分几轮、每种料每分钟多少）与<b>进料要几条带</b>
      （固态 ÷ 30 个/分、流体 ÷ 120 个/分）。这套换算做成了<b>不碰 DOM 的纯函数</b>
      （<code>Rrate</code> / <code>Rcarriers</code> / <code>Rplan</code>）—— 博士要的「全基地产线最精简 + 产能最大化」
      排布器以后直接调它们，不用再重算一遍。<br>
      <b>产线闭环：选目标物品 + 速率 → 一键展开配方树 · 摆机器 · 连管线</b><br>
      <b>「闭环自持」开关</b>：有些料**只有回收路线**（惰气只能靠拆解罐子得到，而罐子又要用惰气灌）。
      关着的时候这种料按「外部输入」处理（链更短、更好摆）；打开就**让它自己循环**，
      并在报告里写清「**在哪台机器先塞什么、塞几个**」—— 这就是产线怎么启动。<br>
      <b>多台并联 + 吞吐体检</b> <span class="lo-tag">路线图 ②a · 2026-09-21 晚</span>：一层里上游 / 下游台数不同时，连 <b>max(上游, 下游, 载具上限反推出来的条数)</b> 条 ——
      保证**每台上游都有出线、每台下游都有进线**，并且线数**不低于单线载具上限算出来的条数**（传送带 30 个/分 · 管道 120 个/分）。
      报告里逐条给出「要几条 / 实际连了几条 / 单线负荷」，并判 <b>会堵 / 紧 / 通畅</b>（单线负荷 &gt; 上限 = 会堵；≥ 90% = 没有余量）。<br>
      &nbsp;&nbsp;⚠️ <b>实测结论：按当前配置表，真并联不会触发</b> —— 317 条配方里<b>单台产出最高的是砂叶粉末（粉碎机）15/分</b>，
      远低于单条传送带的 30/分（管道 120/分更高）。也就是说「一台机器一条线」天然就在上限内，不会堵。
      所以这一步的价值是：① 报告现在<b>把每条线的实测负荷摆出来</b>（不再只写一句「至少要几条并行」）；
      ② 数据以后变了（出现单台产能超上限的机器）它会自动多铺线，改数据不用改代码。<br>
      &nbsp;&nbsp;汇流 / 分流：只要下游进料口够，多台上游各接一条线就是「汇流」，**不需要汇流器**；同理出料口够就不用分流器 ——
      只有**口不够**（或能省下足够多条线，见 <code>RW_MERGE_MIN_SAVE</code>）时才会<b>自动摆</b>汇流器 / 分流器。<br>
      &nbsp;&nbsp;<b>分流器按「每 3 台下游一个」并排摆</b> <span class="lo-tag">⑤-2 · 2026-09-22</span>：
      分流器是 <b>1 进 3 出</b>，所以一台上游要喂 5 台下游就得摆 <b>2 个</b>（各占上游一个出料口）。
      ⚠️ 旧版<b>只摆一个</b>，第 4 台下游起既不接线也不报警（报告还写着「手动连 0」）—— 现在每一条没连上的线都会
      <b>逐条点名</b>（「还有 N 台下游没连上」），生成消息里也会报<b>汇流 X / 分流 Y</b> 的实际摆放数。<br>
      &nbsp;&nbsp;<b>连通率：难例会自动加宽机器间距再搜一轮</b> <span class="lo-tag">⑤-3 · 2026-09-22</span>：
      宽链的手动连多半是「机器挨太紧、竖缝里塞不下并行线」——所以当最优方案<b>还剩下手动连</b>时，
      会自动补跑一组<b>宽间距档（间 6 / 8 × 层内换行）</b>，谁分高用谁；<b>一次就全连通的链不会多花这份时间</b>。
      同时把择优口径改成「<b>手动连的权重压过线长</b>」（少一条线是功能缺陷，多铺几格只是效率问题）—— 实测全库
      52 个中大型工况里<b>零手动连从 44 个提到 51 个</b>，赤铜耐压罐@30 手动连 0。<br>
      <b>评价函数：给一套布局打分</b> <span class="lo-tag">路线图 ① · 2026-09-21 晚</span><br>
      生成产线后立刻给一个 <b>0~100 的分数</b>，五个成本项各自用「<b>理论下界 ÷ 实测</b>」算，再按固定权重合成：
      <b>紧凑度 20%</b>（行数；下界 = Σ 各层最高机器深 + 层数 × 最小通道）· <b>台数效率 20%</b>（下界 = Σ 需求 ÷ 单台产能）·
      <b>走线效率 30%</b>（物流格数；下界 = Σ 每段上下游中心的曼哈顿距离）· <b>集散效率 15%</b>（汇流 / 分流器个数，越少越好）·
      <b>料耗效率 15%</b>（整台凑整带来的产出富余，越少越好）。
      命中硬约束另扣：原料超全图采集上限 −25 · 超防御建筑上限 −15 · 超滑索上限 −10 · 走线连不上或单线会堵每条 −3。<br>
      （<b>协议容量不在其列</b> —— 它只约束集成核心区域<b>外</b>的野外设备，基地内不受限制。）<br>
      <b>「存方案比一比」</b>把当前这版分数存下来（最多 5 套）；换个速率或换个目标再生成一条，报告底部会把它们<b>并排列表比较</b>（分高的一列加粗）——
      这就是「这版比那版好」的依据。⚠️ 权重是**约定**（写在 <code>RW_W</code> 常量里），不是游戏真理：它的作用只是让排序口径固定、可复现、可调。<br>
      ⚠️ **仍然做不到的**：走线只做格内 L 形 / BFS 最短路，端口或走线被前面那条线占了的时候仍会连不上几条（报告里逐条点名，不静默丢）；
      不做全局最优布局搜索（那是路线图 ③ 的局部交换 / 平移搜索）；不做物料排队仿真。<br>
      <b>⚡ 电力与野外开采（配置表能取到的部分）</b><br>
      <b>用电</b>：每座建筑的用电取配置表 <code>powerConsume</code>，计数区实时给出「用电 X 电 · 用电设备 N 台」，
      还按分类拆分。<br>
      <b>发电规则</b>（教学文案原文，可复核）：<b>热能池</b>是发电设备，「利用<b>源矿</b>或<b>电池</b>提供电能」，
      <b>电池的发电效率高于源矿</b>；电网有「总发电功率」；<b>用电功率超过发电功率会消耗"存电"</b>（协议核心有存电），
      存电耗尽设备停转。<br>
      ⚠️ <b>每台热能池到底发多少电，配置表里没有</b> —— 建筑表只有 <code>needPower</code> / <code>powerConsume</code> 两个字段，
      <b>没有发电量</b>；文案也只做定性比较。所以发电侧用的是<b>社区数值</b>（报告里会标明出处，要当硬约束用建议游戏里核一下）。<br>
      <b>存电</b> <span class="lo-tag">路线图 ②c · 2026-09-21 晚</span>：协议核心有存电，<b>社区实测上限 10 万</b>（配置表里没有这一项）。
      用电超过基础发电（200）的部分就是在吃存电 —— 报告会给出<b>纯靠存电还能撑多少分钟</b>，以及按地区燃料补上这个缺口需要几台热能池。
      ⚠️ 存电是<b>缓冲不是电源</b>：撑的时间只是留给你补发电的，不能当长期方案。<br>
      <b>野外开采产量</b>（7 座采集建筑，按建筑表 <code>quickBarType=资源开采</code> 列全）：<br>
      · 采矿机 —— 便携源石矿机 / 电驱矿机 / 二型电驱矿机 都是 <b>20/分</b>（配置表 <code>msPerRound</code> 3000），
      可采 <b>源矿 / 紫晶矿 / 蓝铁矿</b>；<br>
      · <b>水驱矿机</b> —— <b>20/分</b>，可采 <b>赤铜矿</b>（**唯一能采赤铜矿的设备**），
      靠<b>清水自供能</b>（建筑表里它确实有 1 个管道进料口），<b>不需要通电</b>；每台耗水 <b>20/分</b>，一台水泵能供 <b>3 台</b>；<br>
      · 水泵 <b>60/分</b>；<b>二型耐酸水泵</b> <b>60/分</b>，抽 <b>沉积酸</b>（强腐蚀液体）；
      <b>气体收集泵</b> <b>20/分</b>，采 <b>惰气 / 息壤气</b>，无需通电。<br>
      <b>矿点清单 · 按小地图与纯度</b> <span class="lo-tag">2026-09-21 四次核查</span> <span class="lo-tag">数据版本 ${RoreMeta().dataVersion}</span><br>
      矿点位置与数量属**关卡场景数据**（配置表 561 张表全量查过：没有矿点实例表，只有
      <code>int_minerbase_originium/_quartz/_iron</code> 三种矿机基座交互标记，够不着坐标）。
      下面是社区资料，但**链条是闭合的** —— 官方 FAQ + 社区攻略 + TapTap 地图工具/地图集 + NGA 实测贴互相印证。<br>
      <b>⭐ 口径（四次核查后只剩一条）</b>：<b>满采量 = 矿点数 × 20/分</b>（高纯度档）—— <b>一个矿脉只放 1 台矿机</b>。
      证据：四号谷地全开产能 <b>源矿 560 / 紫晶 240 / 蓝铁 1080</b>（NGA 两帖 + 游民星空 + sticweb <b>四方一致</b>），
      除以 20 正好 = 28 / 12 / 54 个矿点，与 TapTap 地图工具的矿脉数 <b>逐项相等</b>。<br>
      <b>⚠️ 我前面两次算错就栽在这一步</b>：最早按「脉数 × 每脉 2~6 点」算，把全图源矿算成 2320~6960/分，
      <b>虚高 2~6 倍</b>（那 2~6 是矿脉上<b>矿石簇的外观数量</b>，不是能放几台矿机）；后来又拿「清波寨一个区」当赤铜矿全图。
      现在构建期有自检：按区求和、按地图求和、点数×20 三处对不上就当场报错。<br>
      <b>每个大地区的可采集最大理论值</b>（<span class="lo-tag">等博士核实</span>）：
      ${oreMapMaxTable()}
      <div class="c-sub" style="margin-top:4px"><span class="c-id">
      两列都是<b>实测</b>：四号谷地是 NGA / 游民星空 / sticweb / TapTap 四方一致；武陵是博士 2026-09-21 武陵简报截图逐区计数 —— 赤铜矿 23 高 + 5 低 = <b>510/分</b>、源矿 22 高 + 10 低 = <b>540/分</b>、蓝铁 6 高 = <b>120/分</b>，全部与游戏内 UI「理论最大开采值」一致 —— <b>闭环，无待核项</b>。</span></div>
      <b>按小地图看矿点（点数 / 满纯度产量）</b>：
      ${oreZoneTable()}
      <div class="c-sub" style="margin-top:6px"><span class="c-id">
      · 单位：源矿 / 紫晶矿 / 蓝铁矿 / 赤铜矿都是<b>矿点</b>（1 个矿点放 1 台矿机）；
        赤铜矿另有叫法「矿源点」，也是 1 点 1 台水驱矿机。<br>
      · 赤铜矿的 6 个产区里，清波寨 / 藏剑谷 / 试验园区 / 北部禁区<b>都放不了次级核心</b>，
        水泵的电要从武陵城或景玉谷拉过去；清波寨偏远那处要用暗管供水，首墩那处矿点与水场有高低差（栖云林地容易漏）。<br>
      · 现在只有「每个区多少个点」，<b>没有逐点坐标</b> —— 要排野外段还是需要截图或坐标。<br>
      · 「稀有矿物」（轻/中/重黯石、燎石、武陵石、协议纹石）是野外<b>手动拾取</b>的武器调谐石，不是矿脉；
        惰气 / 息壤气属<b>气体节点</b>（走气体收集泵）。<br>
      </span></div>
      <b>矿点纯度</b>：只有两档 —— 低纯度 <b>6 秒 1 个（10/分）</b>、高纯度 <b>3 秒 1 个（20/分）</b>；
      出矿速率<b>只由矿点纯度决定，与矿机型号无关</b>（型号只影响耗电）。<br>
      ⚠️ <b>纯度是按「区」分级解锁的</b>，不是整张大地图一起提：四号谷地的「阿伯莉采石场 / 源石研究园」前面几级就满纯度，
      「<b>供能高地要到 11 级</b>」才满；武陵「<b>景玉谷 8 级</b>」满纯度。所以同一版本、不同玩家的矿点纯度可能不同 ——
      本页按博士定的「当前版本地区最大值」口径，<b>一律按高纯度 20/分</b>算。
      想知道自己那份是哪档，在游戏里点矿机看有没有「采集效率提升」提示。<br>
      <b>滑索：只放野外，不摆进基地</b>（所以左栏试摆清单里没有滑索架 —— 博士 2026-09-21 定的）。
      滑索架射程 <b>80m</b>、长距滑索架 <b>110m</b>；建造区的 <code>travelPoleLimit</code>（枢纽区 20 / 谷地通道 10 …）约束的就是野外这一层。<br>
      ${(()=>{const m=RoreMeta(); return m.versionLog.length?('<b>版本记录</b>（版本接口 <code>dataVersion</code> = '+esc(m.dataVersion)
        +'，游戏 '+esc(m.gameVersion)+'）：'+m.versionLog.map(v=>'<br>　· <b>'+esc(v.version)+'</b>　'+esc(v.note)).join('')+'<br>'):'';})()}
      ⚠️ <b>水驱矿机 / 气体收集泵 / 二型耐酸水泵 这三台的速率，配置表里没有字段</b>
      （它们不在矿机表 / 泵表里）—— 上面这三个数是<b>社区实测</b>，已在数据里标 <code>rateSource</code> 并附来源链接；
      含水驱矿机的 <b>20/分</b> 是与其它矿机一致 + 「1 泵供 3 台、每台耗水 20/分」两条相互印证的推断。
      ⚠️ <b>矿脉纯度/矿点品级带来的加成属运行时数值</b>，配置表里没有 —— 所以都是**基础速率**。<br>
      <b>仍然不做</b>（配置表里没有依据，或本来就要玩家实际操作）：物料排队<b>仿真</b>（只按单线负荷做上限判定，不模拟堵料堆积）、
      传送带绕线<b>寻优</b>、供电<b>覆盖范围</b>校验（射程属关卡场景数据）。单条传送带上限 110 / 管道 80（配置表单位是「米」），
      验收时当参考值看；<b>格与米的换算配置表没给</b>（modelHeight/gridHeight 比例在 0.65～1.05 之间浮动，不是常数），
      所以本页一律按<b>格数</b>计，不做米换算。
    </details>
    ${legend}
    ${gasLegend}
    ${planBlock}
    <div class="lo-bar">
      <span>基地：</span>${baseSel}
      ${baseTag}
      <span class="lo-sep"></span>
      <span>画布尺寸：</span>${sizeBtns}
      <span class="lo-sep"></span>
      <span>格子：</span>${cellBtns}
      <span class="lo-sep"></span>
      <button class="lo-size" onclick="Lrot()" title="旋转选中的建筑 / 待放置朝向">旋转 90°（R）</button>
      <button class="lo-size" onclick="LrotView()" title="转镜头：整个画布连网格带已摆的东西一起转 90°，摆放数据不动">旋转视角（${L.viewRot||0}°）</button>
      <button class="lo-size" onclick="Ldup()">复制选中（Ctrl+D）</button>
      <button class="lo-size" onclick="Ldel()">删除选中（Del）</button>
      <span class="lo-sep"></span>
      <button class="lo-size ${lockN?'on':''}" onclick="LlockSel(true)" title="锁住选中的件：拖不动 / 删不掉 / 转不了，重排时位置不动（快捷键 L）">锁定选中${L.sel.length?('（'+L.sel.length+'）'):''}</button>
      <button class="lo-size ${lockN?'':'off'}" onclick="LunlockAll()" title="一次解锁画布上所有锁定的件">解锁全部${lockN?('（'+lockN+'）'):''}</button>
      <span class="lo-sep"></span>
      <button class="lo-size ${L.showPort?'on':''}" onclick="LtogglePort()">接口 ${L.showPort?'显示中':'已隐藏'}</button>
      <button class="lo-size ${L.showGas?'on':''}" onclick="LtoggleGas()" title="气体散布机的环境范围层：13×13 方形，圈色 = 通入的气体（数据 FactoryVaporizerTable + FactoryEnvDisplayTable）">环境圈 ${L.showGas?'显示中':'已隐藏'}</button>
      <button class="lo-size ${L.showPwr?'on':''}" onclick="LtogglePwr()" title="供电桩 / 中继器的配电覆盖层：供电桩 13×13、中继器 7×7（数据 FactoryPowerPoleTable.rangeExtend，与气体散布机同字段同口径；与游戏内实机若有出入按实测修正）">供电范围 ${L.showPwr?'显示中':'已隐藏'}</button>
      <span class="lo-sep"></span>
      <button class="lo-size ${L.undo.length?'':'off'}" onclick="Lundo()">撤销（Ctrl+Z）</button>
      <button class="lo-size ${L.redo.length?'':'off'}" onclick="Lredo()">重做（Ctrl+Y）</button>
      <button class="lo-size" onclick="Lclear()">清空</button>
    </div>
    ${baseTabs}
    ${recipeBlock}
    <div class="lo-wrap">
      <div class="lo-pal ${L.palOpen?'':'folded'}">${L.palOpen?`
        <div class="lo-bar" style="margin:0 0 4px">
          <button class="lo-size on" onclick="LpalToggle()"
            title="收起清单：变成画布左侧的窄竖条，画布让出宽度"
          >▾ 收起</button>
          <span class="lo-tag">${arr.length} 项${f1?(' · 「'+esc(f1)+'」'):''}</span>
        </div>
        ${palHead}${pal||'<div class="empty">没有匹配的分类</div>'}`:`
        <button class="lo-pal-tab" onclick="LpalToggle()"
          title="展开建筑清单（默认 ${arr.length} 项）：点一件建筑即拿起，选完自动收起"
        >◂ 建筑清单 ${arr.length}</button>`}
      </div>
      <div class="lo-stage">
        <div class="lo-canv" style="padding:${CELL+6}px">
          <div class="lo-canvas" style="--locell:${CELL}px;width:${L.size*CELL}px;height:${L.size*CELL}px;transform:rotate(${L.viewRot||0}deg)">${presetBand}${envLayer}${pwrLayer}${cells}${gasBar}${dlvPop}${macPop}</div>
        </div>
        <div class="c-sub" style="margin-top:8px">
          <span>已放 <b>${L.objs.length}</b> 个 · 占地 <b>${used}</b> 格</span>
          <span>画布 ${L.size}×${L.size} = <b>${totalCells}</b> 格 · 剩余 <b>${totalCells-used}</b> 格</span>
          <span>已选 <b>${L.sel.length}</b> 个</span>
          ${lockN?`<span>🔒 已锁定 <b>${lockN}</b> 个</span>`:''}
          ${L.pick?`<span>当前选择：<b>${esc(L.pick.name)}</b>（朝向 ${L.pickRot}° / ${LdirName(L.pickRot)}，占地 ${dm.w}×${dm.d}）</span>`:''}
        </div>
        <div class="c-sub" style="margin-top:4px">
          <span>物流件 <b>${lgs.length}</b> 件（传送带 ${beltN} · 管道 ${pipeN} · 汇流/分流/桥/阀 ${funcN}）</span>
          <span>最长连通段 <b>${longest}</b> 格</span>
          <span>接口已接 <b>${pOn}</b> / ${pAll}</span>
        </div>
        <div class="c-sub" style="margin-top:4px">
          <span>⚡ <b>用电</b>：<b>${pw.total}</b> 电 · 用电设备 <b>${pw.devices}</b> 台</span>
          ${Object.keys(pw.byCat).length?`<span class="c-id">${Object.keys(pw.byCat).map(k=>esc(k)+' '+pw.byCat[k]).join(' · ')}</span>`:''}
        </div>
        <div class="c-sub" style="margin-top:4px">
          ${/* ⭐v145/⭐v156：口径改成说明 —— 协议容量只约束集成核心区域**外**的野外设备，基地内不受限（博士 2026-09-24 游戏内确认）。
                ⭐v156 措辞修正：原来标题写「协议容量上限 N」，容易被读成"基地的容量上限"（与正文自相矛盾）。
                  改为「（野外设备参考）」并把数值定位成"该区野外上限"——本画布排布不受它约束。 */''}
          <span class="c-id">📶 协议容量（野外设备参考）<b>${bw.cap!=null?bw.cap:'—'}</b>${bw.cap!=null?('（'+esc(bw.zone||'本区')+'上限）'):'（未指定基地）'} —— <b>只约束集成核心区域外的野外设备，基地内排布不受它限制</b></span>
          <span class="c-id">（每座设备的 <code>bandwidth</code> 累加；上限取该建造区满级档 —— 配置表数据，此处仅作参考）</span>
        </div>
        ${presetBus?`
        <div class="c-sub" style="margin-top:4px">
          <span><b>仓库存取线：四号谷地由基地升级自动铺设（预设）</b> —— 源桩 / 基段不用自己摆，左栏也不提供；存货口 · 取货口直接贴预设线放置即可。</span>
        </div>
        <div class="c-sub" style="margin-top:4px">
          <span><b style="color:#7FA8A2">画布外缘那条青色带子就是预设存取线</b>（源桩是角上的褐色方块）。
          ${presetBand?'已经画出来了':'（当前这片基地没有可画的档位）'} —— 整条画在画布框<b>外面</b>，<b>一格都不占、也不挡摆放</b>。</span>
        </div>
        <div class="c-sub" style="margin-top:4px">
          <span>摆法照基地面积页那张示意图：<b>${(presZone&&(presZone.edges||1)>=2)?'源桩占左上角，与之相连的上边与左边铺满':'左上一条边铺满（副基地没有源桩）'}</b>。
          具体是哪条边随镜头变，要跟游戏里对齐就用工具栏的「旋转视角」。</span>
        </div>
        <div class="c-sub" style="margin-top:4px">
          <span class="c-id">⚠️ 这是<b>示意图的摆法</b>，不是游戏内实测方位 —— 真实坐标属关卡场景数据（配置表 <code>FactoryBusStructureTable</code> 记录在案但坐标全是 0）。</span>
          <span>也因此这一模式<b>不判「贴靠」</b>，不会出现红块。</span>
        </div>`:`
        <div class="c-sub" style="margin-top:4px">
          <span>存取线：源桩 <b>${nSrc}</b>${hongsCap?' / '+hongsCap.log_hongs_bus_source:''} · 基段 <b>${nBus}</b>${hongsCap?' / '+hongsCap.log_hongs_bus:''}${nBad?' · <b style="color:#C0392B">未连接 '+nBad+' 件</b>':''}</span>
          ${busZones.length?`<span>上限按：<select class="lo-sel" onchange="Lzone(this.value)">${busZones.map(z=>`<option value="${z.levelId}"${z.levelId===(curZone?curZone.levelId:'')?' selected':''}>${esc(z.domainName)}·${esc(z.zoneName)}</option>`).join('')}</select>满级档位算（只有武陵要给数量）</span>`:''}
          ${L.base?'':'<span class="c-id">自由模式未指定基地，这一块按武陵那套算；要精确对照就在上面「基地」里选一片</span>'}
        </div>
        ${nBad?`<div class="c-sub" style="margin-top:4px;color:#C0392B"><span>画布上标红的存取线件没接上：基段要挨着源桩（可直接，也可经其他基段传递，横向并排 / L 形都行）；存货口 · 取货口要贴靠存取线</span></div>`:''}`}
        ${(()=>{ const rp=Rpower(L.objs); return rp.total>0?`
        <div class="c-sub" style="margin-top:4px"><span>⚡ 已摆设备用电 <b>${rp.total}</b> 电（${rp.devices} 台用电设备）—— 这只是<b>用电侧</b>；发电侧（热能池烧源矿 / 电池）配置表里没有发电量</span></div>`:''; })()}
        <div class="c-sub" style="margin-top:4px"><span class="lo-msg">${esc(L.msg||'')}</span></div>
      </div>
    </div>`;
}

function renderMech(){
  let arr=DB.mechanics;
  if(kw){
    const s=kw.toLowerCase();
    arr=arr.filter(m=>m.name.toLowerCase().includes(s)||(m.desc||'').toLowerCase().includes(s));
  }
  if(!arr.length) return `<div class="empty">没有匹配的设施</div>`;
  return `<div class="list">`+arr.map(m=>{
    const o=openSet.has('m:'+m.id);
    return `<div class="card ${o?'open':''}" data-id="m:${esc(m.id)}">
      <div class="c-top">
        <span class="c-name">${esc(m.name)}</span>
        <span class="c-id">${esc(m.id)}</span>
        <span class="spacer"></span>
        <span class="c-cat ${m.domainNames[0]!=='全地区通用'?'acc':''}">${esc(m.domainNames.join('/'))}</span>
      </div>
      <div class="star">★ ${esc(mechLabel(m.mechanics))}</div>
      ${o?`<div class="detail"><div class="d-sec"><div class="d-h">游戏内描述原文</div><div class="c-desc">${esc(m.desc)}</div></div></div>`:''}
    </div>`;
  }).join('')+`</div>`;
}

function fmtIng(list){ return list.map(i=>`<b>${esc(i.name)}</b>×${i.count}`).join(' + ')||'(无)'; }

function renderRecipe(){
  let arr=DB.machine_recipes;
  if(f1) arr=arr.filter(r=>(r.machineCategory||'其他')===f1);
  if(kw){
    const s=kw.toLowerCase();
    arr=arr.filter(r=>r.id.toLowerCase().includes(s)||(r.machineName||'').toLowerCase().includes(s)||
      r.ingredients.some(i=>i.name.toLowerCase().includes(s))||
      r.outcomes.some(i=>i.name.toLowerCase().includes(s)));
  }
  if(!arr.length) return `<div class="empty">没有匹配的配方</div>`;
  const lim=arr.slice(0,200);
  /* ⭐v104 环境依赖标签：FactoryMachineCraftTable.gasEnv（build 注入成 DB.recipeEnv，仅 5 条非零）——
     配方要在对应气体环境里才生效（官方：提纯机省料版/洪炉气液模式/反应炉灼铜整组）。 */
  const _ENV_NM={1:'稳定',2:'湿润',3:'酸性',4:'息壤'};
  const _ENV_CL={1:'#3D9FD8',2:'#F4F7F8',3:'#E7AC3F',4:'#43B06E'};
  return `<div class="list">`+lim.map(r=>{
    const o=openSet.has('r:'+r.id);
    const ge=(DB.recipeEnv||{})[r.id];
    return `<div class="card ${o?'open':''}" data-id="r:${esc(r.id)}">
      <div class="c-top">
        <span class="c-name">${esc(r.machineName||'—')}</span>
        <span class="c-id">${esc(r.id)}</span>
        <span class="spacer"></span>
        ${ge?`<span class="c-cat" style="color:#1B6E9E" title="通入${({1:'惰气',2:'水蒸气',3:'酸气',4:'息壤气'})[ge]}制造${_ENV_NM[ge]}环境后才生效（气体散布机，最低 6 单位/分）">💨 需${_ENV_NM[ge]}环境</span>`:''}
        ${r.seconds!=null?`<span class="c-cat acc">${r.seconds} 秒</span>`:''}
      </div>
      <div class="formula">
        <span class="chain">${fmtIng(r.ingredients)}</span>
        <span class="arrow">→</span>
        <span class="chain">${fmtIng(r.outcomes)}</span>
      </div>
      ${o?`<div class="detail">
        ${r.desc?`<div class="d-sec"><div class="d-h">配方说明</div><div class="c-desc">${esc(r.desc)}</div></div>`:''}
        <div class="d-sec"><div class="d-h">技术参数</div>
          <div class="row"><span class="tag">配方案组</span><span>${esc(r.group||'—')}</span></div>
          <div class="row"><span class="tag">总进度 / 每轮</span><span>${r.totalProgress} / ${r.progressRound}</span></div>
          <div class="row"><span class="tag">每轮耗时</span><span>${r.msPerRound} ms</span></div>
          <div class="row"><span class="tag">设备分类</span><span>${esc(r.machineCategory||'—')}</span></div>
        </div>
      </div>`:''}
    </div>`;
  }).join('')+`</div>`+(arr.length>200?`<div class="empty" style="padding:20px">共 ${arr.length} 条，仅显示前 200 条，请细化搜索条件</div>`:'');
}

function renderBuild(){
  let arr=DB.build_recipes;
  if(kw){
    const s=kw.toLowerCase();
    arr=arr.filter(r=>(r.name||'').toLowerCase().includes(s)||r.id.toLowerCase().includes(s)||
      r.ingredients.some(i=>i.name.toLowerCase().includes(s)));
  }
  if(!arr.length) return `<div class="empty">没有匹配的建造配方</div>`;
  return `<div class="list">`+arr.map(r=>{
    const o=openSet.has('br:'+r.id);
    return `<div class="card ${o?'open':''}" data-id="br:${esc(r.id)}">
      <div class="c-top">
        <span class="c-name">${esc(r.name||r.id)}</span>
        <span class="c-id">${esc(r.id)}</span>
        <span class="spacer"></span>
        ${r.techDomains.map(d=>`<span class="c-cat acc">${esc(d)}</span>`).join('')}
        <span class="c-cat">R${r.rarity}</span>
      </div>
      <div class="formula">
        <span class="chain">${fmtIng(r.ingredients)}</span>
        <span class="arrow">→</span>
        <span class="chain">${fmtIng(r.outcomes)}</span>
      </div>
      ${o?`<div class="detail"><div class="d-sec"><div class="d-h">解锁信息</div>
        <div class="row"><span class="tag">科技树分组</span><span>${esc(r.groups.join(', ')||'—')}</span></div>
        <div class="row"><span class="tag">地区</span><span>${esc(r.techDomains.join('/')||'—')}</span></div>
        <div class="row"><span class="tag">可用等级</span><span>${r.usableLevel}</span></div>
      </div></div>`:''}
    </div>`;
  }).join('')+`</div>`;
}

function renderManual(){
  let arr=DB.manual_recipes;
  if(f1) arr=arr.filter(r=>r.domainName===f1);
  if(kw){
    const s=kw.toLowerCase();
    arr=arr.filter(r=>(r.name||'').toLowerCase().includes(s)||
      r.ingredients.some(i=>i.name.toLowerCase().includes(s)));
  }
  if(!arr.length) return `<div class="empty">没有匹配的手工配方</div>`;
  return `<div class="list">`+arr.map(r=>{
    const o=openSet.has('mn:'+r.id);
    return `<div class="card ${o?'open':''}" data-id="mn:${esc(r.id)}">
      <div class="c-top">
        <span class="c-name">${esc(r.name||r.id)}</span>
        <span class="c-id">${esc(r.id)}</span>
        <span class="spacer"></span>
        <span class="c-cat ${r.domainName!=='通用'?'acc':''}">${esc(r.domainName)}</span>
        ${r.rarity?`<span class="c-cat">R${r.rarity}</span>`:''}
      </div>
      <div class="formula">
        <span class="chain">${fmtIng(r.ingredients)}</span>
        <span class="arrow">→</span>
        <span class="chain">${fmtIng(r.outcomes)}</span>
      </div>
      ${o?`<div class="detail"><div class="d-sec"><div class="d-h">解锁信息</div>
        <div class="row"><span class="tag">默认解锁</span><span>${r.defaultUnlock?'是':'否'}</span></div>
        <div class="row"><span class="tag">展示类型</span><span>${r.showingType}</span></div>
      </div></div>`:''}
    </div>`;
  }).join('')+`</div>`;
}

function renderItem(){
  let arr=Object.values(DB.items);
  if(f1) arr=arr.filter(v=>'R'+v.rarity===f1);
  if(kw){
    const s=kw.toLowerCase();
    arr=arr.filter(v=>v.name.toLowerCase().includes(s)||v.id.toLowerCase().includes(s)||
      (v.desc||'').toLowerCase().includes(s)||(v.content||'').includes(s));
  }
  arr.sort((a,b)=>(b.rarity||0)-(a.rarity||0)||a.name.localeCompare(b.name,'zh'));
  if(!arr.length) return `<div class="empty">没有匹配的物品</div>`;
  const lim=arr.slice(0,150);
  return `<div class="list">`+lim.map(v=>{
    const o=openSet.has('i:'+v.id);
    return `<div class="card ${o?'open':''}" data-id="i:${esc(v.id)}">
      <div class="c-top">
        <span class="c-name">${esc(v.name)}</span>
        <span class="c-id">${esc(v.id)}</span>
        <span class="spacer"></span>
        <span class="c-cat">R${v.rarity}</span>
        ${v.producedBy.length?`<span class="c-cat acc">${v.producedBy.length} 种产出</span>`:'<span class="c-cat">原料</span>'}
        ${v.consumedBy.length?`<span class="c-cat">${v.consumedBy.length} 处消耗</span>`:''}
      </div>
      ${v.content?`<div class="c-desc" style="margin-top:6px"><span class="c-cat acc">${esc(v.content)}</span>${v.desc?` ${esc(v.desc)}`:''}</div>`:(v.desc?`<div class="c-desc" style="margin-top:6px">${esc(v.desc)}</div>`:'')}
      ${o?`<div class="detail">
        <div class="d-sec"><div class="d-h">产出途径</div>
          ${v.producedBy.length?v.producedBy.map(p=>`<div class="row">
            <span class="tag acc">${esc(p.machine)}</span>
            <span>×${p.count}</span>
            ${p.seconds!=null?`<span class="tag">${p.seconds} 秒</span>`:''}
            <span class="c-id">${esc(p.recipeId)}</span>
          </div>`).join(''):'<div class="row"><span class="tag">采集 / 原料，无制造配方</span></div>'}
        </div>
        <div class="d-sec"><div class="d-h">被消耗于</div>
          ${v.consumedBy.length?v.consumedBy.map(c=>`<div class="row">
            <span class="tag">${esc(c.machine)}</span>
            <span>×${c.count}</span>
            <span class="c-id">${esc(c.recipeId)}</span>
          </div>`).join(''):'<div class="row"><span class="tag">暂无下游配方</span></div>'}
        </div>
      </div>`:''}
    </div>`;
  }).join('')+`</div>`+(arr.length>150?`<div class="empty" style="padding:20px">共 ${arr.length} 条，仅显示前 150 条</div>`:'');
}

function renderOverview(){
  const c=DB.meta.counts;
  const cards=[
    ['建筑设施',c.buildings],['占地蓝图',c.blueprintEntries],['占格规格',c.footprintGroups],
    ['有基地的建造区',c.bases],['基地面积条目',c.baseAreas],['据点发展满级',c.domainLevels],
    ['物流接口',c.portEntries],['物流实体',c.logisticsEntities],['暗管设施',c.undergroundPipes],
    ['物流常量',c.logisticsConstants],['玩法规则',c.rules],
    ['生产配方',c.machineRecipes],['建造配方',c.buildRecipes],
    ['手工配方',c.manualRecipes],['关联物品',c.items],['机制数值',c.mechanicsEntries],
    ['培养舱配方',c.growCabin],['制造配方',c.manufacture],
  ].map(([l,n])=>`<div class="ov-card"><div class="ov-num">${n}</div><div class="ov-lbl">${l}</div></div>`).join('');

  const regs=Object.entries(DB.regions).map(([name,v])=>`
    <div class="row">
      <span class="tag ${name!=='全地区通用'?'acc':''}">${esc(name)}</span>
      <span>建筑 ${v.count}</span><span>需通电 ${v.powered}</span>
      <span>手工配方 ${v.manualRecipes||0}</span>
      <span>建造配方 ${v.buildRecipes||0}</span>
    </div>`).join('');

  return `<div class="note">
    <b>⚠ 数据边界（重要）</b><br>
    本知识库只收录游戏配置表（TableCfg）中的<b>静态数据</b>：设施名称、耗电、占地、配方、描述文本等。<br>
    <b>矿脉纯度产率、建设值/RDM 收益、地区建设等级加成</b>这类运行时数值<b>不在配置表内</b>，仍需游戏内实测。<br>
    好消息是：<b>射程、间距、供电范围等机制数值写在建筑描述文本里</b>，本库已自动抽取，见「机制数值」页。
  </div>
  <div class="note" style="margin-top:12px">
    <b>📐 蓝图数据说明</b><br>
    占地格数取配置表 <code>range.width / depth / height</code>，是<b>整数格</b>，可直接用于蓝图排布。<br>
    <code>modelHeight</code> 是模型实际高度（小数，单位米），<b>纯视觉，蓝图不要用</b>。<br>
    ${esc(DB.meta.blueprintNote||'')}
  </div>
  <div class="note" style="margin-top:12px">
    <b>🏗 基地面积是另一套来源</b><br>
    「基地面积」页里，<b>建设区域边长 / 单边存取口路数是社区实测</b>（不在配置表内）；<b>扩建价目、据点发展等级上限、蓝图硬上限来自 TableCfg</b>。
    两类数据在该页分开标注，引用时别混着说。
  </div>
  <div class="ov-grid">${cards}</div>
  <div class="d-sec"><div class="d-h">占格规格分组（同尺寸可共用蓝图网格）</div>
    ${DB.blueprint.footprintGroups.map(g=>`
      <div class="row">
        <span class="tag">${esc(g.footprint)}</span>
        <span>格高 ${g.height}</span><span>面积 ${g.area} 格²</span>
        <span><b>${g.count}</b> 座</span>
      </div>`).join('')}
  </div>
  <div class="d-sec" style="margin-top:20px"><div class="d-h">接口边分布统计（全部带接口设施）</div>
    <div class="row"><span class="tag">进料口</span><span>${Object.entries(DB.blueprint.edgeConvention.input).map(([k,v])=>esc(k)+' '+v).join('　')}</span></div>
    <div class="row"><span class="tag">出料口</span><span>${Object.entries(DB.blueprint.edgeConvention.output).map(([k,v])=>esc(k)+' '+v).join('　')}</span></div>
    <div class="row"><span class="tag">口径说明</span><span>${esc(DB.blueprint.edgeConvention.note)}</span></div>
  </div>
  <div class="d-sec"><div class="d-h">地区分布</div>${regs}</div>
  <div class="d-sec" style="margin-top:20px"><div class="d-h">数据来源</div>
    <div class="row"><span class="tag">项目</span><span>AKEDatabase（明日方舟：终末地非官方数据查询站）</span></div>
    <div class="row"><span class="tag">数据域</span><span>${esc(DB.meta.dataDomain)}</span></div>
    <div class="row"><span class="tag">游戏版本</span><span>${esc(DB.meta.gameVersion)}（hotfix ${esc(DB.meta.hotfix)}）</span></div>
    <div class="row"><span class="tag">构建时间</span><span>${esc(DB.meta.builtAt)}</span></div>
  </div>`;
}

function render(){
  let html='', n=0;
  /* 布局页左栏是可滚动长列表：每摆一座都重建 DOM，不还原 scrollTop 就会跳回顶部 */
  const keepPal = tab==='layout' ? $('.lo-pal') : null;
  const palTop = keepPal ? keepPal.scrollTop : 0;
  if(tab==='building'){ html=renderBuilding(); n=DB.buildings.length; }
  else if(tab==='rules'){ html=renderRules(); n=(DB.rules?DB.rules.rules:[]).length; }
  else if(tab==='blueprint'){ html=renderBlueprint(); n=DB.blueprint.buildings.length; }
  else if(tab==='layout'){ html=renderLayout(); n=DB.blueprint.buildings.length; }
  else if(tab==='base'){ html=renderBase(); n=DB.bases.zones.length; }
  else if(tab==='logistics'){ html=renderLogistics(); n=(DB.logistics.entities||[]).length; }
  else if(tab==='mechanics'){ html=renderMech(); n=DB.mechanics.length; }
  else if(tab==='recipe'){ html=renderRecipe(); n=DB.machine_recipes.length; }
  else if(tab==='build'){ html=renderBuild(); n=DB.build_recipes.length; }
  else if(tab==='manual'){ html=renderManual(); n=DB.manual_recipes.length; }
  else if(tab==='item'){ html=renderItem(); n=Object.keys(DB.items).length; }
  else { html=renderOverview(); }
  $('#out').innerHTML=html;
  if(palTop){ const p2=$('.lo-pal'); if(p2) p2.scrollTop=palTop; }
  /* ⭐v144 清单挂在画布左侧空白里，宽度按当时的可用空白算（画布位置不受影响） */
  if(tab==='layout') LpalFit();
  $('#cnt').textContent = tab==='overview' ? '' : `库中 ${n} 条`;
  refreshFilters();
}

/* ---------- 事件 ---------- */
let tmr=null;
$('#q').addEventListener('input',e=>{
  clearTimeout(tmr);
  tmr=setTimeout(()=>{ kw=e.target.value.trim(); openSet.clear(); render(); },160);
});
$('#f1').addEventListener('change',e=>{ f1=e.target.value; openSet.clear(); render(); });

$('#out').addEventListener('click',e=>{
  /* 布局页画布的交互走 mousedown/mousemove/mouseup（要支持拖拽），click 阶段只吞掉 */
  if(tab==='layout' && e.target.closest('.lo-canvas')) return;
  const card=e.target.closest('.card'); if(!card) return;
  const id=card.dataset.id;
  if(openSet.has(id)) openSet.delete(id); else openSet.add(id);
  render();
});
$('#out').addEventListener('mousedown',e=>{ if(tab==='layout') LonMouseDown(e); });
document.addEventListener('mousemove',LonMouseMove);
document.addEventListener('mouseup',LonMouseUp);
document.addEventListener('keydown',LonKeyDown);

render();
</script>
</body>
</html>
"""

def gen_cat_tables():
    """v132：CAT_COLOR/CAT_GLYPH/CAT_ORDER 动态生成。
    名单源 = bundle['categories']（AKEDatabase FactoryQuickBarTypeTable，build.py 动态读 raw 表），
    再兜底收集数据里实际出现过的全部 categoryName —— 上游加新组时新组自动获得
    灰底（#B4B2A9）+ 名字首字字标。特例字标沿用 v131：资源开采=采/装饰与其他=饰/
    核心结构=核（页面载入后改类的运行时名）/物流件=运（LO_LG 运行时包装名）。"""
    cats = bundle.get("categories") or {}
    names = dict(cats.get("names") or {})
    order = list(cats.get("order") or [])
    seen = []
    def see(c):
        if c and c not in seen:
            seen.append(c)
    for x in (bundle.get("buildings") or []):
        see((x or {}).get("categoryName"))
    bp = bundle.get("blueprint") or {}
    for x in ((bp.get("buildings") if isinstance(bp, dict) else bp) or []):
        see((x or {}).get("categoryName"))
    for x in (bundle.get("mechanics") or []):
        see((x or {}).get("categoryName"))
    for e in ((bundle.get("logistics") or {}).get("entities") or []):
        see((e or {}).get("categoryName"))
    official = [names[i] for i in order if i in names]
    tail = [c for c in seen if c not in official and c not in ("核心结构", "物流件")]
    seq = ["核心结构"] + official + tail
    for must in ("装饰与其他", "物流件"):     # catColor/catGlyph 的 fallback 依赖这两键，强制保证
        if must not in seq:
            seq.append(must)
    COLOR_KNOWN = {"物流": "#8E86C9", "资源开采": "#C7B57A", "仓储存取": "#A9C7C2",
                   "基础生产": "#9FB4C7", "合成制造": "#C79A9A", "电力": "#E4C36A",
                   "功能设备": "#B8C79B", "战斗辅助": "#C79BA8", "装饰与其他": "#D3D0C7",
                   "核心结构": "#C98A5E", "物流件": "#8E86C9"}
    GLYPH_KNOWN = {"物流": "流", "资源开采": "采", "仓储存取": "储", "基础生产": "基",
                   "合成制造": "合", "电力": "电", "功能设备": "功", "战斗辅助": "战",
                   "装饰与其他": "饰", "核心结构": "核", "物流件": "运"}
    color, glyph, corder = {}, {}, {}
    for i, c in enumerate(seq):
        color[c] = COLOR_KNOWN.get(c, "#B4B2A9")
        glyph[c] = GLYPH_KNOWN.get(c, (c[0] if c else "?"))
        corder[c] = i
    def jso(d):
        return "{" + ",".join("'" + str(k).replace("'", "\\'") + "':"
                              + json.dumps(v, ensure_ascii=False) for k, v in d.items()) + "}"
    return ("const CAT_COLOR=%s;\nconst CAT_GLYPH=%s;\n"
            "/* 上三表由构建时动态生成（v132）：官方组序 = FactoryQuickBarTypeTable.priority（面板从上到下），\n"
            "   核心结构（快捷建造位）排最前，装饰与其他、物流件（LO_LG 包装名）垫底；\n"
            "   上游加新组自动获得灰底+首字标，见 tools/build_html.py gen_cat_tables()。 */\n"
            "const CAT_ORDER=%s;" % (jso(color), jso(glyph), jso(corder)))

cat_js = gen_cat_tables()
html = HTML.replace("__PAYLOAD__", payload).replace("/*__CAT_TABLES__*/", cat_js)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(html)

print(f"生成: {OUT}")
print(f"  内联数据 {round(len(payload)/1024,1)} KB")
print(f"  最终文件 {round(os.path.getsize(OUT)/1024,1)} KB")
