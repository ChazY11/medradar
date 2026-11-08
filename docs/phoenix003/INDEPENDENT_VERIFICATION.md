# PHOENIX-003 — independent verification

Verifier: independent reconstruction (own scripts, own resolver, own tokenizer, own linker,
own novelty classifier; nothing imported from `experiments/phoenix003/code/` except for one
read-only cross-check of the *author's* tokenizer output, reported as such).

- Worktree: `D:\DEPPSKK\worktrees\phoenix003`, branch `research/phoenix-003-early-evidence`.
- Raw inputs only: `data/medradar.sqlite` (opened `file:...?mode=ro`, never modified),
  `experiments/phoenix003/dataset/{ctgov,ctgov_ext,epmc,epmc_ext}_compact.jsonl.gz`,
  `dataset/firm_lineage.json`, `dataset/frozen_vocab.json`, `FROZEN_RULES.json`.
- My scripts: `experiments/phoenix003/verify/` (`vcommon.py`, `verify_anchors.py`,
  `verify_anchor_state.py`, `verify_attribution.py`, `verify_links.py`, `verify_novelty.py`,
  `verify_verdict.py`, `verify_case.py`, `verify_case_live.py`, `make_run_log.py`).
- Full transcripts: `experiments/phoenix003/verify/verify_run.log`.
- No git write command was run; nothing under `code/`, `fetch/`, `dataset/` or `results/` was
  modified.

## 0. Artefact states actually verified (the tree moved four times)

The author's pipeline was re-run while this verification was in progress. I snapshotted each
state before it could be overwritten (`verify/committed_snapshot/`, `verify/run2_snapshot/`,
`verify/run3_final_snapshot/`, each with `SNAPSHOT_FILES.json` of sha256s).

| state | time (local) | anchors | links | status |
|---|---|---|---|---|
| SNAPSHOT | 04:16:48–04:26:50 | 268, `REGULATORY_ANCHORS.jsonl` sha `3733be…` at A1 time → later rewritten by B2 | ctgov-core only (1,802 records); no EPMC, no extension corpora | **provisional**, superseded |
| RUN1 | 04:57:26–05:00:44 | 269 | all four corpora; k=**151** because `EVIDENCE_LINKS.jsonl` truncated verified rows | internally inconsistent, superseded |
| RUN2 | 05:03:15–05:04:58 | 269, sha `80be6bbe…` | sha `00d8072d…`, k=**187** (cap now declared) | first complete all-corpus state |
| RUN3 FINAL | 05:07:34–05:10:02 | 269, sha `80be6bbe…` (**unchanged**) | sha `43a2e27d…`; 10,296 rows, emitted verified 4,926 (108 L1 + 4,818 L2), k=**187** | **final state; all headline values identical to RUN2** |

RUN3 FINAL is pinned by `verify/run3_final_snapshot/` (`manifest.json generated_at
2026-11-08T21:10:02Z`, all stages rc=0, including the new `freeze_epmc_df` stage). It adds the
Amendment-5 literature-rarity annotation (`literature_rare` field in `EVIDENCE_LINKS.jsonl`,
`L2_strict_literature_rare = 28` in `d_leadtime.json`), and re-froze `FROZEN_RULES.json`
(sha `9fef22b3…`, which adds **only** `name_vocab.literature_rare_max_epmc_df = 200` and
`literature_rarity_corpus`; every anchor/evidence/verdict/stat threshold is unchanged) and
`FROZEN_PROTOCOL.md` (Amendment 5 appended at 05:11:24, timestamped and disclosive). The anchor
file, `b_links` tier counts, `b2_novelty` counts, `c_controls` and `verdict` values are
**identical to RUN2**; I re-ran the link and verdict verifiers against RUN3 and obtained the same
result (187/187 anchors, 0 lead differences, NO-GO). The numbers below are therefore verified for
both RUN2 and RUN3; the SNAPSHOT numbers are reported because they were the artefacts in place
when verification began and because their failure mode explains the later changes.

## 1. Anchor construction

### 1.1 Store-only counts (identical from the store in every state)

| quantity | my count | committed (`a1_canonical.json`) |
|---|---|---|
| raw `510k` rows | 176,466 | 176,466 |
| raw `pma` rows | 57,372 | 57,372 |
| PMA rows that are supplements | 55,890 | 55,890 |
| — supplement decision codes | OK30 28,000 / APPR 27,749 / APRL 141 | same |
| canonical milestones (`K`+k_number; `P`+pma_number where supplement empty) | **177,948** (176,466 + 1,482) | 177,948 |
| distinct `k_number` / repeats | 176,466 / 0 | 0 repeated keys |
| distinct `(pma_number, supplement_number)` / repeats | 57,372 / 0 | — |
| distinct `pma_number` (all rows incl. supplements) | 1,753 (1,578 pma_numbers have >1 row; 55,619 extra rows) | — |
| distinct `pma_number` originals | 1,482 / 0 duplicates | — |
| distinct `milestone_key` / repeats | 177,948 / **0** | 0 |
| natural-key collisions (applicant, name, date, product code) | 162 cases / 174 extra rows | 162 / 174 |
| attributed milestones (13 firms, brand-token rule) | 12,230 (unknown 165,718, rate 0.931272) | 12,230 / 0.931272 |
| per-firm attribution (all 13) | exactly the a1 values | exactly the a1 values |

So the canonical-milestone layer and the attribution totals are **exactly reproduced**.

### 1.2 Anchors: 268 vs 269 — the brand-token/vocabulary state

My reconstruction (filters → first-in-(firm,product-code), FROZEN_RULES window 2015-01-01…2024-12-31,
substantive decision codes, distinctive-token filter) reproduces **both** committed anchor sets
exactly, but only when the tokenizer state is chosen correctly:

| state | tokenizer | anchors | identical to committed | funnel identical |
|---|---|---|---|---|
| SNAPSHOT | brand tokens of the **5 core firms** excluded (Amendment 1 as written) | 268 | **268/268**, anchor_id 268/268, tokens 268/268 | **yes, all 11 funnel numbers** |
| RUN2 | **all 13 firms'** brand tokens excluded (current `frozen_vocab.json`, 22 tokens) | 269 | **269/269**, anchor_id 269/269, tokens 269/269 | **yes, all 11 funnel numbers** |

Funnel reproduced exactly (SNAPSHOT / RUN2): milestones 177,948/177,948; attributed 12,230/12,230;
excluded decision code 393/393; after decision code 11,837/11,837; excluded missing product code
59/59; after product code 11,778/11,778; excluded for no distinctive token **796/891**; after token
**10,982/10,887**; (firm,code) cells **2,249/2,233**; anchors **268/269**.

The delta between the states is exactly three anchors, and every one is explained by the
brand-token rule, not by data:

- `edwards_lifesciences/OMZ/K153069` (“Edwards Balloon Catheter”, 2016-01-07) is in SNAPSHOT only:
  its sole committed distinctive token is the brand token `EDWARDS`, which the current frozen
  tokenizer removes; the record then has no distinctive token and the cell yields no anchor.
- `stryker/DZL/K231599` and `stryker/OWN/K173866` are in RUN2 only: the earlier pre-window records
  in those cells (`K050535` 2005, `K142310` 2014) carried only the brand token `STRYKER` under the
  old tokenizer, so they entered the cell as “first” and their dates fell outside the window,
  killing the cell. With `STRYKER` excluded those pre-window records drop out of the token filter
  and the 2023/2018 records become the first token-bearing milestones.

Committed SNAPSHOT anchors whose token list contained a brand token: **9** (`EDWARDS` ×6,
`STRYKER` ×2, `ABBOTT` ×1). RUN2 removes those (8 anchors keep other tokens; 1 anchor disappears).
This was a genuine state/timing defect in the artefacts that existed when verification began —
the SNAPSHOT anchor file could not be reproduced from the frozen inputs the study claims to use —
and it is fixed in RUN2.

## 2. Entity attribution

- 15 deterministic spot checks (round-robin across all 13 firms, `verify_attribution.py`):
  all 15 OK.
- Full scan of the 269 RUN2 anchors: **0** resolver mismatches, **0** applicants carrying two
  firms' brand tokens, **0** GE/BOSTON qualifier false positives.
- 18 applicants are parenthetical re-brandings of acquired entities (`Covidien (Part of Medtronic)`,
  `St. Jude Medical (Now Abbott Medical)`, `Novadaq … (Now A Part of Stryker)`,
  `Bard Access Systems … subsidiary of Bd`, etc.). Using analyst-known acquisition close dates,
  **0** are dated before the close (Bard/Becton Dickinson closed 2017-12-29, not 2023).
- **Disagreement — two different firms on one token:** `Zimmer Medizinsysteme GmbH` is an
  independent German physical-therapy/electrotherapy manufacturer, not a Zimmer Biomet entity.
  Three RUN2 anchors are misattributed to `zimmer_biomet` on the `ZIMMER` token:
  `KK161862` (2016-11-14, “ThermoPro”, IMJ diathermy), `KK182963` (2019-06-21, “emFieldPro”, NGX
  muscle stimulator), `KK213256` (2023-05-25, “ThermoTK”, PBX vacuum/RF heat massager).
  Impact: anchors 269 → 266 if corrected; **zero** verified links hang off these three anchors,
  so `k` and the verdict are unaffected (their adjudicated `distinctive_tokens` are
  `THERMOPRO`/`EMFIELDPRO`/`THERMOTK`, which also do not appear in the corpora).
- Philips non-medical divisions are retained by the frozen rule and flagged in the lineage file:
  e.g. `Philips Consumer Lifestyle` (breast pump, TENS), `Philips Electronics Nederland`
  (BlueControl light device). These are Philips products, not false attribution.

## 3. Link tiers and lead times

Protocol §6.1 re-implemented from the frozen text: firm lineage on the evidence record
(`lead_sponsor`/collaborators for CT.gov, `firm_affiliations` for EPMC), exact whole-token identity
of an anchor `distinctive_token` (taken verbatim from the anchor file) with the record's
intervention name/title (CT.gov) or title/abstract (EPMC), evidence date strictly before the
milestone and inside `[a−5y, a−1d]`. L1 = identifier chain through an NCT id present in the
firm's own CT.gov corpus plus the same token identity.

| | SNAPSHOT (ctgov-core only) | RUN2 (all four corpora) |
|---|---|---|
| committed verified rows in `EVIDENCE_LINKS.jsonl` | 213 (L1 0, L2 213) | 4,926 (L1 108, L2 4,818) |
| `b_links.json` verified tier counts | L1 0, L2 213 | L1 108, L2 6,424 |
| rows capped out of the file | 0 | **1,606 L2** (declared: `__emission_capped_l1l2: 1606`) |
| anchors with ≥1 verified link (`k`) | **33** | **187** |
| my anchor-level reproduction | 33/33 identical, 0 lead differences, 213/213 rows identical | 187/187 identical, **0 lead differences**, 4,926/4,926 emitted rows identical; my 6,532 = committed 4,926 + exactly the 1,606 declared capped rows |
| share of `k` with lead ≥90 d | 0.969697 | 0.989305 |
| median / max lead | 1,396 / 1,805 d | 1,625 / 3,512 d |
| per-firm coverage | ctgov only covers the 5 core firms; extension firms 0 records | 269/269 anchors have ≥1 firm-verified record in window |

RUN2's `d_leadtime.json` is now internally consistent with `b_links.json` (k=187); RUN1's was not
(k=151) because the emission cap dropped whole anchors — that was fixed in RUN2.

Two implementation deviations from the frozen protocol remain:

1. **L1 is not constrained by the 5-year evidence window.** `b_links.py` assigns `VERIFIED_L1`
   before the `w_start` test, so **28 of 108 L1 rows lie outside `[a−5y, a−1d]`**. Protocol §5
   defines the evidence window as `[a−5y, a−1d]` and §6.1's L1 requires “the evidence-side name
   identity of VERIFIED_L2”, so whether L1 is exempt from the lower bound is ambiguous; the code
   treats it as exempt. If §5 applies, the reported max lead **3,512 days** (medtronic
   `PP220026`/`SYMPLICITY` EPMC 24858423, 2014-05-20 vs PMA 2023-11-17) and the 3,468-day case in
   `EXPERIMENT_RESULTS.md` §6 are not like-for-like with the L2 leads and should carry a window
   caveat. No anchor is lost either way.
2. **EPMC matches keywords and MeSH terms, not title/abstract.** `b_links.py` builds the EPMC index
   from `all_tokens = title+abstract+keywords+mesh`, while §6.1 says “title or abstract”.
   **502 of the 4,926 emitted verified rows (10.2%)** exist only because of keywords/MeSH; under
   the protocol-literal reading `k = 186` (not 187) and 18 anchors have a different max lead;
   one anchor (`edwards_lifesciences/KK163381`, token `SWAN`) loses its only link.

Protocol-field (`title+abstract`) and author-field (`all_tokens`) views otherwise agree, so the
linker itself is faithfully re-derived; these are specification deviations, not implementation
mistakes.

## 4. Novelty / pre-regulatory classification

For a link with token `T` published at date `d`: `PRE_REGULATORY` iff no canonical 510(k)/PMA
record of any applicant whose record name contains `T` has decision date ≤ `d`. Token history
rebuilt from the store: 177,948 milestones → 56,780 tokens.

| | SNAPSHOT | RUN2 committed | RUN2 full verified set (6,532 rows) |
|---|---|---|---|
| rows PRE_EXISTING / PRE_REGULATORY | 202 / 11 | 4,538 / 388 | 6,014 / 518 |
| anchors with ≥1 PRE_REGULATORY link | **6** | **35** | 35 |
| anchors with product-specific PRE_REGULATORY link | **5** | **32** | 32 |
| Target-B novel / with verified link | 19 / 1 | 21 / 7 | — |

All committed values, row-level `regulatory_status` and `product_specific` flags are reproduced
with **0 mismatches**; the anchor-level counts on the full set equal the committed ones
(35/32), and only the row counts are reduced by the emission cap (388 vs 518). Target-B flags
also reproduce exactly (21/7).

**Substantive disagreement with the label, not with the arithmetic.** The store has no
HDE/IDE event kind (event kinds: `510k, pma, trial, recall, drug_approval, 8k_catalyst`), so a
prior HDE/IDE approval is invisible to the rule. Among the PRE_REGULATORY rows, **5 rows
(4 product-specific)** are self-declared *post-approval / post-market studies* — by construction
follow-up of a device that was already approved. The three most quotable examples:

- SNAPSHOT top case: medtronic `PP140017`/`MELODY`, CT.gov `NCT01186692`, 2010-08-23, lead 1,618 d
  — title “Melody® Transcatheter Pulmonary Valve **Post-Approval** Study”; the official title says
  “A **Post-Market Approval** Study”. The Melody valve was approved under FDA HDE H070003 in 2006
  (analyst knowledge; not in the store). On the frozen latest-plausible clock (`last_update_posted`
  2019-05-01) the lead is **−1,555 days**.
- Among the *admissible* (inside-window) cases the highest lead is the spurious `OVERALL` match
  described below; the highest-lead admissible case carried by a genuine product token is
  boston_scientific `KK172565`/`OBTRYX`, CT.gov `NCT01784588`, 2013-02-06, lead 1,778 d — title
  “**Post Market** Study Of Single Incision Sling…”. Same failure mode.
- Token over-breadth: the frozen tokenizer admits ordinary English words as “distinctive” when
  they happen not to be in the device-name generic vocabulary. The RUN2 protocol-legal top
  product-specific PRE_REGULATORY link is medtronic `KK233838`/token **`OVERALL`** (EPMC 30931726,
  2019-04-01, lead 1,823 d) — the word “overall” in a drug-coated-balloon abstract matched
  “(Overall System Name)” in a microwave-ablation 510(k). `applicant_df = 1` made it
  `product_specific = True`. **The author independently found this and disclosed it**: Amendment 5
  (protocol §12, appended 05:11:24) adds a literature-rarity filter (`literature_rare_max_epmc_df =
  200`) and removes `OVERALL`, `EFFICIENT`, `ORGANS` and a `BULK` variant from the strict ladder
  (32 → 28). My independent check confirms the diagnosis and the arithmetic; it adds that the
  residual strict cases still include ordinary words (`TETHERING` 13 docs, `CAPTURING` 83,
  `POLYSACCHARIDE` 81 — flagged by the author for human adjudication) and that the *pooled* and
  *product-specific* levels (35 / 32 anchors) are unchanged, so `product-specific` still means
  “used in ≤3 applicants’ device names”, not “identifies the product”.

(The 5 post-approval rows above are counted on the full verified set; the committed file
carries the same 35/32 anchor-level classification.)

So the *counts* 35/32 are correct for the rule as implemented; the interpretation “the
information existed before the product had any regulatory footprint” is not established for an
unknown fraction of them, and is demonstrably false for the top examples.

## 5. Verdict arithmetic

Verdict tree re-implemented from `FROZEN_RULES.json → verdict`; `k`, share≥90, firm/year counts
recomputed from the committed links; specificity from `c_controls.c3_decoy` (real/decoy counts
re-derived from `c3_decoy_rows`); placebo p taken from `c4b_date_permutation`.

| gate | SNAPSHOT | RUN2 | committed verdict |
|---|---|---|---|
| coverage | 56/268 = 0.208955 (<0.8 → BLOCKED) | 269/269 = 1.0 | — |
| k | 33 | 187 | 187 (RUN2), 151 (RUN1, wrong) |
| share lead ≥90 d | 0.969697 | 0.989305 | same |
| specificity | 1.9625 | **1.299** | same |
| placebo p (median lead) | 0.588822 | **0.832335** | same |
| firms / years | 3 / 10 | 11 / 10 | same |
| GO? | no (spec, placebo p, firms) | **no (spec 1.299 < 5.0; placebo p 0.832 > 0.05)** | — |
| LIMITED GO? | no | **no (spec 1.299 < 3.0; placebo p 0.832 > 0.10)** | — |
| my verdict | **BLOCKED** | **NO-GO** | `verdict.json`: BLOCKED / NO-GO respectively |

The committed verdict is **correct** in both states: under the frozen tree BLOCKED (coverage <80%)
precedes the other gates, and in RUN2 the coverage gate passes but the substantive gates fail.
Even if the BLOCKED branch were ignored, the numbers are NO-GO, not LIMITED GO. The verdict is
robust to every independent reading I tried (protocol-field linker k=186 → still NO-GO).

Independent control arithmetic: C1 keyword baseline links **267/269 = 99.3%** of anchors vs C2
anchored method **187/269 = 69.5%** — the naive baseline the protocol names as the floor links
almost everything, so the anchored method adds no discriminative value on this outcome; §10 lists
this as a NO-GO condition. Decoy link rate 137/256 = 0.535, i.e. specificity 1.30, far below GO.

Defects in the reporting (not the verdict): `c3_decoy.specificity_note` still claims “decoy link
rate is zero … specificity … null”, contradicting the object's own values (0.535156 / 1.299);
`c4b_date_permutation.draws = 500` although `FROZEN_RULES.controls.c4_placebo.permutations = 2000`
(`c4a` does use 2000); the specificity ratio mixes denominators (real over 269 anchors, decoy over
256 → 1.2990; matched denominator gives 1.3066). None of these changes the verdict.

## 6. Case audits (end-to-end)

All mechanical checks below were run against the raw store and the frozen corpora
(`verify_case.py` for the SNAPSHOT Melody case, `verify_case_live.py` for the RUN2 cases).

**Case A — the study's largest product-specific PRE_REGULATORY lead (RUN2):**
medtronic `PP220026` (QYI) / token `SYMPLICITY` / EPMC `24858423` / 2014-05-20 / 3,468 d.
Milestone P220026 original APPR 2023-11-17 ✓; first-in-code ✓; record in `epmc_compact` with
exact date/title ✓; token in title/abstract ✓; Medtronic affiliations ✓; earliest `SYMPLICITY`
regulatory record 2023-11-17 > evidence date ✓; L1 chain NCT01418261 → “SYMPLICITY HTN-3” ✓.
**But**: evidence 2014-05-20 is **outside** `[2018-11-17, 2023-11-17)` — the link exists only
because of the L1 window bug (§3.1). The case is genuine clinical development evidence, but it is
not admissible under the frozen 5-year window.

**Case B — protocol-legal largest lead (L2, inside window, RUN2):** medtronic `KK233838` /
`OVERALL` / EPMC `30931726` / 2019-04-01 / 1,823 d. Every mechanical check passes, **but the
matched token is the English word “overall”** in an unrelated drug-coated-balloon paper — a
spurious semantic link that only the token-rule oversimplification produces. This is the case the
study would quote as its largest admissible pre-regulatory lead; it does not survive reading.

**Case C — SNAPSHOT top product-specific PRE_REGULATORY (Melody, 1,618 d):** all mechanical
checks pass (milestone P140017 APPR 2015-01-27; NCT01186692 exact date/title; `MELODY` in title and
intervention; `applicant_df=2`, sole pre-2023 use; no earlier `MELODY` record), **but** the record
is a post-approval study of an HDE-approved device and the latest-plausible clock gives
**−1,555 days** (§4). The top product-specific case in the truncated-file state of RUN1 (before
the emission-cap fix), boston `KK172565`/`OBTRYX` 1,778 d, is likewise explicitly a
“Post Market Study”.

## 7. Discrepancy list (exact)

1. **(critical, ambiguity)** L1 assigned without the 5-year evidence window: 28/108 L1 rows outside
   `[a−5y, a−1d]`; headline max lead 3,512 d (and the 3,468 d case quoted in
   `EXPERIMENT_RESULTS.md`) exceeds the 5-year window and carries no window caveat. §5 vs §6.1 is
   ambiguous on whether L1 is exempt; the choice should be stated explicitly.
2. **(major, protocol)** EPMC matching uses keywords+MeSH, not title/abstract: 502/4,926 emitted
   verified rows depend on them; k 187 vs 186 protocol-literal; 18 anchors' max lead differs.
3. **(major, interpretation)** “PRE_REGULATORY” counts post-approval/post-market studies as
   pre-regulatory because HDE/IDE approvals are absent from the store: 5 PRE_REGULATORY rows
   (4 product-specific) self-declare prior approval; top cases §6-A/B/C.
4. **(major, token quality — partly self-disclosed)** Ordinary English words (`OVERALL`, `ORGANS`,
   `CAPTURING`, `EFFICIENT`, `TETHERING`, `POLYSACCHARIDE`, …) enter the distinctive set and, before
   Amendment 5, dominated the within-window top of the pre-regulatory ladder. Amendment 5 removes
   the worst four from the strictest level only (32 → 28) and leaves the residual ones to human
   adjudication; the pooled/product-specific levels (35/32) are unchanged.
5. **(moderate, attribution)** 3 of 269 anchors attributed to Zimmer Biomet are
   `Zimmer Medizinsysteme GmbH` (independent company): `KK161862`, `KK182963`, `KK213256`; no links,
   verdict unaffected; anchors 269 → 266 if corrected.
6. **(moderate, deliverable)** `EVIDENCE_LINKS.jsonl` omits 1,606 of 6,532 verified rows (25%);
   declared in `b_links.json` (`__emission_capped_l1l2`) but not in the file/README claim of
   “every … verified … link”. Anchor-level `k` is correct in RUN2; `b2_novelty` row counts
   (388/4,538) are cap-reduced vs 518/6,014 on the full set (anchor counts 35/32 correct).
7. **(minor, reporting)** `c3_decoy.specificity_note` contradicts `specificity`/`decoy_link_rate`;
   `c4b` uses 500 draws where FROZEN_RULES freezes 2000; specificity ratio mixes denominators
   (1.2990 vs 1.3066 matched).
8. **(process)** SNAPSHOT anchors (268) were not reproducible from the frozen vocabulary; they were
   built before `frozen_vocab.json` v2 and carried brand tokens in 9 anchors. Fixed in RUN2
   (269, exactly reproducible). Separately, RUN1's k=151 was a truncation artefact, fixed in RUN2
   (k=187). A third run (05:07:34) aborted at `freeze_epmc_df` (rc=2) and left `frozen_vocab.json`
   on disk different from the one RUN2's manifest records — the tree is not yet at rest.

## 8. What I could not verify

- The EPMC/CT.gov **harvests themselves** (frozen corpora, no network permitted). I verified that
  the corpus record counts match the fetch manifests (CT.gov 4,856; EPMC 36,644 incl. 23 PAT,
  506 PMC, 168 PPR / 35,947 MED) and that every case record exists verbatim; I did not re-run the
  external queries.
- The **decoy construction and placebo permutations** inside `c_controls.py`: I re-derived the
  specificity ratio from the committed real/decoy counts and checked the arithmetic, but did not
  re-implement the seeded donor/permutation RNG. The placebo p is accepted as committed (it is
  far from every threshold and any plausible value leaves NO-GO).
- **HDE/IDE history** (Melody H070003, 2006) is analyst knowledge, not present in the store; I
  clearly label it and the case also fails on the corpus title and the latest-plausible clock
  without it.
- Any run after RUN3 FINAL (05:10:02). The numbers in this report are pinned by the
  `verify/run2_snapshot` and `verify/run3_final_snapshot` hashes.

## 9. Verdict on the committed numbers

The mechanical layer is trustworthy: with my own resolver, tokenizer, linker and classifier, I
reproduce the canonical milestone set (177,948; 0 duplicates), the attribution totals (12,230
attributed, 0.931272 unknown), the anchor sets exactly in both states (268 under the pre-freeze
tokenizer state, 269 under the frozen vocabulary — full funnel identical), the link tiers exactly
at the anchor/row level (187 anchors, 0 per-anchor lead differences, every one of the 4,926 emitted
verified rows, identical again after the Amendment-5 re-run), the novelty classification exactly
(35 anchors / 32 product-specific), and the verdict gate by gate. The published **NO-GO is the
correct verdict** (and the earlier BLOCKED was correct for its incomplete-corpus state); it stands
under every independent reading I tried. The author's own `EXPERIMENT_RESULTS.md` (05:10:39)
already reports NO-GO and already discloses four caveats (the four ordinary-word/HDE cases and the
weak controls), which my audit confirms. What remains insufficiently disclosed or still wrong:
the 3,512-day / 3,468-day leads are quoted without the 5-year-window caveat (L1 bypasses the
window and §5 is ambiguous on whether it may), ~10% of verified rows depend on EPMC
keywords/MeSH beyond the frozen §6.1 text, the pooled “pre-regulatory” class still contains
post-approval/post-market studies (5 rows, 4 product-specific) and ordinary-word pseudo-matches
outside the strictest level, and one applicant token (ZIMMER) silently merges a different company.
The deliverable file still omits 25% of verified rows (declared in `b_links`, not in the file or
README), and the tree changed four times during verification. The headline sentence “public
evidence existed on average years before approval, before the product had any regulatory
footprint” should not be published from this run as it stands; the safe, fully reproduced
statement is: *a strictly mechanical token linker over firm-anchored corpora produces 187/269
anchors with an earlier record, but every pre-registered control (decoy specificity 1.30, placebo
p 0.83, keyword baseline 99.3% vs 69.5%) and the frozen verdict rule return NO-GO.*

## Reproduction

```bash
cd experiments/phoenix003/verify
PHOENIX_VERIFY_MODE=snapshot python verify_anchors.py        # 268-anchor state
PHOENIX_VERIFY_MODE=live     python verify_anchor_state.py   # 268 vs 269, funnel
PHOENIX_VERIFY_MODE=live     python verify_attribution.py    # 269 anchors
PHOENIX_VERIFY_MODE=snapshot python verify_links.py          # k=33 exact
PHOENIX_VERIFY_MODE=live     python verify_links.py          # k=187 exact, cap 1606
PHOENIX_VERIFY_MODE=snapshot python verify_novelty.py        # 202/11, 6/5
PHOENIX_VERIFY_MODE=live     python verify_novelty.py        # 4538/388, 35/32
PHOENIX_VERIFY_MODE=snapshot python verify_verdict.py        # BLOCKED
PHOENIX_VERIFY_MODE=live     python verify_verdict.py        # NO-GO
PHOENIX_VERIFY_MODE=live     python verify_case_live.py      # SYMPLICITY / OVERALL cases
python make_run_log.py                                        # verify_run.log
```

---

# FINAL-STATE VERIFICATION (post-fix run)

The author fixed every defect reported above and re-ran the pipeline. This section verifies the
resulting state; everything before it is kept unchanged as history.

**State pinned:** `verify/final_snapshot/` — `results/manifest.json generated_at
2026-11-08T21:16:11Z`, all 7 stages rc=0, `REGULATORY_ANCHORS.jsonl` sha `095ecab6…`,
`EVIDENCE_LINKS.jsonl` sha `2ed1c604…`, 266 anchors, k=186. Script: `verify/verify_final.py`;
transcript in `verify/verify_run.log`; machine output `verify/out_final.json`. The live tree was
re-checked and matches the snapshot; the tree is at rest.

## F1. Every claimed fix, independently confirmed

| # | fix claimed | my independent check | result |
|---|---|---|---|
| 1 | L1 5-year window enforced | all rows: `w0 <= evidence < anchor` before tier assignment; L1 rows 76, **0 outside window**; L1 max lead **1,814 d**; overall max lead **1,826 d** ≤ max legal window span 1,827 d; old 3,468/3,512 d rows are `REJECTED_L5 outside_5y_window` | **confirmed** |
| 2 | EPMC matches title+abstract only | of 5,760 verified rows, EPMC rows whose token is not in title+abstract: **0** (in keywords/MeSH: 0). My `match_tokens` re-derivation reproduces every verified row | **confirmed** |
| 3 | Amendment 6 post-approval markers | committed reclassification reproduced: 5,312 `PRE_EXISTING` / 448 `PRE_REGULATORY` rows; markers `post-approval` 44, `post-market` 71, `continued access` 37, `post approval` 25, `product surveillance registry` 5, `postmarket` 9, `post market` 46, `postapproval` 11. Anchor-level ladder unchanged | **confirmed, with an over-breadth caveat (F4)** |
| 4 | Amendment 5 literature rarity | `epmc_rare_tokens.txt` recomputed from the corpus: **0 mismatches / 554 tokens**; committed `literature_rare` flags: **0 mismatches / 5,760 rows**; strict ladder = **28** | **confirmed** |
| 5 | ZIMMER exclusion | anchors 266 (Zimmer Biomet 15 → **12**); no anchor applicant contains `MEDIZINSYSTEME`; attributions 12,217 (unknown 165,731, 0.931345); my resolver returns UNKNOWN for `Zimmer Medizinsysteme GmbH` | **confirmed** |
| 6 | Emission cap | file carries **5,760 / 5,760** verified rows (76 L1 + 5,684 L2); `__emission_capped_l1l2` absent; `__emission_capped_rows = 5,104` are **non-verified** (L4/L5) only | **confirmed** |
| 7 | Reporting defects | `specificity_note` corrected; specificity now **1.3672** with matched denominator (real 175/249 = 0.702811, decoy 128/249 = 0.514056), `specificity_matched_denominator = 1.3672` present; C4b draws = **2,000**, p = **0.881059**; C4a draws = 2,000 | **confirmed** |
| 8 | Process / reproducibility | anchors **266/266 identical** to my rebuild (anchor_id 266/266, token lists 266/266, full a1 funnel identical); manifest: **21/22 files match** on disk (only `results/manifest.json` itself mismatches — see F5) | **confirmed except the manifest self-entry (F5)** |

## F2. Re-derived headline numbers (my implementation vs committed)

| quantity | my independent value | committed |
|---|---|---|
| anchors | 266 | 266 |
| attributed milestones / unknown | 12,217 / 165,731 (0.931345) | same |
| k (anchors with ≥1 L1/L2) | **186** | 186 |
| verified rows (L1 / L2) | 5,760 (76 / 5,684) | 5,760 (76 / 5,684) |
| per-anchor max lead differences | **0** | — |
| share ≥90 d / median lead | 0.989247 / 1,620 d | 0.989247 / 1,620 d |
| max lead / L1 max lead | 1,826 d / 1,814 d | 1,826 d / 1,814 d |
| ladder: any / product-specific / pre-reg / ps∧pre / strict | **186 / 60 / 34 / 31 / 28** | 186 / 60 / 34 / 31 / 28 |
| ladder medians (d) | 1,620 / 1,351 / 1,340.5 / 1,311 / 1,316.5 | identical |
| ladder share ≥90 d | .989247 / .966667 / .970588 / .967742 / .964286 | identical |
| novelty rows PRE_EXISTING / PRE_REGULATORY | 5,312 / 448 | 5,312 / 448 |
| anchors pre-reg / product-specific pre-reg | 34 / 31 | 34 / 31 |
| Target-B novel / with verified link | 18 / 7 | 18 / 7 |
| specificity (matched denominator) | 175/249 ÷ 128/249 = **1.3672** | 1.3672 |
| placebo p (C4b, 2,000 draws) | **0.881059** | 0.881059 |
| coverage | 1.0 | 1.0 |
| **verdict** | **NO-GO** (GO fails specificity 1.367 < 5.0 and p 0.881 > 0.05; LIMITED fails 1.367 < 3.0 and p 0.881 > 0.10) | NO-GO |

No disagreement found in the committed headline numbers.

## F3. Top strict case — end-to-end audit (independent)

Current largest admissible strict case (pre-reg ∧ product-specific ∧ literature-rare):

**abbott `PP200049` / token `AMULET` / CT.gov `NCT02879448` / first posted 2016-08-25 / lead
1,815 d** (PMA P200049 approved 2021-08-14, product code NGV).

| check | value | pass |
|---|---|---|
| milestone in store | P200049, APPR, 2021-08-14, applicant `ABBOTT MEDICAL` | ✓ |
| record in frozen corpus | `ctgov_ext_compact`, exact `first_posted` 2016-08-25, title `AMPLATZER™ Amulet™ LAA Occluder Trial` | ✓ |
| token identity | `AMULET` in brief title + intervention; whole token; `applicant_df=1`, EPMC df=20 ≤ 200 (rare) | ✓ |
| firm attribution | `lead_sponsor = "Abbott Medical Devices"` resolves to abbott | ✓ (see caveat B1) |
| no earlier token record | earliest `AMULET` regulatory record = 2021-08-14 > evidence date | ✓ |
| inside window | [2016-08-14, 2021-08-13]; evidence 2016-08-25 | ✓ |
| no post-approval marker | none in title/abstract | ✓ |
| L1 chain | not applicable (L2 ctgov) | ✓ |

Break attempts (the case survives mechanically, but two caveats must accompany it):

- **B1 — evidence-side lineage is retroactive.** The trial was published 2016-08-25; the device was
  St. Jude Medical's and Abbott acquired St. Jude on 2017-01-04 (analyst knowledge). The corpus's
  `lead_sponsor` now reads “Abbott Medical Devices” — i.e. the current corpus copy carries a
  post-acquisition sponsor rename. §6.1 has no evidence-date lineage condition, so the rule passes,
  but the “same firm” link is back-projected by ~4 months; this is the evidence-side analogue of
  the acquisition rule §3 forbids for regulatory records.
- **B2 — latest-plausible clock is negative.** `last_update_posted = 2025-02-26` → lead
  **−1,292 d** on the frozen latest-plausible clock. The 1,815-day lead is a `first_posted`-clock
  number only (the dual-clock sensitivity is reported in `d_leadtime`, but the strict-case table
  should say so).
- **B3 — the same device already had a “Post-Market Study” in the corpus**: `NCT02447081`
  “Amplatzer™ Amulet™ Post-Market Study”, first posted 2015-05-18 (2,280 d before the PMA, so
  `REJECTED_L5 outside_5y_window`). It does not affect the token-history novelty test (no 510(k)/
  PMA record), but it weakens the plain reading “before the product had any regulatory footprint”.
- Token quality is *not* the `OVERALL` failure mode: `AMULET` is a genuine proprietary product name
  (one applicant; 20 EPMC documents), so the Amendment-5 filter does its job here.

**SYMPLICITY:** the 3,468-day rows are now `REJECTED_L5 outside_5y_window` as claimed, but the
anchor is not gone: 44 rows total, **16 verified** all inside the window, max lead **1,738 d**
(EPMC 30760655, 2019-02-13). It remains a strict case (EPMC df = 41 ≤ 200) but is no longer the top.

Other strict cases after it: INTUITY 1,775 d, KIESTRA 1,767 d, SYMPLICITY 1,738 d, CAPTURING
1,674 d (known ordinary word, flagged), PORTICO 1,673 d, WATCHMAN 1,670 d, SIDUS 1,648 d.
Strict anchors with ordinary-word risk that survive Amendment 5: `CAPTURING` (83), `TETHERING`
(13), `POLYSACCHARIDE` (81) — unchanged from the author's disclosure; they need human adjudication
as stated.

## F4. Remaining discrepancies

1. **(minor, reporting) `results/manifest.json` self-entry.** 21/22 manifest entries match disk;
   the one mismatch is `results/manifest.json` itself, because the pipeline hashes the previous
   manifest before writing the new one. Fix: exclude `results/manifest.json` from the watched set
   (or record “self” separately). All other artefacts, including `FROZEN_RULES.json`,
   `firm_lineage.json`, `epmc_rare_tokens.txt`, both JSONL deliverables and all four corpora, match
   their recorded sha256.
2. **(minor, documentation) Amendment 6 is not appended to `FROZEN_PROTOCOL.md` §12.** The
   post-approval-marker rule is frozen in `FROZEN_RULES.json → novelty` (motivated explicitly by
   independent verification) but the protocol file still ends at Amendment 5 (mtime 05:11:24,
   before the final run). Protocol §12 requires amendments to be appended with timestamp/reason.
3. **(minor, rule breadth) the `continued access` marker can be over-broad.** 37 verified rows are
   reclassified by it; 3 of them would otherwise be `PRE_REGULATORY`, including
   `Continued Access to PREVAIL (CAP2)` (WATCHMAN, 2013-01-04) — an FDA *pre-approval* continued-
   access programme (WATCHMAN PMA approved 2015). Anchor-level ladder is unaffected (WATCHMAN
   remains pre-regulatory via other rows; strict 28 unchanged), but the marker list should
   restrict that phrase to titles or explicitly treat CAP programmes as pre-approval.
4. **(minor, excerpt) 6 row-level novelty statuses differ from my full-text scan.** The committed
   rule scans only the first 600 characters of title+abstract (`evidence_text`); my independent
   full-text scan finds a marker for 6 additional rows (4 `OVERALL`, `AMULET`, `TRICLIP`) that the
   committed rule keeps `PRE_REGULATORY`. Anchor-level counts and the whole ladder are unchanged
   (34/31/28), so this is a transparency issue, not a number error.
5. **(retained caveat, not a defect) publication clock only.** For the top strict case the
   latest-plausible clock is negative (F3-B2); `d_leadtime` reports the dual clock but the
   strict-case table/headline should state that the strict leads are `first_posted` numbers.

## F5. Updated one-paragraph verdict

The committed numbers are now safe to publish: every claimed fix is independently confirmed
(266 anchors reproduced 266/266 with the full funnel identical; all 5,760 verified rows reproduced
row-for-row with zero per-anchor lead differences; L1 fully inside the frozen 5-year window with a
legal 1,826-day maximum; EPMC title+abstract only; rarity flags exact; ZIMMER resolved; verified
links never capped; matched-denominator specificity 1.3672; C4b 2,000 permutations), and the
re-derived k/ladder/medians/specificity/placebo-p/verdict are identical to the committed values
(186 / 60 / 34 / 31 / 28; NO-GO), so the study's negative verdict and its “case series, not a
rate” framing stand. The headline sentence needs two qualifiers, not a rewrite: the strict leads
are `first_posted`-clock numbers (the top case is −1,292 d on the latest-plausible clock), and at
least the top case’s evidence-side firm match is a post-acquisition sponsor rename (Abbott acquired
St. Jude in 2017; the trial is from 2016), with a same-device “post-market study” from 2015 in the
corpus — so “public evidence existed before the product had any regulatory footprint” should be
published as “token-level public records precede the *US approval milestone* on the publication
clock, with the duality and lineage caveats stated”, plus the three minor residuals above
(manifest self-entry, Amendment-6 protocol append, `continued access` marker breadth). With that
wording, the numbers and the NO-GO are safe.
