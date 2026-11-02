# REPRODUCIBILITY — how to re-run Phase 0 of `early_signal_5firms`

All programs are stdlib-only Python, read the frozen stores **read-only**, and write only under
`research/studies/early_signal_5firms/` or `experiments/b08*/`. No network access, no credentials, no paid services.

---

## 1. Environment actually used

| item | value |
|---|---|
| interpreter | Python 3.12 (system) |
| OS | Windows (driver: PowerShell 7) |
| runtime dependencies | **none** (core package declares `dependencies = []`) |
| working tree | `D:\DEPPSKK\worktrees\study-early-signal` (branch `research/early-signal-5firms`) |
| store (read-only) | `D:/DEPPSKK/medradar/data/medradar.sqlite` — 1.37 GB, 375,378 events |
| secondary store | `data/research.sqlite` (junction to the curated lane), `data/b040_device_trials.sqlite` |
| system clock at run | local `2026-11-03T01:14+08:00` / UTC `2026-11-02T17:14Z` (see clock audit) |
| randomness | only in case sampling: `random.Random(8080)` |

## 2. Run order and expected output

```bash
# 1. schemas and store characterisation (evidence for the tier decisions)
python experiments/b080/dump_store_schema.py          # -> experiments/b080/store_schema.json
python experiments/b080/characterise_stores.py        # -> experiments/b080/store_characterisation.json

# 2. coverage matrix + evidence-time audit + clock audit
python experiments/b080/coverage_audit.py             # -> COVERAGE_MATRIX.{json,md}, EVIDENCE_TIME_AUDIT.json

# 3. entity resolution and domain sharing (evidence for the amendment)
python experiments/b081/entity_and_domain_audit.py    # -> ENTITY_AND_DOMAIN_AUDIT.json

# 4. 60 candidate packets (deterministic, seed 8080)
python experiments/b082/build_case_candidates.py      # -> CASE_CANDIDATES.{json,md}

# 5. minimal historical replay + leak audit
python experiments/b083/pilot_replay.py               # -> PILOT_RESULTS.json

# 6. unit tests for the new measurement logic
python -m pytest tests/test_study_coverage.py -q      # 18 passed
```

Observed runtimes on the workstation used: coverage audit ≈ 7 s; entity/domain audit ≈ 15 s; case build ≈ 0.4 s;
replay ≈ 0.2 s; tests < 1 s. The audits dominate because they scan a 1.4 GB store.

## 3. What is deterministic, and what is not

- **Deterministic:** coverage matrix, entity/domain audit, tier assignment, leak audit, pilot replay. No sampling.
- **Seeded:** case sampling (`random.Random(8080)`) — same seed, same 60 packets.
- **Not deterministic:** nothing in this Phase 0 depends on wall-clock time except the clock audit's own timestamp,
  which is recorded rather than used as an input.

## 4. Verification performed

| check | result |
|---|---|
| all programs exit 0 | yes (recorded in the commit messages) |
| `pytest tests/test_study_coverage.py` | 18 passed |
| leak audit | 0 violations over every event informing a score (after correcting the audit's own defect) |
| no writes to the stores | stores opened with `mode=ro` URIs |
| no `data/` files committed | `git status` clean of `data/`; the junction is untracked |
| `main` untouched | `ae18f27`; all work on `research/early-signal-5firms` |
| existing test suite | see note below |

**Note on the full suite:** this study adds a package (`medradar/studies/`) and tests; the programme's 913-test suite
is not re-run on every study commit. Before any merge of this branch, `python tools/round_end.py` must pass at the
merged commit — that is the programme's own gate, and it is not claimed here.

## 5. Artifact inventory

| artifact | size | producer |
|---|---:|---|
| `COVERAGE_MATRIX.json` | 34 KB | `b080/coverage_audit.py` |
| `COVERAGE_MATRIX.md` | 7 KB | same |
| `EVIDENCE_TIME_AUDIT.json` | 5 KB | same |
| `ENTITY_AND_DOMAIN_AUDIT.json` | 106 KB | `b081/entity_and_domain_audit.py` |
| `CASE_CANDIDATES.json` | 71 KB | `b082/build_case_candidates.py` |
| `CASE_CANDIDATES.md` | 8 KB | same |
| `PILOT_RESULTS.json` | 5 KB | `b083/pilot_replay.py` |
| `PILOT_RESULTS.md`, `PROTOCOL.md`, `LABELING_PROTOCOL.md`, `DOMAIN_AMENDMENT_001.md`, `STUDY_DECISIONS.md`, `PHASE0_REPORT.md` | — | written by hand from the above numbers |

## 6. Known limits of this reproducibility package

- The store is **not** in git (1.4 GB); a third party must obtain the same extract to reproduce exact counts. Its
  provenance is described in the prior programme's `research/DATA_PROVENANCE.md`; this study adds no new source.
- Two of the five firms are resolved by **alias matching**, which is a documented approximation, not an identity
  proof.
- The 60 candidate packets are reproducible, but their **labels are not** — they await human adjudication, which is a
  different kind of reproducibility (inter-rater, not deterministic).
