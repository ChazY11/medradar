# 证据与脚本索引（FIRST PRINCIPLES-001）

本目录保存本轮研究产生的原始证据与可复现脚本。

> 文档正文中引用的 `_fp001/xxx` 就是本目录 `_evidence/` 下的同名文件；
> 正文引用的脚本（如 `sample120.py`）在 `_scripts/` 下。路径差异仅为归档位置，内容一致。

## `_evidence/`

| 文件 | 内容 | 对应文档 |
| --- | --- | --- |
| `pubmed_probe.json` | 6 条独立 PubMed 检索式在 2026-10-01→11-18 的原始命中与 ID 列表 | REFERENCE_EVENTS 1.1 |
| `pm_recall.json` | 每条检索式的命中/库中已有/缺失 统计（114/400 覆盖） | REFERENCE_EVENTS 1.1 |
| `pm_missed.json` | 286 条系统未请求的记录（PMID、标题、日期、检索式） | REFERENCE_EVENTS 2.2 |
| `recalls.tsv` | 734 条监护产品码召回（产品码、日期、企业、事件号、产品、原因） | REFERENCE_EVENTS 1.2 / INTELLIGENCE_BRIEF |
| `sample120.txt` | 本轮独立 120 条样本的可读清单（来源、日期、标题、摘要前 200 字） | INDEPENDENT_EVALUATION 1 |
| `labelled120.json` | 120 条的标注结果 + 引擎判定 + observation_id（可与账本逐条核对） | INDEPENDENT_EVALUATION |

## `_scripts/`

| 脚本 | 作用 | 依赖 |
| --- | --- | --- |
| `pm_probe.py` | 对 6 条检索式做 esearch | 公网（NCBI E-utilities） |
| `pm_recall.py` | 取元数据并按 PMID 与账本比对 | 公网 + 只读账本 |
| `recalls.py` | 逐产品码拉取 openFDA 召回 | 公网（openFDA） |
| `sample120.py` | 种子 20261118 分层抽样 120 条 | 只读账本 perf-v2.db |
| `label120.py` | 应用标注并计算混淆矩阵 | 上一步输出 |
| `demo_clamp.py` | 在真实水位线上演示修复前后查询窗口 | 仓库代码 + 只读账本 |
| `synthetic_increment.py` | 隔离临时库验证增量/版本/失败/去重机制 | 仅本地，无网络 |
| `urls.py` | 核对样本每条都有可回溯来源 | 只读账本 |

## 未归档的东西（以及原因）

| 项 | 原因 |
| --- | --- |
| 生产账本原始库（约 56 MB） | 已在仓库外；本轮只做只读查询，不改写 |
| QA-002 的 `evidence/*.json` | 本机不存在，无法归档（见 INDEPENDENT_EVALUATION 第 0 节） |
| 浏览器截图 | 本轮没有做浏览器测试；QA-002 的截图未随附 |
| 全量测试日志 | 只保留结论；如需可重跑 `pytest -q` |

## 重新生成顺序

```
python _scripts/pm_probe.py        # 需要公网
python _scripts/pm_recall.py       # 需要公网 + 账本副本
python _scripts/recalls.py         # 需要公网
python _scripts/sample120.py       # 需要账本副本
python _scripts/label120.py
```
