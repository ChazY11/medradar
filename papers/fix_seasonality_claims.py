"""Repair the seasonality claim lines in build_claims.py so the module parses, and align values with the paper."""
from __future__ import annotations

from pathlib import Path

BUILD = Path("papers/build_claims.py")
REPLACEMENTS = {
    '    ("CC1", "January month factor", "0.891", "experiments/b074/seasonality.json", ""0": 0.891"),':
        "    ('CC1', 'January month factor', '0.891', 'experiments/b074/seasonality.json', '0.8907'),",
    '    ("CC2", "annual month-factor spread", "1.255", '
    '"experiments/b074/seasonality.json", ""spread_max_over_min": 1.255"),':
        "    ('CC2', 'annual month-factor spread', '1.255', "
        "'experiments/b074/seasonality.json', '1.2551020408163265'),",
    '    ("CC3", "month-of-year permutation p-value", "0.0005", '
    '"experiments/b074/seasonality.json", ""p_value": 0.0005"),':
        "    ('CC3', 'month-of-year permutation p-value', '0.0005', "
        "'experiments/b074/seasonality.json', '0.0004997501249375312'),",
    '    ("CC4", "quarter-boundary factor", "1.058", '
    '"experiments/b074/seasonality.json", ""quarter_start_vs_interior": 1.058"),':
        "    ('CC4', 'quarter-boundary factor', '1.058', "
        "'experiments/b074/seasonality.json', '1.0579'),",
    '    ("CC5", "detector alert rate on raw counts", "0.0090", '
    '"experiments/b074/seasonality.json", ""alert_rate": 0.009017223910840932"),':
        "    ('CC5', 'detector alert rate on raw counts', '0.0090', "
        "'experiments/b074/seasonality.json', '0.009017223910840932'),",
    '    ("CC6", "cell-months changed by seasonal adjustment", "9 of 39,151", '
    '"research/DECISIONS.md", "9 of 39,151"),':
        "    ('CC6', 'cell-months changed by seasonal adjustment', '9 of 39,151', "
        "'research/DECISIONS.md', '9 of 39,151'),",
}


def main() -> int:
    text = BUILD.read_text(encoding="utf-8")
    replaced = 0
    for old, new in REPLACEMENTS.items():
        if old in text:
            text = text.replace(old, new, 1)
            replaced += 1
    BUILD.write_text(text, encoding="utf-8", newline="\n")
    print(f"repaired {replaced} of {len(REPLACEMENTS)} claim lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
