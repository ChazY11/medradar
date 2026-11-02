# THIRD-SOURCE PROTOCOL — Europe PMC cross-validation of the nine events

**Status:** FROZEN before any query was issued · **Study:** `early_signal_5firms` ·
**Branch:** `research/early-signal-third-source` · **Supersedes:** nothing

> Question: for each of the **nine** small-sample events, is there an **independent publication record**, dated strictly
> before the clearance, that places research relevant to that device track before the regulatory event?
>
> This adds evidence to packets. It does **not** create labels, and it changes no existing packet field except by adding
> a new one.

---

## 1. Why this source

`EXTERNAL_SOURCE_PROBE.json` (S-022) found that PatentsView returns a landing page while **Europe PMC returns usable
JSON** — the first new earlier source since the study began that is (a) dateable, (b) independent of the regulatory
family, and (c) machine-readable without credentials. Publications are a different recording process from both
ClinicalTrials.gov and openFDA, so a publication hit is an *independent* corroboration, not a tautology.

## 2. The nine events

Taken verbatim from `CASE_PACKETS_SMALL_SAMPLE.json` (nine distinct later clearances, produced by
`experiments/b094/small_sample_lead_time.py`). No event may be added or removed after results are seen.

For each event the protocol uses: company, technology track, the crosswalk's matched keywords, clearance date and the
representative trial date — all already committed.

## 3. Query construction (deterministic, recorded verbatim)

For each event one query string, built by a fixed rule:

```
(AFF:"<company term>" OR AFF:"<company alias term>") AND (<keyword term 1> OR <keyword term 2> ...)
```

- **Company terms** come from a frozen table: Medtronic, GE HealthCare / GE Medical, Philips, Siemens (not used here),
  Mindray, Dräger — the same applicant aliases the study already uses.
- **Keyword terms** are the matched keyword phrases recorded in the packet, upper-cased and reduced to their longest
  token sequence (at most three terms, to keep the query specific).
- The **verbatim query string is stored** in the artifact, so the search is reproducible by hand.
- Result page size **25**, at most one page, sorted by the API default; the API's total hit count is recorded even when
  only the first page is inspected.

## 4. Availability rule

- The date used is Europe PMC's **first publication date** (`firstPublicationDate`), never acceptance, revision or
  deposit date.
- A record is **eligible** only if that date is **strictly before** the clearance date.
- Records without a parseable date are recorded as `UNDATED` and may not be used as corroboration.

## 5. Independence rule

- A publication is independent of the trial registry and of the regulatory record by construction (different recording
  process, different venue).
- A publication that merely reports the *same trial* is **not** independent evidence of a change; it is recorded as
  `TRIAL_REPORT` and may not be counted as corroboration. Detection rule: the record's title or abstract mentions the
  trial's NCT identifier, or the query is restricted to trial reports.

## 6. Status vocabulary (fixed)

| status | meaning |
|---|---|
| `SUPPORTED_BEFORE` | ≥1 independent, dated-before record found |
| `NO_RECORD` | the query returned no usable record |
| `AMBIGUOUS` | records exist but none is independent (e.g. only trial reports), or dates are undated |
| `AFTER_CLEARANCE` | records exist but all are dated on/after the clearance |

## 7. What is computed

Per event: hits total, usable hits, earliest independent publication date, **lead in days and quarters** relative to the
clearance (positive = publication earlier), and the verbatim earliest title/authors/journal as citable evidence. No
aggregate claim is made across the nine events beyond counts per status; the study already recorded that n = 9 is below
the independence floor.

## 8. What is forbidden

- Creating, inferring or back-filling any `final_label`. Packets keep `PENDING_HUMAN_REVIEW` and `final_label = null`.
- Treating `NO_RECORD` as evidence of absence of research: a null search is a null search.
- Treating a publication hit as evidence of a technology *shift*: a paper before a clearance is compatible with routine
  incremental work.
- Any claim of predictive skill; any aggregate across firms; any generalisation from nine events.

## 9. Human sign-off

The owner has authorised this line of work (S-019). The packets remain human work: a reviewer decides, per event,
whether the publication is genuinely about the same device direction.
