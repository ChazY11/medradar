# ROADMAP — from ATLAS-001 to a durable evidence platform

This roadmap is derived from what the pilot actually found, not from a wish list. Each item
names the gap it closes and the evidence that the gap is real.

---

## Phase 4 — deepen the identity bridge (next)

**4.1 Device ↔ 510(k) candidate study (highest value, no new access needed)**
- Gap: GUDID does not publish premarket submissions; 510(k) groups products, so device-level
  linkage is unconfirmed.
- Work: join openFDA `device/registrationlisting` (owner/operator + product code + K number)
  to GUDID on labeler DUNS and product code; measure how often exactly one 510(k) is plausible;
  keep `POSSIBLE_MATCH` unless an official identifier exists.
- Deliverable: a bounded evaluation with a hand-checked sample of 50 clearances and an honest
  confirmation rate.

**4.2 EUDAMED access decision**
- Gap: no EU-wide device key in the system.
- Work: document the legal/access path for the EUDAMED public interface; do **not** scrape.
  If access is lawful and stable, add a `basic_udi_di` connector and re-run the cross-market
  bridge with EU as a third market.
- Blocker to record explicitly: access precondition, project-owner decision.

**4.3 NMPA UDI access decision**
- Same pattern as 4.2; China is the most important missing market for Mindray's coverage.

**4.4 MDALL brand/model enrichment**
- Gap: 99.67 % of MDALL identifier rows are model strings with no brand/model, which makes name
  comparison impossible.
- Work: use the licence detail endpoint (`?id=`, fast) to attach licence name/family to retained
  identifier rows at larger scale (still bounded), and measure how much of the gap it closes.

---

## Phase 5 — research evidence beyond registration

**5.1 Publication / trial connectors (contract already defined)**
- Add OpenAlex + Europe PMC + ClinicalTrials.gov using the same six-operation contract.
- Link to devices only as `POSSIBLE_MATCH` via sponsor/company + technology terms; never
  `STUDIED_IN` without an explicit device mention and a human-checkable rule.

**5.2 Human adjudication of candidates**
- The 44 `POSSIBLE_MATCH` and 7 `RELATED_TECHNOLOGY` candidates are exactly the set a person
  should review. Build a small adjudication worksheet (reuse the repository's review-workbench
  pattern) and record human labels separately from machine labels.

**5.3 Prospective evaluation protocol**
- The registry already timestamps candidates. Pre-register an evaluation: after N months,
  check which candidates acquired a second-market registration; report base rates and
  confidence intervals, not just hits. Include a time-placebo control.

---

## Phase 6 — scale and operations

| Item | Trigger | Note |
|---|---|---|
| Monthly snapshot + drift report | after 2 stable runs | store `source_status`, version counts, duplicate rates; detect API schema drift |
| 10 firms / 5 markets | identity bridge stable | keep the curated alias registry reviewed; do not auto-expand aliases |
| Indexed traversal > 3 hops | only if a research query needs it | do not introduce a graph database pre-emptively |
| Raw payload store | only for open-licence sources | content-addressed, git-ignored, retention policy documented |
| UI integration (PR #12/#13) | after query contracts freeze | the CLI JSON is the contract; the UI is a client |

---

## Explicit non-goals for the next phase

- No LLM or QLoRA training (PR #19/#20 remains a separate research track).
- No Neo4j / distributed services / commercial cloud database.
- No prediction claim or accuracy target. The identity and evidence substrate comes first.
- No bulk merge of the 197k–260k-line research branches.
- No scraping of EUDAMED/NMPA without an explicit access decision.

---

## Definition of done for the identity programme

A future round may claim "cross-market device identity" only when:

1. at least two independent official identifiers (not two interfaces over one registry) agree;
2. the relation has evidence rows, clocks and a written basis;
3. a sample is checked against the official records by a second process or a person;
4. coverage (what fraction of each registry can be bridged) is reported alongside the count.
