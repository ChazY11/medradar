# PHOENIX-001 — 外部方法复现报告

状态：持续追加。所有命令、退出码和日志位于 `experiments/phoenix_001/logs/`。

## 复现状态定义

- **作者代码实跑**：固定官方提交，执行上游代码或经明确白名单选取的上游 notebook 单元。
- **独立实现**：只按公开方法写新代码，不复制无许可源码。
- **理论研究**：只审查公开方法，没有运行结果。
- **受限/失败**：记录具体阻碍，不改写成成功。

## SciTrends

### 已跑通：作者核心无 DL 配置

命令：

```bash
PYTHONPATH=/tmp/phoenix_python_deps taskset -c 0-3 \
  python3 experiments/phoenix_001/scitreands_reproduce.py \
  /mnt/agents/output/phoenix_external/scitreands \
  --output experiments/phoenix_001/scitreands_results.json
```

官方提交：`81711b94181bb8d1f5bd93379670bf3250dfc343`。

复现器只执行 notebook 单元 `[1, 2, 3, 5, 6, 8, 30, 33, 34, 35, 36, 39, 40, 44, 45]`。使用作者已有的 `GET_DL_EMBEDS=False` 分支，剔除 Jupyter magic，做 `np.NaN → np.nan` 的 NumPy 2.x 兼容替换。没有执行模型下载、SHAP、未来预测或写文件单元。

结果文件：`scitreands_results.json`。最终成功日志：`017-scitreands-core-final.json`，退出码 0，墙钟 177.23 秒，记录最大 RSS 324,012 KiB。

- 4,175 个建模样本，4,020 个有预测评估样本，123 个主题，30 折。
- CatBoost：R² 0.845321，MAE 68.084334，RMSE 153.694052。
- 单特征 Ridge：R² 0.196297，MAE 180.444744，RMSE 350.339664。
- 单特征 Ridge 与 notebook 保存输出一致；部分其他 Ridge 结果与保存输出不同，因此不声称完整论文表格复现。
- 30/30 折存在训练/测试共享年份， Cell 34 还存在全量均值插补。这两个问题使结果不能直接视为严格时间外推能力。

### 已跑通：CRISPR 描述性滞后相关

结果文件：`scitreands_crispr_lags.json`，日志 `018-scitreands-crispr-lag-reproduction.json`，退出码 0。

19 个年度观测（2003—2021）：同年相关 0.938010，`shift(-1)` 相关 0.887012；差分同年相关 0.643545。证据类别为 **2：历史回顾性时间关系**。没有训练预测器，没有前瞻验证，没有可推广提前量。

### 未跑通/未运行

- 文本嵌入和完整论文表格：未运行。需要额外 NLP 依赖且上游无锁文件，当前先完成无 DL 核心与泄漏审计。
- 作者原始 `GET_DL_EMBEDS=True` 路径：未执行，避免下载模型和超出小样本复现范围。

### 真实失败记录

| 日志 | 结果 | 根因与处理 |
|---|---|---|
| `011-install-scitreands-catboost` | 退出码 2 | 持久化挂载无法复制大型 `_catboost.so`；改用兼容本地临时盘 |
| `012-install-catboost-local-temp` | 退出码 0 | CatBoost 1.2.10 可用，依赖不进入 MedRadar |
| `013-scitreands-author-no-dl-core` | 退出码 1 | NumPy 2 移除 `np.NaN`；做明确兼容替换 |
| `015-scitreands-numpy2-compatible-core` | 退出码 1 | 模型已跑完，NumPy 整数导致 JSON 序列化失败；修复类型转换 |
| `016-scitreands-core-results-serialization-fix` | 退出码 1 | 模型再次跑完，相对输出路径受 notebook 工作目录切换影响；改为预先解析绝对路径 |
| `017-scitreands-core-final` | 退出码 0 | 数值与前两次一致，机器可读结果成功落盘 |

## PubTrends

### 已跑通：主题词算法 smoke test

命令：

```bash
python3 experiments/phoenix_001/pubtrends_smoke.py \
  /mnt/agents/output/phoenix_external/pubtrends \
  --output experiments/phoenix_001/pubtrends_smoke_results.json
```

官方提交：`8520f2a19493baa776d929cb3d31a0ae9498132a`。日志 `014-pubtrends-topic-smoke.json`，退出码 0，墙钟 0.59 秒，最大 RSS 36,220 KiB。

执行的是上游 `topics.py`，不是重写算法。为避免 `text.py` 在 import 时加载 SpaCy/NLTK，只 stub 本测试不会调用的 `get_frequent_tokens`。官方案例的三个主题词、权重和 ignore-component 分支均通过。

### 未运行

完整 PubTrends 服务、Analyzer、文献聚类、引用网络和主题演化没有复现。当前没有历史论文—引用快照，也不应为一个算法 smoke test 部署 PostgreSQL、Redis 和 Web 服务。本项目因此是 **STUDY_ONLY**，不是“完整系统已验证”。

## MedRadar 数据迁移状态

本轮两个项目的复现均使用其公开外部数据或人工小 fixture，没有使用 MedRadar SQLite 伪装迁移结果。当前两份 MedRadar 数据库缺失，后续迁移实验只能使用已冻结且粒度足够的研究产物；不能满足时间边界和实体去重要求的假设会标为阻断。
