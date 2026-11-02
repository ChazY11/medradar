# HUMAN REVIEW WORKSHEET — 69 packets, 69 decisions

Fill `HUMAN_REVIEW_WORKSHEET.csv` (one row per packet), then run:

```bash
python experiments/b098/ingest_human_review.py --in research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv
```

**Allowed labels (exact):** `Confirmed Shift`, `Routine Iteration`, `False Signal / No Confirmed Shift`,
`Uncertain`, `Insufficient Observation`. A `Confirmed Shift` additionally needs an independent confirmation.
Every row needs a reviewer name and a reason; the ingest script refuses to write anything otherwise.

## Priority order (why this order)

1. small-sample packets with a **NEAR** third-source publication — the only ones where an independent
   prior record exists (1 packet);
2. small-sample packets with **DISTANT** support — decide whether a decade-old paper counts (3 packets);
3. novel-entry candidates with a **consistent** product-code mapping (evidence consistent);
4. routine-stratum candidates — the **controls**: these should mostly be `Routine Iteration`;
5. packets the rubric could not assess (no product code / no mapping).

## Rows

| # | packet | firm | track | stratum | date | third source | agent preliminary |
|---|---|---|---|---|---|---|---|
| 1 | LT-05 | medtronic | vascular_access | — | 2020-07-23 | SUPPORTED_BEFORE | Uncertain (agent-preliminary) |
| 2 | LT-07 | philips | respiratory | — | 2021-06-14 | SUPPORTED_BEFORE | Uncertain (agent-preliminary) |
| 3 | LT-08 | philips | vascular_access | — | 2020-06-30 | SUPPORTED_BEFORE | Uncertain (agent-preliminary) |
| 4 | LT-09 | philips | wearable_remote | — | 2022-08-26 | SUPPORTED_BEFORE | Uncertain (agent-preliminary) |
| 5 | ES5-023 | ge_healthcare | imaging_mr_ct | novel_entry | 2018-01-05 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 6 | ES5-025 | ge_healthcare | imaging_us | novel_entry | 2018-03-13 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 7 | ES5-029 | ge_healthcare | patient_monitoring | novel_entry | 2018-12-06 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 8 | ES5-034 | ge_healthcare | patient_monitoring | novel_entry | 2022-04-01 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 9 | LT-01 | ge_healthcare | patient_monitoring | — | 2021-05-06 | AFTER_CLEARANCE | Uncertain (agent-preliminary) |
| 10 | ES5-031 | ge_healthcare | respiratory | novel_entry | 2019-05-01 | NOT_CHECKED | Not Assessable (agent-preliminary) |
| 11 | ES5-032 | ge_healthcare | respiratory | novel_entry | 2021-10-21 | NOT_CHECKED | Not Assessable (agent-preliminary) |
| 12 | ES5-022 | medtronic | cardiac_rhythm | novel_entry | 2018-01-03 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 13 | LT-02 | medtronic | imaging_mr_ct | — | 2018-07-13 | AFTER_CLEARANCE | Uncertain (agent-preliminary) |
| 14 | ES5-028 | medtronic | medical_ai | novel_entry | 2018-11-08 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 15 | ES5-037 | medtronic | medical_ai | novel_entry | 2023-06-30 | NOT_CHECKED | Not Assessable (agent-preliminary) |
| 16 | ES5-033 | medtronic | respiratory | novel_entry | 2022-01-14 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 17 | ES5-038 | medtronic | respiratory | novel_entry | 2024-04-19 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 18 | LT-03 | medtronic | respiratory | — | 2018-06-27 | AFTER_CLEARANCE | Uncertain (agent-preliminary) |
| 19 | LT-04 | medtronic | respiratory | — | 2021-03-23 | AFTER_CLEARANCE | Uncertain (agent-preliminary) |
| 20 | ES5-021 | mindray | imaging_us | novel_entry | 2018-01-02 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 21 | ES5-030 | mindray | patient_monitoring | novel_entry | 2018-12-10 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 22 | ES5-024 | philips | imaging_mr_ct | novel_entry | 2018-01-12 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 23 | ES5-026 | philips | imaging_us | novel_entry | 2018-07-27 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 24 | ES5-035 | philips | imaging_us | novel_entry | 2022-09-27 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 25 | LT-06 | philips | imaging_us | — | 2019-01-23 | AFTER_CLEARANCE | Uncertain (agent-preliminary) |
| 26 | ES5-027 | philips | medical_ai | novel_entry | 2018-10-24 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 27 | ES5-036 | philips | medical_ai | novel_entry | 2022-10-24 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 28 | ES5-040 | philips | patient_monitoring | novel_entry | 2025-05-05 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 29 | ES5-039 | philips | respiratory | novel_entry | 2024-07-31 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 30 | ES5-042 | ge_healthcare | imaging_mr_ct | routine | 2019-12-13 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 31 | ES5-045 | ge_healthcare | imaging_mr_ct | routine | 2021-04-28 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 32 | ES5-059 | ge_healthcare | imaging_mr_ct | routine | 2025-06-18 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 33 | ES5-049 | ge_healthcare | imaging_us | routine | 2021-09-10 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 34 | ES5-055 | ge_healthcare | imaging_us | routine | 2023-02-16 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 35 | ES5-050 | ge_healthcare | medical_ai | routine | 2021-10-29 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 36 | ES5-043 | ge_healthcare | patient_monitoring | routine | 2020-01-29 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 37 | ES5-051 | ge_healthcare | patient_monitoring | routine | 2022-04-13 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 38 | ES5-044 | medtronic | cardiac_rhythm | routine | 2020-04-16 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 39 | ES5-046 | medtronic | cardiac_rhythm | routine | 2021-05-27 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 40 | ES5-052 | medtronic | cardiac_rhythm | routine | 2022-05-20 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 41 | ES5-053 | medtronic | cardiac_rhythm | routine | 2022-05-26 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 42 | ES5-048 | medtronic | medical_ai | routine | 2021-08-27 | NOT_CHECKED | Not Assessable (agent-preliminary) |
| 43 | ES5-057 | medtronic | medical_ai | routine | 2024-06-05 | NOT_CHECKED | Not Assessable (agent-preliminary) |
| 44 | ES5-058 | medtronic | medical_ai | routine | 2025-01-17 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 45 | ES5-047 | mindray | imaging_us | routine | 2021-06-10 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 46 | ES5-060 | mindray | imaging_us | routine | 2025-11-07 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 47 | ES5-054 | philips | imaging_mr_ct | routine | 2022-12-23 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 48 | ES5-041 | philips | patient_monitoring | routine | 2018-11-15 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 49 | ES5-056 | philips | patient_monitoring | routine | 2023-11-22 | NOT_CHECKED | Routine Iteration (agent-preliminary) |
| 50 | ES5-007 | ge_healthcare | imaging_mr_ct | ambiguous | 2020-09-04 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 51 | ES5-003 | medtronic | medical_ai | ambiguous | 2019-07-31 | NOT_CHECKED | Not Assessable (agent-preliminary) |
| 52 | ES5-010 | medtronic | medical_ai | ambiguous | 2021-08-23 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 53 | ES5-020 | medtronic | medical_ai | ambiguous | 2025-08-07 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 54 | ES5-017 | medtronic | respiratory | ambiguous | 2024-09-12 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 55 | ES5-019 | medtronic | respiratory | ambiguous | 2025-05-20 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 56 | ES5-009 | mindray | imaging_us | ambiguous | 2021-03-23 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 57 | ES5-013 | mindray | imaging_us | ambiguous | 2023-06-09 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 58 | ES5-015 | mindray | imaging_us | ambiguous | 2023-10-26 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 59 | ES5-002 | mindray | patient_monitoring | ambiguous | 2019-07-10 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 60 | ES5-011 | mindray | patient_monitoring | ambiguous | 2022-12-02 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 61 | ES5-001 | philips | imaging_mr_ct | ambiguous | 2018-12-06 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 62 | ES5-006 | philips | imaging_mr_ct | ambiguous | 2020-01-24 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 63 | ES5-014 | philips | imaging_mr_ct | ambiguous | 2023-08-02 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 64 | ES5-018 | philips | imaging_mr_ct | ambiguous | 2025-05-16 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 65 | ES5-005 | philips | imaging_us | ambiguous | 2019-09-06 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 66 | ES5-016 | philips | medical_ai | ambiguous | 2024-03-14 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 67 | ES5-004 | philips | patient_monitoring | ambiguous | 2019-08-06 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 68 | ES5-008 | philips | patient_monitoring | ambiguous | 2020-09-11 | NOT_CHECKED | Uncertain (agent-preliminary) |
| 69 | ES5-012 | philips | patient_monitoring | ambiguous | 2023-02-03 | NOT_CHECKED | Uncertain (agent-preliminary) |

Evidence columns are pre-filled so no database query is needed; the five human columns are empty.
The agent's preliminary label is **not** a label — it is a rubric output shown for contrast only.
---

> **AMENDMENT 2026-11-03 (S-035/D-079).** The project owner authorised the external AI review as this study's **final**
> Target B adjudication and waived the human sign-off for this study. The five human columns will therefore stay empty
> permanently — they are not filled retroactively, because the labels are not human work. The final labels are in
> `ADJUDICATION_FINAL_V1.json` (tier `FINAL_ADJUDICATION_AI_OWNER_AUTHORISED`, `human_truth = false`). This worksheet
> and its guide are kept so that anyone who wants to *check* the AI labels can still do so; the result is already
> closed as a negative (0/69 confirmed shifts).

