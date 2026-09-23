# -*- coding: utf-8 -*-
"""fetch_raw.py —— 从 AKEDatabase 数据域拉取游戏配置表（TableCfg）到 `raw/`

背景：本项目的 `raw/` 是游戏解包原文，**按版权策略不入库、不上云**，因此新克隆的副本里
没有它。本脚本让任何人都能一条命令把 `raw/` 补齐 —— 把「raw 不上云」从自我约束变成
可持续策略：数据留在本地、随时能重建。

数据域地址（**不支持目录浏览**，只能按表名逐个取）：
    https://data.akedata.wiki/public/<版本>/<hotfix>/TableCfg/<表名>.json

用法（在知识库任意位置）：
    python tools/fetch_raw.py                          # 拉全部表到 raw/（已存在的跳过）
    python tools/fetch_raw.py --dry-run                # 只打印将拉什么，不下载
    python tools/fetch_raw.py --only ItemTable RewardTable
    python tools/fetch_raw.py --ver 1.6.0 --hotfix xxxxxxx-x   # 换游戏版本
    python tools/fetch_raw.py --force                  # 覆盖已存在的文件
    python tools/fetch_raw.py --out-dir /path/to/raw   # 指定落点（默认项目根 raw/）

默认版本取自 `data/meta.json` 的 `gameVersion` / `hotfix`，与当前数据包同源。

拉完之后（游戏版本更新时的完整流程）：
    python tools/fetch_raw.py      # 1. 补齐/更新 raw/
    python tools/build.py          # 2. 重建 data/*.json（自动刷新 raw_baked.json）
    python tools/build_html.py     # 3. 重建成品页

退出码：0 = 无失败；1 = 有表失败（清单见末尾）。
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
DEF_OUT = os.path.join(PROJ, "raw")
META = os.path.join(PROJ, "data", "meta.json")
DOMAIN = "https://data.akedata.wiki"

# 当前数据包实际用到的表（与既有 raw/ 目录一致；新增表用 --only 追加即可）
TABLES = [
    "CharGatherBehaviourTable", "DomainDataTable", "FacBlueprintConst",
    "FactoryBoxValveTable", "FactoryBuildingItemTable", "FactoryBuildingTable",
    "FactoryBuildingTypeToNodeType", "FactoryBusStructureTable", "FactoryConst",
    "FactoryEnvDisplayTable", "FactoryFluidContainerTable", "FactoryFluidPumpInTable",
    "FactoryFluidPumpOutTable", "FactoryFluidValveTable", "FactoryFreeBusTable",
    "FactoryGridBeltTable", "FactoryGridConnecterTable", "FactoryGridRouterTable",
    "FactoryHubCraftTable", "FactoryItem2LogisticIdTable", "FactoryItemTable",
    "FactoryLevelRegionTable", "FactoryLiquidConnectorTable", "FactoryLiquidPipeTable",
    "FactoryLiquidRouterTable", "FactoryMachineCraftGroupTable",
    "FactoryMachineCraftTable", "FactoryManualCraftTable", "FactoryMinerTable",
    "FactoryNodeTypeToBuildingType", "FactoryPanelStoreTable",     "FactoryPowerPoleTable", "FactoryQuickBarTypeTable",
    "FactoryRegionTable", "FactoryResourceItemId2MachineIdTable",
    "FactoryResourceItemId2TagIdTable", "FactorySpecialPowerPoleTable",
    "FactoryUndergroundPipeTable", "FactoryVaporizerTable", "I18nTextTable_CN",
    "InteractiveMarkDataTable", "ItemGatherTextTable", "ItemShowingTypeTable",
    "ItemTable", "ItemTypeTable", "LevelDescTable", "LevelGradeTable", "MapIdTable",
    "MapMarkCategoryTable", "MapMarkInsTable", "MapMarkTempTable", "MapMarkTypeTable",
    "MapMarkTypeTempTable", "RewardTable", "SceneAreaTable",
    "SceneCollectableItemTable", "SceneConst", "SettlementBasicDataTable",
    "SettlementLevelPOIMapTable", "SpaceshipGrowCabinFormulaTable",
    "SpaceshipGrowCabinSeedFormulaTable", "SpaceshipManufactureFormulaTable",
    "SpecialLevelToMapTable", "TrackMapPointTable", "WorldEnergyPointConst",
    "WorldEnergyPointGroupTable", "WorldEnergyPointTable",
]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def meta_version() -> tuple[str, str]:
    try:
        with open(META, encoding="utf-8") as f:
            m = json.load(f)
        return str(m.get("gameVersion", "")), str(m.get("hotfix", ""))
    except Exception:
        return "", ""


def url_of(ver: str, hotfix: str, table: str) -> str:
    return "%s/public/%s/%s/TableCfg/%s.json" % (DOMAIN, ver, hotfix, table)


def fetch(url: str, timeout: float = 120.0, tries: int = 3) -> bytes:
    """下载；失败重试。返回原始字节。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "fetch_raw/1.0", "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read()
        except Exception as e:          # noqa: BLE001 - 网络错误一律重试
            last = e
            if i + 1 < tries:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(str(last))


def kb(n: int) -> str:
    return "%.1f KB" % (n / 1024.0)


def main() -> int:
    dver, dhot = meta_version()
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--ver", default=dver)
    ap.add_argument("--hotfix", default=dhot)
    ap.add_argument("--out-dir", dest="out_dir", default=DEF_OUT)
    ap.add_argument("--only", dest="only", nargs="*", default=[])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-verify", action="store_true", help="跳过 JSON 解析校验")
    a, _ = ap.parse_known_args()

    if not a.ver or not a.hotfix:
        print("缺版本信息：用 --ver / --hotfix 指定，或确保 data/meta.json 可读", file=sys.stderr)
        return 2

    tables = a.only or TABLES
    os.makedirs(a.out_dir, exist_ok=True)
    print("目标: %s" % a.out_dir)
    print("版本: %s / %s　表数: %d　并发: %d%s"
          % (a.ver, a.hotfix, len(tables), a.workers, "　(dry-run)" if a.dry_run else ""))

    if a.dry_run:
        for t in tables:
            dst = os.path.join(a.out_dir, t + ".json")
            flag = "覆盖" if (a.force or not os.path.exists(dst)) else "跳过(已存在)"
            print("   %-40s %s" % (t, flag))
        return 0

    results: dict[str, tuple[str, int]] = {}

    def one(t: str) -> None:
        dst = os.path.join(a.out_dir, t + ".json")
        if os.path.exists(dst) and not a.force:
            results[t] = ("SKIP", os.path.getsize(dst))
            return
        try:
            data = fetch(url_of(a.ver, a.hotfix, t))
            if not a.no_verify:
                json.loads(data.decode("utf-8"))        # 校验是合法 JSON
            with open(dst, "wb") as f:
                f.write(data)
            results[t] = ("OK", len(data))
        except Exception as e:                           # noqa: BLE001
            results[t] = ("FAIL:%s" % str(e)[:60], 0)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        list(pool.map(one, tables))

    # 日志（沿用 raw/_download_log.txt 既有格式）
    lines = []
    for t in tables:
        st, size = results.get(t, ("FAIL:未执行", 0))
        lines.append("%s   %s  %s" % (st if st.startswith("FAIL") else st.ljust(4), t,
                                      kb(size) if size else "-"))
    with open(os.path.join(a.out_dir, "_download_log.txt"), "w", encoding="utf-8") as f:
        f.write("\ufeff" + "\n".join(lines) + "\n")

    ok = [t for t in tables if results.get(t, ("", 0))[0] == "OK"]
    skip = [t for t in tables if results.get(t, ("", 0))[0] == "SKIP"]
    fail = [t for t in tables if results.get(t, ("", 0))[0].startswith("FAIL")]
    total = sum(results.get(t, ("", 0))[1] for t in tables)

    print("\n完成 %.1fs　OK %d / SKIP %d / FAIL %d　共 %s"
          % (time.time() - t0, len(ok), len(skip), len(fail), kb(total)))
    for t in fail:
        print("   FAIL %s: %s" % (t, results[t][0]))
    if fail:
        return 1
    print("下一步: python tools/build.py  →  python tools/build_html.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
