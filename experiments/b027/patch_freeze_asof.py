"""Patch freeze_snapshot.py to pass --as-of to the profile builder."""
from __future__ import annotations

from pathlib import Path

PATH = Path("experiments/b027/freeze_snapshot.py")

OLD = '''    result = subprocess.run([sys.executable, "experiments/b027/build_profiles.py",
                             "--scope", args.scope, "--out", str(work_dir)],
                            text=True)'''

NEW = '''    result = subprocess.run([sys.executable, "experiments/b027/build_profiles.py",
                             "--scope", args.scope, "--as-of", args.as_of,
                             "--out", str(work_dir)],
                            text=True)'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if OLD not in text:
        print("anchor missing")
        return 1
    PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8", newline="\n")
    print("freezer patched to pass --as-of")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
