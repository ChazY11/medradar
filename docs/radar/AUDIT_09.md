# Audit 09 — rounds 80–89

Ninth scheduled audit. Audit 08's own question was "which page still answers with a hint where it could
answer with a result". The paper page was answering with a **false statement**.

## 1. Counts

```
product_code_class 5,181 · specialties 21 (20 with literature) · paper_meta 5,485
paper_field 2,336 papers linked to a field · corpus 40,731 files · failures 348,742
每领域篇数 min = max = 120
```

No divergence between the numbers the pages print and the tables they come from.

## 2. The defect: a title was answered with "this paper is not in the index"

```
/paper?id=Ectodermal Dysplasia
  → 索引里没有这篇论文：Ectodermal Dysplasia
    只收录已归档全文的论文…
```

The title is in the corpus, twice. The page only ever looked at identifiers (`paper_id`), so any reader who
arrived with a title - the common case, since titles travel and PMC numbers do not - was told something
false about our own data.

Two papers matched:

```
Clinical Outcomes of Dental Implant Therapy in Patients With Ectodermal Dysplasia: A Narrative Review · Cureus · 2026-11-23
Integrated Prosthodontic Approach for Ectodermal Dysplasia: … · Cureus · 2026-06-18
```

Fixed by searching titles when the identifier misses (6 ms over 5,485 titles), and presenting the matches as
**candidates, not an identity**:

> 按标题文字匹配，不是唯一识别——同名论文会有多个，改写或截断的标题匹配不到。点开确认是哪一篇。

The empty state also now carries the search box and says a title can be typed, so the next reader does not
have to discover this.

## 3. Checked and found sound

| Check | Result |
| --- | --- |
| Query parameters accepted but ignored | Every extra parameter (`limit`, `width`, `page`, `n`, unknown `sort`) is ignored **and** unadvertised — no page links to them, so nothing promises them |
| `areas?sort=<junk>` | Falls back to `devices` silently; acceptable, no claim attached |
| Theme against tables | No drift (see §1) |
| Field page recency vs list page recency | Same function, same units, 91% / 77% / 53% agree |
| Device dossier field-terms vs field page | Agreed this round after round 89's fix (hit counts vs coverage) |

## 4. The pattern worth naming

Two audits in a row found the same class of defect: **one number with two implementations**.

- Audit 08: 中文 query resolved in `/company` but not `/device`.
- This audit: topic chips showed hits on one page and coverage on another (found in round 89 by comparing,
  not by reading).

Both were invisible to the test suite because each implementation was correct on its own. The lesson is
recorded here rather than as a code rule: when a number appears twice, it will diverge, and the check that
catches it is **comparing two pages against each other**, not reading either one.

## 5. Timing

Serveur warm, after 60 s of warm-up:

```
/ 0.29 · /areas 0.30 · /area 0.30 · /sources 0.35 · /map 0.30 · /radar 0.29
/company 0.31 · /compare 0.30 · /device 0.45–0.60 · /topic 0.38 · /paper 0.61 (title miss)
```

Public: 0.69–1.19 s, tunnel overhead included.

## 6. Known and not fixed

- **English miss on `/device` costs 1.0 s** — the scan budget, by design.
- **`/compare` with a very large company is 1–2 s cold.**
- **Patent coverage** 92 applicants / 264 patents.
- **The public address rotates**, and single samples have been 5–9 s while the server answers in 0.3 s.
- **Warm-up competes with real requests** for ~90 s after a restart.
- **`paper_field` covers 2,336 of 5,485 indexed papers** — the rest matched no field query. Not a bug, but
  it means field pages speak for 43% of the corpus.

## 7. What the next audit should ask

1. Which claim on the site is now **the only copy** of a fact that used to be stated twice — and does it
   still agree with its table?
2. `/paper` accepts a title now; which other box still demands one exact kind of input that a reader may not
   have (a DUNS, a product code)?
3. The 2,336-of-5,485 field coverage: can the field pages say that number themselves?
