# README 真实性修订（Phase 2 · D）

**状态：** 已完成，待评审（单独文档 PR）。**未**改动 UI、未重做视觉、未删除任何文件。
**分支：** `docs/readme-truth-phase2`（基于 `origin/main` `b2a14c0`）
**范围：** `README.md`、`README.zh-CN.md`、本报告。

---

## 1. 修改清单（10 处，全部有实测依据）

| # | 位置 | 修改前 | 修改后 | 依据 |
|---|---|---|---|---|
| D1 | EN 开头 | 营销式定位（"知道美国大厂在造什么"） | 科学研究使命："公开证据能否提前揭示医疗技术实质变化？"+ 明确"研究基础设施，非已验证预测产品" | Phase 1 任务定义；避免把研究项目描述为预测产品 |
| D2 | zh 开头 | 同上 | 同上（中文） | 同上 |
| D3 | EN 版本说明 | 只提 v0.2.2 / v0.3.0 | 增加 **当前包版本 0.5.0**（以 `pyproject.toml` 为准） | `pyproject.toml` |
| D4 | zh 版本说明 | 同上 | 同上 | 同上 |
| D5 | EN 新增 `## Project status (2026‑11‑13)` | 无 | main head / 23 open PR（22 Draft）/ 1,074 测试 / 快照数据 / 修订账本未上线 / 治理未启用 | `gh api` 实测；`pytest` 实测；Phase 1 E3 |
| D6 | zh 新增 `## 项目状态（2026‑11‑13）` | 无 | 同上 | 同上 |
| D7 | EN `Timing scope` 行 | "Only real datetime/date availability enters return studies" | **"Event-time only"**：100% 行 `published_at=available_at=event_date`；独立公开时间 = 0；PIT 需重新采集 | E3 §4（375,378/375,378） |
| D8 | zh 时间口径段 | "只有日期级公开时间戳的事件不进入交易研究" | 改为：快照全为日期级且 `available_at=event_date`，回测是"事件日=公开日"同日假设 | E3 §4 |
| D9 | EN/zh `Tests` 行 | **678** offline tests | **1,074**（1,071 passed / 3 skipped，2026‑11‑12） | `pytest -q -o addopts=""` |
| D10 | EN PIT / 研究基础设施行 + "可复现"声明 | "deterministic point-in-time export"；"every number reproducible from `medradar run`" | 机制 vs 数据能力分开；复现限定为"需联网重新采集，干净克隆复现过程而非精确数字" | E3；`.gitignore` 不含 `data/` |

同时新增（EN + zh）：

- **已完成负面结果**区块，明确 Market-to-R&D / S-028/S-029 / prospective 预测的结论，链接到 Draft PR #31 的资产登记（不链接尚不存在的路径）。
- **研究复现入口**代码块（pytest / demo / run）。
- **架构状态图**（Mermaid）：实线 = 已在 `main`；虚线 = 草案或规划；ATLAS 标注 "target contract only"、`not connected yet`。
- **看板图**从首屏主视觉位置下移，并加版本 + 数据日期说明。

---

## 2. 图片处理（满足"过时截图"要求）

| 要求 | 处理 |
|---|---|
| 标注版本与数据日期 | 图注：**数据集 2026‑10‑31**、**包版本 v0.5.0** |
| 不能代表现状则从主视觉撤下 | 已从首屏移除，放在"看板快照"小节，并声明"仅示意 demo 视图，不是实时服务，也不是预测" |
| 不得让读者以为是实时系统 | 明确 "not a live service" / "不是实时服务" |
| 文件本身 | `docs/preview.png` 保留（不删除资产）；未新增未实现模块的截图 |

---

## 3. 架构图（只画已实现或明确标注规划）

Mermaid 图分三组：
- `On main — implemented`：三个采集器、`events` SQLite、analytics、TKG、forecast registry、报告/看板。
- `Draft branches — not released`：ATLAS #28、HORIZON #27、CONVERGENCE #30、DATA-EXPANSION #29、MedRadar 2.0 #12。
- `Phase 2 branch — in progress`：`event_revision` ledger、`schema_version` + migrations。

连接线：实线仅用于 `main` 内实际存在的路径；虚线表示"未接入"。ATLAS 到 ledger 的箭头标 "target contract only"，`events → ATLAS` 标 "not connected yet"（依据 Phase 1 E2 的 L3 结论：双向零导入）。

---

## 4. 验证

| 检查 | 结果 |
|---|---|
| 相对链接解析 | **0 missing**（README.md + README.zh-CN.md；排除 http/#） |
| 敏感内容扫描（diff） | **clean**：无受限值、无邮箱、无绝对路径 |
| `678` 残留 | 0 |
| 版本号 | `0.5.0` 与 `pyproject.toml` 一致 |
| 图片引用 | `docs/preview.png` 存在，已加图注 |
| 未改 UI / 未删文件 | 是 |
| `tests/test_release.py` 测试数断言 | 修正：原正则 `(\d{3})` 与上限 900 无法解析/接受四位测试数（`1,074` 被读成 `74`），导致 PR CI 失败；改为 `([\d,]{3,})` + 上限 5000，仍保留"不得过期"的本意 |

---

## 5. 合并顺序与冲突提示

- 本 PR **只改** `README.md`、`README.zh-CN.md` 与本报告，基于 `main`。
- 已知冲突源：**PR #17**（完整 README 重写）与 **PR #32**（治理状态块会重新生成 README）。
- 建议顺序：先决定 #17 是否承载首页 → 若 #17 合并，本修订应作为其补丁；若 #17 不合并，本 PR 独立合并；#32 的 `gen_views` 在本 PR 之后重新生成，避免互相覆盖。
- 本 PR **不**触碰 `PROJECT_STATE.yaml` 生成的区块，降低与 A 工作流的冲突面。

---

## 6. 明确不做

- 不启动全面 UI/视觉重设计。
- 不把 Draft 功能写成已发布产品。
- 不删除历史资产（图片、文档）。
- 不修改研究结论或负结果。
- 不新增任何未测量数字。
