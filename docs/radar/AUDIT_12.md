# Audit 12 — rounds 110–119

Twelfth audit. Ten rounds of feature work on the "what is moving" thread produced the same defect this series
keeps finding, in a new place: **one threshold, five copies**.

## 1. The defect

The rule is simple: a field's rising term is only worth ranking when its recent window holds at least 60 papers.
Written down, it looked like this:

```
pages.py:1079      TREND_SMALL_WINDOW = 60                      the constant
pages.py:2450      if recent < 60 else ''                       an inline comparison
paper_passes.py    def trend_rank(..., min_total: int = 60)     a default argument
export.py:390      "只排近 90 天样本达到 60 篇的领域"             a sentence in a file
pages.py:2256      f"{TREND_SMALL_WINDOW} 篇的领域"               the only correct use
```

Changing the number would have updated two of five. The page and the export would then disagree about which
fields qualify - the same failure as audit 08 (two Chinese alias parsers), audit 09 (word-frequency units) and
audit 10 (a variable in two scopes), now on a policy constant instead of a value.

Fixed: `paper_passes.TREND_MIN_PAPERS`, a module constant; `trend_rank` takes it as the default; `pages.py`
aliases it (`TREND_SMALL_WINDOW = _TREND_MIN_PAPERS`) and the inline comparison uses it; the export sentence is
an f-string over the same name. A test now fails if a bare `60` reappears in a comparison or in that sentence.

## 2. Counts

```
devices 5,258,159 · papers 5,560 · trials 2,967 · patents 264
papers linked to a field 2,414 · field_trend rows 20, of which 11 qualify (>= 60 recent papers)
```

Every materialised count matches its table. The 11-of-20 is not a defect: nine fields have too little recent
literature for a lift to mean anything, and the page says so instead of ranking them.

## 3. Boundary probes

| Input | Result |
| --- | --- |
| `/topic?id=nope` · `/paper?id=` · `/area?name=Nope` | 200, states the miss |
| `/device?query=` · `/company?q=` · `/compare?q=` | 200 |
| `/areas?sort=bogus` | 200, falls back to devices |
| `/areas?sort=trend` · `csv&sort=trend` · `recent&format=json` | 200 |
| `/format` | 404 (no such route) |

No 500s.

## 4. Timing

```
/ 0.31 · /areas 0.30 · /areas?sort=trend 0.30 · /sources 0.30 · /area 0.30
/company 0.30 · /map 0.31 · /device 0.53
```

The warm set is 0.30 s - half of audit 11's 0.52-0.64 s. Nothing was optimised in these ten rounds; the earlier
sample was taken while the nightly rehearsal and the scheduler were running. Recorded as measured, both times.

## 5. Audit 11's three questions

**"Which numbers are still computed twice?"** This one - the threshold. The genuine duplicates left are
deliberate and named: `order_area_items` and `trend_rank` both apply the threshold, but now read the same
constant, and the second's docstring points at the first.

**"Which `except Exception` wraps a computation rather than a source read?"** Round 115 produced a fresh
example: a test fixture built the six-column `field_trend`, the eight-column read raised, a broad except
swallowed it, and the page silently lost a line. The exception was doing what it was written to do - but what it
was written to protect was a *source that might be missing*, not a *schema that had moved*. Nothing in the
current code distinguishes those; that is the honest state.

**"Does any page answer a question the reader did not ask?"** Round 111 added the answer to the real question on
`/radar` (what came out) beside the one it already answered (what our sources did). No page was found answering
a question nobody asked.

## 6. Known and not fixed

- **53 broad `except Exception` in the page layer**, unchanged. I have not proven they are safe, only that no
  path I exercised broke.
- **One second per unknown company name** in `/compare` and `/company` (bounded to four names since audit 11).
- **`/device` English miss** 1.0 s plus the suggestion table when the scan is truncated.
- **Patent coverage** 92 applicants / 264 patents; **`paper_field` covers 2,414 of 5,560** papers.
- **The public address rotates**; a reconnect costs a few seconds of 502.
- **Nine of twenty fields cannot be ranked** for lack of recent papers - a data gap, not a code one.

## 7. What the next audit should ask

1. Which *policy* constants are still typed twice - the threshold was one; are there others in the 500s
   (page TTLs, top-N limits, sample caps)?
2. Of the 53 broad excepts, how many guard a **schema-dependent read** rather than a network call? Those are the
   ones that can hide a migration.
3. Which page would a reader open first, and does it still lead to the newest answer in one click?
