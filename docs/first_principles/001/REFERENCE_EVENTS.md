# FIRST PRINCIPLES-001 / 第三阶段 A：独立参考事件集与漏检归因

- 采集时间：2026-11-18 11:00–11:20 (Asia/Shanghai)
- 对照对象：`perf-v2.db`（2026-11-18 复制的生产形状账本，schema `radar-ledger-v3`，8,593 条观测）
- 原则：参考集由**本轮独立构造**，检索式与 MedRadar 的 7 条 PubMed 检索式不同，
  目的不是复现它，而是检查它没找到什么。

## 1. 参考集的构造（三层，各自独立）

### 1.1 文献层：6 条比 MedRadar 更宽的 ICU 监护检索式

窗口：Entrez 日期 2026-10-01 → 2026-11-18（48 天）。
与 MedRadar 的差别：MedRadar 的每条检索式都强制 `AND ("intensive care" OR "ICU" OR "patient monitor")`，
本轮把条件放宽到 `critically ill / mechanical ventilation / neonatal / bedside monitor / continuous monitoring`，
以便发现"主题正确但措辞不同"的文献。

| # | 检索式要点 | 命中总数 | 抽样 | 库中已有 | 缺失 | 库内发现率 |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | pulse oximetry / SpO2 / oxygen saturation × ICU、critically ill、ventilation、neonatal | 136 | 100 | 51 | 49 | 51% |
| Q2 | ECG / arrhythmia / telemetry × ICU、bedside/patient monitor、continuous monitoring | 118 | 100 | 31 | 69 | 31% |
| Q3 | arterial/NIBP / blood pressure monitoring × ICU、invasive monitoring | 24 | 24 | 4 | 20 | 17% |
| Q4 | NIRS / cerebral oximetry / continuous EEG / ICP × ICU、neurocritical | 76 | 76 | 11 | 65 | 14% |
| Q5 | alarm fatigue / false alarm / alarm management / signal quality × ICU | 80 | 80 | 15 | 65 | 19% |
| Q6 | capnography / respiratory monitoring / etCO2 × ICU | 20 | 20 | 2 | 18 | 10% |
| **合计** | | **454** | **400** | **114** | **286** | **28.5%** |

方法：E-utilities `esearch`（`datetype=edat`）→ `esummary` → 按 PMID 与账本 `official_identifier` 比对。
原始数据：`_fp001/pubmed_probe.json`、`_fp001/pm_*.json`、`_fp001/pm_missed.json`（本轮工作目录）。

### 1.2 监管层：13 个监护产品码的全部 FDA 召回

`openFDA /device/recall.json`，`search=product_code:"<code>"`，逐一查询 13 个 MedRadar 已配置的监护产品码：

| 产品码 | 含义（taxonomy） | 召回条数 | 最近一条 |
| --- | --- | --- | --- |
| MHX | 生理监护仪（含心律失常检测/报警） | 100* | 2026-09-16 |
| DQA | 血氧计 | 100* | 2025-10-24 |
| DRS | 压力传感器 | 100* | 2026-03-24 |
| DPS | 心电图机 | 98 | 2026-07-20 |
| MWI | （telemetry/连续监护） | 85 | 2026-08-21 |
| CCK | 气体/CO2 分析 | 84 | 2025-04-07 |
| DSI | 心律失常检测与报警 | 82 | 2026-03-26 |
| DXN | 电子血压计 | 36 | 2025-02-24 |
| MSX | telemetry 监护系统 | 23 | 2026-08-31 |
| DRG | （ECG 相关） | 12 | 2026-07-20 |
| DRT | 心脏监护仪 | 11 | 2024-08-09 |
| BZQ | 呼吸监护 | 3 | 2010-12-21 |
| **合计** | | **734** | |

（* 为 openFDA 单次查询上限 100，实际总数可能更多；本层结论只需"远大于零"，不需要精确总数。）

**顺带得到的一个独立发现**：openFDA 的一行是一条**产品记录**，不是一次**召回事件**。
2026 年 42 行只对应 19 个 res_event_number。这与本轮在账本侧发现的
"存储身份是来源行而不是作品"（ROOT_CAUSE R6）是同一类问题：**用行数当事件数会高估约一倍**。

**其中 2026 年当年 42 条记录，去重后是 19 个召回事件。**
按记录行的企业分布：GE HealthCare 12、Mindray 8、Philips 6、Midmark 6、Spacelabs 3、Masimo 2、
Medline 2、Nihon Kohden 1、Criticare 1、Covidien 1。
**账本中召回记录数：0。**（`select count(*) from observation where record_type like "%recall%"` = 0）

### 1.3 企业层：三大目标企业的官方新闻

| 企业 | 状态 | 库内记录 | 与监护主题相关 | 说明 |
| --- | --- | --- | --- | --- |
| Philips | ENABLED | 5 | 0 | 全部为集团新闻室最新 5 条：AGM 提名、Sonicare 牙科顾问委员会、HyperVue/UniGuide 影像介入、EXIT-CVD 联盟 |
| Dräger | ENABLED | 31 | 2 | 主体是 **Dräger Safety（工业安全）** 的故事型内容：海滩清理、矿山安全、清洁能源、气体检测、INARA、"Be creative" |
| GE HealthCare | BLOCKED | 0 | 0 | robots.txt 返回 403（Akamai），适配器正确标记为访问受限而非"无新闻" |

结论：**企业官方通道当前不产生监护技术情报**。36 条记录里 2 条勉强相关，且都不含技术规格。

## 2. 漏检归因（按数据链路阶段，不按"算法好坏"）

任务书要求区分五种漏检根因。本轮在真实数据中**五种全部观察到了**，并给出各自的实例：

| 阶段 | 定义 | 本轮实例 | 数量级 |
| --- | --- | --- | --- |
| S0 来源不存在 | 系统根本没有这个来源 | NMPA（中国监管）、EU MDR/EUDAMED、专利、临床试验注册、竞品产品页 | 0 条来源 |
| S1 来源存在但适配器未采集 | 有通道，但适配器不实现 | FDA 召回（openFDA 明确提供 `/device/recall.json`，配置文件里甚至写了该路径，但没有适配器） | 734 条召回，2026 年 42 条 |
| S2 已采集但检索范围未覆盖 | 适配器只问固定检索式 | PubMed 7 条检索式强制 ICU 词；本轮同样窗口 6 条更宽检索式找到 286 条它没有的 | 286/400（71.5%） |
| S3 入库前被过滤 | 采集时二次过滤 | **已不存在**：REFOUNDATION-004 删除了 `accept_record`（本轮核对 diff，确认删除）。因此 S3 当前为 0，但历史账本无法回溯这批假阴性 | 0（已修复） |
| S4 已入库但准入拒绝 | 引擎判 EXCLUDED | 3 条高价值假阴性（见 2.1） | 10/120 抽样 |
| S5 已准入但未展示 | FEED 但不呈现为"变化" | 7,039 条 FEED 早于 24 个月；8,588 条为 INITIAL_DISCOVERY，使"变化"视图等于建库噪声 | 95.6% 的池 |

### 2.1 S4 的证据（已入库但被拒绝的真实高价值条目）

| 条目 | 来源/时间 | 引擎判定 | 本轮判定 | 为什么重要 |
| --- | --- | --- | --- | --- |
| `Accuracy and precision of continuous non-invasive arterial pressure monitoring in critical care: a systematic review and meta-analysis` | Crossref 2021-12 | EXCLUDED / MEDICAL_UNRELATED（"medical_not_monitoring"） | DIRECT / A3 | 这就是 NIBP 产品线的核心性能证据；被拒原因见 ROOT_CAUSE R2 |
| `Occult hypoxemia in the ICU: Clinical risk factors, mortality and implications for nursing practice` | PubMed 2026-10-21 | EXCLUDED / CLINICAL（clinical_prediction_model） | DIRECT / A1 | "SpO2 在什么情况下不可信"直接决定血氧算法的验证设计 |
| `Electrocardiogram analysis for cardiac arrhythmia classification and prediction through self attention based auto encoder` | Crossref 2025-03 | EXCLUDED / CLINICAL | DIRECT / A3 | 典型 ECG 算法研究，被"clinical_application"分支吃掉 |

### 2.2 S2 的证据（286 条缺失中有多少是高价值）

单评审按标题快速筛查 286 条缺失记录，**约 25–30 条**属 DIRECT/TRANSFER，其余为临床/无关（这是预期的：
宽检索式必然带来低精度）。其中可以直接举例的高价值漏检：

| 条目 | 时间 | 为什么算高价值 |
| --- | --- | --- |
| `Blood Pressure Estimation for Hemodynamic Monitoring Using Reduced Photoplethysmography Features in Intensive Care Units`（PMID 43044098） | 2026-11-17 | 就在账本复制前一天发表，主题=用 PPG 估计血压，正中 SpO2/血压交叉地带 |
| `Effects of Skin Pigmentation on Pulse Oximetry: A Pilot Study`（PMID 42966647） | 2026-11 | 肤色偏差，与库内已收的消费级血氧研究同一议题，系统只收到后者 |
| `Development of a novel non-invasive blood pressure measurement technique using near-infrared spectroscopy and deep neural networks`（PMID 42887526） | 2026-10-27 | 新测量原理 |
| `Assessment of the duration of continuous EEG monitoring in aneurysmal subarachnoid hemorrhage`（PMID 42952828） | 2026 | 连续 EEG 监护方案 |
| `Strain-Insensitive Hydrogel Fiber Electrodes With Micropillar Arrays for Dynamic ECG Monitoring`（PMID 42928520） | 2026-10-25 | 电极材料迁移价值 |
| `Exchange of High-Frequency Medical Monitoring Data Using Fast Healthcare Interoperability Resources`（PMID 42970757） | 2026-11 | 监护数据互操作 |

注意：这些条目**不是**"被规则拒绝"，而是**从未被请求**。修复它们需要改检索式或扩源，
不是改分类器。这是本轮最重要的归因区分。

## 3. 参考集的自我限制

- 文献层只覆盖 PubMed（Crossref 的等价对照未做同规模抽样；Crossref 检索式质量明显更低，
  见 ROOT_CAUSE R3），因此不能据此估计"全部文献来源"的召回。
- "25–30 条高价值"是单评审按标题的估计，误差可能在 ±8 条。
- 召回层只查了 13 个产品码，未查 EU MDR 警戒、NMPA 召回、企业自愿通告。
- 企业层只查了 3 家；Mindray / Nihon Kohden / Masimo / Medtronic 等未纳入。

## 4. 参考集文件（可复现）

| 文件 | 内容 |
| --- | --- |
| `_fp001/pubmed_probe.json` | 6 条检索式的原始命中与 ID 列表 |
| `_fp001/pm_<query>.json` | 每条检索式抽到的 100/76/80… 条元数据 |
| `_fp001/pm_recall.json` | 每条检索式的 命中/库中已有/缺失 统计 |
| `_fp001/pm_missed.json` | 286 条缺失记录（PMID、标题、日期、检索式） |
| `_fp001/recalls.json` | 734 条召回（产品码、日期、企业、产品、原因） |
