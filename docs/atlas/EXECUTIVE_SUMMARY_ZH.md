# ATLAS-001 项目负责人总结（中文）

**日期：** 2026-11-10
**基线：** `main` = `b2a14c0a92332c004445de686daee97754cf94cb`
**开发分支：** `foundation/atlas-001`（从核实过的主干切出，未修改 main，未合并任何 PR）
**交付形式：** GitHub Draft PR [#28](https://github.com/ChazY11/medradar/pull/28)
**交付提交：** `c015a97a1005929d19363ff835c010bb81d7ab70`（分支 `foundation/atlas-001`）

---

## 一、我们实际建设了什么

不是一个新模型，也不是一份新报告，而是**可运行的科研基座**：

1. **ATLAS-ID 身份系统**（`medradar/atlas/identity/`）
   - Company / Manufacturer / Device / Identifier 四类实体，标识符强制带 scheme、issuer、scope；
   - 7 种关系类型，明确区分「来源声明」「结构化推导」「语义推断」三种权威级别；
   - 官方标识相等才允许 `SAME_DEVICE_IDENTITY`；名称相似只能生成候选。

2. **ATLAS-EVIDENCE 统一证据库**（`medradar/atlas/evidence/` + `store.py`）
   - 一条证据一行，不可变版本；`(evidence_id, version)` 追加式；
   - 四时钟：事件时间 / 来源公开时间 / 系统首次观测时间 / 本次获取时间；
   - 公开时间带精度（exact/day/coarse/derived/unknown），derived/coarse 不允许用于领先时间结论；
   - 跨源去重键只由权威标识符生成，同一上游（openFDA UDI 与 AccessGUDID）算重复，不算互证。

3. **可迁移数据库**（`db/migrations.py`）
   - 版本号 + 校验和；迁移前自动备份；失败整体回滚；编辑已应用迁移会直接报错；
   - 不触碰原有研究数据库，只在 `research/atlas/staging/` 下建库。

4. **知识图谱与查询**（`graph/`）
   - 只创建来源直接声明的关系（MANUFACTURED_BY / REGISTERED_AS）和身份关系；
   - 7 个 JSON 查询：公司→设备、设备→身份、公司→设备→官方身份→监管记录、技术分类→公司、
     关系证据与历史、被拒绝关系及理由、研究候选（无数据时明确返回 `NOT_COLLECTED`）。

5. **历史与前瞻**（`research/`）
   - `as_of(T)` 严格区分「当时确实观测到」「按公开日期推定可见」「无法证明」；
   - 前瞻候选登记表：带首次观测时间、当时已知标识符、状态；后续事件追加，不回填。

6. **质量与独立复核**
   - 9 类自动质量检查，把「抓取失败」变成 finding，而不是「0 条事件」；
   - `tools/verify_atlas.py` 只读打开数据库，用独立实现重算哈希、数量、关系不变量和基线算术。

7. **真实数据试点**
   - openFDA UDI + AccessGUDID + FDA 510(k) + Health Canada MDALL；
   - 5 家企业、每种来源有界采样；MDALL 活跃标识表完整流式读取一次（约 2.2 亿字节）。

---

## 二、相比开始之前新增了什么能力

| 能力 | 开始前 | 现在 |
|---|---|---|
| 统一产品身份模型 | 无（仅名称/公司配置） | 四实体 + 标识符 scheme/issuer/scope |
| 跨源身份关系 | 关键词匹配原型 | 934 条官方标识确认关系，1,146 条带理由的拒绝 |
| 证据不可变历史 | 仅 TKG 局部位时表 | 全量证据版本 + 关系撤销历史 |
| 四时钟 | 分散/混用 | 统一实现，derived/coarse 显式标记 |
| 历史状态查询 | 单快照回放 | observed / public_inferred / unprovable 三态 |
| 数据库迁移 | 无版本机制 | 校验和 + 备份 + 回滚 |
| 质量报告 | 人工复制统计 | 自动 findings + 机器报告 + 独立复算 |
| 可查询知识关系 | 无统一 CLI | `python -m medradar.atlas query ...` |

---

## 三、全球产品身份问题解决到什么程度

**可以确认的：**
- 934 对「同一 UDI-DI 同时出现在美国 GUDID 与加拿大 MDALL」的设备关系，来源声明级确认；
- 185 条产品族关系（同一 510(k)/licence 或同企业同产品代码）；
- 1 条同型号不同 DI 的 `SAME_MODEL` 关系（明确不等于同一设备）；
- 20 条完整的「企业→设备→官方 DI→监管记录」证据链，可在 CLI 中复现。

**仍无法解决的，以及原因：**
1. **MDALL 只有 0.33% 的活跃标识符行是 GTIN-14**（5,512 / 1,673,926）。其余是型号/目录号，
   没有可对齐的官方 UDI。所以「美加设备身份」只能覆盖采用 UDI 的那一小部分，不能声称全球覆盖。
2. **GUDID 公开接口不含 510(k) 号**，所以「设备↔510(k)」目前只能是候选/族级，不能确认。
3. **EUDAMED、NMPA UDI 未接入**：需要合法访问前提，本轮不做抓取、不借用账号。
4. **没有人工金标准标签**：本轮不声称总体 Precision/Recall/F1；只报告采样配对上的结果
   （934 正例全部命中、0 误报；名称基线 0 命中、33 误报）。

---

## 四、是否获得真正新增的数据资产

| 指标 | 数量 |
|---|---:|
| 证据记录（唯一 evidence_id） | 7,254 |
| 证据版本 | 7,254（本轮无重复版本） |
| 唯一设备实体 | 5,543 |
| 设备标识符行 | 16,377 |
| 公司实体（五家目标企业） | 5 |
| 确认级身份关系 | 934 |
| 确认级族/型号关系 | 186 |
| 候选级关系 | 51 |
| 拒绝关系（含理由） | 1,146 |

**记录数 ≠ 唯一实体数 ≠ 确认关系数**，三者分开报告。原始响应正文不进入 Git，只保留
哈希、有界样本和可复现的采集日志。

---

## 五、失败的方案与处理

1. **把 MDALL 的 `device_identifier` 当成 UDI-DI 去比较**：第一轮 934 条真关系全部被判为
   「标识符冲突候选」。修正：MDALL 视图不伪造型号字段，标识符相等即来源声明；矛盾检测保留。
2. **用 `licence_number=` 查询 MDALL**：返回 21 MB 全表，超时。改用 `?id=` 单条查询（0.7 秒）。
3. **用公司法定全名搜索 openFDA**（"Medtronic plc"）：返回 404，被当成 0 条。修正：使用经验证的
   检索词，并把 404 记录为覆盖错误。
4. **德语变音折叠丢字母**："Dräger" → "DRAGER"，永远匹配不上 "DRAEGER"。改为双字母转写。
5. **`as_of` 把抓取边界套用到公开可见性**：2019 年的公开记录被错误隐藏。修正为只对 observed 生效。
6. **质量检查逐行输出 7,595 条**：报告不可读。改为按来源聚合为 53 条。
7. **单次历史快照不能当 point-in-time 数据库**：没有观测过的历史版本无法回放。已在文档和
   `as_of` 的 caveats 中明确标为 UNKNOWN，而不是假装可回放。

---

## 六、系统现在能运行哪些真实研究查询

```bash
python -m medradar.atlas query path --key medtronic
```

返回 20 条完整链：`Medtronic plc → 设备（DI 00613994567611 等）→ GUDID 官方身份 →
带 URL/哈希/四时钟的监管记录`，`chain_complete=true`。

其他可用查询：

```bash
python -m medradar.atlas query company --key medtronic      # 公司→有证据的设备
python -m medradar.atlas query tech --key IYN               # FDA 产品代码→企业
python -m medradar.atlas query relation --key <relation_id> # 一条关系的证据+历史
python -m medradar.atlas query rejections                   # 被拒绝关系及理由
python -m medradar.atlas as-of --at 2026-11-10T00:00:00Z --basis observed
python -m medradar.atlas as-of --at 2019-01-01T00:00:00Z --basis public_inferred
```

一次真实查例已提交在 `research/atlas/reports/examples/query_relation_confirmed.json`：
两端的 evidence_id、来源 URL、DI、时间、哈希和关系判定依据全部可核对。

---

## 七、代码与数据库是否安全

- 未修改 `main`，未合并任何 PR，未 force-push；开发在独立 worktree/branch。
- 未改动 `data/`、PHOENIX 冻结结果、S-028/S-029 研究资产；只新增 `medradar/atlas/`、
  `docs/atlas/`、`research/atlas/`、测试、CI 和工具。
- 无密钥、token、`.env`；全仓库凭据模式扫描 0 命中。
- 未使用 UCL 账号或订阅；未联系学校；未申请算力；未调用付费服务。
- EPO OPS 等受限来源仅登记，不抓取、不存储；验证器断言数据库中 restricted 证据为 0。
- 提交的样本仅有界、可再分发（openFDA CC0 / 加拿大开放政府许可），并附归属说明。

---

## 八、下一阶段建议（按优先级）

1. **设备↔510(k) 候选实验**：用 FDA registration/listing 关联，量出可确认率；不做自动升级。
2. **EUDAMED / NMPA 访问决策**：由项目负责人决定是否申请合法访问；在此之前不抓取。
3. **MDALL licence 详情规模化**：把品牌/族名补到更多加拿大记录，量化剩余覆盖缺口。
4. **人工复核 51 条候选关系**：建立人类标签集，与机器候选分离记录。
5. **接入 OpenAlex / Europe PMC / ClinicalTrials.gov**：仍只做候选关系，需人工可核查规则。
6. **前瞻评估协议预注册**：6–12 个月后用第二市场注册作为结果，报告基线与置信区间。

---

## 复现命令

```bash
python -m pytest tests/test_atlas_identity.py tests/test_atlas_evidence.py \
  tests/test_atlas_db.py tests/test_atlas_research.py tests/test_atlas_connectors.py -q
python tools/run_atlas_pipeline.py
python tools/verify_atlas.py
```

预期：ATLAS 测试全绿；流水线产出 `research/atlas/reports/identity_pilot.json`；
独立验证 14/14 通过。数据库与缓存不入库，报告与有界样本入库。
