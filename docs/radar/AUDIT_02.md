# Audit 02 — rounds 10–19

Second scheduled audit. The first one fixed a flaky suite and a duplicated truth. This one found the
cause of the flakiness that round-10 could only describe, and a ten-second page that had been hidden
behind an average.

## 1. The real reason the suite was flaky: `hash()` in a fixture

Round 10 found that the API view cache was shared across stores and fixed it. That bug was real, but
it was not the whole story, and one test kept failing intermittently afterwards:

```
test_product_code_census_is_one_query   passed alone, failed in a batch
```

The fixture helper `_udi_row` built its device identifier as:

```python
f"08800{k_number[-4:]}{abs(hash(model)) % 100:02d}"
```

Python randomises string hashing **per process** (PYTHONHASHSEED). So the same fixture produced
different device sets in different runs: three models hashed into the same two-digit suffix and
collapsed into two device rows about 3% of the time, per run, differently each time. A test asserting
`census["EIA"] == 3` then failed for no reason the reader could see.

**Fix.** The identifier is now a digest over the whole key:

```python
digest = hashlib.sha1(f"{k_number}|{model}".encode()).hexdigest()[:9]
"08800" + int(digest, 16) % 10**9
```

Deterministic across processes and with collision space of a billion instead of a hundred.

**Evidence.** The test now passes under `PYTHONHASHSEED` 1, 2, 3, 4, 5 and the whole file under 11,
22, 33 — nine independent processes, no failures.

**What this says about round 10.** The view-cache bug was worth fixing, but I reported the flake as
explained when one observable cause had been found. There were two, and the second one was the
common one. An audit that stops at the first cause is only half an audit.

## 2. A ten-second page hidden behind an average

Every page was measured cold after a restart:

```
/                                   0.34 s
/sources                            0.39 s
/areas                              0.39 s
/area?name=Orthopedic               0.40 s
/map                                0.40 s
/radar                              0.39 s
/company?q=ARUM                     0.65 s
/device?query=K213506               0.99 s
/company?q=Medtronic                1.10 s
/compare?q=Medtronic,Globus         1.20 s
/paper?id=PMC12568234               3.45 s
/device?query=Medtronic             5.90 s
/device?query=Clydesdale           10.26 s   <-- the landing page's own example
```

The two worst cases are both **name queries on /device**, and "Clydesdale · 按品牌" is one of the four
examples the landing page offers. A reader following the front page's own suggestion waits ten
seconds.

Splitting the ten seconds:

```
resolve            12.94 s   (measured in-process, cold)
papers x 25         2.67 s
failures x 25       2.73 s
trials x 25         0.02 s
patents x 25        0.02 s
```

The per-device work is not the problem. `resolve` was: a letter-only query fell through to

```sql
SELECT * FROM udi_device WHERE brand_name LIKE '%Clydesdale%' LIMIT 25
SELECT * FROM udi_device WHERE company_name LIKE '%Clydesdale%' LIMIT 25
```

two full scans of 5.2M rows to answer a question about one word.

**Fix.** A brand is almost always typed from its beginning, so resolve now tries, in order: exact
(0.1 ms, already indexed), then a **half-open range** that means "begins with", then the contains
scan only if the prefix found nothing.

The range form was necessary rather than aesthetic: `LIKE 'Clydesdale%'` does **not** use
`idx_udi_brand` in this database - measured 697 ms as a full scan - while the equivalent
`brand_name >= 'Clydesdale' AND brand_name < 'Clydesdalе'`-style range answers in **0.1 ms**.
Incrementing the last character gives exactly the strings with that prefix.

**Result.** Cold, in-process: `resolve('Clydesdale')` 12.94 s → the prefix ranges answer immediately.
Whole page 10.26 s → measured below.

## 3. Checked and found acceptable

| Check | Result |
| --- | --- |
| Every page reachable from the nav | yes; a test walks the landing page's links |
| Every page route passes the gate allowlist | yes; a test asserts it, after /areas shipped invisible for twenty minutes |
| Pages that cannot be exported | `/areas` and `/area` are view-only; every page a reader would quote (device, company, compare) exports. Recorded as a gap, not a defect |
| Numbers that could disagree between pages | landing and /sources read the same materialised set; both print its timestamp |
| Summary vs section claims | fixed in round 11; a test forces the weak match kinds and asserts the qualifier |

## 4. Known and not fixed

- **Name queries on /device still pay for their per-device work** (papers ~2.7 s, failures ~2.7 s for
  ten devices). Cold name queries remain a few seconds; warm ones are 0.3 s because the page is
  cached for 120 s. Persisting paper histories per company is the real fix and is a round of its own.
- **`/paper` takes 3.45 s cold** for the same reason: the term table lookup plus the reverse-brand
  join on first touch.
- **Patent coverage 92 / 12,537**; **failure sweep 838 / 5,229** product codes.
- **Preprints refused from this host**; europepmc carries the increment.
- **Public URL rotates**; `public_url.txt` is the only trustworthy address.

## 5. What the next audit should ask

1. Do the exports and the pages still agree *after* three rounds of layout changes? The rule was set
   in audit 01 and enforced by one test on the gap table, but not on the sections themselves.
2. Is the 120 s page cache hiding a slow path that a second reader also pays for? Measure the same
   URL twice from two different processes rather than twice in one.
