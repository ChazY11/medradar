# RELEASE-001 热修 / abb5e11

- 时间：2026-11-20 05:14 CST
- 触发：发布后 20 小时巡检发现调度器每个周期报 `3 error(s)`，且不自愈
- 结果：修复并部署；3 条卡死记录自动重新物化，错误归零

---

## 1. 现象

`[graph] materialized 0 observation(s): 0 new, 0 duplicate, **3 error(s)**`

- 从 2026-11-19 12:27 起，每 5 分钟一次，20 小时里 **106 个周期**
- 错误内容：

```
TKG: idempotency key 'node:obs:bfb7da07...' already used for assertion
     sha256:a3a9acf6... (new content hashes to sha256:1c20c4aa...)
```

- 永远是 3 条，不增不减：失败不标记为已物化，所以每次都被重新取出、再次失败

## 2. 根因

记录节点的幂等键是 `node:obs:<observation_id>` —— **只带身份，不带内容**。
TKG 存储拒绝"同一个键配不同内容"（这是正确的防篡改设计），于是**一条被源更新的记录永远无法更新它的图谱节点**，
观测一直留在 pending，图谱一直保留被取代的旧文本。

关键点：**边（edge）的键早就带了内容摘要**（`edge:...#{digest}`），存储的双时态模型也是
"按 `(recorded_at, seq)` 取最新修订"。唯独记录节点漏了这一步，导致存储本来支持的修订能力对它不可达。

## 3. 修复

把节点 attrs 的摘要并进幂等键，与边完全一致：

```python
attrs = {...}                                  # 与原来相同
digest = hashlib.sha256(canonical_json(attrs)).hexdigest()[:16]
"idempotency_key": f"node:{rec_id}#{digest}",
```

语义：
- 内容不变 → 同一个键 → **duplicate**（幂等，重跑安全）
- 内容变化 → 新键 → **写入新修订**，查询按 `recorded_at` 取最新
- 不覆盖、不删除任何历史修订（append-only 不变）

改动范围：`medradar/radar/graph.py` **一个函数**，其余 1,867 个文件与 `55b269e` 完全相同。

## 4. 回归测试

`tests/test_radar_graph.py::test_an_updated_record_rewrites_its_graph_node_as_a_new_revision`

断言：物化 → 源更新标题 → 再物化 → **无 error**、节点最新修订是新标题、旧修订仍在（共 2 条）。

**先证明它会失败**：把键改回 `node:{rec_id}` 再跑，测试报的正是生产上那条
`idempotency key ... already used for assertion`。这条路径此前**没有任何测试覆盖**，所以漏到了生产。

全量：**1,708 passed / 4 skipped / 0 failed**。

## 5. 部署

| 步骤 | 结果 |
| --- | --- |
| 冻结写入者 → 换符号链接 → 重启 | 停机约 10 s |
| `DEPLOYED_SHA` | `abb5e113413d045cc967b9010c43a531b30a9c53` |
| 指纹 | **1,868 / 1,868** identical，missing 0，mismatched 0 |
| 回退目录 | `app.previous` → `55b269e`（含其数据快照） |
| 门 | 未认证 API 仍 401 |

## 6. 验证（修复前后直接对比）

```
05:13:32  [graph] materialized 0 observation(s): 0 new, 0 duplicate, 3 error(s)   ← 修复前
05:15:01  [graph] materialized 3 observation(s): 6 new assertion(s), 0 duplicate, 0 error(s)  ← 修复后
05:15:01  [graph] materialized 0 observation(s): 0 new, 0 duplicate, 0 error(s)
```

3 条记录现在各有两个修订（原始 + 更新）：

| 观测 | 修订数 | 最新文本 |
| --- | --- | --- |
| `bfb7da07` | 2 | "Medical decision-making preferences and religious decis…"（**首字母与措辞已更新**） |
| `6c3cd160` | 2 | Physiological responses and microbiota dynamics… |
| `c51c3074` | 2 | Fatigue investigation on UHPFRC-enhanced OSBD… |

图谱统计：46,140 行节点 / **46,137 个不同 node id** → 恰好 3 个多修订，其余无变化、无重复膨胀。
`graph_pending` = **0**。

## 7. 剩余风险

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | 公司/产品/主题等实体节点仍是旧式键 | 若 taxonomy 中某个公司名或产品标签改变，会以**同样方式**永久卡死。当前无此配置变更，未修（改动面更大，需单独评审） |
| 2 | 修订会让图谱缓慢增长 | 每次记录内容变化 +1 节点行；当前 3 行。属正常，但长期需观察 `nodes` 行数 |
| 3 | 回退 | `app.previous` = 55b269e；该版本会再次报 3 error（不影响数据），回退后如要清干净需重新物化 |

## 8. 结论

- 缺陷根因修复，且有能在无修复时复现生产错误的回归测试
- 3 条卡死记录已随修复自动恢复，无需人工改数据
- 全量测试通过，部署指纹一致，回退路径完好
