# REVIEW GUIDE — how to adjudicate the 69 packets

You asked to review the packets yourself. This guide is the whole process; nothing else needs to be read first.

**Time estimate:** 69 rows at 1–2 minutes each ≈ **1.5–2 hours**. Reviewing in priority order means the most decisive
cases come first, and you can stop at any point without losing work (the CSV saves continuously).

---

## 1. What you are deciding, and what you are not

For each packet you decide **one of five labels**:

| label | use it when |
|---|---|
| **`Confirmed Shift`** | the evidence shows a real, sustained change in the firm's technology positioning in that track, **and** you can cite a confirmation independent of the source that raised the packet |
| **`Routine Iteration`** | the activity is an ordinary product update within an existing direction |
| **`False Signal / No Confirmed Shift`** | the packet does not correspond to a real change (wrong firm, wrong track, taxonomy artefact) |
| **`Uncertain`** | the evidence conflicts or is insufficient to decide, but the case is real |
| **`Insufficient Observation`** | not enough time or coverage after the event to judge — **this is not a negative** and is censored, not scored |

You are **not** deciding whether the research succeeded, whether the detectors work, or whether public data is useful.
Only whether this packet describes a technology shift.

## 2. The independence rule (the one that matters most)

A `Confirmed Shift` requires confirmation from **a source family different from the one that raised the packet**:

- packet raised by a **regulatory clearance** → confirm with a trial, a publication, an 8-K disclosure, or a documented
  commercial launch — **not** with another clearance in the same track;
- packet raised by a **trial** → confirm with a clearance, a publication, or a commercial milestone;
- if no independent source exists, the label cannot be `Confirmed Shift` — use `Uncertain` or
  `Insufficient Observation`.

This rule exists because the programme already retracted a finding whose "confirmation" came from the same signal family
that produced the alert.

## 3. The worksheet

`HUMAN_REVIEW_WORKSHEET.csv` — one row per packet, opens in Excel. Columns 1–15 are **pre-filled evidence**; you fill the
last five:

| column | what to write |
|---|---|
| `human_label` | exactly one of the five labels (copy-paste them; aliases like "confirmed" are accepted but exact is safer) |
| `human_reason` | one sentence: what evidence decided it. Required — a label without a reason is not a record |
| `independent_confirmation` | **required for `Confirmed Shift`**: the record you used (PMID, trial id, 8-K accession, launch reference) |
| `reviewer` | your name (required on every row) |
| `reviewed_at` | date/time, e.g. `2026-11-04 10:30 +08:00` |

Pre-filled evidence columns include: firm, track, stratum, the event/trial date, the clearance or record, product code
and its mapped track, the Europe PMC third-source status and lead, a one-line evidence summary, and the agent's
preliminary rubric label **for contrast only — it is not a label**.

## 4. If you want more evidence than the row shows

The store is read-only and queryable; examples:

```powershell
# the trial behind a small-sample packet
python -c "import sqlite3,json; con=sqlite3.connect('file:data/research.sqlite?mode=ro',uri=True); print(json.loads(con.execute('select payload from events where event_id=?',('<ID>',)).fetchone()[0]))"

# the clearance record behind a candidate packet
python -c "import sqlite3,json; con=sqlite3.connect('file:data/research.sqlite?mode=ro',uri=True); print(con.execute('select event_date,title,url from events where event_id=?',('<ID>',)).fetchone())"
```

(`data/` is a junction to the frozen stores; nothing you run can modify them.)

## 5. Submitting

When **all 69 rows** are filled:

```bash
python experiments/b098/ingest_human_review.py --dry-run     # checks your file, writes nothing
python experiments/b098/ingest_human_review.py               # writes ADJUDICATION_HUMAN_V1.json
```

The ingester **refuses to write** if any row is missing a label, a reviewer, or a reason, if a `Confirmed Shift` lacks an
independent confirmation, or if packet ids are duplicated. It prints the exact problems with packet ids.

## 6. What happens to your labels

- They become the study's **Target B labels** (`ADJUDICATION_HUMAN_V1.json`, authority = human), replacing the agent's
  rubric as the record of truth.
- Label counts are summarised; the **agreement** between your labels and the agent's rubric is reported as a
  **descriptive diagnostic only** — it says nothing about correctness, and the rubric must not be tuned on it.
- Only then can any Target B analysis be written, and it will be reported with your name attached to each label.

## 7. Recommended order

1. **LT-07** (Philips respiratory) — the only packet with a *near-term* prior publication (76 days). If any packet can be
   `Confirmed Shift`, it is this one; check whether the paper is about the same device direction.
2. **LT-05, LT-08, LT-09** — third-source hits are decades old; decide whether they count (almost certainly not, but say
   why).
3. **Novel-entry candidates with a consistent product-code mapping** — evidence is internally consistent; the question is
   whether a single clearance plus a 12-month gap is a shift.
4. **Routine-stratum candidates** — these are controls; most should be `Routine Iteration`. If you find yourself labelling
   them `Confirmed Shift`, the definition is being stretched.
5. **Unassessable packets** — no product code or no mapping; `Insufficient Observation` or `Uncertain` with the reason
   stated.
