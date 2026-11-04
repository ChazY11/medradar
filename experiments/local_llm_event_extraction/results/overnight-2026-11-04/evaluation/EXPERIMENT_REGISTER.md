# Overnight experiment register

Generated from artifacts by `scripts/make_experiment_register.py`.
Every row is `exploratory`; no precision/recall/F1 is reported anywhere in this
run because the labels are machine-derived silver labels, not human annotations.

| id | kind | hypothesis | prompt | seed | GPU s | stop / failure |
|---|---|---|---|---:|---:|---|
| OVN-TRAIN-01 | qlora_training | QLoRA adaptation on SOURCE_DERIVED_SILVER labels reduces teacher-forced loss on held-out companies and produces schema-valid extractions without destr | extract-v2 | 20261104 | 1200.1 | wall_clock_budget_exhausted |
| OVN-EVAL-01 | evaluation | The repaired system (prompt v2 + schema v2) plus the exploratory adapter changes agreement with silver labels relative to the untuned model and to the | extract-v1 | 20261104 | — | — |
| OVN-EVAL-02 | evaluation | The repaired system (prompt v2 + schema v2) plus the exploratory adapter changes agreement with silver labels relative to the untuned model and to the | extract-v2 | 20261104 | — | — |
| OVN-EVAL-03 | evaluation | The repaired system (prompt v2 + schema v2) plus the exploratory adapter changes agreement with silver labels relative to the untuned model and to the | extract-v2 | 20261104 | — | — |
