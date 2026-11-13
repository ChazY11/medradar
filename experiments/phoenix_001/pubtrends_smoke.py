#!/usr/bin/env python3
"""Smoke-test PubTrends' Apache-2.0 topic-description algorithm without its stack."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_repo", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.source_repo.resolve()
    module_path = repo / "pysrc" / "papers" / "analysis" / "topics.py"

    # The real module imports text.py, which loads SpaCy/NLTK models at import time.
    # Stub only that unused dependency; execute the upstream topics.py itself.
    stub = types.ModuleType("pysrc.papers.analysis.text")
    stub.get_frequent_tokens = lambda tokens: {}
    sys.modules["pysrc.papers.analysis.text"] = stub
    spec = importlib.util.spec_from_file_location("pubtrends_topics_isolated", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    comps = {0: [0], 1: [1], 2: [2]}
    tokens = ["frequent", "rare-1", "rare-2"]
    counts = np.array([[30, 0, 0], [30, 15, 0], [30, 0, 15]])
    one = module._get_topics_description_cosine(comps, tokens, counts, 1)
    two = module._get_topics_description_cosine(comps, tokens, counts, 2, ignore_comp=0)
    expected_one = {0: "frequent", 1: "rare-1", 2: "rare-2"}
    observed_one = {key: values[0][0] for key, values in one.items()}
    assert observed_one == expected_one, (observed_one, expected_one)
    assert two[0] == []
    assert [v[0] for v in two[1]] == ["frequent", "rare-1"]
    assert [v[0] for v in two[2]] == ["frequent", "rare-2"]
    expected_weights = {0: 2.60, 1: 2.77, 2: 2.77}
    for comp, expected in expected_weights.items():
        assert np.isclose(one[comp][0][1], expected, rtol=1e-2), (comp, one[comp])

    payload = {
        "status": "passed",
        "source_repository": "https://github.com/JetBrains-Research/pubtrends",
        "source_file": "pysrc/papers/analysis/topics.py",
        "source_commit": __import__("subprocess").check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        "license": "Apache-2.0",
        "scope": "Topic-description cosine weighting only; no PostgreSQL, Redis, web service, corpus crawler, SpaCy model or GPU.",
        "deviation": "Unused text.py import was stubbed to avoid heavyweight model loading; upstream topics.py executed unchanged.",
        "observed": {
            "single_word_topics": observed_one,
            "single_word_weights": {str(k): one[k][0][1] for k in one},
            "ignore_component_two_word": {str(k): [v[0] for v in values] for k, values in two.items()},
        },
        "versions": {"python": sys.version, "numpy": np.__version__},
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["observed"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
