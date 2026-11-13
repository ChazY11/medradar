# PHOENIX-003 — Scientific conclusion

Three kinds of statements, kept apart on purpose: **F** = a fact established by a committed,
re-runnable artefact; **H** = a hypothesis that the data do not settle; **U** = an unknown that this
round could not resolve. A number quoted here with an **F** is reproducible with
`code/run_pipeline.py` and appears in `results/*.json`.

---

## 1. Facts

**F1. The regulatory corpus can be reduced to an unambiguous milestone identity.**
177,948 canonical device milestones survive from 233,838 raw rows: 176,466 510(k) records keyed by
`k_number` and 1,482 original PMA approvals keyed by `pma_number`. Repeated official identifiers:
**zero**. Repeated (applicant, name, decision date, product code) natural keys: 162 groups / 174
extra rows (0.10 %). 55,890 PMA rows (97.4 % of all PMA rows) are **supplements**, not milestones,
and removing them changes the PMA series by a factor of ~39. Any analysis that counts PMA rows as
"approvals" is 39× wrong about PMA activity. *(F: `results/a1_canonical.json`)*

**F2. Firm attribution can be made reproductive and refused where it is not known.**
A token-equality brand-lineage rule attributes 12,230 milestones to 13 firms with 90.7 % of the
resulting anchors also passing a strict name-position rule, and leaves 93.1 % of all store
applicants `UNKNOWN` rather than imputing them. Pre-acquisition applicants (`Covidien`,
`Spectranetics` before 2017, `Biomet`, `Guidant`) are refused, so no milestone is back-projected
onto today's owner. *(F: `results/a1_canonical.json`, `dataset/firm_lineage.json`)*

**F3. First-in-code milestones give a sampling frame in which every unit can in principle have
earlier evidence.** 269 anchors (59 core + 210 extension), 2015–2024, 249 product codes, all with
at least one firm record inside the 5-year evidence window. This closes the "structurally
impossible negative" defect that invalidated PHOENIX-002. *(F: `REGULATORY_ANCHORS.jsonl`)*

**F4. Keyword matching is vacuous on this data.** A firm-mention-or-generic-device-term baseline
"finds earlier evidence" for **99.2 %** of anchors, with a median apparent lead of **1,821 days** —
longer than the anchored method's 1,620 days. Lead time computed this way is a restatement of the
firm's publication rate. *(F: `results/c_controls.json`)*

**F5. The anchored method's apparent lead time is not distinguishable from a matched wrong
pairing or a shifted date.** Decoys (same firm, ±2 years, different product code) link at 51.4 %
(pooled) and 6.4 % (strict class) against real rates of 69.9 % and 11.6 % — specificity 1.37 and
1.81 on a matched denominator. Time-shifted anchors reproduce the link rate (p = 0.51) and the
median lead (p = 0.53); date permutation gives p = 0.72 / 0.88. *(F: `results/c_controls.json`,
`results/verdict.json`)*

**F6. Most "early evidence" is follow-up study of already-regulated devices.** 5,315 of 5,760
verified rows (92.3 %) are about a product that already had an FDA record when the evidence was
published; only 445 are pre-regulatory, and **211 rows declare a prior approval in their own
title** (post-approval, post-market, continued-access). Without that distinction the round would
have over-claimed by a factor of roughly seven in the strict class (186 vs 28).
*(F: `results/b2_novelty.json`)*

**F7. Only 28 milestones have a public record that is simultaneously product-specific,
literature-rare, verifiable and pre-regulatory; 24 of them rest on unambiguous proprietary
names.** Median lead 1,317 days, range 28–1,815, maximum bounded by the frozen 5-year window. These
are existence facts a human can check one by one, not a rate.
*(F: `results/d_leadtime.json`, `EVIDENCE_LINKS.jsonl`)*

**F8. When the evidence exists, a hindsight-free query usually reaches it — at a real cost.**
A frozen query built from the product code's *generic* name surfaces the eventual evidence for
82.3 % of the 186 anchors, but the median retrieval set is 124 records (IQR 54–357) and 33 anchors
are hindsight-only. *(F: `results/d_leadtime.json`)*

**F9. The method is stable across firms and years.** Leave-one-firm-out link rate ≈ 65 %–71 %;
the largest product-code contribution is ~2 %; no year drives the result. The NO-GO is therefore a
property of the instrument, not of a subset. *(F: `results/c_controls.json`)*

## 2. Hypotheses the data do not settle

**H1. *"There exists a class of milestones for which public evidence is genuinely early and
could be identified in advance."* The data neither confirm nor exclude it.** The 24 named cases are
consistent with it; the decoy/placebo results forbid generalising from them. A design that starts
from the *evidence* (a paper or trial about a device that has no regulatory footprint yet) and waits
forward is the only way to test it — see `NEXT_EXPERIMENT.md`.

**H2. *"Publication-led firms (imaging, diagnostics) leak more than procedure-led firms."* Not
testable here.** The strict cases are dominated by Medtronic/Abbott/Boston Scientific/Edwards/BD;
GE HealthCare and Philips anchors are too few to compare, and Dräger/Mindray have no measurable
publication footprint at all (42 and 234 EPMC records respectively).

**H3. *"The 5,315 pre-existing-product links still carry information — they are extension studies
of products that later grew into new indications."* Plausible, untested, and outside this round's
question.**

## 3. Unknowns this round could not resolve

**U1. Observation time.** The store is a single 2026-10-30 snapshot: `available_at` equals the event
date and `fetched_at` spans two days. No claim about what an observer could have *seen on a given
day* can be verified from it. Every date used is a metadata publication date.

**U2. True identity of a semantic match.** Token identity is machine-checkable; "same technology" is
not. The 28 cases carry enough provenance for a human to adjudicate, and that adjudication has not
been done. No precision/recall/F1 is reported anywhere in this round because there is no
gold-standard label set.

**U3. Coverage of non-510(k)/PMA pathways.** HDE approvals, De Novo grants and device recalls are
absent or partial in the store. A product with an earlier HDE (the Melody case) looks new here.
This is an identified, quantified source of error for small-volume devices.

**U4. Firm identity of 93 % of the market.** Attribution covers 13 firms by design; the rest is
`UNKNOWN`. Nothing here can be said about the other device firms.

**U5. Whether the "lead" is a lead from the applicant's perspective.** A product can be discussed in
public before its US clearance because it was cleared in Europe, Japan or China first. The corpus
does not contain non-US regulatory registers, so "public before the FDA milestone" cannot be
separated from "already approved elsewhere".

## 4. What this round changes for MedRadar

1. **The headline claim "we detect technical activity ahead of regulatory milestones" must not be
   made.** It is reproducible *at a rate*, but that rate is what a wrong pairing produces.
2. **Two instruments are now available and reusable**: the canonical anchor builder (identifier-
   based dedup, lineage attribution with `UNKNOWN`, first-in-code frame) and the control battery
   (keyword baseline, decoy, time placebo, pre-regulatory split, literature-rarity). The second is
   the more valuable one: it is the thing that makes an early-signal claim falsifiable.
3. **The base rate is now measured**, which converts a vague worry into a number: a large device
   firm supplies a product-named public record inside any 5-year window for ~70 % of its milestones
   under the pooled rule, ~54 % under a deliberately mismatched pairing.
4. **The strict class — 28 cases — is the only defensible positive asset** from this round, and it
   should be treated as a curated case library to be adjudicated by humans, not as a statistical
   finding.

## 5. One-paragraph judgement

PHOENIX-003 set out to find whether independent public sources reveal a device firm's technical
activity before its regulatory milestones. It built the trustworthy anchor set that the previous
two rounds lacked, measured the question properly for the first time, and produced a **rigorous
negative**: the apparent ~4.4-year median lead is not distinguishable from the background rate at
which large device firms publish product-named records, and 92 % of the "evidence" is follow-up
study of products that were already on the market. The round's positive assets are methodological (a
reusable anchor-and-control instrument that demonstrably destroys naive claims) and a curated
28-case library of genuine pre-regulatory public evidence, 24 of which rest on unambiguous product
names. It is 成果 B and 成果 C of the brief, with a bounded, honestly-labelled subset of 成果 A.
