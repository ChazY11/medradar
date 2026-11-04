# MedRadar 第二阶段总结：本地小模型真实实验

**日期**：2026-11-04　**分支**：`research/local-llm-foundation`（Draft PR #19）
**一句话**：MedRadar 第一次在本机 GPU 上真正跑起了自己的医疗产业事件抽取模型——Qwen3-4B-Instruct 以 4-bit NF4 在 RTX 5080 Laptop 上完成 19 份真实公开文档的推理，并通过了证据验证；QLoRA 训练管线完成了技术性验证；**正式科研微调仍被阻断（`RESEARCH_TRAINING_BLOCKED`）**。

本文只总结已经发生的事。所有数字都能在 `results/phase2-2026-11-04/` 的产物里复核。

---

## 一、本轮完成的工作（按顺序）

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| 独立审计 PR #19 | **VERIFIED** | 独立审计发现 26 个问题、2 个 BLOCKER；本轮修复了会影响本次实验有效性的 12 项（见第四节） |
| 本地 GPU 环境 | **VERIFIED** | Windows 原生 + `torch 2.9.1+cu128`，独立 venv，全部依赖固定版本；用真实张量计算验证 sm_120，而不是只看 `nvidia-smi` |
| 模型下载与加载 | **VERIFIED** | `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f…`，13 个文件全部 SHA-256 校验通过；4-bit NF4 加载成功 |
| GPU 推理 | **VERIFIED** | 19/19 文档推理完成，JSON 合法率 100%，19/19 定位到原文逐字引用 |
| 真实文档实验集 | **VERIFIED** | 19 份真实公开文档（openFDA 510(k)/PMA/召回 + ClinicalTrials.gov），覆盖五家企业，含来源、获取时间、内容哈希 |
| 规则 vs 模型对照 | **VERIFIED（测量）/ EXPLORATORY（准确率）** | 见第二节；准确率只有"源记录银标签"，不是人工金标准 |
| QLoRA 技术验证 | **VERIFIED（管线）** | 真实前向/反向/Adam、LoRA 参数更新、checkpoint 保存、**跨进程**重载并恢复优化器状态、适配器推理 |
| 正式科研微调 | **BLOCKED** | 缺独立人工事件抽取标签，不降低数据标准 |
| 预测/早期信号验证 | **NOT_RUN** | 不在本轮范围，且抽取尚未达到可评估水平 |

---

## 二、核心结果（同一批 19 份文档）

| 指标 | 规则基线 A | Qwen3-4B-Instruct B |
| --- | --- | --- |
| JSON 合法率 | 19/19（100%） | 19/19（100%） |
| 定位到逐字引用的文档 | 5/19（26.3%） | **19/19（100%）** |
| 抽取事件数 | 5 | 20 |
| 弃答（abstain） | **14** | 0 |
| 验证通过 / 隔离（文档） | 18 / 1 | 12 / 7 |
| 单文档延迟（中位） | **0.010 s** | 25.90 s |
| 峰值显存（单次，最大） | 无（CPU） | **5,020 MiB** |
| 进程峰值内存 | 34 MiB | 2,324 MiB |
| 解码速度（中位） | — | 9.95 tokens/s |

**银标签一致率（EXPLORATORY，不是准确率）**

| 字段 | A | B |
| --- | --- | --- |
| 公司 | 5/19（26.3%） | **19/19（100%）** |
| 事件类别 | 2/19（10.5%） | **17/19（89.5%）** |
| 事件日期 | 1/19（5.3%） | **17/19（89.5%）** |

**按文本风格拆分（这张表最重要）**

| 风格 | 文档数 | A 类别 | A 日期 | B 类别 | B 日期 |
| --- | --- | --- | --- | --- | --- |
| 散文（企业/申办方原文） | 10 | 2/10 | 1/10 | **10/10** | **10/10** |
| 字段渲染（510(k)/PMA 记录） | 9 | 0/9 | 0/9 | 7/9 | 7/9 |

结论要克制地读：
- 模型在**散文文档**上 10/10，规则基线几乎失效（它本为散文关键词设计，但在这批文档上覆盖率差）；
- 模型在**结构化记录**上 7/9，两次错误都是 PMA 补充申请被标为 `manufacturing_change`，属于类别粒度的真实分歧；
- 89.5% 是**与同一来源记录派生银标签的一致率**，衡量的是"读取保真度"，不是"抽取准确率"，不能对外引用为模型准确率；
- 成本不低：约 2,000 倍延迟、约 3.7 GB 显存。

---

## 三、实跑暴露的问题（都已记录，部分已修复）

1. **prompt 缺陷**：`technology_domains` 在 schema 里是闭集，但 prompt 没给词表，模型只能猜 → 8 个事件被隔离。修复方式是把 23 个 domain 渲染进 prompt，这属于协议变更，必须在下一轮评估前声明。
2. **验证器缺陷（日期格式）**：日期在证据中的校验只认 ISO 格式。模型抽对了日期（2026-10-06），但引用了原文的 `10/06/2026` 写法 → 5 个事件被误隔离。
3. **验证器缺陷（时间顺序）**：规则假设"文档发布时间不能早于事件时间"，但临床试验注册恰恰先注册后开始 → 5 份注册文档全部触发，其中 2 份被隔离。该规则对前瞻性注册不成立。
4. **解码预算**：1 份文档在 512 tokens 处截断，第二个事件受污染。属于真实预算失败。
5. **训练显存陷阱（已修）**：单进程里保留三份模型 → 15.8 GB、100% 占用、无进展，被主动终止；随后发现 resume 路径悄悄丢失了 gradient checkpointing（未重新调用 `prepare_model_for_kbit_training`）→ 峰值 30,887 MiB、每步 87–172 s；修复后 7,036 MiB、约 2.7 s/步。
6. **NaN 损失陷阱（已修）**：`max_seq_len=512` 把 1.1k token 的 prompt 之外的目标全截掉，标签全 `-100` → loss=NaN。现在训练器显式拒绝该配置，并拒绝记录非有限 loss。

---

## 四、审计修复清单（本轮完成）

| 审计项 | 修复 |
| --- | --- |
| 模型适配接口能否真正加载模型 | 已实跑验证；顺手修了 `device_map` 静默下沉 CPU、context 越界无检查、dtype 参数版本差异 |
| Qwen3 tokenizer / chat template / 结构化输出 | 增加 `enable_thinking` 仅在有该变量的模板上传 `False`（2507 Instruct 无此变量，记录为 `thinking_supported=false`）；prompt/template 哈希入册 |
| JSON Schema 与 Python 契约一致性 | 未改（审计确认一致）；补了 34 个针对性测试 |
| 验证器误判/漏判/循环验证 | 修复**实体自证循环**（模型自己的 raw_text 不再能证明公司身份）；新增测试复现"对的 raw_text、错的公司" |
| Benchmark 是否隔离测试数据 | 审计确认缺失；本轮真实语料全部 `split=test`、且不参与训练；缺陷仍记录在案（见"未完成"） |
| GPU 显存检测与保护 | 每次推理前 `reset_peak_memory_stats` + 同步，逐次测量；训练前测量空闲显存，低于 5,500 MiB 拒绝启动 |
| 训练模块是否为占位实现 | 审计确认原 `run_train` 只做预检、不训练；新增**可执行**的 `training/smoke_train.py`（两阶段、可恢复） |
| 重复代码/过度抽象 | 未做大改（审计建议不要在首次真跑前重构）；记录为后续事项 |

---

## 五、科研资格判断

**`RESEARCH_TRAINING_BLOCKED`**：正式 QLoRA 科研微调**没有启动**，也没有以任何形式暗示"微调后更好"。

阻断条件（均未满足）：
- 独立可靠的事件抽取人工标签：**0 条**（69 份证据包 `human_label` 全空）；
- 训练/验证/测试隔离：无标签就无法建立；
- 预注册指标：指标已定义，但无法计算；
- 可复现训练配置：已具备（配置+种子+哈希），但无合格数据。

允许并已完成的是**技术性训练测试**：用明确标注的合成数据跑通管线。它只能证明"训练能跑"，不能证明"模型变强"。适配器 6 步训练后的输出是 `{"event": ...}` 这种自由 JSON，而不是项目 schema——这正是"技术测试 ≠ 能力提升"的直接证据。

---

## 六、本轮没有做的事（NOT_RUN，明确不声称）

- 正式 QLoRA 微调、Arm C 对照；
- 多随机种子方差、逐类别 Precision/Recall/F1；
- 预测/早期信号评估、point-in-time 回测；
- 对任意网页/新闻稿的泛化；
- 任何"模型能预测医疗技术发展"的结论。

---

## 七、下一步科研建议（按优先级）

1. **先修 prompt 再重跑**（成本最低、收益最大）：把 23 个 domain 与 50 条 track 渲染进 prompt，把日期引用规则写成"引用中必须出现 ISO 日期或原样日期片段"。这是一次协议修订，须事先登记并与本轮结果并列报告，不能覆盖本轮数字。
2. **给验证器补两个回归测试再修**：日期格式（ISO + 源格式）与前瞻性注册的时间顺序。修复后重跑，观察"隔离率"变化——这本身就是一个可发表的方法学结果：*多少"模型错误"其实是验证器的错误*。
3. **人工标注 20–30 份文档**（最小可行）：五家企业、四种来源各覆盖，两人独立标注 + 分歧仲裁。有了它，才能第一次计算真正的 Precision/Recall/F1，才能谈 Arm C。
4. **再决定是否微调**：如果人工标注显示基础模型在"证据引用"和"弃答"上仍明显不足，QLoRA 才有明确的改进目标；否则优先做 prompt/解码与约束解码（如 JSON grammar），成本远低于训练。
5. **冻结并扩充语料**：当前 19 份只够功能实验。扩到 60–100 份时，务必保留 `text_style` 分层与采集时间戳，禁止把事后可见文档伪装成当时可得信息。
6. **产品隔离**：以上全部留在 `experiments/local_llm_event_extraction/`，不进入 `medradar` 产品逻辑。

---

## 八、如何复核

```powershell
# 环境与 GPU（真实张量计算，不是 nvidia-smi）
D:\DEPPSKK\mlenv\Scripts\python.exe ...\scripts\verify_cuda.py --out gpu_verification.json

# 权重完整性（13 个文件逐一 SHA-256）
D:\DEPPSKK\mlenv\Scripts\python.exe ...\scripts\verify_model.py

# 单文档端到端（加载 → JSON → 验证 → 资源）
$env:MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD="1"
D:\DEPPSKK\mlenv\Scripts\python.exe ...\scripts\model_smoke.py --doc-id fda510k-k260579

# 规则 + 模型 双臂对照（约 9 分钟）
D:\DEPPSKK\mlenv\Scripts\python.exe ...\scripts\run_real_document_experiment.py `
  --weights-path D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507 --max-new-tokens 512

# QLoRA 技术验证（两个进程）
$env:MEDRADAR_LOCAL_LLM_ALLOW_TRAINING="1"
...\training\smoke_train.py --phase train  --steps 6 --out <dir>
...\training\smoke_train.py --phase resume --checkpoint <dir>\checkpoint-step-3 --steps 6 --out <dir>
```

产物索引：`results/phase2-2026-11-04/`（环境、模型、实验、训练、单文档冒烟）＋
`docs/PHASE2_ENVIRONMENT.md`（环境与版本锁定）＋`docs/PHASE2_REAL_RUN.md`（英文技术报告）。

---

## 九、科研完整性声明

- 未修改 `main`、未合并其他 PR、未删除历史研究材料、未提交模型权重或训练 checkpoint、未改动 S-028/S-029 研究记录；
- 语料全部来自公开 API 的真实响应，逐字保留，未由 AI 生成或改写；每份文档有 `content_sha256` 与 `raw_sha256`，加载时重新校验；
- 模型输出、失败案例、NaN/显存事故全部保留，没有做"清理"；
- 未把探索性一致率写成准确率，未把技术性训练测试写成能力提升；
- 所有实验产物通过 manifest、模型 revision、权重指纹、数据哈希、配置哈希与随机种子关联。
