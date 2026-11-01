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
3. **版本单元是断言**：每个节点身份（`node_type, node_id`）是一条断言谱系，
   每个有向边身份（`edge_type, src, dst`）是另一条独立谱系，各自按
   `(recorded_at, seq)` 版本化（`assertion_id` = 内容 SHA256）。一个实体的
   多条关系 = 多条边谱系；**节点属性整体作为一个对象版本化**（无属性级
   diff，见下"精确限制"）。
4. **端点可见性合同（快照/导出）**：边只在**两个端点都出现在同一组
   `(known_at, valid_at)` 切割线选中的节点集合中**时才输出。端点被撤销、
   尚未生效或在该切割线下不存在时，该边被**排除**——绝不输出悬空引用，
   绝不回填未来节点元数据，也绝不为了让边成立而"复活"节点。
5. **重试安全**：相同 `idempotency_key` + 相同内容 → 返回原始版本、零新历史；
   相同键不同内容 → 显式冲突；不同键 → 新版本。
6. **历史不可变**：`UPDATE`/`DELETE` 在版本表上被 SQL 触发器物理拒绝；
   重提交守卫（`BEFORE INSERT`）进一步拒绝任何主键（或幂等键）已存在的
   插入，因此 `INSERT OR REPLACE` / upsert 也无法覆写已记录的版本。
   **边界**：这防的是**改写/删除**（游离 SQL 会话/缺陷代码），**不防伪造追加**——
   游离 SQL 仍可 `INSERT` 一条带任意 `recorded_at` 的伪造修订；也**不防数据库属主**
   （可删触发器或重建库），属主级防护依赖文件权限与外部审计，不在本组件承诺内。
7. **导入语义**：从现有 events 库导入时，`recorded_at` 一律为实际导入观测
   时刻；`first_seen_at`/`available_at` 仅保存为溯源字段，**不是**知识时间的证据。

## 精确限制（勿过度解读）

- **公开时钟**：未实现、且从当前版本证据看暂不可辩护（`available_at` 塌缩为
  `event_date`，见 KIMI_AUDIT H1）。需要先有公开滞后分布的经验测量（D2）。
- **覆盖边界**：适配器只导入"源库存在哪些行、它们声称什么"（含保守包含关系），
  不推断股权/技术/竞争关系，不与外部世界去重，不认证公开可得性。
- **节点属性即载荷**：节点属性整体作为一个 JSON 对象版本化（无属性级 diff）；
  "属性级独立断言"未实现，文档与实现均以本条为准。
- **时间戳渲染**：存储/比较的规范渲染为固定 6 位微秒 UTC
  （`YYYY-MM-DDTHH:MM:SS.ffffffZ`），保证字典序 = 时间序；schema 版本
  `tkg-schema-2` 起生效（旧 `tkg-schema-1` 库请重建，不自动迁移；打开时被
  schema 版本门禁显式拒绝，见上条）。**date-only 输入没有秒级快路径**：字符串
  `2024-02-03` 或 `date(2024,2,3)` 一律补齐为 `2024-02-03T00:00:00.000000Z`
  （适配器导入的 `event_date` 走同一路径），因此同日 `00:00:00.5Z` 切割线与
  `valid_to` 的 half-open 判断都正确。小数秒接受 1–9 位：解析前统一右补/截断
  为 6 位，因此 Python 3.10（`fromisoformat` 只接受 3/6 位）与 3.11+ 行为一致
  （共享 helper：`medradar/tkg/_time.py`）。
- **schema 版本门禁**：新库创建即永久写入 `meta.schema_version`；打开旧库时
  校验该戳——缺失（schema-1 时代未打戳）或不匹配一律**拒绝打开**并给出可执行
  提示（重建、不自动迁移、不删数据），不会把微秒级 schema-2 与秒级旧行混存。
- **证据 `source_version`**：验收规范 C2 的逐断言 `source_version` **未实现**——
  不存储、不拒绝，缺省视为**显式 unknown**。manifest 级
  `schema_version`/`adapter_version`/`code_version` 是**代码与 manifest 身份**，
  **不声称**等价于源数据版本；`evidence_sha256` 是**内容哈希**，不是源修订号。
  源修订号关键时由调用方显式写入 `source_locator`/`attrs`（随导出保留）。
  逐条选中证据保留 `assertion_id`/`source_locator`/`evidence_sha256`/`evidence_kind`。
- **单写者假设**：时钟单调锚点假定单进程写入；多进程并发写需外部串行化。
- **导出是数据集快照**，不是预测基准；哈希稳定性仅保证"切割线之后的写入"
  不改变历史导出，schema/adapter/code 版本变化会改变哈希（刻意如此）。
- **适配器公开时间分级**：仅 `timestamp_quality='datetime'` 记 `observed`，
  其余一律 `inferred`（含被默认标成 `'date'` 的塌缩行）。
- 测试时钟（`clock=`）**仅**允许内存存储；生产路径注入即抛错。

## 测试

`tests/test_tkg.py` 与 `tests/test_forecast_registry.py` 为离线测试，覆盖迟到、修正、
撤销、先选后滤、时钟时区/回退（含同秒微秒回退）、未来元数据泄漏、证据校验、原子回滚、
幂等/冲突、SQL 不可变守卫（含 `INSERT OR REPLACE`/upsert 绕过尝试）、端点可见性合同
（撤销/未生效/缺失端点）、固定哈希向量、schema 版本门禁（legacy/未打戳/不匹配拒绝且
不损数据）、只读适配器、导出哈希稳定性、1–9 位小数秒与 date-only 时间戳规范化、
CLI 端到端。运行全量离线测试：

```bash
python -m medradar selftest
```

以命令实际输出为准；本文档不硬编码测试数量（数量会随集成与新增用例变化）。
