# Experiments index

Every experiment is identified, versioned and reproducible. An experiment with no
committed artifact is not an experiment. Statuses: `FROZEN` (artifacts committed and
re-runnable), `ACTIVE`, `PLANNED`, `ABANDONED` (with reason).

| ID | Question | Protocol | Artifacts | Status |
|---|---|---|---|---|
| E1 | Does an already-active `(company, track)` pair continue to show public activity within 12 months? | purged expanding-origin, 25 origins, 10 R&D features, logistic regression | `experiments/reverse_rd_v1/` | FROZEN |
| E2 | Does a pair dormant ≥36 months enter a new track within 12 months? | purged expanding-origin, 24 origins, 16 entry features, base rate 1.23% | `experiments/reverse_rd_v2/entry_metrics.json` | FROZEN |
| E3 | Multi-window robustness of E1/E2 | last 3 origins as sequential holdouts, per-window mean/std | `experiments/reverse_rd_v2/continuation_metrics.json` | FROZEN |
| E4 | Do consolidated SEC financial features add ranking skill? | identical rows, one specification per cell | `ablation_metrics.json` | FROZEN (negative) |
| E5 | Do point-in-time market features add ranking skill? | `market_bars` ≤ cutoff, 8 features + missing flag | `market_metrics.json` | FROZEN (negative) |
| E6 | Do OpenAlex publication counts add ranking skill? | complete years ≤ year(t)-1, 15-Feb lag | `publication_metrics.json` | FROZEN (negative) |
| E7 | Is the stored feature matrix reproducible from as-of SQL? | independent replay of every feature from `events`/`financial_facts` at cutoff | leakage replay in `run_v2.py` output | FROZEN (0 mismatches on 1,107,081 entry values / 140,721 continuation values) |
| E8 | Can the bitemporal graph over real history answer as-of questions? | import 55,090 events → assertions, deterministic PIT snapshot | `experiments/reverse_rd_v2/tkg_import_report.json` | FROZEN |
| E9 | Does the research agent produce fully cited, non-hallucinated evidence chains? | deterministic 5-question workflow, 8 PIT tools, citation check | `experiments/reverse_rd_v2/agent_demo.json` | FROZEN (5 questions, 55 claims, 224 cited ids, 0 missing) |
| E10 | Do genuine future forecasts register and stay pending until maturity? | continuous cycle, idempotent re-run | `forecast_cycle_report.json`, `data/registry.sqlite` | FROZEN (25 nowcasts, 0 matured) |
| **E11** | **Does widening the entity universe from 51 curated parents to a deterministic applicant universe change measured predictability of first entry?** | **identical label/purge protocol as E2, expanded 200-entity panel, cluster-aware inference** | **`experiments/cycle2_coverage/`** | **FROZEN — ΔAP +0.0973, excludes 0 in 3/3 windows (both clusterings), above MDE; P1 counterparts fail the same rule** |
| E12 | Does entity granularity (legal applicant vs corporate parent) materially change the estimate? | same rows under two entity definitions | `experiments/cycle2_coverage/` | FROZEN as E11's P1-vs-P2 contrast (panel definition differs in composition too; a clean parent panel needs acquisition chains) |
| E13 | Is the E2 entry result an underpowered null or a true null? | MDE / power analysis on observed positive counts | `experiments/cycle2_coverage/analysis.json` | FROZEN — E2 configuration underpowered (ΔAP 0.0564 < MDE 0.0708) |
| E14 | How long before the milestone does the model actually fire, at matched false-alarm rate? | probability-of-detection curve, censored units counted | `experiments/cycle2_coverage/REPORT.md` §5 | FROZEN — detection advantage (+0.30…+0.44), **no** earlier-warning advantage |
| E15 | Does predictability vary systematically by track, firm scale, data maturity? | stratified metrics with cluster CIs | `experiments/cycle2_coverage/REPORT.md` §6 | FROZEN — pre-declared firm-scale split degenerate; track table descriptive only |
| E16 | Lead/lag structure between source classes and milestones | cross-correlation with multiple-comparison control | — | PLANNED (Phase 3) |
| E17 | Do public hiring signals lead technology entry? | requires lawful hiring data collection | — | PLANNED (Phase 3, blocked on data) |
| E18 | Do patent features add skill? | needs API key or bulk files | — | PLANNED (blocked on data access) |

## Reproduction discipline

- Training/test rows are defined by `available_at` and label-window closure, never by
  random split.
- Each frozen experiment records: config, data provenance, code commit, and a command
  that regenerates its artifacts.
- Diagnostics (`leaky_labels_diagnostic`) exist only to quantify bias and are never
  cited as results.
- A cell is only comparable to another cell if rows, purge rule, model and
  hyperparameters are identical; the ablation driver enforces this.
