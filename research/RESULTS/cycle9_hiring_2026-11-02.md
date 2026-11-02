# Cycle 9 — hiring data: lawful source found, coverage measured, lag question not yet answerable (2026-11-02)

**Status:** completed as a **feasibility partial**. B-030 moves to blocked with a measured reason.
Evidence: `experiments/b030/` (panel, lag analysis, generated report). Decisions: D-028, D-029.

## Why this cycle mattered

Six cycles established that the regulatory filing lane cannot answer the programme's questions: ~0.2
events per cell-month, no independent confirmation source until B-040, and every clustering claim
dissolving under its own control. The declared remedy was not another estimator but **more
information**: hiring data, with genuine historical availability.

## What was found

Three lawful routes were probed; two closed on access grounds:

| route | result |
|---|---|
| PatentsView bulk (S3) | **403 Forbidden** — credentials required; patents stay blocked |
| Common Crawl index API | **persistent 504** even for `example.com` |
| **Wayback Machine CDX** | **works keyless**; archives real job-posting URLs (Medtronic: 15 index pages, postings back to 2010) |

A bounded, rate-limited collector now produces a monthly posting-flow panel from the archive
**index only** — no page content is fetched. Because the archive predates the analysis by years, the
signal is genuinely historical rather than reconstructed by our own collection.

## Coverage, measured honestly

16 device firms probed → 6 yielded posting URLs → **2 pass the pre-declared usability floor**:

| company | postings | months with postings | usable |
|---|---:|---:|---|
| `bd` | 2,408 | 60 | **yes** |
| `boston_scientific` | 2,065 | 88 | **yes** |
| `dexcom` | 125 | 22 | no (< 24 months) |
| `edwards_lifesciences` | 119 | 34 | no (> 50 % silent months) |
| `intuitive_surgical` | 80 | 16 | no (< 24 months) |
| `medtronic` | 31 | 7 | no (shallow paging) |
| 8 further firms | 0 | 0 | no archived postings under the probed hosts |

## Why the lag profile is not reported as a result

The pre-registered lag test was run and its output committed, but it rests on **two** companies: the
pooled profile is close to an average of two correlations with no usable standard error. Its values
are uniformly negative, and that sign is **uninterpretable** — the proxy counts only postings the
archive happened to capture, so capture gaps and regulatory gaps can align for reasons unrelated to
hiring. This is an **unrun question with its machinery built**, not a null result about hiring.

**The usability floor was deliberately not loosened** to raise the sample: adjusting eligibility after
seeing that it excludes most of the data is the specification search that D-027 closed for the entry
thread.

## What would unblock it (B-047)

1. **Per-company career-domain mapping** — eight firms returned nothing because their career sites are
   on hosts the patterns did not guess. Discovery problem, not statistical.
2. **Platform-change audit** — career sites migrate between posting-URL schemes; a migration creates a
   level shift that is a collection artifact.
3. **Archive-depth fix** — CDX deep paging did not return Medtronic's full 15 pages under the current
   parameterisation; an implementation defect, not a property of the source.

## Position of the programme after nine cycles

Six tempting positives, all dissolved under better controls; zero surviving positive claims; one
lawful independent lane (trials) that is too sparse at cell level, and one lawful historical hiring
lane that is too thin in coverage. The deliverable remains the map — now specific enough to say
exactly which two data-acquisition problems stand between this programme and its first defensible
empirical claim: **career-domain discovery** and **patent access**.
