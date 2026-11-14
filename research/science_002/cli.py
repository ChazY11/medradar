"""SCIENCE-002 command chain.

    python research/science_002/cli.py fetch      # network: openFDA bulk + SEC documents
    python research/science_002/cli.py universe   # offline: entity resolution + inclusion ledger
    python research/science_002/cli.py panel      # offline: issuer-month panel with labels
    python research/science_002/cli.py experiment # offline: models, bootstrap, permutation null
    python research/science_002/cli.py audit      # offline: leakage / attribution audit battery
    python research/science_002/cli.py figures    # offline: figures from committed artifacts
    python research/science_002/cli.py all        # panel -> experiment -> audit -> figures

Every step is resumable and idempotent: inputs are cached under
research/science_002/data/cache/ (git-ignored) and each artifact is rebuilt from
the recorded input hashes. --offline forbids all network access.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.science_002 import pipeline  # noqa: E402
from research.science_002.sources import Cache  # noqa: E402


def _cache(args: argparse.Namespace) -> Cache:
    return Cache(offline=args.offline)


def cmd_fetch(args: argparse.Namespace) -> int:
    from research.science_002 import fda
    cache = _cache(args)
    outdir = pipeline.CACHE / "openfda"
    manifest_payload = fda.manifest(cache)
    parts = fda.download_bulk(cache, outdir, "510k", manifest_payload)
    for part in parts:
        print("510k bulk", part["path"], part["bytes"], part["sha256"])
    records = fda.iter_json_records(Path(parts[0]["path"]))
    info = fda.write_records_csv(records, pipeline.FIVE_TEN_K_CSV)
    print("records csv", info)
    return 0


def cmd_universe(args: argparse.Namespace) -> int:
    from research.science_002 import report
    cache = _cache(args)
    build = pipeline.build_universe(cache, artifacts=pipeline.ARTIFACTS,
                                    cache_dir=pipeline.CACHE)
    report.write_universe_artifacts(build, pipeline.ARTIFACTS)
    manifest = report.write_source_manifest(pipeline.CACHE, pipeline.ARTIFACTS)
    print("source manifest entries:", manifest["n_entries"])
    print("universe:", build.meta)
    return 0


def cmd_panel(args: argparse.Namespace) -> int:
    from research.science_002 import panel, report
    cache = _cache(args)
    build = pipeline.build_universe(cache, artifacts=pipeline.ARTIFACTS,
                                    cache_dir=pipeline.CACHE)
    p = panel.build_panel(build, pipeline.clearance_index(build))
    report.write_panel_artifacts(p, build, pipeline.ARTIFACTS)
    print("panel:", p.meta)
    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    from research.science_002 import experiment, panel, report
    cache = _cache(args)
    build = pipeline.build_universe(cache, artifacts=pipeline.ARTIFACTS,
                                    cache_dir=pipeline.CACHE)
    p = panel.build_panel(build, pipeline.clearance_index(build))
    result = experiment.run(p, seed=args.seed, n_perm=args.n_perm,
                            n_boot=args.n_boot, n_placebo=args.n_placebo)
    report.write_experiment_artifacts(result, p, pipeline.ARTIFACTS)
    print("experiment:", result["verdict"]["verdict"])
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    import json
    from research.science_002 import audit, experiment, fda, panel, report
    cache = _cache(args)
    build = pipeline.build_universe(cache, artifacts=pipeline.ARTIFACTS,
                                    cache_dir=pipeline.CACHE)
    index = pipeline.clearance_index(build)
    p = panel.build_panel(build, index)
    records = fda.read_records_csv(pipeline.FIVE_TEN_K_CSV)
    result = audit.run(build, p, index, records, seed=args.seed)

    # A7 reproducibility: rerun the frozen experiment and compare the payload.
    fast = dict(n_perm=args.n_perm, n_boot=args.n_boot, placebo_features=False)
    first = experiment.run(p, seed=args.seed, **fast)
    second = experiment.run(p, seed=args.seed, **fast)
    digest = report.primary_digest
    committed = None
    committed_path = pipeline.ARTIFACTS / "experiment_results.json"
    if committed_path.exists():
        committed = digest(json.loads(committed_path.read_text(encoding="utf-8")))
    result["checks"]["A7_reproducibility"] = {
        "first_sha256": digest(first), "second_sha256": digest(second),
        "identical": digest(first) == digest(second),
        "committed_sha256": committed,
        "committed_matches": committed == digest(first),
        "passed": digest(first) == digest(second),
    }
    # A8 permutation-seed stability: the p-value must not hinge on the seed.
    third = experiment.run(p, seed=args.seed + 1, **fast)
    result["checks"]["A8_permutation_seed_stability"] = {
        "p_seed_a": first["permutation"]["p_two_sided"],
        "p_seed_b": third["permutation"]["p_two_sided"],
        "delta_seed_a": first["primary"]["delta_stratified_auc_B3c_minus_B2c"],
        "delta_seed_b": third["primary"]["delta_stratified_auc_B3c_minus_B2c"],
        "same_verdict": first["verdict"]["verdict"] == third["verdict"]["verdict"],
        "passed": first["verdict"]["verdict"] == third["verdict"]["verdict"],
    }
    result["verdict"] = audit._verdict(result["checks"]) if hasattr(audit, "_verdict") else result["verdict"]
    report.write_audit_artifacts(result, pipeline.ARTIFACTS)
    print("audit:", result["verdict"]["summary"])
    return 0


def cmd_sensitivity(args: argparse.Namespace) -> int:
    from research.science_002 import sensitivity
    cache = _cache(args)
    result = sensitivity.run_all(cache, seed=args.seed, n_perm=1000, n_boot=1000)
    payload = {"_payload_sha256": "", **result}
    from research.science_002.report import payload_sha256, write_json
    payload["_payload_sha256"] = payload_sha256(result)
    write_json(pipeline.ARTIFACTS / "sensitivity_results.json", payload)
    print("sensitivities:", result["_summary"])
    return 0


def cmd_figures(args: argparse.Namespace) -> int:
    from research.science_002 import figures
    figures.render(pipeline.ARTIFACTS)
    print("figures written")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    for fn in (cmd_panel, cmd_experiment, cmd_audit, cmd_figures):
        code = fn(args)
        if code:
            return code
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "universe", "panel", "experiment",
                                            "audit", "sensitivity", "figures", "all"])
    parser.add_argument("--offline", action="store_true",
                        help="replay the cache; never touch the network")
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--n-perm", type=int, default=2000)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--n-placebo", type=int, default=100)
    args = parser.parse_args(argv)
    handler = {
        "fetch": cmd_fetch, "universe": cmd_universe, "panel": cmd_panel,
        "experiment": cmd_experiment, "audit": cmd_audit,
        "sensitivity": cmd_sensitivity, "figures": cmd_figures,
        "all": cmd_all,
    }[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())