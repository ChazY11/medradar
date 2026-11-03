# AI evidence review of the 69 packets — summary

**Tier:** `AI_EVIDENCE_REVIEW` · **Authority:** `ai_evidence_review_v1` · **Date:** 2026-11-04
**Scope:** the 69 packets of `research/studies/early_signal_5firms/` (60 candidate records + 9 lead-time pairs)
**Record:** [`AI_EVIDENCE_REVIEW.jsonl`](AI_EVIDENCE_REVIEW.jsonl) (one line per packet) ·
**Reader's guide:** [`AI_REVIEW_GUIDE_ZH.md`](AI_REVIEW_GUIDE_ZH.md) ·
**Validator:** [`verify_ai_review.py`](verify_ai_review.py)

> **What this is not.** It is not human adjudication, not expert truth, and not a gold-standard label set.
> It may not be used as ground truth or to score the study's own detectors — doing so would recreate the
> circularity this programme has already retracted once. The frozen study material is unchanged: the
> original 69 packets, `HUMAN_REVIEW_WORKSHEET.csv`, `LABELING_PROTOCOL.md`, `ADJUDICATION_AGENT_V1.json`
> and all frozen results were only read. The owner's uncommitted worksheet edits were not touched, and
> `experiments/b098/ingest_human_review.py` was **not** run.

---

## 1. Why this review exists

The study's frozen protocol assigns labels to a **named human reviewer**, and every packet has carried
`PENDING_HUMAN_REVIEW` / `final_label = null` since publication. Two things then happened: the programme
already created a lower, non-human tier (`AGENT_PRE_ADJUDICATION`, rubric `agent_rubric_v1`), whose 69
labels were mostly "Uncertain" and were explicitly barred from scoring; and the owner is not a device
regulatory specialist, so asking them to adjudicate 69 technical cases by hand is neither realistic nor
obviously more accurate.

This review does the evidence work that a first-pass review would do, without pretending to be the human
label it replaces:

1. **verify the record** each packet points at, against the live primary source;
2. **look for counter-evidence** (prior clearances of the same device, prior activity in the same code,
   process-only supplements, entity and track artefacts);
3. **separate the three clocks** (event date, public availability, collection time) and say when a public
   date is only an assumption;
4. **classify** with the frozen five-label vocabulary, and say plainly when the case cannot be decided;
5. **say what is still unknown**, including which cases need a real domain expert.

## 2. Method

**Evidence collection (automated, reproducible).** For each of the 60 candidate packets the FDA record was
re-queried live on `api.fda.gov` (510(k) by `k_number`, PMA by `pma_number` + `supplement_number`), and the
following were recorded: applicant, device name, product code, decision date, decision code, clearance
type, supplement type, original PMA, prior clearances by the same firm in the same product code, prior
clearances under the same device name, and subsequent clearances in the same code within 24 months.
For the 9 lead-time pairs, the later clearance was located in the study's read-only store and verified
live; the earlier trial was re-fetched from the ClinicalTrials.gov v2 API; the cited third-source paper
was re-fetched from Europe PMC. 14 shortlisted cases additionally received independent-source searches
(ClinicalTrials.gov and Europe PMC by device name). Every record states which sources were searched,
including searches that returned nothing.

**Verification result.** 69/69 packets carry a verified record reference; 60/60 candidate FDA records were
found live with matching applicant, date and product code; 9/9 later clearances were verified; 9/9 trials
were verified live on ClinicalTrials.gov (sponsor, title, status, start date); 8/9 third-source hits were
re-verified by PMID (the ninth, LT-05, is an unindexed patent-style record, which is itself informative).

**Two reviewers, one adjudicator — and an honest note on independence.**

| role | who | independence |
|---|---|---|
| Reviewer A | the Lead model session (`deepseek-flash`) | had built the evidence dossiers, so not blind to the evidence |
| Reviewer B | a separate model session, `kimi`, run through the agent-hub CLI, given only a compact fact sheet | **different model family**, and did not see A's labels; but it is still an LLM with no device-regulatory certification |
| Adjudicator | the Lead session (same model as A) | compares A and B, resolves disagreements, records the reasoning |

So: two models, but **not two independent experts**, and A and the adjudicator are the same model. Where
A and B disagreed, the adjudication is recorded in the record's `adjudication_note` with the evidence
used, and the case is flagged `DIVERGENT`. No majority voting was used: every disagreement was resolved on
evidence, not by counting.

**Label vocabulary (frozen, from `LABELING_PROTOCOL.md`):** `Confirmed Shift`, `Routine Iteration`,
`False Signal / No Confirmed Shift`, `Uncertain`, `Insufficient Observation`.
**Review status (new):** `AI_ADJUDICATED` (a decided label) or `AI_UNRESOLVED` (must stay open).

## 3. Results

### 3.1 Label distribution (69 packets)

| label | all | 60 candidates | 9 pairs |
|---|---:|---:|---:|
| `Routine Iteration` | **48** | 48 | 0 |
| `False Signal / No Confirmed Shift` | **14** | 6 | 8 |
| `Uncertain` | **4** | 3 | 1 |
| `Insufficient Observation` | **3** | 3 | 0 |
| `Confirmed Shift` | **0** | 0 | 0 |

- `AI_ADJUDICATED`: **62** records. `AI_UNRESOLVED`: **7** (`ES5-010`, `ES5-017`, `ES5-019`, `ES5-020`,
  `ES5-027`, `ES5-028`, `LT-01`).
- Reviewer agreement: **64/69 agree; 5 disagreements, all adjudicated on evidence**
  (`ES5-017`, `ES5-033`, `ES5-039`, `ES5-042`, `ES5-048`).
- **Zero packets reach the frozen `Confirmed Shift` bar.** That bar requires a real change, sustained
  activity, separable dates, **and** confirmation from a source family different from the one that raised
  the packet. No packet in this set satisfies all four. The closest cases are recorded as unresolved and
  routed to expert review rather than promoted.

### 3.2 What the evidence actually shows — five findings

**F1 — Six of the 60 "technology events" are not product events at all.**
`ES5-022`, `ES5-044`, `ES5-046`, `ES5-052`, `ES5-053`, `ES5-057` are **PMA supplements**: five of type
"30-Day Notice" and one "Real-Time Process". Under FDA rules these cover manufacturing/process changes
that do not affect safety or effectiveness. They verify as real records belonging to the right firm — and
they carry no device change. The candidate rule counts regulatory events without distinguishing
administrative supplements from product clearances, so these packets are false alarms by construction.
*This is a packet-generation issue, not a change to any frozen result; no study number is affected.*

**F2 — Eight of the nine lead-time pairs join two different devices.**
The pair was formed by assigning a trial to a device track with keyword matching and then pairing it with
the next clearance in that firm-track. Case-level verification shows the two ends are usually unrelated
products that merely share a coarse track:

| pair | earlier trial | later clearance | verdict |
|---|---|---|---|
| LT-01 | continuous non-invasive blood pressure (GE) | B105M/B125M patient monitors | plausibly same family; not linked by any document → `Uncertain` |
| LT-02 | superDimension bronchoscopic navigation (lung) | Visualase laser ablation (brain) | different devices → false pair |
| LT-03 | LIFEGUARD ward respiratory monitoring | Puritan Bennett 980 ventilator | different products → false pair |
| LT-04 | BIS / end-tidal gas monitoring | Bio-Medicus life-support cannula | different products → false pair |
| LT-05 | Ellipsys arteriovenous fistula system | Bio-Medicus life-support cannula | different products → false pair |
| LT-06 | 3D fetal biometry ultrasound study | Lumify handheld ultrasound | different product lines → false pair |
| LT-07 | DreamKit respiratory-effort signal | AF531 CPAP oro-nasal mask | different products → false pair |
| LT-08 | DEFINE PCI intravascular pressure sensors | Bridge Plus peripheral occlusion balloon | different products → false pair |
| LT-09 | paediatric asthma care (withdrawn) | HeartStart FRx defibrillator PMA process supplement | unrelated **and** process-only |

The study already reports this 9-event description as descriptive, underpowered and left-truncated. This
review adds the case-level reason: the pairs do not represent same-technology sequences, so the median
"lead" of 3.3 quarters cannot be read as an early signal of those clearances. The cited third-source
"SUPPORTED_BEFORE" hits are similarly loose (a 1998 catheter-introducer record for an AV-fistula device; a
2011 ultrasound-thrombolysis paper for an occlusion balloon; a 2016 remote-monitoring protocol for a
defibrillator).

**F3 — One "first use" is an entity-resolution artefact.**
`ES5-048` (PillCam SB 3, 2021) appears as the firm's first use of product code NEZ. It is not: Given
Imaging Ltd. — acquired by Covidien and then Medtronic — has 22 NEZ clearances from 2002–2017. The
substring-alias matching used in the study cannot see "Given Imaging" as Medtronic. The packet is
therefore a software/device update of an existing line (`Routine Iteration`), and the artefact is recorded
in the record.

**F4 — The genuinely interesting technologies are one-off clearances, not sustained repositioning.**
The cases with substantive-looking capabilities — CardioInsight non-invasive cardiac mapping (`ES5-028`),
SureTune4 DBS programming (`ES5-010`), LumiGuide fibre-optic navigation (`ES5-016`), Critical Care Suite
AI triage (`ES5-050`), Deep-Learning Image Reconstruction (`ES5-042`), VitalFlow ECMO (`ES5-017`,
`ES5-019`), UNiD Spine Analyzer (`ES5-020`) — either are updates of already-cleared devices, or have no
follow-on activity inside the 24-month window, or fall too close to the study window's end to judge. None
can be called a sustained shift on this evidence; all are flagged for a domain expert.

**F5 — The candidate rule selects timing, not technology substance.**
48 of 69 packets are ordinary product iterations (Special 510(k)s modifying the firm's own device, new
models in a code the firm already uses, same device name cleared again). The gap rule that raises a
candidate ("no event in this track for ≥ 12 months") says nothing about whether the next event is a new
capability. This is consistent with, and helps explain, the study's own negative conclusion: at firm ×
track × quarter granularity the constraint is information, not modelling.

## 4. What this supports — and what it does not

**Supported by this review:** a source-linked, counter-evidence-checked, reproducible *case-level reading*
of all 69 packets; a precise list of which candidates are administrative records, cross-device artefacts,
entity artefacts, routine iterations, or genuinely open; and a documented basis for prioritising expert
review.

**Not supported (must not be claimed anywhere):** that 69 cases are human-confirmed; that expert ground
truth now exists; that the detectors' accuracy is validated; that MedRadar can predict technology change
early; that `Confirmed Shift = 0` means "no technology shift exists" — it means none of these packets
meets the evidence bar; that the study's frozen results are altered (they are not).

## 5. Priority list for external expert review

Two lists, because they answer different questions.

**A. Conclusion-critical (15).** These are the packets whose reading could change how the study's own
numbers should be interpreted — the six PMA process supplements (`ES5-022`, `ES5-044`, `ES5-046`,
`ES5-052`, `ES5-053`, `ES5-057`) and the nine cross-device pairs (`LT-01`…`LT-09`).

**B. Domain judgement (8).** Records where a device specialist's opinion would move the label:
`ES5-010`, `ES5-016`, `ES5-017`, `ES5-019`, `ES5-020`, `ES5-028`, `ES5-042`, `ES5-050`.

**C. Stratified random sample for error-rate estimation (20).** Validating only the hard cases cannot
estimate the overall error rate, so this sample was drawn with a fixed seed (`20261104`) in proportion to
the label distribution: 14 `Routine Iteration`, 4 `False Signal`, 1 `Uncertain`, 1 `Insufficient
Observation`.

`ES5-003`, `ES5-009`, `ES5-013`, `ES5-014`, `ES5-017`, `ES5-024`, `ES5-025`, `ES5-034`, `ES5-040`,
`ES5-043`, `ES5-044`, `ES5-049`, `ES5-051`, `ES5-052`, `ES5-054`, `ES5-055`, `ES5-056`, `LT-01`, `LT-05`,
`LT-09`.

If no external expert is available, these conclusions stay **exploratory**; that does not stop the review
from being usable as a triage document.

## 6. Limitations and disclosure

- **Two models, not two experts.** Reviewer A and the adjudicator are the same model session; Reviewer B is
  a different model family but was given compact fact sheets, not raw payloads, and is not a certified
  device reviewer. Agreement between them is evidence of reproducibility, not of correctness.
- **No human truth.** Nothing here fills `human_label`, `reviewer` or `reviewed_at`; the human worksheet
  remains untouched and un-ingested.
- **Identity is checked by the study's own alias rule** (substring matching on `applicant_raw`), which
  cannot establish legal-entity continuity. That limitation is inherited from the study and is why the
  `ES5-048` artefact is reportable but not fixable here.
- **Time check.** Each record carries the store's `published_at`, `first_seen_at`, `available_at` and
  `timestamp_quality`; the packets' `declared_available_at` is a *Tier B* assumption (event date + 30
  days), not a recorded publication time. No packet is credited with a public lead time.
- **Coverage of independent searches.** Only 14 of 60 candidate packets received a device-name
  independent-source search; for the rest, "no independent confirmation" means "not found in the sources
  searched", which is recorded per record.
- **Live data can change.** Verification was executed on 2026-11-04; the openFDA API and the study store
  will drift.

## 7. Reproduce

```bash
python research/studies/early_signal_5firms/ai_review/verify_ai_review.py   # structural validation
```

The collection and rendering scripts were run from a scratch directory outside the repository (they query
the network); the committed record contains the URLs, the retrieved timestamp and the verification method
for every packet, so each claim can be re-checked by hand or re-run against the live APIs.

## 8. Frozen-material check

No file outside `research/studies/early_signal_5firms/ai_review/` was modified by this review. To confirm:

```bash
git diff --stat origin/main -- \
  research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv \
  research/studies/early_signal_5firms/LABELING_PROTOCOL.md \
  research/studies/early_signal_5firms/ADJUDICATION_AGENT_V1.json \
  research/studies/early_signal_5firms/STUDY_DECISIONS.md
```
