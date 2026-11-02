"""Patch build_profiles.py so all outputs honour --out."""
from __future__ import annotations

from pathlib import Path

PATH = Path("experiments/b027/build_profiles.py")


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    replacements = [
        ('(OUT_DIR / "profiles" / f"{company_key}.md")',
         '(out_dir / "profiles" / f"{company_key}.md")'),
        ('write_json(OUT_DIR / "profiles.json", payload)',
         'write_json(out_dir / "profiles.json", payload)'),
        ("print(f\"wrote {OUT_DIR / 'profiles.json'} and {len(payload['profiles'])} markdown profiles\")",
         "print(f\"wrote {out_dir / 'profiles.json'} and {len(payload['profiles'])} markdown profiles\")"),
    ]
    for old, new in replacements:
        if old not in text:
            print(f"anchor missing: {old[:60]}")
            return 1
        text = text.replace(old, new)
    PATH.write_text(text, encoding="utf-8", newline="\n")
    print("patched build_profiles.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
