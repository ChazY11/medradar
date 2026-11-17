"""Measured evaluation of the local enrichment model.

The point of this module is that the numbers are produced by running the model, not by
asserting that it works. It reports, for one labelled set:

* **JSON validity rate** - share of outputs that parsed as the required object;
* **topic precision / recall / F1** - against hand-assigned expected topic ids;
* **organisation accuracy** - against hand-assigned expected vendor (or ``null``);
* **evidence fidelity** - share of *accepted* claims whose quote actually appears verbatim in
  the source text (this should be 1.0 by construction, and a value below 1.0 is a bug in the
  vetting gate, so it is measured rather than assumed);
* **CPU inference speed** - tokens/second and seconds per record;
* **peak RSS** - the worker's own peak resident memory;
* **impact on discovery** - a wall-clock comparison of a discovery cycle run before, during
  and after the batch, so "the model does not block collection" is a measurement.

The labelled set is keyed by *official identifier* (PMID, DOI, K-number), not by a database
row, so it stays valid across databases and machines.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..classify import RuleMapper
from ..ledger import ObservationLedger
from ..resources import peak_rss_mb
from .prompts import PROMPT_VERSION, build_messages, build_prompt, extract_json
from .worker import AIUnavailable, MODEL_VERSION_TAG, QwenClassifier, default_model_path


def load_eval_set(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if not items:
        raise ValueError(f"{path}: the evaluation set has no items")
    return payload


def _resolve(ledger: ObservationLedger, identifier: str) -> dict[str, Any] | None:
    row = ledger.one(
        "SELECT * FROM observation WHERE official_identifier=? ORDER BY first_observed_at LIMIT 1",
        (identifier,),
    )
    return row


def _source_text(ledger: ObservationLedger, observation_id: str) -> tuple[dict[str, Any], str, str]:
    head = ledger.observation_row(observation_id) or {}
    versions = ledger.versions(observation_id)
    payload = (versions[-1]["payload"] if versions else {}) or {}
    body = " ".join(str(payload.get(key) or "") for key in ("abstract", "description", "summary",
                                                            "statement_or_summary", "ao_statement"))
    title = str(head.get("title") or "")
    return head, title, body


def run_evaluation(
    ledger: ObservationLedger,
    taxonomy,
    eval_set: Mapping[str, Any],
    *,
    model_path: str | Path | None = None,
    classifier: QwenClassifier | None = None,
    log: Callable[[str], None] = print,
    discovery_probe: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Run the model over the labelled set and report measured metrics."""
    started = time.perf_counter()
    mapper = RuleMapper(taxonomy)
    allowed_topics = [topic.public() for topic in taxonomy.topics]
    allowed_orgs = [org.public() for org in taxonomy.organizations]
    if classifier is None:
        path = Path(model_path) if model_path else default_model_path()
        if path is None:
            raise AIUnavailable("no local model directory was found")
        classifier = QwenClassifier(path)
    discovery_before = discovery_probe() if discovery_probe else None
    classifier.load()

    rows: list[dict[str, Any]] = []
    #: Every item the model was actually asked about. This - not ``evaluated`` - is the
    #: denominator for JSON validity: an output that failed to parse is still an attempt, and
    #: excluding it is exactly the selective accounting this metric exists to prevent.
    attempts = 0
    json_valid = 0
    json_invalid = 0
    ledger_misses = 0
    tp = fp = fn = 0
    org_correct = org_total = 0
    accepted_claims = 0
    fidelity_ok = 0
    generation_seconds: list[float] = []
    generated_tokens = 0
    discovery_during = None
    for index, item in enumerate(eval_set["items"]):
        identifier = str(item["official_identifier"])
        row = _resolve(ledger, identifier)
        if row is None:
            ledger_misses += 1
            rows.append({"official_identifier": identifier, "state": "not_in_ledger"})
            continue
        head, title, body = _source_text(ledger, row["observation_id"])
        source_text = " ".join([title, body])
        prompt = build_prompt(title=title, body=body, record_type=str(head.get("record_type") or ""),
                             source=str(head.get("source") or ""),
                             allowed_topics=allowed_topics, allowed_organizations=allowed_orgs)
        generation = classifier.generate(build_messages(prompt))
        attempts += 1
        generation_seconds.append(generation["seconds"])
        generated_tokens += generation["generated_tokens"]
        if index == 0 and discovery_probe:
            discovery_during = discovery_probe()
        parsed, error = extract_json(generation["text"])
        expected_topics = set(item.get("expected_topics") or [])
        expected_org = item.get("expected_organization")
        if error is not None or not isinstance(parsed, dict):
            json_invalid += 1
            rows.append({"official_identifier": identifier, "state": "json_invalid", "error": error,
                         "raw_output": generation["text"][:400],
                         "expected_topics": sorted(expected_topics)})
            fn += len(expected_topics)
            # An unparseable output is also a wrong organisation answer: it named no vendor.
            # Counting it in the denominator keeps organisation accuracy from flattering itself
            # by dropping exactly the records the model failed on.
            org_total += 1
            continue
        json_valid += 1
        predicted: set[str] = set()
        claims: list[dict[str, Any]] = []
        for claim in (parsed.get("topics") or [])[:3]:
            if not isinstance(claim, dict):
                continue
            verdict = mapper.vet_model_claim(
                {"kind": "topic", "value": claim.get("id"),
                 "evidence_quote": claim.get("evidence_quote")}, source_text=source_text)
            claims.append(verdict)
            if verdict["accepted"]:
                accepted_claims += 1
                predicted.add(str(claim.get("id")))
                if str(claim.get("evidence_quote") or "").lower() in source_text.lower():
                    fidelity_ok += 1
        predicted_org = None
        for claim in (parsed.get("organizations") or [])[:3]:
            if not isinstance(claim, dict):
                continue
            verdict = mapper.vet_model_claim(
                {"kind": "organization", "value": claim.get("name"),
                 "evidence_quote": claim.get("evidence_quote")}, source_text=source_text)
            claims.append(verdict)
            if verdict["accepted"]:
                accepted_claims += 1
                predicted_org = verdict.get("organization_id") or predicted_org
                # An accepted organisation claim must also carry a verbatim quote, so it belongs
                # in the fidelity denominator. Counting only topic claims made fidelity look
                # like a gate failure when it was a metric bug.
                if str(claim.get("evidence_quote") or "").lower() in source_text.lower():
                    fidelity_ok += 1
        org_total += 1
        if (predicted_org or None) == (expected_org or None):
            org_correct += 1
        tp += len(predicted & expected_topics)
        fp += len(predicted - expected_topics)
        fn += len(expected_topics - predicted)
        rows.append({
            "official_identifier": identifier,
            "title": title[:120],
            "state": "evaluated",
            "expected_topics": sorted(expected_topics),
            "predicted_topics": sorted(predicted),
            "expected_organization": expected_org,
            "predicted_organization": predicted_org,
            "accepted_claims": sum(1 for claim in claims if claim["accepted"]),
            "rejected_claims": sum(1 for claim in claims if not claim["accepted"]),
            "generated_tokens": generation["generated_tokens"],
            "seconds": generation["seconds"],
        })
    discovery_after = discovery_probe() if discovery_probe else None
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    elapsed = round(time.perf_counter() - started, 2)
    evaluated = [row for row in rows if row["state"] == "evaluated"]
    summary = {
        "schema": "medradar.radar.ai_eval.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "eval_set": {
            "name": eval_set.get("name"),
            "version": eval_set.get("version"),
            "labelled_by": eval_set.get("labelled_by"),
            "items": len(eval_set["items"]),
            "in_ledger": attempts,
            "attempted": attempts,
            "evaluated": len(evaluated),
            "not_in_ledger": ledger_misses,
        },
        "model": {
            "id": classifier.model_id,
            "version": MODEL_VERSION_TAG,
            "prompt_version": PROMPT_VERSION,
            "load_seconds": classifier.load_seconds,
            "threads": classifier.threads,
        },
        "metrics": {
            # Denominator = every item the model produced an output for. A previous revision
            # divided by ``evaluated`` (parsed-only) and reported 100% on a batch that had three
            # ``json_invalid`` outputs in fourteen attempts. That was a metric bug, not a model
            # result, and it is the reason these counts are reported next to the rate.
            "json_validity_rate": round(json_valid / attempts, 4) if attempts else None,
            "model_attempts": attempts,
            "json_valid_outputs": json_valid,
            "json_invalid_outputs": json_invalid,
            "topic_precision": round(precision, 4) if precision is not None else None,
            "topic_recall": round(recall, 4) if recall is not None else None,
            "topic_f1": round(f1, 4) if f1 is not None else None,
            # Same rule: organisation accuracy is measured over every attempt, and an output that
            # did not parse counts as a wrong answer rather than disappearing from the sample.
            "organization_accuracy": round(org_correct / org_total, 4) if org_total else None,
            "organization_samples": org_total,
            "evidence_fidelity_rate": round(fidelity_ok / accepted_claims, 4) if accepted_claims else None,
            "accepted_claims": accepted_claims,
            "tokens_per_second": (round(generated_tokens / sum(generation_seconds), 2)
                                  if generation_seconds and sum(generation_seconds) else None),
            "median_seconds_per_record": round(statistics.median(generation_seconds), 3)
            if generation_seconds else None,
            "peak_rss_mb": peak_rss_mb(),
            "elapsed_seconds": elapsed,
        },
        "discovery_impact": {
            "before_seconds": discovery_before,
            "during_seconds": discovery_during,
            "after_seconds": discovery_after,
            "note": (
                "The discovery probe measures one real source check immediately before, during and "
                "after the model batch. A materially slower 'during' value would mean the worker "
                "competes with collection."
            ),
        },
        "items": rows,
        "interpretation": (
            "Topic precision is measured against hand-assigned labels, not against a rule's own "
            "output. A rejected model claim is a correct behaviour, not a miss: the vetting gate "
            "requires a verbatim quote in the source text. JSON validity is divided by every model "
            "attempt, including outputs that failed to parse; organisation accuracy counts an "
            "unparseable output as a wrong answer."
        ),
    }
    try:
        log(f"[ai-eval] json={summary['metrics']['json_validity_rate']} "
            f"f1={summary['metrics']['topic_f1']} "
            f"org_acc={summary['metrics']['organization_accuracy']} "
            f"tok/s={summary['metrics']['tokens_per_second']} "
            f"rss={summary['metrics']['peak_rss_mb']}MB")
    except Exception:  # pragma: no cover
        pass
    return summary


def build_candidate_set(ledger: ObservationLedger, *, limit: int = 24, seed: int = 7) -> dict[str, Any]:
    """Dump real records for a human to label. Never auto-labels."""
    rows = ledger.raw(
        "SELECT official_identifier, source, record_type, title FROM observation"
        " WHERE official_identifier IS NOT NULL AND record_type IN ('publication','regulatory_record')"
        " ORDER BY official_identifier"
    )
    import random

    random.Random(seed).shuffle(rows)
    chosen = rows[:limit]
    return {
        "schema": "medradar.radar.ai_eval_set.v1",
        "version": "candidate-" + datetime.now(timezone.utc).strftime("%Y%m%d"),
        "name": "unlabelled candidate set",
        "labelled_by": "NOT LABELLED YET",
        "items": [
            {"official_identifier": row["official_identifier"], "title": row["title"],
             "source": row["source"], "expected_topics": [], "expected_organization": None}
            for row in chosen
        ],
    }


def main(argv: list[str] | None = None) -> int:
    from ..paths import radar_paths
    from ..taxonomy import load_taxonomy

    parser = argparse.ArgumentParser(description="Measure the RADAR-001 AI worker on a labelled set.")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--eval-set", default=None, help="path to the labelled JSON set")
    parser.add_argument("--model", default=None)
    parser.add_argument("--out", default=None, help="write the full report JSON here")
    parser.add_argument("--build-candidates", action="store_true",
                        help="print an unlabelled candidate set instead of evaluating")
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args(argv)

    paths = radar_paths(args.data_dir)
    taxonomy = load_taxonomy()
    ledger = ObservationLedger(paths.ledger, create=False)
    try:
        if args.build_candidates:
            print(json.dumps(build_candidate_set(ledger, limit=args.limit), indent=2, ensure_ascii=False))
            return 0
        eval_path = args.eval_set or str(Path(__file__).resolve().parents[3] /
                                         "config" / "radar" / "ai_eval_set.json")
        eval_set = load_eval_set(eval_path)
        report = run_evaluation(ledger, taxonomy, eval_set, model_path=args.model)
    finally:
        ledger.close()
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(json.dumps({key: value for key, value in report.items() if key != "items"},
                         indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
