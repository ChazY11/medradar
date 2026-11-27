# Audit 04 — rounds 30–39

Fourth scheduled audit. Audits 01–03 fixed a flaky suite, a ten-second page and a cold-start gap. This
one answered the two questions audit 03 left for it, then found the defect that no amount of
measurement inside the product could have shown: **the first thing a Chinese-speaking reader types
does not work, and the page blames them for it.**

## 1. The two questions audit 03 asked

**Is the warm-up bounded?** Measured by running `warmup()` against the live store with nothing else
touching it: **5.4 s**, once, in a daemon thread. It covers five identifier shapes, one dossier, the
paper index, the landing counts and — added in round 30 — one paper's terms, a company, the specialty
map and the coverage assembly. Bounded, and it fails soft: every step is wrapped, so a deployment
missing one table still serves the rest.

**Is any number printed that was never compared against the table it describes?** Checked all thirteen
materialised counts against live SQL, in one pass:

```
devices 5,258,159 · failures 348,742 · trials 2,967 · patents 264 · papers 3,366 · codes 5,181
failure_codes 838 · failure_models 47,553 · failure_brands 40,707 · trial_sponsors 808
patent_assignees 92 · specialties 21 · corpus 40,731
```

All thirteen match. (`trial_sponsors` first reported a mismatch; the audit script had used a column
name that does not exist. The product was right and the audit was wrong — worth writing down because
the same thing happened twice this month.)

## 2. The defect: the most likely first action is a dead end

A Chinese medical-device engineer's first move is to type the Chinese name of a manufacturer they know.
Measured in the browser, before this round:

```
/company?q=美敦力
  没有找到「美敦力」
  在设备注册表里按公司名匹配（先精确、后包含）。
  没有数据，原因：设备注册表里没有匹配到这家公司  company_not_in_register
```

The register stores the English legal names filed with the FDA, so a Chinese name cannot match. But the
page reported it as **"this identifier is not in the register"** — which reads as "this product has
never heard of Medtronic". The reader is told their input was wrong when the cause is that our data
speaks a different language than they do.

Every other audit found something measurable. This one was only visible by *being the reader*: type
what they would type, on the page they would land on.

**Fix.** A query containing CJK now explains the actual constraint and offers a way through:

```
「美敦力」在注册表里是英文法定名称。
FDA 登记的是厂商申报的英文名，中文名不会命中。试试：Medtronic
（中文名对照只是方便输入，不是注册表内容）
```

* A 25-entry alias table (`medradar/radar/aliases.py`) maps common Chinese names to the English name to
  search. It is labelled in the page as convenience, not register data.
* A Chinese name that is *not* in the table gets the honest advice and a link to `/areas`, with no
  invented translation.
* An English query that fails keeps its ordinary reason — the hint fires only when the query contains
  CJK, so a typo in English is still reported as a missing identifier.

## 3. Checked and found acceptable

| Check | Result |
| --- | --- |
| Dead links | 102 unique internal links across five pages, all 200 |
| Narrow viewport (390 px) | no page-level horizontal overflow; wide tables scroll inside their card |
| Empty / whitespace / unknown query | 200 with a stated reason; no stack traces |
| Chinese input on `/device`, `/company`, `/compare`, `/area` | no crash; now explained |
| Nightly job's new steps | the rotation snippet runs and picks Orthopedic + Cardiovascular |
| Source health and graph staleness on `/sources` | present, with last success and failure reason |

## 4. Known and not fixed

- **The public URL rotates.** localhost.run free tier; measured overhead ~0.5 s typically, but single
  samples of 7–9 s occur when the tunnel congests. A stable address needs an operator decision (open
  443 or buy a domain).
- **Patent coverage 92 applicants / 264 patents.** Google Patents is windowed, not blocked: one window
  gave 2 of 3 companies, then four rounds gave 0 of 12. Three attempts a night with early abort.
- **`/company?q=Medline` ~1.1 s cold** — 252,243 devices to count brands and failures over.
- **Labels are English.** A Chinese reader searching 牙科 for "Dental" also finds nothing; the alias
  table covers companies only.

## 5. What the next audit should ask

1. Are the twelve specialty queries the right ones? The rotation picks by yield, but nothing checks
   whether a field's papers are *about devices* rather than adjacent clinical practice.
2. The alias table is hand-written. Does it age? A company renamed by the FDA (Synthes → DePuy Synthes)
   leaves a mapping that still works but may point at a stale English name.
