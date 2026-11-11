"""Fetch one GUDID release ZIP and inspect its internal structure + columns.

Run:  python CONNECTORS/regulatory/_inspect_gudid.py
"""

from __future__ import annotations

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from CONNECTORS.regulatory._util import ROOT, make_client, save_raw, utc_now, write_provenance  # noqa: E402

URL = "https://accessgudid.nlm.nih.gov/release_files/download/gudid_monthly_update_october_2026.zip"
NAME = "gudid_monthly_update_october_2026.zip"


def main() -> int:
    with make_client("regulatory-gudid-fetch", max_requests=2,
                     max_bytes_per_response=12_000_000, max_total_bytes=12_000_000,
                     rps=1.0) as c:
        res = c.get(URL)
        rec = save_raw("accessgudid", NAME, res, url_note="GUDID monthly release ZIP, Oct 2026")
        budget = c.budget_report()
    write_provenance("accessgudid", [rec], extra={
        "generated_at": utc_now(),
        "budget": budget,
        "note": "Verbatim GUDID release archive. Unzipped only for parsing; the archive "
                "as saved is the exact byte stream the server returned.",
    })
    print("saved", rec["path"], rec["bytes"], rec["sha256"][:16])

    zf = zipfile.ZipFile(io.BytesIO(res.body))
    print("members:")
    for info in zf.infolist():
        print(f"  {info.filename}  {info.file_size} bytes")
    for info in zf.infolist():
        if info.filename.lower().endswith((".txt", ".csv")):
            raw = zf.read(info.filename).decode("utf-8", errors="replace")
            lines = raw.splitlines()
            print(f"\n=== {info.filename}: {len(lines)} lines ===")
            hdr = lines[0].split("|")
            print("n_columns:", len(hdr))
            for i, h in enumerate(hdr):
                print(f"  [{i}] {h}")
            print("\nrow 1 preview:")
            vals = lines[1].split("|")
            for h, v in zip(hdr, vals):
                print(f"  {h} = {v[:110]!r}")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
