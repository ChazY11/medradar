# Cycle 40 — count the store before calling anything blocked; versioned taxonomy (2026-11-03)

**Status:** completed. Closes B-073. Decision: D-071.
Artifacts: `experiments/b073/lane_inventory.json`, `medradar/intelligence/taxonomy.py` (+10 tests),
`experiments/b027/profiles.json` (taxonomy stamp), repaired `research/BACKLOG.yaml`.

## The plan I was about to carry out, and why it was wrong

The previous cycle's next action was to reclassify backlog items whose data is "structurally unavailable" as blocked.
That is exactly the move the programme already retracted once: D-029 recorded a "coverage too thin" conclusion that
turned out to be a pagination bug in our own collector. **So the count came first.**

## What the count found

| table | rows | items that need it |
|---|---:|---|
| events | 55,090 | B-029, B-032, B-037 |
| financial_facts | 43,420 | B-018, B-021 |
| market_bars | 95,725 | B-018, B-021 |
| publication_counts | 616 | B-018, B-021, B-041 |
| procurement_awards | 3,453 | B-021 |
| company_identifiers | 34 | B-014, B-029 |
| horizon_forecasts | 25 | B-015 |

**The financial, market and publication data that five "todo" items need is present.** Marking them blocked would have
been a second self-inflicted falsehood. They stay open with the row counts recorded as notes so the next reader does
not redo the inventory.

**What is genuinely blocked, and why it is not about data:** B-014 needs a **human-adjudicated** labelled sample and
its own criterion forbids AI-created fixtures; B-015 waits on wall clock (2027-10); B-030/B-031 on external access.
**B-028 is now done** (contradictory evidence is a required profile field, 51 of 53 companies carry it).

## B-032 shipped rather than discussed

`medradar/intelligence/taxonomy.py` gives the taxonomy a **version** (`tracks_device_2026-11`), an **effective date**
(`2026-11-03`) and SHA-256 **fingerprints of both mapping files**, so a product-code remap is visible as a regime
change even if nobody remembers to bump the version. `profiles.json` now carries the regime; `regime_changed()` and
`compare()` report comparability; ten tests cover fingerprints, stamping and change detection.

## A process defect found while doing this

My first backlog edit inserted the `notes:` lines after the section comments instead of inside their items, and the
unquoted prose contained colons — the YAML became unparseable and the objective audit failed with
`could not parse BACKLOG.yaml`. Both were repaired. The lesson is the standing one: a text-formatting change to a
machine-read file needs the parser run before the commit, and the audit plus gate both check it — which is why the
defect died in the same cycle.

## Verification

- `python tools/audit_objectives.py` → **11 PASS / 0 FAIL / 1 N/A**; backlog: 60 tasks, no duplicate ids.
- `python -m pytest tests/test_taxonomy.py` → **10 passed**.
- `python tools/round_end.py` → **10 steps, 0 failures**.
- `profiles.json` carries `taxonomy.version`, `effective_from`, both fingerprints.

## Not claimed

That the remaining open items are cheap. They are analyses with real work in them. What this cycle establishes is only
that **their data exists**, so their absence from the results is a scheduling fact, not a data-availability one.
