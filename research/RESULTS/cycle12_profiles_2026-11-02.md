# Cycle 12 — Understand layer: seven-field company technology profiles (2026-11-02)

**Status:** completed. Closes B-027. Decision: D-032.
Artifacts: `medradar/intelligence/profile.py`, `tests/test_profile.py` (34 tests),
`experiments/b027/profiles.json`, `experiments/b027/profiles/*.md`, `experiments/b027/selfcheck.py`.

## What was built

The first Understand-layer deliverable of the programme: a pure, unit-tested engine that turns
already-held evidence (regulatory filings with tracks and product codes; device trials) into a
company technology profile with **exactly seven required fields**:

1. `identity` — company, resolved entities, as-of, coverage window, sources
2. `technology_footprint` — per-track counts, first/last dates, shares, sufficiency
3. `momentum` — last 24 months vs the 24 before, direction and numbers
4. `concentration` — top-track share and HHI
5. `independent_corroboration` — trial support per track, and explicitly where it is absent
6. `contradictory_evidence` — the checks run and what they found against the reading
7. `limits_and_provenance` — sources, window, what would change the conclusion

## The three design rules

- **No scores.** Every statement is generated from the numbers in the same structure, so prose cannot
  drift from evidence; a single number would hide the evidence and invite ranking.
- **Contradictory evidence is structural.** Field 6 must list the checks run and the findings (even if
  none). `validate_profile` rejects a profile without it and `render_markdown` refuses to render it.
  The programme's repeated failure mode was a positive reading surviving because nobody looked for its
  contradiction — this makes that omission a schema error.
- **Degrade honestly.** No trial support, no hiring board, sparse months: each is said in the profile
  rather than dropped or scored zero.

## Generated profiles (all five mandated deep cases)

| company | events | tracks | momentum | trial-supported tracks | contradictions |
|---|---:|---:|---|---:|---:|
| Medtronic | 299 | 24 | rising (90 vs 66) | 14 / 24 | 2 |
| GE HealthCare | 274 | 5 | stable | — | 0 |
| Philips | 224 | 11 | rising | — | 1 |
| Dräger | 16 | 2 | stable | — | 1 |
| Mindray | 82 | 3 | rising | — | 1 |

Dräger's profile is thin (16 events, 2 tracks) and says so; GE HealthCare's four checks found no
contradiction and the profile says that too, rather than manufacturing balance.

## Verification

`experiments/b027/selfcheck.py` re-derives every number the Markdown states from the JSON (footprint
rows, totals, contradiction statement, entity count), checks all seven headings, and confirms
rendering is deterministic: **5 of 5 profiles pass**. `python -m medradar selftest` is now **829 tests,
OK (skipped=3)**.

## Why this matters for the mission

The programme has spent nine cycles on the Observe layer and has zero surviving positive findings. The
Understand layer is where "what does this mean for the company's technology position" is supposed to
be answered — and it can be answered *without* a positive association result, because it assembles
what is already evidenced and states explicitly what is missing. This is also the first part of the
system that a human analyst could use without reading the code: the profile names its sources, its
window, its contrary observations and the conditions under which its reading would fail.

## Limits that carry forward

Profiles are only as good as the lane: ~0.2 events per cell-month, taxonomy not versioned by effective
date, entity resolution table-driven, trial lane sparse. Those are stated inside every profile rather
than in a global disclaimer.
