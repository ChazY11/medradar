# V1-001 / BASELINE — 真实代码、分支、测试与数据状态

> 本文件只记录**本轮实际核查到的**事实。任何没有在本机复现的内容都标为 NOT VERIFIED。

## 1. 运行环境

| 项 | 值 |
| --- | --- |
| 主机 | Windows，本地开发机（非生产） |
| Python | 3.12.10（系统解释器；包未安装，从工作树根目录导入） |
| pytest | 9.1.1 |
| FastAPI | 0.115.6（可选 product extra 已安装） |
| 仓库 | `D:/DEPPSKK/medradar`（主工作树） |
| 本轮工作树 | `D:/DEPPSKK/worktrees/v1-001`，分支 `v1/001` |
| 数据目录 | `D:/DEPPSKK/v1-001-data`（从基线账本复制，见第 4 节） |

## 2. 分支与祖先关系（实测，不是传闻）

本轮开始时逐条执行 `git merge-base --is-ancestor`，结论如下：

| 引用 | SHA | 与 main 的关系 |
| --- | --- | --- |
| `origin/main` | `86311b1` | 基线 |
| `feat/radar-001-live-intelligence-graph`（PR #54） | `14eaf61` | main 的**后代**（67 个提交） |
| `origin/pr/46` … `origin/pr/54` | `4fd094e` … `14eaf61` | 全部是 `14eaf61` 的祖先（严格线性堆叠） |
| `refoundation/004` | `380aa37` | main 的后代（76 个提交），**且 `14eaf61` 是它的祖先** |
| `first-principles/001` | `6f4d079` | main 的后代（77 个提交），`380aa37` 是它的父提交 |

关键实测：`git merge-base 380aa37 14eaf61` 的输出就是 `14eaf61`。也就是说：

```
main 86311b1
  └─ 67 commits（PRODUCT-001..004 / DATA-001..003 / RADAR-001 / LAUNCH-001 / HOTFIX-001 / QUALITY-001）
       └─ 14eaf61  = PR #54 的顶端
            └─ 9 commits（REFOUNDATION-004：relevance、admission v3、质量评估、日期精度、回归测试、文档）
                 └─ 380aa37  = refoundation/004
                      └─ 1 commit（FIRST PRINCIPLES-001：水位线修复 + 9 份文档 + 证据）
                           └─ 6f4d079  = first-principles/001  = 本轮基线
```

这意味着任务书中的线索「#46–#54 与 refoundation/004 / first-principles/001 可能冲突、需要合并或选择基线」
**在本环境不成立**：两者不是分叉，而是同一条线性链。**不存在重叠改动需要人工解决**，
也没有任何本地未推送成果被遗漏——`first-principles/001` 已经是包含全部成果的栈顶。

因此本轮基线选择：**`first-principles/001` @ `6f4d079`**，新建分支 `v1/001`，不复制、不重建、不重排任何已有实现。

## 3. 历史成果保护

- 主工作树 `D:/DEPPSKK/medradar` 未被切换分支、未被 reset、未被清理；
- `refoundation/004`（`worktrees/rf004` 指向 `6f4d079` 所在提交链）与本轮新工作树**并存**，没有删除；
- 研究模块（`research/`、`experiments/`、`medradar/intelligence`、`medradar/studies`、历史 `report.py` / `replay.py`）一行未删；
- 本轮只新增文件与最小的局部修改，见 `COMPLEXITY_DELTA.md`；
- 全部改动为**本地提交**；未 push、未合并远程、未 force push、未部署。

## 4. 数据基线（真实账本，可复现）

| 项 | 值 |
| --- | --- |
| 基线账本副本 | `D:/DEPPSKK/data004-baseline/work/radar.db`（101 MB，schema `radar-ledger-v3`） |
| 本轮工作副本 | `D:/DEPPSKK/v1-001-data/radar.db`（从基线复制，从未回写基线） |
| 观测数（基线） | 8,593：openFDA 清关 6,936 / Crossref 1,137 / PubMed 484 / Dräger 31 / Philips 5 / **召回 0** |
| 判定（基线，`radar-assessment-2026.11.19`） | FEED 7,360 / EXCLUDED 1,210 / REVIEW 23 |
| importance（基线） | **MEDIUM 8,590 / HIGH 3 / LOW 0** |
| discovery_phase（基线） | INITIAL_DISCOVERY 8,588 / INCREMENTAL 5 |
| 水位线（基线） | crossref **2027-02（未来，缺陷）**、openfda_device 2026-11-02、pubmed 2026-11-17、philips 2026-11-16T07:30Z、draeger 2026-11-09T12:41Z |
| GE HealthCare | `enabled=0`、`BLOCKED_BY_ACCESS_POLICY`（robots.txt 403），未被伪装抓取 |

## 5. 回归基线（本轮改动前）

在 `v1/001` 的基线提交（`6f4d079`，工作树干净）上运行：

```
python -m pytest tests -q
```

- **1,632 个测试，0 失败，0 错误，4–5 个跳过**（跳过项取决于可选依赖，主要是需要 fastapi 的用例）；
- 实际耗时约 50 分钟（Windows 本地，单进程）；
- 完整输出留档：`D:/DEPPSKK/worktrees/v1-001/_baseline_pytest.txt`；
- `python tools/governance/check_licence.py`：**PASS**（20 项检查，0 失败，1 warning）；
- `python -m pytest tests/governance -q`：71 passed。

## 6. QA-002 的 120 条标注：**当前环境可独立复算**

任务书提到「此前工作环境未找到 120 条逐条证据」。本环境核实结果相反：原始逐条证据**已提交在仓库中**。

| 文件 | 内容 |
| --- | --- |
| `docs/first_principles/001/_evidence/labelled120.json` | **120 条**逐条记录（实测 `len == 120`），字段：`observation_id`、`title`、`source`、`label`（人工判读）、`engine_rel` / `engine_decision` / `engine_tier` / `engine_imp`（引擎判定）、`priority`、`uncertain`、`note` |
| `docs/first_principles/001/_evidence/sample120.txt` | 同样 120 条的文本副本 |
| `docs/first_principles/001/_evidence/pm_recall.json` / `pm_missed.json` | PubMed 覆盖实验的命中与缺失明细 |
| `docs/first_principles/001/_evidence/recalls.tsv` | 734 条召回行的离线副本 |
| `docs/first_principles/001/_scripts/label120.py` | 生成该样本的脚本 |

可直接从该文件复算的分布（本机实测）：

- 人工标签 `label`：DIRECT 45 / CLINICAL 38 / MEDICAL_UNRELATED 20 / NON_MEDICAL 11 / TRANSFER 6；
- 引擎 `engine_rel`：CLINICAL 55 / DIRECT 41 / MEDICAL_UNRELATED 17 / NON_MEDICAL 4 / TRANSFER 3；
- 引擎 `engine_imp`：**MEDIUM 120 / 120**——这是「importance 是常量」在 120 条样本上的独立复现；
- 因此报告记载的 0.659 / 0.730 属于**可复算的 A 级证据**（方法与分母见 `docs/first_principles/001/INDEPENDENT_EVALUATION.md`）。

结论：不是「样本不存在」，而是「样本此前没被找到」。本环境可以复算，因此本轮**不再重复做一次 120 条标注**；
本轮的质量评估改用 15 天内的真实运行结果 + 召回参考集（见 `QUALITY_REPORT.md`）。

## 7. 安全边界与未验证项

| 项 | 状态 |
| --- | --- |
| 生产数据库 | **未触碰**（NOT VERIFIED：本轮无法访问生产环境） |
| 远程分支 / PR | **未 push、未合并**（本轮只做本地提交） |
| 部署 | **未部署**（NOT VERIFIED） |
| 浏览器端到端 | 未运行（无浏览器自动化；既有前端产物未重建，见 `FINAL_REPORT.md` 的说明） |
| 真实用户 | 无（四周试验状态 NOT STARTED） |
| FDA 网页（HTML） | **本机不可取**（站点返回 JavaScript 倒计时拦截，HTTP 400）；改用官方 openFDA API 复核，见 `RECALL_COVERAGE.md` |

## 8. 基线运行的可重复命令

```bash
cd D:/DEPPSKK/worktrees/v1-001
python -m pytest tests -q                       # 全量
python tools/governance/check_licence.py        # 许可证/清单门
python -m medradar radar init                   # 注册表自检
MEDRADAR_RADAR_DIR=D:/DEPPSKK/v1-001-data python -m medradar radar status
```
