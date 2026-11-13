# TIME_SEMANTICS - what an EDGAR timestamp can and cannot prove

**Status:** phase-1 result, accepted as the precondition for the experiment.
**Sample:** 720 filings, 12 issuers, 2017-2026, all downloaded from the archive
and parsed from their own header block (see `artifacts/time_verification.csv`).
**Evidence layer:** 28 SEC / GPO primary sources with verbatim quotes, hashes and
URLs in `evidence/sec_docs/SOURCES.md`.

---

## 1. Verdict

EDGAR gives a **verified acceptance instant**, and it does **not** give a public
dissemination instant.

* The raw archive header `ACCEPTANCE-DATETIME` is a **US/Eastern wall-clock** value
  (UTC-5 in EST, UTC-4 in EDT). Converting it with the US DST rule reproduces
  `data.sec.gov`'s `acceptanceDateTime` **exactly** - residual 0 s for **720/720**
  filings, with the offset switching at the DST boundaries across ten years.
* SEC never documents that field. Its meaning and its timezone are established
  here **empirically plus by a second SEC artifact that states its offset
  explicitly** - not by reading a definition.
* SEC accepts the filing; it does not publish when the public could first
  retrieve it. The closest published behaviour is that after **17:30 Eastern** a
  filing is dated, and disseminated, on the **next business day**.
* That deferral is **measurable in this sample**: for the 17 filings accepted
  after 17:30 ET, the archival file's `Last-Modified` is a median **11.6 h** after
  acceptance (16/17 more than an hour, 3/17 a full weekend), against a median of
  **35 s** for the other 703.

Consequence: acceptance is a valid **lower bound** on public availability and a
good one for the 97.6% of filings accepted before the cut-off. It is **not** a
timestamp of public availability, and for after-hours filings it can run up to a
weekend ahead of reality.

---

## 2. The four times, kept apart

| concept | EDGAR field | this study's use |
|---|---|---|
| what happened | 8-K `reportDate` / CONFORMED PERIOD OF REPORT | reported, never used as availability |
| when EDGAR accepted it | raw header `ACCEPTANCE-DATETIME` (Eastern) | the point-in-time instant |
| when the public could retrieve it | **none published** | bounded, never asserted |
| when we fetched it | `fetched_at_utc` in the provenance sidecar | audit only, never a public time |

They live in different files and are never copied into one another. The code
enforces this: `timesemantics.py` has no function that returns "publication time";
it returns `AvailabilityBounds`, whose `not_after_utc` is null when no bound exists.

---

## 3. What SEC actually documents

Full quotes and SHA-256 in `evidence/sec_docs/SOURCES.md`. The decisive ones:

| # | Source | What it does and does not say |
|---|---|---|
| S8 | EDGAR Filer Manual Vol. II (v78, 2026-09-14), p. 2-4 | "**Acceptance** means that the filing meets all of the EDGAR processing rules and, if live, the filing will be disseminated." Dissemination "can often occur within seconds of your transmission". |
| S8 | same, p. 3-34 | "Normally filings received after 5:30 P.M. Eastern time will receive a filing date of the next business day and **will not be disseminated until the next business day**." |
| S8 | same, search result | The string `ACCEPTANCE-DATETIME` occurs **0 times** in the manual; so do "acceptance date" and "acceptance time". The field is undocumented. |
| S13 | 17 CFR 232.13(a)(2) (GPO/govinfo) | Legally operative rule: filings whose direct transmission commences by "5:30 p.m. **Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect**" are filed that business day; later ones the next. DST-aware by regulation. |
| S13 | 17 CFR 232.13(a)(1) | The filing date is the business day of **receipt**, and (a)(2) keys on when transmission *commences*, not when EDGAR finishes accepting. |
| S1 | SEC API documentation page (2025-04-08) | Describes API freshness as "updated in real-time as filings are **disseminated**", but defines **no JSON field**, and never states that any API timestamp is UTC. It does write "3:00 a.m. ET" elsewhere, so the omission is not a lack of vocabulary. |
| S22 | SEC, EDGAR Public Dissemination Service (PDS) | The paid feed exists to give the public filings "as soon as reasonably feasible". SEC states the system was changed "to ensure that EDGAR filings are available to the public on the SEC website **before** such filings are made available to the public dissemination system (PDS)". PDS is therefore not even the first public moment, and no per-filing PDS time is published. |
| S15 | EDGAR company Atom feed, CIK 0000064670 | Each entry carries `<updated>` as ISO-8601 **with an explicit offset** (-05:00 in winter, -04:00 in summer), and it equals the raw header value to the second. A second SEC artifact thus corroborates both the instant and the Eastern basis. SEC documents neither. |
| S16/S17 | EDGAR daily index `form.idx` / `company.idx` | Columns are Form Type / Company / CIK / **Date Filed** (YYYYMMDD) / File Name. No time of day, no timezone, no dissemination column. |
| S24-S27 | raw `.hdr.sgml` headers, 2013-2015 | The header block itself carries `ACCEPTANCE-DATETIME` with **no offset marker at all** - which is precisely why its zone had to be established rather than assumed. |

Net documentary position: **the acceptance field is undocumented; the regulatory
deferral for after-hours filings is documented and legally operative; no public
dissemination timestamp exists in SEC public data.**

---

## 4. What this study measured

### 4.1 The header is a US/Eastern wall clock

| check | result |
|---|---|
| filings parsed from their own archive header | **720 / 720** |
| graded `A_acceptance_verified` (header->UTC equals API instant) | **720 / 720** |
| maximum absolute residual | **0 s** |
| implied offset -5 (EST) / -4 (EDT) | **257 / 463** |
| local wall-clock value ambiguous or nonexistent under DST | **0 / 720** |
| header accession equals the index accession | **720 / 720** |
| header form type equals the index form type | **720 / 720** |

The alternative hypothesis - "the serialised value is already UTC and the `Z`
is honest" - would leave a residual of exactly 240 or 300 minutes on every
filings. It is rejected by 720/720 cases at 0 s.

### 4.2 The offset tracks DST, every year

Filings were verified in both regimes in every year from 2017 to 2026 (figure 1b).
The 42-filing pilot that motivated the full sample straddles the transition
directly: 2025-03-07 accepted at 08:32:24 local with offset -5, and 2025-03-10 at
08:31:23 local with offset -4. The rule in `timesemantics.py` is written out rather
than delegated to a tz database, so a published number cannot change under a
system update; it is cross-checked against `zoneinfo` where available.

### 4.3 The after-hours deferral is measurable, not assumed

`Last-Modified` on the archived document is the only server-side moment at which
we can **prove** the bytes existed. Split at the 17:30 ET cut-off:

| group | n | median | p95 | > 1 h | > 1 day |
|---|---|---|---|---|---|
| accepted before 17:30 ET | 703 | **35 s** | 141 s | 5 | 5 |
| accepted after 17:30 ET | 17 | **41 717 s (11.6 h)** | 215 854 s | 16 | 3 |

The after-hours cases land at ~10:00 UTC = **06:00 ET**, the moment EDGAR opens
(Filer Manual §2.3.1: "available ... from 6:00 A.M. to 10:00 P.M., Eastern Time"),
and the three Friday-evening filings land on **Monday** at that hour. This is the
documented deferral, observed independently of the document that states it.

### 4.4 The filing date is a business day, not an instant

| filing date vs Eastern acceptance date | filings |
|---|---|
| same day | 704 (97.8%) |
| +1 day | 13 |
| +3 days (Friday evening -> Monday) | 3 |

All 13 "+1" and 3 "+3" cases were accepted after 17:30 ET. One further
after-hours filing (SYK, 2020-07-30 18:51 ET) kept a same-day filing date; the
regulation keys on when *direct transmission commences*, not when EDGAR finishes
accepting, so this is consistent with 17 CFR 232.13(a)(2) rather than an
exception to it. **Using `filingDate` as an instant is therefore wrong by construction,
and using it as "public by this day" is right only at day granularity.**

### 4.5 One honest anomaly

Eight filings show an acceptance->`Last-Modified` gap above one hour, and four of
those are 43-244 **days** - all from early 2017. The archive file was rewritten
(most likely a bulk re-render), so for those filings `Last-Modified` bounds
nothing useful. They are counted in `> 1 day` above and shown as the high outliers
in figure 1c. `Last-Modified` is an upper bound that can be arbitrarily loose;
it is never a dissemination time.

---

## 5. Field-by-field: what may be claimed

| field | supports | does not support |
|---|---|---|
| raw `ACCEPTANCE-DATETIME` (+ DST rule) | "accepted by EDGAR at T_utc"; intraday ordering; lower bound on availability | that an outsider could retrieve it at T; that any market had priced it; anything about the event |
| `acceptanceDateTime` (API, Z) | the same instant, if the header is unavailable | independent information - it is a faithful transform of the same field (verified 720/720) |
| `filingDate` | day-level membership; the business day the filing is dated | any intraday ordering; a reliable availability instant |
| HTTP `Last-Modified` of the archived document | "the bytes existed on the SEC server by T" | when they *first* existed (re-renders); that anyone was notified |
| Atom `<updated>` | the same acceptance instant with an explicit offset | dissemination - it equals acceptance, so it adds no availability information |
| PDS feed | that a paid dissemination channel exists | any per-filing time; PDS is documented to *follow* SEC.gov |
| `reportDate` / period of report | when the reported event occurred | availability - it often precedes the filing by days |
| our `fetched_at_utc` | when we collected the bytes | any historical public time |

## 6. What cannot be reconstructed

1. **The first external retrieval instant.** Not published, not derivable. Our
   bound is `[acceptance, archival Last-Modified]`; for 97.6% of filings that
   interval is under a minute, so the residual uncertainty is small - but it is
   an interval, not a timestamp.
2. **Whether a third party had the data earlier** (newswire, investor relations
   site). Out of scope for EDGAR; a company press release may precede the 8-K by
   hours, and this study cannot see that.
3. **Content state at a historical instant.** EDGAR archives are immutable per
   accession (no in-place edit was observed; corrections arrive as new 8-K/A
   accessions), so the archived bytes *are* the historical bytes - but our only
   proof of retrieval is the archive itself.

## 7. Rules this study adopts (and enforces in code)

1. Point-in-time cuts use the **verified acceptance instant**, never `filingDate`.
2. Every timed row must carry grade A (or A2) or be excluded; `build` refuses
   `B`/`C`/`D` rows instead of imputing.
3. After-hours filings are flagged: they are the rows where "accepted" is knowably
   not "available". In this panel they are 13/683 (1.9%) of 8-Ks.
4. `Last-Modified` is used only as an upper bound, and an loose one; it never
   narrows a claim.
5. Any lead-time statement is reported against the **acceptance** clock and
   labelled a lower bound on the true lead time.

## 8. Correction to E1b

E1b (`docs/refoundation/phase2/E1B_SOURCE_RECOVERY.md`) concluded that `acceptanceDateTime`
is "a genuine public instant" and that ""Public by instant T" iff
`acceptanceDateTime` <= T". On a 5-filing, one-issuer sample that was a
reasonable reading; on 720 filings it is not tenable as stated:

* the instant is real and now verified (E1b could not verify the offset; we can),
  but it is an **acceptance**, not a publication, instant;
* E1b's own corroboration (`Last-Modified` trailing by 21-75 s) is in fact
  evidence of a *gap* between acceptance and availability - one that becomes a
  weekend for after-hours filings;
* E1b's "filing and acceptance are same-day in all sampled cases" holds on
  n=5 but is false for 2.2% of filings in this sample, exactly where the
  regulation predicts it should be.

Nothing in E1b's operational recommendation (use EDGAR first) changes. What
changes is the claim: acceptance bounds availability; it does not equal it.

## 9. Reproduce

```
python research/science_001/cli.py fetch      # network
python research/science_001/cli.py verify     # offline; writes time_verification.*
python research/science_001/cli.py figures    # offline; figure 1
```

`artifacts/time_verification_summary.json` holds every number quoted above;
`artifacts/time_verification.csv` holds the per-filing evidence.
