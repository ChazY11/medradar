# REFOUNDATION-003 · Phase 3 验收报告
## Mainline Integration, Repository Consolidation & GitHub Renewal

**基线：** `origin/main` = `b2a14c0`（全程未变）
**集成候选：** `integration/ref003` → **Draft PR #38**
**性质：** 本地完成合并 dry-run、独立验收与新首页；**未合并、未改设置、未 force-push**。真正合并需负责人批准。

---

## 0. 一页结论

| 交付 | 状态 |
|---|---|
| 受控合并链 #32 → #35 → #36 → #34 → 新 README | ✅ 本地完成，**零冲突**（README 有意取舍） |
| 集成测试矩阵 | ✅ **1,145 passed / 3 skipped / 224 subtests**（1,148 collected） |
| 6 道治理门在集成树 | ✅ 全 PASS；冻结篡改 → FAIL，恢复 → PASS |
| Evidence Core 生产验收 | ✅ **37/37 PASS**；迁移 +114.93%（+1.46 GiB）；`available_at` 查询 1,260 ms → 0.49 ms |
| PR 清理清单 | ✅ 27 个 open PR 全部定级（5 类），未关闭/未合并任何 PR |
| 文档导航 | ✅ `docs/INDEX.md`（4 层分类） |
| 新首页 EN/ZH | ✅ 已并入集成候选；截图降级并标注；架构图区分实现/路线图 |
| 发布候选 | ✅ 建议合并后 bump 到 **v0.6.0-rc1**；当前 `pyproject` 仍为 **0.5.0** |
| **合并到 `main`** | ⛔ **等待负责人明确批准** |

**最重要的验收指标：** 主分支候选实际获得 6 项经过验证的能力（治理 6 门、Evidence Core、E1b 研究记录、文档导航、新首页、测试矩阵）；重复工作收敛为 **1 条集成线 + 1 份验收包**；首页不再把未合并功能写成已发布。

---

## 1. 集成后的统一测试矩阵

| 层 | 结果 | 说明 |
|---|---|---|
| 全量 pytest | **1,145 passed, 3 skipped, 224 subtests**（1,148 collected） | `python -m pytest -q -o addopts=""`，45–48 s |
| 基线保持 | 1,071 个原有测试全部通过 | 未修改任何既有测试断言（#34 的 `test_release` 修复是放宽四位数解析，仍保留漂移检测） |
| 治理测试 | 46 passed | 19 licence / 12 freeze / 8 rule-audit / 4 bump / 3 inventory-exemption |
| Evidence Core 测试 | 28 passed | revision、幂等、first_seen、触发器、迁移、回滚 |
| 6 道治理门 | 全 PASS | state 240 / views 3 / frozen 36 / licence 14 / links 3 / rule-audit 18 |
| CI（GitHub） | PR #32 **11/11 绿**（含 6 个治理 job）；#34/#35/#36/#37 各 5/5 | 集成 PR #38 的 CI 由 GitHub 运行 |

**已知 flaky：** `tests/governance/test_bump_state.py::test_generated_at_is_the_ref_commit_time` 在一次全量运行中失败、单独运行与随后重跑均通过；判定为时钟边界 flake，**不建议在修复前把它设为必需检查**。

---

## 2. 分步骤合并及回滚记录

**实际合并顺序与提交：**

| 步 | 来源 | 合并提交 | 冲突 |
|---|---|---|---|
| 1 | #32 `1331883` | `d746b86` | 无 |
| 2 | #35 `f088e37` | `faab1a5` | 无 |
| 3 | #36 `6ffe7e7` | `413254f` | 无 |
| 4 | #34 `6a95a5b` | `3be8a4e` | 无 |
| 5 | 新 README `032b960` | `96950ba` + `81aaa84` | **README.md / zh-CN**：按要求取新设计，#34 的 README 文本被取代，其测试修复与记录保留 |
| — | 集成记录 + triage | `a93afe3` / `8182f07` | — |

**过程中发现并修复的真实跨 PR 阻断（修在对应 PR #32 上，未建巨型 PR）：**
1. `check_licence` 正清单拒绝我们自己的证据 JSON（#32 × #35）→ `4ea5ada`：`docs/refoundation/*/_evidence/*` **仅豁免清单**，内容分类与受限格式拒绝不变；记录 `RC-0002`/`GOV-0002`。
2. 同一豁免在 PR diff 扫描中缺失（#32 × #36）→ `1331883`。

**另一个真实教训：** 第一次合并错误地使用了**本地陈旧** 的 `governance/refoundation-002`（`8d7fd62`）而不是远端 `beacd11`；已重置并全部改用 `origin/*` 引用。这证明 dry-run 的价值。

**回滚：**
- 撤销单步：`git revert -m 1 <merge-sha>`（保留历史）。
- 回到某一步：在集成分支上 `git reset --hard <上一合并提交>`。
- `main` 未动、无 force-push、生产 DB 只读（sha256 `445807ca…` 不变）。

---

## 3. 数据库迁移验收结果（独立验收，37/37 PASS）

**证据：** [`EVIDENCE_CORE_ACCEPTANCE.md`](EVIDENCE_CORE_ACCEPTANCE.md) · `_evidence/core_acceptance/acceptance.json`

| 组 | 项 | 结果 |
|---|---|---|
| 原始完整性 + 副本 | SHA-256 / mtime / 副本哈希 | **4/4 PASS**（原始未变） |
| 迁移与 `schema_version` | 版本 [1,2]、checksum、幂等、篡改 checksum 拒绝、未知版本拒绝 | **8/8 PASS** |
| 账本一致性（全库） | 375,378 events ↔ 375,378 revisions；0 gap/orphan/head mismatch；全部 `legacy_baseline`/`baseline_only` | **8/8 PASS** |
| 历史保留 | v2 update 保留 v1 旧值、`prev_content_hash` 链、相同重写不新增 | **PASS** |
| 直接 SQL 检测 | UPDATE/REPLACE → `head_mismatch=1`；DELETE → `orphan=1`；账本 UPDATE/DELETE/REPLACE 被拒 | **6/6 PASS** |
| 事务/迁移回滚 | 部分批次回滚头行+修订；失败迁移不记录 v2 | **3/3 PASS** |
| 读取方兼容 + pytest | 4 个聚合 + 200 行 19 列逐值一致；1,099 passed | **4/4 PASS** |
| 恢复演练 | 恢复文件 = 原始 SHA；revision/schema_version 不存在 | **2/2 PASS** |

**成本与性能（诚实数字）：**
- 存储：1,368,469,504 B → **2,941,247,488 B**，**+114.93%（+1.46 GiB）**；修订载荷 ≈2.99 KB/条（19 列全快照，无压缩/裁剪）。规划时按 **~2.15× 空间**。
- 迁移：**73.0 s**（作者 68.7 s，+6.3%）；`reconcile()` **18.2 s**（+8.3%）。
- `available_at >= '2020-01-01'`：**1,260.5 ms → 0.49 ms（≈2,500×）**，计划由全表扫描变为覆盖索引。
- 限制（已记录）：checksum 保护迁移身份而非数据库本身；无签名；`DROP TRIGGER` 后伪造修订对 `reconcile()` 不可见（仅 `verify_guards()` 报警）；`ensure_schema()` 需要 `sqlite3.Row` 连接（生产 `DB` 路径不受影响）。

---

## 4. 治理门实际运行证明

- **GitHub Actions 真实运行：** PR #32 的 6 个治理 job（state/views/frozen/licence/links/rule-audit）+ ci = **11/11 绿**。
- **本地集成树：** 6 门全 PASS；`gen_views --check` PASS（README 状态区来自 `PROJECT_STATE.yaml`）。
- **故意破坏：** 冻结文件追加 1 字节 → `FAIL check_frozen (2 failures)`；`git checkout --` 恢复 → PASS。
- **规则变更审计：** 修改 `DATA_LICENSES.yaml`/`check_licence.py` 必须带 `RC-0002` + `GOV-0002`；无记录 → FAIL，未知决策 → FAIL。
- **状态源：** `bump_state --ref HEAD --dry-run` 显示 main.head/date/subject/`tracked_files` 1,135→1,225 与视图更新；**没有静默自动更新**，每次合并后必须显式 bump，否则门会持续失败（这是设计，防止状态漂移）。
- **对其他 PR：** 治理 workflow 只在 #32 分支上存在；合并前其他 PR 不会运行它。合并后第一个普通 PR 必须确认 6 个 job 真实触发。

---

## 5. PR 状态清理清单（27/27 定级，未关闭任何 PR）

| 状态 | 数量 | PR |
|---|---:|---|
| **READY_TO_INTEGRATE** | 6 | #31, #32, #33, #34, #35, #36 |
| **NEEDS_REWORK** | 6 | #12, #13, #14, #21, #28, #30 |
| **RESEARCH_ARCHIVE** | 9 | #15, #16, #18, #19, #20, #22, #24, #25, #26 |
| **BLOCKED_LEGAL** | 2 | **#27, #29**（含受限 UN Comtrade 载荷；禁止按原样合并） |
| **SUPERSEDED** | 4 | #1, #17, #23, **#37**（其 4/5 文件与 #32/#34/#35/#36 报告逐字节相同） |

**结论：** 活跃队列从 27 收敛为 **6 个可集成 + 2 个需法务处理**；9 个科研 PR 建议保留分支、标记归档；4 个已被取代。**未关闭、未评论、未改目标分支**（需负责人执行）。

---

## 6. 重组后的文档导航

**新增 `docs/INDEX.md`（4 层）：**
1. 用户/开发者入口：README、quickstart、METHODS。
2. 当前科研协议与成果：`research/RESULTS`、studies、protocols。
3. 数据与架构契约：schema、Evidence Core、licensing。
4. 历史审计/实验归档：`docs/refoundation/phase0–phase3`、旧审计报告。

状态列区分 current / archived / draft；**链接而非复制**；未删除/移动任何科研证据。`research/STATE.json` 标记为 **advisory, not canonical**（其部分断言已被 E3 的事件时间限制推翻）。

---

## 7. 新 README 与视觉方案

- `README.md`：397 → **257 行**（−35%）；`README.zh-CN.md`：325 → **240 行**（−26%）。
- 科学使命前置；明确 "research infrastructure, not a validated predictive product"。
- 能力表区分 **working / partial / mechanism only**；架构图（Mermaid）只画 `main` 已实现模块，路线图单列。
- 保留有来源的数字：375,378 events（2026-10-31）、60 天事件研究（n=61, +5.65%, t=2.45, CI [+1.35,+10.32]）、M2RD 负结果（AP 0.7935 vs 0.7913，CI [−0.032,+0.037]）、E1b 逐源结论。
- 删除 16 项过时/夸大声明（678 测试、v0.2.2/v0.3.0、"2,384 cases"、"281 signals"、PIT 导出、AdCom 50 赛道、"每周情报"等）。
- 截图：`docs/preview.png` 保留但下移，标注 **数据集 2026-10-31 / 包版本 v0.5.0**，明确"非实时、非预测"。
- 视觉方案：`docs/refoundation/phase3/README_VISUAL_PLAN.md`（保留/重标注/后续替换清单 + 风格规则）。
- 状态区由 `PROJECT_STATE.yaml` 生成，**不手改**；测试数实录 **1,148 collected / 1,145 passed / 3 skipped**。

---

## 8. 发布候选建议

**建议：通过 PR #38 以 merge commit 合并；合并后 bump 到 `v0.6.0-rc1`（当前 `pyproject` 仍 `0.5.0`）。**

| 项 | 建议 |
|---|---|
| 版本号 | 合并后 **0.6.0**（当前 0.5.0；新增 Evidence Core 与治理门，语义化 minor） |
| 合并方式 | **merge commit**，保留 #32/#35/#36/#34 的 provenance；不 squash |
| 合并后立即 | `python tools/governance/bump_state.py --ref origin/main --with-views` 小提交；确认 CI 6 门全绿 |
| 合并顺序 | 先合并 #32/#35/#36/#34 各自（可选），或直接合并 #38（含全部）；**二者不要混用** |
| 不发布 | #27/#29（受限数据）；#31/#33 下一轮；#37 标记 SUPERSEDED |
| 分支保护 | **合并后**再启用；先用一个故意破坏 PR 验证 6 门会变红 |
| 回滚 | `git revert -m 1 <merge-sha>`；集成分支可随时重置 |

---

## 9. 需要负责人明确批准的操作（本轮未执行）

| # | 操作 | 风险 |
|---|---|---|
| A1 | 合并 **PR #38**（或按顺序合并 #32→#35→#36→#34）到 `main` | 写 main；有完整回滚与测试证据 |
| A2 | 合并后运行 `bump_state` 并推送小提交 | 必要的状态更新 |
| A3 | 处理 #27 / #29（剥离受限数据 / 法务决定） | **BLOCKED_LEGAL**，不得直接合并 |
| A4 | 关闭/归档 9 个科研 PR、关闭 #37、#1、#17、#23 | 仅 PR 元数据，不删分支/证据 |
| A5 | 启用分支保护 | 影响所有贡献者；需在 CI 稳定后 |
| A6 | 先 bump 版本，再生成 v0.6.0-rc1 tag / Release | 公开发布 |
| A7 | 重写 #29 历史以清除已公开的 Comtrade 载荷 | **仅 owner 可决定**，本轮禁止 |

---

## 10. 剩余风险

| # | 风险 | 级别 |
|---|---|---|
| R1 | Evidence Core 迁移使 DB 体积 **+114.93%**；磁盘/备份成本需预算 | P1 |
| R2 | 头行仍可被裸 SQL 改；`reconcile()` 可检测但不可阻止；`DROP TRIGGER` 后不可见 | P1（已在文档声明） |
| R3 | `test_bump_state` 时钟 flake，设为必需检查前需修复 | P1 |
| R4 | 治理 workflow 只在 #32 分支；合并前其他 PR 无治理门 | P2 |
| R5 | #27/#29 仍含受限数据；#29 的公开暴露需 owner 决策 | **P0（法务）** |
| R6 | 新 README 的部分数字来自既有 `metrics.json`（非本次重跑），已在文档标注来源 | P2 |
| R7 | 27 个 PR 的收敛需要 owner 执行关闭/归档，否则队列仍会漂移 | P2 |
| R8 | `#33`（ADR 证据对比）尚未并入；Evidence Core 文档引用它，合并后应尽快补 | P2 |

---

## 11. 边界声明

- **未合并任何 PR**；`main` 仍 `b2a14c0`。
- 未 force-push；#32 为 fast-forward；集成分支为普通合并提交。
- 未删除科研成果/冻结资产；未重写历史。
- 生产数据库只读，字节与哈希未变。
- 未修改 GitHub 设置；未启用分支保护。
- 未推送受限数据；集成分支 diff 扫描 0 受限值 / 0 邮箱 / 0 绝对路径 / 0 私钥 / 0 token。
- 未把未合并功能写成已发布能力；README 逐条标注 working/partial/mechanism-only。
