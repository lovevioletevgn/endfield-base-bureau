# 终末地基建知识库

从 AKEDatabase 数据域提取的《明日方舟：终末地》基建数据包，用于攻略内容生产时的数值核对。

**数据版本**：游戏 1.5.3（hotfix 10024360-6）· 构建于 2026-09-19
**数据来源**：[AKEDatabase](https://github.com/NagiYume/AKEDatabase) / `data.akedata.wiki`

---

## 🔗 在线体验（无需安装）

**👉 <https://workbuddy.link/p/YQO3ePeFiFgF6BrMKIpFbs>**

完整成品页托管在 WorkBuddy 资料库，打开即用 —— 查询、蓝图俯视图、产线排布器全都在里面，不用装 Python、不用 clone、不用构建，也**不需要注册或登录**。这条链接始终指向最新发布版，URL 永远不变。

| | 在线版 | 本地版 |
|---|---|---|
| 打开方式 | 点上面的链接 | clone 后跑 `tools/build_html.py` |
| 需要环境 | 浏览器 | Python 3.8+ |
| 网络 | 需要 | **完全离线** |
| 适合 | 快速查一个数、分享给别人 | 自己改代码、批量查、离线使用 |

> 仓库里**不含** `终末地基建查询.html` —— 它是构建产物（约 1.4 MB），可由 `data/` + `tools/` 完整重建，纳入版本控制会让每次改动都产生 1.4 MB 的 diff。想要文件就本地构建，想要直接用就走在线版。
>
> 仓库根目录的 `index.html` 是一页纯静态介绍页（**需要 clone 后本地打开**，未启用 GitHub Pages）。它同时兼任托管页的入口跳板：在 WorkBuddy 托管域下打开时自动跳转到成品页。

> ⚠️ **对外分享只写上面这条 `workbuddy.link/p/` 短链**（免登录、URL 永不变）。`workbuddy.cn/space/d/...` 形式是登录态入口，访客打开会被要求登录，别拿它分享；托管页另有一类含版本号的静态直链（形如 `.../page/<节点>/<版本号>/...`），**每次发布都会变**，且会把整个产物树暴露在无需登录的地址上 —— 都不要写进文档、README、聊天记录或任何长期留存的地方。

---

## 快速开始

**打开查询界面**：双击 `终末地基建查询.html`。单文件、无外部依赖、离线可用。

**命令行查询**：

```bash
python tools/ake.py 统计                    # 看数据包内容
python tools/ake.py 建筑 滑索                # 按关键词查建筑
python tools/ake.py 建筑 --分类 电力设施      # 按分类列
python tools/ake.py 蓝图 --规格              # 按占格规格分组（搭蓝图用）
python tools/ake.py 蓝图 精炼炉              # 占地格数 + 接口平面图
python tools/ake.py 蓝图 --接口 --详细        # 只列有接口的，带坐标明细
python tools/ake.py 基地                    # 各基地建设区面积 + 扩建价目 + 据点建造上限
python tools/ake.py 基地 --详细              # 据点发展等级逐级上限矩阵
python tools/ake.py 基地 枢纽区              # 查某个建造区
python tools/ake.py 物流                    # 物流规则总览（吞吐 + 连接常量）
python tools/ake.py 物流 --常量              # 全部全局物流常量
python tools/ake.py 物流 --蓝图码            # 蓝图系统规则（码前缀/上限/有效期）
python tools/ake.py 规则                    # 玩法机制规则（开采/无线传输/管道/区域限制）
python tools/ake.py 规则 无线               # 搜规则，附原文证据可复核
python tools/ake.py 数值                    # 列出所有带机制数值的设施
python tools/ake.py 物品 砂叶粉末            # 查物品及产出/消耗链路
python tools/ake.py 树 息壤                 # 追溯完整上下游链（跨机器/建造/手工三张配方表）
python tools/ake.py 建造 滑索                # 造一个建筑要什么材料
python tools/ake.py 手工 --地区 武陵         # 手工配方按地区筛
python tools/ake.py 地区                    # 地区概览
```

> `ake.py 树` 会在**三张配方表**（机器 / 建造 / 手工）里联合查找。早先只查机器表，导致 169 条建造/手工配方在下游链里被静默丢掉、只显示「需要:」后面空一格——已修，现在会标出 `[建造配方]` / `[手工配方]` 来源表。

---

## 目录结构

```
终末地基建知识库/
├── index.html              ← 静态介绍页（GitHub 用；托管页上兼任自动跳转入口）
├── 终末地基建查询.html      ← 本地查询界面（构建产物，双击打开）
├── README.md               ← 门面：在线体验 / 快速开始 / 目录 / 版权 / 文档索引
├── docs/                   ← 详细文档（2026-09-24 自 README 拆分）
│   ├── 数据手册-蓝图.md              占格 / 接口 / 俯视图 / 试摆
│   ├── 数据手册-玩法与物流.md        玩法六则 / 物流 / 矿点 / 面积 / 速查
│   └── 维护与更新.md                数据边界 / 更新流程 / 回归基线
├── 排布器版本演进记录.md    ← 排布器功能演进全史（路线图 + vNN 版本日志）
├── 排布器算法地图.md        ← build_html.py 排布器函数阅读索引
├── raw/                    ← 原始 TableCfg（未处理，约 18 MB；不入库，fetch_raw.py 补齐）
│   ├── FactoryBuildingTable.json
│   ├── FactoryMachineCraftTable.json
│   ├── FactoryManualCraftTable.json
│   ├── FactoryHubCraftTable.json
│   ├── DomainDataTable.json          据点发展等级 → 建造上限（协议容量/防御/滑索）
│   ├── FactoryPanelStoreTable.json   集成管家：区域扩大 / 仓库存取线 的档位与券价
│   ├── LevelDescTable.json           建造区中文名（枢纽区、景玉谷…）
│   ├── SettlementBasicDataTable.json 据点名（基建前站、天王坪援建点…）
│   ├── ItemTable.json
│   ├── I18nTextTable_CN.json
│   └── ...
├── data/                   ← 清洗后的结构化数据包（约 1.0 MB）
│   ├── meta.json           数据版本、来源、统计
│   ├── buildings.json      107 个建筑
│   ├── blueprint.json      106 条占地/接口数据（蓝图核心）
│   ├── bases.json          基地面积/扩建价目/据点建造上限/蓝图硬上限（面积部分是实测）
│   ├── logistics.json      物流规则层（传送带/管道/常量/蓝图码规则）
│   ├── rules.json          玩法机制规则（开采/无线传输/管道/区域限制，附证据）
│   ├── mining_power.json   矿点/产量（版本接口 schemaVersion=3，构建自检）
│   ├── machine_recipes.json  317 条机器配方
│   ├── build_recipes.json    67 条建造配方
│   ├── manual_recipes.json   102 条手工配方
│   ├── items.json          427 个关联物品 + 上下游索引
│   ├── mechanics.json      25 条机制数值（射程/间隔/攻击力）
│   ├── regions.json        地区分布
│   ├── raw_baked.json      raw 派生字段烘焙（无 raw 环境构建用）
│   ├── grow_cabin.json     18 条培养舱配方
│   └── manufacture.json    8 条制造配方
└── tools/
    ├── fetch_raw.py        从数据域拉取 raw/（仓库不含 raw，用它补齐）
    ├── build.py            构建数据包（结尾自动刷新 raw 烘焙）
    ├── build_logistics.py  物流规则层构建
    ├── build_rules.py      玩法机制规则层构建（开采/运输/区域）
    ├── build_bases.py      基地/据点层构建（面积、扩建价目、建造上限）
    ├── bake_raw.py         把 raw/ 派生字段烘焙进 data/raw_baked.json
    ├── build_html.py       生成查询界面（含排布器）
    ├── ake.py              命令行查询
    ├── test_html.js        回归测试 778 项（改完必跑，见 docs/维护与更新.md）
    ├── test_layout_events.js 事件层回归 106 项
    ├── test_push_kb_guard.py 推送防线回归
    ├── scan_all.js         全库扫描器（布局工况体检）
    ├── release.py          一条龙发布（build→测试→推送）
    ├── push_kb.py          WorkBuddy 托管页推送（commit + publish + 终验）
    └── gh_deploy.py        GitHub 推送（Git Data API）
```

---

## 数据分层与版权（重要）

本项目的文件按**版权归属**分三层，这决定了哪些能进版本库、哪些不能：

| 层 | 内容 | 体量 | 进 git？ | 说明 |
|---|---|---|---|---|
| **① 游戏解包数据** | `raw/` —— 67 张 TableCfg | 18.4 MB | ❌ **绝不** | 含 `I18nTextTable_CN`（14.7 万条游戏内文案原文）。版权归鹰角网络，**不外传、不上云、不进版本库** |
| **② 烘焙产物** | `data/raw_baked.json` | 36 KB | ✅ | 从 `raw/` 提取的**派生参数**（环境色、散布机规格、5 条环境依赖配方、281 件可出货物品的 id/名/稀有度/域归属）。是「数据」不是「原文」，替代 14.3 MB 的 raw 依赖 |
| **③ 清洗后数据包** | `data/*.json` | 1.0 MB | ✅ | 结构化数据，本项目主体 |
| **④ 源码** | `tools/` | 847 KB | ✅ | 构建 / 测试 / 推送脚本 |

**为什么这么分**：`build_html.py` 原先直接读 `raw/` 做注入层加工。为把版权风险压到最低（2026-09-23 定策），把「raw → 注入字段」的加工抽成 `tools/bake_raw.py`，结果落到 `data/raw_baked.json`；`build_html.py` **优先读烘焙文件，缺了才回落读 `raw/`**。

**效果**：没有 `raw/` 的机器（云端开发环境、新克隆的副本）也能完整构建出**字节完全一致**的产物 —— 已实测 sha256 相同。

**怎么更新烘焙**（游戏版本更新后）：
1. 一条命令补齐 `raw/`：

   ```bash
   python tools/fetch_raw.py                              # 拉全部（已存在的跳过）
   python tools/fetch_raw.py --ver 1.6.0 --hotfix xxxxxxx-x  # 换游戏版本
   python tools/fetch_raw.py --only ItemTable RewardTable     # 只拉指定的表
   ```

   默认版本取自 `data/meta.json`，与当前数据包同源。底层是数据域直取：
   `https://data.akedata.wiki/public/<版本>/<hotfix>/TableCfg/<表名>.json`
   —— 该地址**不支持目录浏览**，只能按表名逐个取；脚本已内嵌 66 张表的清单，不用自己记；
2. 跑 `python tools/build.py`（会重建数据包并**自动刷新**烘焙）；
3. 或单独跑 `python tools/bake_raw.py`。

烘焙文件里记了 6 张源表的 `sha256_16` 指纹（`_rawFiles` 字段），可据此判断它是否与手头 `raw/` 同源。

> ⚠️ **不要手改 `data/raw_baked.json`** —— 它由脚本生成；改了也会在下次 `build.py` 时被覆盖。

### 云端环境的能力边界（重要）

因为 `raw/` 不上云（版权），**没有 `raw/` 的机器（云端 Codespaces / 新克隆副本）只能做以下事**：

| 能 ✅ | 不能 ❌ |
|---|---|
| 跑 `build_html.py` 生成成品 HTML（靠 `data/raw_baked.json` + `data/*.json`） | 跑 `build.py` 重建 `data/*.json` |
| 改 HTML 模板 / CSS / JS / 排布算法 | 跑 `bake_raw.py` 刷新烘焙 |
| 跑 `test_html.js` / `test_layout_events.js` 回归测试 | 拉取或更新 `raw/` |
| 改 `data/*.json` 的单条内容（手工编辑） | — |

**为什么**：`build.py` 需要读 **26 张** raw 表（`FactoryMinerTable`、`FactoryFluidPumpInTable`、`Spaceship*` 等），这些表的加工逻辑是过程式的，没法简单烘焙；且其中 `I18nTextTable_CN` 单表就有 11 MB —— 烘焙它等于把 raw 搬上云，**与版权策略冲突**。

**所以数据更新的正确流程是**：**游戏版本更新时在本地跑 `build.py`**（有 raw，全功能）→ 把重算后的 `data/*.json` 提交上来。日常改代码在云端即可。

---

## 收录了什么

| 内容 | 数量 | 说明 |
|---|---|---|
| 建筑设施 | 107 | 名称、分类、耗电、**协议容量**、占地、地区、游戏内描述 |
| **占地蓝图** | **107** | **占地方格（宽×深×高）、面积、外圈周长、接口坐标与所在边** |
| **建造区** | **15** | **四号谷地 6 个 + 武陵 9 个，其中只有 **8 个有基地** |
| **基地面积** | **4** | **⚠ 社区实测，非配置表：四号谷地 主 70×70 / 副 40×40；武陵 主 80×80 / 副 50×50** |
| 机器配方 | 317 | 输入→输出、耗时、所属配方案组 |
| 建造配方 | 67 | 造一个建筑需要什么材料、所属科技树 |
| 手工配方 | 102 | 按地区分组，多为料理 |
| 关联物品 | 427 | 含产出途径与被消耗位置的双向索引 |
| **机制数值** | **25** | **从建筑描述中自动抽取的射程、间隔、攻击力** |
| **物流实体** | **10** | **传送带/管道/分流汇流/连接器/阀门：吞吐、端口朝向** |
| **暗管设施** | **4** | **地下管道入口/出口，成对配对，最大连接 300** |
| **物流常量** | **31** | **连接长度、角度限制、阀门档位、滑索射程、采掘速率** |
| **玩法规则** | **5** | **核心区域定义、传送带区域锁定、矿机放置、矿物无线传输、流体只能走管道（每条附原文出处）** |
| 培养舱/制造 | 26 | 种植与制造配方 |

> 以上各项的详细口径、字段说明与完整表格，见上方「📖 文档索引」所列文档。

---

## 📖 文档索引

详细内容按域拆分在以下文档（2026-09-24 起），README 只留门面：

| 文档 | 内容 |
|---|---|
| [docs/数据手册-蓝图.md](docs/数据手册-蓝图.md) | 占格规格分布、接口坐标、SVG 俯视图、布局试摆（交互沙盘）、经验规律、典型布局、尺寸极端值 |
| [docs/数据手册-玩法与物流.md](docs/数据手册-玩法与物流.md) | 区域限制/开采/无线传输/管道六则、吞吐速率、物流实体与常量、暗管、滑索、矿点清单与理论值、物流做不到、蓝图分享码、基地面积与建造上限、基建机制速查 |
| [docs/维护与更新.md](docs/维护与更新.md) | 数据边界完整清单、游戏版本更新流程、raw 表清单、审计与回归基线 |
| [排布器版本演进记录.md](排布器版本演进记录.md) | 排布器功能演进全史：路线图 ③④⑤⑥ 各节、v50~v128 版本日志（含 README 迁入存档） |
| [排布器算法地图.md](排布器算法地图.md) | `build_html.py` 排布器 117 个函数的阅读入口索引 |

---

## ⚠️ 数据边界（重要）

三句话版：

1. **配置表里没有的数据，本库不编** —— 传送带无占格字段、吞吐未经逐项实测、蓝图分享码无法从配置表解码、取货口吞吐无单列数据。逐项清单见 [docs/维护与更新.md](docs/维护与更新.md) 的「数据边界」。
2. **基地面积是社区实测**，不在任何 TableCfg 里；扩建价目、据点等级上限、蓝图硬上限才是配置表数据。引用时务必分开说。
3. **排布器是工具不是模拟器** —— 个别场景按可解释口径建模（如超限报警不拦截），报告与页面均明说。

---

## 版权

游戏数据与相关图片版权归**鹰角网络及相关权利方**所有。本项目仅供学习、交流与研究使用，不得用于侵犯权利方权益或其他非法用途。

AKEDatabase 项目代码采用 AGPL v3.0。
