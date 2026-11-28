# Audit 08 — rounds 70–79

Eighth scheduled audit. Audit 07 found that "not found" was the slowest page on the site. This one found
that the tool **denied owning a company it holds 45,433 devices for**, and that a URL the route itself
accepts answered with a server error.

## 1. Counts: eleven materialised numbers, all matching

```
devices 5,258,159 · failures 348,742 · trials 2,967 · patents 264 · papers 5,485
codes 5,181 · failure_codes 838 · specialties 21 · corpus 40,731 · paper_indexed 5,485
```

Run before the audit proper, in the regression sweep of round 79: no differences.

## 2. The defect: a Chinese name was answered with "not found"

```
/device?query=美敦力    →  没有找到「美敦力」
                            试试：Medtronic
```

The product is Chinese-facing. The register holds English legal names. The alias table already mapped
美敦力 → Medtronic, the page already printed that mapping as a **hint**, and the answer was still "this
identifier is not in the device register" — for a company with 45,433 devices. The reader had to click
through to become a result.

Fixed by resolving the alias in the route when a Chinese query finds nothing, then rendering the devices
with the substitution stated:

```
「美敦力」按英文法定名称「Medtronic」查询（中文名对照只是方便输入，不是注册表内容）
INFINITY™ Occipitocervical Upper Thoracic System · MEDTRONIC SOFAMOR DANEK, INC. · 型号 G3650317
```

Measured after: 美敦力 0.46 s, 捷迈 0.39 s, 史赛克 0.44 s — all 200, all stating the substitution.

This is the same rule /compare already followed. The inconsistency, not the lookup, was the bug.

## 3. The second defect: a 500 on a URL the route accepts

```
/download?kind=area_failures&format=json&name=Dental   →  500
UnboundLocalError: cannot access local variable 'one'
```

Round 79 added the `area_failures` kind and wired only the CSV; the JSON branch called a function that is
not imported in that scope, and passed an empty list where a summary mapping was expected. Both mistakes
were invisible because nothing linked to that URL.

Fixed with its own exporter and its own schema, and the whole matrix is now swept:

```
7 kinds × 3 formats = 21 combinations, non-200: 0
```

The test asserts the matrix rather than the one case, because the failure mode was "a combination nobody
tried".

## 4. `resolve()`: which fallbacks actually fire

Audit 07 asked whether the five-step chain is longer than the data needs. Ran 18 real queries:

```
company_name 6 · version_or_model 3 · brand_name 2 · submission_number 1 · di 1 · no match 5
```

Every step fires except the numeric-DUNS branch, which the sample did not exercise. No step is dead, so the
chain stays. The one cost worth naming: an English miss costs 1.0 s — that is the scan budget doing exactly
what audit 07 installed it for, and a Chinese miss costs 10 ms because it never scans.

## 5. Timing, after

Server-side, warm:

```
/ 0.29 · /areas 0.30 · /area 0.30 · /sources 0.35 · /map 0.30 · /radar 0.29
/company 0.31 · /compare 0.30 · /device 0.45 · /topic 0.38 · /paper 0.40
```

Public through the tunnel: 0.63–1.02 s.

## 6. Checked and acceptable

| Check | Result |
| --- | --- |
| 21 export combinations | 0 × 5xx |
| Chinese input on four pages | device / company / area / compare all resolve and label it |
| Cold start | every page 0.28–0.34 s once the warm-up finishes |
| Public gate | 401 without credentials |
| Failed units | 0 |
| Corpus accounting | 5,485 indexed + 270 skipped = 5,755 files |

## 7. Known and not fixed

- **English miss costs 1.0 s.** The budget bounds it; it does not remove it.
- **`/compare` with a very large company is ~1–2 s cold** (Medline's own dossier is 0.7 s).
- **Patent coverage** 92 applicants / 264 patents; Google Patents is windowed.
- **Public address rotates**, and single samples have been 5–9 s while the server answers in 0.3 s.
- **The warm-up competes with real requests** for the first ~90 s after a restart.

## 8. What the next audit should ask

1. Which page still answers with a hint where it could answer with a result?
2. Is there any other URL shape the validators accept but no branch handles — the export matrix was checked,
   what about query parameters on the pages themselves?
3. Every page now states a bound somewhere; which of those statements is now **stale** because the data or
   the code changed under it?
