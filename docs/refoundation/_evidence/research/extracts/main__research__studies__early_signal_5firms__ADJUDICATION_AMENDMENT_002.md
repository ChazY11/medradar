# AMENDMENT 002 — agent pre-adjudication of the 69 packets (not human truth)

**Status:** FROZEN before the rubric was applied · **Authorisation:** project owner, 2026-11-03
("69 份证据包的你来裁决" — the owner instructed the agent to adjudicate the packets) ·
**Amends:** `LABELING_PROTOCOL.md` §1 and §2

---

## 1. What the owner asked, and what this amendment does about it

`LABELING_PROTOCOL.md` §1 states that the agent may not assign labels, and every packet carries
`human_review_status = PENDING_HUMAN_REVIEW` with `final_label = null`. The owner has now instructed the agent to
adjudicate all 69 packets. Rather than either refusing outright or quietly breaking the rule, this amendment creates a
**third tier** that did not exist before:

| tier | produced by | may be called human truth | may be used to score the study's detectors |
|---|---|---|---|
| `PENDING_HUMAN_REVIEW` | nobody yet | — | no |
| **`AGENT_PRE_ADJUDICATION`** (new) | the agent, by a deterministic rubric | **no** | **no** |
| human adjudication | a named reviewer | yes | yes |

The new tier records a **preliminary label** in a separate field (`agent_preliminary_label`) with
`label_authority = "agent_rubric_v1"`. It leaves `human_review_status` and `final_label` untouched. Nothing in the
study may be scored against it: an agent-produced label would make the evaluation circular, which is precisely the
failure the programme retracted before (a post-hoc nomination evaluated on the data that produced it).

## 2. The rubric (fixed now, before it is applied)

Three checks, each computed from committed evidence only:

**R1 — device relevance.** The packet's trial text (`conditions` + `brief_title` from the store payload) must contain
the tokens of the assigned track's keywords. Score: `STRONG` if ≥1 full keyword phrase matches; `WEAK` if only single
tokens match; `NONE` if neither.

**R2 — taxonomy consistency.** The packet's product code (candidates) must map to the same track in the store's
`product_codes` table, or the clearance's track assignment must equal the packet's track (small-sample packets, where
the clearance id is synthetic and the assignment came from the same store). Score: `CONSISTENT` / `INCONSISTENT` /
`UNKNOWN` (no product code and no checkable mapping).

**R3 — third-source support.** Small-sample packets only, from `CASE_PACKETS_SMALL_SAMPLE_V2.json`:
`NEAR_SUPPORT` if status `SUPPORTED_BEFORE` and distance class `NEAR`; `DISTANT_SUPPORT` if `SUPPORTED_BEFORE` and
`DISTANT`; `AFTER` if `AFTER_CLEARANCE`; `AMBIGUOUS`; `NO_RECORD`. Candidates have no third source: `NOT_CHECKED`.

**Rule table (applied in order, first match wins):**

| condition | preliminary label |
|---|---|
| R1 `STRONG` and R2 `CONSISTENT` and R3 `NEAR_SUPPORT` | `Confirmed Shift (agent-preliminary)` |
| R1 `STRONG` and R2 `INCONSISTENT` | `False Signal / No Confirmed Shift (agent-preliminary)` |
| R1 `NONE` | `False Signal / No Confirmed Shift (agent-preliminary)` |
| R1 `STRONG` and packet stratum `routine` | `Routine Iteration (agent-preliminary)` |
| R1 `STRONG` and R2 `CONSISTENT` and R3 in {`DISTANT_SUPPORT`, `AFTER`, `NO_RECORD`, `AMBIGUOUS`} | `Uncertain (agent-preliminary)` |
| R1 `WEAK` | `Uncertain (agent-preliminary)` |
| R2 `UNKNOWN` and R1 `STRONG` | `Uncertain (agent-preliminary)` |

No packet may receive `Insufficient Observation` from the rubric: every packet refers to a historical event whose
observation window is already complete.

## 3. What the resulting numbers mean

- They describe **how a fixed text/mapping rubric classifies 69 packets**, not how a human would.
- They are **not** evidence about the detector, the fusion hypothesis or lead time; using them that way would be the
  circularity this programme already retracted once.
- They are **not** a Target B dataset. Until a named human re-adjudicates, the study has zero Target B labels, and the
  papers continue to say so.

## 4. Disclosure obligations

Every artifact carrying an `agent_preliminary_label` must state, in the same document: the tier, the rubric version,
and the prohibition in §3. The packets' own `human_review_status` stays `PENDING_HUMAN_REVIEW`; a reader who only opens
the packet sees the human boundary, not the agent's opinion.
