# TIME_SEMANTICS - what each timestamp in this study can and cannot prove

**Status:** result of the Phase-A source audit, and the rule set the panel builder
enforces. Every claim below is either backed by a captured source (URL and hash in
`evidence/SOURCES.md`) or by a measurement on the downloaded data, reported with
its sample size.

Three sources are used and they have three different time regimes. They are never
mixed into one field.

| source | what we take | regime |
|---|---|---|
| SEC EDGAR submissions | `acceptanceDateTime`, `filingDate`, `items` | UTC instant per filing (verified) |
| SEC XBRL companyfacts | `filed`, `start`, `end` | calendar day |
| openFDA device/510k bulk | `decision_date`, `date_received` | calendar day |
| openFDA device/registrationlisting bulk | establishment name, owner/operator | undated snapshot |

---

## 1. The four times, kept apart

| concept | field used | what the study does with it |
|---|---|---|
| **when the FDA decision happened** | 510(k) `decision_date` | defines the outcome window |
| **when the decision was publicly retrievable** | **not published per record** | bounded, never asserted; see section 3 |
| **when a filing was accepted by EDGAR** | `acceptanceDateTime` | the prediction-time cut for 8-K activity; a *lower bound* on availability |
| **when an XBRL fact became public** | `filed` (day) | the prediction-time cut for R&D features |
| **when we collected the bytes** | sidecar `fetched_at_utc` | audit only; never a public time |

The panel builder can only read the first four. `fetched_at_utc` lives in the
cache sidecar and no feature function can see it (the panel module does not import
the cache at all).

---

## 2. SEC: acceptance is not publication

This was established on 720 filings in SCIENCE-001 and is not re-litigated here:
the raw archive header `ACCEPTANCE-DATETIME` is a **US/Eastern wall clock**,
converting it with the US DST rule reproduces `data.sec.gov`'s
`acceptanceDateTime` to the second for 720/720 filings, and after 17:30 ET the
archival write is a median 11.6 h later (weekend for Friday evenings) against 35 s
before the cut-off. So:

* `acceptanceDateTime` **can** support filed-before-T reasoning;
* it **cannot** support a claim that the world could read the filing at that
  instant. For the 2.2% of after-hours filings the gap is hours to a weekend.
* `filingDate` is a business-day label and is never used as an instant.

Consequence for this study: an 8-K contributes to a firm-month feature only if its
`acceptanceDateTime` is at or before the month-end instant. Because 97.8% of
filings are accepted before the cut-off, the residual error is at most a few hours
and in the conservative direction (a filing accepted at 23:59:59 on the last day of
the month is treated as known, which is generous by minutes, never by days).

## 3. FDA: the decision date is not a publication date

**What openFDA publishes.** Each 510(k) record carries `decision_date` and
`date_received`. The dataset-level metadata carries `last_updated` (per
endpoint) and the bulk manifest carries `export_date`. No per-record
publication, dissemination or first-availability field exists anywhere in the
endpoint, and no such field exists in FDA's own 510(k) database download.

**What we measured** on the bulk export used by this study
(`device-510k-0001-of-0001.json.zip`, 176,625 records, 249,963,096 bytes,
SHA-256 `eb479de53bcb8b48c73c9a5ecaf6eea75eb84a00431ac0c04000090005c663c9`):

* `last_updated` = **2026-11-02**, manifest `export_date` = **2026-11-09**;
* the latest `decision_date` present = **2026-10-30**;
* monthly decision counts: 2026-08 = 253, 2026-09 = 320, 2026-10 = 295, 2026-11 = 0.

So at the moment of this snapshot the database trailed the newest decision by at
most about **3 days** (`last_updated` minus newest decision) and the export ran about
10 days behind. November having no records at all on a 2026-11-09 export is the
clearest single piece of evidence that the refresh is a **batch** process with a
lag of order days, not a streaming feed.

**What this supports.** `decision_date` is a valid **lower bound** on
availability: a decision cannot be public before it is a decision. It is also a
good bound in practice, since the observed batch lag is under two weeks.

**What this does not support.** Saying that a clearance was *known to the market*
on its `decision_date`. A firm often announces a clearance in a press release or
an 8-K before the database is refreshed; the database row can therefore be
*later* than public knowledge, never earlier. Consequently:

* using `decision_date` to build the **historical** clearance counts is safe only
  with a lag, and this study uses **30 days** (pre-registered sensitivity S3
  reruns with 0 and 60). With lag 0 a firm-month could read a clearance as known
  before the batch that published it.
* using `decision_date` to build the **outcome** is safe without a lag, because the
  outcome window only ever starts after the prediction instant: an event that has
  not happened yet cannot have leaked into a feature.
* no **lead time** may be claimed in days. A clearance dated day d is publicly
  retrievable at some point in [d, d + observed batch lag]; the study therefore
  reports horizon-relative results (90-day window), not lead times.
* the one direction that is genuinely unsafe - a firm's own 8-K quoting a
  clearance whose `decision_date` is still in the future - cannot happen: a
  company learns of a clearance after FDA decides, so its announcement cannot
  precede the recorded decision by construction. AUDIT.md reports the check that
  verifies this on the data rather than only in argument.

## 4. FDA registration/listing is an undated snapshot

The `device/registrationlisting` export (336,932 rows, 25,222 distinct
establishment/owner pairs) carries an establishment's **current** owner/operator and
a registration expiry year, but **no date at which that ownership relation began**.
It is therefore used only to *group* applicant strings into a corporate group,
never to date anything:

* an attribution derived from it is applied to the whole 2021-2026 panel,
  identically in the past and in the future, so a firm's event stream has no
  attribution discontinuity at an acquisition;
* the interpretation is 'the group as registered with FDA in 2026', and a
  pre-acquisition clearance of an acquired subsidiary is credited to the
  acquirer. ENTITY_RESOLUTION.md records which firms depend on this and the
  sensitivity S1 removes it entirely.

## 5. XBRL: day granularity, first report only

`companyfacts` gives, per fact, the fiscal `start`/`end` and the `filed` day of the
filing that reported it. Three rules follow, and all three are enforced in code:

1. a fact is known only from its `filed` day, so a feature at month-end t uses only
   facts with `filed <= t`. Day granularity means a fact filed on the last day of
   the month is treated as known at that day's end - a ≤ 24 h generosity, stated
   here and nowhere netted out.
2. the same period can be reported again later. The **first** report is used and
   restatements are not backfilled, so a 2025 revision is invisible to a 2022 row.
3. duration facts only (70-110 days) build the trailing-twelve-month sum; annual
   facts are ignored so a fiscal year is never double counted with its quarters.

## 6. What cannot be reconstructed in this study

1. **The first public retrieval instant of a 510(k) clearance.** Not published, not
   derivable from openFDA. The study's bound is
   [`decision_date`, `decision_date` + observed batch lag]; it is an interval.
2. **Whether a third party knew earlier** (company press release, newswire, investor
   call). Out of scope for both sources.
3. **When a corporate ownership relation began.** The registration snapshot is
   undated. Any historical attribution is a present-day grouping.
4. **Whether the FDA database of 2021 had the same refresh behaviour as 2026.** The
   batch-lag evidence is from one snapshot. That is why the study uses a 30-day
   conservative lag rather than the observed 3-10 days.

## 7. Rules the code enforces

| rule | where |
|---|---|
| 8-K feature cut is `acceptanceDateTime <= t` | `panel._filing_counts`, `panel.filing_window` |
| clearance-history cut is `decision_date <= t - 30d` | `panel.clearance_counts` |
| outcome window is `t < decision_date <= t + 90d` | `panel.clearance_window` |
| XBRL cut is `filed <= t` and `end <= t`, first report wins | `sec.duration_facts`, `panel._ttm` |
| a window crossing the maturity cut is dropped, never labelled 0 | `panel.build_panel` |
| no feature function can read the collection time | `panel` does not import `sources.Cache` |

`AUDIT.md` documents the adversarial checks that verify these on the data,
including an independent re-implementation of the feature rules and an executed
future-filing injection test.

## 8. Evidence layer

Every external statement above that is not a measurement of our own data is
captured in `evidence/SOURCES.md` with URL, retrieval date, verbatim quote and
SHA-256 of the captured bytes: the openFDA manifest and endpoint metadata, the
EDGAR filing-manual and 17 CFR 232.13 statements on acceptance and dissemination,
and the FDA device-database download descriptions.
