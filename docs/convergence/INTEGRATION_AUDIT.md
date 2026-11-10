# INTEGRATION_AUDIT — CONVERGENCE-001

What was integrated, from exactly which commits, by what method, and what was
deliberately left out. Every claim here was checked against the live repository at
the start of this work, not against a stored snapshot.

## 1. Verified repository state (Phase 0)

| ref | commit | state at audit time |
|---|---|---|
| `main` | `b2a14c0a92332c004445de686daee97754cf94cb` | base of both PRs |
| PR #28 `foundation/atlas-001` | `c63683631a1b277e2d27cfbe3adf6e133cf55e83` | open, **draft**, `mergeable=clean`, +18,648 / −0, 70 files |
| PR #29 `research/horizon-001` | `2dcdc995102f094d723005c79bb9b0ec7d9737f7` | open, **draft**, `mergeable=clean`, +692,975 / −0, 691 files |

The three commits match the historical baseline quoted in the brief exactly, so
no rework had to be reconciled. `git fetch --prune` was run and both PR heads were
re-read from the GitHub API rather than trusted from the brief.

Both PRs share the same merge base (`b2a14c0`), which is what makes a **selective**
integration possible without either branch depending on the other.

## 2. Why this is a selective import and not a merge of the two PRs

The instruction "do not merge the two complete PRs just because GitHub says
mergeable" turns out to be substantively right, for a reason GitHub's mergeability
check cannot see:

- PR #29 commits **6,234,301 bytes across 30 paths derived from UN Comtrade**,
  which its own manifest marks `licence_status=terms_restricted`. UN Comtrade
  §5 prohibits redistribution and publication of *any* material without prior
  written permission. Merging that PR would publish those bytes on `main`.
- A plain `git merge` of both branches would therefore have satisfied "mergeable"
  while creating a licence violation on the default branch.

So the integration branch introduces the **bytes of both branches minus the
restricted material**, with provenance recorded in the commit message of each
import:

| import commit | source | files |
|---|---|---|
| `76a7403` | ATLAS-001 @ `c636836` (full merge, no exclusions needed) | 70 |
| `3c3a295` | HORIZON-001 @ `2dcdc99`, selective | **661 of 691** |

30 HORIZON paths were **not** introduced:

- `exports/horizon-2026-11-10/un_comtrade.jsonl` + `.sha256`
- `experiments/industry/evidence/un_comtrade.jsonl`
- `DATASETS/industry/un_comtrade/summary.json`
- 26 files under `DATASETS/industry/un_comtrade/raw/`

Retained as licence evidence (no trade values): the archived
`comtrade_license.html` and `terms_of_use.html`, `PROVENANCE.json`, and
`registry/sources/un_comtrade.json`.

Two further remediations were applied to the imported tree, because the payload
quarantine alone did not make the artefact compliant (see
`LICENCE_AND_SECURITY_REVIEW.md`):

- **Derived Comtrade values redacted** from `reports/INDUSTRY_DATA_REPORT.md`
  (five China import cells plus an exact cell value and the exchange rate derived
  from it) and from `experiments/industry/EXP_H4_INDUSTRY.json`. A derived number
  is still redistribution under §5.
- **Three raw UK OCDS award packages removed** (3,912,347 bytes) because they
  vendor 248 named individuals' work e-mail addresses that the derived export does
  not need.

## 3. Scope separation between the two workstreams

The two branches are cleanly disjoint, which is why the integration does not need
to resolve semantic conflicts — only a licence conflict:

| area | ATLAS (PR #28) | HORIZON (PR #29) |
|---|---|---|
| code | `medradar/atlas/**`, `tools/*atlas*`, `tests/test_atlas_*` | `research/horizon/{CONNECTORS,hz,tools}/**` |
| data | reports + one bounded sample under `research/atlas/**` | `research/horizon/{DATASETS,exports}/**` |
| docs | `docs/atlas/**` | `research/horizon/*.md` |
| CI | `.github/workflows/atlas.yml` | none for HORIZON |
| shared files | `README.md`, `.gitignore` (additive hunks only) | `research/horizon/.gitignore` |

No file outside those sets is modified by either branch, so the integration's own
surface is additive: `medradar/integration/**`, `tools/convergence/**`,
`config/convergence/**`, `docs/convergence/**`, `tests/convergence/**`,
`research/convergence/**`, `.github/workflows/convergence.yml`.

## 4. What the integrated system actually reads

The pipeline consumes the **versioned HORIZON evidence export**, not HORIZON's
loose datasets, so every imported byte is bound to a declared SHA-256:

```
research/horizon/exports/horizon-2026-11-10/
  MANIFEST.json                 24 declared sources, 6,492 records, 20,335,003 bytes
  <source>.jsonl                one file per source
  <source>.jsonl.sha256         sidecar digest
```

Integrity result on the integration branch:

<!-- convergence:numbers
declared_sources=24
declared_records=6492
integrity_verified=23
integrity_quarantined=1
integrity_mismatch=0
permitted_records=608
-->

`un_comtrade.jsonl` is **declared by the manifest but absent by design**; the
pipeline classifies it as `quarantined_absent` rather than reporting a missing
file, and never silently pretends the export is complete.

ATLAS's own research database (`research/atlas/staging/atlas.sqlite`) is **not**
touched or imported. It is read-only evidence used by the identity workstream, and
the integration writes to a brand-new database at
`research/convergence/staging/convergence.sqlite`.

## 5. Guarantees about the source branches

- `foundation/atlas-001` and `research/horizon-001` were **not modified**: no
  commit, no force-push, no history rewrite.
- `main` was **not modified**.
- PHOENIX frozen experiment branches were not touched.
- No automatic merge was performed anywhere. The integration branch is unpushed
  work until it is offered as a draft PR.
- The two prose files corrected in this branch (`EXPERIMENT_RESULTS.md`,
  `REGULATORY_FRONTIER_REPORT.md`) are corrected **only in this branch**; the
  identical patch is prepared for the HORIZON owner in
  `research/convergence/h2/HORIZON_PATCH_FOR_OWNER.md`. PR #29 still carries the
  stale numbers until the owner applies it.

## 6. Conflicts found and how they were handled

| conflict | kind | resolution |
|---|---|---|
| UN Comtrade bytes in PR #29 | licence | excluded from the import; quantified; owner decision documented, not executed |
| Derived Comtrade values in prose | licence | redacted with a visible note; values not restated anywhere |
| 248 named buyers' e-mails in raw OCDS | privacy | three raw packages removed; derived export unaffected |
| EXP-H2 prose vs machine artefact | science | artefact is authoritative; prose corrected; gate added so it cannot drift again |
| `records.jsonl` record-id collisions (62) | data quality | versioned rather than dropped; measured in EXP-C3 |
| `temporal_note` "not a publication date" | semantics | publication clock refused rather than assumed |

## 7. Known integration limits

- The HORIZON export is a **bounded sample**, not a census: 6,492 declared records
  across 24 sources. Conclusions are sample-scoped.
- Only **23** of the manifest's 24 sources are usable; the restricted one is
  excluded by design.
- ATLAS's local collection cache (220 MB MDALL table) is gitignored and therefore
  **not** part of the integration artefact; identity results that depend on it are
  bound to frozen hashes in `IDENTITY_RECONCILIATION.md` instead.
- No source in the corpus carries a corporate-history record, so "current group
  ownership" and "acquisition date" are explicitly **not** answered by the
  integrated data (see `KNOWLEDGE_GRAPH_DEMO.md`).

## 8. Reproduce this audit

```bash
git -C <repo> rev-parse origin/main origin/foundation/atlas-001 origin/research/horizon-001
python tools/convergence/licence/licence_gate.py \
  --export-dir research/horizon/exports/horizon-2026-11-10 \
  --policy config/convergence/licence_policy.json
python tools/convergence/run_integration.py --fresh --run-id audit_repro
```

The audit's machine evidence is `research/convergence/licence/gate_integration_branch.json`,
`research/convergence/licence/pr29_exposure.json` and
`research/convergence/reports/integration_audit_repro.json`.
