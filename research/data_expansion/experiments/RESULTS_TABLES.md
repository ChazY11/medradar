# Experiment outputs (generated)

## EXP-A — coverage per source

| source | anchors with relevant hit | coverage | hits | unique | dup rate | verdict |
|---|---|---|---|---|---|---|
| clinicaltrials_gov | 10/38 | 26.3% | 227 | 35 | 0.0% | INCREMENTAL |
| crossref | 31/38 | 81.6% | 702 | 453 | 8.3% | INCREMENTAL |
| europepmc | 13/38 | 34.2% | 357 | 103 | 0.0% | INCREMENTAL |
| nih_reporter | 0/38 | 0.0% | 760 | 0 | 0.0% | NOT_INCREMENTAL |
| openalex | 29/38 | 76.3% | 785 | 340 | 6.1% | INCREMENTAL |
| pubmed_eutils | 9/38 | 23.7% | 227 | 45 | 0.0% | INCREMENTAL |
| semantic_scholar | 1/38 | 2.6% | 23 | 20 | 0.0% | NOT_INCREMENTAL |
| usaspending | 14/38 | 36.8% | 201 | 125 | 11.3% | INCREMENTAL |

## EXP-B — linker behaviour vs two controls

| strategy | real link rate | decoy link rate | spec vs decoy | false-link vs unrelated | firm-confirmed? | refusal |
|---|---|---|---|---|---|---|
| name_only | 84.2% | 0.4% | 210.084 | 0.3% | False | 0.0% |
| name_plus_firm | 18.4% | 0.0% | None | 0.0% | True | 78.1% |
| regulatory_id | 0.0% | 0.0% | None | 0.0% | False | 100.0% |
| multi_field | 5.3% | 0.0% | None | 0.0% | True | 93.8% |
| candidate_semantic | 84.2% | 0.4% | 210.084 | 0.8% | False | 0.0% |

Usable for confirmed links: **none** (threshold: requires firm confirmation AND specificity_vs_decoy >= 1.5 AND specificity_vs_unrelated_evidence >= 1.5 AND authoritative_error_rate < 0.05 AND refusal_rate <= 0.5)

## EXP-C — lead time

- tier A (firm-confirmed): n=29, median=2508
- tier B (product-only): n=863, median=2636
- placebo median: 2593.5, p=0.569
- verdict: **NO_DETECTABLE_LEAD**

