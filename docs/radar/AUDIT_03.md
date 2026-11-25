# Audit 03 — rounds 20–29

Third scheduled audit. Audit 01 fixed a flaky suite and a duplicated truth; audit 02 found the second
cause of the flake and the slowest page. This one is about what a reader pays on their **first** visit
to each page, and about three conclusions from earlier rounds that later measurements overturned.

## 1. The defect: the warm-up covered the front page and nothing else

Cold, server-side, on a freshly restarted process:

```
/                                0.29 s
/areas                           0.34 s
/map                             0.30 s
/device?query=K213506            0.47 s
/device?query=Clydesdale         0.48 s
/company?q=ARUM                  0.42 s
/compare?q=Medtronic,Globus      0.89 s
/sources                         0.94 s
/company?q=Medline               1.08 s
/radar                           1.16 s
/paper?id=PMC12568234            4.71 s   <-- the second link in the nav
```

`/paper` again, immediately after: **0.29 s.** Nothing was slow; the index was cold. The startup
warm-up (`warmup()`) touched the device register, five identifier shapes, the paper *total*, and the
landing page's four counts — but never the paper index the reverse-lookup page reads.

So the cost landed on whoever opened the second-most-prominent link in the navigation, once per
restart, and the page's own 120 s cache made it look like a random hang to the next reader who
happened to be second.

**Fix.** `warmup()` now runs the same queries each nav page runs — the paper record, its terms, the
distinctive-term filter and the brand join for the paper with the most terms; `_company_data`, the
specialty map, and the coverage assembly. Each step is allowed to fail, because a deployment without
one of those tables must still serve the others.

Measured after a restart, first visit to each:

```
/                               0.28 s
/map                            0.30 s
/areas                          0.33 s
/radar                          0.41 s
/device?query=X1209255          0.50 s
/company?q=Medtronic            0.61 s
/compare?q=Medtronic,Globus     0.91 s
/sources                        0.95 s
/paper?id=PMC12568234           1.02 s   (was 4.71 s)
```

The remaining second on `/paper` is that one paper's own terms; the warm-up primes the index, not
every document.

## 2. Three things I got wrong, and what measurement said

Recorded here because an audit that only lists successes is not an audit.

| Claim | Where | What measurement showed |
| --- | --- | --- |
| "The health unit is failing because three sources refuse this host" | round 22 report | All four critical sources were OK. The unit was red because one probe sample landed in a deploy's 18 s restart. Fixed in round 23 with retries. |
| "The remaining 1.4 s of `resolve` is `SELECT *` on wide JSON columns" | round 27 commit | The table has ten small columns. The cost was two `COLLATE NOCASE` full scans running before the name paths, where they could not match. Fixed in round 28: 1.40 s → 0.003 s. |
| "Persisting paper histories is what a name query needs" | audit 02 | Not first. The page computed ten to twenty-five device histories and displayed one. Fixed in round 27: 5.39 s → 3.02 s, before any persistence work. |

The pattern is the same each time: a plausible cause accepted without a measurement. The instrument
that found the third one was SQLite's `set_trace_callback`, which prints every statement and its
timing — two minutes of work after two rounds of guessing.

## 3. Checked and found acceptable

| Check | Result |
| --- | --- |
| Every page reachable from the nav | yes |
| Every page route passes the gate allowlist | yes, tested |
| Every gap code has a sentence | yes, tested |
| Exports carry the page's qualifiers | yes, tested per page (group-level trials, company-level papers, sampled areas, capped code lists) |
| A number that means "how much we fetched" is never printed where "how much there is" belongs | fixed three times: papers (round 14), watermarks (round 24), product-code caps (round 26) |
| Cached numbers print when they were taken | yes |
| Source health and graph staleness are visible | yes; `/sources` lists 13 sources with last success and reason |

## 4. Known and not fixed

- **`/sources` at 0.95 s** is the second slowest page; it runs three live count queries plus the
  ledger's source table. It is a page about data, opened rarely, and it is honest; not worth the
  complexity of another materialised set.
- **`/company?q=Medline` at 1.08 s cold, 0.30 s after warm-up.** The remaining cost is counting
  brands and failures for a labeler with 252,243 devices.
- **Patent coverage 92 / 12,537 labelers; failure sweep 838 / 5,229 product codes.** Both are stated
  on `/sources` with their reason.
- **The map covers three companies.** Stated, not hidden.
- **Public URL rotates.** `public_url.txt` is the only trustworthy address.

## 5. What the next audit should ask

1. Does the warm-up stay bounded? It now runs several page queries at startup; if the register grows,
   a restart could spend a minute warming. Measure the warm-up's own duration, not only its effect.
2. Round 22 added source health and round 24 unified watermarks. Is there any number left on a page
   that has never been compared against the table it claims to describe?
