# Audit 10 — rounds 90–99

Tenth audit. Audit 09 asked three questions; two of them were answered by the very first probe.

## 1. Counts

```
devices 5,258,159 · failures 348,742 · trials 2,967 · patents 264
papers 5,560 (paper_files 5,833) · codes 5,181 · failure_codes 838 · specialties 21
papers linked to a field 2,414
```

Materialised counts compared against their tables: no differences.

The field-linked count moved from 2,336 to 2,414 during rounds 97–99 — the observation chain now carries
papers into fields unattended, which was audit 09's third question.

## 2. The defect: any field name that was not exactly right returned 500

```
/area?name=dental            500
/area?name=dentistry         500
/area?name=Dental Implants   500
/area?name=牙科               200   (resolved through the alias table)
```

Two separate faults on a page every field page links to:

* `field_recency` and `literature_coverage` were declared **inside** the branch that computes them, so the
  path for an unresolved name referenced an undefined local → `NameError` → 500. That is the third
  audit in a row where the defect was a variable's scope, not its logic.
* Even without the crash, `dental` would have been treated as a name we do not hold, one keystroke from
  `Dental`.

Fixed: both variables are declared with the others; a case-insensitive lookup runs before the failure path;
and the page that explains an unknown name (already written, never reached) now renders:

```
技术领域用的是 FDA 的英文分类名。可以用 Orthopedic、Dental、Cardiovascular 这样的英文名，
或从 技术领域总表 里点进去。
```

After: `dental` 200 · `DENTAL` 200 · `dentistry` 200 (hint) · `Dental Implants` 200 (hint) · `牙科` 200.

## 3. Audit 09's other two questions

**"Which fact is now the only copy, and does it still agree?"** — The paper count has one source
(`store_stats`, refreshed nightly and by `--refresh`). It disagreed with the corpus until the refresh ran;
the page's own timestamp is what exposed it, which is the mechanism working as designed.

**"Which input box still demands something the reader may not have?"** — `/area` did; that became §2. The
remaining one is `/topic?id=`, which needs an internal topic id. It is reachable only from `/map`, which
always supplies one, so it is not a dead end a reader can walk into.

## 4. Timing

Server warm, 60 s after restart:

```
/ 0.68 · /areas 0.67 · /area 0.83 · /sources 0.82 · /map 0.84 · /radar 0.68
/company 0.62 · /compare 0.63 · /device 0.89 · /paper 0.64 · /topic 0.73
```

Public through the tunnel: 0.98–1.31 s.

Note: the whole warm set is 0.6–0.9 s here rather than the 0.28–0.45 s measured in audit 08. The box is the
same; the difference is that these were taken while the nightly rehearsal's leftovers and the scheduler were
running. Recorded as measured, not corrected for.

## 5. Checked and sound

| Check | Result |
| --- | --- |
| 11 materialised counts | match their tables |
| Every page in the warm set | 200 |
| Public gate | 401 without credentials |
| Failed units | 0 |
| Field-linked papers | 2,414 (was 2,336) |

## 6. Known and not fixed

- **`/device` English miss costs 1.0 s** (the scan budget).
- **`/compare` with a very large company is 1–2 s cold.**
- **Patent coverage** 92 applicants / 264 patents.
- **The public address rotates**; a reconnect costs a few seconds of 502 (`TUNNEL_AVAILABILITY.md`).
- **`paper_field` covers 2,414 of 5,560 papers** (43%) — the same proportion as before, because the corpus
  grew too. The field pages say so themselves.
- **A five-minute watcher plus a nightly that both write** means a slow night can overlap the next cycle;
  the lock covers the nightly, not the watcher.

## 7. What the next audit should ask

1. Which page has a branch that **cannot be reached** because an earlier `return` covers it? (The unknown-
   field page was written long before this audit and never executed.)
2. Every `except Exception` in the page layer: which ones are hiding a bug rather than a missing source? The
   NameError here was invisible because the surrounding code catches broadly.
3. Of the four "not fixed" timing items, which is now the one a reader actually feels most often?
