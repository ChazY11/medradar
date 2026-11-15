# ATTRIBUTION_VALIDATION

Independent sample review of MedRadar's applicant-to-organization attribution (PRODUCT-002, Phase A4).

## Headline

| Question | Answer |
|---|---|
| Is attribution accuracy reliably estimated? | **Not yet.** An evidence-backed estimate exists for a small decidable subset; 66% of the pre-registered sample has no collected independent source yet, and the reviewer is an AI agent applying a documentary rule, not a human analyst. |
| Point estimate over decidable cases | 100% (13 of 13 supported) |
| 95% Wilson interval | **0.772 - 1.000** |
| Decidable sample | 13 of 38 (34%) |
| Undecidable sample | 25 of 38 (66%) |
| Contradicted cases | 0 |
| Reviewer class | agent (documentary rule) - **human sample review still required** |

The product therefore publishes Estimated Attribution Precision as this estimate **with its
caveats**, not as a headline accuracy claim. Where this file and `validation/precision.json` differ,
the JSON file is authoritative (it is generated, this file is written around it).

## Numbers the product publishes (snapshot only, no local review ledger)

| Metric | Value |
|---|---|
| Collected records | 91,457 |
| Attributed records | 91,384 (Attributed Share **99.92%**) |
| Evidence-verified or human-reviewed | 8,998 (**Curated Share 9.85%**) |
| Rule-verified but not reviewed | 40,339 (**Rule-verified Share 44.14%**) |
| Provisional (no rule, no evidence) | 42,047 (**Provisional Share 46.01%**) |
| Human-reviewed | **0** |
| Applicant strings observed / accepted spellings | 1,563 / 1,590 |
| Organizations with records | 59 of 59 |
| Median organization Curated Share | 0.0% (only organizations with a collected jurisdiction filing have verified records) |

These numbers are produced by `medradar/product/metrics.py` and served by `GET /api/metrics`; the
tables here are a copy for review.

## Sample design (pre-registered)

See `IDENTITY_REVIEW_PROTOCOL.md` §5. Fixed seed 20261115, six per stratum (all six in S1), strata
chosen to cover the evidence situations the protocol names. Sample: `validation/sample.json`.

## Results by stratum

| Stratum | Cases | Supported | Contradicted | Undecidable |
|---|---|---|---|---|
| S1 high volume (>=1000 records) | 6 | 3 | 0 | 3 |
| S2 mid volume (100-999) | 6 | 1 | 0 | 5 |
| S3 low volume (1-99) | 6 | 1 | 0 | 5 |
| S4 lexical rule | 6 | 2 | 0 | 4 |
| S5 ownership evidence | 6 | 6 | 0 | 0 |
| S6 corporate relation (no evidence) | 6 | 0 | 0 | 6 |
| S7 ambiguous scope | 2 | 0 | 0 | 2 |
| **Total** | **38** | **13** | **0** | **25** |

What the strata say:

* Every case that already had a recorded ownership relation (S5) was independently confirmed by a
  filing. That is expected by construction, and it is why S5 is reported separately rather than
  pooled into a flattering total.
* High-volume name-identity mappings (S1) are decidable when the company files an Exhibit 21 listing
  the entity (Abbott Medical, Abbott Laboratories, Boston Scientific) and undecidable when the
  applicant is a business-unit name that is not a legal entity (Medtronic Cardiac Rhythm Disease
  Management, Medtronic Neuromodulation) or when the company is not an SEC registrant.
* S6 (subsidiary/division/historical-name attributions with no evidence) is **entirely undecidable**:
  none of the six sampled corporate-relation mappings could be checked. This is the largest concrete
  quality gap the product now exposes instead of hiding.
* S7 contains the two genuinely ambiguous strings: "Abbott Vascular-Cardiac Therapies dba Guidant
  Corporation" (17 records) and "Olympus Terumo Biomaterials Corporation" (3 records). Both are
  *unattributed* today; both are visible in the review queue with risk flags.

## What could not be verified, and why

| Reason | Cases | What would fix it |
|---|---|---|
| No jurisdiction filing collected for the organization (not SEC-registered or no exhibit located) | 18 | collect EU/JP/CN registries, annual reports or official company subsidiary lists |
| Filing located but does not list the entity (threshold-based exhibit) | 7 | use the regulator's establishment registration data, or a fuller subsidiary register |

The decision rule treats both as **undecidable, never as correct**, so the estimate cannot be
inflated by absence of evidence.

## Honest conclusion

1. MedRadar can now *measure* attribution correctness instead of asserting it.
2. On the part of the sample where independent documentation exists (13 cases, dominated by the
   organizations with collected filings), no wrong attribution was found.
3. That is **not** a product-level precision claim: the decidable subset over-represents
   organizations with good filings, the interval is wide (0.77-1.00), and the reviewer is an agent.
4. The correct statement for a user today is: **"9.85% of attributed records rest on independent
   evidence; attribution accuracy has not yet been established by an independent human review."**
5. Next step to close G3 fully: a human analyst repeats the same fixed sample (the worksheet and the
   decision rule are ready) and, where the answer is undecidable, adds a named independent source.
   Until then `human_review_completed` stays `false`.

## Reproduce

```bash
python tools/validation/validate_attribution.py --collect-evidence   # re-fetch filings (network)
python tools/validation/validate_attribution.py --sample             # deterministic sample
python tools/validation/validate_attribution.py --review --report    # rule applied, precision.json
```

Artifacts: `validation/sample.json`, `validation/sec_entity_lists.json`,
`validation/review_records.json`, `validation/precision.json`.
