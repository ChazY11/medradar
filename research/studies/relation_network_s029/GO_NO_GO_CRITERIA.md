# S-029 预注册决策门槛 / Pre-Registered GO-NO-GO Criteria

**Fixed before any quality metric was computed.** Written and committed before the quality
metrics script (`code/s029_08_quality_metrics.py`) was first executed. Its sha256 is recorded in
`artifacts/prereg_decision.json` and re-checked by `code/s029_12_verify_report.py`, so the order of events
is verifiable rather than asserted.

This file defines what would count as success *before* looking at the numbers, because the temptation
after S-028 is to lower the bar until the project can continue.

---

## 0. What is being decided

S-029 does not decide "is the network interesting". It decides one thing:

> Are these evidential relations good enough to be used as the input of a **time-ordered** prediction
> experiment in S-030?

Three possible verdicts, exactly one must be issued:

* `GO FOR S-030 PREDICTION` — all conditions T1–T6 hold;
* `REVISE DATA CONSTRUCTION` — the relations are observable and traceable (T1, T2, T3, T5 hold) but
  time quality and/or human validation is insufficient (T4 and/or T6 fails);
* `NO-GO FOR PREDICTION` — the relation layer itself is not trustworthy (T1, T3 or T5 fails).

A partial pass is a `REVISE` only if the *relation layer* passes; a weak relation layer cannot be
fixed by better time metadata, and a strong relation layer with weak time metadata cannot be
"corrected" by modelling.

---

## 1. Thresholds and their justification

| # | Condition | Threshold | Why this threshold (not a round number) |
|---|---|---|---|
| **T1** | Machine-verified relation claims (`VERIFIED_BY_SOURCE` + `CANDIDATE`) | ≥ **250** claims total, spanning **≥2** relation families, with **≥40 per company for ≥4 of 5 companies** | S-028's decisive failure was a graph resting on 12.1% of the event lane and 51 companies × 38 tracks, with only 303 observed pairs — too small and too flat to carry structural inference. 250 claims is not "large", but it is enough for *countable* per-company coverage and for a stratified audit; the 4/5-company condition rejects a dataset that is secretly a Medtronic-only sample. |
| **T2** | Evidence traceability | **100%** of claims carry `evidence_id`, source record id and payload hash; **≥95%** re-resolvable to the committed raw payload by `code/s029_12_verify_report.py` | A claim whose evidence cannot be re-fetched is not evidence. 100% is attainable because evidence rows are generated only from stored payloads; the 95% floor allows for gzip/round-trip edge cases only. |
| **T3** | Entity resolution quality | `UNMAPPED` ≤ **20%** of source-stated candidate records; `AMBIGUOUS + CONFLICTED` ≤ **10%** of claims; `FUZZY`-only claims ≤ **10%** | S-028's entity layer was 82.7% unmapped on the company key and contained hindsight alias merges. 20% still leaves a fifth of the evidence unusable, which is the most a downstream study can tolerate while still reporting a coverage number honestly. `FUZZY` ≤10% enforces that identity does not rest on string similarity. |
| **T4** | Temporal quality — **point-in-time capability** | ≥ **100** claims whose `first_seen_at − published_at ≤ 7 days` (real `ACTUAL_OBSERVATION`) **and** ≥ **50%** of claims carrying both a `declared_at` and a source event/valid date at DAY or MONTH precision | This is the condition that decides whether a *temporal* prediction experiment is honest at all. S-028 had 6 such records out of 400 and could not use them; the threshold is set at 100 because a temporal holdout needs enough genuinely-late-observed events to form at least one evaluation window. The precision sub-condition exists because a year-only date cannot order events within a year. |
| **T5** | Cross-source linkage | ≥ **25%** of trial-referenced PMIDs resolvable in Europe PMC **and** ≥ **30%** of institutions appearing in ≥2 sources share a verified ROR id | A network that only exists inside one database is not a cross-source network; S-028 had **zero** cross-source relations. 25%/30% are floors for "the linkage is measurable and non-trivial", not targets. |
| **T6** | Human adjudication | ≥ **100** worksheet rows with filled `human_label`, `reviewer_id`, `review_date` | Machine agreement is not truth. Without this, no precision/recall claim may be made and a prediction study would be building on unvalidated labels. This condition is expected to **fail** in this round, because no human reviewer was available. |

---

## 2. Pre-declared expected outcome (before measurement)

Declared now, so that the later verdict is not fitted to the data:

* **T2** expected to pass by construction.
* **T1** likely to pass only in the reduced sense of "≥250 claims across families", because Europe PMC
  affiliation claims are plentiful; per-company coverage for Dräger and Mindray is the risk.
* **T3** expected to be the strongest failure point: affiliation strings in Europe PMC are free text,
  and the trial-site/collaborator institutions are also free text.
* **T4** expected to **fail decisively**: the oldest record in this study is decades old and MedRadar's
  own observation history is one day long, so genuine `ACTUAL_OBSERVATION` records will be ~0.
* **T5** expected to be measurable but partial.
* **T6** will fail by construction (no human reviewer in this session).

Therefore the *scientifically expected* verdict is `REVISE DATA CONSTRUCTION` or
`NO-GO FOR PREDICTION`, and any `GO` would require T4 and T6 to pass, which cannot happen without
new observation history or a real reviewer. This is stated in advance so that a negative verdict is
not later described as a surprise, and a positive one would require evidence strong enough to
overturn this prior.

---

## 3. Anti-relaxation clause

1. No threshold may be edited after seeing the quality metrics. If one must change, it changes in a
   new dated amendment **with the old and new value and the reason**, and the verdict is recomputed
   under both thresholds and both are reported.
2. No verdict may be softened ("conditional go", "go with caveats") — the three allowed strings are
   the entire vocabulary.
3. A `REVISE` verdict must name the specific condition that failed and the specific, testable thing
   that would make it pass in a future round.
4. S-029 does not train a model and does not report predictive performance regardless of verdict.
5. If a threshold passes for a trivial reason (e.g. T2 passes because each claim is generated from its
   own stored payload), that is reported as what it is: a construction guarantee, not an empirical
   finding.


---

## 附录 A — 修正记录 / Amendments (dated, appended after first measurement)

> **修正规则：** 阈值本身不变；以下两条是对**度量口径**的澄清，均在看到第一次质量指标之后写下，
> 因此都附上"修正前数值 / 修正后数值 / 对判定的影响"。任何读者都可以据此判断结论是否被挑选过。

### Amendment 1 — 2026-11-04 · T3 的 UNMAPPED 分母

* **问题：** 原条款写"UNMAPPED ≤20% of source-stated candidate records"，未指定候选集合。
  第一次计算使用全部 4,395 个候选（含 211 个公司名与 1,041 个无法归类字符串），得到 **32.4% → FAIL**。
  ROR 是科研机构注册库，不索引公司，把公司名放进机构解析分母是类别错误。
* **修正：** 以**机构类候选**（3,143 个）为分母：**18.2% → 通过该子项**。
  两个数值均保留在 `artifacts/quality_metrics.json`（`institution_unmapped_pct_class_correct` 与
  `institution_unmapped_pct_naive_all_candidates`）。
* **对判定的影响：无。** T3 仍为 FAIL，因为第三子项"仅模糊身份"为 **10.08% > 10.0%**（超出 0.08 个百分点），
  与分母无关。若两项都通过，判定也只是 `REVISE`，不是 `GO`（T4/T6 仍未通过）。

### Amendment 2 — 2026-11-04 · T5 子条款 (b) 的操作化

* **问题：** 原条款"≥30% of institutions appearing in ≥2 sources share a verified ROR id"表述含混：
  分母是"全部机构"还是"出现在两个来源中的机构"？
* **修正：** 按字面条件分母计算——出现在 ≥2 个来源中的机构中 **300/300 = 100%** 带已验证 ROR id
  → **通过**；"全部机构中出现在两个来源的比例 = 15.08%" 作为**描述性统计**单独报告，不参与阈值判定。
* **对判定的影响：** T5 由 FAIL 变为 **PASS**。最终判定仍为 `NO-GO FOR PREDICTION`，
  因为 T3、T4、T6 各自独立失败。

### 关于"事件顺序可验证"的更正

初稿声称"事件顺序可验证而不是断言"。这是过度表述：本文件、质量指标与 `prereg_decision.json`
**首次进入 git 是在同一个提交中**，因此顺序由文件内的生成时间戳、本附录与修正记录来记录，
而不是由更早的提交来证明。该句已从文档中删除。

### 不允许的修改（仍然禁止）

1. 阈值本身（20% / 10% / 25% / 30% / ≥100 条 / ≥250 条）不得改动。
2. 不得新增第三种判定字符串。
3. 上述任何修正都不得改变 `NO-GO FOR PREDICTION`；若未来某轮达到 `GO`，必须重新预注册并重新采集。
