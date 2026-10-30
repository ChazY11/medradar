"""Score the 8-K judge calibration - thin wrapper over :mod:`medradar.calibration`.

Historical note
---------------
The first version of this script **hardcoded** the parsed LLM verdicts as a Python
literal (``LLM = {"<id>": (direction, materiality, "catalyst_type"), ...}``) and
dumped them back to ``llm_verdicts.json``. That is not a measurement: it cannot be
re-run, it cannot disagree with itself, and the original model strings were never
archived. The line is gone - every number below is derived from recorded raw
responses in ``tests/fixtures/calibration/`` through the same ``parse_verdict`` the
production judge uses.

What this script does
---------------------
1. replay the recorded LLM responses (``llm`` suite) on the 25 labelled filings;
2. replay the recorded keyword-baseline responses (``heuristic`` suite);
3. print the tables used in ``docs/CALIBRATION.md`` (overall metrics, per-filing
   comparison, confusion matrices);
4. rewrite ``docs/calibration/metrics.json`` after checking that the recomputed
   numbers match the committed table (a drifted fixture fails loudly instead of
   silently updating the published numbers).

No network, no API key: ``python docs/calibration/score.py`` is enough.

Usage::

    python docs/calibration/score.py                # print + verify + write
    python docs/calibration/score.py --no-write     # print + verify only
    python docs/calibration/score.py --out-dir tmp  # keep raw artefacts elsewhere
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # allow `python docs/calibration/score.py`
    sys.path.insert(0, str(ROOT))

from medradar.calibration import (  # noqa: E402  (path bootstrap must run first)
    CATALYST_LABELS,
    ReplayJudge,
    legacy_summary,
    metrics_sha1,
    run_calibration,
)
from medradar.util import read_json, write_json  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "calibration"
LABELS_CSV = ROOT / "docs" / "calibration" / "ground_truth.csv"
FILINGS_DIR = FIXTURES / "filings"
DEFAULT_OUT_DIR = ROOT / "data" / "calibration" / "runs"
DEFAULT_METRICS = ROOT / "docs" / "calibration" / "metrics.json"
LEGACY_KEYS = ("type_acc", "dir_acc", "dir_acc_sign", "spearman", "mae", "hi_p", "hi_r", "hi_f1")

# published values from docs/CALIBRATION.md §2 - used as a drift check
PUBLISHED = {
    "llm": {
        "type_acc": 1.0,
        "dir_acc": 0.92,
        "dir_acc_sign": 0.92,
        "spearman": 0.7997714534915624,
        "mae": 0.1464,
        "hi_p": 0.9375,
        "hi_r": 0.9375,
        "hi_f1": 0.9375,
    },
    "heuristic": {
        "type_acc": 0.6,
        "dir_acc": 0.72,
        "dir_acc_sign": 0.72,
        "spearman": 0.5822613129549279,
        "mae": 0.184,
        "hi_p": 1.0,
        "hi_r": 0.5,
        "hi_f1": 0.6666666666666666,
    },
}
TOLERANCE = 1e-9


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def _fmt_direction(value: int) -> str:
    return f"{int(value):+d}"


def _provenance(suite: str) -> dict[str, Any]:
    manifest = read_json(FIXTURES / "manifest.json", {}) or {}
    return (manifest.get("suites") or {}).get(suite, {})


def _run_suite(suite: str, out_dir: Path) -> dict[str, Any]:
    judge = ReplayJudge.from_fixtures(FIXTURES, suite=suite)
    return run_calibration(FILINGS_DIR, LABELS_CSV, judge, out_dir / suite)


def _print_overall(runs: Mapping[str, Mapping[str, Any]]) -> None:
    llm = legacy_summary(runs["llm"]["metrics"])
    baseline = legacy_summary(runs["heuristic"]["metrics"])
    print("== overall (replayed from tests/fixtures/calibration) ==")
    header = (
        f"{'metric':22}{'LLM':>9}{'heuristic':>11}{'delta':>9}"
    )
    print(header)
    for key in LEGACY_KEYS:
        delta = None
        if llm.get(key) is not None and baseline.get(key) is not None:
            delta = float(llm[key]) - float(baseline[key])
        print(
            f"{key:22}{_fmt(llm.get(key)):>9}{_fmt(baseline.get(key)):>11}"
            f"{('' if delta is None else f'{delta:+.3f}'):>9}"
        )
    print(f"{'n':22}{llm['n']:>9}{baseline['n']:>11}")


def _print_per_filing(runs: Mapping[str, Mapping[str, Any]]) -> None:
    rows = runs["llm"]["metrics"].get("per_filing") or []
    heuristic = {
        row["id"]: row for row in runs["heuristic"]["metrics"].get("per_filing") or []
    }
    print("\n== per filing ==")
    for row in rows:
        other = heuristic.get(row["id"], {})
        flags = []
        if not row["type_ok"]:
            flags.append("type")
        if not row["direction_ok"]:
            flags.append("dir")
        flag_text = f"  [{'+'.join(flags)}]" if flags else ""
        print(
            f"{row['id']} {row['company'][:26]:26} "
            f"gt={row['gt_type']:13}{_fmt_direction(row['gt_direction'])} "
            f"{row['gt_materiality']:.2f} | "
            f"llm={row['pred_type']:13}{_fmt_direction(row['pred_direction'])} "
            f"{row['pred_materiality']:.2f} | "
            f"heur={str(other.get('pred_type', '')):13}"
            f"{_fmt_direction(other.get('pred_direction', 0))} "
            f"{float(other.get('pred_materiality', 0.0)):.2f}{flag_text}"
        )


def _print_confusions(runs: Mapping[str, Mapping[str, Any]]) -> None:
    for suite, name in (("llm", "LLM"), ("heuristic", "heuristic")):
        block = runs[suite]["metrics"].get("type") or {}
        labels = block.get("labels") or list(CATALYST_LABELS)
        print(f"\n== confusion: gt (rows) vs {name} (cols), n={block.get('n')} ==")
        print("gt\\pred " + " ".join(f"{str(label)[:8]:>8}" for label in labels))
        for label, row in zip(labels, block.get("matrix") or []):
            print(f"{str(label)[:8]:8} " + " ".join(f"{count:>8}" for count in row))
        direction = runs[suite]["metrics"].get("direction") or {}
        print(f"direction labels {direction.get('labels')} matrix {direction.get('matrix')}")


def _verify(runs: Mapping[str, Mapping[str, Any]]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    for suite in ("llm", "heuristic"):
        summary = legacy_summary(runs[suite]["metrics"])
        for key, expected in PUBLISHED[suite].items():
            actual = summary.get(key)
            if actual is None or abs(float(actual) - float(expected)) > TOLERANCE:
                problems.append(
                    f"{suite}.{key}: recomputed {actual!r} != published {expected!r}"
                )
        n = runs[suite]["n"]
        if n != 25:
            problems.append(f"{suite}.n: recomputed {n} != published 25")
    return (not problems), problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay the committed calibration fixture and score it (offline)."
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="where raw responses land")
    parser.add_argument("--metrics-out", default=str(DEFAULT_METRICS), help="legacy metrics.json path")
    parser.add_argument("--no-write", action="store_true", help="print and verify only")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    runs = {
        suite: _run_suite(suite, out_dir) for suite in ("llm", "heuristic")
    }

    print("== fixture provenance ==")
    for suite in ("llm", "heuristic"):
        info = _provenance(suite)
        print(
            f"[{suite}] model={info.get('model')!r} prompt={info.get('prompt_version')!r} "
            f"recorded_at={info.get('recorded_at')!r} n={info.get('n')!r} "
            f"raw_source={info.get('raw_source')!r}"
        )
        print(f"        source: {info.get('source')}")

    _print_overall(runs)
    _print_per_filing(runs)
    _print_confusions(runs)

    ok, problems = _verify(runs)
    print("\n== reproducibility check vs docs/CALIBRATION.md §2 ==")
    if ok:
        print("PASS: recomputed metrics match the published table (tolerance 1e-9).")
    else:
        print("FAIL: fixture/score drift detected:")
        for problem in problems:
            print(f"  - {problem}")

    metrics = {
        "n": runs["llm"]["n"],
        "llm": legacy_summary(runs["llm"]["metrics"]),
        "heuristic": legacy_summary(runs["heuristic"]["metrics"]),
        "repro": {
            "how": "python docs/calibration/score.py (offline replay, no API key)",
            "fixtures": "tests/fixtures/calibration",
            "raw_source": "reconstructed_from_parsed_verdict",
            "labels_sha1": runs["llm"]["manifest"]["labels_csv"]["sha1"],
            "llm_metrics_sha1": runs["llm"]["metrics_sha1"],
            "heuristic_metrics_sha1": runs["heuristic"]["metrics_sha1"],
            "n": runs["llm"]["n"],
            "match_published": ok,
        },
    }
    metrics_path = Path(args.metrics_out)
    if not args.no_write:
        if not ok:
            print(f"not writing {metrics_path}: drifted numbers must never be published silently")
            return 1
        write_json(metrics_path, metrics)
        print(f"wrote {metrics_path}")
    print(
        json.dumps(
            {
                "metrics_sha1": metrics_sha1(runs["llm"]["metrics"]),
                "match_published": ok,
                "artefacts": {suite: runs[suite]["out_dir"] for suite in runs},
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
