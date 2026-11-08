# PHOENIX-003 human review queue

10 links, ordered by the frozen buckets (1) product-specific AND pre-regulatory, (2) product-specific, (3) pre-regulatory, (4) other verified links; then descending lead time.

The three questions a reviewer must answer are the three the study asks:
1. is this really the same technology or product?
2. was the evidence publicly available before the milestone?
3. without knowing the later regulatory outcome, could an observer have identified this candidate from what was already public?

No model fills the `human_*` columns.

| # | firm | milestone (date) | token | df | regime | lead d | evidence |
|---:|---|---|---|---:|---|---:|---|
| 1 | medtronic | MELODY TRANSCATHETER PULMONARY VALVE (TPV), ENSE (2015-01-27) | `MELODY` | 2 | PRE_REGULATORY | 1618 | ctgov:NCT01186692 — Melody® Transcatheter Pulmonary Valve Post-Approval Study |
| 2 | medtronic | PulseSelect Pulsed Field Ablation (PFA) system (2023-12-13) | `PULSESELECT` | 1 | PRE_REGULATORY | 1461 | ctgov:NCT04198701 — Pulsed Field Ablation to Irreversibly Electroporate Tissue and Treat A |
| 3 | medtronic | Abre Venous Self-expanding Stent System (2020-10-21) | `ABRE` | 1 | PRE_REGULATORY | 1359 | ctgov:NCT03038438 — ABRE Clinical Study of the Abre Venous Self-expanding Stent System |
| 4 | medtronic | Symplicity Spyral Renal Denervation System (2023-11-17) | `SYMPLICITY` | 1 | PRE_REGULATORY | 1340 | ctgov:NCT04311086 — SPYRAL DYSTAL Renal Denervation Global Clinical Study |
| 5 | medtronic | VENASEAL CLOSURE SYSTEM (2015-02-20) | `VENASEAL` | 1 | PRE_REGULATORY | 714 | ctgov:NCT01807585 — VenaSeal Sapheon Closure System Pivotal Study (VeClose) |
| 6 | medtronic | RESOLUTE ONYX ZOTAROLIMUS-ELUTING CORONARY STENT (2017-04-28) | `RESOLUTE` | 3 | PRE_EXISTING_PRODUCT | 1752 | ctgov:NCT01638507 — An Evaluation of the Commercially Available Medtronic Resolute Integri |
| 7 | medtronic | PillCam SB 3 capsule endoscopy system, PillCam S (2021-08-27) | `PILLCAM` | 3 | PRE_EXISTING_PRODUCT | 1550 | ctgov:NCT03167970 — Evaluation of Performance Characteristics of Capsule Endoscopy With Pi |
| 8 | medtronic | InPen System App (MMT-8060 (iOS), MMT-8061 (Andr (2024-11-12) | `INPEN` | 2 | PRE_EXISTING_PRODUCT | 1169 | ctgov:NCT05029271 — InPen User Experience |
| 9 | medtronic | Signia Circular Adapter (Standard Length) (SIGC (2024-11-01) | `SIGNIA` | 3 | PRE_EXISTING_PRODUCT | 1101 | ctgov:NCT05095935 — Medtronic Signia SDR Product Surveillance Registry |
| 10 | medtronic | HawkOne Directional Atherectomy System (2016-10-14) | `HAWKONE` | 2 | PRE_EXISTING_PRODUCT | 77 | ctgov:NCT02850107 — DiRectional AthErectomy + Drug CoAted BaLloon to Treat Long, CalcifIed |
