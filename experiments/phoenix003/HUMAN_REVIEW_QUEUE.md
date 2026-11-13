# PHOENIX-003 human review queue

40 links, ordered by the frozen buckets (1) product-specific AND pre-regulatory, (2) product-specific, (3) pre-regulatory, (4) other verified links; then descending lead time.

The three questions a reviewer must answer are the three the study asks:
1. is this really the same technology or product?
2. was the evidence publicly available before the milestone?
3. without knowing the later regulatory outcome, could an observer have identified this candidate from what was already public?

No model fills the `human_*` columns.

| # | firm | milestone (date) | token | df | regime | lead d | evidence |
|---:|---|---|---|---:|---|---:|---|
| 1 | medtronic | Emprint Ablation System with Thermosphere Techno (2024-03-28) | `OVERALL` | 1 | PRE_REGULATORY | 1823 | epmc:30931726 — Outcomes After Drug-Coated Balloon Treatment of Femoropopliteal Lesion |
| 2 | abbott | Amplatzer Amulet Left Atrial Appendage Occlude (2021-08-14) | `AMULET` | 1 | PRE_REGULATORY | 1815 | ctgov:NCT02879448 — AMPLATZER™ Amulet™ LAA Occluder Trial |
| 3 | edwards_lifesciences | EDWARDS INTUITY ELITE VALVE SYSTEM (2016-08-12) | `INTUITY` | 1 | PRE_REGULATORY | 1775 | ctgov:NCT01445171 — Surgical Treatment of Aortic Stenosis With a Next Generation Surgical  |
| 4 | bd | BD Kiestra IdentifA (2021-11-03) | `KIESTRA` | 2 | PRE_REGULATORY | 1767 | epmc:PMC5631243 — Impact of Automation Process on Microbiological Laboratory Efficiency |
| 5 | medtronic | Symplicity Spyral Renal Denervation System (2023-11-17) | `SYMPLICITY` | 1 | PRE_REGULATORY | 1738 | epmc:30760655 — Sufficient and Persistent Blood Pressure Reduction in the Final Long-T |
| 6 | boston_scientific | Capio SLIM Suture Capturing Device (2017-11-03) | `CAPTURING` | 1 | PRE_REGULATORY | 1674 | ctgov:NCT01823055 — Safety and Efficacy of a Transvaginal Suture Capturing Mesh Device |
| 7 | abbott | Portico Transcatheter Aortic Valve Implantation  (2021-09-17) | `PORTICO` | 1 | PRE_REGULATORY | 1673 | ctgov:NCT03056573 — Assessment of the St Jude Medical Portico Resheathable Aortic Valve Sy |
| 8 | boston_scientific | WATCHMAN LEFT ATRIAL APPENDAGE (LAA) CLOSURE TEC (2015-03-13) | `WATCHMAN` | 3 | PRE_REGULATORY | 1670 | ctgov:NCT01182441 — Evaluation of the WATCHMAN Left Atrial Appendage (LAA) Closure Device  |
| 9 | zimmer_biomet | Sidus Stem-Free Shoulder (2017-12-18) | `SIDUS` | 1 | PRE_REGULATORY | 1648 | ctgov:NCT01878253 — Sidus Stem-Free Shoulder IDE Study |
| 10 | boston_scientific | VERCISE DEEP BRAIN STIMULATION (DBS)SYSTEM (2017-12-08) | `VERCISE` | 1 | PRE_REGULATORY | 1611 | ctgov:NCT01896115 — CUSTOM-DBS: Current Steering to Optimize Deep Brain Stimulation |
| 11 | abbott | TriClip G4 System (2024-04-01) | `TRICLIP` | 1 | PRE_REGULATORY | 1607 | epmc:31708188 — Transcatheter edge-to-edge repair for reduction of tricuspid regurgita |
| 12 | stryker | Neuroform Atlas® Stent System (2019-05-16) | `NEUROFORM` | 1 | PRE_REGULATORY | 1581 | ctgov:NCT02340585 — Neuroform Atlas Stent System Study |
| 13 | medtronic | PulseSelect Pulsed Field Ablation (PFA) system (2023-12-13) | `PULSESELECT` | 1 | PRE_REGULATORY | 1461 | ctgov:NCT04198701 — Pulsed Field Ablation to Irreversibly Electroporate Tissue and Treat A |
| 14 | medtronic | Abre Venous Self-expanding Stent System (2020-10-21) | `ABRE` | 1 | PRE_REGULATORY | 1359 | ctgov:NCT03038438 — ABRE Clinical Study of the Abre Venous Self-expanding Stent System |
| 15 | bd | BD ONCLARITY HPV ASSAY (2018-02-12) | `ONCLARITY` | 1 | PRE_REGULATORY | 1322 | epmc:24926084 — Clinical performance of the BD Onclarity HPV assay using an adjudicate |
| 16 | bd | BD Kiestra Methicillin-resistant Staphylococcus  (2023-05-04) | `KIESTRA` | 2 | PRE_REGULATORY | 1311 | epmc:PMC6809780 — 2161. Organism-Specific Turn Around Time Improvement in Urinary Specim |
| 17 | edwards_lifesciences | Edwards EVOQUE Tricuspid Valve Replacement Syste (2024-02-01) | `EVOQUE` | 1 | PRE_REGULATORY | 1289 | ctgov:NCT04482062 — TRISCEND II Pivotal Trial |
| 18 | boston_scientific | TheraSphere (2021-03-17) | `THERASPHERE` | 1 | PRE_REGULATORY | 1267 | ctgov:NCT03295006 — A TheraSphere® Advanced Dosimetry Retrospective Global Study in HCC |
| 19 | siemens_healthineers | AI-Rad Companion Organs RT (2020-11-06) | `ORGANS` | 3 | PRE_REGULATORY | 1166 | epmc:28848035 — Biodistribution and Dosimetry Results from a Phase 1 Trial of Therapy  |
| 20 | abbott | TactiFlex Ablation Catheter, Sensor Enabled, T (2023-05-18) | `TACTIFLEX` | 1 | PRE_REGULATORY | 1122 | ctgov:NCT04356040 — TactiFlex Paroxysmal Atrial Fibrillation IDE Trial |
| 21 | boston_scientific | Eluvia Drug-Eluting Vascular Stent System (2018-09-18) | `ELUVIA` | 1 | PRE_REGULATORY | 1070 | ctgov:NCT02574481 — ELUVIA™ Drug-eluting Stent Versus Zilver® PTX® Stent |
| 22 | zimmer_biomet | AccuFill Bone Substitute Material (2019-06-10) | `ACCUFILL` | 1 | PRE_REGULATORY | 789 | ctgov:NCT03110224 — SCP® Observational Study of the Knee |
| 23 | medtronic | VENASEAL CLOSURE SYSTEM (2015-02-20) | `VENASEAL` | 1 | PRE_REGULATORY | 714 | ctgov:NCT01807585 — VenaSeal Sapheon Closure System Pivotal Study (VeClose) |
| 24 | abbott | Aveir Retrieval Catheter (2022-04-01) | `AVEIR` | 1 | PRE_REGULATORY | 555 | ctgov:NCT04559945 — The LEADLESS II IDE Study for the Aveir VR Leadless Pacemaker System |
| 25 | abbott | Aveir VR Leadless System (2022-03-31) | `AVEIR` | 1 | PRE_REGULATORY | 554 | ctgov:NCT04559945 — The LEADLESS II IDE Study for the Aveir VR Leadless Pacemaker System |
| 26 | zimmer_biomet | Efficient Care 3D Planning (2019-08-23) | `EFFICIENT` | 1 | PRE_REGULATORY | 509 | epmc:30276077 — Anterior and Lateral Lumbar Interbody Fusion With Supplemental Intersp |
| 27 | medtronic | MELODY TRANSCATHETER PULMONARY VALVE (TPV), ENSE (2015-01-27) | `MELODY` | 2 | PRE_REGULATORY | 393 | ctgov:NCT02023775 — Non Interventional Study on Pulmonary Valve Replacement by Thranscathe |
| 28 | bd | BD FACSPresto System, BD FACSPresto CD4/Hb Cartr (2015-12-17) | `FACSPRESTO` | 1 | PRE_REGULATORY | 268 | ctgov:NCT02396355 — Accuracy Evaluation of the BD FACS Presto System |
| 29 | boston_scientific | POLARx/POLARx FIT Cryoablation Catheters, SMARTF (2023-08-08) | `POLARX` | 1 | PRE_REGULATORY | 166 | epmc:36786515 — Acute procedural efficacy and safety of a novel cryoballoon for the tr |
| 30 | medtronic | TRANSLACE Spinal Tethering System (2017-05-16) | `TETHERING` | 1 | PRE_REGULATORY | 127 | epmc:28070685 — Porcine spine finite element model: a complementary tool to experiment |
| 31 | baxter | PerClot® Polysaccharide Hemostatic System (2023-05-19) | `POLYSACCHARIDE` | 3 | PRE_REGULATORY | 28 | epmc:37085652 — Modelling of icodextrin hydrolysis and kinetics during peritoneal dial |
| 32 | abbott | Assurity MRI and Endurity MRI Pacemakers, Tendri (2017-01-31) | `TENDRIL` | 2 | PRE_EXISTING_PRODUCT | 1820 | ctgov:NCT01528150 — Safety and Efficacy Study of Tendril MRI™ Leads in Standard Bradycardi |
| 33 | abbott | FreeStyle Libre 2 Flash Glucose Monitoring Syste (2020-06-12) | `LIBRE` | 3 | PRE_EXISTING_PRODUCT | 1795 | epmc:26171659 — The Performance and Usability of a Factory-Calibrated Flash Glucose Mo |
| 34 | abbott | FreeStyle Libre 2 Flash Glucose Monitoring Syste (2023-03-03) | `LIBRE` | 3 | PRE_EXISTING_PRODUCT | 1780 | ctgov:NCT03502174 — FreeStyle Libre Glucose Monitoring System in Pediatric Populations |
| 35 | boston_scientific | Advantage/Advantage Fit Delivery Device, Lynx De (2017-12-20) | `OBTRYX` | 1 | PRE_EXISTING_PRODUCT | 1778 | ctgov:NCT01784588 — Post Market Study Of Single Incision Sling Versus Transobturator Sling |
| 36 | medtronic | RESOLUTE ONYX ZOTAROLIMUS-ELUTING CORONARY STENT (2017-04-28) | `RESOLUTE` | 3 | PRE_EXISTING_PRODUCT | 1752 | ctgov:NCT01638507 — An Evaluation of the Commercially Available Medtronic Resolute Integri |
| 37 | zimmer_biomet | G7® Vivacit-E® Freedom® Constrained Liner (2022-04-28) | `VIVACIT` | 2 | PRE_EXISTING_PRODUCT | 1739 | ctgov:NCT03226808 — Vivacit-E Post-market Follow-up Study |
| 38 | stryker | Trevo Trak 21 Microcatheter (2019-11-22) | `TREVO` | 3 | PRE_EXISTING_PRODUCT | 1704 | epmc:25805755 — Stagnation of treatment times over a decade: results of a pooled analy |
| 39 | stryker | Trevo XP ProVue Retriever (2019-06-25) | `TREVO` | 3 | PRE_EXISTING_PRODUCT | 1697 | epmc:25399522 — Development of the Trevo ProVue Retriever for intracranial clot remova |
| 40 | abbott | Libre Rio Continuous Glucose Monitoring System (2024-06-07) | `LIBRE` | 3 | PRE_EXISTING_PRODUCT | 1681 | epmc:31673972 — The Impact of Flash Glucose Monitoring on Glycaemic Control as Measure |
