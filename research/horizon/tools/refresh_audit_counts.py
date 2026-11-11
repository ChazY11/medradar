"""Derive the clock-class table in DATA_QUALITY_AUDIT.md from the export itself.

The audit must not contain hand-typed counts. This script recomputes the numbers
and rewrites the relevant blocks in place.
"""

from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from hz.timeq import classify_record  # noqa: E402

EXPORT = os.path.join(ROOT, "exports", "horizon-2026-11-10")
DOC = os.path.join(ROOT, "DATA_QUALITY_AUDIT.md")


def load() -> list[dict]:
    rows = []
    for p in sorted(glob.glob(os.path.join(EXPORT, "*.jsonl"))):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def main() -> int:
    rows = load()
    cls = collections.Counter(
        classify_record(r.get("event_at"), r.get("source_public_at"))["class"] for r in rows
    )
    flags = collections.Counter(f for r in rows for f in (r.get("quality_flags") or []))
    snap = flags.get("SNAPSHOT_ONLY", 0)
    ev_only = cls.get("EVENT_ONLY", 0)
    pbe = cls.get("PUBLICATION_BEFORE_EVENT", 0)
    full = cls.get("FULL_TWO_CLOCK", 0)
    pub_only = cls.get("PUBLICATION_ONLY", 0)

    pbe_src = collections.Counter(
        r["source_id"]
        for r in rows
        if classify_record(r.get("event_at"), r.get("source_public_at"))["class"]
        == "PUBLICATION_BEFORE_EVENT"
    )

    s = open(DOC, encoding="utf-8").read()

    old_block_start = s.find("| class | meaning | sources where it dominates |")
    old_block_end = s.find("### 3.2 Date confusion cases actually encountered")
    assert old_block_start != -1 and old_block_end != -1, "anchor not found"

    new_block = f"""| class | meaning | count in this export |
|---|---|---|
| `FULL_TWO_CLOCK` | a recorded public date and a recorded event date, correctly ordered | **{full}** |
| `PUBLICATION_ONLY` | public date known, event date unknown (e.g. GUDID) | **{pub_only}** |
| `EVENT_ONLY` | event date known, **no recorded public date** | **{ev_only}** |
| `PUBLICATION_BEFORE_EVENT` | became public *before* the event it describes | **{pbe}** |

`EVENT_ONLY` is the dangerous class. It means "we know when the thing happened but
not when anyone could have seen it". **Any record in this class is ineligible for
historical-observability claims** and `hz.timeq.audit_clocks` refuses it.
**{ev_only} of {len(rows)} exported records** are in that state — most of the trade
and regulatory corpus. That is a property of the sources, not a defect in the
collection, and it is the honest reason trade data cannot support early-signal
research.

`PUBLICATION_BEFORE_EVENT` is a genuinely interesting fourth state and it is **not**
a data error: a trial is registered *before* it starts, and a DOI is registered
*before* the issue date. {pbe} records are in this state
({dict(pbe_src)}). They are excluded from observability claims — the event had not
happened when the record appeared — but they are reported separately rather than
silently bracketed with data errors, because the pattern is itself the finding
(registration-first workflows, e-pub-ahead-of-print).

"""
    s = s[:old_block_start] + new_block + s[old_block_end:]

    # refresh the snapshot-only sentence
    s = re.sub(
        r"`SNAPSHOT_ONLY` records can support .*?`\n\n---",
        f"`SNAPSHOT_ONLY` records can support \"what is true now\" but not \"what was knowable\n"
        f"then\". **{snap} records** in the export carry that flag.\n\n---",
        s,
        flags=re.S,
    )

    s = re.sub(
        r"\d[\d ]*records in the export are in that state",
        f"{ev_only} records in the export are in that state",
        s,
    )
    s = re.sub(
        r"\d[\d ]*records in the export carry that flag",
        f"{snap} records in the export carry that flag",
        s,
    )
    s = re.sub(
        r"\*\*\d[\d ]*records are `EVENT_ONLY`\*\*",
        f"**{ev_only} records are `EVENT_ONLY`**",
        s,
    )
    s = s.replace("2 687", str(ev_only)).replace("2 383", str(snap))
    open(DOC, "w", encoding="utf-8", newline="\n").write(s)

    print(json.dumps({"records": len(rows), "classes": dict(cls), "snapshot_only": snap}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
