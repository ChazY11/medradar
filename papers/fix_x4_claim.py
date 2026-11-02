"""Fix claim X4 wording (words vs digits) and keep the paper in sync."""
from __future__ import annotations

import json
from pathlib import Path

BUILD = Path("papers/build_claims.py")
CLAIMS = Path("papers/CLAIMS.json")
PAPER = Path("papers/PAPER_v1.md")

OLD_LINE = '    ("X4", "eligible hiring series in the second domain", "8", "research/DECISIONS.md", "8 of 13"),'
NEW_LINE = ('    ("X4", "eligible hiring series in the second domain", "eight of thirteen", '
            '"research/DECISIONS.md", "Eight of thirteen"),')


def main() -> int:
    build = BUILD.read_text(encoding="utf-8")
    if OLD_LINE not in build:
        print("build_claims.py anchor missing")
        return 1
    BUILD.write_text(build.replace(OLD_LINE, NEW_LINE, 1), encoding="utf-8", newline="\n")

    payload = json.loads(CLAIMS.read_text(encoding="utf-8"))
    for claim in payload["claims"]:
        if claim["id"] == "X4":
            claim["value"] = "eight of thirteen"
            claim["source_needle"] = "Eight of thirteen"
    CLAIMS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")

    paper = PAPER.read_text(encoding="utf-8")
    old_phrase = "the hiring lane's 8\nseries)"
    new_phrase = "(eight of thirteen eligible hiring series)"
    if old_phrase in paper:
        PAPER.write_text(paper.replace(old_phrase, new_phrase, 1), encoding="utf-8", newline="\n")
        print("paper updated")
    else:
        print("paper phrase not found; leaving as is")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
