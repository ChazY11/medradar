# Results

Each result is a committed artifact plus a plain-language statement of what it does
and does not show. Results are never edited to look better; a superseded result gets
a new entry and a pointer, not a rewrite.

| # | Result | Direction | Evidence |
|---|---|---|---|
| R1 | Continuation of active pairs is predictable but not beyond persistence | null on model advantage | `experiments/reverse_rd_v2/continuation_metrics.json` |
| R2 | First entry into a dormant track is weakly predictable at best | weak / not validated | `experiments/reverse_rd_v2/entry_metrics.json` |
| R3 | Consolidated SEC financials add no detectable continuation ranking skill | negative | `ablation_metrics.json` |
| R4 | Point-in-time market features add no detectable ranking skill | negative | `market_metrics.json` |
| R5 | OpenAlex publication counts add no detectable ranking skill | negative | `publication_metrics.json` |
| R6 | Financial features show a small positive entry ranking delta (+0.008 AP) | hypothesis only | `ablation_metrics.json` |
| R7 | Stored features are reproducible from as-of SQL (0 mismatches, 1.1M values) | consistency pass, not semantic proof | `run_v2.py` leakage replay |
| R8 | A bitemporal graph over real history supports deterministic as-of snapshots | infrastructure | `tkg_import_report.json` |
| R9 | 25 genuine prospective forecasts registered, none matured | pending | `data/registry.sqlite`, `forecast_cycle_report.json` |
| R10 | A deterministic applicant-entity universe doubles the observable firm panel without fuzzy matching | infrastructure | `config/universe_v1.json`, `docs/research/UNIVERSE.md` |
| R11 | On the entity cohort the entry model's ΔAP over per-pair persistence excludes zero in 3/3 windows under both entity and pair clustering | **supported (modest)** | `experiments/cycle2_coverage/` |
| R12 | The cycle-1 configuration is underpowered: its ΔAP sits below its own MDE and its pair-cluster interval includes zero | negative about cycle 1 | `experiments/cycle2_coverage/REPORT.md` §4 |
| R13 | The model's advantage at matched false-alarm rate is detection, not earlier warning | mixed / negative on lead time | `experiments/cycle2_coverage/REPORT.md` §5 |

## Cycle 1 (2026-11-02) — the honest headline

**The system, as of v0.5.0, has not demonstrated predictive skill for corporate
technological entry.** It has demonstrated: a rigorous, reproducible protocol; a
leakage-audited feature store; a persistence baseline that explains most of what
looked like skill; and a set of well-documented negative results about additional
data sources.

That is the correct baseline. Any future claim must beat it, not replace it.

See `cycle1_frozen_2026-11-02.md` for the numbers and their provenance.

## Cycle 2 (2026-11-02) — coverage, power, and whether the entry signal is real

Pre-registered question: *does widening the entity universe change the measured
predictability of first entry, and is the remaining estimate distinguishable from
zero?*

**Answer: yes to both, modestly.** On a 200-entity deterministic legal-entity cohort the
entry model beats per-pair persistence with ΔAP +0.0973, excluding zero in 3/3
pre-declared windows under both entity and pair clustering and exceeding its own MDE
(0.0877). On the original 51-parent panel the same protocol yields ΔAP +0.0564, below
its own MDE (0.0708), with the pair-cluster interval including zero — i.e. **the
cycle-1 negative was partly a coverage artefact**.

Boundaries that matter: the effect is small in absolute terms (AP 0.129 at a 0.68% base
rate), part of the gain is the persistence baseline getting weaker, the advantage is
**detection rather than earlier warning**, and the pre-declared firm-scale heterogeneity
split was degenerate. Details and all numbers: `cycle2_2026-11-02.md` and
`experiments/cycle2_coverage/REPORT.md`.
