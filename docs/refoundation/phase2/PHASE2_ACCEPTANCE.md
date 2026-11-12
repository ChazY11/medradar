# REFOUNDATION-002 · Phase 2 验收报告
## Engineering Implementation: Governance, Evidence Integrity & Historical Recovery

**时间：** 2026-11-13（Asia/Shanghai）
**基线：** `origin/main` = `b2a14c0`（未改变）
**性质：** 本轮交付的是**可运行、可测试、可复现的代码**，不是又一份架构报告。

---

## 0. 结论

| 交付 | 状态 | 证据 |
|---|---|---|
| 治理系统修复（许可/冻结/规则变更/状态） | ✅ 代码 + 43 个新测试；全部绕过被捕获；0 误杀 | PR #32 @ `beacd11` |
| Evidence Core v1（修订账本） | ✅ 代码 + 28 个新测试；1,099 通过；DB 未变 | PR #35 @ `f088e37` |
| E1b 来源恢复实验 | ✅ 真实小样本；EDGAR PASS / CT.gov PARTIAL / openFDA FAIL | PR #36 @ `6ffe7e7` |
| README 真实性修订 | ✅ 10 处修正；截图降级并标注 | PR #34 @ `0c44de0` |
| 合并 / 分支保护 | ❌ 未执行（按要求） | `main` 仍 `b2a14c0` |

**一句话：三个核心问题都有对应代码，且都用真实测试证明；但仍有两件事不能声称——数据库级完全防篡改，和真正的 point-in-time 证据。**

---

## 1. 已实现的代码

### A. 治理硬化（PR #32，6 个提交）

| 文件 | 作用 |
|---|---|
| `tools/governance/check_licence.py` | 从"路径模式"升级为**正清单 + 内容/魔数分类**；扫描最终 git 树 **和** PR diff；覆盖改名、扩展名伪装、跨目录、未跟踪文件 |
| `docs/governance/DATA_INVENTORY.yaml` | 167 个数据文件的正清单（分类 + 内容哈希） |
| `tools/governance/check_frozen.py` | 冻结 v2：目录 per-file SHA-256 清单；`rebalances:` 审计日志需 `decision_id`；覆盖 `research/forecasts/`、`papers/CLAIMS.json` |
| `docs/governance/FROZEN.yaml`、`DECISION_LOG.yaml`、`RULE_CHANGES.yaml` | 冻结清单、决策登记、规则变更记录 |
| `tools/governance/check_rule_audit.py` | 治理面（workflow / tools / policy）变更必须有决策记录；防止 Agent 静默降低 CI |
| `tools/governance/bump_state.py` | 主分支前进后的状态刷新（dry-run + apply） |
| `tests/governance/` | 43 个测试（19 licence / 12 freeze / 8 rule-audit / 4 bump） |

### B. Evidence Core v1（PR #35）

| 文件 | 作用 |
|---|---|
| `medradar/evidence_core/migrations.py` | `schema_version` + 幂等事务迁移（name/checksum/applied_at） |
| `medradar/evidence_core/ledger.py` | `event_revision` 表、内容哈希、append/read/reconcile、guard 安装/校验 |
| `medradar/db.py` | `upsert_events` 改为"头行 + 每次内容变化一条 revision"；`first_seen_at = MIN`；`event_history()` |
| `tests/test_event_revision.py`、`tests/test_evidence_core.py` | 28 个测试 |

### C. E1b 来源恢复（PR #36）

| 文件 | 作用 |
|---|---|
| `research/e1b/collect_e1b.py` | 小样本采集（stdlib only，UA 联系地址走环境变量） |
| `research/e1b/derive_findings.py` | 生成 retrospective / prospective 两份独立证据 |
| `docs/refoundation/phase2/E1B_SOURCE_RECOVERY.md` | 逐源结论 |
| `_evidence/e1b/*.json,jsonl` | 采集、发现、两份时间证据 |

### D. README 修订（PR #34）

`README.md`、`README.zh-CN.md`：使命、main vs draft、事件时间局限、测试数、版本、PIT 限定、截图标注、架构状态图、负结果、复现入口。

---

## 2. 实际运行的测试

| 套件 | 结果 | 位置 |
|---|---|---|
| 治理新测试 | **43 passed** | `tests/governance/` |
| 治理分支全量 | **1,117 collected / 1,114 passed / 3 skipped / 224 subtests** | PR #32 |
| Evidence Core 全量 | **1,099 passed / 3 skipped / 224 subtests**（基线 1,071 + 28 新） | PR #35 |
| `python -m medradar selftest`（CI 路径） | `Ran 1,117, OK (skipped=3)` | PR #32 |
| 治理 6 道门 | state 240 / views 3 / frozen 36 / licence 14 / links 3 / rule-audit 12 — **全 PASS** | PR #32 |
| 生产 DB 完整性 | sha256 `445807ca…`、1,368,469,504 B、mtime **不变** | PR #35 |
| 全库迁移 + 恢复演练 | 375,378 events → **375,378 baseline revisions**（68.7 s）；`reconcile()` 16.8 s，0 mismatch；恢复后字节一致 | PR #35 |
| CI（GitHub Actions） | **全绿**：#32 11/11（含 6 个治理 job，run `43288232206`）· #34 5/5 · #35 5/5 · #36 5/5 · #37 5/5 | 仓库 |

**未运行/不可运行：** 服务端分支保护未启用（按约束）；合并动作未执行。\n\n`[FACT]` #34 首次 CI 失败暴露了仓库自身测试的一个缺陷：`tests/test_release.py` 用 `(\\d{3})` 与上限 900 校验 README 测试数，无法解析四位数（`1,074` 被读成 `74`）。已修正为 `([\\d,]{3,})` + 上限 5000，并保留“不得过期”的本意；修复后 5/5 通过。

---

## 3. 已修复的已知漏洞

| 漏洞 | 修复前 | 修复后 | 证据 |
|---|---|---|---|
| 许可：新来源/新路径 | MISS | **CAUGHT** | `inventory.coverage`, `diff.changed_data_file` |
| 许可：已知 AMBER 源未声明路径 | MISS | **CAUGHT** | 同上 |
| 许可：`docs/` 下二进制 SQLite | MISS | **CAUGHT** | `content.restricted_kind` |
| 许可：`docs/` 下 CSV | MISS | **CAUGHT** | `diff.changed_data_file` |
| 许可：扩展名伪装（.csv 实为 SQLite） | MISS | **CAUGHT** | `inventory.content_match` |
| 许可：改名已声明文件 | MISS | **CAUGHT** | `inventory.stale_entry` |
| 许可：未跟踪数据文件 | MISS | **CAUGHT** | `untracked.data_file` |
| 冻结：name-only 文件修改 | MISS | **CAUGHT** | per-file digest |
| 冻结：未批准 re-baseline | MISS | **CAUGHT** | `rebalance.unapproved` |
| 冻结：新 forecast set / CLAIMS.json | MISS | **CAUGHT** | 覆盖扩展 |
| 规则变更：静默降低 CI | 无门 | **FAIL 无记录**；有决策 + 记录才 PASS | `rules.uncovered_change` |
| 状态：main 前进后持续失败 | 会漂移 | `bump_state.py` 模拟验证通过 | 4 文件/20-19 行修复 |
| 事件写入覆盖旧记录 | `INSERT OR REPLACE` 无历史 | **每次内容变化追加 revision；旧值可查** | PR #35 测试 + 全库演练 |

**误杀基线：167 个数据文件，0 flagged，0 unclassified。** 日志中未出现任何 fixture 内容标记（0 次）。

---

## 4. 可恢复的历史数据

| 来源 | 能恢复什么 | 不能恢复什么 | 证据 |
|---|---|---|---|
| **SEC EDGAR** | `acceptanceDateTime`（真实 UTC 时刻）、原始文档不可变、修订以 8-K/A 新 accession 出现 | —（这是当前最好的真 PIT 来源） | 5/5 重取字节一致；`Last-Modified` = acceptance +21–75 s |
| **ClinicalTrials.gov v2** | `studyFirstPostDate`（仅 `type='ACTUAL'`）；更新日期 | **历史内容版本不可恢复**（`/history` 404、`/versions` 404、`?history=true` 400） | 28 请求，2×404、1×400 |
| **openFDA 510(k)/PMA** | `decision_date`（事件日）、原始记录可按 K/P 号重取 | **公开日期不可从 API 恢复；`first_public = UNKNOWN`** | 两 endpoint 无 posting 字段；重取字节一致 |
| 旧 SQLite 快照 | 作为 `legacy_baseline` 快照迁移（每事件一条，标记 `baseline_only`） | **不能**伪装成有完整修订历史的新证据 | PR #35 明确 `history_completeness` |

**prospective observation**（从 2026-11-12 起）：三个来源均可行；已保存 6+3+16 条 first-seen 记录（含响应 sha256 与取回时间），与 retrospective 文件**物理分离**。

---

## 5. 仍然不能成立的科研主张

| 主张 | 状态 | 原因 |
|---|---|---|
| "系统能提前 N 天发现变化"（lead-time） | **不可成立** | 快照独立公开时间 = 0；只有 EDGAR 可回溯真时刻，CT.gov 仅日期、openFDA 无公开时间 |
| "point-in-time 回测" | **不可成立（当前数据）** | 100% 行 `available_at = event_date`；只能做同日假设 |
| "预测能力已获验证" | **不可成立** | 无到期 prospective 预测；Phase 1 负面结果 |
| "企业级归因" | **受限** | company 35.2%，可审计依据 10.9% |
| "数据库不可篡改" | **不可声称** | 修订账本防的是 UPDATE/DELETE；DROP TRIGGER/TABLE、整文件替换**不防**；头行仍可被裸 SQL 改（可检测不可阻止） |
| "许可自动扫描 = 法律合规保证" | **不可声称** | 文档明确写为人工复核的辅助 |

---

## 6. 可安全进入合并评审的 PR

| PR | 内容 | 建议 | 前置 |
|---|---|---|---|
| **#35** Evidence Core v1 | 代码 + 迁移 + 28 测试 | **优先评审**（低耦合、不改 readers） | CI **5/5 绿**；确认生产库迁移在副本执行 |
| **#32** 治理硬化（更新） | 6 道门 + 43 测试 | **可评审** | CI **11/11 绿**（6 个治理 job + ci）；`fetch-depth: 0` 已设 |
| **#36** E1b 恢复 | 研究文档 + 脚本 | **可评审**（研究结论，不影响运行时） | CI **5/5 绿** |
| **#34** README 真实性 | 文档 + 1 个测试修复 | **最后合并** | CI **5/5 绿**；先决定 #17；合并后重跑 `gen_views` |
| #31 / #33 | Phase 0 审计/对比 | 保持 Draft | 与 Phase 2 无冲突 |

**没有 PR 被自动合并；没有启用分支保护；`main` 未变。**

---

## 7. 下一步整合起点

1. **合并顺序：** #35 → #32 → #36 → #34。先代码后治理再文档；README 最后，避免生成区块冲突。
2. **合并 #32 后立刻做：** 把 `governance.yml` 落到 `main`（否则其他 PR 不跑治理门）；然后在下一个普通 PR 上确认 6 个 job 真实运行。
3. **启用保护前：** 先跑一个"故意破坏"PR（改许可/冻结文件）确认 CI 红；再按 `BRANCH_PROTECTION_PLAN.md` 启用（仍需 owner 明确授权）。
4. **Evidence Core 上线前：** 在数据库副本上执行迁移 + `reconcile()`，记录耗时（全库 68.7 s / 16.8 s）；确认备份可回滚。
5. **E1b 全量回收：** 先做 EDGAR（真 PIT 可行）→ CT.gov（ACTUAL 守卫）→ openFDA 仅 prospective。不要为扩大行数牺牲真实性。
6. **README：** 应用 #34 后，重新生成 README 状态块并跑 `check_links`。

---

## 8. 边界声明

- 未合并任何 PR；#32/#34/#35/#36 均 Draft。
- 未 force-push；#32 为 fast-forward 更新。
- 未重写科研历史、未删除冻结资产、未改 `main`。
- 未修改 GitHub 仓库设置；未启用分支保护。
- 生产数据库只读：**哈希与字节数不变**。
- 未将受限数据推送到公开仓库；三个新分支的 diff 扫描：受限值 0、邮箱 0、绝对路径 0、私钥 0、token 0。
- 未为满足门槛补造时间/身份字段。
