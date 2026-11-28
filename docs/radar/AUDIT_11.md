# Audit 11 — rounds 100–109

Eleventh audit. The defect came from probing edge inputs rather than reading code, and one of my own
measurements was wrong in a way worth recording.

## 1. Counts

```
devices 5,258,159 · failures 348,742 · trials 2,967 · patents 264
papers 5,560 · papers linked to a field 2,414 · field_trend rows 20
```

Every materialised count matches its table. The trend table built by the night lists 20 fields, all with a
term, all stamped `2026-11-28`.

## 2. The defect: extra names in a comparison were each paid for, then thrown away

```
/compare?q=A,B           1.89 s
/compare?q=A,B,C         3.15 s
/compare?q=A,B,C,D       4.29 s
/compare?q=A,B,C,D,E     6.57 s      <- five scans, four columns
```

Two costs, neither visible in the code:

* `_compare_names` probed the whole string as one company with `_company_data` before splitting it. That probe
  is right for `GLOBUS MEDICAL, INC.` and it costs about a second because a miss runs a name scan. It nearly
  always misses here - the string is a list.
* The cap `[:4]` lived only in the comma branch, and was applied after every name had been resolved.

Fixed: the probe is one indexed `COLLATE NOCASE` read on `udi_company`, and the cap applies to all branches
before anything is resolved.

```
after: A,B,C,D 4.96 s · A,B,C,D,E 4.34 s · A,B,C,D,E,F 4.18 s
       GLOBUS MEDICAL, INC. still resolves as one company (1 家公司并列)
```

Four unknown names still cost about a second each; that is the scan's price, and the page is honest about it
rather than hiding it behind a spinner.

## 3. My own measurement was wrong

I read `/areas` against the field page and found "ivus 5.27×" beside "ivus 35×", and started treating it as a
second implementation of one number - the defect class this audit series keeps finding. It was my regex: it
captured across `2/35`. The three code paths (direct, cached, materialised) all return 5.27, and the rendered
page does too.

Fourth time a loose regex has produced a false alarm in this project. The rule that would have prevented all
four: **extract rows by structure, then compare fields**, never by a single pattern spanning the row.

## 4. Edge inputs (13 probes)

| Input | Result |
| --- | --- |
| `/topic?id=does_not_exist` · `/topic?id=` | 200 (states the miss) |
| `/paper?id=` · `/paper?id=zzzz` | 200 |
| `/device?query=` · `/device?query=%20%20` | 200 |
| `/company?q=` · `/compare?q=` · `/area?name=` | 200 |
| `/areas?sort=bogus` | 200, falls back to the default order |
| `/download?kind=area&name=Nope&format=json` | 200 with an empty area payload |
| `/download?kind=sources&format=json` | 422 — unknown kind rejected by validation |

No 500s. The 422 is a schema rejection, not a crash; a reader only reaches it by editing the URL.

## 5. Audit 10's three questions

**"Which branch cannot be reached because an earlier return covers it?"** The unknown-field page from audit 10
is now reached (probed: `dentistry` and `Dental Implants` render it). No new unreachable branch found by
probing; this is evidence about the inputs I tried, not a proof about the file.

**"Which `except Exception` hides a bug?"** 53 in `pages.py`. The one that hid audit 10's `NameError` is gone
because the variables are declared before the branch. This pass found no new hiding, and that is a weak claim:
it means the paths I exercised did not need an exception to survive.

**"Which timing item does a reader feel most?"** The 1 s per unknown name, because it multiplies. It is now
bounded (four names maximum, no probe scan) instead of growing with whatever was pasted.

## 6. Timing

```
server warm  / 0.62 · /areas 0.58 · /sources 0.64 · /area 0.59 · /map 0.61
public       / 1.32 · /areas 1.42 · /sources 1.50 · /area 1.32   (measured in round 109)
```

The warm set sits at 0.52–0.64 s, unchanged by the /areas column added in round 109.

## 7. Known and not fixed

- **One second per unknown company name** in `/compare` and `/company`. Bounded now, not eliminated.
- **`/device` English miss** 1.0 s, plus the suggestion table when the scan is truncated.
- **Patent coverage** 92 applicants / 264 patents.
- **`paper_field` covers 2,414 of 5,560** papers (43%).
- **The public address rotates**; a reconnect costs a few seconds of 502.
- **53 broad `except Exception` in the page layer** — unchanged, and the honest reading is that I have not
  proven they are all safe.

## 8. What the next audit should ask

1. Which numbers are still computed **twice** on purpose - the trend table vs the field page are two call
   sites of one function, which is the shape that survives; which pairs are genuinely two implementations?
2. Of the 53 broad excepts, how many sit around a **computation** rather than a source read? Those are the ones
   that can hide a bug.
3. Does any page still answer a question the reader did not ask? The edge probes say no dead ends; the question
   left is whether the *right* page answers it.
