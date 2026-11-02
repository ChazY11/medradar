"""Print the momentum test numbers for every generated profile (for the report)."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    payload = json.loads(Path("experiments/b027/profiles.json").read_text(encoding="utf-8"))
    print(f"{'company':16s} {'recent':>6s} {'prior':>6s} {'ratio':>6s} {'p':>7s} "
          f"{'mde':>6s} {'detected':>9s}  direction")
    for key, profile in payload["profiles"].items():
        momentum = profile["momentum"]
        ratio = momentum["ratio"]
        p_value = momentum["p_value"]
        mde = momentum["mde_ratio"]
        print(f"{key:16s} {momentum['recent']:6d} {momentum['prior']:6d} "
              f"{(f'{ratio:.2f}' if ratio is not None else 'n/a'):>6s} "
              f"{(f'{p_value:.3f}' if p_value is not None else 'n/a'):>7s} "
              f"{(f'{mde:.2f}' if mde else 'n/a'):>6s} "
              f"{str(momentum['detected']):>9s}  {momentum['direction']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
