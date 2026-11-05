# S-031 — Hiring Capability & R&D Evidence Study

Independent audit of PR #21 at `c4327ce44c6aafe0e4af5a73df7f356dfffcb438`.

## Directory guide

- `deliverables/`: the eight requested non-programmer-readable research deliverables.
- `scripts/`: deterministic sampling, prelabel validation, legacy-rule comparison, count audit and case-study rendering.
- `tests/`: standard-library offline tests, including source-hash and verbatim-quote checks.
- `audit/`: descriptive rule-comparison artifacts and the independently recomputed PR #21 count audit.
- `work/`: generated locally and gitignored. It contains selected raw records and full-text review packs; these are not redistributed in GitHub.
- `../../verifier/v2/`: acceptance criteria and verifier. Every run appends `verifier/runs/`; v1 is not replaced.

## Evidence status

All 100 labels are `AI_PRELIMINARY_LABEL`, not human gold. Disagreement counts are not accuracy, Precision, Recall or F1. The 100 jobs are a fixed-seed difficult-stratified sample, not a representative random sample. Three records have unavailable text and remain insufficiently evidenced.

## Reproduce

Run from the repository root. Defaults write the eight deliverables to `/mnt/agents/output/` and generated working files to `research/s031/work/`.

```bash
python3 research/s031/scripts/select_sample.py
python3 research/s031/scripts/build_prelabels.py
python3 research/s031/scripts/compare_legacy_rules.py
python3 research/s031/scripts/audit_pr21_counts.py
python3 research/s031/scripts/build_case_studies.py
python3 -m unittest discover -s research/s031/tests -v
python3 verifier/v2/verify.py
```

For a repository-local delivery, set:

```bash
export S031_OUTPUT_DIR="$PWD/research/s031/deliverables"
export S031_WORK_DIR="$PWD/research/s031/work"
```

Then run the same commands. Both variables also apply to tests and the verifier. No network, model training, GPU, Qwen weights or full raw-corpus redistribution is required.

The canonical protocol filename is always `S031_RESEARCH_PROTOCOL.md`. The local mirror also accepts `RESEARCH_PROTOCOL.md` as a fallback because that one exact filename proved unstable on the current shared mount; the GitHub delivery uses the canonical name.

## Important audit anchors

- Current Medtronic snapshot: 994 rows and 994 distinct opaque posting ids.
- Earlier documented denominator: 992 unique ids after two pagination duplicates; old source file unavailable for independent hash verification.
- Conservative analytical clusters: 983, with all duplicate/multi-city ambiguity retained.
- Robotics: 20 broad title hits, 80 title+description probe mentions, zero legacy `surgical_robotics` assignments; none of these alone means R&D.
- Description-only: 47 under the any-title-keyword definition; 54 under the non-generic-title-keyword definition.
- Twenty-four case studies include source evidence, old output, independent prelabel, disagreement mechanism, missing evidence and human-review decision.
