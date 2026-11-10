# H2_RECONCILIATION — EXP-H2 numerical reconciliation

**Task:** P0-A of CONVERGENCE-001 (`task-1`).
**Worktree:** `D:\DEPPSKK\worktrees\convergence-001`, branch `integration/convergence-001`
(based on `main` `b2a14c0`); HORIZON-001 frozen input is PR #29 head `2dcdc99`.
**Written:** 2026-11-11.
**Scope of this report:** the numerical disagreement only. No protocol change, no
network access, no commits.
**Correction status:** the two frozen prose files are corrected in this integration
branch as a forward correction of PR #29's copy; PR #29 itself still carries the stale
numbers until the HORIZON owner applies
`research/convergence/h2/HORIZON_PATCH_FOR_OWNER.md`. See “Where the correction lives”.

---

## 1. The disagreement

| source | pairs | CONFIRMED | REJECTED | UNKNOWN | S2 fired | S3 fired | hard negatives |
|---|---:|---:|---:|---:|---:|---:|---:|
| `research/horizon/EXPERIMENT_RESULTS.md` (at source `2dcdc99`; corrected here) | 712 | 0 | 387 | 325 | 445 | 365 | 12 (HN4 only) |
| `research/horizon/reports/REGULATORY_FRONTIER_REPORT.md` (at source `2dcdc99`; corrected here) | 712 | 0 | 387 | 325 | 445 | 365 | 12 (HN4 only) |
| `research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json` | 726 | 0 | 0 | 726 | 0 | 708 | 26 (HN3 14 + HN4 12) |
| `research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl` (726 lines) | 726 | 0 | 0 | 726 | 0 | 708 | 26 (HN3 14 + HN4 12) |

Before correction in this integration branch, the prose was not a rounding
difference: it asserted 387 pairs were refutable and only 325 unknown, while the
machine artifact asserts no pair is refuted at all and 445 pairs share a model token.
Both prose files were introduced by the same HORIZON-001 workstream, and both quoted
the same superseded run; §7 lists the corrections now applied here.

---

## 2. Frozen inputs and reproduction (offline)

All inputs are local files; nothing was fetched.

| role | path | SHA-256 |
|---|---|---|
| FDA input | `research/horizon/DATASETS/regulatory/accessgudid/records.jsonl` (320 lines) | `233274cb66d4a75552b6d4be52af89c1ae10fec46ce22c0d1052ff1b1c089c54` |
| Canada input | `research/horizon/DATASETS/regulatory/canada_mdall/records.jsonl` (174 lines) | `b00c4565ba24346877954124dceecebcbf844dd5cbce1792749bb404479e0dc7` |
| rule | `research/horizon/experiments/regulatory/EXP_H2_SELECTION_RULE.md` | `a6a94fa7956344b2a69b51bdd6025dac41c0e49be78fa783cc48a6f09ab7036a` |
| code | `research/horizon/experiments/regulatory/exp_h2_identity.py` | `898cfbdc7ed1e6c80969496ab6250a46a13d4a032e9182b3c4f2b11e4dcadd29` |
| pairs | `research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl` | `e7ad98e1d6b45636d1e1ea4159ce1780e22ec3c2d977cd1b5fa98ab1046390d9` |
| summary | `research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json` | `6967dbd941f0c61e32252836e9707836820c622db69c2c2f20532ea195f78a19` |

The frozen pair file and summary are **byte-identical to the blobs introduced in
commit `18a7580`**, so they have not been touched since birth:

```
$ git hash-object research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl
d92ef98aa89a44ba2edb652a996f683242f52a6a
$ git rev-parse 18a7580:research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl
d92ef98aa89a44ba2edb652a996f683242f52a6a
$ git hash-object research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json
835ae45c45d1ae4136992a0ebbce0cb81e57684b
$ git rev-parse 18a7580:research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json
835ae45c45d1ae4136992a0ebbce0cb81e57684b
$ git diff --stat 18a7580 -- research/horizon/experiments/regulatory
(no output)
```

### 2.1 The reproduction copy

`tools/convergence/h2/exp_h2_identity_local.py` is a copy of the frozen script.
`git diff --no-index` between the two files shows changes to **the module
docstring, the loader and the output paths only** (22 insertions, 8 deletions);
`hz.schema.read_jsonl` is replaced by an identical, local stdlib implementation:

```
python tools/convergence/h2/_make_local_copy.py
git diff --no-index research/horizon/experiments/regulatory/exp_h2_identity.py \
    tools/convergence/h2/exp_h2_identity_local.py
```

The script has no network code path; it reads exactly the two JSONL files above
(320 + 174 records) and writes nothing into the frozen tree.

```
$ python tools/convergence/h2/exp_h2_identity_local.py
primary: pairs_total=726 pairs_candidate=700 pairs_hard_negative=26
         verdicts={"UNKNOWN": 726}
         by_construction_rule={"candidate":700,
             "HN3_same_family_different_device":14,
             "HN4_subsidiary_vs_parent":12}
sensitivity_lenient: pairs_total=726 verdicts={"UNKNOWN": 726}
```

The regenerated pair file is byte-identical to the frozen one:

```
$ python tools/convergence/h2/reproduce_h2.py
frozen pairs sha256   = e7ad98e1d6b45636d1e1ea4159ce1780e22ec3c2d977cd1b5fa98ab1046390d9
recomputed pairs sha256 = e7ad98e1d6b45636d1e1ea4159ce1780e22ec3c2d977cd1b5fa98ab1046390d9
checks: 10/10 passed
RESULT: REPRODUCED        (exit 0)
```

**Answer to the reproduction question:** yes — the current committed code, run
offline on the two frozen inputs, reproduces the frozen artifact exactly, and the
frozen artifact is **726 pairs / 0 CONFIRMED / 0 REJECTED / 726 UNKNOWN**. The prose's
712/387/325 does not come from this code on these inputs.

---

## 3. What the current code does

`exp_h2_identity.py` (528 lines):

* **Inputs:** `DATASETS/regulatory/accessgudid/records.jsonl` (320) and
  `DATASETS/regulatory/canada_mdall/records.jsonl` (174). No network.
* **Pair construction:** all 320 × 174 cross pairs for which at least one of
  S1–S5 fires, sorted by `(-len(signal_set), pair_id)`, deterministically capped at
  **700 candidates**, then four deterministic hard-negative builders append labelled
  rows (`HN1`…`HN4`).
* **Signals:** S1 exact normalised name; S2 shared model token
  (`model_tokens`: letter+digit token ≥4 chars, or ≥6 alnum with a digit; `strict`
  primary, `lenient` sensitivity); S3 same firm (`target_firm_slice`, with a
  manufacturer-string fallback); S4 same-scheme official identifier equality;
  S5 ≥2 shared non-stopword name tokens.
* **Verdict function (pre-registered):**
  1. `CONFIRMED` iff S4;
  2. else `REJECTED` iff `S2 and not S3`, or (`S2` and MDALL `end_date` < GUDID
     `source_public_at`);
  3. else `UNKNOWN`.
* **Run result:** S1 = 0, S2 = 0, S3 = 708, S4 = 0, S5 = 37 over the 726 published
  rows; therefore the rejection branch is unreachable and all 726 rows are
  `UNKNOWN`.

The committed code therefore *can* emit `REJECTED` (the `HN2` builder even
constructs such rows on purpose), but on this sample S2 never fires, so it emits
none. That is the documented intent of `EXP_H2_SUMMARY.json`'s `finding` text.

---

## 4. Root cause, with evidence

### 4.1 Provenance of the committed artefacts

```
$ git log --oneline --all -- research/horizon/experiments/regulatory
3c3a295 integration(convergence-001): import HORIZON-001 data frontier ...
18a7580 research(horizon-001): global data-frontier acquisition, two new patent corpora ...
```

* `18a7580` (2026-11-10 07:34:17 +0800) introduced **all** four EXP-H2 files
  (selection rule, script, 726-line pairs file, summary) and `EXPERIMENT_RESULTS.md`.
* `4c8d8f9` (2026-11-11 01:36:37 +0800) added `REGULATORY_FRONTIER_REPORT.md`.
  Its parent is `18a7580`:
  `git rev-parse 4c8d8f9^` → `18a7580875c27554168ff2842ca3ffb02efce426`.
* At source `2dcdc99` the two documents were byte-identical to the blobs introduced
  by those commits, and they were byte-identical to this worktree's pre-correction
  copies. This integration branch applies a forward correction derived from
  `2dcdc99` (see “Where the correction lives” and
  `research/convergence/h2/HORIZON_PATCH_FOR_OWNER.md`).

Thus the report was added in the child commit `4c8d8f9` and carries the same stale
numbers as `EXPERIMENT_RESULTS.md`; whether one was copied from the other or both
were drafted from one earlier run cannot be distinguished from git. Either way the
mismatch was born inside the HORIZON-001 workstream, not introduced by the
CONVERGENCE-001 import. (Note: the task brief said both documents came from the one
commit `18a7580`; the report actually came from its child `4c8d8f9`.)

### 4.2 Where 712 comes from — exact, no duplicate collapse

`726 − 712 = 14`, and 14 is exactly the current `HN3` row count:

```
$ python research/convergence/h2/audit_pairs.py
rows=726  unique_pair_id=726  duplicate_pair_id=0
verdicts={'UNKNOWN': 726}
by_construction_rule={'candidate': 700,
                      'HN3_same_family_different_device': 14,
                      'HN4_subsidiary_vs_parent': 12}
per_signal_fired={'S1': 0, 'S2': 0, 'S3': 708, 'S4': 0, 'S5': 37}

identity checks
  726 - HN3(14)                     = 712
  candidate(700) + HN4(12)          = 712
  candidate(700) + HN3(14) + HN4(12) = 726
```

So **712 = 700 candidate rows + 12 HN4 rows**. The prose's own hard-negative
sentence names only `HN4_subsidiary_vs_parent` with **12 pairs** — the prose was
written against an earlier revision of the script that had only the HN4 builder.
The pair cap (700) and HN4 count (12) are unchanged in the committed code. This is
not a dedupe artefact: the 726 `pair_id`s are unique.

### 4.3 Where 387/325 (and 445/365) come from — a coherent earlier run with a different S2

The stale table is *internally consistent* under exactly the verdict rule the
committed code implements, provided S2 fired 445 times:

```
$ python research/convergence/h2/analyze_claim_arithmetic.py
quoted verdicts: {'CONFIRMED': 0, 'REJECTED': 387, 'UNKNOWN': 325}
quoted per-signal fired: {'S2': 445, 'S3': 365}
quoted combinations: {'S1+S2+S3': ..., 'S2+S3+S5': 5/0/5/0,
                      'S2+S3': 93/0/35/58, 'S2+S5': 156/0/156/0}
derived buckets
  S2-only = 445 - 5 - 93 - 156 = 191
  S3-only = 365 - 5 - 93      = 267
  total   = 5 + 93 + 156 + 191 + 267 = 712
  REJECTED = 5 + 35 + 156 + 191 = 387
  UNKNOWN  = 58 + 267 = 325
internal consistency: PASS
```

So the stale family was produced by **a run whose S2 matcher fired 445 times** (and
whose pair set is exactly 700 candidates + 12 HN4). Under the committed rule that is
enough to generate 387 `REJECTED` rows (S2∧¬S3, plus 40 date contradictions inside
S2∧S3/S2∩S5); the current code cannot produce them because **S2 fires 0 times**.

The committed `model_tokens` modes give 0 shared model tokens between the two
samples (this is also what `EXP_H2_SUMMARY.json` documents in
`sensitivity_note`). We tested plausible earlier matchers on the frozen inputs and
none reproduces 445:

| matcher variant | pairs with S2 (full cross product) |
|---|---:|
| current strict model tokens, set intersection | 0 |
| current lenient model tokens, set intersection | 0 |
| any digit-bearing token ≥2 / ≥3 / ≥4, set intersection | 7 / 2 / 0 |
| numeric token ≥2 / ≥3, set intersection | 4 / 0 |
| strict model token as substring of MDALL text | 0 |
| digit-bearing token ≥3 / ≥4 as substring of MDALL text | 47 / 0 |
| any shared name token (≥1, current stop list) | 3,801 |

Commands: `python research/convergence/h2/explore_superseded.py` and
`python research/convergence/h2/explore_tokens.py`. These are diagnostics, not a
reconstruction claim; see §10.

**The exact earlier S2 code is not recoverable.** The only H2 implementation in the
object database is the committed script (`d09ffd54`, 23,022 bytes). The 135
unreachable blobs contain three final-session scratch helpers (two summary
inspectors, one patch script that adds the `hard_negative_rules_attempted` key) but
no earlier `exp_h2_identity.py` and no earlier pair file
(`research/convergence/h2/_recovered/README.md`). We therefore report the *numeric
mechanism* (S2-dependent REJECTED counts) with an exact internal-consistency proof,
and do **not** guess the old matcher text.

### 4.4 Hypotheses from the brief, adjudicated

| hypothesis | verdict | evidence |
|---|---|---|
| 712 comes from duplicate `pair_id`s (e.g. 14 duplicates) | **rejected** | 726 rows, 726 unique ids, 0 duplicates (`audit_pairs.py`) |
| 712 comes from an earlier pair-construction pass | **confirmed, exactly** | 712 = 700 candidate + 12 HN4; prose names only HN4; 726 − 14 HN3 = 712 |
| 387 REJECTED comes from a looser verdict rule that let name/model disagreement refute | **mechanism confirmed, code text unrecoverable** | committed rule itself rejects on S2∧¬S3; stale table is arithmetically consistent only with S2=445; committed matcher fires S2=0; no earlier script blob exists |
| combination (712 unique + old-rule rejections) | **yes** | the stale header total and the stale verdict table both belong to one earlier run, as §4.2–4.3 show |

A new detail relative to the brief: the pre-registered rule text and the committed
code agree on an S2-dependent `REJECTED` path, while the summary's `finding` prose
argues that name-level evidence can never refute. With S2 = 0 the two readings
coincide at 0 rejections; this should be noted but does not change the official
result.

---

## 5. Official result

**Official EXP-H2 result (pre-registered rule + committed code + frozen inputs):**

| quantity | value |
|---|---:|
| pairs total | **726** |
| — candidate pairs | 700 |
| — constructed hard negatives | 26 (`HN3_same_family_different_device` 14, `HN4_subsidiary_vs_parent` 12) |
| CONFIRMED | **0** |
| REJECTED | **0** |
| UNKNOWN | **726** |
| S1 fired | 0 |
| S2 fired | 0 |
| S3 fired | 708 |
| S4 fired | 0 |
| S5 fired | 37 |
| lenient-model-token sensitivity | identical: 726 total, 0/0/726 |
| signal combinations | `S3+S5` 19 (0/0/19), `S3` 689 (0/0/689), `S5` 18 (0/0/18) |

**Why this is official:** it is what the frozen pre-registration, the frozen
committed implementation and the frozen inputs produce; the pair file is
byte-identical to the committed one and the summary's claimed counts match the
recomputed ones. The stale prose cannot be produced by any committed artefact and
is therefore historical/superseded. Changing the protocol to match the prose (e.g.
re-introducing a loose S2 matcher) would be post-hoc rule tuning and is explicitly
not done here.

**Effect on the science:** none of the substantive conclusions change. The headline
— *zero confirmed identity pairs; GUDID and MDALL share no official identifier
namespace, so there is no keyless official-identifier bridge* — is reproduced and,
if anything, strengthened: not only does S4 never fire, S2 never fires either, so
there is no model-token collision to be tempted by. The stale prose's rhetorical
near-miss ("445 pairs share a model token, 0 provable") is factually wrong; the
true statement is that no pair shares a model token.

---

## 6. Superseded numbers (label them historical)

| number | status |
|---|---|
| 712 pairs | **superseded** = earlier run before the HN3 builder (700 + 12) |
| 387 REJECTED | **superseded** = earlier S2 matcher that fired 445 times |
| 325 UNKNOWN | **superseded** = complement of the above |
| S2 = 445 fired | **superseded** = old matcher; current S2 = 0 |
| S3 = 365 fired | **superseded** = artefact of the old pair selection; current S3 = 708 |
| hard negatives = 12 (HN4 only) | **superseded** = current total 26 (HN3 14 + HN4 12) |

Everything in `EXP_H2_SUMMARY.json` and `EXP_H2_PAIRS.jsonl` is **not**
superseded; those files are the official record.

---

## 7. Impact: files whose quoted numbers must be corrected

The machine artifacts need no change. Two prose files quoted the stale run and have
now been corrected in this integration branch; no other tracked markdown file in the
repository quotes these numbers (checked with a repository-wide markdown grep for
`712 pairs`, `712 candidate`, `445 fired`, `365 fired`, `445 pairs share`). Line
numbers below are from source commit `2dcdc99`.

### `research/horizon/EXPERIMENT_RESULTS.md`

| line(s) | stale | correct |
|---|---|---|
| 105 | `` `EXP_H2_PAIRS.jsonl` (712 pairs) `` | `(726 pairs)` |
| 112 | `### Result: 712 pairs, 0 CONFIRMED` | `726 pairs` |
| 117 | `REJECTED 387` | `0` |
| 118 | `UNKNOWN 325` | `726` |
| 126–133 | signal table with S2-combinations, S2 445 fired, S3 365 fired | replace with the official combinations (`S3+S5` 19, `S3` 689, `S5` 18), S2 0 fired, S3 708 fired; all C/R = 0 |
| 135–137 | `Hard negatives: **12 pairs** … HN4` | `26 pairs` (`HN3` 14, `HN4` 12), all UNKNOWN |
| 141–143 | “Agreement on name, model token and firm is *common*” | model-token agreement occurs **zero** times; only name-token overlap (S5, 37 pairs) is common |
| 145–147 | “445 pairs share a model token, 0 are provable” | “0 pairs share a model token” (rewrite; the old sentence is false) |

### `research/horizon/reports/REGULATORY_FRONTIER_REPORT.md`

| line(s) | stale | correct |
|---|---|---|
| 188 | `712 candidate pairs were generated` | `726 pairs` total (700 candidate + 26 hard negatives) |
| 194 | `REJECTED 387` | `0` |
| 195 | `UNKNOWN 325` | `726` |
| 199–206 | signal table with S2-combinations, S2 445 fired, S3 365 fired | replace with official combinations and per-signal counts as above |
| 208–210 | `Hard negatives: 12 pairs … HN4` | `26 pairs` (`HN3` 14 + `HN4` 12) |
| 217–218 | “no combination of name, model token and firm … ever produces a confirmation” | numerically still true (0 confirmed), but “model token” agreement does not occur in this sample; optional wording fix, not a numeric error |

`docs/convergence/H2_RECONCILIATION.md` (this file) is the only new document that
quotes both the official and the superseded numbers.

**Does any substantive conclusion depend on the stale numbers?** No:
* zero CONFIRMED — unchanged (0 = 0);
* “no official-identifier bridge” — unchanged (S4 = 0 in both runs);
* “name/model agreement never reaches CONFIRMED” — unchanged, and the model-token
  variety of that statement is vacuous because model tokens never agree;
* hard-negative design — unchanged in kind, larger in count (26 vs 12);
* ATLAS-001 handoff / design conclusion — unchanged (no keyless official bridge).

### Application status

The corrections above are applied in this integration worktree
(`integration/convergence-001`), derived from source commit
`2dcdc995102f094d723005c79bb9b0ec7d9737f7`. Before the edit the two files here were
byte-identical to that commit's blobs (`04503e43…` and `5762939f…`); after the edit
they are `3c8788c7…` and `93ed84c2…`. The ready-to-apply patch for the HORIZON-001
branch and PR #29 is `research/convergence/h2/HORIZON_PATCH_FOR_OWNER.md` (unified
diff also at `research/convergence/h2/horizon_h2_correction.patch`). PR #29 itself
still carries the stale numbers until its owner applies that patch.

---

## Where the correction lives

The **official result is 726 pairs / 0 CONFIRMED / 0 REJECTED / 726 UNKNOWN**
(700 candidate + 26 hard negatives; S4 = 0). This integration branch carries the
corrected prose as a *forward correction* of PR #29's copy: the HORIZON source
branches (`research/horizon-001`, `foundation/atlas-001`) and public history are not
rewritten, and the exact source commit that needs the same patch is recorded as
`2dcdc995102f094d723005c79bb9b0ec7d9737f7`. PR #29 itself still carries the stale
712/387/325 numbers until its owner applies
`research/convergence/h2/HORIZON_PATCH_FOR_OWNER.md`; until then, the integration
branch and PR #29 disagree by design, and that disagreement is visible rather than
silent. The gate (`python tools/convergence/h2/check_h2_consistency.py`) is the
enforcement mechanism: it recomputes from `EXP_H2_PAIRS.jsonl` and fails on any
reintroduced stale number, so the stale state cannot ship as green again.

---

## 8. The consistency gate

`tools/convergence/h2/check_h2_consistency.py` (stdlib only, no third-party
imports, no network):

1. recomputes every count **from `EXP_H2_PAIRS.jsonl`** (`verdict`, `signal_set`,
   `signals`, `construction_rule`, unique `pair_id`s) — the summary JSON is never
   trusted;
2. compares the recomputed truth with `EXP_H2_SUMMARY.json` (top-level and
   `primary` blocks, per-signal sufficiency, construction rules, finding counters);
3. extracts the quoted numbers from the two prose files and compares each with the
   recomputed truth;
4. prints every mismatch with `file:line`, the quoted value and the truth; exit 0
   only if every check and every extraction passes; exit 1 on any mismatch or
   missing claim; exit 2 if an input cannot be read.

```
python tools/convergence/h2/check_h2_consistency.py
python tools/convergence/h2/check_h2_consistency.py --json
```

Observed on the **source state** (before the prose correction, recorded for the
record):

| command | observed |
|---|---|
| gate, human output | `39/75 passed, 36 mismatched, 0 extraction errors`; `RESULT: INCONSISTENT`; **exit 1** |
| gate, `--json` | `status=inconsistent, exit_code=1, checks=75, mismatches=36`; **exit 1** |

Observed on the **corrected integration branch** (current state):

| command | observed |
|---|---|
| gate, human output | `73/73 passed, 0 mismatched, 0 extraction errors`; `RESULT: CONSISTENT`; **exit 0** |
| gate, `--json` | `status=consistent, exit_code=0, checks=73, mismatches=0`; **exit 0** |
| `python -m pytest tests/convergence/test_h2_consistency.py -q` | 7 passed; **exit 0** |
| `python tools/convergence/h2/reproduce_h2.py` | 10/10 checks, byte-identical pair file; **exit 0** |

`research/convergence/h2/verify_corrected_prose.py` is the pre-application harness
used while the frozen files still carried the stale numbers: it splices the proposed
corrections into temporary copies and exits 0 against the real artifacts. It is kept
as a regression check on the proposed prose; on the corrected tree the real gate is
green without any splice.

The test suite proves the gate can detect errors, not merely run:

* passes on a consistent fixture;
* fails on a fixture whose documents quote `712 / 387 / 325 / 445 / 365 / 12`;
* fails when the summary contradicts the pair file (a lying summary);
* fails on duplicated `pair_id`s;
* `--json` contract and exit codes;
* no third-party imports in the gate.

Extraction is fail-closed: if a document loses a required claim shape (total pairs,
verdict table, per-signal S2/S3 fired, hard-negative count) the gate reports an
extraction error and exits non-zero rather than passing silently. After the prose is
corrected, keep those sentence/table templates so the gate can keep checking them.

---

## 9. Files written by this task

| path | purpose |
|---|---|
| `docs/convergence/H2_RECONCILIATION.md` | this report |
| `tools/convergence/h2/check_h2_consistency.py` | the gate |
| `tools/convergence/h2/reproduce_h2.py` | offline reproduction check (current code vs frozen summary) |
| `tools/convergence/h2/exp_h2_identity_local.py` | algorithm-identical copy with local loader |
| `tools/convergence/h2/_make_local_copy.py` | the transform that generated the copy |
| `research/convergence/h2/audit_pairs.py` | pair-file facts and the 712 arithmetic |
| `research/convergence/h2/analyze_claim_arithmetic.py` | internal-consistency proof of the stale table |
| `research/convergence/h2/verify_corrected_prose.py` | proof that corrected prose makes the gate green |
| `research/convergence/h2/explore_superseded.py` | S2 matcher sensitivity diagnostics |
| `research/convergence/h2/explore_tokens.py` | token-overlap diagnostics |
| `research/convergence/h2/_recovered/` | unreachable-blob evidence + scan programs + README |
| `research/convergence/h2/out/recomputed_pairs.jsonl`, `recomputed_summary.json` | local reproduction output |
| `research/convergence/h2/HORIZON_PATCH_FOR_OWNER.md` | ready-to-apply correction package (edit list, inline diff, instructions) for PR #29 / `research/horizon-001` |
| `research/convergence/h2/horizon_h2_correction.patch` | unified diff of the two corrected prose files |
| `research/convergence/h2/_edit_list.py` | regenerates the source-line before/after edit table |
| `tests/convergence/test_h2_consistency.py` | gate tests |

Two files under `research/horizon/**` were modified — only the two EXP-H2 prose
files, and only the numeric/rhetorical corrections listed in §7 — under an explicit
Lead authorisation for this integration branch. `medradar/atlas/**` was not modified.
No git ref, commit, merge or checkout was changed; nothing was committed.

---

## 10. Residual unknowns

1. **The exact superseded S2 implementation** that fired 445 times is not in the
   repository object database and is not deducible from the committed artefacts.
   We proved the *consequence* (387 = 347 S2∧¬S3 + 40 date contradictions, per the
   internal-consistency check) and that the current matcher cannot produce it, but
   the old code text remains unknown. We did not fabricate a reconstruction.
2. **Whether the stale run used exactly today's 320/174 inputs.** The stale table is
   arithmetically coherent and the prose states those exact inputs, but without the
   old code this cannot be independently re-run.
3. **Whether the stale run had any other pair-construction difference** beyond
   “no HN3”. The 712 = 700 + 12 identity and the prose naming only HN4 make this
   the only hypothesis consistent with all quoted numbers, but it is inference from
   the committed artefacts, not from recovered code.
4. **External exposure.** PR #29's body, issue comments and any out-of-repo copies
   could quote 712/387/325. This workstream is offline, so only tracked repository
   files were checked.
5. **Ordering of working-tree edits inside `18a7580`.** Git cannot order the prose
   draft against the script revision because both landed in one commit. The
   arithmetic and the unreachable patch scratch script show the final script/artefact
   were still being revised when the prose was already fixed, but the exact edit
   timeline is unknown.

### Exact non-recoverability of the superseded S2 matcher

The superseded S2 matcher source is **unrecoverable**, and 387/325 must be read as a
*reconstructed arithmetic result*, not as a recovered run:

* the only EXP-H2 implementation blob in the object database is the committed one,
  `d09ffd540be83f5d3d7cf278c3210eb1a923121c` (23,022 bytes);
* all 135 unreachable blobs were inspected: they contain three final-session scratch
  helpers (two summary inspectors and one script that adds the
  `hard_negative_rules_attempted` key) but **no candidate earlier matcher** and no
  earlier pair file (no unreachable blob lies in the 600–750 KB range an earlier
  726/712-row pair file would occupy);
* therefore the superseded code was never committed and cannot be recovered from this
  repository. We did not execute the superseded rule and did not fabricate a
  replacement: `387 = 347 S2∧¬S3 + 40 date contradictions` and `325 = 58 + 267` are
  identities derived from the stale table's own quoted numbers under the documented
  verdict rule, assuming the quoted `S2 = 445`; they are *reconstructed arithmetic*.
  The gate and the official result use the committed matcher (`S2 = 0`), never the
  reconstruction.

---

## 11. What would make this report wrong

* **An earlier `exp_h2_identity.py` (or an equivalent matcher) is found outside this
  repository's object database** — e.g. in a PR description, a saved transcript, or
  another machine — and it reproduces 445 S2 hits on these inputs. That would not
  change the official result (the committed protocol and code still produce
  726/0/0/726), but it would complete §4.3 and could change the *causal* wording
  from “unrecoverable” to “recovered”.
* **The frozen inputs are not the ones the committed run used.** Ruled out here by
  the blob hashes: the pairs/summary files are byte-identical to their `18a7580`
  blobs, and re-running the committed code on the frozen JSONL reproduces the pairs
  byte-for-byte.
* **The “official” result is defined as the prose rather than the reproducible
  artefact.** The task defines official as pre-registered rule + current code +
  frozen inputs, so this report would be wrong under the opposite convention. The
  disagreement itself would not disappear.
* **The pre-registered rule is interpreted differently** — e.g. as allowing
  `REJECTED` from name disagreement independently of S2, or as falling back to a
  looser model-token definition. That could yield a non-zero REJECTED count. This
  report deliberately does not retune the protocol; any such run must be labelled a
  new sensitivity analysis, not the official result.
* **A later commit regenerates `EXP_H2_PAIRS.jsonl` with different code** but leaves
  the summary/prose untouched. The gate would catch the summary/prose side; this
  report's byte-identity evidence pins the current state only.
* **The gate's extraction templates are changed without changing the prose.** The
  gate would then report missing claims (fail-closed), not a pass; a pass on
  fixtures still requires the quoted numbers to equal the recomputed truth.
