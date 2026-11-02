# MedRadar — Global MedTech Intelligence & Foresight

**Global MedTech Intelligence & Foresight · 全球医疗器械产业智能与技术前瞻**
**Status:** living document. Realigned 2026-11-02 (see `DECISIONS.md` D-011). Supersedes the
previous framing of this project as primarily a forecasting-model research program.
**Revision history:** v2 (2026-11-02) realignment — Observe / Understand / Anticipate.

## 1. Mission

Build an **evidence-grounded industry-intelligence and technology-foresight system for the
world's leading medical-device companies** — and, through it, produce scientific knowledge
about how corporate technological change actually happens and how early it can be seen.

Core research objective: by systematically tracking regulatory, product, patent, research,
financial, procurement and other public activity of medical-device firms, **notice changes in
technology positioning earlier than conventional industry research, explain what they mean with
traceable evidence, and form evidence-supported judgements about what may come next**.

Explicit scope boundaries (these are commitments, not aspirations):

- We do **not** attempt to predict the entire global industry.
- Inventing a complex AI forecasting algorithm is **not** the project's purpose.
- The primary object of study is **the leading medical-device firms and the technological and
  strategic evolution they are actually undergoing**.
- MedRadar is **first** a serious industrial-technology research project, and **second** an
  AI-application and forecasting-model project.

## 2. Unified research architecture

All work must serve one of three ascending layers. A task that serves none of them does not
belong in the backlog.

### Layer 1 — OBSERVE · 更早、更全面地发现变化

*What technological change is happening inside the leading firms?*

- FDA, clinical-trial, product-registration and recall monitoring.
- Patents and research output.
- Product-family and technology-track mapping.
- Financials, R&D spend, and business-mix change.
- Hospital procurement and market demand.
- R&D hiring and technical-team change.
- M&A, partnerships and technology investment.
- **Cross-company anomaly detection** of technology activity.

The point is **not** to add more data. The point is to surface real changes a human analyst
would miss. The system must be able to answer: is a company suddenly entering a new area? Is a
technical direction showing sustained activity growth? Are several competitors moving into a
similar area at once? Is something moving from research into products? Is a company's product
portfolio changing structure?

**It must distinguish genuine technological change from ordinary product refresh, data-source
fluctuation and regulatory statistics noise. This is the first priority.**

### Layer 2 — UNDERSTAND · 解释变化及其意义

*Why does this change matter, and what trend does it reflect?*

Capabilities: corporate technology knowledge graph · cross-source entity resolution · product and
technology taxonomy · evidence fusion · research-hypothesis generation · contradictory-evidence
discovery · company R&D profiles · competitive technology mapping.

The system must not stop at "company A had 10 new regulatory events". It must establish *which*
technical directions changed and how the change relates to historical capability, competitor
activity, market demand and R&D resources.

**Every material judgement must carry:** (1) raw evidence, (2) data source, (3) timing
information, (4) the technology-classification basis, (5) supporting evidence, (6) contradictory
evidence, (7) uncertainty and research limitations.

LLMs may assist with research, evidence organisation and hypothesis generation — but **may never
invent facts, citations or determinate conclusions**. The system should behave like a rigorous
medtech industry analyst, not a summarising chatbot. **Second priority.**

### Layer 3 — ANTICIPATE · 形成可靠的技术前瞻

Level A — identify trends that are forming. Example form: *"company X appears to be strengthening
its position in technology area Y; no product has launched, but multiple independent evidence
types agree."*

Level B — forecast verifiable future events. Example form: *"probability that company X produces
a verifiable regulatory milestone in technology area Y within 12–24 months."* Requires strict
train/backtest discipline and probability calibration.

**Level A comes first.** Algorithmic complexity must never be bought by weakening the underlying
fact-monitoring capability.

## 3. Research scope

Personal research team; limited compute, budget and manual-labelling capacity.

**Deep-case companies (5, mandated):** Medtronic · GE HealthCare · Philips · Dräger · Mindray.
Adjusted only for real data coverage and technical comparability, with the change recorded.

**Comparison companies:** a retained set of other leading firms used for technology-layout
comparison, competitive-change detection, statistical baselines, historical sample size and
generalisation testing. Equal research depth is **not** required for all of them.

**Granularity:** `Company × Technology/Product Family × Time`. Company-level revenue or share
price must **never** be mapped to a specific product family without justification.

## 4. Priorities (P0–P4)

Superseding the previous ordering (see `ROADMAP.md` for the phase plan):

- **P0 — Scientific reliability.** Data truthfulness, entity-matching accuracy, device-technology
  classification, temporal consistency, provenance, reproducible statistics and experiments,
  false-positive and bias control. If the foundation is wrong, fix it first.
- **P1 — Advanced technology change detection.** Technology-layout change detection; product-family
  first-entry identification; technology-portfolio migration; abnormal R&D activity detection;
  cross-company technology-trend comparison; multi-source weak-signal fusion. **This is
  MedRadar's most important new capability.**
- **P2 — AI research intelligence.** Company R&D profiles; evidence-driven research reports;
  cross-domain knowledge linking; scientific hypothesis generation; automatic counter-evidence
  search; auditable research conclusions. Value is depth, accuracy and efficiency — not report count.
- **P3 — Forward-looking forecasting research.** Point-in-time snapshots, future-milestone
  prediction, baselines, ablation, forecast registry, genuine prospective validation. Continues as
  a long-term program and does not outrank P0–P2.
- **P4 — Advanced algorithm research.** Temporal graph learning, dynamic knowledge graphs,
  multimodal temporal models, evidence-aware forecasting, causal designs — only once data and
  baselines justify them. Complexity must be driven by experimental need.

## 5. Intended scientific contributions

**A — High-quality cross-source technology knowledge representation.** Reliable linking of
companies, subsidiaries, product families, technology domains, patents, regulatory approvals,
clinical trials and commercial activity, with explicit entity alignment, technology
classification, temporal constraints and evidence uncertainty.

**B — Early identification of emerging technologies and strategic redirection.** Detecting weak
but real technology-turn signals from multiple public sources. Measured by detection accuracy,
lead time, false-alarm rate, cross-company generalisation and robustness to data-quality change.

**C — AI-assisted, verifiable industry-research methodology.** Can an intelligent system find,
link and explain evidence that is otherwise scattered? Evaluation must rely on verifiable
evidence, human-labelled samples and comparator methods.

**D — Anticipatory forecasting of corporate R&D trends.** Retains the historical forecast
benchmark, cross-domain ablation and probabilistic models; pursued deeply only when experiments
show value.

The standard for a contribution is **new, credible, externally checkable knowledge** — not more
features.

## 6. What we are deliberately NOT doing now

Unless a research reason and explicit authorisation appear: general global industry prediction;
cross-industry technology digital twins; full macroeconomic forecasting; large-scale equity
trading strategies; training large language models from scratch; AI infrastructure unrelated to
medtech research; unverifiable speculation about internal corporate R&D; large visualisation
platforms without research value; simultaneously ingesting many data sources of unverifiable quality.

The existing financial event-study and paper-trading features are **maintained but are not the
core direction** of this program.

## 7. Epistemic rules (unchanged, still binding)

1. **Forward-only evidence.** Every claim states its knowledge cutoff; no feature may use
   data published after it. `event_date`, `published_at`, `first_seen_at`, `available_at` and
   ingestion time are distinct and never conflated.
2. **Verifiable statements only.** No "company X is secretly developing Y". Claims must be
   checkable against future public events or against a labelled benchmark.
3. **Baselines before models.** Historical-frequency and no-feature baselines precede any learned
   detector or forecaster; complexity is not evidence of skill.
4. **Detection is not causation.** Neither a detected change nor predictive skill identifies a
   mechanism. Causal language requires an identification design.
5. **Failure is a result.** Unreproducible experiments, detectors that do not beat baselines,
   sources that add no information, unstable estimates, rejected hypotheses and negative findings
   are recorded and published.
6. **No fabricated numbers or citations, ever.** Every number traceable to a committed artifact or
   a re-runnable command; every null carries its minimum detectable effect.
7. **Pre-register the test.** Evaluation windows and primary metrics are fixed before modelling and
   are not re-chosen to improve results.
8. **Human judgement is not replaced.** The system surfaces changes and evidence; it does not
   claim to know the future or to substitute for a scientist's judgement.

## 8. Success criteria (redefined)

Not: GitHub stars, lines of code, number of APIs, dashboards, model parameters, auto-generated
report count.

Instead:

1. Are company and technology classifications accurate?
2. Can the system identify real, non-obvious technology-layout changes?
3. Is the evidence complete and traceable for every claim?
4. Does it find changes earlier than simple methods?
5. Does it reduce research false positives?
6. Do new models actually improve analysis quality?
7. Can the method be reproduced?
8. Does it produce empirical findings worth public discussion?

A paper demonstrating a new **early technology-change detection method** would satisfy this
mission even if it never predicted a product launch.

## 9. Honest position as of 2026-11-02

What is already established (evidence in `RESULTS/`):

- The temporal foundation is real and audited: bitemporal knowledge store, immutable forecast
  registry, deterministic point-in-time export, independent leakage replay (0 mismatches over
  656,048 values).
- A deterministic legal-entity universe now exists (9,412 entities, no fuzzy matching), and the
  two roster-absent mandated case companies (Dräger, Mindray) are resolvable.
- Forecast-side (Anticipate, Level B): continuation of active pairs is not detectably better than
  per-pair persistence; first entry into a dormant track is *weakly* predictable and the cycle-1
  negative was partly a coverage artefact (cycle 2: ΔAP +0.0973, 3/3 windows exclude zero, MDE
  0.0877). No forecast has matured, so there is **zero** calibration evidence.
- The **OBSERVE layer — which this document makes the first priority — has no validated change
  detector yet.** That is the current frontier and the current bottleneck.
