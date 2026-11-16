"""Local small-model enrichment worker (Qwen3-0.6B by default).

This is the *optional* second layer of the intelligence engine. It is built to fail safely:

* it runs as a **single-start, low-priority process** that exits when its batch is done, so a
  model never sits resident on a 2 vCPU / 4 GB host;
* it is started only when the resource guard allows it, and only for a bounded batch;
* **nothing it produces is a confirmed fact.** Every proposal is written to
  ``ai_candidate`` with the deterministic verdict of
  :meth:`medradar.radar.classify.RuleMapper.vet_model_claim`. A proposal without a verbatim
  quote from the source text is rejected and the rejection is stored;
* if the model is missing, unloadable, slow or wrong, discovery, the ledger and the graph are
  unaffected - the queue simply keeps its backlog.

Measured, not asserted: :func:`run_batch` returns JSON-validity, acceptance, timing, tokens
per second and peak RSS for the batch it actually ran, and :mod:`medradar.radar.ai.evaluate`
runs the same harness against a labelled set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Mapping

from ..classify import RuleMapper
from ..ledger import ObservationLedger
from ..records import PROC_AI_DONE, PROC_AI_FAILED, PROC_AI_PENDING
from ..resources import peak_rss_mb, set_low_priority
from .prompts import PROMPT_VERSION, build_messages, build_prompt, extract_json

DEFAULT_MODEL = "Qwen3-0.6B"
MODEL_VERSION_TAG = "qwen3-0.6b-transformers-cpu-fp32"
PROMPT_VERSION_TAG = PROMPT_VERSION
MAX_NEW_TOKENS = 192
MAX_THREADS = 4


class AIUnavailable(RuntimeError):
    """The model or its runtime is not available on this host."""


def default_model_path() -> Path | None:
    """Look for a local model directory in the usual places. Never downloads anything."""
    candidates: list[Path] = []
    env = str(os.environ.get("MEDRADAR_AI_MODEL") or "").strip()
    if env:
        candidates.append(Path(env))
    home = str(os.environ.get("MEDRADAR_MODEL_DIR") or "").strip()
    if home:
        candidates.append(Path(home) / DEFAULT_MODEL)
    candidates.append(Path.home() / ".medradar" / "models" / DEFAULT_MODEL)
    # A sibling of the checkout: the layout the acceptance runs use.
    repo = Path(__file__).resolve().parents[3]
    candidates.append(repo.parent / "ml-models" / DEFAULT_MODEL)
    candidates.append(repo / "models" / DEFAULT_MODEL)
    for candidate in candidates:
        if (candidate / "config.json").is_file():
            return candidate
    return None


class QwenClassifier:
    """Thin wrapper around a local causal LM. Lazy imports keep the base install light."""

    def __init__(self, model_path: Path, *, max_new_tokens: int = MAX_NEW_TOKENS,
                 threads: int = MAX_THREADS) -> None:
        self.model_path = Path(model_path)
        self.max_new_tokens = int(max_new_tokens)
        self.threads = int(threads)
        self._loaded = False
        self.model = None
        self.tokenizer = None
        self.load_seconds: float | None = None

    @property
    def model_id(self) -> str:
        return self.model_path.name

    def load(self) -> "QwenClassifier":
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as error:  # noqa: BLE001
            raise AIUnavailable(
                "transformers and torch are required for the AI worker "
                f"({type(error).__name__}: {error}). Discovery does not need them."
            ) from error
        started = time.perf_counter()
        torch.set_num_threads(max(1, self.threads))
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))
            self.model = AutoModelForCausalLM.from_pretrained(
                str(self.model_path),
                dtype=torch.float32,
                low_cpu_mem_usage=True,
            )
        except TypeError:
            # Older transformers used ``torch_dtype``.
            self.model = AutoModelForCausalLM.from_pretrained(
                str(self.model_path), torch_dtype=torch.float32, low_cpu_mem_usage=True,
            )
        self.model.eval()
        self._torch = torch
        self.load_seconds = round(time.perf_counter() - started, 2)
        self._loaded = True
        return self

    def _render(self, messages: list[dict[str, str]]) -> str:
        try:
            return self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            return self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

    def generate(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if not self._loaded:
            raise AIUnavailable("the model is not loaded")
        torch = self._torch
        prompt = self._render(messages)
        started = time.perf_counter()
        with torch.no_grad():
            encoded = self.tokenizer(prompt, return_tensors="pt")
            output = self.model.generate(
                **encoded,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        elapsed = time.perf_counter() - started
        generated = output[0][encoded["input_ids"].shape[-1]:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        return {
            "text": text,
            "prompt_tokens": int(encoded["input_ids"].shape[-1]),
            "generated_tokens": int(generated.shape[-1]),
            "seconds": round(elapsed, 3),
            "tokens_per_second": round(int(generated.shape[-1]) / elapsed, 2) if elapsed > 0 else None,
        }


def _record_text(ledger: ObservationLedger, observation_id: str) -> tuple[dict[str, Any], str]:
    head = ledger.observation_row(observation_id) or {}
    versions = ledger.versions(observation_id)
    payload = (versions[-1]["payload"] if versions else {}) or {}
    body = " ".join(str(payload.get(key) or "") for key in ("abstract", "description", "summary",
                                                            "statement_or_summary", "ao_statement"))
    return head, body


def run_batch(
    ledger: ObservationLedger,
    taxonomy,
    *,
    limit: int = 8,
    model_path: str | Path | None = None,
    classifier: QwenClassifier | None = None,
    log: Callable[[str], None] = print,
    polite: bool = True,
) -> dict[str, Any]:
    """Enrich up to ``limit`` queued observations. Returns measured batch statistics."""
    started = time.perf_counter()
    priority = set_low_priority() if polite else {"applied_on": "none"}
    tasks = ledger.claim_tasks(kind="ai_enrichment", limit=limit)
    if not tasks:
        return {
            "state": "idle", "claimed": 0, "processed": 0,
            "reason": "no queued enrichment task",
            "queue": ledger.queue_summary(),
        }
    if classifier is None:
        path = Path(model_path) if model_path else default_model_path()
        if path is None:
            for task in tasks:
                ledger.defer_task(task["task_id"],
                                  reason="no local model directory was found",
                                  retry_after_at=None)
            return {
                "state": "unavailable", "claimed": len(tasks), "processed": 0,
                "reason": (
                    "no local model directory was found. Set MEDRADAR_AI_MODEL to a directory "
                    "containing config.json; nothing was downloaded."
                ),
                "queue": ledger.queue_summary(),
            }
        classifier = QwenClassifier(path)
    try:
        classifier.load()
    except AIUnavailable as error:
        for task in tasks:
            ledger.defer_task(task["task_id"], reason=str(error), retry_after_at=None)
        return {"state": "unavailable", "claimed": len(tasks), "processed": 0,
                "reason": str(error), "queue": ledger.queue_summary()}

    mapper = RuleMapper(taxonomy)
    allowed_topics = [topic.public() for topic in taxonomy.topics]
    allowed_orgs = [org.public() for org in taxonomy.organizations]
    results: list[dict[str, Any]] = []
    json_valid = 0
    accepted_topics = 0
    rejected_claims = 0
    total_tokens = 0
    total_seconds = 0.0
    for task in tasks:
        observation_id = task["observation_id"]
        head, body = _record_text(ledger, observation_id)
        title = str(head.get("title") or "")
        source_text = " ".join([title, body])
        prompt = build_prompt(
            title=title, body=body, record_type=str(head.get("record_type") or ""),
            source=str(head.get("source") or ""),
            allowed_topics=allowed_topics, allowed_organizations=allowed_orgs,
        )
        try:
            generation = classifier.generate(build_messages(prompt))
        except Exception as error:  # noqa: BLE001 - one bad record must not stop the batch
            ledger.finish_task(task["task_id"], state="FAILED",
                               error=f"{type(error).__name__}: {error}"[:400])
            ledger.set_processing_state(observation_id, PROC_AI_FAILED)
            results.append({"observation_id": observation_id, "state": "generation_failed",
                            "error": f"{type(error).__name__}: {error}"[:300]})
            continue
        total_tokens += generation["generated_tokens"]
        total_seconds += generation["seconds"]
        parsed, error = extract_json(generation["text"])
        validations: list[dict[str, Any]] = []
        if error is not None or not isinstance(parsed, dict):
            ledger.record_ai_candidate(
                observation_id=observation_id, version_id=task.get("version_id"),
                model_id=classifier.model_id, model_version=MODEL_VERSION_TAG,
                prompt_version=PROMPT_VERSION_TAG,
                payload={"raw_output": generation["text"][:2000]},
                validation={"json_error": error or "output is not a JSON object"},
                validation_state="JSON_INVALID",
            )
            ledger.finish_task(task["task_id"], state="DONE",
                               error=f"unparseable output: {error}"[:400])
            ledger.set_processing_state(observation_id, PROC_AI_FAILED)
            results.append({"observation_id": observation_id, "state": "json_invalid",
                            "error": error, "generated_tokens": generation["generated_tokens"]})
            continue
        json_valid += 1
        for claim in (parsed.get("topics") or [])[:3]:
            if not isinstance(claim, dict):
                continue
            verdict = mapper.vet_model_claim(
                {"kind": "topic", "value": claim.get("id"),
                 "evidence_quote": claim.get("evidence_quote"), "confidence": claim.get("confidence")},
                source_text=source_text,
            )
            validations.append(verdict)
            if verdict["accepted"]:
                accepted_topics += 1
            else:
                rejected_claims += 1
        for claim in (parsed.get("organizations") or [])[:3]:
            if not isinstance(claim, dict):
                continue
            verdict = mapper.vet_model_claim(
                {"kind": "organization", "value": claim.get("name"),
                 "evidence_quote": claim.get("evidence_quote"), "confidence": claim.get("confidence")},
                source_text=source_text,
            )
            validations.append(verdict)
            if not verdict["accepted"]:
                rejected_claims += 1
        accepted = any(verdict["accepted"] for verdict in validations)
        ledger.record_ai_candidate(
            observation_id=observation_id, version_id=task.get("version_id"),
            model_id=classifier.model_id, model_version=MODEL_VERSION_TAG,
            prompt_version=PROMPT_VERSION_TAG,
            payload={"parsed": parsed, "summary": parsed.get("summary")},
            validation={"claims": validations, "accepted_any": accepted},
            validation_state="ACCEPTED" if accepted else "REJECTED",
        )
        ledger.finish_task(task["task_id"], state="DONE")
        ledger.set_processing_state(observation_id, PROC_AI_DONE)
        results.append({
            "observation_id": observation_id,
            "state": "accepted" if accepted else "rejected",
            "accepted_topics": sum(1 for verdict in validations
                                   if verdict["accepted"] and verdict["kind"] == "topic"),
            "claims": len(validations),
            "generated_tokens": generation["generated_tokens"],
            "tokens_per_second": generation["tokens_per_second"],
        })
    elapsed = round(time.perf_counter() - started, 2)
    summary = {
        "state": "ran",
        "claimed": len(tasks),
        "processed": len(results),
        "json_valid": json_valid,
        "json_validity_rate": round(json_valid / len(results), 4) if results else None,
        "accepted_topic_claims": accepted_topics,
        "rejected_claims": rejected_claims,
        "model": {
            "id": classifier.model_id,
            "version": MODEL_VERSION_TAG,
            "prompt_version": PROMPT_VERSION_TAG,
            "load_seconds": classifier.load_seconds,
            "threads": classifier.threads,
            "path": str(classifier.model_path),
        },
        "performance": {
            "elapsed_seconds": elapsed,
            "generated_tokens": total_tokens,
            "generation_seconds": round(total_seconds, 2),
            "tokens_per_second": round(total_tokens / total_seconds, 2) if total_seconds else None,
            "peak_rss_mb": peak_rss_mb(),
        },
        "priority": priority,
        "queue": ledger.queue_summary(),
        "results": results,
    }
    try:
        log(f"[ai] processed {len(results)} record(s): json_valid={json_valid} "
            f"accepted_topics={accepted_topics} rejected={rejected_claims} "
            f"tokens/s={summary['performance']['tokens_per_second']} "
            f"rss={summary['performance']['peak_rss_mb']}MB")
    except Exception:  # pragma: no cover
        pass
    return summary


def main(argv: list[str] | None = None) -> int:
    from ..graph import open_graph
    from ..paths import radar_paths
    from ..taxonomy import load_taxonomy

    parser = argparse.ArgumentParser(description="Run one RADAR-001 AI enrichment batch and exit.")
    parser.add_argument("--data-dir", default=None, help="radar data directory")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--model", default=None, help="local model directory")
    parser.add_argument("--json", action="store_true", help="print only the JSON result")
    args = parser.parse_args(argv)

    paths = radar_paths(args.data_dir)
    taxonomy = load_taxonomy()
    if not paths.ledger.is_file():
        print(json.dumps({"state": "unavailable", "reason": "no radar ledger at " + str(paths.ledger)}))
        return 0
    ledger = ObservationLedger(paths.ledger, create=False)
    try:
        result = run_batch(ledger, taxonomy, limit=args.limit, model_path=args.model,
                           log=(lambda message: None) if args.json else print)
        ledger.set_runtime("ai_state", result)
    except Exception as error:  # noqa: BLE001
        result = {"state": "failed", "reason": f"{type(error).__name__}: {error}",
                  "traceback": traceback.format_exc()[-2000:]}
        ledger.set_runtime("ai_state", result)
        if not args.json:
            print(json.dumps(result, indent=2))
        return 1
    finally:
        ledger.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps({key: value for key, value in result.items() if key != "results"},
                         indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
