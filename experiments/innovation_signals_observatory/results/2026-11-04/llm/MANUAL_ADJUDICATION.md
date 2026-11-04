# Manual adjudication — single author review (NOT human gold truth)

**Reviewer**: experiment author (`llm-jobtext`), after seeing the outputs; not blind.
**Date**: 2026-11-04. **Corpus**: the 20 sampled postings (12 primary + 8 negative controls).
**What this is**: a small human-readability check of whether the machine-checkable metrics are
too generous or too harsh. It is **not** a gold standard and it is **not** blind, so it cannot
turn the A/B numbers into accuracy. Verdict vocabulary is deliberately coarse.

Method: for each posting I read the title, the arm's quoted evidence and (where the quote was
ambiguous) the surrounding posting text, then recorded `AGREE` / `DISAGREE` / `UNCERTAIN` for
the function class and `SUPPORTED` / `PRODUCT-CONTEXT-ONLY` / `OVERREACH` for the technology
track. `PRODUCT-CONTEXT-ONLY` means the track names the company's product area that the role
supports/sells, not a technology the role develops — allowed for quality/support functions by
the taxonomy's track gate, but it is **not** R&D-direction evidence.

| posting_id | title | arm | function | track | function verdict | track verdict | note |
|---|---|---|---|---|---|---|---|
| e7c298…0000 | Senior Principal Software Engineer | A | ALGORITHM_SOFTWARE | — | AGREE | n/a | |
| e7c298…0000 | Senior Principal Software Engineer | B | ALGORITHM_SOFTWARE | cardiac_rhythm | AGREE | OVERREACH | quote only mentions software teams serving Cardiovascular portfolios; no cardiac-rhythm technology in the role |
| 332333…0000 | Product Manager / Associate PM | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 332333…0000 | Product Manager / Associate PM | B | SALES_ADMIN_OTHER | — | AGREE | n/a | function evidence quote not verbatim (model condensed the sentence) |
| b7fd2a…0000 | Principal Quality Engineer, Neuromodulation | A | QUALITY_REGULATORY | neurostimulation | AGREE | PRODUCT-CONTEXT-ONLY | |
| b7fd2a…0000 | Principal Quality Engineer, Neuromodulation | B | QUALITY_REGULATORY | neurostimulation | AGREE | PRODUCT-CONTEXT-ONLY | |
| 0b2e3c…0001 | Software Test Engineer II | A | PRODUCT_ENGINEERING | wearable_remote | UNCERTAIN | OVERREACH | "test/verification" is defensibly product engineering; the track comes from an unrelated product mention |
| 0b2e3c…0001 | Software Test Engineer II | B | ALGORITHM_SOFTWARE | endoscopy | UNCERTAIN | OVERREACH | test-automation software is defensibly software; endoscopy quote is a company blurb, not the role's technology |
| 91a675…0000 | Regional Sales Manager – Neurovascular | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 91a675…0000 | Regional Sales Manager – Neurovascular | B | SALES_ADMIN_OTHER | neurovascular | AGREE | OVERREACH | product portfolio being sold, not developed |
| ec02c9…0000 | Estagiário de Departamento Pessoal (HR intern, PT) | A | UNCLASSIFIED | — | UNCERTAIN | n/a | A declined on a non-English posting |
| ec02c9…0000 | Estagiário de Departamento Pessoal (HR intern, PT) | B | SALES_ADMIN_OTHER | — | AGREE | n/a | 193 s wall clock (TIMEOUT) |
| 524923…0001 | Field Tech Svc Spec (JA) | A | UNCLASSIFIED | — | UNCERTAIN | n/a | |
| 524923…0001 | Field Tech Svc Spec (JA) | B | SALES_ADMIN_OTHER | — | AGREE | n/a | correctly quoted Japanese text verbatim |
| 571f03…0001 | EP Mapping Specialist, CAS | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 571f03…0001 | EP Mapping Specialist, CAS | B | SALES_ADMIN_OTHER | ep_pfa | AGREE | OVERREACH | commercial field role; ep_pfa is the product being supported (internal contradiction) |
| 032f14…0000 | Surgical Senior Technical Sales Rep | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 032f14…0000 | Surgical Senior Technical Sales Rep | B | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| b968d2…0002 | Software Engineering Manager | A | ALGORITHM_SOFTWARE | — | AGREE | n/a | |
| b968d2…0002 | Software Engineering Manager | B | ALGORITHM_SOFTWARE | endoscopy | AGREE | OVERREACH | R&D flag true; "developing and maintaining software applications" is borderline R&D (UNCERTAIN) |
| 705919…0000 | OR Sales Representative, Acute Care & Monitoring | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 705919…0000 | OR Sales Representative, Acute Care & Monitoring | B | SALES_ADMIN_OTHER | respiratory | AGREE | OVERREACH | respiratory is the product line sold (internal contradiction) |
| d47844…0001 | Calibration Engineer | A | MANUFACTURING_PROCESS | — | UNCERTAIN | n/a | equipment maintenance vs quality/calibration; both plausible |
| d47844…0001 | Calibration Engineer | B | QUALITY_REGULATORY | — | UNCERTAIN | n/a | same ambiguity, opposite side |
| 44592d…0000 | Customer Service Rep II (JA) | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 44592d…0000 | Customer Service Rep II (JA) | B | SALES_ADMIN_OTHER | — | AGREE | n/a | 160 s wall clock (TIMEOUT) |
| 6e581d…0001 | Sr. Principal Legal Counsel, GCC | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 6e581d…0001 | Sr. Principal Legal Counsel, GCC | B | **QUALITY_REGULATORY** | — | **DISAGREE** | n/a | legal role misclassified as quality/regulatory; function evidence quote not located |
| f8066f…0000 | Associate Customer Service Specialist (Spanish) | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| f8066f…0000 | Associate Customer Service Specialist (Spanish) | B | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| dde5ac…0001 | Co-op/Apprentice (Non-Tech) | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| dde5ac…0001 | Co-op/Apprentice (Non-Tech) | B | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| bf8f5c…0002 | Intern: Graduate (Non-Tech) | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| bf8f5c…0002 | Intern: Graduate (Non-Tech) | B | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| ae2b9a…0001 | Senior Marketing Specialist, EndoVenous | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| ae2b9a…0001 | Senior Marketing Specialist, EndoVenous | B | SALES_ADMIN_OTHER | **peripheral_vascular** | AGREE | **OVERREACH** | **negative-control false positive**: business-unit name ("Endovenous business") turned into a technology track; function quote also not located |
| 2e1ef6…0000 | Principal Financial Analyst | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 2e1ef6…0000 | Principal Financial Analyst | B | **QUALITY_REGULATORY** | — | **DISAGREE** | n/a | finance role misclassified as quality/regulatory (still no R&D/track, so not a false positive by the headline definition) |
| 41c07e…0001 | GPO Commercial Enablement | A | SALES_ADMIN_OTHER | — | AGREE | n/a | |
| 41c07e…0001 | GPO Commercial Enablement | B | SALES_ADMIN_OTHER | — | AGREE | n/a | |

## What this table adds beyond the automatic metrics

1. **B's negative-control track false positive is real and visible**: the Marketing Specialist
   posting is a genuine non-technical role and the model emitted `peripheral_vascular` from a
   business-unit phrase. This is the same failure mode the programme's prior fine-tuning run
   made worse; on the untuned model it appears once in 8 controls.
2. **B did not invent R&D function classes for negatives** (0/8), but it did misclassify 2/8
   non-R&D roles as `QUALITY_REGULATORY` (legal, finance). The headline metric rightly does not
   count that as a direction false positive; a reader looking only at the headline would miss it.
3. **B's track claims are frequently product-context overreach**, not technology identification:
   4 of 8 track claims are `OVERREACH` on this sample (plus the negative-control one). The
   internal-consistency metric (4/20 contradictions) counts this without needing labels.
4. **The cue-support metric (B function 0.588) is too harsh on non-English and paraphrased
   quotes**, not necessarily wrong labels: the adjudicated function verdicts are mostly AGREE.
   This is why cue-support is reported as a conservative lower bound, never as accuracy.
5. **A's 5 unlocated quotes are a span-construction artefact**, not hallucination: the cue
   "budget" (plural-tolerant match on "budgets") emits the span text `budget`, a prefix that is
   not verbatim. A's real locatability is therefore ~1.0 for function cues other than that rule;
   the defect belongs to the A arm's evidence construction (owner: `job-identity`), and the
   experiment reports it rather than patching it.
