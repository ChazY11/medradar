# Audit 05 — rounds 40–49

Fifth scheduled audit. Audits 01–04 fixed a flaky suite, a ten-second page, a cold-start gap and a
dead end for Chinese company names. This one found that **the feature I added in rounds 38–39 made two of
the most-used pages five seconds slow**, and that a number on `/areas` was counting the wrong thing.

## 1. The scheduled run has not fired, and the clock did not help

The nightly job is scheduled for 04:31 local. I checked at 03:01, 03:15, 03:27, 03:35, 03:42, 03:49,
03:58 and the wall clock did not advance. So the evidence for the scheduled run is not a scheduled run;
it is the dry run from round 46, which executed the same script with the 600 s patent waits shortened to
seconds. That is what validates the chain. Recorded here so the next audit does not mistake the dry run
for a scheduled one.

## 2. Every number compared against its table

Thirteen materialised counts, one pass, all match:

```
devices 5,258,159 · failures 348,742 · trials 2,967 · patents 264 · papers 3,594 · codes 5,181
failure_codes 838 · failure_models 47,553 · failure_brands 40,707 · trial_sponsors 808
patent_assignees 92 · specialties 21 · corpus 40,731
```

New surfaces checked for the first time: `paper_meta` 3,594 (equals `paper_term`'s distinct papers, so
nothing is indexed without metadata), `paper_field` 357, `paper_pass` 3, `failure_sweep` 108.

## 3. The defect: a label counting the wrong set

`paper_field` says which papers a field's query **matched**. `paper_meta` says which are **archived**.
The column reads 篇已归档 and took its number from the first:

```
Cardiovascular   matched 117   archived 115
Dental           matched 120   archived 117
Orthopedic       matched 120   archived 120
```

Five papers were counted as held while we hold no full text for them. `by_specialty` now reports both:
`papers` (archived, what the label claims) and `matched`, and the column prints the difference:

```
Dental  117 篇已归档（查询命中 120，其中 3 篇没有全文）
```

## 4. The defect that mattered more: five-second pages

Measured cold, ten pages, server-side:

```
/                0.33s     /company      0.61s
/areas           0.28s     /compare      1.20s
/radar           0.46s     /paper        1.18s
/map             0.31s     /sources      1.39s
/device?query=K213506   5.17s   ←
/area?name=Dental       4.99s   ←
```

Both are the pages that gained literature blocks in rounds 38–39. The cause was not the page code:

```
EXPLAIN QUERY PLAN: SCAN paper_term USING INDEX idx_paper_term_term
2,704 ms for one "terms of these 120 papers" query, twice per field page
```

`paper_term` had an index on `term` and none on `paper_id`, so asking for the terms of a list of papers
scanned all 982k rows. Adding `idx_paper_term_paper` (1.3 s to build):

```
SEARCH paper_term USING INDEX idx_paper_term_paper (paper_id=?)
58 ms   — 47× faster
```

After the fix, cold:

```
/device?query=K213506  0.49s      /area?name=Dental        0.38s
/area?name=Cardiovascular 0.37s   /sources                 1.39s
/                        0.31s    median 0.38s
```

This is the same class of mistake as audit 02's ten-second page: a feature added without measuring the
query it introduced. The instrumentation that catches it — server-side timing of every page, cold — was
in place and I did not run it after adding the feature.

## 5. Checked and acceptable

| Check | Result |
| --- | --- |
| Chinese company names on /device, /company, /compare | resolved, substitution printed |
| Chinese field names on /area | opens the field, names the mapping used |
| Forward-dated records (14 of 3,594) | excluded from every "latest" list, labelled on the paper page |
| Function words in paper term chips | filtered (186-entry list) |
| Export of a field's papers | md carries the bound; csv is pure data and the page says so |
| Nightly chain | 11 steps recorded, numbers agree with the index |
| Narrow viewport (390 px) | no page-level overflow; wide tables scroll inside their card |

## 6. Known and not fixed

- **Public address rotates** and occasionally spikes (single samples of 7–9 s through the tunnel while
  the server answers in 0.5 s). A stable address needs an operator decision.
- **Patent coverage** 92 applicants / 264 patents. Google Patents is windowed; three attempts a night.
- **Literature coverage** 3 of 12 fields.
- **`/sources` at 1.39 s** is the slowest page now; it assembles four separate aggregates.

## 7. What the next audit should ask

1. Does the warm-up cover the pages it claims? `/device` and `/area` were slow cold and fast warm, which
   is why the regression hid.
2. Is there any other query keyed on a column without an index? Two found so far, both by measurement
   rather than review.
