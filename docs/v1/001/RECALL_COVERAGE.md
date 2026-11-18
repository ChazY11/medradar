# V1-001 / RECALL COVERAGE — 监护设备召回通道的真实覆盖

> 全部数字来自 `D:/DEPPSKK/v1-001-data/radar.db` 的真实采集，可由
> `docs/v1/001/_scripts/recall_coverage.py` 与 `verify_reference_events.py` 复算；
> 证据 JSON 在 `docs/v1/001/_evidence/`。

## 1. 一句话结论

本轮之前，雷达账本里的**监护设备召回是 0 条**；本轮之后是 **626 个监护召回事件**（来自 6,563 条召回观测、
2,330 个 FDA 召回事件），其中 **2026 年 55 个监护事件**，且 FIRST PRINCIPLES-001 点名的 4 个漏检案例**全部在库**，
8 个关键事件已用**实时 openFDA 查询逐字段复算一致**。

## 2. 采集结果（真实运行，2026-11-18）

| 项 | 值 |
| --- | --- |
| 来源 | `https://api.fda.gov/device/recall.json`（openFDA 官方，公有领域） |
| 采集方式 | 既有 `SourceAdapter` 契约 + 既有账本；新增一个适配器，无第二套管线 |
| 采集范围 | 29 个监护产品码的**完整召回历史**（清单）+ 2025-01-01 起**全部产品码**的按公开日期窗口（增量发现） |
| 观测数 | **6,563**（每个 FDA 产品召回记录一行） |
| 去重后事件数 | **2,330** 个 `res_event_number` |
| 其中监护范围内 | **1,352 条记录 = 626 个事件** |
| 其中非监护（存储但不进周报） | 5,211 条记录 = 1,711 个事件 |
| 运行耗时 | 138 秒 / 30 页 / 36 次请求 |
| 运行状态 | 第一次为 PARTIAL（6 个产品码返回 404，见第 6 节缺陷 1），修复后同一清单重跑为 **OK、0 新增 1,481 条未变** |

### 2.1 监护判定的四个层级（每条都记录依据）

| 依据 | 记录数 | 事件数 | 含义 |
| --- | --- | --- | --- |
| `PRODUCT_CODE` | 1,215 | 565 | 该行官方产品码在已提交的 `config/radar/topics.json` 里映射到监护设备族 |
| `DEVICE_TEXT` | 122 | 56 | 产品码不在清单里，但官方产品描述/召回原因点名了监护设备或测量（**需人工复核**） |
| `UNCONFIRMED` | 15 | 6 | 召回企业是监护厂商、但设备无法确认（**需人工复核**） |
| `OUT_OF_SCOPE` | 5,211 | 1,711 | 无任何监护信号；**保留在库**、以理由排除、并在周报里计数 |

`DEVICE_TEXT` 不是理论上的补充：它实际抓到了码表之外的真实监护设备，例如
**Philips Avalon FM20 胎儿监护仪**（产品码 HGM）、**BD ForeSight 组织血氧线缆**（MUD）、
**Sarnova Curaplex 二氧化碳采样套件**（CCX）。只按产品码筛选会漏掉这一类。

### 2.2 按年份（监护范围内，记录数）

| 年份 | 记录 | 年份 | 记录 |
| --- | --- | --- | --- |
| 2010 | 82 | 2021 | 11 |
| 2014 | 55 | 2022 | 8 |
| 2016 | 200 | 2023 | 35 |
| 2019 | 3 | 2024 | 63 |
| 2020 | 24 | **2025** | **171** |
| — | — | **2026** | **120（55 个事件）** |

（另有 233 条没有公开日期，保留为 ARCHIVE。）

## 3. 四个点名漏检案例：官方记录核实结果

任务书要求「必须实际取得官方记录并核实其名称、事件身份、日期、设备、范围和状态」，并「不得仅根据此前报告复制事实」。
下表是**从账本读出的原始字段**，并用实时 openFDA 复算过（第 4 节）。

| 案例 | FDA 事件 | 产品记录 | 公开日期 | 状态 | 官方原因（节选） |
| --- | --- | --- | --- | --- | --- |
| GE Portrait（软件） | **99536** | Z-3036-2026 等 4 条 | **2026-08-27** | Open, Classified | Software issue may result in a loss of patient monitoring at the Hub and Central Viewer… alarm settings could be reset to factory defaults |
| GE Portrait（网络安全） | **99475** | Z-2878-2026 | **2026-08-04** | Open, Classified | A software vulnerability may allow unauthorized persons to gain privileged access… could result in loss of patient monitoring, missed patient alarms |
| Philips PIC iX（连接中断） | **99908** | Z-0199-2027 | **2026-10-16** | Open, Classified | Unreliable wireless roaming… resulting in loss of connectivity to the central monitoring system (PIC iX) |
| Philips PIC iX（无法重连） | **99126** | Z-2579-2026 | **2026-06-24** | Open, Classified | device reset… failure to reconnect to the PIC iX central monitoring system |
| Mindray 说明书（报警措辞） | **99828** | Z-0109-2027 等 8 条 | **2026-10-07** | Open, Classified | Certain monitor operator manuals contain descriptions that may be insufficient… regarding selected physiological alarm functions |
| Nihon Kohden 中央站（网络安全） | **99549** | Z-0089-2027 | **2026-10-06** | Open, Classified | cybersecurity issue associated with a NULL Pointer Dereference vulnerability… could potentially cause disruption of the centralized monitoring of multiple beds and the visualization of alarms |

**与 FIRST PRINCIPLES-001 记载的差异（必须写明）**：此前报告的日期（GE Portrait 2026-07-20、Philips PIC iX 2026-07-31）
与本轮官方记录不一致；本轮以官方 `event_date_posted` 为准。此外 Mindray 案例是一**个事件 8 条产品记录**，
Nihon Kohden 是 CNS-6200 系列（不是笼统的中央站）。

## 4. 独立复核：8 个事件逐字段对源验证

`docs/v1/001/_scripts/verify_reference_events.py` 对每个事件**重新查询** openFDA（不是复用已存副本），比较：
产品召回号集合、事件日期、公开日期、状态、企业名、召回原因的规范化哈希。

结果：**8 / 8 全部一致**（`_evidence/reference_verification.json`，`ok: true`）。事件号：
99536、99475、99908、99126、99828、99549、99545、99801。

**限制（必须读）**：`www.accessdata.fda.gov` 的 HTML 页面在本机返回 JavaScript 倒计时拦截（HTTP 400），
因此**没有打开人类可读的 FDA 网页**。复核对象是同一份监管记录在官方机器可读 API 中的内容。
这证明内容一致，不证明网页渲染或链接可用性。对产品的影响：用户点击「原始链接」可能遇到该拦截，
这是一个**真实的可用性风险**，列入 `QUALITY_REPORT.md` 的待办。

## 5. 漏检根因分类（按链路阶段，不按算法好坏）

| 案例 | 根因阶段 | 具体原因 | 本轮是否修复 |
| --- | --- | --- | --- |
| 全部 4 个案例 | **S1：来源存在但适配器未采集** | `config/radar/sources.json` 早已写了 `/device/recall.json`，但 `adapters/` 下没有召回适配器；账本 0 条 | **是**（新适配器） |
| GE Portrait / Mindray 多产品行 | **存储身份** | FDA 一行 = 一个产品记录；一次召回可含 8 条。若按行计数会把 1 个事件算成 8 个 | **是**（事件号进 `observation_identifier`，事件计数 = GROUP BY） |
| Nihon Kohden 网络安全 | S1 + 展示语义 | 即使采到，网络安全类记录在旧的单一 tier 下会被当成「非技术」 | **是**（分类为 `monitoring_safety_action` + CRITICAL） |
| 6 个产品码 404 | 采集正确性 | openFDA 对「无结果」返回 404；适配器当时把它当失败，导致这 6 个码永远无法完成清单 | **是**（`allow_not_found`，404 = 合法的空清单） |

## 6. 本轮修复的采集缺陷（都在一个适配器内）

| # | 缺陷 | 影响 | 修复 |
| --- | --- | --- | --- |
| 1 | 404（无结果）被当成采集失败 | 6 个产品码反复失败、来源状态 PARTIAL、清单永远不完整 | 传 `allow_not_found=True`；404 = 空清单 |
| 2 | 事件号没有进入身份体系 | 事件计数只能靠标题去重，不可靠 | 事件号写入既有 `observation_identifier`（kind=`FDA_RECALL_EVENT`） |
| 3 | 窗口下界无「意图」区分 | 一次普通首跑会回扫 90 天，而历史导入需要从 2025-01-01 起 | 无水位线时按 `origin` 决定：BACKFILLED → 2025-01-01，否则 90 天 |
| 4 | 试运行（dry-run）留下 RUNNING 记录 | 状态页会显示一个永远「运行中」的周期 | 试运行不再创建/恢复运行记录 |

## 7. 历史回填与增量采集：如何保证不产生「虚假新增」

| 证据 | 值 |
| --- | --- |
| 回填观测 | 6,563 条，`observation_origin = BACKFILLED`、`discovery_phase = HISTORICAL_BACKFILL`、带 `backfill_reason` |
| 增量观测（本轮真实运行） | 0 条新增；第二次运行 4.3 秒、2 次请求、266 条未变 |
| 周报如何区分 | 只有「来源声明的公开日期落在窗口内」才是 `NEW_EVENT`；窗口前公开的标注为 `FIRST_DISCOVERED_HISTORICAL`（历史补充） |
| 本期实测 | 354 条本周公开（全部为文献）、14,771 条历史首次采集、0 条被错误标记为「本周新发生」的召回 |

**发现延迟**（`first_observed_at - event_date_posted`，监护记录 1,119 条样本）：中位数 **3,655 天**，最小 33 天。
这个数字**不能**当作「产品延迟」：它是历史回填的必然结果。真实增量延迟只有等下一批新召回发布后才可测（见 `INCREMENTAL_RELIABILITY.md`）。

## 8. 当前仍然发现不了什么（诚实缺口）

| 缺口 | 影响 | 本轮是否处理 |
| --- | --- | --- |
| NMPA（中国）、EU MDR / EUDAMED、Health Canada | 只在这些辖区发布的安全行动不可见 | 否（新增事实来源超出本轮范围） |
| 企业官网（除 Philips / Dräger；GE HealthCare 被 robots.txt 拒绝） | 主动召回公告、现场安全通知不可见 | 否 |
| 竞品产品页 / 说明书 / 固件版本 | 性能与配置变化不可见 | 否 |
| PubMed 的 7 条检索式 | 文献覆盖仍窄（FIRST PRINCIPLES-001 实测 28.5%） | 否（记录为缺口） |
| FDA HTML 网页 | 用户点链接可能遇到反爬拦截 | 否（记录为风险） |

## 9. 复算命令

```bash
python docs/v1/001/_scripts/recall_coverage.py \
    --db D:/DEPPSKK/v1-001-data/radar.db \
    --json docs/v1/001/_evidence/recall_coverage.json
python docs/v1/001/_scripts/verify_reference_events.py \
    --db D:/DEPPSKK/v1-001-data/radar.db \
    --events 99536,99475,99908,99126,99828,99549,99545,99801 \
    --json docs/v1/001/_evidence/reference_verification.json
```
