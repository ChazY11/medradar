# Audit 06 — rounds 50–59

Sixth scheduled audit. Audit 05 found a label counting the wrong set and the literature feature that had
turned two pages five seconds slow. This one found a **4.7% hole in the literature lane that no page
mentioned**, and confirmed that the warm-up did not cover the pages it should — the question audit 05
left for itself.

## 1. Counts: eleven materialised numbers, all matching

```
devices 5,258,159 · failures 348,742 · trials 2,967 · patents 264 · papers 5,485 · codes 5,181
failure_codes 838 · trial_sponsors 808 · patent_assignees 92 · specialties 21 · corpus 40,731
```

## 2. The defect: 270 files that nothing counted

The literature corpus holds **5,755 files**. The index holds **5,485 papers**. Every page reported the
second number and nothing anywhere explained the difference — a reader could not tell whether the lane
was complete, filtered, or failing.

Measured, by walking the corpus and comparing identifiers:

```
files 5,755 · indexed 5,485 · missing 270 (4.7%)
reason: all 270 yield no vocabulary term (they also carry no title; the empty abstract is the cause)
```

`index_corpus` now counts what it skips and why:

```
{"papers_indexed": 5485, "files_seen": 5755,
 "skipped_no_title": 270, "skipped_no_terms": 270, "unreadable": 0}
```

5,485 + 270 = 5,755 — the accounting closes. `/sources` now says so beside the number:

> 论文全文 5,485 · 已归档全文，不是摘要；语料目录里还有 270 个文件没有被索引：它们没有命中注册表词表的词，无法检索。

And the nightly ledger row carries the same three numbers, so a run that suddenly skips a lot is visible
the night it happens.

## 3. The warm-up did not cover two of the pages

Audit 05 asked: "Does the warm-up cover the pages it claims?" It did not. Measured cold, first request
after a restart, before this round's change:

```
/radar     3.80 s     /compare   1.78 s     /sources  0.96 s     /company  0.95 s
everything else 0.28-0.55 s
```

`warmup()` read the device register, the dossier, the paper index and the landing-page counts, and
stopped. The radar feed reads the whole observation table and was never touched.

Added to the warm-up: the change stream plus the observation count, and the company lookups the compare
page needs. Result:

```
/radar  3.80 s -> 0.42 s
```

`/compare` is unchanged at 1.76 s cold, and the reason is worth stating precisely: **warming the data
does not warm the route's cache.** Every page is served through `cached(key, ttl, render)`, which stores
the rendered HTML; `warmup()` calls the underlying builders, so the route still renders on first hit.
Fixing that means priming the cached entries themselves, which needs the render closures extracted to
module level. Not done this round, and recorded below.

Warm, everything is 0.28–0.34 s except `/company` (0.75 s) and `/device` (0.53 s).

## 4. The ledger now distinguishes a rehearsal from the night

Twenty-one runs accumulated in the ledger, most of them mine. `/sources` showed the newest under
最近一次夜间任务 with real step counts — indistinguishable from the 04:31 run that actually fired.
`MEDRADAR_NIGHTLY_DRY=1` now marks a run, and the page says 这次是手动试跑.

An interrupted run (steps but no `done`) is likewise annotated, and the guard that stops two crawlers
running at once was added with its own check (`tools/check_nightly_lock.sh`), after the first attempt
shipped and had to be reverted.

## 5. Checked and acceptable

| Check | Result |
| --- | --- |
| Every specialty has literature | 20 of 20 rows on /areas carry an archived count |
| Archive count vs match count | the difference is printed, per field |
| Function words in chips | filtered on the field, company and topic pages |
| Forward-dated records | excluded everywhere, labelled on the paper page |
| Public gate | 401 without credentials, 404 for non-public paths |
| Failed units | 0 |
| Narrow viewport | no page-level overflow |

## 6. Known and not fixed

- ~~**`/compare` cold 1.76 s.**~~ **Resolved in round 61.** The routes now register their canonical
  requests in `_PAGE_ROUTES` and `warmup()` calls them, so the cached HTML is primed instead of only the
  data underneath. Measured after a restart: `/compare` 1.76 s -> 0.28 s, `/radar` 3.80 s -> 0.31-0.45 s,
  `/sources` and `/company` unchanged and already fast.

  One honest caveat: for about 90 seconds *after* a restart the warm-up thread competes with real
  requests for the two cores, and `/compare` measured 1.72 s at 45 s in. Priming all seven pages made it
  worse (4.6 s) - home, areas and map answer in 0.27-0.39 s cold and are no longer primed.
- **Patent coverage** 92 applicants / 264 patents; Google Patents is windowed.
- **`paper_field`** holds 23 papers with no archived text; the column reports the difference.
- **Public address rotates**; a single sample has been 5–9 s while the server answers in 0.3 s.

## 7. What the next audit should ask

1. Is there a page whose cache key can collide — two different inputs sharing one `cached()` key?
2. Does any count on a page come from a `glob` rather than the database, where the two could drift?
3. The ledger has 21 runs of which most are rehearsals; should the page show the newest *scheduled*
   run instead of the newest run of any kind?
