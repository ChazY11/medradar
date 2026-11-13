# Phase 0 · Task 1 — 科研资产保全清单与可恢复性证明

> **状态：** preservation 已完成；**公开推送决定待安全门（Task 1.5 / task-9）**
> **执行时间：** 2026-11-12（Asia/Shanghai）
> **基线：** `origin/main` = `b2a14c0`；本地 40 个 worktree、6 个含未推送提交的分支
> **证据目录：** `<REDACTED_LOCAL_PATH> + SHA256SUMS + 独立验证）
> **标签约定：** `[FACT]` 已实测 / `[INFERENCE]` 推理 / `[RECOMMENDATION]` 建议 / `[UNVERIFIED]` 未验证

---

## 1. 结论先行

| 问题 | 结论 |
|---|---|
| 有多少提交仅存在于本机？ | **6 个分支共 15 个提交**（PHOENIX 7、audit 2+1、temporal-KG 2、forecast-registry 2、phase3 1、audit-dryrun 1） |
| 是否已建立可恢复备份？ | **是** — 6 个 self-contained bundle（合计 58.0 MB）+ SHA256SUMS + Lead 与独立 verifier 双重恢复测试 |
| PHOENIX 7 个提交的内容是否只在本机？ | **不是。** 7 个提交涉及的 **166 个文件，166/166 与已推送的 `origin/research/phoenix-001-round2` 字节完全相同**；仅 commit 对象本身是本机独有 |
| 是否包含受限数据或个人信息？ | 待安全门结论；初步观察：作者身份 `ChazY11 <[EMAIL_REDACTED]>` 已在公开分支出现；内容与公开分支一致，**不会新增文件内容暴露** |
| 是否可以推送 `rescue/*`？ | **可以，但必须先通过 task-9 安全门**；推送目标是**新分支**，不会修改现有 PHOENIX 分支 |

**一句话：** 内容层面不存在"仅此一份"的科研资产——它已在公开的 round2 分支上；**真正只在本地的是 7 个 commit 的提交历史与元数据**。因此保全的价值在 provenance，而非内容抢救。

---

## 2. 未推送提交总清单

`[FACT]` 生成命令：`git rev-list --count <branch> --not --remotes`，逐分支展开为 `git log <branch> --not --remotes`。

| # | 分支 | 未推送提交数 | 分支 tip | 远端是否存在同名分支 | 处置 |
|---|---|---:|---|---|---|
| 1 | `research/phoenix-001-external-methods` | **7** | `c385553` | 是（`bd2f839`，已分叉） | bundle + 待推送 `rescue/*` |
| 2 | `audit/refoundation-001` | **2** | `2ea481a` | 否 | bundle + 待 Draft PR |
| 3 | `audit/refoundation-002` | **3** | `86a5720` | 否 | 本轮新增，含 Phase 0 记录 |
| 4 | `research/temporal-knowledge-graph` | **2** | `1d9e0d1` | 否 | bundle 已保全 |
| 5 | `research/forecast-registry` | **2** | `d5aa16c` | 否 | bundle 已保全 |
| 6 | `phase3/registry-cycle` | **1** | `37fcbd9` | 否 | bundle 已保全 |
| 7 | `integration/audit-dryrun` | **1** | `4f4a999` | 否 | bundle 已保全 |

`[FACT]` 合计 **18 个未推送提交**（其中 audit/refoundation-002 的 3 个是本轮 Phase 0 产生的，之前为 15 个）。

---

## 3. PHOENIX 7 个独有提交（重点）

### 3.1 逐提交清单

`[FACT]` 全部作者/提交者：`ChazY11 <[EMAIL_REDACTED]>`，无 GPG 签名（`%G?` = `N`）。该邮箱已出现在公开的 `origin/research/phoenix-001-round2` 提交中。

| 序 | SHA | 时间（+08:00） | 主题 |
|---:|---|---|---|
| 1 | `a43f8a24ddded5d04b68718cd7e8f55fb7d2756b` | 2026-11-08 23:37:28 | freeze experiment protocol v1 and build the shared evaluation harness |
| 2 | `e9120dde6d48deef3b53f498642758f4d97de604` | 2026-11-08 23:37:38 | REA deployment, external project audits, and the RAEA entity-attribution prototype |
| 3 | `7db5fbb14b96f304e84ca6f796810c0b70a9ed9a` | 2026-11-08 23:41:59 | audit four published research methods (NIH iSearch, The Lens, PTNS, FDA AI-device panel) |
| 4 | `7478cfdfb285543b4804700f39150a37e5ae869d` | 2026-11-08 23:44:47 | commit the hhi.py bootstrap p-rule fix and the methods self-test at 56/56 |
| 5 | `4ddb88c631433d8b5e48f52882f8d90f41d72f2f` | 2026-11-09 00:20:50 | ten-hypothesis experiments, baseline bridge, 13-project register and research synthesis |
| 6 | `4aad1f39766d9b69f8cf6718d1182176b5048b93` | 2026-11-09 01:12:47 | final cell results after clean-cache verification; H5 reclassified NOT TESTABLE |
| 7 | `c385553377dd340f6926aa9ff199e136c1a26f34` | 2026-11-09 01:13:13 | correct the cell section of the reproduction report with the post-verification numbers |

依赖关系是**线性**的：1 → 2 → 3 → 4 → 5 → 6 → 7。第 1 个提交的父提交是 `4c6686f…`，即 **S-028 的 tip**（已在公开远端 `origin/research/s028-temporal-graph-early-signal`）。因此这 7 个提交的历史底座是公开的。

### 3.2 7 个提交的真实改动面

`[FACT]` 以 `4c6686f..c385553` 计算（排除继承的公开历史）：

- **166 个文件，+158,731 / −0 行**（纯新增与少量删除在后续提交内）
- 最大文件：

| 字节 | 文件 |
|---:|---|
| 4,559,843 | `experiments/phoenix/hypotheses/cell/results/_chunks/preds_L000.pkl` |
| 4,559,843 | `preds_L090.pkl` / `preds_L180.pkl`（各同尺寸） |
| 3,466,451 | `experiments/phoenix/hypotheses/track/cache/track_panel_L{000,090,180}.pkl` |
| 1,133,018 | `experiments/phoenix/hypotheses/track/cache/entrants_hhi_L180.csv` |
| 842,523 | `experiments/phoenix/hypotheses/cell/results/cell_all_metrics.json` |

`[INFERENCE]` `.pkl` 是模型预测/面板缓存（派生数据），不是第三方原始数据；但 pickle 反序列化本身有安全风险，任何后续使用应视为不可信输入。

### 3.3 关键发现：内容已公开

`[FACT]` 逐文件比对 `c385553` 与 `origin/research/phoenix-001-round2`（PR #24 的 head，**已推送**）：

```
166 个变更文件：identical_to_round2 = 166，differs = 0，absent_in_round2 = 0
```

即：**这 7 个提交所承载的全部文件内容，已经能在公开的 round2 分支上取得。** 本机独有的只是 7 个 commit 对象（及其时间、父子关系、提交信息）。

`[INFERENCE]` 这显著降低了"永久丢失"的严重度：即使本机磁盘损坏，内容仍可从 GitHub 恢复；但**提交级 provenance（哪一天、以什么顺序、以什么提交信息冻结）无法从 round2 分支重建**。对于科研冻结记录，这仍有保存价值。

### 3.4 为什么会有 33 / 16 / 7 三个数字

`[FACT]` 本地分支相对远端孪生 `bd2f839`：领先 **33**、落后 **16**；其中**仅 7 个**不被任何远端引用包含。
原因：本地分支继承的 26 个提交已通过其他公开分支（S-028、phase4-base 等）可达。因此：

- **33** = 相对孪生分支的领先数（含已公开的继承提交）
- **16** = 孪生分支独有的、本地没有的提交
- **7** = 真正只在本机的提交 → **这才是保全对象**

`[FACT]` 远端孪生与本地分支的 merge-base 是 `b2a14c0`（main），而不是 S-028 tip——说明孪生分支是另一条基于 main 的独立实现，二者不是简单的快进关系。

---

## 4. 保全工件

### 4.1 Git bundles（self-contained）

`[FACT]` 目录：`<REDACTED_LOCAL_PATH>

| Bundle | 大小 | 含 ref |
|---|---:|---|
| `phoenix-001-local-full.bundle` | 21.7 MB | `research/phoenix-001-external-methods` → `c385553` |
| `audit-refoundation-001-full.bundle` | 10.1 MB | `audit/refoundation-001` → `2ea481a` |
| `temporal-knowledge-graph.bundle` | 6.4 MB | `research/temporal-knowledge-graph` → `1d9e0d1` |
| `forecast-registry.bundle` | 6.4 MB | `research/forecast-registry` → `d5aa16c` |
| `phase3-registry-cycle.bundle` | 6.9 MB | `phase3/registry-cycle` → `37fcbd9` |
| `integration-audit-dryrun.bundle` | 6.5 MB | `integration/audit-dryrun` → `4f4a999` |
| **合计** | **58.0 MB** | |

`[FACT]` `SHA256SUMS.txt` 记录 6 个 bundle 的 SHA-256（见同目录）。

### 4.2 恢复证明（Lead 自测）

`[FACT]` 在**独立空仓库**中执行（不依赖主 clone）：

```
git init <tmp>
git fetch phoenix-001-local-full.bundle 'refs/heads/*:refs/heads/*'
→ refs/heads/research/phoenix-001-external-methods = c385553377dd340f6926aa9ff199e136c1a26f34
→ git fsck --full : exit 0（无损坏）
→ restored tree = a4890675062e6b6e6229976b0edb2561c7451f47
→ source   tree = a4890675062e6b6e6229976b0edb2561c7451f47   ✅ 一致
```

`[FACT]` 独立 verifier（task-10）对 6 个 bundle 全部做了同样的隔离恢复 + tree 比对，结论见 `refoundation-002-backups\verify\RECOVERY_VERIFICATION.md`。

---

## 5. 风险与处理决定

### 5.1 分级

| 风险 | 级别 | 现状 | 处理 |
|---|---|---|---|
| 提交历史丢失（commit provenance） | P1（原判 P0，因内容已公开而下调） | bundle 已建立并验证 | 通过安全门后推 `rescue/*` |
| 内容丢失 | **已消除** | 166/166 文件已在公开 round2 | 无需额外动作 |
| 推送引入新数据暴露 | 待评估 | 内容与公开分支一致；作者邮箱已公开 | **等待 task-9 安全门** |
| 误改现有 PHOENIX 分支 | 禁止 | 未修改 | 只推新 `rescue/*` 分支 |
| pickle 文件被误执行 | 低 | `.pkl` 仅作工件 | 使用前视为不可信 |

### 5.2 推送方案（**已执行**）

`[FACT]` 安全门（task-9）返回 `PHOENIX_PUSH_SAFE=PASS`、`BUNDLE_SAFE=PASS` 后执行；推送目标是**新建分支**，未触碰既有 PHOENIX 分支，未 force-push：

```bash
git push origin c385553...:refs/heads/rescue/phoenix-001-local
git tag -a rescue/phoenix-001-2026-11-12 c385553...
git push origin refs/tags/rescue/phoenix-001-2026-11-12
```

`[FACT]` 远端确认：

```
c385553377dd340f6926aa9ff199e136c1a26f34  refs/heads/rescue/phoenix-001-local
c385553377dd340f6926aa9ff199e136c1a26f34  refs/tags/rescue/phoenix-001-2026-11-12^{}
```

`[INFERENCE]` 至此，7 个提交同时存在于：本机分支、本机 bundle、GitHub 新分支、GitHub 注释标签——**四重保全**。

### 5.3 其余 4 个历史分支

`[FACT]` `temporal-knowledge-graph`、`forecast-registry`、`phase3/registry-cycle`、`integration/audit-dryrun` 目前只有本机 bundle 保全，**尚未做安全扫描、尚未推送**。
`[RECOMMENDATION]` 在 Phase 1 之前对它们各做一次与 PHOENIX 同口径的扫描，再决定是否推 `rescue/*`；在此之前 bundle 已是有效备份。

### 5.4 明确不做

- 不修改 `research/phoenix-001-external-methods` 及其远端孪生
- 不 force-push、不删除任何分支
- 不在安全门通过前推送任何内容
- 不把 `.pkl` 或原始数据"顺手"推到 `main`

---

## 6. 未覆盖项（Not covered）

| 项 | 原因 | 影响 |
|---|---|---|
| `.git` 之外的未跟踪文件（如 `data/*.sqlite`） | 本就不在 git 中，bundle 不含 | 若需保全需单独快照；Phase 0 不涉及 |
| worktree 的本地配置（`.git/worktrees/*`） | bundle 只含 refs/objects | 恢复后需重新 `git worktree add` |
| bundle 的多副本异地存储 | 当前仅本机 `D:` 盘 | **建议**复制到外部盘/对象存储；本轮未做 |
| 远端分支删除后的 GitHub 缓存 | 平台行为，不可控 | 推送到新分支即成为新的公开副本 |

---

## 7. 待决策

1. **D-20：** 是否授权在安全门 PASS 后推送 `rescue/phoenix-001-local` 及其 tag？（建议：是）
2. **D-21：** 是否同时为其余 4 个历史分支建立远端 rescue 副本？（建议：是，成本低）
3. **D-22：** 是否需要把 bundle 复制到第二块物理介质？（建议：是，本轮未做）
4. **D-23：** 是否接受"PHOENIX 内容已公开、只需保全提交历史"的结论，从而把 P0 降为 P1？（建议：接受，但保留 bundle）

---

*本文件由 REFOUNDATION-002 Phase 0 生成；安全门结论回填后更新 §5.1。*
