# 前瞻观察登记 / Prospective Observation Registry — 设计与方法说明

状态：Live Observatory v1 的 Research Lab 子模块（分支 `feat/live-observatory-v1`）。
实现：`medradar/observatory/prospective.py`（领域逻辑）、
`medradar/product/prospective.py`（只读整形）、
`medradar/web/routes_lab.py`（`/api/lab/prospective*`）。

## 1. 它是什么，不是什么

它是一台**可审计的登记器**：在科学假设的结局尚不可观察之前，先把假设、目标事件定义、
观察窗口、基线、评估判据以及**冻结时刻账本中已知的证据**一次性固定下来，之后在窗口结束后
报告窗口内新观察到的候选证据。

它**不是**预测引擎：

* 不产生概率、评分、置信度或准确率；
* 不做校准，也没有校准误差；
* 不宣称任何条目"已验证 / validated / calibrated / predictive"；
* 不自动判定目标事件是否发生——它只列出窗口内新观察到的候选证据，并明确要求研究者按
  冻结时声明的判据自行判定。

登记器解决的是"我们怎么知道当时到底能看到什么"：冻结输入来自观察账本的
**时点视图** `ledger.snapshot(freeze_at)`，只包含 `first_seen_at <= freeze_at` 的记录，
且每条记录取 `captured_at <= freeze_at` 的最新版本。之后才被采集到的历史记录（即使
`event_at` 更早）不会进入冻结输入。

## 2. 存储与不可变性

登记目录：`MEDRADAR_PROSPECTIVE_DIR` 环境变量 → 数据主目录下的 `prospective/`
（默认 `data/prospective/`，`data/` 已被 git 忽略，不入库）。

```
data/prospective/entries/<entry_id>.json                  # 冻结正文，只写一次
data/prospective/entries/<entry_id>.evaluation.<n>.json   # 评估附录，append-only
data/prospective/entries/<entry_id>.status.<n>.json       # 状态附录（撤回），append-only
```

* `freeze()` 使用排他创建（`open("x")`）写入：文件已存在时**永不覆盖**。重复提交完全相同的
  内容返回 `result="duplicate"`；同一 `entry_id` 但内容不同则抛
  `FrozenDocumentConflict`。
* 冻结正文带有 `content_sha256`（对除该字段外的规范化 JSON 计算 SHA-256）。
* 任何后续状态变化（撤回）或评估结果都是**新的附录文件**，不修改冻结正文；附录记录它所
  依据的冻结正文哈希 `frozen_content_sha256`。
* `verify_frozen(entry_id)` 重新读取文件、重算正文哈希与证据列表哈希（`evidence_sha256`），
  与登记值不一致时返回 `ok=false`，并说明"文件已被改写或损坏"。在哈希校验失败的正文上，
  评估会被拒绝（`status="TAMPERED"`），不会产生任何结果。
* 边界：这是**防误改与防事后改写**的审计手段，不是对拥有文件系统的对手的密码学证明
  （有权限的人可以重写文件并重算哈希；此时 `evidence_sha256` 与账本记录仍会被复核发现）。

## 3. 状态词汇

冻结正文只写 `EXPERIMENTAL`（未验证的默认状态）；**有效状态**由窗口、只读附录与当前时间
派生，不写回正文：

| 状态 | 含义 |
|---|---|
| `EXPERIMENTAL` | 冻结后的默认状态：尚未进入声明窗口，任何结论都未验证 |
| `ACTIVE` | 已冻结，声明的观察窗口正在进行 |
| `DUE` | 窗口已结束，但还没有评估附录 |
| `MATURED` | 窗口结束且已按声明判据追加评估附录（不等于已验证） |
| `RETRACTED` | 研究者已撤回该条目（必须给出原因） |

## 4. 冻结、回放与防篡改复核

```python
from medradar.observatory import prospective

registry = prospective.open_registry()             # 默认目录；也接受显式目录
frozen = registry.freeze({
    "entry_id": "demo-2026-001",
    "label_zh": "示例假设（前瞻登记）",
    "hypothesis_zh": "……",
    "target_event_definition_zh": "……",
    "baseline_zh": "……",
    "evaluation_criteria_zh": "……",
    "window_start": "2026-01-01T00:00:00+00:00",
    "window_end":   "2026-04-01T00:00:00+00:00",
    "freeze_at":    "2025-12-20T00:00:00+00:00",
    "scope": {"source": "sec_edgar", "entity_id": "medtronic", "track_id": None},
    "synthetic": False,
}, ledger=ledger)

registry.verify_frozen("demo-2026-001")            # {"ok": True, "content_sha256": ...}
registry.evaluate_against_ledger("demo-2026-001", ledger)   # now >= window_end 才计算
registry.list_entries()                            # 摘要（含有效状态、证据数、评估数）
registry.get_entry("demo-2026-001")                # 冻结正文 + 只读附录历史
```

时间纪律：

* `freeze_at` 必须是真实过去/当前时间，且**不得晚于** `window_start`——窗口开始后才登记
  属于事后登记，不是前瞻冻结，会被拒绝。
* 带时区缺失的时间输入被拒绝（不猜时区）；缺失时间保持为空。
* `freeze_at`/`window_*`/`computed_at` 一律规范化成 UTC、秒级 ISO-8601。

## 5. 评估语义

`evaluate_against_ledger(entry_id, ledger, now)`：

1. 先复核冻结正文哈希；失败则拒绝（`TAMPERED`）。
2. `now < window_end` → 返回 `{"status": "NOT_DUE", "evaluated": false, "reason_zh": ...}`，
   **不写任何文件**，不伪造结果。
3. `now >= window_end` → 用账本自身的时点视图计算：
   * `inputs`：冻结输入（冻结时刻账本已知、且符合声明范围的记录）；
   * `outcomes`：`first_seen_at ∈ (max(freeze_at, window_start), window_end]` 且不属于
     冻结输入的新观察——即"冻结之后、窗口内才被发现"的候选证据；
   * `new_versions`：冻结输入在窗口内被采集到的新版本（单独披露，不混入新观察计数）；
   * `pre_window_discoveries`：冻结之后、窗口开始之前发现的记录（既非输入也非结局）；
   * `ledger.counts` / `snapshot_as_of`：**计算时刻**的账本计数，以及结局所依据的
     `snapshot(window_end)` 时点；
   * 窗口结束后才发现（`first_seen_at > window_end`）的记录被 `snapshot(window_end)`
     自然排除。
4. 结果作为新的 `evaluation.<n>.json` 附录写入，返回该附录；评估本身带
   `classification="CANDIDATE_EVIDENCE_ONLY"` 与 `human_classification_required=true`。
5. 修正/复评是新的附录序号（`evaluation_seq` +1，`supersedes` 指向前一版），原始附录保留。

`append_evaluation(entry_id, evaluation)` 只接受 `status="MATURED"` 且
`computed_at >= window_end` 的评估；其他状态或更早的 `computed_at` 一律拒绝。

## 6. 合成测试条目的标注

测试/演示条目必须 `synthetic: true`，且 `label_zh` 与 `note_zh` 必须包含「合成测试」
（否则 `freeze()` 直接拒绝）。接口与页面据此：

* 列表与详情返回 `synthetic: true`、`synthetic_badge_zh="合成测试（非真实前瞻结果）"`；
* 列表页显示「合成测试」徽标与"不得引用为证据"的提示；
* 评估附录的 `honesty_zh` 首条声明这是测试构造；
* `evidence_status` 为 `SYNTHETIC`（非合成条目为 `UNVALIDATED`，登记器**没有**"已验证"
  这一档）。

任何真实世界的结论都不能来自合成条目。

## 7. API

`GET /api/lab/prospective`

```jsonc
{
  "registry": {"path": "data/prospective", "exists": true, "entry_count": 1,
               "status_counts": {"EXPERIMENTAL":1,"ACTIVE":0,"DUE":0,"MATURED":0,"RETRACTED":0},
               "synthetic_count": 0, "matured_count": 0, "integrity_issues": 0,
               "empty": false, "notice_zh": "..."},
  "entries": [{"entry_id", "label_zh", "hypothesis_zh", "freeze_at", "window_start",
               "window_end", "target_event_definition_zh", "baseline_zh",
               "evaluation_criteria_zh", "status", "status_label_zh", "synthetic",
               "synthetic_badge_zh", "evidence_status", "frozen_evidence_count",
               "frozen_evidence_as_of", "evaluation_count", "latest_evaluation",
               "evaluation_history", "frozen_verified", "integrity", "content_sha256"}],
  "empty": false,
  "empty_zh": "...",                    // 空登记器时的诚实说明
  "status_vocabulary": [...], "policy_zh": [...], "honesty_zh": [...],
  "validation": {"validated": false, "calibrated": false, "predictive": false}
}
```

`GET /api/lab/prospective/{entry_id}` 返回 `entry`（冻结协议 + 冻结证据条目）、
`evaluations`（append-only 历史）、`verification`（重算哈希的防篡改结果）与
`policy_zh/honesty_zh/validation`。未知条目为 404。

登记器缺失或为空时两个接口都返回 200 与诚实的空状态，**从不生成示例条目**。
`GET /api/lab` 额外包含 `prospective` 摘要块（状态计数、合成条目数、已到期数、目录与说明），
既有字段不变。

## 8. 页面

`web/js/pages/lab.js` 在既有 Research Lab 内容之后追加独立分区
「前瞻观察登记 / Prospective Observation Registry」：条目表（冻结时间、声明窗口、目标事件
定义、基线、判据、状态徽标、合成徽标、冻结证据数、评估数），每条目一个
`disclosure` 展开"冻结输入与评估历史"（append-only 附录表）。空登记器显示诚实空状态。
既有研究卡片、详情与产物渲染保持不变。

## 9. 测试与运行

```bash
python -m pytest tests/test_observatory_prospective.py -q          # 合成测试层
python -m pytest tests/test_product_api.py -q                      # 既有 API 不回退
python -m medradar web --port 8793                                 # 人工核对三个接口
```

测试使用 `tmp_path` + `MEDRADAR_OBSERVATORY_DB` / `MEDRADAR_PROSPECTIVE_DIR`，不写真实
`data/`。覆盖：重复/冲突冻结被拒、冻结后账本新增（新记录 + 输入新版本）不改变冻结字节与哈希、
窗口结束前拒绝评估（`NOT_DUE`）、窗口后只计窗口内新观察并记录计算时刻账本计数、合成条目
标注「合成测试」且不作为证据、撤回是新的状态附录且冻结正文不变、三个 HTTP 接口的形状与
既有 `/api/lab`、`/api/lab/{study_id}` 仍可用。

## 10. 已知边界

* 登记器不判断"目标事件是否发生"，只列候选证据；判定必须由研究者按冻结判据完成。
* 冻结范围按 `source/entity_id/track_id` 过滤；实体/赛道归属使用账本的 append-only 映射
  历史（按秒级时间比较，因为账本映射时间戳带微秒）。
* 账本目录里 `payload_hash` 等字段只证明"当时存了什么"，不证明来源本身真实。
* 有文件系统写权限的人可以删除/重写附录文件；登记器的协议是 append-only 软件约束 + 哈希
  复核，不是分布式不可篡改存储。
