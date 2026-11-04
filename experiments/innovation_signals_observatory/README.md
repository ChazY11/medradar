# Innovation Signals Observatory（Phase 4 研究工作区）

本目录是 MedRadar Phase 4 的**研究执行区**：它回答「医疗器械企业公开的技术招聘活动，
能否为其新兴研发方向提供可信、可追溯的早期证据」，并把这条链路的每一环做成可复核的代码与数据。

**生产代码不在这里**：可复用的采集/观察契约在 `medradar/recruitment/`，
采集入口是 `scripts/collect_recruitment.py`。本目录只放：来源探测、实验、证据、结果、报告。

## 目录

| 路径 | 内容 |
|---|---|
| `docs/EXISTING_CAPABILITY_AUDIT.md` | **WP1**：对 PR #19/#20 及既有系统的审计；哪些结论必须保留、哪些能力不可用 |
| `docs/PROTOCOL.md` | **预注册**：研究问题的操作化、三层评价指标、信号分级、关联规则、允许/禁止的结论尺度 |
| `docs/SOURCE_DISCOVERY.md` | 五家企业数据源调查与可行性矩阵（含 robots / 自动化访问条款） |
| `docs/LLM_EXPERIMENT.md` | 真实岗位文本上的规则臂 vs 本地 4B 模型臂实验（协议、结果、限制） |
| `docs/EVIDENCE_REPORT.zh-CN.md` | **中文可读的证据样例报告**：候选方向 + 独立证据 + 反证 + 未知 |
| `docs/NINETY_DAY_PLAN.zh-CN.md` | 90 天前瞻观察方案与启动条件（本轮不部署） |
| `../../PHASE4_RESEARCH_REPORT.zh-CN.md` | 本轮中文科研总结（直接回答六个科研问题，含「不允许被读成什么」） |
| `sources/` | 来源探测与分页行为测量脚本（可重跑，带请求数上限） |
| `llm/` | 岗位文本抽取实验（schema、prompt、运行、评价） |
| `evidence/` | 候选信号与独立证据的关联流水线 |
| `results/<date>/` | 当次运行的产物：岗位快照、采集清单、模型输出、关联结果 |

## 复现

```bash
# 1) 采集一次有界快照（Medtronic，Workday 公开端点；robots 先取后断言）
python scripts/collect_recruitment.py --company medtronic --limit 1000 \
    --min-interval 0.8 --out experiments/innovation_signals_observatory/results/2026-11-04

# 2) 离线契约测试（不联网、不加载模型）
python -m pytest tests/test_recruitment_records.py -q

# 3) 来源探测（五家，23 次请求上限）
python experiments/innovation_signals_observatory/sources/probe_careers.py \
    --out experiments/innovation_signals_observatory/results/2026-11-04
```

## 产物状态分级（与 `PROTOCOL.md` §5 一致）

`VERIFIED`（可重复、可核验）/ `EXPLORATORY`（真实但不足以支撑比较）/ `BLOCKED`（无合法稳定路线）/ `NOT_RUN`。

数据缺口与失败不是需要补齐的空白，而是结果的一部分：见 `results/` 下的 `collection_*.json`
（请求数、robots 原文、截断标记、失败明细）与 `docs/EVIDENCE_REPORT.zh-CN.md` 的「未找到独立证据」栏目。
