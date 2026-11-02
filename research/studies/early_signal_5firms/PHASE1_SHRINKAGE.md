# PHASE 1 SHRINKAGE REPORT — what public data cannot answer here

**Study:** `early_signal_5firms` · **Gate:** G1 (frozen in `PHASE1_PROTOCOL.md`) · **Verdict: NO-GO for a lead-time
study** · **Commits:** earlier-source audit and probe on `research/early-signal-5firms`

> This is a **negative finding about public data**, not a failure of the study. It was obtained by running the
> pre-registered probe, not by asserting a limitation. The coverage and time audits stand; the lead-time question
> cannot be answered on this corpus.

---

## 1. The gate, and its outcome (numbers from `LEAD_LAG_PROBE.json`)

| scope | definition | eligible pairs (lag 0 / 30 / 60 / 90 d) | firms |
|---|---|---:|---:|
| **S1 primary** | trials on the study's device tracks (`imaging_us`, `respiratory`) | **0 / 0 / 0 / 0** | 0 |
| **S2 sensitivity** | assumed crosswalk `t_respiratory → respiratory` | **3 / 3 / 3 / 3** | 2 |
| **S3 descriptive** | firm level, any trial → next clearance | 0 (see §3) | 0 |

Frozen G1 floor: **≥10 eligible pairs across ≥2 firms**. Best scope reaches **3 pairs**, so **G1 = NO-GO**.

## 2. Why S1 is zero — a taxonomy gap, not a data shortage

The store holds **55,592** clinical trials and **375,378** regulatory events. But:

- trial records are assigned **therapy-area** tracks (`t_*`: 22 of them, e.g. `t_respiratory`, `t_oncology`);
- the study's confirmatory tracks are **device** tracks (`imaging_us`, `respiratory`);
- only **four** therapy-area ids have an id-identical device counterpart (`t_respiratory`, `t_ophthalmology`,
  `t_urology`, `t_womens_health`), and only one of those (`t_respiratory`) touches a confirmatory track;
- on the device tracks themselves, the number of trials with a firm and track is **zero**.

So the limiting factor is **the absence of a therapy-area → device-track crosswalk**, not the absence of trials.
Building one is a taxonomy task that requires human adjudication, and building it *after* seeing outcomes would
violate the pre-registration.

## 3. Why S3 is not a rescue

At firm level every trial is followed almost immediately by some clearance:

| firm | trials | regulatory events | eligible pairs | pairs below the 2-quarter floor | multiplicity skipped |
|---|---:|---:|---:|---:|---:|
| medtronic | 113 | 4,947 | 0 | 112 | **303,942** |
| ge_healthcare | 35 | 229 | 0 | 34 | 3,774 |
| philips | 59 | 271 | 0 | 59 | 9,577 |

With thousands of clearances, the "next event after a trial" is usually days away. **Firm-level pairing therefore has
almost no discriminative power**: it produces a near-certain match regardless of whether a real technology change
exists. The 303,942 skipped follow-on events for Medtronic are the measurement of that ambiguity.

## 4. What this establishes (and does not)

**Establishes, with numbers:**
- SEC 8-K is unusable at cell level in this store: **1,360 of 20,976** records carry a `company_key`, about **5 per
  firm** in the window, and none carries a technology track.
- The trial lane cannot be joined to the device tracks without a reviewed crosswalk; the join is not merely sparse,
  it is **structurally absent**.
- Even the one id-identical crosswalk yields far too few pairs (3) to estimate a lead-time distribution.
- The pre-declared lag sensitivity does not change the decision at ±30/±60/±90 days — not because the result is
  robust in a good sense, but because the counts are too small for lag to matter.

**Does not establish:** that public data can never give early warning — only that **this corpus, with this taxonomy,
at this granularity, cannot measure it**. That distinction is the finding.

## 5. What can still be done, in order of cost

| option | what it would answer | cost | blocker |
|---|---|---|---|
| **O1 Concurrent detection** (shrink the question) | at equal false-alarm budget, does multi-source evidence identify a change *as it happens* more reliably than one source? | low: the pilot's design already fits, positives must become sustained changes | none agent-side |
| **O2 Reviewed trial crosswalk** | whether therapy-area trial activity precedes device-track clearance activity | medium: a keyword/rules crosswalk validated on a labelled sample | needs human adjudication of the mapping |
| **O3 External earlier source** | whether anything precedes regulatory activity (patents, standards bodies, procurement) | high | patents blocked (access), procurement Tier C (dates NULL) |
| **O4 Firm-level descriptive study** | ordering of sources within a firm | low but weak: see §3, no discriminative power | — |

## 6. Recommendation

Run **O1** next: it is the only question this corpus can answer with credible statistics, and it directly tests the
directive's fusion hypothesis (H1) even though it cannot test lead time (H2). Report the lead-time question as
**unanswerable on this corpus**, with the evidence in §2–§3, rather than diluting it into a proxy.

## 7. Reproduction

```bash
python experiments/b084/earlier_source_audit.py    # source tiers, taxonomy gap, per-firm counts
python experiments/b085/lead_lag_probe.py          # the three scopes and the G1 verdict
python -m pytest tests/test_study_pairing.py -q    # 14 tests for the pairing logic
```
