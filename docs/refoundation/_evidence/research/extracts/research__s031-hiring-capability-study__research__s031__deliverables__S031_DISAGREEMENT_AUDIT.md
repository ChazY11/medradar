# S-031 独立审计：PR #21 分类规则、计数口径与分歧

## 1. 审计结论先行

PR #21 的数据采集和保守门槛有真实价值，但“函数类 + 既有器械产品 track”不足以表达岗位技术能力。本轮看到的主要问题不是简单的“关键词太松”或“门槛太严”，而是分类对象错了：产品领域、岗位职能、具体能力和研发证据被压在同一套输出里。

在 100 条困难分层样本上：

- 旧规则只有 3 条 `MAPPED`，这 3 条在 AI 预标注中均为 `DIRECT_R&D_EVIDENCE`。因此，本样本不支持“旧规则大量把纯销售岗位 MAPPED 成研发”的说法。
- 23 条 AI 直接研发/研究证据中，12 条被旧函数门槛压制，8 条只有 ambient 产品线索，3 条被 MAPPED。
- 88 条被程序标为“旧规则未给 track、AI 有能力标签”的复核候选。这不是 88 个已证明漏报，因为既有 track 本来就不打算覆盖全部能力。
- 29 条函数家族宽口径不一致。该数字只定位单标签、多语言和职能边界问题，不是函数分类错误率。
- 旧规则正确挡住了许多产品背景岗位，也挡住了真实的企业软件、产品工程、临床研究和工艺开发岗位。门槛不能简单删除，应改成四维证据模型。

上述双方都不是人工真值。本报告不提供准确率、Precision、Recall 或 F1。

## 2. 审计对象与可复现性

| 项目 | 值 |
|---|---|
| PR #21 分支 | `research/innovation-signals-observatory` |
| 审计 HEAD | `c4327ce44c6aafe0e4af5a73df7f356dfffcb438` |
| PR #21 base | `integration/phase4-base` @ `aa0f6fca85e0d88ddbec871ede6da9d9c8fa357d` |
| PR #20 | head `5954d7d81bc47ec5143fa7504fbe61debe51c29c`；base `research/local-llm-foundation` @ `d4c4e43c9afa353b9b4af6f4f020a959024a07bd` |
| 旧规则 | `recruitment_taxonomy_rules_2026-11-04b` |
| S-031 样本 | 100 条，五家公司各 20 条，固定 seed 31031 |
| 样本性质 | 困难分层样本，不是代表性随机样本 |

本轮先完成原文预标注，再调用 `medradar.recruitment.taxonomy.classify_rules()`。比较结果保存在 worktree 的 `research/s031/work/legacy_rule_comparison.jsonl`，全量计数审计保存在 `pr21_count_audit.json`。

## 3. 岗位身份和计数审计

### 3.1 994、992、983 是三个不同口径

| 数字 | 含义 | 本轮核验状态 |
|---:|---|---|
| 994 | 当前最终 JSONL 行数；同时也是当前唯一 `posting_id` 数 | 独立流式重算确认：994 行、994 ID、0 个同 ID 重复行 |
| 992 | 早期证据报告的去重分母：当时 994 行含 2 个同 ID 分页重复 | 文档内部算术一致；旧 SHA 文件当前不可取得，不能独立复核其文件哈希 |
| 983 | 当前 994 唯一 ID 经 8 个不可完全判定的重复簇保守合并后的分析簇数 | 独立重算：5 个同内容簇合并 6 条，3 个多城市簇再合并 5 条，994−6−5=983 |

早期 `EVIDENCE_REPORT.zh-CN.md` §2.1 明确记录“994 行、992 个去重 ID、2 行分页重复”，SHA 为 `165dce8e…f80217`。当前分支可见的两个历史 JSONL 版本分别为 994 个唯一 ID，SHA 为 `cff61741…` 和 `2ca362ee…`，均不是该旧文件。因此正确写法是“早期文档报告 992”，而不是把 992 当成当前文件的真实 ID 数。

983 也不是客观唯一的“岗位总数”。同一标题、地点、描述但不同 ID，可能是重复发布，也可能是同时招聘多人；同一描述跨城市发布，可能是一个多城市 vacancy，也可能是多个城市各自招人。保守合并只是避免把疑似副本当新增需求，不能消除组织事实的不确定性。

### 3.2 内容哈希

当前 994 条保存的 `content_sha256` 全部能按当前 `records.content_hash` 重算一致，说明当前文件与当前哈希规则相容。但 994 条都缺少 `hash_rule_version`。这仍是来源版本记录缺口，不能因为重算一致就声称历史跨规则比较问题不存在。

### 3.3 20 与 80 不冲突

- 标题用宽泛 `/robot/i` 检索，得到 20 条。
- 标题和正文用 PR #21 独立通俗探针 `\brobot|\bhugo\b|robotic` 检索，得到 80 条。
- 若标题只检索 `robotic|robotics`，会漏掉 “Robot assisted surgery” 等写法，不能复现 20。
- 80 是“文本提及”，不是“机器人研发岗位”；0 是“旧规则归入 surgical_robotics”，不是“企业没有机器人研发”。

### 3.4 47 与 54 是定义差异

对当前 61 条 `MAPPED` 逐条重算：

| 指标 | 数量 | 定义 |
|---|---:|---|
| 已归类 track 在标题中有任意对应关键词 | 14 | 包括 `software` 等泛化标题词 |
| 没有任何对应标题关键词、仅靠描述 | **47** | `evidence_linking.json` 当前汇总口径 |
| 标题有非泛化对应关键词 | 7 | 排除泛化词 |
| 没有非泛化标题关键词、仅靠描述或非标题泛化词 | **54** | `PHASE4_RESEARCH_REPORT.zh-CN.md` §5 口径 |

所以 47 和 54 不能任选一个当“真实值”。47 更宽松地承认标题证据，54 更严格地要求标题词具有 track 特异性。报告应把定义写在数字旁边。

### 3.5 168 与 275 也是不同门槛

当前 717 条被函数门槛压制的岗位中，275 条有一个最佳具体候选 track；其中 168 条若移除函数门槛，会满足现有的标题特定词、至少两个描述特定词或 frontier 单词命中条件。168 不是经人工确认的误报数，275 也不是。它们只是反事实规则计算。

## 4. 当前 Medtronic 全量分类复核

独立重算结果与当前 `evidence_linking.json` 一致：

| 函数类 | 数量 |
|---|---:|
| `SALES_ADMIN_OTHER` | 585 |
| `UNCLASSIFIED` | 132 |
| `QUALITY_REGULATORY` | 88 |
| `ALGORITHM_SOFTWARE` | 70 |
| `MANUFACTURING_PROCESS` | 47 |
| `PRODUCT_ENGINEERING` | 34 |
| `CORE_R&D` | 14 |
| `CLINICAL_R&D` | 13 |
| `HARDWARE_SYSTEMS` | 11 |

track 状态为 `MAPPED=61`、`AMBIENT_ONLY=147`、`NO_EVIDENCE=69`、`SUPPRESSED_BY_FUNCTION_CLASS=717`。61 条 MAPPED 中 50 条 WEAK、11 条 MODERATE；这些规则强度不是语义正确概率。

独立通俗探针复核：

| track | 文本提及 | 归入同一 track | 必须同时看到的限制 |
|---|---:|---:|---|
| `surgical_robotics` | 80 | 0 | 提及中 49 销售/其他、18 未分类、6 产品工程 |
| `medical_ai` | 141 | 25 | 提及中 48 销售/其他、17 质量法规；也有真实软件与企业 IT |
| `ep_pfa` | 117 | 8 | 提及中 86 销售/其他，产品采用背景很多 |
| `neurostimulation` | 57 | 14 | 提及中 40 销售/其他 |
| `cardiac_rhythm` | 56 | 2 | 提及中 43 销售/其他 |

这些数字证明了“提及”和“归类”之间有大 gap，却没有替人工判断每一条 gap 都是错误。尤其是机器人：直接取消门槛会把大量销售、培训和启动专员重新带入；保留现状又可能漏掉 6 个产品工程类提及岗位。需要能力级证据，而不是换一个阈值。

## 5. 100 条样本的描述性对照

### 5.1 旧规则输出

| 旧函数类 | 数量 |
|---|---:|
| `UNCLASSIFIED` | 39 |
| `SALES_ADMIN_OTHER` | 36 |
| `QUALITY_REGULATORY` | 11 |
| `ALGORITHM_SOFTWARE` | 4 |
| `MANUFACTURING_PROCESS` | 4 |
| `PRODUCT_ENGINEERING` | 3 |
| `CLINICAL_R&D` | 2 |
| `CORE_R&D` | 1 |

track 状态：`SUPPRESSED_BY_FUNCTION_CLASS=75`、`AMBIENT_ONLY=13`、`NO_EVIDENCE=9`、`MAPPED=3`。3 条 MAPPED 分别为 GE `medical_ai`、Philips `patient_monitoring`、Philips `imaging_mr_ct`。

### 5.2 AI 预标注分布

| 证据强度 | 数量 |
|---|---:|
| `DIRECT_R&D_EVIDENCE` | 23 |
| `INDIRECT_TECHNICAL_EVIDENCE` | 48 |
| `PRODUCT_CONTEXT_ONLY` | 23 |
| `NON_R&D` | 3 |
| `INSUFFICIENT_EVIDENCE` | 3 |
| `CONFLICTING_EVIDENCE` | 0 |

34 条标记为优先人工复核。以上都是工作标签，不是人工确认结果。样本故意多选困难岗位，23% 不能外推为公司直接研发岗位占比。

### 5.3 旧 track 状态与 AI 证据强度交叉表

| 旧规则状态 | AI 直接 | AI 间接 | 仅产品背景 | 非研发 | 证据不足 |
|---|---:|---:|---:|---:|---:|
| `MAPPED` | 3 | 0 | 0 | 0 | 0 |
| `AMBIENT_ONLY` | 8 | 5 | 0 | 0 | 0 |
| `NO_EVIDENCE` | 0 | 9 | 0 | 0 | 0 |
| `SUPPRESSED_BY_FUNCTION_CLASS` | 12 | 34 | 23 | 3 | 3 |

这张表显示旧门槛“挡住产品背景”和“挡住直接研发”同时存在。它不能告诉我们哪一方总体更准确，因为样本不是随机样本，且 AI 标签尚未人工 adjudicate。

### 5.4 三类 MAPPED 的语义并不相同

1. GE AIS ISC Digital & AI Director：直接建设 AI 能力，但用于供应链。`medical_ai` 若被理解为医疗产品 AI 就会误导。
2. Philips Senior Software Technologist：直接软件组件交付，`patient_monitoring` 是产品背景；Copilot 是开发工具，不增加医疗 AI 证据。
3. Philips Senior Clinical Scientist – CT：直接临床 prototype 和研究证据，不等于 CT 工程开发。

所以即使 3 条都为直接证据，也不能把 track 当作充分的研发能力描述。

## 6. 独立缺陷清单

### D1：单标签函数无法表达混合职责

`Principal Engineer / Junior Program Manager` 同时有系统架构、设计概念和项目管理；Dräger 软件子项目负责人同时做嵌入式全生命周期与项目领导。旧规则必须选一个函数，容易让局部标题词覆盖主交付物。

### D2：`SALES_ADMIN_OTHER` 过宽

它混合销售、现场服务、采购、法务、企业 IT 和其他运营。把这些岗位都放入同一门槛，会把“卖机器人”和“用 Python 开发销售系统”当成同一种证据情形。

### D3：`UNCLASSIFIED` 混合不同原因

样本中既有 3 条真正正文缺失，也有中文、德文职责未被词表覆盖，还有 API Lead、机械 co-op 等可判断岗位。未分类不是非研发，也不一定是文本不足。

### D4：既有器械 track 不能替代能力本体

R&D Engineer II 的 GD&T/容差、C++ 视频岗位的实时处理/硬件加速、HIL 岗位的系统验证，都可有明确研发活动而没有合适旧 track。技术 track 覆盖率因此不是能力识别率。

### D5：商业门槛双刃剑

23 条仅产品背景、3 条非研发、3 条正文不足都被压制，说明门槛有防误报价值；12 条直接研发/研究证据也被压制，说明函数先行会阻止正文研发证据被看见。

### D6：产品—能力—用途没有分开

供应链 AI、销售 enablement 软件、企业 Device Management 都是真实技术工作，但目标不是医疗器械产品。旧 track 即使命中，也无法说明能力服务对象。

### D7：多义词和标题语义无法靠字符串解决

- Development 可指疗法采用与临床支持。
- API 可指 active pharmaceutical ingredient。
- Device Management 可指员工电脑和手机。
- AI/Copilot 可只是开发工具。
- 产品经理可以涉及架构评审，却不以编码为主。

### D8：质量、制造和服务的技术含量被函数名称遮蔽

DOE、PFMEA、DFMA、HIL、系统集成和设备验证都有能力价值，但不应为追求“研发覆盖”而全部改成研发岗。四维模型允许“主职质量/生产/服务 + 明确技术能力 + 间接研发证据”。

### D9：临床研究与工程研发被混在一起

临床评价、prototype 可行性、多中心试验可以是直接研究证据，但不等于硬件或算法开发。旧 `CLINICAL_R&D` 太粗，新报告也必须保留研究子类型。

### D10：语言与标题 boilerplate 影响规则

Mindray 大量中文岗位旧规则全部未分类；Dräger 部分标题混入公司模板和跨语言文本。选样表层规则也曾因此被标题中的 “klinischen Anwendung” 命中，说明标题解析本身需要审计，不能把 strata 当最终函数标签。

### D11：报告口径没有机器可检验的一致性约束

992/994、47/54 等同报告数字并存。它们不全是计算错误，但缺少显式定义会让读者把不同快照、不同标题证据定义当成同一指标。

### D12：单快照无法支持战略转向

即使某岗位有直接研发职责，也可能是既有产品维护、替补或常规迭代。旧候选规则要求多个岗位 ID，只能证明公开文本中存在重复需求线索，不能证明新方向、项目立项或投入增加。

## 7. 四类错误的本轮证据状态

| 审查类型 | 本轮能否确认普遍存在 | 证据状态 |
|---|---|---|
| False Technical Attribution | 不能据本样本声称大量存在 | 3 条 MAPPED 都有直接活动；GE 供应链 AI 是“track 用途误导”而非无技术能力 |
| Missed Technical Capability | 有大量复核候选，待人工确认 | 88 条无旧 track 但有 AI 能力标签；其中直接研发被压制 12 条 |
| Product–Capability Confusion | 有明确机制案例 | 机器人销售、供应链 AI、Copilot、试剂设备、企业 Device Management |
| Unsupported Inference | 旧报告已有防护，但风险仍在任何上游升级结论处 | DIRECT_R&D_EVIDENCE 也不能升级为新方向；本轮未做战略转向断言 |

## 8. 应如何修改，而不是简单调阈值

1. 保留旧函数和 track 命中作为候选证据，不直接作为最终能力标签。
2. 先抽取主/辅助职能，再抽取“活动动词 + 技术对象 + 目标对象”。
3. 产品 track 命中默认进入 Product Context；只有职责证据支持时才进入 Capability。
4. 商业门槛不再一刀切：销售产品可压制产品研发推断，但正文开发企业软件仍保留直接软件证据，并标记用途非医疗产品。
5. 质量、制造、服务和临床研究使用各自研发证据规则，不能共用“含 engineer 即研发”。
6. 对中文、德文和混合 boilerplate 做独立解析测试。
7. 报告生成器加入分母、track 状态、标题证据定义的自动一致性检查。
8. 新方向判断必须另接时间序列和独立项目证据，不由岗位分类器输出。

24 条逐案例证据见 `S031_CASE_STUDIES.zh-CN.md`；下一步人工验证和工程优先级见 `NEXT_STEPS.md`。
