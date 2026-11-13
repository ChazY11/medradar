# Phase 0 · Task 2 — REFOUNDATION-001 审计成果的安全发布状态

> **结论：** 原始审计历史 **不发布**（安全门 FAIL）；已构建**单提交、已脱敏**的独立发布分支，待独立复检。
> **执行时间：** 2026-11-12
> **相关分支：** `audit/refoundation-001`（原始，本地）、`audit/refoundation-002`（含 Phase 0，本地）、`publish/refoundation-001`（脱敏发布候选，基于 main）

---

## 1. 审计提交与完整性

| 项 | 值 | 等级 |
|---|---|---|
| 原始分支 | `audit/refoundation-001` | FACT |
| 提交 | `5c9a397`（12 份交付物 + 证据包）、`2ea481a`（PHOENIX/5 层栈修正） | FACT |
| Phase 0 分支 | `audit/refoundation-002`，tip `86a5720`（增加 16 处链接修复） | FACT |
| 交付物 | 12 份必需文档 + `README.md` + `_FACTS.md`，全部存在且非空 | FACT |
| 文件总数 | 176（审计树）/ 3,328,808 B | FACT |
| 导航文档链接 | **47 条，0 断链**（独立 verifier 与 Lead 双重确认） | FACT |
| `_evidence/**` 链接 | 93/93 因"从 repo 根提取到子目录"而悬空——**不是缺陷**，已在 README 说明其为原样摘录 | FACT |

`[FACT]` 独立 verifier（task-10）结论：`AUDIT_INTEGRITY=PASS`、`LINK_INTEGRITY（导航）=PASS`。

---

## 2. 安全门结果（task-9）

| 门 | 结论 | 说明 |
|---|---|---|
| `PHOENIX_PUSH_SAFE` | **PASS** | 7 个提交无凭据；内容与公开 round2 一致 |
| `BUNDLE_SAFE` | **PASS** | 6 个 bundle 仅含预期 ref |
| `AUDIT_PUSH_SAFE` | **FAIL** | 2 个 critical 命中 + 4 个 PII high |

### 2.1 阻断项（原文脱敏）

| 严重度 | 文件 | 规则 | 处理 |
|---|---|---|---|
| **critical** | `docs/refoundation/_evidence/repo_facts.json:572` | `comtrade_derived_value` | 该值在一段 PR body 字符串里 |
| **critical** | `_evidence/research/extracts/integration__convergence-001__docs__convergence__EXECUTIVE_SUMMARY_ZH.md:76` | `comtrade_derived_value` | 公开分支文档的摘录 |
| high | `DATA_GOVERNANCE_AUDIT.md:295` | email ×3 | 项目别名 + 公开提交身份 + 机构邮箱 |
| high | `_evidence/comms/main_live.yml:41` | email | GitHub noreply |
| high | s029 摘录 ×2 | email | 论文作者邮箱（该分支已公开） |
| medium | 7 个证据文件 | absolute path | 本机 `<REDACTED_LOCAL_PATH> |

**[关键判断]** 这些内容大多**已在 GitHub 公开**（PR body、convergence 分支文档、s029 分支）。但 `AUDIT_PUSH_SAFE=FAIL` 的含义是：**不应由审计成果再复制一份受限值**。审计报告可以描述"存在受限值"，但不能把值本身写进新文件。

---

## 3. 为什么不能"加一个删除提交"了事

`[FACT]` 受限值存在于 `5c9a397` 与 `2ea481a` 的历史 blob 中。Git 是内容寻址的：即使新提交删除了该行，`git show 5c9a397:docs/refoundation/_evidence/repo_facts.json` 仍可取出原值；推分支即推送历史。

`[FACT]` 本轮**禁止重写历史**。因此唯一合规路径是：**在 `main` 之上新建一个只含脱敏快照的提交**，其历史里从未出现受限值。

---

## 4. 发布候选分支（已构建，待复检）

| 项 | 值 |
|---|---|
| Worktree | `<REDACTED_LOCAL_PATH> |
| Branch | `publish/refoundation-001`，基于 `origin/main`（`b2a14c0`） |
| 提交 | `c697546`，**单个提交** |
| 内容 | 仅 `docs/refoundation/`（178 文件） |
| 历史 | `main` + 1 个脱敏提交，**不含受限值** |

### 4.1 脱敏规则（39 个文件被修改）

| 替换 | 次数 |
|---|---:|
| 受限 Comtrade 派生值 → `[REDACTED: COMTRADE_DERIVED_VALUE]` | 2 |
| 任意邮箱 → `[EMAIL_REDACTED]` | 8 |
| 绝对本地路径 → `<REDACTED_LOCAL_PATH>` | 94 |

`[FACT]` 脱敏后自检：177 个文本文件、19 个 JSON 全部可解析（BOM 容忍）、受限值/邮箱/绝对路径命中 **0**、导航链接 **47/47 通过**。见 `SANITIZATION_LOG.json`。

### 4.2 尚未执行：推送 + Draft PR

`[RECOMMENDATION]` 仅在独立复检返回 `PUBLISH_BRANCH_SAFE=PASS` 后执行：

```bash
git push -u origin publish/refoundation-001
gh pr create --draft --base main --head publish/refoundation-001 \
  --title "docs(refoundation): REFOUNDATION-001 audit (sanitized)" \
  --body-file <prepared body>
```

`[FACT]` 当前状态：**未推送、未开 PR**。若复检 FAIL，则只保留本地分支 + bundle，不发布。

---

## 5. 备份

| 工件 | 位置 | 大小 | SHA-256 |
|---|---|---:|---|
| 审计分支 bundle | `refoundation-002-backups/audit-refoundation-001-full.bundle` | 10.1 MB | 见 `SHA256SUMS.txt` |
| 审计树 SHA-256 清单 | `refoundation-002-backups/lead-checks/audit_tree_manifest.json` | — | 176 个文件逐一哈希 |
| 发布分支 | 本地 `publish/refoundation-001` | — | 待推送后再 bundle |

`[FACT]` 已知缺口：审计 bundle 生成于链接修复提交 `86a5720` **之前**，因此恢复出来的是**修复前**状态（16 处断链）。Phase 0 结束时会重新生成包含修复与 Phase 0 记录的最终 bundle。

---

## 6. 结论与待决策

- **D-24：** 是否授权在复检 PASS 后推送 `publish/refoundation-001` 并开 Draft PR？（建议：是；Draft 不合并）
- **D-25：** 是否接受"审计报告可以描述受限值的存在，但不得复制值本身"作为发布准则？（建议：接受，写入治理文档）
- **D-26：** 原始 `audit/refoundation-001`/`002` 是否永久保留在本地与 bundle 中、永不推送？（建议：是）
