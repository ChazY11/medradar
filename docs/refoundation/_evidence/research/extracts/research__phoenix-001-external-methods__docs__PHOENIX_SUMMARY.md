# PHOENIX-001 — 研究总览

状态：**研究产物完成，等待人工审查；Draft PR 不自动合并。**

分支：`research/phoenix-001-external-methods`。本轮未修改 `main`、历史数据库、冻结模型或已有实验结果；未建设实时采集、购买商业服务或启动云训练。

## 核心结论

- **H1 支持**：企业—赛道监管活动有持续性。Continuation 的 pair 基线 AP=0.791259，高于发生率 0.420195、公司 0.570689 和赛道 0.506832。
- **H9 在当前协议内否定**：多源融合没有稳定超过最强单源。Continuation 监管单源 AP=0.793476，全源融合 0.786696；entry 共享财务 0.116347，全源融合 0.097863。
- **H5、H6 阻断**：缺试验→FDA 成熟目标和 MedRadar HHI→扩散面板。
- **H2、H3、H4、H7、H8、H10 未决**：联合模型不能识别单列贡献，变化检测无正新颖性证据，复杂模型未稳定超过持续性基线。
- 所有预测结果都是**类别 3：历史模拟预测**，不是独立前瞻验证。

## 外部技术吸收

13 个项目均有完整审计、证据和决定：

- **ADAPT**：SciTrends、FDA AI 纵向研究、MedVantage、NextDevice、DevicePro。
- **STUDY_ONLY**：PubTrends、NIH iSearch、The Lens、Clarivate DRG、GBI DEVINT、众成医械大数据。
- **REJECT**：CMOP。
- **BLOCKED**：PTNS。
- 无项目被轻率标为 ADOPT；候选模块必须先经过下一轮数据与集成评审。

SciTrends 作者无 DL 核心实验已复现，CatBoost R²=0.845321，但 30/30 折存在训练/测试共享年份，且存在全量均值插补。FDA 论文的 HHI、趋势、卡方和置换检验已独立复算，支持描述性多样化而非预测结论。

## 数据边界

当前环境没有 `data/medradar.sqlite` 或 `data/research.sqlite`，未重新抓取或生成替代品。统一比较只读使用既有冻结产物，记录六份源文件 SHA-256。3,833 是 material event 行数，不是独立设备数；原始 ID 去重和派生副本跨分区检查在当前环境不可复核。

REA 6.8.0 已完成官方版本、许可、依赖与资源预审。当前 Node v20.20.2 不满足要求，精确 MCP 配置未获批准，因此未安装、未注册、未执行；后续研究不依赖 REA。

## 独立候选模块

- `evidence_contract.py`：时间证据、实体所有权、分类版本与 train/validation 血缘隔离。
- `build_method_comparison.py`：20 个方法的统一冻结证据比较。
- `fda_ai_longitudinal.py`：HHI、bootstrap、趋势和稀疏表稳健性。
- SciTrends/PubTrends 隔离复现器，仅用于研究，不进入生产。

## 交付导航

- `PHOENIX_EXTERNAL_PROJECT_REGISTER.md`：13 项目技术图谱。
- `PHOENIX_LICENSE_AUDIT.md`：许可与供应链风险。
- `PHOENIX_REPRODUCTION_REPORT.md`：成功、失败、独立实现、理论研究和阻断。
- `PHOENIX_RESEARCH_PROTOCOL.md`：H1—H10 冻结定义与判定。
- `PHOENIX_METHOD_COMPARISON.md`：相同时间边界下的公平比较。
- `PHOENIX_CANDIDATE_MODULES.md`：候选模块及集成边界。
- `PHOENIX_INNOVATION_OPPORTUNITIES.md`：科研差距和可证伪新问题。
- `PHOENIX_NEXT_ROADMAP.md`：三个下一轮方向、成本和失败风险。

## 复现与验收

```bash
python3 experiments/phoenix_001/audit_assets.py
python3 experiments/phoenix_001/build_method_comparison.py
python3 experiments/phoenix_001/fda_ai_longitudinal.py \
  <REDACTED_LOCAL_PATH> \
  --output experiments/phoenix_001/fda_ai_longitudinal_results.json
python3 -m pytest tests/test_phoenix_001.py -q
python3 verifier/v1/verify.py
python3 verifier/run_v2.py
```

实际命令、退出码、资源观测和失败尾部日志汇总于 `experiments/phoenix_001/logs/index.json`。v2 每次验收另追加到 `verifier/runs/`。

下一轮优先恢复只读历史资产并做最小特征消融，其次建立试验→FDA 成熟链接样本，最后以冻结前瞻登记积累真正的 category-4 证据。复杂网络或 GNN 只有在最简模型稳定超过 pair persistence 后才值得投入。
