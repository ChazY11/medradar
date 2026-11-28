# Audit 07 — rounds 60–69

Seventh scheduled audit. Audit 06 found a 4.7% hole in the literature lane; this one found that **the
page which says "not found" was the slowest page on the site**.

## 1. Counts: eleven materialised numbers, all matching

```
devices 5,258,159 · failures 348,742 · trials 2,967 · patents 264 · papers 5,485
codes 5,181 · failure_codes 838 · sponsors 808 · assignees 92 · specialties 21 · corpus 40,731
```

`paper_files` 5,755 and `paper_indexed` 5,485 are both correct - one is the corpus directory, the other is
the index. My first check compared the file count against `paper_meta` and called it a mismatch: the error
was in the audit, not the data. (Fourth time an audit's own instrument has been the thing at fault.)

## 2. The defect: saying "not found" cost 20.7 seconds

```
/device?query=不存在的编号    21.6 s
/device?query=zzzznotarealbrand   6.6 s
```

Both are misses, and a miss is the case a reader hits by typo or by typing a name we do not hold. Profiled:

```
resolve('不存在的编号')   20.7 s, in 9 sqlite execute calls at 2.3 s each
```

The chain fell through to four full passes over 5.2M rows:

- `brand_name LIKE '%…%'` and `company_name LIKE '%…%'` - a leading wildcard cannot use an index
- `version_or_model = ? COLLATE NOCASE` and `catalog_number = ? COLLATE NOCASE` - a `BINARY` index cannot
  answer a case-insensitive comparison, so each scans the whole table

### Fix 1 — the register is ASCII, so Chinese needs no scan

GUDID names, models and catalog numbers are ASCII. A Chinese query can never contain-match them, and the
alias table resolves Chinese names to English earlier in the same function. Anything still Chinese at that
point is a miss, so it now returns without scanning.

```
不存在的编号   21.6 s -> 0.27 s
```

### Fix 2 — expression indexes instead of full scans

```sql
CREATE INDEX idx_udi_model_nocase   ON udi_device(version_or_model COLLATE NOCASE);
CREATE INDEX idx_udi_catalog_nocase ON udi_device(catalog_number  COLLATE NOCASE);
```

The same miss became 0.1 ms, and recall is unchanged - this was never about dropping the fallback, it was
about making it indexable.

```
zzzznotarealbrand   6.6 s -> 1.29 s
Q999999             0.29 s (was 1.7 s)
```

### Fix 3 — a scan that stops early must say so

The two contains-scans now carry a one-second budget. If the budget is spent the search ends, and the page
prints 按名称片段搜索时扫描到了时间上限就停了 instead of claiming the name is absent - "we stopped looking"
and "it is not there" are different answers.

The mechanism is tested, but on the live store the scans usually finish inside the budget, so in practice
the time is saved by the expression indexes and the note rarely appears. Recorded that way rather than
described as if the budget were doing the work.

Also fixed while wiring it: the not-found page printed one hardcoded gap code and ignored the rest of
`timeline.gaps`, which would have hidden this note even when it fired.

## 3. Timing, after

Server-side, warm, after the deploy:

```
/ 0.28 · /areas 0.32 · /sources 0.30 · /map 0.30 · /radar 0.30
/company 0.30 · /compare 0.34 · /area 0.33 · /topic 0.39 · /paper 0.39
/device K213506 0.52 · Medtronic 0.60 · Clydesdale 0.58
```

Public, through the tunnel: 0.69–1.02 s.

## 4. Checked and acceptable

| Check | Result |
| --- | --- |
| Every route answered | 24 paths, 0 × 5xx |
| Chinese input | `/area?name=牙科`, `/company?q=美敦力` resolve via alias, 0.30 s |
| Cold start after restart | every page 0.28–0.34 s once the warm-up finishes |
| Public gate | 401 without credentials |
| Failed units | 0 |
| Corpus accounting | 5,485 indexed + 270 skipped = 5,755 files |

Four paths answer 400 to a raw unencoded CJK query in curl; percent-encoded (what a browser sends) they
answer 200. That is correct behaviour, not a defect.

## 5. Known and not fixed

- **A cold `/compare` pair is still ~1–2 s** when one company is very large; Medline's own dossier costs
  0.7 s, mostly `COUNT(DISTINCT json_each(...))` over 252k devices, which no index removes.
- **Patent coverage** 92 applicants / 264 patents; Google Patents is windowed.
- **Public address rotates**, and a single sample has been 5–9 s while the server answers in 0.3 s.
- **The warm-up competes with real requests** for the first ~90 s after a restart.

## 6. What the next audit should ask

1. Does any page still print a count from a `glob` where the database would answer?
2. `resolve()` has five fallbacks in sequence - is any of them still reachable, or is the chain longer than
   the data needs?
3. Which claims on the site would a hostile reader call unfalsifiable, and can each one link to the row
   that supports it?
