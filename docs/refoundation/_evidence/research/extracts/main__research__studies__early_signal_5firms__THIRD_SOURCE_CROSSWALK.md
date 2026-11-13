# THIRD-SOURCE CROSS-CHECK — Europe PMC against the nine events

Protocol frozen first (`THIRD_SOURCE_PROTOCOL.md`). Status counts: `{'AFTER_CLEARANCE': 5, 'SUPPORTED_BEFORE': 4}`.

| event | firm | track | clearance | hits | status | distance | earliest pub | lead (d) | lead (q) |
|---|---|---|---|---:|---|---|---|---:|---:|
| LT-01 | ge_healthcare | patient_monitoring | 2022-04-01 | 227 | **AFTER_CLEARANCE** | NEAR | 2023-06-02 | -427 | -4.68 |
| LT-02 | medtronic | imaging_mr_ct | 2019-03-06 | 418 | **AFTER_CLEARANCE** | NEAR | 2024-10-25 | -2060 | -22.58 |
| LT-03 | medtronic | respiratory | 2020-11-20 | 518 | **AFTER_CLEARANCE** | NEAR | 2022-09-01 | -650 | -7.12 |
| LT-04 | medtronic | respiratory | 2022-01-14 | 518 | **AFTER_CLEARANCE** | NEAR | 2022-09-01 | -230 | -2.52 |
| LT-05 | medtronic | vascular_access | 2021-07-15 | 95 | **SUPPORTED_BEFORE** | DISTANT | 1998-04-10 | 8497 | 93.12 |
| LT-06 | philips | imaging_us | 2019-09-06 | 1934 | **AFTER_CLEARANCE** | NEAR | 2025-01-01 | -1944 | -21.3 |
| LT-07 | philips | respiratory | 2024-07-31 | 1631 | **SUPPORTED_BEFORE** | NEAR | 2024-05-16 | 76 | 0.83 |
| LT-08 | philips | vascular_access | 2025-06-24 | 32 | **SUPPORTED_BEFORE** | DISTANT | 2011-01-05 | 5284 | 57.91 |
| LT-09 | philips | wearable_remote | 2023-04-03 | 451 | **SUPPORTED_BEFORE** | DISTANT | 2016-08-01 | 2436 | 26.7 |

## Queries (verbatim)

- **LT-01**: `(AFF:"GE HealthCare" OR AFF:"GE Medical") AND ("PATIENT MONITOR" OR "PULSE OXIMETER" OR "BLOOD PRESSURE")`
- **LT-02**: `(AFF:"Medtronic") AND ("X RAY SYSTEM" OR "COMPUTED TOMOGRAPHY" OR "MAGNETIC RESONANCE")`
- **LT-03**: `(AFF:"Medtronic") AND ("RESPIRATORY" OR "VENTILATOR" OR "ANESTHESIA")`
- **LT-04**: `(AFF:"Medtronic") AND ("RESPIRATORY" OR "VENTILATOR" OR "ANESTHESIA")`
- **LT-05**: `(AFF:"Medtronic") AND ("CATHETER INTRODUCER" OR "ADMINISTRATION SET" OR "VASCULAR ACCESS")`
- **LT-06**: `(AFF:"Philips") AND ("ECHOCARDIOGRAPHY" OR "ULTRASOUND" OR "SONOGRAPH")`
- **LT-07**: `(AFF:"Philips") AND ("RESPIRATORY" OR "VENTILATOR" OR "ANESTHESIA")`
- **LT-08**: `(AFF:"Philips") AND ("CATHETER INTRODUCER" OR "ADMINISTRATION SET" OR "VASCULAR ACCESS")`
- **LT-09**: `(AFF:"Philips") AND ("REMOTE MONITORING" OR "AMBULATORY" OR "WEARABLE")`

## Not claimed

- no label: every packet remains PENDING_HUMAN_REVIEW with final_label null
- no predictive claim: a paper before a clearance is compatible with routine incremental work
- no aggregate claim across nine events, three firms, and a post-hoc keyword crosswalk
- NO_RECORD is not evidence that no research existed
