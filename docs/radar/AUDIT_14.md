# Audit 14 — rounds 130–139

Fourteenth audit. This one ran the test audit 13 only proposed: **break a copy of the store and load every
page.**

## 1. The experiment

```
cp /srv/medradar/reference_slim.db /tmp/broken.db          (2.7 GB, 19 s)
ALTER TABLE specialty_stats RENAME COLUMN top_companies TO top_companies_moved
DELETE FROM code_leader
systemd-run --unit=uibroken ... MEDRADAR_REFERENCE_DB=/tmp/broken.db ... --port 8793
```

Then each page was loaded from both instances and compared by status and size:

| Page | healthy | broken | note |
| --- | --- | --- | --- |
| `/` | 200 · 12,904 B | 200 · 12,904 B | identical |
| `/areas` | 200 · 27,085 B | 200 · **6,477 B** | content gone, no error |
| `/area?name=Dental` | 200 · 42,962 B | 200 · **6,563 B** | content gone, no error |
| `/device?query=K213506` | 200 · 26,968 B | 200 · 25,866 B | peer block absent (table empty - correct) |
| `/company?q=Medtronic` | 200 · 21,045 B | 200 · 18,747 B | rank block absent (table empty - correct) |
| `/compare`, `/sources`, `/radar`, `/paper` | unchanged | | |

**No page returned 500.** Two pages lost most of their content and said nothing true about why.

## 2. What the pages said

```
/areas (broken)   没有数据，原因：技术领域分布表还没有生成（运行 tools/specialty_stats.py --refresh）
/area?name=Dental 技术领域用的是 FDA 的英文分类名。可以用 Orthopedic、Dental、Cardiovascular 这样的英文名…
```

Both sentences are false. The table exists. `Dental` **is** an FDA name. The first sends the reader to a tool
that would rebuild the table and hide the real cause; the second tells them to retype a correct word.

Round 132 built the instrument that knows the difference (`materialised.table_status`, shown on `/sources`, which
did report `specialty_stats ✗ no such column: top_companies`). **The instrument was right and the pages it
instruments still lied.**

## 3. The fix

`/areas` and `/area` now ask the table what state it is in before choosing a sentence:

```
table absent      -> specialty_stats_absent      还没有生成（运行 tools/specialty_stats.py --refresh）
table unreadable  -> specialty_stats_unreadable  表存在，但按页面的列读不出来——通常是表结构变了…
```

`/area` also stops guessing at the name: an unreadable table no longer produces the "retype it in English" hint.

Verified against the same broken copy after the fix: `/areas` prints `结构变了…`, `/area?name=Dental` prints the
same reason instead of the name hint, and the healthy instance is unchanged (27,085 B, no gap).

## 4. What this says about the other reads

The 53 broad `except Exception` in the page layer are mostly of this shape: *a read fails, the page prints a
plausible sentence about a different cause*. Two are now instrumented (`field_trend` in audit 13,
`specialty_stats` here), and `/sources` reports six materialised tables. The rest have not been enumerated, and
the broken-store run only proves what it touched: `/device` and `/company` degraded **correctly** (the leader
table was empty, so the block was absent - that is the honest state for "not built").

## 5. Counts and availability

```
devices/papers/trials/patents  consistent with store_stats
field_trend 20 · code_leader 2,225 · specialty_stats 21
public / 0.76 s · /areas 1.00 s · /sources 0.77 s · gate 401 · failed units 0 · tunnel restarts 1 (earlier today)
```

## 6. Known and not fixed

- **51 of the 53 broad excepts** are still un-instrumented. The broken-store run is repeatable and is the way to
  find them; it has only been run against two tables so far.
- **`/device` and `/company` when the leader table is empty** show nothing about it. That is arguably correct
  (the block is optional), but a reader cannot tell "not built" from "no peers".
- **One second per unknown company name**; **patent lane covers 92 applicants**; **`paper_field` covers 2,414 of
  5,560** papers; **nine of twenty fields cannot be ranked**; **the public address rotates**.

## 7. What the next audit should ask

1. Run the broken-store probe against **each remaining materialised table in turn** (`store_stats`,
   `paper_field`, `code_leader`) and record which pages change size without changing their sentence.
2. Which page prints a number derived from a table it **never checks the state of** at all?
3. Is there a place where the honest sentence exists in `gaps.py` but no branch ever reaches it?
