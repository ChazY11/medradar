# MedRadar

**一个以可验证公开证据为基础，研究医疗技术发展变化及早期信号的开放科研项目。**

MedRadar 把公开的监管、临床试验与公司披露证据采集进一个可审计的事件数据库，用来回答一个问题：

> **公开可观察的信息，能否为医疗技术发展的重要变化提供可靠、可重复验证的早期信号？**
>
> Can publicly observable evidence provide reliable early signals of meaningful changes in medical
> technology development?

它是**研究工具，不是产品**：目前没有证明能预测医疗器械产业走向，也不构成任何投资建议。

> English README → [README.md](README.md)
> 当前状态、研究索引与路线图 → [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)
> 数据资产清单 → [docs/DATA_ASSET_REGISTER.md](docs/DATA_ASSET_REGISTER.md)
> 仓库审计 → [docs/REPOSITORY_AUDIT.md](docs/REPOSITORY_AUDIT.md)

本文件只保留中文摘要，**不**与英文 README 维护两套完整但会不同步的文档。权威内容以 `README.md`
与三份治理文档为准。

## 现在真正能做什么（`main` 分支，已有离线测试）

- **公开数据采集**：openFDA 510(k)/PMA/召回/分类/药品批准、ClinicalTrials.gov v2、可选 SEC EDGAR 8-K，
  统一写入一个 SQLite 事件库；所有 HTTP 响应被缓存，每个阶段可单独重跑。
- **时点（point-in-time）事件模型**：每条事件带事件时间、发布时间、首次观察时间、可用时间与
  `timestamp_quality` 分级；只有 `estimated`/`unknown` 的记录只作描述，不进入推断。
- **指标与统计**：Gamma–Poisson 收缩、赛道热度、产品码结构变化（JS 散度）、首次出现、
  block bootstrap 与 Holm 校正。
- **报告与看板**：19 章中文报告 + 自包含 HTML 看板与回放时间线（零外部请求，可离线、可 GitHub Pages）。
- **案例库与事件研究**：可追溯案例、1/5/20/60 日异常收益、模拟盘（非真实交易）。
- **研究基础设施**：双时态知识库（有效时间 vs 知识时间）、只追加预测登记册（as-of 评估）。
- **离线测试**：1,074 项检查（47 个模块，约 25 秒，无需网络、无需 API key）。

## 目前不能宣称什么

- **没有**证明可以预测医疗技术变化（`research/RESULTS/README.md` 原文：
  *"The system, as of v0.5.0, has not demonstrated predictive skill for corporate technological entry."*）。
- **没有**测到领先时间：预注册的 G1 门只有 3 个合格对（门槛 10），判 NO-GO。
- **没有**校准过的预测：25 条前瞻预测尚未到期（最早窗口 2027-10）。
- **没有**时点可用、经人工核验的关系网络：S-029 判 `NO-GO FOR PREDICTION`，人工核验待完成。
- **没有**生产部署：Observatory 仅本机部署（`DEPLOYED_LOCAL`），七天验证仍在进行中。

## 研究结果摘要（均为负结果，按原始记录表述）

| 研究 | 状态 | 结论 |
|---|---|---|
| 五家企业早期信号研究（`main`） | 已完成 / 负结果 | 在「企业 × 赛道 × 季度」粒度上，现象出现得不够频繁，无法测量；**瓶颈是信息，不是建模**。69 个候选包仍待人工标注。 |
| S-028 图结构早期信号（草稿 [PR #15](https://github.com/ChazY11/medradar/pull/15)，未合并） | 探索性 / 负结果 + Correction 1 | ΔAP = −0.00609，两个聚类 CI 均含零，0/3 窗口排除零：**未检测到改进**。Correction 1 作废了部分原始统计表述，只能作为「可信的探索性负结果」封存，**不能**作为确证性结论。 |
| S-029 证据关系网络（草稿 [PR #16](https://github.com/ChazY11/medradar/pull/16)，未合并） | 完成 / `NO-GO FOR PREDICTION` | 关系可重建、可逐条追溯，但**不是时点证据、也未经人工核验**。T4（时点）与 T6（人工核验）未通过，102 行核验工作表为空。 |
| Market-to-R&D / 前景预测（`main`） | 已完成 / 负结果 | 七种来源设定的消融：**没有任何新增来源带来可检测的排序增益**；延续性目标主要来自「持续性」。25 条预测尚无到期样本，校准状态为 `insufficient_matured_forecasts`。 |

## 快速开始

```bash
git clone https://github.com/ChazY11/medradar.git
cd medradar
python -m venv .venv && . .venv/Scripts/activate   # Windows；Unix 用 .venv/bin/activate
pip install -e .

python -m medradar demo       # 离线演示：约 0.4 秒，输出 out/demo/，打开 out/demo/index.html
python -m medradar selftest   # 离线测试：1,074 项，跳过 3 项，约 25 秒
```

真实采集（需联网、耗时数分钟，本轮整顿未复验）：
`python -m medradar run --months 24 --with-trade --with-dashboard`

## 主要限制

- 复现分两类：**克隆即可复现**（离线测试、demo、claim map 校验、S-029 证据链）与
  **只能在本机复现**（各研究需要未入库的 `data/` 数据：1.37 GB 运行库、289 MB 冻结研究库）。
- S-028 / S-029 / Live Observatory / 2.0 产品层都还在草稿分支，`main` 上**看不到**。
- 观测系统单机运行、仅本地备份，未购买任何云资源。
- 报告里的数字来自 2026-10-31 的采集快照，重跑会变化。

## 路线图（唯一当前路线图见 `docs/PROJECT_STATUS.md`）

1. **Priority 1 — 项目清晰**：仓库状态、研究状态、数据资产准确可查（本次整顿）。
2. **Priority 2 — Observatory 可靠性**：让真实观察记录与备份链可持续、可审计；七天验证按实际结果如实记录。
3. **Priority 3 — 核心科研验证**：回到「公开信息能否提供早期信号」，以少量可追溯案例的研究设计推进。

**下一步最小行动**：完成五家企业研究 69 个候选包的人工标注（工作表与校验脚本已存在）。
在此之前不启动新研究编号、不训练新模型、不扩展数据源。

## 许可与数据来源

- **代码**：MIT，见 [LICENSE](LICENSE)。（GitHub 许可检测显示 "Other"，因为 LICENSE 在 MIT 正文后
  附加了数据说明段；MIT 授权本身不变。）
- **数据**：归各发布方所有。openFDA 为美国政府公有领域数据；ClinicalTrials.gov、SEC EDGAR、
  Europe PMC、Crossref 各有条款与合理访问要求；行情数据为供应商衍生数据，不得再分发。
  仓库**不**再分发批量源数据，`data/` 运行时目录不入库。
- **署名**：按增量记录在 [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md)。
- **不构成投资建议**：组合为模拟盘，产出页面均标注。
