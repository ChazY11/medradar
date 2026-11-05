# MedRadar S-031 岗位技术能力本体 v1

状态：研究用 `AI_PRELIMINARY_LABEL` 规范，不是人工确认金标准。  
核心原则：岗位做什么、需要什么能力、提到什么产品、能否构成研发证据，是四个不同问题。

## 1. 为什么必须分四维

“机器人销售代表”“机器人控制软件工程师”和“机器人产品质量工程师”都可能在同一段文本里出现机器人。若只保留 `surgical_robotics` 一个标签，就丢失了最重要的区别：第一个人卖产品，第二个人开发技术，第三个人保证质量。

四维记录采用以下最小结构：

```text
Role Function = 这个人被招来做什么
Technical Capability = 完成工作时必须会做什么
Product / Business Context = 工作在哪个产品、客户或业务环境
R&D Evidence Strength = 这些原文能在多大程度上支持研发活动判断
```

任何一维都不能由另一维自动推出。产品背景不能自动生成技术能力；技术能力不能自动生成直接研发证据；直接研发证据也不能自动生成战略转向。

## 2. 维度一：Role Function

### 2.1 主职能与辅助职能

`primary` 是岗位职责中心和主要交付物；`secondary` 是明确存在但不占中心的职责。辅助职能不是“也可能相关”的猜测，必须有正文支持。

例：嵌入式开发同时负责子项目协调，可记 `primary=SOFTWARE_ALGORITHM`、`secondary=BUSINESS_OPERATIONS`；产品技术领导同时负责架构和项目交付，可记 `primary=PRODUCT_ENGINEERING`、`secondary=RESEARCH_DEVELOPMENT/BUSINESS_OPERATIONS`。

### 2.2 本轮函数词表

| 值 | 定义 | 不应仅凭什么判定 |
|---|---|---|
| `RESEARCH_DEVELOPMENT` | 研究、技术开发、设计探索或研发领导是主要交付物 | 公司被称为研发驱动、标题有 Development |
| `PRODUCT_ENGINEERING` | 产品设计、系统工程、工程实现、产品验证或工程交付 | 产品经理、产品支持、产品营销中的 product |
| `SOFTWARE_ALGORITHM` | 软件、算法、数据或 AI 系统的设计与实现是主职 | 会使用办公软件、销售工具含 AI |
| `MANUFACTURING_PROCESS` | 生产、工艺、设备、制造运营与放量 | 在工厂工作就一定是产品研发 |
| `QUALITY_REGULATORY` | 质量保证、供应商质量、法规、合规、设计控制 | 做 V&V 就自动等于新产品研发 |
| `CLINICAL_RESEARCH` | 临床评价、研究设计、试验执行、临床证据生成 | 临床培训、术中支持、医院客户关系 |
| `CLINICAL_APPLICATION` | 临床应用、扫描、术中支持、用户培训、疗法采用 | 熟悉临床技术就等于开发该技术 |
| `FIELD_SERVICE` | 安装、维修、诊断、维护、客户技术实施 | 维修复杂设备就等于设计设备 |
| `SALES_MARKETING` | 销售、市场、渠道、商业采用、产品营销 | 销售高科技产品就等于研发高科技产品 |
| `BUSINESS_OPERATIONS` | 采购、财务、人力、行政、供应链、企业 IT、项目管理 | 支撑研发部门就等于本人做研发 |
| `LEGAL_COMPLIANCE` | 法务、隐私、合同、法律风险 | 文本出现 AI 法规就等于医疗 AI 研发 |
| `UNCLASSIFIED` | 文本不足或职责无法可靠归类 | 为了覆盖率强行选择最相似类别 |

硬件和系统工程本轮不单列函数类，通常放在 `PRODUCT_ENGINEERING`，通过能力字段区分机械、电子、系统和验证。这样避免函数词表无限膨胀。

## 3. 维度二：Technical Capability

### 3.1 判定标准

技术能力必须回答“岗位需要做什么技术工作”，优先由职责动词和交付物支持，例如设计、开发、实现、验证、放大、分析、集成、维修。仅出现产品名、行业名、公司介绍或员工福利，不构成能力证据。

允许一个岗位有多项能力，也允许空数组。空数组表示原文没有足够能力证据，不表示岗位没有技术含量。

### 3.2 能力家族与本轮叶标签示例

JSONL 保留接近原文的细粒度叶标签，避免为覆盖率强行合并。下表是阅读与后续归一化用的能力家族，不是假装所有叶标签已经完成人工标准化。

| 能力家族 | 本轮真实叶标签示例 | 典型边界 |
|---|---|---|
| 软件与嵌入式 | C++、embedded software、Qt6、QML、real-time operating systems | 企业办公软件与医疗产品软件分开记录 |
| AI、数据与算法 | AI inference、agentic AI、digital twin、predictive analytics | Copilot 是开发工具时不自动标医疗 AI 产品 |
| 图像、视频与信号 | real-time video processing、3D imaging、hardware acceleration | 演示影像产品不等于开发图像算法 |
| 系统与硬件工程 | systems engineering、system architecture、hardware-in-the-loop、system verification | 客户部署与企业内部系统集成另记用途 |
| 机械、材料与原型 | mechanical design、GD&T、tolerance analysis、prototyping、cryogenic systems、superconducting magnets | 机械维修不等于机械设计 |
| 工艺、放大与设备 | IVD reagent process development、scale-up、technology transfer、automation equipment development、process validation | 试剂产品、生产工艺和生产设备是不同对象 |
| 制造与运营技术 | DFMA、PFMEA、SPC、OEE、lean manufacturing、production planning | 可制造性技术支持不自动变成产品研发 |
| 质量、验证与法规技术 | design of experiments、verification and validation、CAPA、regulatory submissions | 强技术质量岗可为间接证据，不必硬改成研发岗 |
| 临床研究与证据 | clinical study design、multicenter research、clinical prototype evaluation、evidence generation | 临床研究是直接研究证据，但不是工程开发 |
| 临床应用与客户支持 | three-dimensional cardiac mapping、ultrasound clinical application、clinical therapy support | 主要用于培训、采用或术中支持时不是产品开发 |
| 服务、实施与医疗 IT | medical device troubleshooting、healthcare IT integration、equipment calibration | 复杂维护或实施能力仍是间接技术证据 |
| 企业 IT 与商业数字化 | client device management、API design、MuleSoft、business intelligence | API 可指软件接口，也可指药物活性成分，必须读正文 |

### 3.3 产品词不能直接变成能力词

以下转换被禁止：

```text
提到 robotic surgery ≠ 机器人运动控制
提到 AI ≠ 医疗 AI 算法研发
提到 ultrasound ≠ 超声成像算法
提到 patient monitoring ≠ 生理参数算法
提到 API ≠ 软件 API 设计
```

只有当正文明确给出相应工作时才记录能力。例如“开发实时视频采集、处理、AI inference 和硬件加速软件”可以支持软件与视频能力；“推动机器人产品组合销售”只支持销售职能和机器人产品背景。

### 3.4 能力用途必须保留

同一种技术可以服务不同对象：

- agentic AI 用于供应链，不等于医疗产品 AI。
- Apex/Python 用于销售 enablement，不等于患者软件。
- API 工艺开发中的 API 若为 active pharmaceutical ingredient，不是软件接口。
- 非标自动化设备开发用于试剂生产，不等于试剂配方产品研发。
- Device Management 若指员工电脑和手机，不是医疗设备研发。

因此后续结构化时，每个能力还应增加 `target_object` 与 `work_activity`，本轮通过职能、产品背景和解释字段保留这些信息。

## 4. 维度三：Product / Business Context

这一维记录文本提到的产品、业务线、临床环境、客户环境或内部运营环境，例如 `robotic surgery`、`patient monitoring`、`IVD reagent production`、`integrated supply chain`、`sales enablement`。

它回答“在哪里工作”，不回答“做什么研发”。销售机器人产品的岗位可以有 `product_business_context=[robotic surgery]`，同时 `technical_capabilities=[]`、`rd_evidence_strength=PRODUCT_CONTEXT_ONLY`。

产品背景也可为空。空数组不表示公司没有产品，只表示该岗位文本没有足够具体的背景，或无需为背景分类增加推测。

## 5. 维度四：R&D Evidence Strength

证据等级评估的是“这条招聘文本支持何种研发活动判断”，不是岗位高低、技术含量高低或战略概率。

| 值 | 必要证据 | 能说什么 | 不能说什么 |
|---|---|---|---|
| `DIRECT_R&D_EVIDENCE` | 明确设计、开发、实验、研究、原型、工艺开发或研究评价活动 | 企业正在公开招聘相应研发/研究职责 | 新项目已立项、方向全新、投入很大 |
| `INDIRECT_TECHNICAL_EVIDENCE` | 有明确技术或专业行为能力，但主要用于生产、质量、服务、临床采用或运营 | 企业需要该能力来完成特定工作 | 该能力用于新医疗器械研发 |
| `PRODUCT_CONTEXT_ONLY` | 主要证据是产品、业务线、客户或市场采用背景 | 该岗位与某产品/业务有关 | 企业正在开发该产品技术 |
| `NON_R&D` | 主职明确为非研发，且没有具体技术或研究活动证据 | 此岗位本身不提供研发证据 | 企业整体没有研发 |
| `INSUFFICIENT_EVIDENCE` | 正文缺失、过短、无法理解或线索不足 | 当前文本不能可靠判断 | 凭标题、URL 或公司印象补全 |
| `CONFLICTING_EVIDENCE` | 同一文本存在实质矛盾，无法由职责中心解决 | 需要查源或人工 adjudication | 为减少 UNKNOWN 而任选一边 |

### 5.1 直接证据的子类型必须口头保留

`DIRECT_R&D_EVIDENCE` 包含工程研发、临床研究、软件研发、工艺开发和工艺装备开发，但这些不是同一种创新。报告中必须写清对象。例如“临床 prototype evaluation”支持临床研究，“试剂生产设备设计”支持工艺装备开发，都不能改写成“新医疗器械算法”。

### 5.2 证据等级不是概率

这些值没有 0.8、0.6 之类的校准含义，也不能相加得到企业研发分数。同一家公司多条直接证据仍可能来自既有产品维护、常规迭代或人员替补。

## 6. 引文与解释字段

每条预标注包含：

- `exact_evidence_quotes`：原文短句及它支持的判断。
- `support_explanation`：为什么这段原文支持当前标签。
- `alternative_explanation`：另一种同样合理的读法。
- `missing_information`：要进一步提高判断等级还缺什么。
- `needs_human_review`：是否属于优先争议或边界案例。
- `label_status` 与 `preliminary_label_source`：固定为 `AI_PRELIMINARY_LABEL`。

引文采用 NFC 与空白归一化后逐字回查。正文不可用时引文为空，不能编造一句“该岗位负责研发”。

## 7. 优先人工复核触发条件

1. 标题和正文指向不同职能，例如 Development 实为临床支持。
2. 同一岗位有多个实质职能，单标签会丢失交付物。
3. 高科技产品背景与非研发职责并存。
4. AI、API、device、development 等多义词影响结论。
5. 技术能力较强，但是否属于研发取决于团队或项目背景。
6. 直接研发证据的对象不清，例如企业 AI 与医疗产品 AI。
7. 中文、德文等标题解析或 boilerplate 可能干扰函数识别。
8. 正文缺失、采集失败或来源字段不完整。
9. 同岗多城市、重发与多人招聘无法区分。
10. 需要由“岗位有研发职责”进一步推断“战略新方向”。

## 8. 与 PR #21 旧分类的关系

旧函数类可保留为上游粗筛线索，旧产品 track 可保留为产品背景候选，但不应继续把二者拼成一个“技术能力标签”。推荐迁移为：

```text
旧 function_class → Role Function 的候选证据
旧 track keyword hit → Product / Business Context 的候选证据
职责动词 + 技术对象 → Technical Capability
活动性质 + 交付物 → R&D Evidence Strength
```

旧 `SALES_ADMIN_OTHER` 过宽，混合了销售、现场服务、法务、企业 IT、采购等岗位；旧 `UNCLASSIFIED` 也混合了真正证据不足和词表未覆盖。二者都不应自动等于 `NON_R&D`。

## 9. 本体 v1 的限制

本轮叶标签有 251 种写法，保留了细节，却尚未完成同义词归一化，例如 C/C++、verification/validation、临床研究与临床评价仍需人工维护映射。产品背景也没有统一企业产品编码。下一轮应先冻结能力家族和同义词规则，再进行双人标注，而不是直接把本轮 AI 叶标签训练成新模型。
