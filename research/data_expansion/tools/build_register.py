#!/usr/bin/env python
"""Build GLOBAL_DATA_SOURCE_REGISTER.json from documentation + probe evidence.

Usage
-----
    python research/data_expansion/tools/build_register.py            # write the register
    python research/data_expansion/tools/build_register.py --check     # validate only, non-zero on problems

The tool never invents a field.  A source that has not been probed keeps
``connection_status = NOT_TESTED``; a source whose documentation claims an API
but whose probe returned 401 is reported with both facts visible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import registry  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="research/data_expansion root")
    parser.add_argument(
        "--out",
        default=str(ROOT / "GLOBAL_DATA_SOURCE_REGISTER.json"),
        help="output path for the merged register",
    )
    parser.add_argument("--check", action="store_true", help="validate only; non-zero exit on problems")
    args = parser.parse_args(argv)

    register = registry.build_register(Path(args.root))
    if args.check:
        problems = register["validation_problems"]
        for problem in problems:
            print(f"PROBLEM: {problem}", file=sys.stderr)
        print(json.dumps(register["counts"], indent=2, sort_keys=True))
        return 1 if problems else 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(register, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {out} with {register['counts']['sources']} sources")
    print(json.dumps(register["counts"], indent=2, sort_keys=True))
    if register["validation_problems"]:
        print(f"{len(register['validation_problems'])} validation problems:", file=sys.stderr)
        for problem in register["validation_problems"][:20]:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
