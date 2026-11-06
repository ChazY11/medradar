# PHOENIX-001 — 候选独立科研模块

这些模块只进入实验目录，不修改 MedRadar 正式研究结论或生产数据管线。

## 1. 时间证据与血缘隔离契约 — 可进入下一轮集成评审

文件：`experiments/phoenix_001/evidence_contract.py`

来源：MedVantage 的 filing 级证据设计，以及 S-028/S-029 暴露的实体、所有权、分类版本和跨源时间缺陷。代码为本轮独立实现，没有复制闭源平台。

提供三项检查：

- 事件必须有 source_event_id、source_locator、lineage_id、event_date、available_at 和 timestamp_quality；类别 4 只接受 `observed`。
- 公司链接必须有 matched_alias、match_rule、confidence 和所有权有效期；赛道链接必须有 taxonomy_version。
- train/validation 共享 lineage_id 时直接拒绝，另将事件行数与独立血缘数分开报告。

验收：合法历史事件通过；估计时间不能进入类别 4；未来事件、并购前归属、无分类版本、置信度越界和跨分区血缘均被拒绝。局限：尚未接入缺失的原始数据库，不能声称旧数据已满足契约。

## 2. 冻结证据统一比较器 — 保留为实验工具

文件：`experiments/phoenix_001/build_method_comparison.py`

按相同三个 holdout 原点整理 20 个方法，重算 Recall@K，记录源文件 SHA-256、三窗口波动、配对区间、子组稳定性和 S-028/S-029 风险。它没有重新训练模型，也不把聚合产物伪装成原始数据复跑。

研究价值：让 H1/H9 的支持/否定与其他假设的不可识别性可以从同一机器可读证据重建。原始 ID 去重仍标为不可复核。

## 3. FDA 专科集中度统计模块 — ADAPT 候选

文件：`experiments/phoenix_001/fda_ai_longitudinal.py`

独立实现 HHI、bootstrap、Cochran–Armitage、卡方、Cramér's V 和置换检验。公开 17×4 数据上的点估计与论文一致，测试覆盖简单 HHI 和 Radiology Z。

集成边界：只接受带版本的 company×track×time 面板。没有原始 MedRadar 映射前，不得用其输出支持 H6 的预测结论。

## 4. 外部方法复现器 — 仅限隔离研究

- `scitreands_reproduce.py`：作者 notebook 白名单复现与共享年份/全量插补审计；无许可证源码不进入 MedRadar。
- `scitreands_crispr_lags.py`：19 年描述性专利—论文相关复算。
- `pubtrends_smoke.py`：Apache-2.0 主题词函数隔离测试，不引入完整服务。

这些是研究证据，不是生产模块，也不满足 MedRadar 历史数据迁移条件。
