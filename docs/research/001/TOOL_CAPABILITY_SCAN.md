# 能力扫描 / 这类工具到底需要什么

- 时间：2026-11-20
- 方法：定向检索 + 抓取一手产品页与第三方评测；**不是**凭印象列的清单
- 范围：不限于医疗。覆盖四个相邻品类：市场/竞争情报、监管情报、科研文献监测、风险/OSINT
- 限制：G2、OpenEvidence 官网有反爬（403），这两处只能引用二手描述；厂商页面本身是营销材料，
  所以"用户抱怨"一律以第三方评测为准

---

## 1. 这四类工具在抢同一件事

| 品类 | 代表 | 它承诺的回答 |
| --- | --- | --- |
| 竞争情报 CI | Klue、Crayon、Kompyte、Contify | "对手做了什么，我怎么应对" |
| 市场/研究情报 | AlphaSense、Feedly AI、Comintelli | "这个主题发生了什么，证据在哪" |
| 监管情报 | Vixio、Corlytics、ECRI、Emergo | "规则/召回变了什么，我要做什么" |
| 风险/OSINT | Recorded Future、Dataminr | "有什么信号，多紧急" |

MedRadar 落在"市场/研究情报"与"监管情报"的交叉点：**公开记录 + 判定 + 证据**。
所以下面按这四类共同的能力面来评，而不是只看医疗。

---

## 2. 十类必备能力（带证据）

### 2.1 覆盖与采集（Discovery）

- 自动摄取是**入门券**：Flares 对 500 条 G2 评论的编码显示，28 项共同被称赞的能力里，
  "自动获取对手数据"过了 3% 显著度门槛，是四项工具共同的价格底线
  （[Flares CI Research 2026](https://www.flares.tech/research/competitive-intelligence-tools-g2-review-study)）。
- Feedly 的做法是把采集包装成**预训练模型**：公司、行业、威胁、漏洞等模型直接可订阅
  （[Feedly AI](https://feedly.com/ai)）。

**MedRadar**：7 个来源，含被策略封禁的 GE（正确显示为 blocked 而非"没发现"）。✅ 达标。

### 2.2 降噪与排序（Signal over noise）

**这是整个品类唯一被所有厂商用户共同抱怨的问题。**
同一份研究：11 条抱怨在四家都出现，只有"告警太多、多到不相关"在四家都过了显著度门槛
（Klue 3.3% / Crayon 10.0% / Kompyte 5.0% / Contify 6.0%）。

ZoomInfo 的采购指南也直说：**"把销售淹没在未过滤告警里的平台，覆盖面再广也会被无视"**
（[ZoomInfo 2026](https://pipeline.zoominfo.com/sales/competitive-intelligence-software)）。

**MedRadar**：1,660 条 → 17 条的准入判定 + 今日摘要。✅ **这是目前最强的一项**。

### 2.3 单一口径的"真相源"（Single source of truth）

第二被称赞的主题（Klue 22.0%、Kompyte 24.0% 的用户提到）。用户买的就是"别让我去十个地方找"。

**MedRadar**：账本统一，但**只有雷达这一块**；公司/设备/主题还散在图谱与筛选里。⚠️ 部分。

### 2.4 工作流：从"读到"到"做完"

监管情报类把这一点做成了产品骨架。Vixio 的五段式：**监控 → 识别 → 评估影响 → 落地 → 追溯审计**，
配套的是任务管理、项目跟踪、报告、义务库
（[Vixio](https://www.vixio.com/articles/automated-regulatory-intelligence)）。

CI 类同理：Crayon 用户最不满的是**battlecard 编辑**（18.7%），Kompyte 用户最不满的是**内容过期**（13.0%）
—— 都在抱怨"下游产出物"，不是"采集"。

**MedRadar**：只到"读"。有"待核实"队列，但没有指派、状态、任务、期限、产出物。❌ **最大的结构性缺口**。

### 2.5 投递到人所在的地方（Delivery）

AlphaSense 的仪表盘卖点是"自定义你跟踪的公司与主题视图"；Feedly 出 iOS/Android/Chrome 扩展/API。
成熟产品的默认投递面是：邮件摘要、Slack/Teams、Webhook、API、Office 插件。

**MedRadar**：只有网页。没有邮件/Slack/推送。❌ 缺。

### 2.6 个人化：关注清单与保存的检索

AlphaSense、Feedly、Recorded Future 都以此为核心交互（watchlist、saved search、自定义视图）。
这也是"相关性"的唯一实现手段——因为系统不知道你在意什么。

**MedRadar**：有筛选与筛选计数，但**筛选状态不保存**，刷新即失。❌ 缺（且成本很低）。

### 2.7 出处、可核查、可引用

JMIR 的访谈研究里，用户对 AI 信息的核心疑虑就是**"没有引用"**
（[JMIR 2025](https://www.jmir.org/2025/1/e79961)）。

OpenEvidence 之所以被医生接受，卖点就是每条结论都带原文引用与指南链接（其官网 403，见二手描述）。
监管类的"可审计"是合规刚需。

**MedRadar**：证据抽屉 = 判定维度 + 三条理由 + 官方链接 + 内容哈希 + 版本历史。✅ **与任何一家比都不弱**。

### 2.8 实体解析与"谁/什么/何时变了"

所有成熟的 CI 工具都以**公司**为主键组织信息（Klue/Crayon 的 company tracking、Feedly 的 company lists）。
监管类以**产品**为主键。用户真正的问题是"这家公司最近怎么了"，不是"今天来了哪些文档"。

**MedRadar**：有科技地图（公司×主题）与两套时钟，但**没有公司页**：点 GE 只能看到分支，看不到"GE 最近发生了什么"。
⚠️ 部分。

### 2.9 时间维度：变了什么

"what changed" 是这批产品的高频功能（Kompyte 的"内容过期"抱怨正是它没做好）。
AlphaSense/CI 工具都在做 diff 与时间线。

**MedRadar**：版本历史、"What changed" 图谱 diff、两套时钟（公开时间/知识时间）。✅ **明显强于平均**。

### 2.10 审计、权限与合规

监管类客户买的就是"能证明"。Vixio 的 Track/Audit、任务与义务库都是为此存在；企业级还需要 SSO、留存策略、导出。

**MedRadar**：账本 append-only、判定不可改写、完整性审计 —— 数据层很硬；
但**没有用户体系、没有导出、没有审计报告**。❌ 缺（对外销售前必须有）。

### 2.11（2026 新增的默认项）给 AI 代理一个入口

2026 年一个明显的新常态：主流平台开始发布 **MCP server**，让 Claude/ChatGPT/自建代理直接查询平台数据：
AlphaSense 的 SuperAnalyst MCP（[AlphaSense](https://www.alpha-sense.com/resources/product-articles/superanalyst-mcp/)）、
ZoomInfo MCP、Feedly 开发者 API。

含义：**"有 Web 界面"已经不够，数据要能被代理调用。**
MedRadar 已有完整只读 JSON API（是优势），但**没有 MCP**。❌ 缺，且门槛很低。

---

## 3. 差距矩阵

| 能力 | 行业地位 | MedRadar | 差距 |
| --- | --- | --- | --- |
| 自动采集 | 入门券 | ✅ | — |
| 降噪排序 | **品类第一痛点** | ✅ 强 | — |
| 单一口径真相源 | 入门券 | ⚠️ 仅雷达内 | 中 |
| 工作流（指派/任务/产出物） | 监管类骨架 | ❌ | **大** |
| 投递（邮件/Slack/推送） | 默认项 | ❌ | 大 |
| 关注清单/保存的检索 | 默认项 | ❌ | **小成本、高收益** |
| 出处与可核查 | 信任基础 | ✅ 强 | — |
| 实体页（公司/产品） | 默认项 | ⚠️ 只有地图 | 中 |
| 时间与变更 | 高频功能 | ✅ 强 | — |
| 审计/权限/导出 | 企业准入 | ❌ | 大（对外销售前） |
| MCP/AI 入口 | 2026 新默认 | ❌ | 小成本 |

---

## 4. 结论：三个判断

### 4.1 MedRadar 已经赢在正确的两处

**降噪**（1,660 → 17）与**出处**（每条可点开核查）。这两项恰好是品类最普遍的两个失败点：
前三家做得再好，用户仍抱怨告警噪音；AI 工具做得再多，用户仍不信没有引用的结论。
这两项不要再"优化"，要**守住**。

### 4.2 最大缺口不是功能，是"读完以后"

所有成熟产品都在把阅读变成行动：指派、任务、产出物、报告、审计。
MedRadar 现在是一条很好的"阅读流水线"，但读完就结束了。
对一个要做四周试验的产品，这意味着**无法回答"这条情报带来了什么动作"**。

### 4.3 最便宜的三个改进

| 优先级 | 改进 | 理由 |
| --- | --- | --- |
| P0 | **保存筛选为"我的关注"** | 默认项、成本极低、直接改善相关性 |
| P1 | **公司页**（这家公司最近发生了什么） | 用户的语言是公司，不是文档 |
| P2 | **MCP 只读入口** | 2026 默认项，已有 API，包一层即可 |

明确**不该做**的：内容营销式的 battlecard、CRM 集成、win-loss 分析、站点爬虫扩张。
那些是 CI 品类的战场，不是这个产品的战场。

---

## 5. 引用

1. Flares CI Research (2026), _The State of Competitive Intelligence Tools_ —
   https://www.flares.tech/research/competitive-intelligence-tools-g2-review-study
2. ZoomInfo (2026), _10 Best Competitive Intelligence Software Platforms_ —
   https://pipeline.zoominfo.com/sales/competitive-intelligence-software
3. Feedly, _Feedly AI_ — https://feedly.com/ai
4. Vixio, _Automated Regulatory Intelligence Solutions_ —
   https://www.vixio.com/articles/automated-regulatory-intelligence
5. AlphaSense, _SuperAnalyst MCP_ —
   https://www.alpha-sense.com/resources/product-articles/superanalyst-mcp/
6. AlphaSense, _The New AlphaSense Dashboard_ —
   https://www.alpha-sense.com/blog/product/go-from-reactive-to-proactive-with-the-new-alphasense-dashboard/
7. JMIR (2025), _Evolving Health Information-Seeking Behavior … Think-Aloud_ —
   https://www.jmir.org/2025/1/e79961
8. Emergo by UL, _Post-Market Surveillance Services_ —
   https://www.medical-xprt.com/services/post-market-surveillance-services-871858

**未能取得一手内容的**：G2 分类页（403）、OpenEvidence 官网（403）。
涉及这两处的结论均标注为二手描述，未当作独立证据使用。
