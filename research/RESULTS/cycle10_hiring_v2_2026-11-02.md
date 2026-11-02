# Cycle 10 — hiring lane: a collector bug corrected, coverage tripled, verdict still pending (2026-11-02)

**Status:** completed. **Corrects** cycle 9's coverage conclusion. Evidence: `experiments/b030/`
(`host_depth.json`, `hiring_panel_v2.json`, `lag_analysis_v2.json`, generated `REPORT.md`).
Decisions: D-030.

## What was wrong

Cycle 9 concluded that the Wayback hiring proxy covered only 2 usable companies because of **archive
depth**. That was wrong, and wrong because of my own collector: it combined `collapse=urlkey` with
`limit` + `page` pagination, a combination that **does not page** on this endpoint. Every query
silently returned one capped page, hiding most of the archive.

## What a direct measurement shows

One generous request per host:

| host | posting URLs | months | months with ≥5 postings |
|---|---:|---:|---:|
| `jobs.bostonscientific.com/job/*` | 4,999 | 123 | 100 |
| `jobs.medtronic.com/job/*` | 4,984 | 46 | 29 |
| `jobs.bd.com/job/*` | 4,672 | 66 | 44 |
| `careers.stryker.com/*` | 3,878 | 39 | 28 |
| `abbott.taleo.net/careersection/*` | 579 | 34 | 15 |
| `dexcom.wd1.myworkdayjobs.com/*` | 767 | 31 | 16 |
| `careers.intuitive.com/job/*` | 532 | 18 | 8 |

## Corrected coverage

The rebuilt panel covers **11 companies with posting URLs**, 6 with ≥24 months, 9 with ≥50 postings —
against 2 usable companies in cycle 9. Four firms hit the per-host cap, so their series are lower
bounds. Five firms still return nothing under the probed hosts: Philips, Dräger, Mindray, Zimmer
Biomet, Masimo — **including two of the five mandated focus companies**.

## The verdict is still pending, and says so

Under the **unchanged** pre-declared usability floor, **3 companies** are usable (`bd`,
`boston_scientific`, `stryker`). The pre-registered lag profile is committed; every value sits inside
its null band, and the uniformly negative sign is uninterpretable because the proxy counts only
archive-captured postings, so capture gaps can align with regulatory gaps.

So the association question remains **unrun**, not answered. What changed is the blocker's identity:

| cycle 9 said | cycle 10 measured |
|---|---|
| archive depth is insufficient | depth is ample; **power** (3 companies) and **board discovery for 5 firms** are the limits |
| 2 usable companies | 6 with ≥24 months, 9 with ≥50 postings |
| — | collector truncation is now recorded per host instead of hidden |

## Why this correction matters as much as a finding

A negative conclusion about data availability is as falsifiable as a positive scientific claim, and
the same discipline applies: when a measurement says "the data is too thin", the measurement itself
must be checked before the conclusion is carried forward. This is the second self-retraction of the
programme (D-025 was the first: 79 % of "entries" were entity appearances). Both came from testing a
claim against an alternative explanation, not from new data — which is the behaviour the mission's
"failure is a result" rule is supposed to produce.

## Next

1. **Board discovery for the five uncovered firms** (B-048) — two are mandated focus companies, so
   this is also a mission-compliance issue, not only a statistical one.
2. Re-run the pre-registered lag test once enough firms clear the floor, floor unchanged.
3. In parallel, the Understand-layer deliverable (B-027 company technology profile), which does not
   depend on a positive association result.
