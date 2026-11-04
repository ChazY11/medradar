"""Single-document smoke run of the local model adapter (real GPU, real weights).

Why a separate script from the benchmark driver
-----------------------------------------------
The benchmark records *numbers*; on the first real load we want to see the raw text
the model produced, because "0/19 parsed" is a very different bug from "the model
answered in prose".  This script prints the completion, the parse status, the
validator verdict and the measured resources for one document, and writes the whole
thing to JSON so the first real inference is a quotable artifact, not a console scroll.

It is the smallest end-to-end proof of the four distinct questions the protocol
insists on separating:

* did the model **load** (`loaded: true`, revision + weights fingerprint recorded),
* did it emit **valid JSON** (`parse_status`),
* did the output pass **evidence validation** (`validation.verdict`),
* and is the extracted content **factually right** (not answered here -- that needs a
  label; the script says so instead of implying it).

Usage:
    python experiments/local_llm_event_extraction/scripts/model_smoke.py \
        --corpus D:\\DEPPSKK\\ml-work\\corpus --doc-id fda510k-k260579
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.local_llm_event_extraction.adapters import AdapterDescriptor, HFLocalAdapter  # noqa: E402
from experiments.local_llm_event_extraction.datasets.real_documents import (  # noqa: E402
    build_real_document_dataset,
)
from experiments.local_llm_event_extraction.parsing import parse_response  # noqa: E402
from experiments.local_llm_event_extraction.prompting import build_prompt  # noqa: E402
from experiments.local_llm_event_extraction.adapters.base import ExtractionRequest  # noqa: E402
from experiments.local_llm_event_extraction.schema import ExtractorProvenance  # noqa: E402
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=r"D:\DEPPSKK\ml-work\corpus")
    parser.add_argument("--doc-id", default=None)
    parser.add_argument("--weights-path", default=DEFAULT_WEIGHTS)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--quantization", default="nf4", choices=["nf4", "none"])
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument("--max-input-chars", type=int, default=12_000)
    parser.add_argument("--out", default=r"D:\DEPPSKK\ml-work\runs\model-smoke.json")
    args = parser.parse_args(argv)

    os.environ[GATE_ENV] = "1"
    dataset = build_real_document_dataset(Path(args.corpus))
    case = next(
        (c for c in dataset.cases if args.doc_id is None or c.case_id == args.doc_id),
        None,
    )
    if case is None:
        print(f"no such document: {args.doc_id}", file=sys.stderr)
        return 2

    descriptor = AdapterDescriptor(
        adapter_id="hf-qwen3-4b-instruct",
        display_name=f"ARM B - {args.model_id} ({args.quantization})",
        backend="hf_local",
        model_id=args.model_id,
        model_revision=args.revision,
        quantization=args.quantization,
        device="cuda",
        max_input_chars=args.max_input_chars,
        max_new_tokens=args.max_new_tokens,
        prompt_version="extract-v1",
        requires_gpu=True,
        deterministic=True,
        load_gate="model_load",
    )
    adapter = HFLocalAdapter(descriptor, weights_path=args.weights_path)

    started = time.perf_counter()
    adapter.load()
    load_seconds = time.perf_counter() - started

    prompt = build_prompt(
        case.document,
        max_input_chars=args.max_input_chars,
        company_hint=case.document.metadata.get("company_hint"),
    )
    request = ExtractionRequest(
        doc_id=case.document.doc_id,
        text=case.document.text,
        source_type=case.document.source_type,
        company_hint=case.document.metadata.get("company_hint"),
        prompt=prompt,
        metadata=dict(case.document.metadata),
    )
    response = adapter.generate(request)

    provenance = ExtractorProvenance(
        system="hf_local",
        adapter_id=descriptor.adapter_id,
        model_id=descriptor.model_id,
        model_revision=descriptor.model_revision,
        prompt_version=prompt.prompt_version,
        decoding={"temperature": 0, "do_sample": False, "seed": 0},
    )
    parsed = parse_response(response.text, doc_id=case.document.doc_id, extractor=provenance)
    roster = EntityRoster.from_config()
    taxonomy = Taxonomy.from_config()
    validation = validate_extraction(
        parsed, document=case.document, roster=roster, taxonomy=taxonomy
    )

    adapter.unload()
    payload: dict[str, Any] = {
        "purpose": "FIRST_REAL_INFERENCE",
        "doc_id": case.case_id,
        "document": {
            "source_type": case.document.source_type,
            "text_style": case.document.metadata.get("text_style"),
            "company_hint": case.document.metadata.get("company_hint"),
            "text_chars": len(case.document.text),
            "content_sha256": case.document.metadata.get("content_sha256"),
        },
        "model": {
            "adapter_id": descriptor.adapter_id,
            "model_id": descriptor.model_id,
            "model_revision": descriptor.model_revision,
            "quantization": args.quantization,
            "weights_path": args.weights_path,
            "describe": adapter.describe(),
        },
        "load_seconds": round(load_seconds, 2),
        "generation": {
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "wall_time_s": response.wall_time_s,
            "finish_reason": response.finish_reason,
            "peak_vram_mb": response.peak_vram_mb,
            "metadata": dict(response.metadata),
            "raw_text": response.text,
        },
        "parse": {
            "parse_status": parsed.parse_status,
            "parse_error": parsed.parse_error,
            "events": len(parsed.events),
        },
        "validation": {
            "verdict": validation.verdict.value if hasattr(validation.verdict, "value") else str(validation.verdict),
            "judgements": [
                {
                    "index": judgement.index,
                    "verdict": judgement.verdict.value
                    if hasattr(judgement.verdict, "value")
                    else str(judgement.verdict),
                    "issues": [
                        {"code": issue.code, "severity": issue.severity.value, "detail": issue.detail}
                        for issue in judgement.issues
                    ],
                }
                for judgement in validation.judgements
            ],
        },
        "factual_correctness": "NOT_DETERMINED — requires an independent label; not implied by parse/validation success",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:6000])
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
