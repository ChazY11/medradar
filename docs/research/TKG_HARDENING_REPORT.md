# TKG_HARDENING_REPORT — TKG-HARDEN-005 对抗性加固报告

- **TASK_ID**: TKG-HARDEN-005｜**AGENT**: Kimi Code（全新独立复审上下文，非原实现会话）
- **日期**: 2026-11-01｜**分支**: `research/kimi-tkg-hardening`｜**基线**: f1b8132
- **范围**: 仅 `medradar/tkg`、`tests/test_tkg.py`、相关文档。未读原始 Kimi 会话日志；所有结论均经独立复现实验确认。全部合成数据、零网络。

## 1. 方法与判定标准

对每个 Priority Check 先写**对抗性复现脚本/测试**（独立连接、注入时钟、手工构造陷阱历史），
在 f1b8132 原始代码上确认失败，再修复，并验证新测试在旧代码上红、新代码上绿。
未复现的怀疑不修、不扩面。无真实数据基准；bench 为明确标注的合成冒烟。

## 2. 确认的缺陷与修复（均有先红后绿证据）

### D1 悬空边端点（Priority 1）— 确认，已修复
原始 `snapshot()` 独立选择节点与边：端点节点被撤销、尚未生效、或（raw 会话场景下）
从未写入节点版本时，边仍被输出 → 导出图含悬空引用。复现：`known_at` 后期端点撤销后
快照仍含 `A→B` 边而节点集合无 `B`（复现脚本输出 `DANGLING: True`）。
**修复**（`query.py::snapshot`）：确立**端点可见性合同**——仅当两端点都出现在同一组
`(known_at, valid_at)` 选中的节点集合中才输出该边；排除时绝不回填未来元数据、绝不复活节点。
测试：`test_snapshot_excludes_edge_when_dst_retracted` / `_src_retracted` /
`_endpoint_not_yet_valid` / `_endpoint_missing_from_store`（raw 会话模拟）+
`test_snapshot_keeps_edge_when_endpoints_visible_and_hash_regresses`（正向控制 + 固定哈希向量）。
旧代码上 5 个端点测试全红。

### D2 INSERT OR REPLACE 绕过 append-only（Priority 3）— 确认，已修复
原始 `nodes`/`edges` 只有 UPDATE/DELETE 触发器；独立连接执行
`INSERT OR REPLACE INTO nodes (...同主键, 篡改内容...)` **成功覆写历史**
（复现：`attrs` 被改写为 `{"v":999}`、`assertion_id` 变为 `sha256:FORGED`；同内容 REPLACE
同样成功）。upsert `DO UPDATE` 因触发 UPDATE 触发器被拒。
**修复**（`store.py` schema）：`nodes_no_resubmit` / `edges_no_resubmit` /
`idempotency_no_resubmit` 三个 `BEFORE INSERT` 守卫——主键（或幂等键）已存在的插入一律
`RAISE(ABORT)`，与冲突解决模式无关。`idempotency` 守卫同时防止幂等键被重新绑定后让
伪造内容冒充"duplicate"。测试：`test_insert_or_replace_cannot_rewrite_history`
（4 种绕过方式：OR REPLACE 篡改/同内容、upsert、纯重复主键，全部拒绝且行内容不变）、
`test_idempotency_key_cannot_be_rebound_via_replace`。
**边界声明**：守卫防的是游离 SQL 会话/缺陷代码，**不防数据库属主**（可删触发器、重建库）；
对属主的防护靠文件权限与外部审计。文档已如实写明。

### D3 混合精度时间戳字典序 ≠ 时间序（Priority 5）— 确认，已修复
原始 `normalize_moment` 渲染不定宽微秒（`...T00:00:00Z` vs `...T00:00:00.500000Z`）。
`'Z'(0x5A) > '.'(0x2E)`，同秒比较出错。三个实测后果：
(i) 时钟守卫接受同秒内回退（守卫在 `.500000`，时钟回到整秒 `.000000` 实例被放行）；
(ii) 切割线漏检：`recorded_at=00:00:00.123456` 的写入在 `known_at=00:00:00`（同一更早瞬间）
**错误可见**（知识泄漏到切割线之前）；
(iii) 等瞬间不同渲染可能误报 `ClockRegressionError`。
**修复**：规范渲染固定 6 位微秒 `YYYY-MM-DDTHH:MM:SS.ffffffZ`；schema 版本升 `tkg-schema-2`
（旧库不自动迁移，文档明示）。测试：`test_timestamps_fixed_width_microseconds_lexical_order`、
`test_cutoff_at_equal_instant_excludes_subsecond_later_write`、
`test_clock_guard_rejects_same_second_regression`（含等瞬间不同渲染不误报）。
另修复**确定性缺陷**：duplicate 重试原按 `assertion_id` 取行（同内容多键时 `fetchone`
无 ORDER BY，可能返回他键行），改为按调用方 `idempotency_key` 精确取行
（`test_duplicate_retry_returns_exact_original_row_per_key`）。

### D4 文档声明与实现不符（Priority 2/4）— 文档已更正，无 gratuitous 扩面
- **断言粒度**：ADR D2/TKG.md 曾称"每条关系/属性是独立版本谱系"，实现实为
  "每节点身份一条谱系（属性整体版本化）+ 每有向边身份一条谱系"。已按实现更正文档，
  未实现属性级断言（"无属性级 diff"在 TKG.md 早已声明，现与 ADR 一致）。
- **`source_version`**（验收 C2 证据五元组之一）：实现无逐断言该列；源版本标识由 manifest 级
  `schema_version`/`adapter_version`/`code_version` 承担，逐条选中证据保留
  `assertion_id`/`source_locator`/`evidence_sha256`/`evidence_kind`。验收附录新增 O7–O9
  记录本次加固合同（O7 端点可见性、O8 重提交守卫、O9 微秒时间戳）。

## 3. 复测未发现问题的 Priority 项

- **批次原子性/FK/幂等/源只读/导出历史稳定**：既有测试（`test_batch_is_atomic_rollback`、
  `test_orphan_edge_fails_and_rolls_back`、幂等三测、源库字节级不变、
  `test_snapshot_stability_after_later_writes`）在新代码下全绿；复审未发现新缺口。
- ** reopened store 单调锚点 / 等时序 seq / 重试幂等**：既有测试通过。

## 4. 验证命令与证据

```bash
python -m pytest tests/test_tkg.py -q          # 42 passed（31 旧 + 11 新对抗性）
python -m medradar selftest                    # Ran 482 tests ... OK (skipped=3)
python -m medradar.tkg demo --out-dir demo_out # 离线端到端；early/final 哈希不同
python -m medradar.tkg bench --n 2000          # deterministic_repeat_export=true（合成）
pip wheel . --no-deps --no-build-isolation -w <隔离目录>
# 隔离 --target 安装、非仓库 cwd 运行 demo：与源码树导出哈希一致
#   034824ecbe7f239e468eb988935dedafcb6fdf3554652b26e49d25834f71af57
```

先红后绿证据：新 `HardeningTests` 11 个测试中 10 个在 f1b8132 原始代码上失败
（唯一例外为 duplicate 确定性的强度测试，原实现偶发正确）；修复后全部通过。
bench 哈希因 schema-2/格式修正**刻意**变化（4d4b7049… → 1091db6e…），
已重新生成并在文件内注明；仍为合成冒烟，**不是真实数据预测精度**。

## 5. 明确不做/不承诺

- 不对数据库属主提供防篡改承诺（D2 边界）；未做超出上述范围的广义安全审计。
- 不实现公开时钟模式、不注入生产时钟、`recorded_at` 仍由存储层写时赋值。
- 单写者假设不变；`tkg-schema-1` 库不迁移，需重建。
- 无端到端真实数据基准；任何性能数字均为合成且仅供复现冒烟。

## 6. 残余风险

- 多进程并发写仍依赖外部串行化（单写者假设）。
- 导出哈希随 schema/adapter/code 版本变化（设计如此），跨版本比较需先核对 manifest。
- 属性级断言、公开时钟重建仍为显式 DEFERRED 项。
