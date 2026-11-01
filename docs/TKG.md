# TKG 使用说明 — 双时态知识图谱与确定性 PIT 导出

最小可用的**双时态（系统知识时钟）事实存储**：append-only 断言版本 + 独立
`known_at`/`valid_at` 切割查询 + 确定性 point-in-time 导出。仅 Python 标准库
+ SQLite，零新依赖，全程离线。架构决策见 [`research/TKG_ADR.md`](research/TKG_ADR.md)，
验收合同见 [`research/TKG_ACCEPTANCE.md`](research/TKG_ACCEPTANCE.md)。

## 快速开始（全部离线）

```bash
# 合成演示：构造含迟到/修正/撤销的历史，生成两个切割线的导出
python -m medradar.tkg demo --out-dir out/tkg_demo

# 从现有 events 库导入（源库只读，绝不修改）
python -m medradar.tkg import --db data/medradar.sqlite --tkg data/tkg.sqlite --limit 100

# 确定性导出（同一参数重复运行字节级一致）
python -m medradar.tkg export --tkg data/tkg.sqlite \
    --known-at 2026-06-01T00:00:00Z --valid-at 2026-06-01T00:00:00Z \
    --out-dir out/tkg_export          # 加 --jsonl 输出 nodes/edges/manifest 三个文件

# 合成数据上的可复现/性能冒烟（明确标注非真实数据结果）
python -m medradar.tkg bench --n 2000
```

## Python API

```python
from medradar.tkg import TKGStore, TKGQuery, export_snapshot, import_events

store = TKGStore("data/tkg.sqlite")          # 生产：时钟由存储层管理
store.add_node(
    "company", "ACME", {"stage": "ipo-filed"},
    valid_from="2024-05-01",                 # 可传历史日期；naive 时间会被拒绝
    idempotency_key="acme-stage:2024-05",    # 显式幂等键（必填）
    source_locator="https://example.test/8k",
    evidence_kind="source_observed", confidence=1.0,
)
snap = TKGQuery(store).snapshot(known_at="2024-12-31T00:00:00Z")   # valid_at 默认=known_at
doc = export_snapshot(store, known_at="2024-12-31T00:00:00Z")
print(doc["manifest"]["snapshot_sha256"])
```

## 语义要点（必读）

1. **只有一个时钟**：`recorded_at`（系统知识时间）由存储层在写入事务内赋
   UTC 时间戳，单调、不可由调用方设置。`public_time` 只是可选源元数据，绝不
   参与切割。本 MVP **没有**公开时钟重建模式。
2. **先选后滤**：查询先按 `known_at` 取每个断言谱系的最新版本，再按
   `valid_at` 过滤有效区间 `[from, to)`。因此后来的修正/撤销永远不会让旧版本
   "复活"。
3. **版本单元是断言**：一个实体可有多条关系/属性，各自独立版本化
   （`assertion_id` = 内容 SHA256）。
4. **重试安全**：相同 `idempotency_key` + 相同内容 → 返回原始版本、零新历史；
   相同键不同内容 → 显式冲突；不同键 → 新版本。
5. **历史不可变**：`UPDATE`/`DELETE` 在版本表上被 SQL 触发器物理拒绝。
6. **导入语义**：从现有 events 库导入时，`recorded_at` 一律为实际导入观测
   时刻；`first_seen_at`/`available_at` 仅保存为溯源字段，**不是**知识时间的证据。

## 精确限制（勿过度解读）

- **公开时钟**：未实现、且从当前版本证据看暂不可辩护（`available_at` 塌缩为
  `event_date`，见 KIMI_AUDIT H1）。需要先有公开滞后分布的经验测量（D2）。
- **覆盖边界**：适配器只导入"源库存在哪些行、它们声称什么"（含保守包含关系），
  不推断股权/技术/竞争关系，不与外部世界去重，不认证公开可得性。
- **节点属性即载荷**：节点属性整体作为一个 JSON 对象版本化（无属性级 diff）。
- **单写者假设**：时钟单调锚点假定单进程写入；多进程并发写需外部串行化。
- **导出是数据集快照**，不是预测基准；哈希稳定性仅保证"切割线之后的写入"
  不改变历史导出，schema/adapter/code 版本变化会改变哈希（刻意如此）。
- **适配器公开时间分级**：仅 `timestamp_quality='datetime'` 记 `observed`，
  其余一律 `inferred`（含被默认标成 `'date'` 的塌缩行）。
- 测试时钟（`clock=`）**仅**允许内存存储；生产路径注入即抛错。

## 测试

`tests/test_tkg.py`：31 个离线测试覆盖迟到、修正、撤销、先选后滤、时钟时区/
回退、未来元数据泄漏、证据校验、原子回滚、幂等/冲突、SQL 不可变守卫、只读
适配器、导出哈希稳定性、CLI 端到端。运行：

```bash
python -m medradar selftest     # 全量 471 tests OK (skipped=3)
```
