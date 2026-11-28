# Audit 13 — rounds 120–129

Thirteenth audit. The tests this time were the ones audit 12 left: policy constants typed twice, broad excepts
around schema-dependent reads, and whether the front page still leads to the newest answer.

## 1. The defect: an unreadable table reported as "never computed"

`field_trends()` returns an empty mapping for every failure. The pages interpret that mapping as "no field has a
rising term" and `/areas` prints **从未算过** - never computed. So a table whose schema moved (a column added by a
newer tool, a rebuild by an older one) produces a sentence that is false about a different thing:

```
table missing      -> 从未算过                     correct
table unreadable   -> 从未算过                     wrong: it was computed, and cannot be read
```

This is the same distinction rounds 124-127 fixed at the four search boxes ("we cannot count" is not "there is
none"), missing one layer down at the data source.

Fixed: `field_trends_status()` probes with **the same eight-column select `field_trends` performs** - `COUNT(*)`
answers happily on a table whose schema moved, which is why the first version of the probe passed the broken case.
`/areas` now prints `读不出来（no such column: recent）` instead of `从未算过`, and a healthy table is unchanged.

```
no table      {"present": false, "readable": false, "error": ""}
old schema    {"present": true,  "readable": false, "error": "no such column: recent"}
healthy       {"present": true,  "readable": true,  "rows": 20, "computed_at": "2026-11-28"}
```

## 2. Policy constants, one round after the last one

Audit 12 found the trend threshold written five times. This audit asked whether more policy values are typed
repeatedly, and found the page TTL: `300.0` at **nine** `cached(...)` call sites, each with a comment explaining
that the number is the scheduler cycle. One `PAGE_TTL` now.

Also removed: `_MAP_CACHE` and `_MAP_TTL`, defined at the top and referenced nowhere - dead since the map moved
to a written snapshot. A dead constant holding the live value (300.0) is what a later reader "fixes" in good
faith.

## 3. Broad excepts and schema-dependent reads

53 in the page layer. The question audit 12 posed was how many guard a **schema-dependent read** rather than a
network call, because those can hide a migration. The trend table was one, and it is now instrumented. The rest
were not enumerated - that remains a known gap, and this audit does not claim otherwise.

## 4. The front page

`/` answers the newest-answer question in place: a "最近发表" block with the eight newest papers we hold, each
linked, with the bound printed ("这是'我们手上的论文里最新的'，不是全部新论文；出版日期在未来的期刊预填记录已
排除"). The block does **not** link to `/radar`, which since round 111 carries the full 14-day, per-field view.
The navigation bar has 实时雷达, so the path exists, but the block itself does not offer it - recorded as a
nicety, not fixed this round.

## 5. Counts and availability

```
gate 401 · tunnel restarts 0 · failed units 0
public / 0.74 s · /areas 0.92 s · /area 1.19 s · /sources 0.80 s
```

## 6. Known and not fixed

- **53 broad `except Exception`** in the page layer; only the trend table is now instrumented.
- **The front page's recent block does not link to /radar.**
- **One second per unknown company name** in `/compare` and `/company` (bounded to four names).
- **Patent coverage** 92 applicants / 264 patents; **`paper_field` covers 2,414 of 5,560** papers.
- **Nine of twenty fields cannot be ranked** for lack of recent papers - a data gap.
- **The public address rotates**; a reconnect costs a few seconds of 502.

## 7. What the next audit should ask

1. Which other **materialised tables** are read through a broad except (`specialty_stats`, `store_stats`,
   `paper_field`)? Each is the same "empty or broken?" question, answered silently today.
2. Does any page print a number whose **basis** the reader cannot see (a count over a capped window, a rank over
   a filtered set)? The trend rank and the 120-per-field cap both qualify; both are stated, in two places.
3. Which of the 53 excepts would **survive a deliberately broken store**? That is a runnable test, not a reading
   exercise: drop a column, load each page, see which one lies quietly.
