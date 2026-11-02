"""Quantify how each event's track_id was assigned: explicit code map vs text keyword.

If a product code has no explicit taxonomy entry, the track comes from matching the
device text, so the SAME code can land in different tracks over time. That is a
first-class false-change channel for the OBSERVE layer.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.config import TrackRegistry, load_config  # noqa: E402

DB = Path("data/research.sqlite")


def main() -> int:
    # config/product_code_tracks.json is a flat {product_code: track_id} map, which is
    # exactly what the bulk lane passes to ``_event_track`` as ``code_map``.
    explicit = json.loads(Path("config/product_code_tracks.json").read_text(encoding="utf-8"))
    if not isinstance(explicit, dict):
        raise SystemExit("unexpected product-code map shape")
    tracks = load_config("tracks_device").get("tracks", [])
    print(f"taxonomy: {len(tracks)} tracks, explicit code map: {len(explicit)} product codes")

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select product_code, track_id, title, summary, count(*) n from events "
        "where kind in ('510k','pma') and track_id is not null and track_id<>'' "
        "group by product_code, track_id, title, summary").fetchall()
    con.close()

    by_code: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_code[str(row["product_code"] or "")][row["track_id"]] += row["n"]

    explicit_events = 0
    keyword_events = 0
    multi_track_codes = []
    for code, counter in by_code.items():
        total = sum(counter.values())
        if code in explicit:
            explicit_events += total
            mapped = explicit[code]
            wrong = total - counter.get(mapped, 0)
            if wrong:
                multi_track_codes.append((code, "explicit", mapped, dict(counter)))
        else:
            keyword_events += total
            if len(counter) > 1:
                multi_track_codes.append((code, "keyword", None, dict(counter)))

    total_events = explicit_events + keyword_events
    print(f"\n== assignment provenance (events) ==")
    print(f"  explicit product-code map : {explicit_events} ({explicit_events/total_events:.1%})")
    print(f"  text-keyword fallback     : {keyword_events} ({keyword_events/total_events:.1%})")
    print(f"\n== codes landing in >1 track: {len(multi_track_codes)} ==")
    for code, how, mapped, counter in sorted(multi_track_codes, key=lambda r: -sum(r[3].values()))[:15]:
        print(f"  {code:6s} via {how:8s} mapped_to={mapped} observed={counter}")
    payload = {
        "events_explicit_code_map": explicit_events,
        "events_text_keyword_fallback": keyword_events,
        "events_total": total_events,
        "fraction_keyword": keyword_events / total_events if total_events else None,
        "codes_multi_track": len(multi_track_codes),
        "multi_track_examples": [
            {"code": code, "how": how, "explicit_mapping": mapped, "observed": counter}
            for code, how, mapped, counter in multi_track_codes[:30]],
    }
    Path("experiments/detect_v1/track_assignment_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nwrote experiments/detect_v1/track_assignment_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
