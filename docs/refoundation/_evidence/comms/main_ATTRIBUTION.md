# 开发署名 / Attribution

## 一句话

**截至 `v0.2.2`（提交 `7a639f7`）的稳定核心由 DeepSeek Harness 智能体团队使用 `deepseek-flash` 完成；`v0.3.0`（提交见 `docs/INTEGRATION_2026-11-02.md`）在独立取证审计与缺陷修复后合并了研究底座与 Market-to-R&D 分支。后续增量的署名见文末，不回溯改写稳定核心的开发记录。**

## 增量贡献（后续）

| 时间 | 内容 | 负责方 |
|---|---|---|
| 2026-11-01 | **TKG 双时态知识图谱 MVP**（`medradar/tkg/`：append-only 存储、as-of 查询、确定性 PIT 导出、只读 events 适配器、`python -m medradar.tkg` CLI、31 个离线测试、ADR 与验收规范修订） | **Kimi Code**（分支 `research/tkg-mvp`；仅上述 TKG 增量，不改动既有采集/回放/分析路径） |
| 2026-11-01 | 独立审计 AUDIT-KIMI-001 + TKG/PIT 验收规范 VALIDATION-DESIGN-002（报告与规范，无代码） | Kimi Code（独立审计） |
| 2026-11-01 | TKG-HARDEN-005 对抗性加固（端点可见性合同、重提交守卫、微秒级规范时间戳、tkg-schema-2、11 个对抗性回归测试、TKG_HARDENING_REPORT） | Kimi Code（分支 `research/kimi-tkg-hardening`，独立复审上下文） |
| 2026-11-01 | **Forecast Registry**（`medradar/forecast_registry.py`：不可变预测注册 + 确定性二值结果评估、append-only 结果账本、as-of 评估、确定性导出工件、CLI、43 个离线测试、FORECAST_REGISTRY.md + ADR） | **Kimi Code**（分支 `research/forecast-registry`） |
| 2026-11-01 | **FOUNDATION-INTEGRATE-007 集成与对抗性复审**（cherry-pick 上述两支；修复未来事件正解、horizon 派生 window_end、fixture 污染隔离、TKG schema 版本门禁、source_version 溯源表述更正；8 个新对抗性测试 + 独立探针套件） | **Kimi Code**（分支 `research/research-foundation-integration`，同模型全新上下文复审，独立于作者会话与 TKG-HARDEN-005 会话） |

> 2026-11-02 起，上述三个研究分支已由 DeepSeek Harness 智能体团队完成独立取证审计（含真实数据重下载与实验重跑）、缺陷修复与整合；历史署名保留，不追认未经核验的能力。详见 `docs/INTEGRATION_2026-11-02.md`。


## 开发主体

| 项 | 内容 |
|---|---|
| 开发框架 | **DeepSeek Harness (DSH)** —— 智能体团队编排（Agent Teams + 目标模式 + 任务板） |
| 模型 | **deepseek-flash**（深度求索 / DeepSeek，中国国产模型） |
| 开发时间 | 2026‑10‑31（约 11 小时连续自主迭代，多轮目标模式） |
| 团队形态 | 1 个 Lead（负责集成、验收、发布）+ 8 个专职智能体 |
| 外部模型 | **无**（没有使用任何非国产模型） |

## 智能体分工

| 智能体 | 职责 |
|---|---|
| Lead | 架构、集成、CLI/指标契约、真实数据全链路验收、发布与 GitHub 推送 |
| dev-device | openFDA 器械采集（510(k)/PMA/召回）、全历史回填、产品码词典 |
| dev-drug | 药品批准、ClinicalTrials.gov 全历史、NMPA 适配器（诚实不可用） |
| dev-quant | 价格层、事件研究、模拟盘与成本模型 |
| dev-viz | 19 章中文报告 + 自包含 HTML 看板 + 交互式 dashboard |
| dev-product | 204 个产品族、2,740 条中文产品名、新品雷达 |
| dev-replay | 7 年回放引擎（1 分钟/日线、10/25/50bps）、假设登记表 |
| dev-research | 统计模块（block bootstrap、Holm）、可复现校准 harness、研究协议 |
| dev-pack | 打包（wheel data-files）、`MEDRADAR_HOME`、demo/doctor/watchlist、CI |

## 交付规模（可复核）

- **375,378** 条事件（510(k) 176,466 / PMA 57,372 / 召回 59,646 / 试验 55,592 / 药品 5,326 / 8‑K 催化剂 20,976）
- **20,976** 份 EDGAR 8‑K 语料，**2,384** 个可追溯案例（含逐字证据与价格反应）
- **625** 个离线测试全绿（`v0.4.0`，py3.10/3.11/3.12）；19 章报告；7 视图交互式看板；GitHub Pages 在线
- 数据来自公开来源（openFDA、ClinicalTrials.gov、SEC EDGAR、Yahoo Finance），不包含任何非公开数据

## 复核方式

```bash
git log --oneline            # 全部提交均来自该智能体团队
python -m medradar selftest  # 625 tests, 不联网
```

> 说明：以上署名为开发过程事实陈述，不构成对模型能力的第三方评测；项目内容仅用于开源研究与技术演示，不构成投资建议。

## Market-to-R&D 功能分支（2026-11-01）

`feature/market-to-rd` 的仓库审计、SEC/XBRL 与 USAspending 数据层、openFDA 批量流式管线、时点数据集、滚动回测、Horizon 登记、测试与研究文档由 **Kimi K3.1（Moonshot AI）独立执行**。未调度 Codex、GitHub Copilot 编码代理或其他 AI Agent。真实数据、负面实验结果和未能完成的边界均保留在 `experiments/reverse_rd_v1/` 与 `docs/REVERSE_RD.md`。

## 整合与缺陷修复（2026-11-02，`v0.3.0`）

| 内容 | 负责方 |
|---|---|
| 三个分支（#2 研究底座 / #3 Market-to-R&D / #1 前沿雷达）的独立取证审计：隔离 worktree、逐项复现、真实数据重下载与实验重跑、对抗性探针 | DeepSeek Harness 智能体团队（`deepseek-flash`；报告见 `medradar-orchestration/audit2/`，结论摘要见 `docs/INTEGRATION_2026-11-02.md`） |
| 缺陷修复：py3.10 时间解析、日期型微秒定宽、registry key-rebind 守卫、purge/embargo、朴素/persistence 基线、独立 as-of 泄漏重放、AdCom 空结果、case 价格基准、重复文档、前瞻性门槛说明 | DeepSeek Harness 智能体团队（fix 分支 `fix/pr2-defects`、`fix/pr3-science`、`fix/pr1-frontier`） |
| 整合：三支合并、文档与版本统一、py3.10/3.11/3.12 测试矩阵、wheel 冒烟、行为式验收脚本、推送整合分支（不合并 main） | DeepSeek Harness 智能体团队（`integration/market-to-rd-v2`） |

**PR #1 的来源说明**：`feat/frontier-device-radar` 的 Git 提交由 `ChazY11` 账号提交，本记录不推断其生成方式；其内容已在 2026-11-02 的审计中逐项核验（真实采集器、无伪造数据；AdCom 采集器对实时页面失效已修复），并以 squash 方式合入，不保留其原始提交历史（原因见整合记录 §3）。

## Phase 1–2 研究增量（2026-11-02，`v0.4.0`）

| 内容 | 负责方 |
|---|---|
| Phase 1：休眠→进入（`first_entry_v1`）目标、左删失说明、6 个 entry 特征、`holdouts=K` 多窗口评估、泄漏重放扩展、41,003 样本真实实验 | DeepSeek Harness 智能体团队（`phase1/entry-multiwindow` 分支） |
| Phase 2A：`market_bars` 只读导入 + 8 个 PIT 市场特征 + 真实消融 | DeepSeek Harness 智能体团队（`phase2/market-features` 分支） |
| Phase 2B：OpenAlex 论文采集/特征（51 家公司、150,087 works）+ 需 API key 的 USPTO 专利适配器（未评估）+ 消融 | DeepSeek Harness 智能体团队（`phase2/publications-patents` 分支） |
| Phase 2 整合、A–G 特征消融矩阵、`ablation_metrics.json`、文档与验收 | DeepSeek Harness 智能体团队（`integration/market-to-rd-v2` 分支，Lead 集成） |

## Phase 3 研究闭环（2026-11-02，`v0.5.0`）

| 内容 | 负责方 |
|---|---|
| Phase 3A：规范登记簿新增 `nowcast` 类型 + 队列隔离、Horizon→canonical 适配器、幂等持续预测周期（25 条真实 nowcast）、周度 workflow | DeepSeek Harness 智能体团队（`phase3/registry-cycle` 分支） |
| Phase 3B：真实 55,090 条事件只读导入双时态 TKG（57,381 节点 / 114,419 边、确定性 PIT 快照、重复导入幂等）、`graph_context` 只读查询 | DeepSeek Harness 智能体团队（`phase3/tkg-integration` 分支） |
| Phase 3C：确定性证据驱动研究 Agent（8 工具、5 模板、冲突检测、反证、引用式综合、19 个离线测试）与真实演示 | DeepSeek Harness 智能体团队（`phase3/research-agent` 分支） |
| Phase 3 整合、真实 registry/TKG/Agent 端到端复跑、行为式验收与文档 | DeepSeek Harness 智能体团队（`integration/market-to-rd-v2` 分支，Lead 集成） |

> Phase 3 的 TKG 知识时钟等于回填观测时间（不是历史公开时间）；预测登记簿尚无到期预测（校准为 `insufficient_data`）；研究 Agent 只叙述存储证据，不做因果断言；专利/招聘仍是明确的证据缺口。

> 所有 Phase 1–3 结果均为真实数据可复现实验；新增来源的增量价值结论为负面（无统计可检测的排序增益），已如实报告。专利因缺少 USPTO ODP API key 未评估，采购因快照不可作时点使用而排除。

> 以上为开发过程事实陈述，不构成对任何模型能力的第三方评测；项目仅用于开源研究与技术演示，不构成投资建议。
