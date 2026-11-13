# PHOENIX-001 — 导航与阅读顺序

> 本轮任务的唯一目标：**系统分析国际同类项目，复现有价值的方法，在 MedRadar 已有历史数据上开展统一实验，最后形成自己的创新方法。**
> 分支：`research/phoenix-001-external-methods`（**未合并 main，未自动合并任何 PR**）
> 协议版本：`phoenix-001/v1`（实验开始前冻结）
> 数据：`data/medradar.sqlite`，SHA-256 `445807CA…97002C92`，**全程只读，程序结束后复核一致**

---

## 先读这三份（决策者）

| 顺序 | 文件 | 回答什么 |
|---|---|---|
| 1 | [`docs/PHOENIX_EXTERNAL_PROJECT_REGISTER.md`](../PHOENIX_EXTERNAL_PROJECT_REGISTER.md) | 13 个外部项目各自是什么、许可证、能不能跑、值不值得迁移、最终 ADOPT/ADAPT/STUDY_ONLY/REJECT/BLOCKED |
| 2 | [`docs/PHOENIX_REPRODUCTION_REPORT.md`](../PHOENIX_REPRODUCTION_REPORT.md) | 到底哪些真的跑起来了、哪些失败、为什么失败、复现指令 |
| 3 | [`PHOENIX_GAP_AND_OPPORTUNITY.md`](PHOENIX_GAP_AND_OPPORTUNITY.md) | 别人的方法哪些已被完成、哪些不能迁移、MedRadar 最硬的数据限制、哪些规律被支持/被否定、下一步该做什么 |

## 再看方法与证据

| 文件 | 内容 |
|---|---|
| [`PHOENIX_FROZEN_PROTOCOL.md`](PHOENIX_FROZEN_PROTOCOL.md) | **实验前冻结**的协议：任务定义、三档滞后场景、切分、基线、指标、H1–H10 判定规则、L1–L8 审计项 |
| [`EXPERIMENTS_CELL_H1_H2_H4_H5_H10.md`](EXPERIMENTS_CELL_H1_H2_H4_H5_H10.md) | 单元级（企业×赛道）五个假设的结果 |
| [`EXPERIMENTS_TRACK_H3_H6_H7_H8_H9.md`](EXPERIMENTS_TRACK_H3_H6_H7_H8_H9.md) | 赛道级五个假设的结果 + 半合成变化点基准 |
| [`INNOVATION_RAEA.md`](INNOVATION_RAEA.md) | 候选创新模块（监管锚定实体归属），含实测增益与**已知错误类别** |
| [`REA_VALIDATION.md`](REA_VALIDATION.md) | REA 部署与实测验证（85 KB，含 207 工具全表与全部原始日志） |
| [`../PHOENIX_LICENSE_AUDIT.md`](../PHOENIX_LICENSE_AUDIT.md) | 许可证、依赖、供应链风险与处置 |
| [`PHOENIX_ROADMAP.md`](PHOENIX_ROADMAP.md) | 下一轮 1–3 个最值得投入的方向，含成本与失败风险 |

## 逐项审计（13 个项目，无跳过）

| 文件 | 项目 |
|---|---|
| [`audits/A01_scitrends.md`](audits/A01_scitrends.md) | 1. SciTrends `ddofer/Trends` |
| [`audits/A02_pubtrends.md`](audits/A02_pubtrends.md) | 2. PubTrends |
| [`audits/A03_nih_isearch.md`](audits/A03_nih_isearch.md) | 3. NIH iSearch |
| [`audits/A04_the_lens.md`](audits/A04_the_lens.md) | 4. The Lens |
| [`audits/A05_ptns.md`](audits/A05_ptns.md) | 5. PTNS |
| [`audits/A06_fda_ai_device_longitudinal.md`](audits/A06_fda_ai_device_longitudinal.md) | 6. FDA AI 器械纵向研究 |
| [`audits/A07_clarivate_drg_medtech.md`](audits/A07_clarivate_drg_medtech.md) | 7. Clarivate DRG Medtech |
| [`audits/A08_medvantage.md`](audits/A08_medvantage.md) | 8. MedVantage |
| [`audits/A09_cmop.md`](audits/A09_cmop.md) | 9. CMOP |
| [`audits/A10_nextdevice.md`](audits/A10_nextdevice.md) | 10. NextDevice |
| [`audits/A11_gbi_devint.md`](audits/A11_gbi_devint.md) | 11. GBI DEVINT |
| [`audits/A12_devicepro.md`](audits/A12_devicepro.md) | 12. DevicePro |
| [`audits/A13_joinchain.md`](audits/A13_joinchain.md) | 13. 众成医械 |
| [`audits/A00_commercial_synthesis.md`](audits/A00_commercial_synthesis.md) | 七家商业平台的横向综合 |

## 代码与证据

```
experiments/phoenix/
├── common/phoenix_common.py       冻结的共享评估工具库（双时钟、切分、指标、bootstrap、基线、审计）
├── scripts/00–05_*.py             资产核验、覆盖事实、时间语义审计、harness 冒烟、有效性测试
├── reports/                       上述脚本的机器可读结果（含 sha256 与 integrity_check）
├── hypotheses/cell/               H1/H2/H4/H5/H10 的面板构建、主运行、审计、自测
├── hypotheses/track/              H3/H6/H7/H8/H9 的面板、进入者/HHI、主运行、变化点基准、审计、自测
├── baseline_bridge/               与既有 S-028 基线的桥接（并明确"未复现"）
├── external/methods/              A03/A05/A06 方法的独立实现 + 56/56 自测
├── external/scitrends|pubtrends/  A01/A02 的隔离算法重实现
├── innovation/                    RAEA 候选创新模块 + 自测 + 人工复核日志
├── rea/                           REA 验证脚本、测试件、证据与日志
└── evidence/                      运行日志（真实 stdout/stderr）
```

## 三条不可越过的诚实边界

1. **本轮不产生第 4 类证据。** 库里 `available_at == event_date` 且全部数据来自 2026-10-30/31 的单快照 → 没有真正的 point-in-time，也没有前瞻验证。最高只能声称"有保守公开时间约束的模拟预测"。
2. **没有复制任何第三方代码。** 所有迁移的方法都是独立重实现；无许可证的项目（SciTrends）只借鉴思想。
3. **负面结果全部保留。** H3/H6/H9/H10 未被支持；S-028 基线未被复现；A06 的 Era 1 HHI 未被复现；REA 有 8 项能力不可用。这些都写在文档里，不是附录。
