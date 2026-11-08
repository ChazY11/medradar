"""Remove sample payloads for sources whose licence forbids redistribution.

Two problems, one fix:

1. Compliance: the licence audit rule is "redistribution_allowed == NO ->
   commit nothing".  Several sample directories for career-site / ATS sources
   (NO or UNKNOWN) had raw HTML committed anyway.
2. GitHub secret scanning rejected the push because scraped career-site HTML
   contains token-like strings.  Removing the payloads removes the finding;
   granting an exception would be the wrong direction.

What is kept: a manifest with the file name, full-response sha256, byte count,
request URL and a withheld note.  A reviewer can re-fetch the same URL and verify
the hash themselves, without this repository redistributing the content.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path("research/data_expansion")
REGISTER = json.loads((ROOT / "GLOBAL_DATA_SOURCE_REGISTER.json").read_text(encoding="utf-8"))
BLOCKING = {"NO", "UNKNOWN"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    status = {r["source_id"]: r.get("redistribution_allowed") for r in REGISTER["sources"]}
    removed = 0
    for directory in sorted(p for p in (ROOT / "samples").iterdir() if p.is_dir()):
        source_id = directory.name
        if status.get(source_id) not in BLOCKING:
            continue
        payloads = [p for p in directory.rglob("*") if p.is_file() and p.name != "SAMPLES.json"]
        payloads = [p for p in payloads if p.suffix not in {".py"}]
        if not payloads:
            continue
        withheld = []
        for path in payloads:
            entry = {
                "file": path.relative_to(directory).as_posix(),
                "sha256_full": sha256(path),
                "bytes": path.stat().st_size,
                "content_withheld": True,
                "reason": f"redistribution_allowed = {status.get(source_id)} for {source_id}",
            }
            withheld.append(entry)
            path.unlink()
            removed += 1
        manifest = {
            "source_id": source_id,
            "redistribution_allowed": status.get(source_id),
            "policy": "payload withheld: the source licence does not permit redistribution",
            "how_to_verify": "re-fetch the request URL recorded in probes/<source_id>/requests.jsonl and compare sha256",
            "withheld_samples": withheld,
        }
        (directory / "SAMPLES.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"{source_id:<24} withheld {len(withheld)} file(s) (redistribution={status.get(source_id)})")
    print(f"total withheld: {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
