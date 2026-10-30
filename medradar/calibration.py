"""Reproducible calibration harness for the 8-K judge (LLM vs human labels).

The problem
-----------
``docs/CALIBRATION.md`` reports "type accuracy 100% vs 60%, direction 92% vs 72%"
for the LLM judge. Those numbers used to live *inside* ``score.py`` as a Python
literal - the parsed verdicts were hardcoded, and the original model responses
were never archived. That makes the table a **pilot observation**, not a
reproducible measurement: no key, no network, no re-run.

This module turns calibration into a measurement you can re-execute:

* :func:`run_calibration` calls any judge (``HttpJudge``, ``HeuristicJudge`` or
  :class:`ReplayJudge`) on a directory of filing texts, records the **raw model
  output**, the prompt version, model name, UTC timestamps and per-call latency,
  and then scores it against a human-labelled CSV.
* :class:`ReplayJudge` replays **recorded** responses from
  ``tests/fixtures/calibration/``. The fixture is lookup-by-fingerprint, never
  lookup-by-call-order, so replay is order-independent and idempotent; CI needs
  no API key and no network.
* The recorded fixture stores the raw text; the verdict is **re-derived** at
  replay time with the same :func:`medradar.llm.parse_verdict` the production
  path uses. No judgement is hardcoded in this file.

Honesty about the recording
---------------------------
The 25 English filings in the published calibration were judged by a DSH
sub-agent and only the *parsed* verdict (``docs/calibration/llm_verdicts.json``)
was archived - the raw chat-completions body was not. ``export_fixtures``
therefore reconstructs a minimal, valid model response from that parsed verdict
and labels it ``raw_source="reconstructed_from_parsed_verdict"`` in the fixture
manifest. It is enough to re-run the *scoring* pipeline end-to-end (that is what
the numbers depend on), but it is **not** a recording of the original string;
a true raw response requires re-running :class:`HttpJudgeRecorder` with
``MEDRADAR_LLM_API_KEY`` set. Every artefact carries this provenance so the
report cannot claim more than it has.

API
---
    read_labels(path) -> list[dict]
    filing_fingerprint(headline, text) -> str
    ReplayJudge.from_fixtures(fixtures_dir, suite="llm")
    run_calibration(filings_dir, labels_csv, judge, out_dir, ...) -> dict
    evaluate(records) -> dict          # pure scoring, unit-testable
    export_fixtures(filings_dir, labels_csv, verdicts_json, out_dir, ...) -> dict
    legacy_summary(metrics) -> dict    # {type_acc, dir_acc, ...} for old docs
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import stats
from .llm import (
    MAX_INPUT_CHARS,
    PROMPT_VERSION,
    HttpJudge,
    JudgeConfig,
    parse_verdict,
)
from .util import ensure_dir, read_json, read_text, sha1, utc_now_iso, write_json

CALIBRATION_VERSION = "calibration-v1"
HIGH_MATERIALITY = 0.5
DEFAULT_HEADLINE_TEMPLATE = "{company} 8-K"
CATALYST_LABELS = ("approval", "crl", "trial_result", "earnings")
DIRECTION_LABELS = (-1, 0, 1)
POSITION_MAX = 0.05
POSITION_FLOOR = 0.20

__all__ = [
    "CALIBRATION_VERSION",
    "HIGH_MATERIALITY",
    "DEFAULT_HEADLINE_TEMPLATE",
    "ReplayJudge",
    "ReplayMiss",
    "HttpJudgeRecorder",
    "read_labels",
    "filing_fingerprint",
    "headline_for",
    "call_judge",
    "confusion_matrix",
    "direction_confusion",
    "high_materiality_prf",
    "evaluate",
    "legacy_summary",
    "run_calibration",
    "export_fixtures",
]


# ---------------------------------------------------------------------- labels
def read_labels(path: str | Path) -> list[dict[str, Any]]:
    """Read the human labels CSV (``id,company,filed,gt_type,gt_direction,gt_materiality,gt_note``).

    Rows with a missing id or an unparsable ``gt_materiality`` are skipped loudly
    (recorded under ``"skipped"`` in the return of :func:`run_calibration`)?  No -
    here they raise, because a silently dropped label changes the denominator of
    every published accuracy. The caller decides what to do.
    """
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for line_no, raw in enumerate(csv.DictReader(handle), start=2):
            identifier = str(raw.get("id") or "").strip()
            if not identifier:
                continue
            try:
                materiality = float(raw.get("gt_materiality"))
                direction = int(float(raw.get("gt_direction")))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_no}: bad gt_materiality/gt_direction") from exc
            rows.append(
                {
                    "id": identifier,
                    "company": str(raw.get("company") or "").strip(),
                    "filed": str(raw.get("filed") or "").strip(),
                    "gt_type": str(raw.get("gt_type") or "").strip(),
                    "gt_direction": 1 if direction > 0 else (-1 if direction < 0 else 0),
                    "gt_materiality": min(1.0, max(0.0, materiality)),
                    "gt_note": str(raw.get("gt_note") or "").strip(),
                }
            )
    return rows


def filing_fingerprint(headline: str, text: str) -> str:
    """Stable content key for a filing under the production prompt.

    ``fingerprint = sha1(PROMPT_VERSION | headline | text[:MAX_INPUT_CHARS])``

    Deliberately mirrors the truncation used by :func:`medradar.llm.build_prompt`
    and the cache key in :class:`medradar.llm.CachedJudge`, but **excludes the
    model name**: the same filing may be judged by several models and each replay
    file is per-model anyway (``tests/fixtures/calibration/<suite>/``). This is
    the join key that makes replay order-independent.
    """
    return sha1(
        f"{PROMPT_VERSION}|{str(headline or '').strip()}|{(text or '')[:MAX_INPUT_CHARS]}"
    )


def headline_for(company: str, template: str = DEFAULT_HEADLINE_TEMPLATE) -> str:
    """Render the headline passed to the judge (documented, not implied)."""
    return str(template).format(company=str(company or "").strip() or "Unknown").strip()


# ---------------------------------------------------------------------- replay
class ReplayMiss(RuntimeError):
    """Raised when a filing has no recorded response (never fabricate a verdict)."""


class ReplayJudge:
    """Deterministic judge that replays recorded model responses from fixtures.

    Lookup is by :func:`filing_fingerprint`, so the same filing always maps to the
    same raw response regardless of call order, working directory or process.
    The verdict is re-derived from the raw string with ``parse_verdict`` at every
    call - the fixture stores evidence, not conclusions.

    Attributes
    ----------
    name: ``"replay:<suite>"`` - recorded in each verdict so a report can tell a
        replay run apart from a live endpoint run.
    calls / misses: counters for the manifest (misses raise, they are never
        counted as "other").
    """

    raw_source = "replay_recorded"

    def __init__(
        self,
        responses: Sequence[Mapping[str, Any]] | str | Path,
        *,
        suite: str = "replay",
        model: str = "",
        prompt_version: str = PROMPT_VERSION,
        recorded_at: str = "",
        source: str = "",
    ) -> None:
        entries = _load_response_entries(responses)
        self.entries: dict[str, dict[str, Any]] = {}
        for entry in entries:
            fingerprint = str(entry.get("fingerprint") or "")
            if not fingerprint:
                raise ValueError("replay entry without fingerprint")
            self.entries[fingerprint] = dict(entry)
        self.suite = str(suite)
        self.name = f"replay:{self.suite}"
        self.model = str(model)
        self.prompt_version = str(prompt_version)
        self.recorded_at = str(recorded_at)
        self.source = str(source)
        self.calls = 0
        self.misses = 0
        self.last_raw_source = self.raw_source

    # -- construction ------------------------------------------------------
    @classmethod
    def from_fixtures(cls, fixtures_dir: str | Path, suite: str = "llm") -> "ReplayJudge":
        """Load ``<fixtures>/<suite>/responses.json`` (+ ``manifest.json`` provenance)."""
        base = Path(fixtures_dir)
        payload = read_json(base / suite / "responses.json")
        if not payload:
            raise FileNotFoundError(f"no replay responses at {base / suite / 'responses.json'}")
        manifest = read_json(base / "manifest.json", {}) or {}
        info = (manifest.get("suites") or {}).get(suite, {})
        entries = payload.get("responses") if isinstance(payload, Mapping) else payload
        return cls(
            entries or [],
            suite=suite,
            model=str(info.get("model") or payload.get("model") or ""),
            prompt_version=str(info.get("prompt_version") or payload.get("prompt_version") or PROMPT_VERSION),
            recorded_at=str(info.get("recorded_at") or payload.get("recorded_at") or ""),
            source=str(info.get("source") or payload.get("source") or ""),
        )

    # -- judge protocol ----------------------------------------------------
    def covers(self, headline: str, text: str) -> bool:
        return filing_fingerprint(headline, text) in self.entries

    def judge_with_raw(self, headline: str, text: str) -> tuple[str, dict[str, Any]]:
        """Return ``(raw_response, verdict)``; raises :class:`ReplayMiss` if absent."""
        fingerprint = filing_fingerprint(headline, text)
        entry = self.entries.get(fingerprint)
        if entry is None:
            self.misses += 1
            raise ReplayMiss(
                f"no recorded response for fingerprint {fingerprint[:12]} "
                f"(suite={self.suite}); re-record with HttpJudgeRecorder"
            )
        self.calls += 1
        raw = str(entry.get("raw") or "")
        self.last_raw_source = str(entry.get("raw_source") or self.raw_source)
        verdict = dict(parse_verdict(raw))
        verdict["judge"] = self.name
        return raw, verdict

    def judge(self, headline: str, text: str) -> dict[str, Any]:
        _, verdict = self.judge_with_raw(headline, text)
        return verdict


def _load_response_entries(
    responses: Sequence[Mapping[str, Any]] | str | Path,
) -> list[dict[str, Any]]:
    if isinstance(responses, (str, Path)):
        payload = read_json(responses)
        if payload is None:
            raise FileNotFoundError(f"cannot read replay responses: {responses}")
        entries = payload.get("responses") if isinstance(payload, Mapping) else payload
        return [dict(entry) for entry in (entries or [])]
    return [dict(entry) for entry in responses]


class HttpJudgeRecorder(HttpJudge):
    """``HttpJudge`` that also returns the raw chat-completions content.

    ``medradar/llm.py`` deliberately keeps only the parsed verdict, and the
    calibration harness must not fork the production parser. We therefore let the
    real request run and temporarily swap the module-level ``parse_verdict`` for a
    spy that stores its argument. The parser itself is the production one, so a
    prompt/schema change in ``llm.py`` is picked up automatically.

    Not thread-safe (module-global swap); the calibration loop is single-threaded
    by design so that timings and ordering are reproducible.
    """

    raw_source = "http_chat_completions_content"

    def __init__(self, config: JudgeConfig) -> None:
        super().__init__(config)
        self.model = config.model
        self.name = f"http:{config.model}"
        self.last_raw_source = self.raw_source

    def judge_with_raw(self, headline: str, text: str) -> tuple[str, dict[str, Any]]:
        from . import llm as llm_module

        captured: dict[str, str] = {}
        original = llm_module.parse_verdict

        def spy(raw: str):  # type: ignore[no-untyped-def]
            captured["raw"] = raw
            return original(raw)

        llm_module.parse_verdict = spy  # type: ignore[assignment]
        try:
            verdict = super().judge(headline, text)
        finally:
            llm_module.parse_verdict = original  # type: ignore[assignment]
        return captured.get("raw", ""), verdict


def call_judge(
    judge: Any, headline: str, text: str
) -> tuple[dict[str, Any], str, str]:
    """Call any judge and return ``(verdict, raw_response, raw_source)``.

    A judge that only implements ``judge()`` (e.g. a bare callable judge or the
    production :class:`medradar.llm.HeuristicJudge`) cannot expose the model
    string, so the raw body is recorded as the canonical JSON of the validated
    verdict and flagged ``"verdict_json_reserialised"``. That keeps the artefact
    honest: the file says what it is.
    """
    method = getattr(judge, "judge_with_raw", None)
    if callable(method):
        raw, verdict = method(headline, text)
        source = getattr(judge, "last_raw_source", None) or getattr(
            judge, "raw_source", "judge_with_raw"
        )
        return verdict, str(raw or ""), str(source)
    verdict = judge.judge(headline, text)
    raw = json.dumps(verdict, ensure_ascii=False, sort_keys=True)
    return verdict, raw, "verdict_json_reserialised"


# -------------------------------------------------------------------- scoring
def confusion_matrix(
    truth: Sequence[str], prediction: Sequence[str], labels: Sequence[str]
) -> dict[str, Any]:
    """Type confusion matrix (rows = human truth, cols = judge) + per-label P/R/F1.

    ``precision = tp / (tp + fp)``, ``recall = tp / (tp + fn)``,
    ``f1 = 2pr / (p + r)``; undefined ratios are ``None`` (never ``0.0`` silently,
    which would read as "wrong" instead of "no examples").
    """
    if len(truth) != len(prediction):
        raise ValueError("truth and prediction must align")
    label_list = [str(label) for label in labels]
    index = {label: i for i, label in enumerate(label_list)}
    matrix = [[0 for _ in label_list] for _ in label_list]
    for true_label, predicted in zip(truth, prediction):
        if true_label in index and predicted in index:
            matrix[index[true_label]][index[predicted]] += 1
    total = sum(sum(row) for row in matrix)
    correct = sum(matrix[i][i] for i in range(len(label_list)))
    by_label: dict[str, dict[str, Any]] = {}
    for i, label in enumerate(label_list):
        tp = matrix[i][i]
        support = sum(matrix[i])
        predicted_n = sum(matrix[r][i] for r in range(len(label_list)))
        fp = predicted_n - tp
        fn = support - tp
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and (precision + recall)
            else None
        )
        by_label[label] = {
            "support": support,
            "predicted": predicted_n,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return {
        "labels": label_list,
        "matrix": matrix,
        "by_label": by_label,
        "n": total,
        "correct": correct,
        "accuracy": (correct / total) if total else None,
    }


def direction_confusion(
    truth: Sequence[int], prediction: Sequence[int]
) -> dict[str, Any]:
    """Direction confusion matrix over ``{-1, 0, +1}`` with accuracy."""
    labels = list(DIRECTION_LABELS)
    index = {label: i for i, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    correct = 0
    for true_value, predicted in zip(truth, prediction):
        if true_value not in index or predicted not in index:
            continue
        matrix[index[true_value]][index[predicted]] += 1
        if true_value == predicted:
            correct += 1
    total = sum(sum(row) for row in matrix)
    return {
        "labels": labels,
        "matrix": matrix,
        "n": total,
        "correct": correct,
        "accuracy": (correct / total) if total else None,
    }


def high_materiality_prf(
    truth: Sequence[float],
    prediction: Sequence[float],
    threshold: float = HIGH_MATERIALITY,
) -> dict[str, Any]:
    """Binary P/R/F1 for "material enough to size a position" (>= threshold).

    Classification, not ranking: it answers "would we have traded this?", which
    is the operational question behind the rubric's 0.5 anchor.
    """
    if len(truth) != len(prediction):
        raise ValueError("truth and prediction must align")
    tp = fp = fn = tn = 0
    for true_value, predicted in zip(truth, prediction):
        real = true_value >= threshold
        guess = predicted >= threshold
        if real and guess:
            tp += 1
        elif guess and not real:
            fp += 1
        elif real and not guess:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall)
        else None
    )
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "support": sum(1 for value in truth if value >= threshold),
        "predicted": sum(1 for value in prediction if value >= threshold),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _position(materiality: float) -> float:
    """Position size implied by the live rule: ``5% * clamp(materiality, 20%, 100%)``."""
    return POSITION_MAX * _clamp(materiality, POSITION_FLOOR, 1.0)


def evaluate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Score per-filing records into the calibration metrics table (pure function).

    ``records`` are the rows produced by :func:`run_calibration`: each needs the
    human label fields (``gt_type`` / ``gt_direction`` / ``gt_materiality``) and a
    ``verdict`` dict (or an ``error`` string). Records without a usable verdict
    are excluded from every ratio and counted in ``meta`` - the denominator is
    never silently shrunk.

    Emitted blocks: ``type`` (confusion + accuracy + per-label P/R/F1),
    ``direction`` (confusion + accuracy), ``materiality`` (Spearman / Pearson /
    MAE / RMSE / bias), ``high_materiality`` (P/R/F1 at 0.5), ``sizing`` (the
    position-size implication per true type) and ``per_filing`` (audit table).
    """
    usable = [
        record
        for record in records
        if record.get("verdict") and not record.get("error")
    ]
    errors = [
        {"id": str(record.get("id") or ""), "error": str(record.get("error"))}
        for record in records
        if record.get("error")
    ]
    payload: dict[str, Any] = {
        "status": "ok" if usable else "insufficient_data",
        "n": len(usable),
        "n_total": len(records),
        "n_errors": len(errors),
        "errors": errors,
        "high_materiality_threshold": HIGH_MATERIALITY,
    }
    if not usable:
        payload["reason"] = "no_usable_verdicts"
        return payload

    truth_type = [str(record["gt_type"]) for record in usable]
    pred_type = [str(record["verdict"].get("catalyst_type") or "other") for record in usable]
    truth_dir = [int(record["gt_direction"]) for record in usable]
    pred_dir = [int(record["verdict"].get("direction") or 0) for record in usable]
    truth_mat = [float(record["gt_materiality"]) for record in usable]
    pred_mat = [float(record["verdict"].get("materiality") or 0.0) for record in usable]

    present = set(truth_type) | set(pred_type)
    labels = [label for label in CATALYST_LABELS if label in present]
    labels += sorted(present - set(labels))
    payload["type"] = confusion_matrix(truth_type, pred_type, labels)
    payload["direction"] = direction_confusion(truth_dir, pred_dir)
    payload["direction"]["accuracy_sign"] = payload["direction"]["accuracy"]

    predicted_minus_truth = [p - t for t, p in zip(truth_mat, pred_mat)]
    payload["materiality"] = {
        "n": len(truth_mat),
        "spearman": stats.spearman(truth_mat, pred_mat),
        "pearson": stats.pearson(truth_mat, pred_mat),
        "mae": stats.mae(truth_mat, pred_mat),
        "rmse": (
            (sum(value * value for value in predicted_minus_truth) / len(predicted_minus_truth)) ** 0.5
            if predicted_minus_truth
            else None
        ),
        "bias": (
            sum(predicted_minus_truth) / len(predicted_minus_truth)
            if predicted_minus_truth
            else None
        ),
        "note_zh": "bias > 0 表示判定系统性高估材料性（历史上约 +0.15）。",
    }
    payload["high_materiality"] = high_materiality_prf(truth_mat, pred_mat)

    by_true_type: dict[str, dict[str, Any]] = {}
    for label in sorted(set(truth_type)):
        members = [
            index for index, value in enumerate(truth_type) if value == label
        ]
        if not members:
            continue
        gt_mean = sum(truth_mat[index] for index in members) / len(members)
        pred_mean = sum(pred_mat[index] for index in members) / len(members)
        by_true_type[label] = {
            "n": len(members),
            "gt_position_pct": 100.0 * _position(gt_mean),
            "pred_position_pct": 100.0 * _position(pred_mean),
            "delta_pct": 100.0 * (_position(pred_mean) - _position(gt_mean)),
        }
    payload["sizing"] = {
        "rule": f"{POSITION_MAX:.0%} x clamp(materiality, {POSITION_FLOOR:.0%}, 100%)",
        "by_true_type": by_true_type,
        "note_zh": "材料性误差如何变成仓位误差：批准/CRL/试验应与财报拉开差距。",
    }

    per_filing: list[dict[str, Any]] = []
    for record in usable:
        verdict = record["verdict"]
        type_ok = str(record["gt_type"]) == str(verdict.get("catalyst_type"))
        direction_ok = int(record["gt_direction"]) == int(verdict.get("direction") or 0)
        per_filing.append(
            {
                "id": str(record.get("id") or ""),
                "company": str(record.get("company") or ""),
                "filed": str(record.get("filed") or ""),
                "gt_type": str(record["gt_type"]),
                "gt_direction": int(record["gt_direction"]),
                "gt_materiality": float(record["gt_materiality"]),
                "pred_type": str(verdict.get("catalyst_type") or ""),
                "pred_direction": int(verdict.get("direction") or 0),
                "pred_materiality": float(verdict.get("materiality") or 0.0),
                "pred_confidence": float(verdict.get("confidence") or 0.0),
                "type_ok": type_ok,
                "direction_ok": direction_ok,
                "materiality_error": float(verdict.get("materiality") or 0.0)
                - float(record["gt_materiality"]),
                "raw_source": str(record.get("raw_source") or ""),
                "elapsed_ms": record.get("elapsed_ms"),
                "started_at": record.get("started_at"),
                "judge": str(verdict.get("judge") or ""),
            }
        )
    payload["per_filing"] = per_filing
    payload["meta"] = {
        "calibration_version": CALIBRATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "high_materiality_threshold": HIGH_MATERIALITY,
        "n_usable": len(usable),
        "n_total": len(records),
        "n_errors": len(errors),
        "note_zh": (
            "所有比率的分母都是 n_usable；错误/缺失文件单独计数，绝不静默缩小分母。"
        ),
    }
    return payload


def legacy_summary(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Map :func:`evaluate` output onto the flat keys used by ``docs/CALIBRATION.md``.

    Keeps the published table reproducible without teaching the report a second
    vocabulary: ``type_acc`` / ``dir_acc`` / ``spearman`` / ``mae`` / ``hi_p`` /
    ``hi_r`` / ``hi_f1``.
    """
    type_block = metrics.get("type") or {}
    direction_block = metrics.get("direction") or {}
    materiality = metrics.get("materiality") or {}
    high = metrics.get("high_materiality") or {}
    return {
        "type_acc": type_block.get("accuracy"),
        "dir_acc": direction_block.get("accuracy"),
        "dir_acc_sign": direction_block.get("accuracy_sign", direction_block.get("accuracy")),
        "spearman": materiality.get("spearman"),
        "pearson": materiality.get("pearson"),
        "mae": materiality.get("mae"),
        "rmse": materiality.get("rmse"),
        "bias": materiality.get("bias"),
        "hi_p": high.get("precision"),
        "hi_r": high.get("recall"),
        "hi_f1": high.get("f1"),
        "n": metrics.get("n"),
    }


# ------------------------------------------------------------------ execution
def _filing_path(filings_dir: Path, identifier: str) -> Path | None:
    for suffix in (".txt", ".md", ".html", ".htm", ""):
        candidate = filings_dir / f"{identifier}{suffix}"
        if suffix and candidate.exists():
            return candidate
    direct = filings_dir / identifier
    return direct if direct.exists() else None


_VOLATILE_METRIC_KEYS = ("generated_at", "elapsed_ms", "total_elapsed_ms", "started_at")


def _stable_metrics_payload(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Strip wall-clock fields so a re-run hashes identically."""
    payload = json.loads(json.dumps(metrics, ensure_ascii=False, default=str))
    for key in _VOLATILE_METRIC_KEYS:
        payload.pop(key, None)
    meta = payload.get("meta")
    if isinstance(meta, dict):
        for key in _VOLATILE_METRIC_KEYS:
            meta.pop(key, None)
    for row in payload.get("per_filing") or []:
        if isinstance(row, dict):
            for key in _VOLATILE_METRIC_KEYS:
                row.pop(key, None)
    return payload


def metrics_sha1(metrics: Mapping[str, Any]) -> str:
    """Hash of the timing-free metrics - the reproducibility fingerprint."""
    canonical = json.dumps(
        _stable_metrics_payload(metrics), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha1(canonical)


def run_calibration(
    filings_dir: str | Path,
    labels_csv: str | Path,
    judge: Any,
    out_dir: str | Path,
    *,
    headline_template: str = DEFAULT_HEADLINE_TEMPLATE,
    max_files: int = 0,
) -> dict[str, Any]:
    """Judge every labelled filing, archive raw responses, and score the judge.

    Parameters
    ----------
    filings_dir:
        Directory of filing texts named ``<id>.txt`` (the id from the labels CSV).
    labels_csv:
        Human labels (see :func:`read_labels`). The CSV is the only source of
        ground truth; nothing is hardcoded.
    judge:
        Anything with ``judge(headline, text) -> verdict``: :class:`HttpJudgeRecorder`
        for a live endpoint, :class:`ReplayJudge` for recorded responses, or
        ``medradar.llm.HeuristicJudge`` for the keyword baseline.
    out_dir:
        Where artefacts are written: ``verdicts.jsonl`` (one line per filing with
        the raw response + metadata), ``raw_responses/<id>.txt`` (the exact raw
        string), ``metrics.json`` and ``manifest.json`` (provenance).

    Returns a dict with the metrics, per-file paths and a reproducibility hash
    (``metrics_sha1``) that excludes timestamps - running the same fixtures twice
    yields the same hash, which is how the test suite proves idempotency.
    """
    started = time.perf_counter()
    out = ensure_dir(out_dir)
    raw_dir = ensure_dir(out / "raw_responses")
    filings = Path(filings_dir)
    labels = read_labels(labels_csv)
    if max_files and max_files > 0:
        labels = labels[: int(max_files)]

    records: list[dict[str, Any]] = []
    for label in labels:
        identifier = label["id"]
        headline = headline_for(label["company"], headline_template)
        record: dict[str, Any] = {
            **label,
            "headline": headline,
            "verdict": None,
            "raw_response": "",
            "raw_source": "",
            "started_at": utc_now_iso(),
            "elapsed_ms": None,
            "error": None,
            "filing_path": None,
            "filing_sha1": None,
            "chars": 0,
            "fingerprint": None,
        }
        path = _filing_path(filings, identifier)
        if path is None:
            record["error"] = "missing_filing"
        else:
            text = read_text(path)
            record["filing_path"] = str(path)
            record["filing_sha1"] = sha1(text)
            record["chars"] = len(text)
            record["fingerprint"] = filing_fingerprint(headline, text)
            call_started = time.perf_counter()
            try:
                verdict, raw, raw_source = call_judge(judge, headline, text)
                record["verdict"] = verdict
                record["raw_response"] = raw
                record["raw_source"] = raw_source
            except Exception as exc:  # a broken call must be visible, not fatal
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["elapsed_ms"] = round((time.perf_counter() - call_started) * 1000.0, 3)
            if record["raw_response"]:
                (raw_dir / f"{identifier}.txt").write_text(
                    record["raw_response"], encoding="utf-8"
                )
        records.append(record)

    metrics = evaluate(records)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    metrics["meta"] = {
        **(metrics.get("meta") or {}),
        "generated_at": utc_now_iso(),
        "judge": str(getattr(judge, "name", type(judge).__name__)),
        "model": str(getattr(judge, "model", "")),
        "prompt_version": PROMPT_VERSION,
        "total_elapsed_ms": elapsed_ms,
    }
    stable_digest = metrics_sha1(metrics)

    manifest = {
        "schema": CALIBRATION_VERSION,
        "generated_at": utc_now_iso(),
        "judge": str(getattr(judge, "name", type(judge).__name__)),
        "model": str(getattr(judge, "model", "")),
        "prompt_version": PROMPT_VERSION,
        "headline_template": headline_template,
        "labels_csv": {
            "path": str(Path(labels_csv)),
            "sha1": sha1(Path(labels_csv).read_text(encoding="utf-8-sig")),
            "n": len(labels),
        },
        "filings_dir": str(filings),
        "replay": (
            {
                "suite": getattr(judge, "suite", ""),
                "recorded_at": getattr(judge, "recorded_at", ""),
                "source": getattr(judge, "source", ""),
            }
            if isinstance(judge, ReplayJudge)
            else None
        ),
        "n_records": len(records),
        "n_usable": metrics.get("n", 0),
        "n_errors": metrics.get("n_errors", 0),
        "metrics_sha1": stable_digest,
        "elapsed_ms": elapsed_ms,
        "python_version": sys.version.split()[0],
        "inputs": [
            {
                "id": record["id"],
                "filing_path": record["filing_path"],
                "filing_sha1": record["filing_sha1"],
                "fingerprint": record["fingerprint"],
                "raw_source": record["raw_source"],
                "error": record["error"],
            }
            for record in records
        ],
    }

    verdicts_path = out / "verdicts.jsonl"
    with verdicts_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    write_json(out / "metrics.json", metrics)
    write_json(out / "manifest.json", manifest)

    return {
        "status": metrics.get("status"),
        "out_dir": str(out),
        "n": metrics.get("n", 0),
        "n_total": len(records),
        "n_errors": metrics.get("n_errors", 0),
        "metrics": metrics,
        "manifest": manifest,
        "metrics_sha1": stable_digest,
        "paths": {
            "metrics": str(out / "metrics.json"),
            "manifest": str(out / "manifest.json"),
            "verdicts": str(verdicts_path),
            "raw_responses": str(raw_dir),
        },
        "elapsed_ms": elapsed_ms,
    }


# ------------------------------------------------------------------- fixtures
def export_fixtures(
    filings_dir: str | Path,
    labels_csv: str | Path,
    verdicts_json: str | Path,
    out_dir: str | Path,
    *,
    suite: str = "llm",
    model: str = "deepseek-chat",
    prompt_version: str = PROMPT_VERSION,
    source_note: str = "",
    recording_date: str = "",
    headline_template: str = DEFAULT_HEADLINE_TEMPLATE,
    copy_filings: bool = True,
) -> dict[str, Any]:
    """Freeze existing parsed verdicts into a replay fixture (with provenance).

    The archive format is::

        <out>/manifest.json                 # provenance: source, model, dates, honest raw_source
        <out>/filings/<id>.txt              # filing texts, so the replay is self-contained
        <out>/<suite>/responses.json        # fingerprint -> raw response + audit fields

    ``verdicts_json`` accepts the two shapes this repo already has: a mapping of
    ``{"<id>": {"direction": 1, ...}}`` (``docs/calibration/llm_verdicts.json``)
    or a list of dicts with ``id`` (``docs/calibration/heuristic_verdicts.json``).

    The ``raw`` field is rebuilt as a minimal, valid model-style JSON object from
    the archived parsed verdict - the original chat string was not kept. The
    manifest says so in ``raw_source``; do not cite this fixture as evidence that
    the endpoint was re-validated.
    """
    out = ensure_dir(out_dir)
    filings_root = Path(filings_dir)
    labels = read_labels(labels_csv)
    archived = _load_archived_verdicts(verdicts_json)

    if copy_filings:
        target = ensure_dir(out / "filings")
        for label in labels:
            source = _filing_path(filings_root, label["id"])
            if source is not None:
                (target / f"{label['id']}.txt").write_text(
                    read_text(source), encoding="utf-8"
                )

    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for label in labels:
        identifier = label["id"]
        verdict = archived.get(identifier)
        if not verdict:
            missing.append(identifier)
            continue
        source = _filing_path(filings_root, identifier)
        if source is None:
            missing.append(identifier)
            continue
        text = read_text(source)
        headline = headline_for(label["company"], headline_template)
        raw_verdict = {
            "direction": int(verdict.get("direction") or 0),
            "materiality": float(verdict.get("materiality") or 0.0),
            "catalyst_type": str(verdict.get("catalyst_type") or "other"),
            "confidence": float(verdict.get("confidence") or 0.0),
            "is_pivotal": bool(verdict.get("is_pivotal", False)),
            "asset": str(verdict.get("asset") or ""),
            "indication": str(verdict.get("indication") or ""),
            "revenue_relevance": str(verdict.get("revenue_relevance") or "unknown"),
            "evidence_quotes": list(verdict.get("evidence_quotes") or []),
            "rationale_zh": str(verdict.get("rationale_zh") or ""),
        }
        entries.append(
            {
                "id": identifier,
                "company": label["company"],
                "filed": label["filed"],
                "headline": headline,
                "fingerprint": filing_fingerprint(headline, text),
                "filing_sha1": sha1(text),
                "raw": json.dumps(raw_verdict, ensure_ascii=False),
                "raw_source": "reconstructed_from_parsed_verdict",
                "recorded_verdict": {
                    "direction": int(verdict.get("direction") or 0),
                    "materiality": float(verdict.get("materiality") or 0.0),
                    "catalyst_type": str(verdict.get("catalyst_type") or "other"),
                },
                "recorded_at": str(recording_date or ""),
                "judge": str(verdict.get("judge") or suite),
            }
        )
    entries.sort(key=lambda item: item["id"])

    suite_dir = ensure_dir(out / suite)
    payload = {
        "schema": "replay-fixture-v1",
        "suite": suite,
        "model": model,
        "prompt_version": prompt_version,
        "headline_template": headline_template,
        "recorded_at": str(recording_date or ""),
        "exported_at": utc_now_iso(),
        "source": str(source_note or str(verdicts_json)),
        "raw_source": "reconstructed_from_parsed_verdict",
        "responses": entries,
    }
    write_json(suite_dir / "responses.json", payload)

    manifest_path = out / "manifest.json"
    manifest = read_json(manifest_path, {}) or {}
    verdict_source = {
        "path": str(Path(verdicts_json)),
        "sha1": sha1(Path(verdicts_json).read_text(encoding="utf-8")),
    }
    manifest.update(
        {
            "schema": "calibration-fixtures-v1",
            "exported_at": utc_now_iso(),
            "note_zh": (
                "回放 fixture：原始响应未留档，raw 字段由已解析的判定重建，"
                "只用于复现打分流程；不构成对端点的独立验证。"
            ),
            "note_en": (
                "Replay fixture. The original model string was not archived; `raw` is "
                "rebuilt from the parsed verdict. It reproduces the scoring pipeline, "
                "not the endpoint."
            ),
            "labels_csv": {
                "path": str(Path(labels_csv)),
                "sha1": sha1(Path(labels_csv).read_text(encoding="utf-8-sig")),
            },
        }
    )
    verdict_sources = manifest.get("verdicts_sources") or {}
    verdict_sources[suite] = verdict_source
    manifest["verdicts_sources"] = verdict_sources
    suites = manifest.get("suites") or {}
    suites[suite] = {
        "model": model,
        "prompt_version": prompt_version,
        "recorded_at": str(recording_date or ""),
        "recorded_at_note": (
            "日期取自判定归档文件的写入时间；原始 LLM 调用日期未归档。"
            if recording_date
            else "未提供录制日期。"
        ),
        "source": str(source_note or str(verdicts_json)),
        "verdicts_source": verdict_source,
        "raw_source": "reconstructed_from_parsed_verdict",
        "n": len(entries),
        "path": f"{suite}/responses.json",
    }
    manifest["suites"] = suites
    write_json(manifest_path, manifest)
    return {
        "suite": suite,
        "out_dir": str(out),
        "n": len(entries),
        "missing": missing,
        "path": str(suite_dir / "responses.json"),
        "manifest": str(manifest_path),
    }


def _load_archived_verdicts(path: str | Path) -> dict[str, dict[str, Any]]:
    payload = read_json(path)
    if payload is None:
        raise FileNotFoundError(f"cannot read archived verdicts: {path}")
    if isinstance(payload, Mapping):
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, Mapping)}
    archived: dict[str, dict[str, Any]] = {}
    for entry in payload or []:
        if not isinstance(entry, Mapping):
            continue
        identifier = str(entry.get("id") or "").strip()
        if identifier:
            archived[identifier] = dict(entry)
    return archived


# ------------------------------------------------------------------------ CLI
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m medradar.calibration",
        description="Reproducible 8-K judge calibration (record, replay, score).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="score a judge on labelled filings")
    run.add_argument("--filings", required=True, help="directory with <id>.txt filing texts")
    run.add_argument("--labels", required=True, help="ground_truth.csv")
    run.add_argument("--out", required=True, help="output directory")
    run.add_argument("--judge", default="replay", choices=("replay", "http", "heuristic"))
    run.add_argument("--fixtures", default="tests/fixtures/calibration", help="replay fixture root")
    run.add_argument("--suite", default="llm", help="replay suite name (llm / heuristic)")
    run.add_argument("--headline-template", default=DEFAULT_HEADLINE_TEMPLATE)
    run.add_argument("--max-files", type=int, default=0)

    export = sub.add_parser("export-fixtures", help="freeze archived verdicts into a replay fixture")
    export.add_argument("--filings", required=True)
    export.add_argument("--labels", required=True)
    export.add_argument("--verdicts", required=True, help="parsed verdicts JSON to archive")
    export.add_argument("--out", required=True, help="fixture root (tests/fixtures/calibration)")
    export.add_argument("--suite", default="llm")
    export.add_argument("--model", default="deepseek-chat")
    export.add_argument("--recording-date", default="")
    export.add_argument("--source-note", default="")
    export.add_argument("--headline-template", default=DEFAULT_HEADLINE_TEMPLATE)
    export.add_argument("--no-copy-filings", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "export-fixtures":
        result = export_fixtures(
            args.filings,
            args.labels,
            args.verdicts,
            args.out,
            suite=args.suite,
            model=args.model,
            source_note=args.source_note,
            recording_date=args.recording_date,
            headline_template=args.headline_template,
            copy_filings=not args.no_copy_filings,
        )
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    if args.judge == "replay":
        judge: Any = ReplayJudge.from_fixtures(args.fixtures, suite=args.suite)
    elif args.judge == "http":
        config = JudgeConfig.from_env()
        if not config.enabled:
            print("MEDRADAR_LLM_API_KEY is not set; cannot run a live calibration", file=sys.stderr)
            return 2
        judge = HttpJudgeRecorder(config)
    else:
        from .llm import HeuristicJudge

        judge = HeuristicJudge()

    result = run_calibration(
        args.filings,
        args.labels,
        judge,
        args.out,
        headline_template=args.headline_template,
        max_files=args.max_files,
    )
    summary = legacy_summary(result["metrics"])
    print(
        f"[{result['manifest']['judge']}] n={result['n']}/{result['n_total']} "
        f"type_acc={_fmt(summary['type_acc'])} dir_acc={_fmt(summary['dir_acc'])} "
        f"spearman={_fmt(summary['spearman'])} mae={_fmt(summary['mae'])} "
        f"hiP={_fmt(summary['hi_p'])} hiR={_fmt(summary['hi_r'])} hiF1={_fmt(summary['hi_f1'])}"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "out_dir": result["out_dir"],
                "metrics_sha1": result["metrics_sha1"],
                "n_errors": result["n_errors"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0 if result["status"] == "ok" else 1


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
