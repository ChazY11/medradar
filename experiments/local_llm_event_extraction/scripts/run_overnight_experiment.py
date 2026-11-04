"""Evaluate the overnight arms on the independent test split (Phase D entry point).

Arms
----
``A0 rules-baseline``        the Phase 2 deterministic rules system, unchanged;
``B  hf-qwen3-4b-instruct``  the untuned base model, prompt v2;
``C  qlora-overnight``       the exploratory QLoRA adapter, prompt v2.

Optional ablation runs differ in exactly one prompt factor (``extract-v1`` vs
``extract-v2``), with the same checkpoint, the same split and the same decoding.

What this driver refuses to do
------------------------------
* It will not evaluate on anything but ``--splits`` (default: the test split) and
  the runner records which splits it used in the config hash.
* It will not report precision/recall/F1 as a result.  The gold events are
  ``source_record_derived`` silver labels, so the numbers are *exploratory
  agreement*; that distinction is written into the summary and the report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.local_llm_event_extraction.adapters import (  # noqa: E402
    AdapterDescriptor,
    HFLocalAdapter,
    RuleBasedAdapter,
    rules_descriptor,
)
from experiments.local_llm_event_extraction.adapters.rule_based_locale import (  # noqa: E402
    LocaleAwareRuleBasedAdapter,
    locale_rules_descriptor,
)
from experiments.local_llm_event_extraction.benchmark import run_benchmark  # noqa: E402
from experiments.local_llm_event_extraction.datasets.overnight_corpus import (  # noqa: E402
    build_dataset,
)
from experiments.local_llm_event_extraction.prompting import PROMPT_VERSION  # noqa: E402
from experiments.local_llm_event_extraction.validation.entities import (  # noqa: E402
    EntityRoster,
    Taxonomy,
)
from experiments.local_llm_event_extraction.validation.validator import (  # noqa: E402
    validate_extraction,
)

GATE_ENV = "MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD"
DEFAULT_MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
DEFAULT_WEIGHTS = r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507"
DEFAULT_CORPUS = r"D:\DEPPSKK\ml-work\overnight\corpus\ovn-2026-11-04"
DEFAULT_OUT = r"D:\DEPPSKK\ml-work\overnight\runs\eval"


def _alias_map(roster: EntityRoster) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical_id in roster.canonical_ids:
        mapping[canonical_id] = canonical_id
        for alias in roster.aliases_for(canonical_id):
            mapping.setdefault(alias, canonical_id)
    return mapping


def _hf_descriptor(
    *, adapter_id: str, display: str, max_new_tokens: int
) -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id=adapter_id,
        display_name=display,
        backend="hf_local",
        model_id=DEFAULT_MODEL_ID,
        model_revision=DEFAULT_REVISION,
        quantization="nf4",
        device="cuda",
        max_input_chars=12_000,
        max_new_tokens=max_new_tokens,
        prompt_version=PROMPT_VERSION,
        requires_network=False,
        requires_gpu=True,
        deterministic=True,
        load_gate="model_load",
        enabled_by_default=False,
    )


def build_arms(args: argparse.Namespace, roster: EntityRoster) -> tuple[list[Any], dict[str, Any]]:
    alias_map = _alias_map(roster)
    arms: list[Any] = []
    info: dict[str, Any] = {}
    if args.include_rules:
        descriptor = rules_descriptor()
        arms.append(RuleBasedAdapter(descriptor, alias_map=alias_map))
        info[descriptor.adapter_id] = descriptor.to_dict()
    if args.include_rules_a1:
        descriptor_a1 = locale_rules_descriptor()
        arms.append(LocaleAwareRuleBasedAdapter(descriptor_a1, alias_map=alias_map))
        info[descriptor_a1.adapter_id] = descriptor_a1.to_dict()
    descriptor_b = _hf_descriptor(
        adapter_id="hf-qwen3-4b-instruct",
        display=f"ARM B - {DEFAULT_MODEL_ID} (nf4) untuned",
        max_new_tokens=args.max_new_tokens,
    )
    if args.include_base:
        arms.append(
            HFLocalAdapter(descriptor_b, weights_path=args.weights_path, cache_dir=args.cache_dir)
        )
        info[descriptor_b.adapter_id] = descriptor_b.to_dict()
    if args.adapter_path:
        descriptor_c = _hf_descriptor(
            adapter_id="qlora-overnight",
            display=f"ARM C - {DEFAULT_MODEL_ID} (nf4) + exploratory QLoRA adapter",
            max_new_tokens=args.max_new_tokens,
        )
        arms.append(
            HFLocalAdapter(
                descriptor_c,
                weights_path=args.weights_path,
                cache_dir=args.cache_dir,
                peft_adapter_path=args.adapter_path,
            )
        )
        info[descriptor_c.adapter_id] = descriptor_c.to_dict()
    return arms, info


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--weights-path", default=DEFAULT_WEIGHTS)
    parser.add_argument("--cache-dir", default=r"D:\DEPPSKK\ml-cache\hf")
    parser.add_argument("--adapter-path", default=None)
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    parser.add_argument("--splits", default="test")
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-rules", action="store_true", default=True)
    parser.add_argument("--include-base", action="store_true", default=True)
    parser.add_argument("--rules-only", dest="include_base", action="store_false")
    parser.add_argument("--include-canonical-id-hint", default="1")
    parser.add_argument(
        "--include-rules-a1",
        action="store_true",
        default=True,
        help="arm A1: the strengthened deterministic rules (locale dates + date kinds)",
    )
    parser.add_argument(
        "--no-rules-a1", dest="include_rules_a1", action="store_false"
    )
    args = parser.parse_args(argv)

    os.environ[GATE_ENV] = "1"
    manifest, audit = build_dataset(args.corpus)
    roster = EntityRoster.from_config()
    taxonomy = Taxonomy.from_config()
    # The 50-track list is not rendered (see training/train_overnight.py): it costs
    # ~560 tokens per sample and this run's prompt budget cannot afford it.  The
    # 23-domain closed vocabulary is rendered, which is the factor under test.
    domain_track_map: dict[str, str] = {}
    splits = [part.strip() for part in args.splits.split(",") if part.strip()]
    prompt_options = {
        "prompt_version": args.prompt_version,
        "technology_domains": list(taxonomy.domain_ids) if args.prompt_version != "extract-v1" else None,
        "domain_track_map": domain_track_map if args.prompt_version != "extract-v1" else None,
        "include_canonical_id_hint": args.include_canonical_id_hint not in {"0", "false", "no"},
    }
    arms, arms_info = build_arms(args, roster)
    if not arms:
        print("REFUSED: no arms selected", file=sys.stderr)
        return 2

    run = run_benchmark(
        manifest,
        arms,
        output_dir=args.out,
        run_id=args.run_id,
        validator=validate_extraction,
        roster=roster,
        taxonomy=taxonomy,
        splits=splits,
        limit=args.limit,
        prompt_options=prompt_options,
        config={
            "corpus_dir": args.corpus,
            "corpus_sha256": audit["corpus"]["corpus_sha256"],
            "dataset_label_tier": "source_record_derived",
            "prompt_version": args.prompt_version,
            "prompt_options": {
                key: (value if key != "domain_track_map" else f"{len(value or {})} tracks")
                for key, value in prompt_options.items()
                if key != "technology_domains"
            },
            "domain_vocabulary_size": len(taxonomy.domain_ids),
            "splits": splits,
            "max_new_tokens": args.max_new_tokens,
            "note": (
                "EXPLORATORY agreement against SOURCE_DERIVED_SILVER labels. No precision, "
                "recall or F1 may be quoted from this run: the labels are machine-derived "
                "and not human annotations."
            ),
            "arms": arms_info,
        },
    )
    print(json.dumps({"run_id": run.run_id, "run_dir": str(run.run_dir), "status": run.status}, indent=2))
    print(f"artifacts: {run.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
