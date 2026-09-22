#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bake_raw.py —— 把 build_html.py 需要的 raw 派生数据预烘焙进 data/raw_baked.json

为什么存在（2026-09-23，博士定策略「版权风险最低」）：
  raw/ 是游戏解包 TableCfg（14.3 MB，含 I18nTextTable_CN 11.4 MB 全文案），
  版权归鹰角网络。上云 = 数据落到第三方服务器，风险等级升高。
  → 策略：raw/ 一张表都不上云（本地保留 + .gitignore）。
  → 但 build_html.py 依赖 raw 做注入层加工（v103 环境圈 / v104 recipeEnv / v109 出货表）。
  → 解法：把「raw → 注入字段」的加工在这里跑一次，落成 data/raw_baked.json（约 30 KB），
     build_html.py 优先读烘焙文件，缺了才回落读 raw/。

烘焙产物 = 与 raw 加工结果字节等价，但不含任何游戏原文案（物品名走 data/items.json，
剩余缺名的走 I18n 反查后的**结果名**，不是整张 I18n 表）。

复现：删掉 data/raw_baked.json 再跑 tools/build.py 或本脚本即可（需本地有 raw/）。
"""
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "raw")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "raw_baked.json")

# build_html.py 读到的 raw 表（顺序固定，指纹用）
RAW_TABLES = (
    "FactoryVaporizerTable.json",
    "FactoryEnvDisplayTable.json",
    "FactoryMachineCraftTable.json",
    "FactoryItemTable.json",
    "I18nTextTable_CN.json",
    "ItemTable.json",
)


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def jload(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    if not os.path.isdir(RAW):
        print("✗ 缺 raw/ 目录，无法烘焙（这是正常的：克隆到无 raw 的机器时不需要烘焙）")
        return 1

    files = {}
    for t in RAW_TABLES:
        p = os.path.join(RAW, t)
        if not os.path.exists(p):
            print("✗ 缺 raw/%s，无法烘焙" % t)
            return 1
        files[t] = {"size": os.path.getsize(p), "sha256_16": sha16(p)}

    vap = jload("FactoryVaporizerTable.json")
    env = jload("FactoryEnvDisplayTable.json")
    mct = jload("FactoryMachineCraftTable.json")
    fit = jload("FactoryItemTable.json")
    itn = jload("I18nTextTable_CN.json")
    itab = jload("ItemTable.json")

    # ---- v103：环境色表 ----
    env_list = []
    for gid in sorted(env, key=lambda x: int(x)):
        e = env[gid]
        eff = str(e.get("EnvEffect", ""))
        c = eff.split("scope_")[1].split("_")[0] if "scope_" in eff else "gray"
        env_list.append({"id": int(gid), "color": c,
                         "icon": str(e.get("EnvIconAtlas", ""))})

    # ---- v103：散布机 ----
    GAS_NAMES = {"item_gas_inert": "惰气", "item_gas_water": "水蒸气",
                 "item_gas_acid": "酸气", "item_gas_xiranite": "息壤气"}
    v1 = vap.get("vaporizer_1") or {}
    vaporizer = {
        "rangeExtend": v1.get("rangeExtend") or {},
        "gasGroups": [
            {"item": g.get("consumeItem"),
             "name": GAS_NAMES.get(g.get("consumeItem"), str(g.get("consumeItem"))),
             "rate": g.get("consumeRate"), "cap": g.get("consumeRateUpperLimit"),
             "env": g.get("genEnv")}
            for g in (v1.get("groups") or [])
        ],
    }

    # ---- v104：配方 → 环境依赖 ----
    recipe_env = {}
    for rid, r in mct.items():
        ge = r.get("gasEnv") or 0
        if ge:
            recipe_env[rid] = ge

    # ---- v109：协议核心可出货物品 ----
    #   名字优先取 data/items.json（已清洗），缺失才走 I18n 反查；只落**结果名**，不落整张 I18n。
    items_db = {}
    ip = os.path.join(DATA, "items.json")
    if os.path.exists(ip):
        with open(ip, encoding="utf-8") as f:
            items_db = json.load(f)
    hub_domain = {"1": "domain_1", "2": "domain_2"}
    hub_items = {}
    noname = 0
    for iid, iv in fit.items():
        dl = iv.get("deliverItemTypeList") or []
        if not dl:
            continue
        doms = []
        for v in dl:
            d = hub_domain.get(str(v))
            if d and d not in doms:
                doms.append(d)
        if not doms:
            continue
        nm = (items_db.get(iid) or {}).get("name")
        if not nm:
            nid = ((itab.get(iid) or {}).get("name") or {}).get("id")
            nm = itn.get(str(nid)) if nid is not None else None
            if not nm:
                nm = iid
                noname += 1
        hub_items[iid] = {
            "name": nm,
            "rarity": ((items_db.get(iid) or {}).get("rarity")
                       or (itab.get(iid) or {}).get("rarity") or 1),
            "domains": doms,
        }

    baked = {
        "_note": "由 tools/bake_raw.py 从 raw/ 烘焙，勿手改；raw 在本地不复制的机器上靠它构建",
        "_bakedAt": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "_rawFiles": files,
        "vaporizer": vaporizer,
        "envDisplay": env_list,
        "recipeEnv": recipe_env,
        "hubItems": hub_items,
        "hubDomainMachine": {"domain_1": "sp_hub_1", "domain_2": "sp_hub_1"},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(baked, f, ensure_ascii=False, indent=1, sort_keys=False)
    print("✓ 烘焙完成:", os.path.relpath(OUT, ROOT), "%.1f KB" % (os.path.getsize(OUT) / 1024))
    print("  vaporizer 气体 %d 种 · envDisplay %d 条 · recipeEnv %d 条 · hubItems %d 件（名字待补 %d）"
          % (len(vaporizer["gasGroups"]), len(env_list), len(recipe_env), len(hub_items), noname))
    print("  指纹: %s" % ", ".join("%s=%s" % (k.split("Table")[0].replace("Factory", "").replace(".json", ""),
                                              v["sha256_16"]) for k, v in files.items()))
    return 0


if __name__ == "__main__":
    sys.exit(build())
