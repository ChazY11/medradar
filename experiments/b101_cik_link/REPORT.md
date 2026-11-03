# B-029 — CIK-based deterministic linking for the 8-K lane (b101)

Worktree `D:\DEPPSKK\worktrees\es-ai-review`, branch `research/early-signal-ai-review`.
Inputs pinned: `data/medradar.sqlite` sha256 `445807cab60df66e…`, `data/research.sqlite`
sha256 `dd241bfec138d797…` (the latter matches the digest in `config/universe_v1.json`).
The store was opened with `sqlite3.connect("file:…?mode=ro", uri=True)` and is byte-identical
after the run; nothing is written back into it.

## Headline

**0 new links.** All 19,616 unlinked 8-K events do carry a payload CIK, but **none of those
CIKs equals the CIK of a curated roster company**, so the exact-equality rule has nothing to
join. B-029's acceptance ("19,616 unlinked CIK-bearing 8-K events become linked") rests on a
premise that the store does not support, and I have not manufactured links to meet it.

What the run *does* establish: 826 of the 1,360 existing 8-K links are independently
corroborated by exact CIK, **0 contradict**, and the 57-entry curated CIK registry is
committed and reproducible.

## The rule implemented (and nothing else)

An event links iff `normalise(payload.cik)` is an integer that appears in the committed curated
CIK registry **and maps to exactly one curated `company_key`**. CIKs whose evidence names two
company keys are refused and counted. No applicant name, alias, token or similarity is read
when deciding; name-token overlap is computed afterwards and reported as descriptive only.
See `link_cik.py::resolve_events` and `tests/test_cik_link.py::ResolveRuleTests`
(a "MEDTRONIC INC" event with an uncurated CIK must not link; a curated CIK with a completely
unrelated applicant string must link).

## Measured funnel

| step | events | notes |
|---|---:|---|
| `sec_edgar_corpus` 8-K events | 20,976 | 1,613 distinct payload CIKs |
| … with `payload.cik` present | 20,976 | 100%; every payload has `cik` and `accession` |
| … already carrying `company_key` | 1,360 | pre-existing lane links |
| … unlinked | 19,616 | matches the backlog figure |
| … unlinked with a payload CIK | 19,616 | 1,530 distinct CIKs, 1,888 distinct `applicant_raw` |
| CIK exactly equals exactly one curated CIK (all events) | 826 | all 826 are already linked |
| CIK ambiguous — maps to >1 curated `company_key` | 35 | one CIK (`0000200406`, ticker JNJ) |
| CIK not in the curated registry (all events) | 20,115 | 19,616 unlinked + 499 unverifiable links |
| **newly linked by this run** | **0** | |
| unresolved: no CIK / ambiguous / not curated | 0 / 0 / 19,616 | `unresolved_reasons` in `link_report.json` |

Existing-link audit: **826 corroborated**, **0 contradicted**, **35 excluded as ambiguous**,
**499 unverifiable** because their company has no curated CIK evidence (57 of 89 roster
companies are covered).

## The curated CIK registry (`cik_registry.json`, committed)

Built by `--rebuild-registry` from two offline sources only, with exact equality at every hop:

1. `research.sqlite.company_identifiers` — 34 rows, 34 device companies. **The scheme is
   `SEC_CIK`, not `cik`**, and the source is `sec_company_tickers` (`confidence=1.0`).
2. The SEC-reported registrant ticker on the local EDGAR candidate dumps
   (`data/edgar_corpus/candidates.jsonl` sha256 `e393156e…`, `candidates_v2.jsonl` sha256
   `9c84cb74…`, 27,985 rows): CIK→ticker from the search response, joined to a curated ticker
   **only when the ticker exactly equals exactly one roster ticker**. This adds 24 roster
   companies that the identifier table does not cover (49 of the 57 have ticker evidence;
   33 have identifier evidence).

Union: **57 CIKs → 57 companies** (1:1). Refused as ambiguous: `0000200406` because ticker
`JNJ` denotes both `jnj_pharma` and `johnson_johnson_medtech` — this is what the acceptance
means by "CIK maps to >1 company key"; 35 existing links are therefore excluded from
corroboration. 32 of the 89 roster companies have no curated CIK evidence from either source.

## Precision check (deterministic, seed 20261103)

Sample 60 of the 826 CIK-anchored links (`random.Random(20261103).sample` over event ids):
60/60 CIK in registry, 60/60 map to exactly one curated company, 60/60 not ambiguous, 60/60
`company_key` matches the registry; 17/17 cross-checked against the raw
`company_identifiers` table agree; 0 failures → `PASS`. Descriptive name-token overlap with
`applicant_raw`: 60/60 (reported, never used). **No new links exist to spot-check**, because
the count of new links is 0 — the spot-check therefore audits the CIK rule against the
existing lane, which is the strongest precision statement the data permits.

## What did not link, and why

- **19,616 events / 1,530 CIKs / 1,888 applicants are outside the curated roster.** Top
  registrants by volume: Tonix Pharmaceuticals (264), Aerie Pharmaceuticals (193), Axsome
  Therapeutics (133), Lipocine (128), Aquestive Therapeutics (123). The store has no
  `company_key` for these registrants; creating one is a roster decision, not a CIK join.
- **58 events are a deliberate near-miss exclusion** (38 Pfizer, 9 Amgen, 9 Novartis,
  2 Stryker). Their CIKs belong to acquired registrants, not to the parent: Seattle Genetics
  `1060736`, Horizon Pharma `1492426`, Chinook/Aduro `1435049`, Tornier/Wright Medical
  `1492658`. The only evidence tying those CIKs to the parent is name/M&A knowledge
  (`SEAGEN`, `HORIZON THERAPEUTICS`, `CHINOOK`, `WRIGHT MEDICAL` aliases), which B-029 forbids.
  **Trap found before implementation:** the local `corpus_v2.jsonl` ticker field is
  name-resolved, so using it as CIK→ticker evidence would have emitted 58 "confidence 1.0"
  links that are not CIK links at all. The registry builder therefore reads only the
  pre-resolution candidate dumps; `tests` plus this note make the exclusion explicit.

## Data-quality surprises

1. **`companies.cik` is empty in every store** — 0/89 in `medradar.sqlite`, 0/51 in
   `research.sqlite` (and in the dev stores). The column the backlog points at is dead; the
   only CIK evidence in-repo is `research.sqlite.company_identifiers`.
2. **The identifier scheme is `SEC_CIK`, not `cik`**, and it covers 34 device companies only —
   no drug-roster CIKs were ever ingested.
3. **A CIK is a registrant id that survives mergers.** CIK `1492658` is Tornier N.V. in
   early-2015 filings and Wright Medical Group N.V. in later filings; `1492426` is Horizon
   Pharma and later Horizon Therapeutics. CIK equality therefore cannot be time-blindly
   interpreted as "same corporate group".
4. The corpus's own ticker field is not SEC-reportable evidence for pre-resolution events
   (point above); it must not be used for identity work.

## Honest limits

This links **legal-entity identity of the filing registrant by CIK** — not event relevance,
not corporate-group membership, and not a time-invariant identity. It covers 57/89 roster
companies; the `events_linked.jsonl` artifact is a *proposal* generated from the read-only
store (nothing was written into the store). The 58 excluded acquired-registrant events are
arguably product-relevant but cannot be linked under a no-name rule.

## Files

| file | role |
|---|---|
| `experiments/b101_cik_link/link_cik.py` | stdlib-only deterministic linker + registry builder |
| `experiments/b101_cik_link/cik_registry.json` | committed curated CIK→company input, with provenance/sha256 |
| `experiments/b101_cik_link/link_report.json` | full funnel, ambiguity, data-quality, precision audit |
| `experiments/b101_cik_link/events_linked.jsonl` | 826 CIK-anchored mappings at `confidence=1.0` (regenerable, **not committed by me** — the Lead commits) |
| `tests/test_cik_link.py` | 33 tests |

`events_linked.jsonl` is regenerable from committed code + the local stores; it is 826 rows
because it contains every CIK-anchored link (all `link_status=existing_corroborated`; new links
would be `link_status=new`). `cik_registry.json` is committed because rebuilding it needs
`data/edgar_corpus/`, which `data/` being gitignored keeps out of git.

## Reproduction

```
python experiments/b101_cik_link/link_cik.py
python -m unittest tests.test_cik_link          # 33 tests, OK
# byte-identical re-run: link_report.json sha256 C21341CF1B2874872ACA17C15FF23BBD05C1…,
# events_linked.jsonl sha256 B1AA5528A97D8858F847F8CAD07C2F71B093… (same before/after)
# registry rebuild (needs the local EDGAR corpus; not portable):
python experiments/b101_cik_link/link_cik.py --rebuild-registry
```

## Recommendation to close B-029

Restate the acceptance to what a CIK join can actually guarantee: *every unlinked 8-K event
whose payload CIK equals a curated company CIK is linked* — today that set is empty, and the
826 curated-CIK events in the lane are already linked and now CIK-verified. The 19,616
remaining events need **roster expansion** (or acceptance that 8-K catalysts stay outside the
observed universe), not a better CIK join; populating `companies.cik` alone would not change
this result because the unlinked registrants are not in the roster.
