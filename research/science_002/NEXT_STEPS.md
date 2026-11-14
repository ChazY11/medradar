# NEXT_STEPS - what is actually worth doing next

Ordered by expected scientific value per unit of work. Items marked **blocking**
would have to be solved before any GO-style result could be believed.

---

## 1. Fix the measurement before the model (**blocking**)

The single weakest number in this study is attribution coverage: **8.8%** - only
3,143 of 35,680 cleared 510(k)s in 2015-2026 are attributable to the 48 universe
firms with exact-name evidence. Every remaining conclusion is bounded by that.

Concretely, in order:

1. **Use FDA's establishment registration numbers, not names.** A 510(k) record's
   `openfda.registration_number` and `openfda.fei_number` arrays point at the
   establishment that filed it. Joining through the FEI number and then to
   `registration.owner_operator.owner_operator_number` removes the name-matching
   step for the second hop entirely and would recover subsidiaries whose applicant
   string is not a registration name (e.g. `BOSTON SCIENTIFIC SCIMED`).
2. **Add a dated ownership source.** The 2026 registration snapshot is undated,
   which is why tier B has to be applied to the whole panel. SEC 10-K Exhibit 21
   filings are dated, per registrant, and would allow an ownership relation that is
   *as-of* rather than *now*. That is the difference between a defensible
   attribution and a documented assumption.
3. **Measure the FDA batch lag, don't assume it.** Weekly snapshots of the 510(k)
   endpoint's `last_updated` and newest `decision_date` would give an empirical
   lag distribution instead of the 30-day stand-in used here.

## 2. Change the outcome to the thing we actually care about

A 90-day "at least one clearance" indicator is saturated for large firms (7 of 46
holdout firms are at 1.00) and empty for small ones (8 at 0.00). Fifteen of 44
holdout firms contribute nothing to a within-firm statistic. Two better outcomes:

* **novel-technology clearance**: a clearance whose product code the firm has not
  used in the previous 36 months. This is closer to "meaningful change" and less
  mechanically tied to firm size. First check: the fraction of firms with both
  classes under this definition (a quick look suggested it is workable but tighter
  for the largest firms).
* **count models instead of a binary indicator**: a Poisson/negative-binomial with
  firm fixed effects on clearances per quarter uses the count information the
  binary indicator throws away and would raise power without changing the question.

## 3. Test a different SEC input, not a different classifier

This study tested XBRL R&D amounts and 8-K item activity. Two structured inputs are
unexplored and have real point-in-time semantics:

* **8-K Item 8.01 product/regulatory announcements**, parsed for named devices and
  submission types. This is the closest EDGAR gets to the event being predicted,
  and the leakage question becomes interesting rather than trivial (a company can
  announce a *submission* long before the *decision*).
* **10-K/10-Q "Business" and "Regulatory" sections** over time - but only with a
  pre-registered extraction rule, because free-text features are where exploratory
  degrees of freedom destroy inference.

## 4. If a signal ever appears, attack it before believing it

The control battery in this study is reusable and should be the price of entry for
any future positive: within-firm permutation null, circular-shift variant, cluster
bootstrap, leave-one-firm-out, R&D-timing placebo, item-5.07 placebo outcome,
label transplant. A future result should be reported only alongside all of them.

## 5. Do not do these

* **Do not report a pooled cross-firm AUC as early signal.** This study reproduces,
  on a different source pair, that it is firm composition: 0.83 pooled against 0.45
  within firm, and 0.385 leave-one-firm-out.
* **Do not add more features to B3 until the attribution problem in item 1 is
  solved.** With 8.8% coverage, another feature is measuring the same small slice
  of each firm's regulatory activity.
* **Do not re-run this design on another 90-day window hoping for significance.**
  The stable result across the binomial and circular nulls, the LOFO split and the
  placebo is a null, and repeating it with different windows is the exact failure
  mode the pre-registration exists to prevent.

## 6. The one thing to do first

If only one item is funded: **item 1.1** - re-derive the attribution through FDA
establishment numbers instead of names, then re-run this frozen protocol unchanged.
It is mechanical, verifiable, and it is the only change that could move the
measurement from 8.8% coverage to something a reviewer would accept, without
touching a single modelling decision.
