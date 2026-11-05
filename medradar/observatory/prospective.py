"""Frozen Prospective Observation Registry — the auditable Research Lab instrument.

What this module *is*
---------------------
A registry that freezes a scientific hypothesis **before** its outcome is
observable, together with a provable record of the evidence that existed at that
instant, and later reports the outcome after the declared window has closed.

It is deliberately **not** a prediction engine:

* it produces no probability, no score, no calibration and no accuracy claim;
* it never rewrites a frozen document.  ``freeze()`` writes one JSON file with
  exclusive-create semantics; every later mutation (an evaluation, a retraction)
  is a **new immutable appendix file** that references the frozen document's
  content hash;
* the frozen evidence snapshot is the ledger's own point-in-time view
  (``ledger.snapshot(freeze_at)``), so a record discovered *after* the freeze can
  never leak into the inputs — even if its ``event_at`` is older;
* an evaluation is refused while ``now < window_end`` (``status="NOT_DUE"``);
  nothing is ever fabricated to make an entry look matured;
* outcome counting separates (a) the evidence that existed at freeze (inputs)
  from (b) observations *first seen* inside the declared window after the freeze
  (candidate outcomes).  The registry does not decide whether the declared target
  event happened — it lists the candidate evidence and records that a human
  classification against the frozen criteria is still required;
* a ``synthetic`` entry is a test fixture.  Its ``label_zh``/``note_zh`` are
  forced to carry ``合成测试`` and it must never be presented as a real
  prospective result.

On-disk layout (under the writable data home, ``data/`` is git-ignored)::

    <registry_dir>/entries/<entry_id>.json                    # frozen core, write-once
    <registry_dir>/entries/<entry_id>.evaluation.<n>.json     # append-only appendix
    <registry_dir>/entries/<entry_id>.status.<n>.json         # append-only status appendix

``<registry_dir>`` resolves ``MEDRADAR_PROSPECTIVE_DIR`` env → ``$DATA_DIR/prospective``.

Status vocabulary (the *effective* status is derived, never written back)
-------------------------------------------------------------------------
``EXPERIMENTAL``  default at freeze / before the declared window opens — the
                  honest "unvalidated" label this instrument exists to keep.
``ACTIVE``        frozen and the declared observation window is open.
``DUE``           the window has ended but no evaluation has been appended yet.
``MATURED``       the window ended and an evaluation appendix exists.
``RETRACTED``     a status appendix withdrew the entry (reason required).

The frozen document stores the *declared* status (``EXPERIMENTAL``); the
effective status is computed from the window, the append-only history and the
current clock, so a reader can always re-derive it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..config import DATA_DIR
from .ledger import ObservationLedger, open_ledger_readonly
from .records import (
    ENTITY_MAPPED,
    TRACK_MAPPED,
    canonical_json,
    utc_now_iso,
)

SCHEMA_VERSION = "prospective-registry-v1"
ENTRY_SCHEMA = "medradar-prospective-entry-1"
EVALUATION_SCHEMA = "medradar-prospective-evaluation-1"
STATUS_SCHEMA = "medradar-prospective-status-1"

#: Env override for the registry root (tests / CI use a throwaway directory).
DIRECTORY_ENV = "MEDRADAR_PROSPECTIVE_DIR"
ENTRIES_SUBDIR = "entries"
DEFAULT_DIR_RELATIVE = Path("prospective")

#: Marker every synthetic fixture must carry in its label and note.
SYNTHETIC_MARKER = "合成测试"

STATUS_EXPERIMENTAL = "EXPERIMENTAL"
STATUS_ACTIVE = "ACTIVE"
STATUS_DUE = "DUE"
STATUS_MATURED = "MATURED"
STATUS_RETRACTED = "RETRACTED"

STATUSES = (
    STATUS_EXPERIMENTAL,
    STATUS_ACTIVE,
    STATUS_DUE,
    STATUS_MATURED,
    STATUS_RETRACTED,
)

STATUS_LABELS_ZH = {
    STATUS_EXPERIMENTAL: "实验性（未验证）",
    STATUS_ACTIVE: "观察窗口进行中",
    STATUS_DUE: "窗口已结束，待评估",
    STATUS_MATURED: "已到期并完成评估",
    STATUS_RETRACTED: "已撤回",
}

STATUS_NOTES_ZH = {
    STATUS_EXPERIMENTAL: "冻结后的默认状态：尚未进入声明窗口，任何结论都未验证。",
    STATUS_ACTIVE: "假设已冻结，声明的观察窗口仍在进行，不得提前计算结局。",
    STATUS_DUE: "声明窗口已结束，但尚未追加评估附录。",
    STATUS_MATURED: "窗口结束且已按冻结时声明的判据追加评估附录；这不等于已校准或已验证。",
    STATUS_RETRACTED: "研究者已撤回该条目；撤回原因保存在状态附录中。",
}

#: Honesty statements shipped with every frozen document.
FROZEN_POLICY_ZH = [
    "冻结文档只写入一次；此后对状态或评估的任何变更都是新的附录文件，不修改冻结正文。",
    "冻结证据来自观察账本在 freeze_at 时点的只读视图（first_seen_at <= freeze_at 且版本 captured_at <= freeze_at）；之后才发现的历史记录不进入冻结输入。",
    "本登记器不产生预测、不做校准、不宣称已验证；条目在人工按声明判据判定前只是待验证的前瞻观察。",
    "缺失的时间保持为空，不做插补；窗口结束后才发现的记录不计入窗口内结局。",
]

#: Honesty statements shipped with every evaluation appendix.
EVALUATION_HONESTY_ZH = [
    "这是按冻结时声明的时间窗口与判据统计的观察结果，不是预测，也不是校准误差。",
    "结局只统计冻结之后、窗口内首次观察到的候选证据；登记器不自动判定目标事件是否发生。",
    "冻结输入的内容哈希与冻结文档哈希一并记录；冻结正文一旦被改写，评估会被拒绝。",
]

_ENTRY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_APPENDIX_RE = re.compile(r"^(?P<entry>.+)\.(?P<kind>evaluation|status)\.(?P<seq>\d+)\.json$")

#: Keys a freeze() caller may supply (aliases included; unknown keys are rejected
#: so a typo cannot silently widen the frozen protocol).
_ALLOWED_ENTRY_KEYS = frozenset(
    {
        "entry_id",
        "label_zh",
        "hypothesis",
        "hypothesis_zh",
        "target_event",
        "target_event_definition_zh",
        "target_event_type",
        "baseline",
        "baseline_zh",
        "evaluation_criteria",
        "evaluation_criteria_zh",
        "window_start",
        "window_end",
        "scope",
        "synthetic",
        "note_zh",
        "freeze_at",
    }
)

#: Reserved keys a caller must never supply: they are derived by the registry.
_RESERVED_ENTRY_KEYS = frozenset(
    {"status", "content_sha256", "frozen_recorded_at", "evidence", "schema", "schema_version"}
)


# ---------------------------------------------------------------------- errors
class ProspectiveRegistryError(RuntimeError):
    """Base error for the prospective observation registry."""


class EntryValidationError(ValueError):
    """A freeze/evaluation input failed validation (HTTP 400 in the API layer)."""


class FrozenDocumentConflict(ProspectiveRegistryError):
    """A freeze/evaluation would rewrite a frozen, append-only document."""


class FrozenDocumentTampered(ProspectiveRegistryError):
    """A frozen document no longer matches its recorded content hash."""


class FrozenDocumentCorrupt(ValueError):
    """A frozen document on disk is not valid JSON (HTTP 400 in the API layer)."""


# ------------------------------------------------------------------- path setup
def default_registry_dir() -> Path:
    """Writable registry root: env override → ``$DATA_DIR/prospective``."""
    override = os.environ.get(DIRECTORY_ENV)
    if override:
        return Path(override).expanduser()
    return Path(DATA_DIR) / DEFAULT_DIR_RELATIVE


# --------------------------------------------------------------------- helpers
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def document_hash(document: Mapping[str, Any]) -> str:
    """Content hash of a document, excluding the hash field itself."""
    body = {key: value for key, value in document.items() if key != "content_sha256"}
    return sha256_text(canonical_json(body))


def protocol_hash(document: Mapping[str, Any]) -> str:
    """Hash of the *scientific protocol* (frozen body without append-time context).

    Excluded from the comparison (they are honest context, not protocol):

    * ``frozen_recorded_at`` — the real wall-clock moment the file was written;
    * ``evidence.excluded_discovered_later`` — how many ledger rows had been
      discovered *after* ``freeze_at`` when the file was written.  It changes as
      the ledger grows, while the point-in-time evidence items themselves cannot.

    A re-freeze of the identical protocol therefore stays an idempotent duplicate
    even after later ledger writes, while a changed hypothesis/window/evidence
    still hashes differently and is refused.
    """
    body = {
        key: value
        for key, value in document.items()
        if key not in ("content_sha256", "frozen_recorded_at")
    }
    evidence = body.get("evidence")
    if isinstance(evidence, Mapping):
        body["evidence"] = {
            key: value
            for key, value in evidence.items()
            if key != "excluded_discovered_later"
        }
    return sha256_text(canonical_json(body))


def normalize_moment(value: Any, field: str) -> str:
    """Strict UTC ISO-8601 at second precision; a naive time is rejected."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    text = str(value or "").strip()
    if not text:
        raise EntryValidationError(f"{field} 不能为空（缺失的时间不插补）")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EntryValidationError(f"{field} 必须是 ISO 8601 时间，收到 {text!r}") from exc
    if parsed.tzinfo is None:
        raise EntryValidationError(f"{field} 缺少时区：不猜测时区，请给出 UTC 偏移")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _now() -> str:
    return utc_now_iso()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FrozenDocumentCorrupt(f"无法解析冻结文档 {path.name}: {exc}") from exc


def _write_once(path: Path, document: Mapping[str, Any]) -> None:
    """Exclusive-create write: an existing file is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:  # pragma: no cover - guarded by callers
        raise FrozenDocumentConflict(f"文件已存在，拒绝覆盖：{path.name}") from exc


def _at_or_before(stamp: str | None, as_of: str) -> bool:
    """Second-granularity comparison.

    Ledger mapping rows are stamped with the real wall clock at microsecond
    precision while registry moments are second precision; comparing the second
    field only keeps "known at freeze time" deterministic instead of depending on
    a sub-second race (the frozen *evidence* itself is compared by the ledger's
    own second-precision ``first_seen_at``/``captured_at``).
    """
    if not stamp:
        return False
    return str(stamp)[:19] <= str(as_of)[:19]


def _validate_entry_id(entry_id: Any) -> str:
    text = str(entry_id or "").strip()
    if not _ENTRY_ID_RE.match(text) or ".." in text:
        raise EntryValidationError(
            f"entry_id 必须是 1-120 位安全字符（字母、数字、点、下划线、连字符），收到 {entry_id!r}"
        )
    return text


def _pick(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return None


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise EntryValidationError(f"{field} 不能为空")
    return text


def _truthy_flag(value: Any, field: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise EntryValidationError(f"{field} 必须是 true/false，收到 {value!r}")
    return value


# --------------------------------------------------------------------- registry
class ProspectiveRegistry:
    """Append-only, content-addressed prospective observation registry.

    ``directory`` defaults to :func:`default_registry_dir`.  Reads never create
    the directory, so a missing registry is an honest empty state, not an error.
    """

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_registry_dir()
        self.entries_dir = self.directory / ENTRIES_SUBDIR

    # ------------------------------------------------------------------ paths
    @property
    def exists(self) -> bool:
        return self.directory.is_dir()

    def entry_path(self, entry_id: str) -> Path:
        return self.entries_dir / f"{_validate_entry_id(entry_id)}.json"

    def _appendix_paths(self, entry_id: str, kind: str) -> list[tuple[int, Path]]:
        if not self.entries_dir.is_dir():
            return []
        found: list[tuple[int, Path]] = []
        prefix = f"{_validate_entry_id(entry_id)}.{kind}."
        for path in self.entries_dir.glob(f"{prefix}*.json"):
            match = _APPENDIX_RE.match(path.name)
            if not match or match.group("kind") != kind:
                continue
            found.append((int(match.group("seq")), path))
        return sorted(found, key=lambda item: item[0])

    def _frozen_paths(self) -> Iterable[Path]:
        if not self.entries_dir.is_dir():
            return []
        paths = []
        for path in self.entries_dir.glob("*.json"):
            if _APPENDIX_RE.match(path.name):
                continue
            paths.append(path)
        return sorted(paths, key=lambda item: item.name)

    # ------------------------------------------------------------------ freeze
    def freeze(
        self,
        entry: Mapping[str, Any],
        *,
        ledger: ObservationLedger | None = None,
    ) -> dict[str, Any]:
        """Freeze one hypothesis: write the frozen document + ledger snapshot once.

        Refuses to touch an existing frozen document.  A re-freeze of the identical
        protocol (same frozen body apart from the real append stamp) is an
        idempotent no-op reported as ``result="duplicate"``; any different content
        for the same ``entry_id`` raises :class:`FrozenDocumentConflict`.
        """
        spec = self._validate_spec(entry)
        owns_ledger = ledger is None
        if ledger is None:
            try:
                ledger = open_ledger_readonly()
            except FileNotFoundError as exc:
                raise ProspectiveRegistryError(
                    "冻结需要已存在的观察账本：请先运行采集，或显式传入 ledger"
                    f"（{exc}）"
                ) from exc
        try:
            document = self._build_document(spec, ledger)
        finally:
            if owns_ledger and ledger is not None:
                ledger.close()

        path = self.entry_path(spec["entry_id"])
        if path.exists():
            existing = _read_json(path)
            stored = existing.get("content_sha256")
            if stored != document_hash(existing):
                raise FrozenDocumentConflict(
                    f"条目 {spec['entry_id']} 的冻结文档哈希与正文不一致（疑似被改写），拒绝任何写入"
                )
            if protocol_hash(existing) == protocol_hash(document):
                return {**existing, "result": "duplicate"}
            raise FrozenDocumentConflict(
                f"条目 {spec['entry_id']} 已冻结为 {str(stored)[:12]}…，本次内容哈希为"
                f" {document['content_sha256'][:12]}…；冻结文档只写一次，不可改写"
            )
        _write_once(path, document)
        written = json.loads(path.read_text(encoding="utf-8"))
        return {**written, "result": "created"}

    def _validate_spec(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(entry, Mapping):
            raise EntryValidationError("freeze 需要一个对象（字典）")
        unknown = sorted(set(entry) - _ALLOWED_ENTRY_KEYS)
        if unknown:
            raise EntryValidationError(f"freeze 不接受未声明字段：{', '.join(unknown)}")
        reserved = sorted(set(entry) & _RESERVED_ENTRY_KEYS)
        if reserved:
            raise EntryValidationError(f"以下字段由登记器派生，不能由调用方提供：{', '.join(reserved)}")

        entry_id = _validate_entry_id(entry.get("entry_id"))
        label_zh = _text(entry.get("label_zh"), "label_zh")
        hypothesis_zh = _text(_pick(entry, "hypothesis_zh", "hypothesis"), "hypothesis_zh")
        target_event_definition_zh = _text(
            _pick(entry, "target_event_definition_zh", "target_event"),
            "target_event_definition_zh",
        )
        baseline_zh = _text(_pick(entry, "baseline_zh", "baseline"), "baseline_zh")
        evaluation_criteria_zh = _text(
            _pick(entry, "evaluation_criteria_zh", "evaluation_criteria"),
            "evaluation_criteria_zh",
        )
        window_start = normalize_moment(entry.get("window_start"), "window_start")
        window_end = normalize_moment(entry.get("window_end"), "window_end")
        if not window_start < window_end:
            raise EntryValidationError(
                f"目标窗口必须非空且 window_end > window_start，收到 [{window_start}, {window_end})"
            )
        freeze_at = (
            normalize_moment(entry["freeze_at"], "freeze_at")
            if entry.get("freeze_at") is not None
            else _now()
        )
        real_now = _now()
        if freeze_at > real_now:
            raise EntryValidationError(
                f"freeze_at {freeze_at} 晚于当前真实时间 {real_now}：不能把冻结时间写到未来"
            )
        if freeze_at > window_start:
            raise EntryValidationError(
                f"freeze_at {freeze_at} 必须不晚于 window_start {window_start}："
                "窗口开始后才登记就是事后登记，不是前瞻冻结"
            )

        synthetic = _truthy_flag(entry.get("synthetic"), "synthetic")
        note_zh = entry.get("note_zh")
        note_zh = str(note_zh).strip() if note_zh is not None else ""
        if synthetic:
            for field, value in (("label_zh", label_zh), ("note_zh", note_zh)):
                if SYNTHETIC_MARKER not in value:
                    raise EntryValidationError(
                        f"合成测试条目（synthetic=true）的 {field} 必须包含「{SYNTHETIC_MARKER}」，"
                        "以便任何界面都不会把它当成真实的前瞻结果"
                    )
        else:
            note_zh = note_zh or None

        scope = self._validate_scope(entry.get("scope"))
        target_event_type = entry.get("target_event_type")
        target_event_type = str(target_event_type).strip() if target_event_type else None

        return {
            "entry_id": entry_id,
            "label_zh": label_zh,
            "hypothesis_zh": hypothesis_zh,
            "target_event_definition_zh": target_event_definition_zh,
            "target_event_type": target_event_type,
            "baseline_zh": baseline_zh,
            "evaluation_criteria_zh": evaluation_criteria_zh,
            "window_start": window_start,
            "window_end": window_end,
            "freeze_at": freeze_at,
            "scope": scope,
            "synthetic": synthetic,
            "note_zh": note_zh,
        }

    @staticmethod
    def _validate_scope(scope: Any) -> dict[str, str | None]:
        cleaned: dict[str, str | None] = {"source": None, "entity_id": None, "track_id": None}
        if scope is None:
            return cleaned
        if not isinstance(scope, Mapping):
            raise EntryValidationError("scope 必须是对象，可含 source/entity_id/track_id")
        unknown = sorted(set(scope) - set(cleaned))
        if unknown:
            raise EntryValidationError(f"scope 不接受未声明字段：{', '.join(unknown)}")
        for key in cleaned:
            value = scope.get(key)
            if value is None or str(value).strip() == "":
                cleaned[key] = None
            else:
                cleaned[key] = str(value).strip()
        return cleaned

    def _build_document(
        self, spec: Mapping[str, Any], ledger: ObservationLedger
    ) -> dict[str, Any]:
        snapshot = self._scoped_snapshot(ledger, spec["freeze_at"], spec["scope"])
        items = [
            _evidence_item(
                row,
                self._change_at(
                    ledger,
                    str(row.get("observation_id")),
                    row.get("version_id"),
                    snapshot["as_of"],
                ),
            )
            for row in snapshot["items"]
        ]
        evidence = {
            "as_of": snapshot["as_of"],
            "policy_zh": snapshot["policy_zh"],
            "observation_policy_zh": (
                "冻结输入 = 账本在 as_of 时点已知的记录（first_seen_at <= as_of），"
                "各记录取该时点之前的最新版本（captured_at <= as_of）；"
                "之后才发现的历史记录不进入冻结输入。展示用标题/事件时间来自该版本的"
                " append-only 变更行，而不是会被后续修订覆盖的 observation 显示缓存。"
            ),
            "count": len(items),
            "items": items,
            "evidence_sha256": sha256_text(canonical_json(items)),
            "excluded_discovered_later": snapshot["excluded_discovered_later"],
        }
        document: dict[str, Any] = {
            "schema": ENTRY_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "entry_id": spec["entry_id"],
            "label_zh": spec["label_zh"],
            "hypothesis_zh": spec["hypothesis_zh"],
            "target_event_definition_zh": spec["target_event_definition_zh"],
            "target_event_type": spec["target_event_type"],
            "baseline_zh": spec["baseline_zh"],
            "evaluation_criteria_zh": spec["evaluation_criteria_zh"],
            "window_start": spec["window_start"],
            "window_end": spec["window_end"],
            "freeze_at": spec["freeze_at"],
            "frozen_recorded_at": _now(),
            "scope": dict(spec["scope"]),
            "synthetic": bool(spec["synthetic"]),
            "note_zh": spec["note_zh"],
            "status": STATUS_EXPERIMENTAL,
            "evidence": evidence,
            "policy_zh": list(FROZEN_POLICY_ZH),
        }
        document["content_sha256"] = document_hash(document)
        return document

    # ------------------------------------------------------------------- reads
    def list_entries(self, *, now: Any | None = None) -> list[dict[str, Any]]:
        """Summarise every frozen entry; a missing registry is an empty list."""
        now_iso = normalize_moment(now, "now") if now is not None else _now()
        summaries: list[dict[str, Any]] = []
        for path in self._frozen_paths():
            entry_id = path.stem
            try:
                raw = path.read_bytes()
                document = json.loads(raw.decode("utf-8"))
            except (OSError, ValueError) as exc:
                summaries.append(
                    {
                        "entry_id": entry_id,
                        "integrity": "CORRUPT",
                        "integrity_zh": f"冻结文档无法解析：{exc}",
                        "status": STATUS_EXPERIMENTAL,
                        "status_label_zh": STATUS_LABELS_ZH[STATUS_EXPERIMENTAL],
                        "synthetic": False,
                        "label_zh": entry_id,
                        "frozen_verified": False,
                    }
                )
                continue
            summaries.append(self._summary(document, raw, now_iso))
        summaries.sort(key=lambda item: (str(item.get("freeze_at") or ""), item["entry_id"]), reverse=True)
        return summaries

    def _summary(self, document: Mapping[str, Any], raw: bytes, now_iso: str) -> dict[str, Any]:
        entry_id = str(document.get("entry_id") or "")
        evaluations = self._appendices(entry_id, "evaluation")
        statuses = self._appendices(entry_id, "status")
        status = self._effective_status(document, evaluations, statuses, now_iso)
        verification = self._verification(document, raw)
        latest = evaluations[-1] if evaluations else None
        return {
            "entry_id": entry_id,
            "label_zh": document.get("label_zh"),
            "hypothesis_zh": document.get("hypothesis_zh"),
            "target_event_definition_zh": document.get("target_event_definition_zh"),
            "baseline_zh": document.get("baseline_zh"),
            "evaluation_criteria_zh": document.get("evaluation_criteria_zh"),
            "freeze_at": document.get("freeze_at"),
            "window_start": document.get("window_start"),
            "window_end": document.get("window_end"),
            "scope": dict(document.get("scope") or {}),
            "status": status,
            "status_label_zh": STATUS_LABELS_ZH[status],
            "frozen_status": document.get("status"),
            "synthetic": bool(document.get("synthetic")),
            "note_zh": document.get("note_zh"),
            "frozen_evidence_count": int((document.get("evidence") or {}).get("count") or 0),
            "frozen_evidence_as_of": (document.get("evidence") or {}).get("as_of"),
            "evaluation_count": len(evaluations),
            "latest_evaluation": latest,
            "evaluations": list(evaluations),
            "status_history": statuses,
            "retracted": status == STATUS_RETRACTED,
            "retraction_reason_zh": self._retraction_reason(statuses),
            "content_sha256": document.get("content_sha256"),
            "integrity": "OK" if verification["ok"] else "TAMPERED",
            "frozen_verified": bool(verification["ok"]),
        }

    def get_entry(self, entry_id: str, *, now: Any | None = None) -> dict[str, Any]:
        """Full frozen document plus the append-only evaluation/status history."""
        entry_id = _validate_entry_id(entry_id)
        now_iso = normalize_moment(now, "now") if now is not None else _now()
        path, raw, document = self._load_frozen(entry_id)
        evaluations = self._appendices(entry_id, "evaluation")
        statuses = self._appendices(entry_id, "status")
        status = self._effective_status(document, evaluations, statuses, now_iso)
        verification = self._verification(document, raw)
        view = dict(document)
        view["frozen_status"] = document.get("status")
        view["status"] = status
        view["status_label_zh"] = STATUS_LABELS_ZH[status]
        view["status_note_zh"] = STATUS_NOTES_ZH[status]
        view["evaluations"] = evaluations
        view["latest_evaluation"] = evaluations[-1] if evaluations else None
        view["evaluation_count"] = len(evaluations)
        view["status_history"] = statuses
        view["retracted"] = status == STATUS_RETRACTED
        view["retraction_reason_zh"] = self._retraction_reason(statuses)
        view["integrity"] = "OK" if verification["ok"] else "TAMPERED"
        view["frozen_verified"] = bool(verification["ok"])
        view["verification"] = {
            "ok": verification["ok"],
            "content_sha256": verification["content_sha256"],
            "recomputed_sha256": verification["recomputed_sha256"],
            "evidence_sha256_ok": verification["evidence_sha256_ok"],
            "checked_at": verification["checked_at"],
        }
        return view

    # ------------------------------------------------------------- verification
    def verify_frozen(self, entry_id: str) -> dict[str, Any]:
        """Recompute the frozen document hash and detect tampering."""
        entry_id = _validate_entry_id(entry_id)
        path, raw, document = self._load_frozen(entry_id)
        return self._verification(document, raw, path=path)

    def _verification(
        self,
        document: Mapping[str, Any],
        raw: bytes,
        *,
        path: Path | None = None,
    ) -> dict[str, Any]:
        stored = document.get("content_sha256")
        recomputed = document_hash(document)
        evidence = document.get("evidence") or {}
        stored_items_hash = evidence.get("evidence_sha256")
        recomputed_items_hash = sha256_text(canonical_json(list(evidence.get("items") or [])))
        evidence_sha256_ok = stored_items_hash == recomputed_items_hash
        ok = stored == recomputed and evidence_sha256_ok
        entry_id = str(document.get("entry_id") or (path.stem if path else ""))
        return {
            "entry_id": entry_id,
            "ok": bool(ok),
            "content_sha256": stored,
            "recomputed_sha256": recomputed,
            "stored_evidence_sha256": stored_items_hash,
            "recomputed_evidence_sha256": recomputed_items_hash,
            "evidence_sha256_ok": bool(evidence_sha256_ok),
            "evidence_count": int(evidence.get("count") or 0),
            "bytes": len(raw),
            "file": f"{ENTRIES_SUBDIR}/{entry_id}.json",
            "checked_at": _now(),
            "reason_zh": (
                "冻结文档内容与登记哈希完全一致"
                if ok
                else "冻结文档内容与登记哈希不一致：文件已被改写或损坏"
            ),
        }

    def _load_frozen(self, entry_id: str) -> tuple[Path, bytes, dict[str, Any]]:
        path = self.entry_path(entry_id)
        if not path.is_file():
            raise KeyError(f"unknown prospective entry: {entry_id}")
        try:
            raw = path.read_bytes()
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise ProspectiveRegistryError(f"无法读取冻结文档 {path.name}: {exc}") from exc
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise FrozenDocumentCorrupt(f"无法解析冻结文档 {path.name}: {exc}") from exc
        if not isinstance(document, dict):
            raise FrozenDocumentCorrupt(f"冻结文档 {path.name} 不是 JSON 对象")
        return path, raw, document

    def _require_untampered(self, entry_id: str) -> dict[str, Any]:
        _, _, document = self._load_frozen(entry_id)
        verification = self._verification(document, self.entry_path(entry_id).read_bytes())
        if not verification["ok"]:
            raise FrozenDocumentTampered(
                f"条目 {entry_id} 的冻结文档哈希校验失败，拒绝在其上追加任何内容"
            )
        return document

    # -------------------------------------------------------------- appendices
    def _appendices(self, entry_id: str, kind: str) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for seq, path in self._appendix_paths(entry_id, kind):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                documents.append(
                    {
                        "schema": f"{kind}-unreadable",
                        "entry_id": entry_id,
                        f"{kind}_seq": seq,
                        "integrity": "CORRUPT",
                        "error_zh": f"附录无法解析：{exc}",
                    }
                )
                continue
            if not isinstance(document, dict):
                documents.append(
                    {
                        "schema": f"{kind}-unreadable",
                        "entry_id": entry_id,
                        f"{kind}_seq": seq,
                        "integrity": "CORRUPT",
                        "error_zh": "附录不是 JSON 对象",
                    }
                )
                continue
            documents.append(document)
        return documents

    @staticmethod
    def _retraction_reason(statuses: Sequence[Mapping[str, Any]]) -> str | None:
        for document in reversed(list(statuses)):
            if document.get("status") == STATUS_RETRACTED:
                return document.get("reason_zh")
        return None

    @staticmethod
    def _effective_status(
        document: Mapping[str, Any],
        evaluations: Sequence[Mapping[str, Any]],
        statuses: Sequence[Mapping[str, Any]],
        now_iso: str,
    ) -> str:
        for item in reversed(list(statuses)):
            if item.get("status") == STATUS_RETRACTED:
                return STATUS_RETRACTED
        if evaluations:
            return STATUS_MATURED
        window_end = str(document.get("window_end") or "")
        window_start = str(document.get("window_start") or "")
        if window_end and now_iso >= window_end:
            return STATUS_DUE
        if window_start and now_iso >= window_start:
            return STATUS_ACTIVE
        return STATUS_EXPERIMENTAL

    # ------------------------------------------------------------ evaluation
    def evaluate_against_ledger(
        self,
        entry_id: str,
        ledger: ObservationLedger | None = None,
        now: Any | None = None,
    ) -> dict[str, Any]:
        """Evaluate a matured entry against the ledger — or refuse with ``NOT_DUE``.

        Before ``window_end`` nothing is written and ``status="NOT_DUE"`` is
        returned with the reason.  At/after ``window_end`` the outcome is counted
        from the ledger's own point-in-time view:

        * ``inputs``  — the frozen evidence captured at freeze time;
        * ``outcomes`` — observations whose ``first_seen_at`` falls in
          ``(max(freeze_at, window_start), window_end]`` and that were *not*
          known as inputs (later revisions of inputs are disclosed separately);
        * discoveries after ``window_end`` are excluded by construction because
          the outcome set is taken from ``ledger.snapshot(window_end)``.
        """
        entry_id = _validate_entry_id(entry_id)
        now_iso = normalize_moment(now, "now") if now is not None else _now()
        _path, raw, document = self._load_frozen(entry_id)
        verification = self._verification(document, raw)
        if not verification["ok"]:
            return {
                "entry_id": entry_id,
                "status": "TAMPERED",
                "evaluated": False,
                "now": now_iso,
                "reason_zh": "冻结文档哈希校验失败：拒绝在已被改写的冻结正文上计算结局。",
                "frozen_content_sha256": document.get("content_sha256"),
                "computed_at": None,
                "recorded_at": None,
            }

        window_start = str(document["window_start"])
        window_end = str(document["window_end"])
        if now_iso < window_end:
            return {
                "entry_id": entry_id,
                "status": "NOT_DUE",
                "evaluated": False,
                "now": now_iso,
                "window_start": window_start,
                "window_end": window_end,
                "reason_zh": (
                    f"目标窗口尚未结束（now={now_iso} < window_end={window_end}）："
                    "拒绝提前计算结局，也不写入任何评估附录。"
                ),
                "frozen_content_sha256": document.get("content_sha256"),
                "computed_at": None,
                "recorded_at": None,
                "synthetic": bool(document.get("synthetic")),
                "ledger_counts": ledger.counts() if ledger is not None else None,
            }

        owns_ledger = ledger is None
        if ledger is None:
            try:
                ledger = open_ledger_readonly()
            except FileNotFoundError as exc:
                raise ProspectiveRegistryError(
                    f"评估需要已存在的观察账本：{exc}"
                ) from exc
        try:
            evaluation = self._build_evaluation(document, ledger, now_iso)
        finally:
            if owns_ledger and ledger is not None:
                ledger.close()
        return self.append_evaluation(entry_id, evaluation)

    def _build_evaluation(
        self,
        document: Mapping[str, Any],
        ledger: ObservationLedger,
        now_iso: str,
    ) -> dict[str, Any]:
        scope = dict(document.get("scope") or {})
        freeze_at = str(document["freeze_at"])
        window_start = str(document["window_start"])
        window_end = str(document["window_end"])
        lower_bound = max(freeze_at, window_start)

        at_window_end = self._scoped_snapshot(ledger, window_end, scope)
        at_lower_bound = self._scoped_snapshot(ledger, lower_bound, scope)

        frozen_items = list((document.get("evidence") or {}).get("items") or [])
        frozen_ids = {str(item.get("observation_id")) for item in frozen_items}
        known_at_lower = {str(item["observation_id"]): item for item in at_lower_bound["items"]}

        outcomes: list[dict[str, Any]] = []
        for item in at_window_end["items"]:
            observation_id = str(item["observation_id"])
            if observation_id in frozen_ids or observation_id in known_at_lower:
                continue
            outcomes.append(_outcome_item(item))
        outcomes.sort(key=lambda row: (str(row.get("first_seen_at") or ""), row["observation_id"]))

        new_versions: list[dict[str, Any]] = []
        end_by_id = {str(item["observation_id"]): item for item in at_window_end["items"]}
        for observation_id in sorted(frozen_ids):
            before = known_at_lower.get(observation_id)
            after = end_by_id.get(observation_id)
            if before is None or after is None:
                continue
            if before.get("version_id") == after.get("version_id"):
                continue
            new_versions.append(
                {
                    "observation_id": observation_id,
                    "source": after.get("source"),
                    "record_type": after.get("record_type"),
                    "title": after.get("title"),
                    "first_seen_at": after.get("first_seen_at"),
                    "frozen_version_id": before.get("version_id"),
                    "version_id": after.get("version_id"),
                    "payload_hash": after.get("payload_hash"),
                    "captured_at": after.get("captured_at"),
                }
            )

        pre_window = []
        for item in at_lower_bound["items"]:
            observation_id = str(item["observation_id"])
            if observation_id in frozen_ids:
                continue
            pre_window.append(_outcome_item(item))
        pre_window.sort(key=lambda row: (str(row.get("first_seen_at") or ""), row["observation_id"]))

        counts = ledger.counts()
        synthetic = bool(document.get("synthetic"))
        honesty = list(EVALUATION_HONESTY_ZH)
        if synthetic:
            honesty.insert(
                0,
                f"{SYNTHETIC_MARKER}条目：这是测试构造的登记项与账本，不是真实的前瞻观察结果。",
            )
        evaluation: dict[str, Any] = {
            "schema": EVALUATION_SCHEMA,
            "status": STATUS_MATURED,
            "computed_at": now_iso,
            "synthetic": synthetic,
            "window_start": window_start,
            "window_end": window_end,
            "freeze_at": freeze_at,
            "target_event_definition_zh": document.get("target_event_definition_zh"),
            "target_event_type": document.get("target_event_type"),
            "baseline_zh": document.get("baseline_zh"),
            "evaluation_criteria_zh": document.get("evaluation_criteria_zh"),
            "inputs": {
                "count": len(frozen_items),
                "evidence_sha256": (document.get("evidence") or {}).get("evidence_sha256"),
                "frozen_at": freeze_at,
                "snapshot_as_of": (document.get("evidence") or {}).get("as_of"),
                "observation_ids": sorted(frozen_ids),
                "note_zh": "冻结输入 = 假设冻结时刻账本中已知、且符合声明范围的记录。",
            },
            "outcomes": {
                "count": len(outcomes),
                "new_version_count": len(new_versions),
                "items": outcomes,
                "new_versions": new_versions,
                "window_policy_zh": (
                    f"结局窗口 = ({lower_bound}, {window_end}]：只统计冻结之后、窗口内首次观察到的记录；"
                    "窗口结束后才发现的记录不计入。"
                ),
                "classification": "CANDIDATE_EVIDENCE_ONLY",
                "human_classification_required": True,
                "note_zh": (
                    "登记器只列出窗口内新观察到的候选证据，不自动判定目标事件是否发生；"
                    "目标事件是否成立按冻结时声明的判据由研究者判定。"
                ),
            },
            "pre_window_discoveries": {
                "count": len(pre_window),
                "items": pre_window,
                "note_zh": "冻结之后、窗口开始之前发现的记录：既不是冻结输入，也不是窗口内结局。",
            },
            "ledger": {
                "path": counts.get("path"),
                "counts": counts,
                "snapshot_as_of": now_iso,
                "window_end_snapshot_as_of": at_window_end["as_of"],
                "lower_bound_snapshot_as_of": at_lower_bound["as_of"],
                "excluded_discovered_later_than_window_end": at_window_end[
                    "excluded_discovered_later"
                ],
                "note_zh": "counts 为评估计算时刻（snapshot_as_of）账本的当前计数；结局计数只来自窗口内快照。",
            },
            "honesty_zh": honesty,
        }
        return evaluation

    def append_evaluation(
        self, entry_id: str, evaluation: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Append one evaluation as a new immutable appendix file.

        Only a ``MATURED`` evaluation computed at/after ``window_end`` is accepted;
        anything else is refused so a premature or fabricated result cannot be
        stored.  The appendix records the frozen document hash it was computed
        against, so a later rewrite of the frozen body is detected.
        """
        entry_id = _validate_entry_id(entry_id)
        if not isinstance(evaluation, Mapping):
            raise EntryValidationError("append_evaluation 需要评估对象（字典）")
        document = self._require_untampered(entry_id)

        status = str(evaluation.get("status") or "").strip().upper()
        if status != STATUS_MATURED:
            raise EntryValidationError(
                f"只接受 status={STATUS_MATURED} 的评估附录；拒绝 {status or '（空）'}"
                "（窗口尚未结束或未完成计算的结果不得写入）"
            )
        computed_at = normalize_moment(evaluation.get("computed_at"), "computed_at")
        window_end = str(document["window_end"])
        if computed_at < window_end:
            raise EntryValidationError(
                f"评估 computed_at {computed_at} 早于 window_end {window_end}：拒绝窗口结束前的结果"
            )

        existing = self._appendices(entry_id, "evaluation")
        seq = len(existing) + 1
        synthetic = bool(document.get("synthetic"))
        honesty = evaluation.get("honesty_zh")
        if not isinstance(honesty, list) or not honesty:
            honesty = list(EVALUATION_HONESTY_ZH)
        honesty = [str(item) for item in honesty]
        if synthetic and not any(SYNTHETIC_MARKER in item for item in honesty):
            honesty.insert(0, f"{SYNTHETIC_MARKER}条目：该评估基于测试构造的登记项，不是真实前瞻结果。")

        appendix: dict[str, Any] = {
            "schema": EVALUATION_SCHEMA,
            "entry_id": entry_id,
            "evaluation_seq": seq,
            "supersedes": seq - 1 if seq > 1 else None,
            "status": STATUS_MATURED,
            "computed_at": computed_at,
            "recorded_at": _now(),
            "synthetic": synthetic,
            "freeze_at": document.get("freeze_at"),
            "window_start": document.get("window_start"),
            "window_end": window_end,
            "target_event_definition_zh": document.get("target_event_definition_zh"),
            "target_event_type": document.get("target_event_type"),
            "baseline_zh": document.get("baseline_zh"),
            "evaluation_criteria_zh": document.get("evaluation_criteria_zh"),
            "frozen_content_sha256": document.get("content_sha256"),
            "frozen_evidence_sha256": (document.get("evidence") or {}).get("evidence_sha256"),
            "inputs": evaluation.get("inputs"),
            "outcomes": evaluation.get("outcomes"),
            "pre_window_discoveries": evaluation.get("pre_window_discoveries"),
            "ledger": evaluation.get("ledger"),
            "honesty_zh": honesty,
            "note_zh": evaluation.get("note_zh"),
        }
        appendix["content_sha256"] = document_hash(appendix)
        path = self.entries_dir / f"{entry_id}.evaluation.{seq}.json"
        _write_once(path, appendix)
        return json.loads(path.read_text(encoding="utf-8"))

    # ----------------------------------------------------------------- status
    def append_status(
        self,
        entry_id: str,
        status: str,
        *,
        reason_zh: str,
        now: Any | None = None,
    ) -> dict[str, Any]:
        """Append a status transition (append-only; currently ``RETRACTED`` only)."""
        entry_id = _validate_entry_id(entry_id)
        normalized = str(status or "").strip().upper()
        if normalized != STATUS_RETRACTED:
            raise EntryValidationError(
                f"状态附录只接受 {STATUS_RETRACTED}；ACTIVE/DUE/MATURED 由冻结窗口与评估派生"
            )
        reason = _text(reason_zh, "reason_zh")
        document = self._require_untampered(entry_id)
        changed_at = normalize_moment(now, "now") if now is not None else _now()
        existing = self._appendices(entry_id, "status")
        seq = len(existing) + 1
        appendix: dict[str, Any] = {
            "schema": STATUS_SCHEMA,
            "entry_id": entry_id,
            "status_seq": seq,
            "status": normalized,
            "changed_at": changed_at,
            "recorded_at": _now(),
            "reason_zh": reason,
            "frozen_content_sha256": document.get("content_sha256"),
            "synthetic": bool(document.get("synthetic")),
        }
        appendix["content_sha256"] = document_hash(appendix)
        _write_once(self.entries_dir / f"{entry_id}.status.{seq}.json", appendix)
        return json.loads(
            (self.entries_dir / f"{entry_id}.status.{seq}.json").read_text(encoding="utf-8")
        )

    # -------------------------------------------------------------- snapshots
    def _scoped_snapshot(
        self,
        ledger: ObservationLedger,
        as_of: str,
        scope: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Point-in-time ledger view filtered to the hypothesis's declared scope."""
        source = scope.get("source") if scope else None
        entity_id = scope.get("entity_id") if scope else None
        track_id = scope.get("track_id") if scope else None
        snapshot = ledger.snapshot(as_of, source=source)
        if not entity_id and not track_id:
            return snapshot
        items: list[dict[str, Any]] = []
        for item in snapshot["items"]:
            mapping = self._mapping_at(ledger, str(item["observation_id"]), snapshot["as_of"])
            if entity_id and not (
                mapping
                and mapping.get("entity_status") == ENTITY_MAPPED
                and mapping.get("entity_id") == entity_id
            ):
                continue
            if track_id and not (
                mapping
                and mapping.get("track_status") == TRACK_MAPPED
                and mapping.get("track_id") == track_id
            ):
                continue
            items.append(item)
        return {**snapshot, "items": items, "total": len(items)}

    @staticmethod
    def _change_at(
        ledger: ObservationLedger,
        observation_id: str,
        version_id: Any,
        as_of: str,
    ) -> dict[str, Any] | None:
        """Append-only change row for exactly this as-of version (immutable facts)."""
        if not version_id:
            return None
        chosen: dict[str, Any] | None = None
        for row in ledger.changes_for(observation_id):
            if row.get("version_id") != version_id:
                continue
            if not _at_or_before(row.get("observed_at"), as_of):
                continue
            chosen = row
        return chosen

    @staticmethod
    def _mapping_at(
        ledger: ObservationLedger, observation_id: str, as_of: str
    ) -> dict[str, Any] | None:
        chosen: dict[str, Any] | None = None
        for row in ledger.mapping_history(observation_id):
            if _at_or_before(row.get("mapped_at"), as_of):
                chosen = row
        return chosen


# ------------------------------------------------------------------ item shaping
def _evidence_item(
    row: Mapping[str, Any], change: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The frozen-evidence fields a reader can re-verify against the ledger.

    Identity/version facts are immutable in the ledger.  Display facts (title,
    event/publish time, URL) are taken from the append-only ``observation_change``
    row of *this exact version* — never from ``observation.title``, which is a
    mutable display cache that a later revision overwrites.  A later ledger write
    therefore cannot change what a re-freeze would capture.
    """
    change = change or {}
    return {
        "observation_id": row.get("observation_id"),
        "version_id": row.get("version_id"),
        "payload_hash": row.get("payload_hash"),
        "first_seen_at": row.get("first_seen_at"),
        "source": row.get("source"),
        "source_record_id": row.get("source_record_id"),
        "record_type": row.get("record_type"),
        "title": change.get("title"),
        "event_at": change.get("event_at"),
        "event_at_precision": change.get("event_at_precision"),
        "published_at": change.get("published_at"),
        "published_at_precision": change.get("published_at_precision"),
        "url": change.get("url"),
    }


def _outcome_item(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": row.get("observation_id"),
        "source": row.get("source"),
        "source_record_id": row.get("source_record_id"),
        "record_type": row.get("record_type"),
        "title": row.get("title"),
        "first_seen_at": row.get("first_seen_at"),
        "event_at": row.get("event_at"),
        "event_at_precision": row.get("event_at_precision"),
        "published_at": row.get("published_at"),
        "version_id": row.get("version_id"),
        "payload_hash": row.get("payload_hash"),
        "original_url": row.get("original_url"),
    }


# ----------------------------------------------------------- module-level API
def open_registry(directory: str | Path | None = None) -> ProspectiveRegistry:
    """Open (or address) a registry directory without creating it."""
    return ProspectiveRegistry(directory)


def freeze(
    entry: Mapping[str, Any],
    *,
    ledger: ObservationLedger | None = None,
    registry: ProspectiveRegistry | None = None,
) -> dict[str, Any]:
    """Module-level shortcut for :meth:`ProspectiveRegistry.freeze`."""
    return (registry or ProspectiveRegistry()).freeze(entry, ledger=ledger)


def list_entries(
    *, now: Any | None = None, registry: ProspectiveRegistry | None = None
) -> list[dict[str, Any]]:
    return (registry or ProspectiveRegistry()).list_entries(now=now)


def get_entry(
    entry_id: str, *, now: Any | None = None, registry: ProspectiveRegistry | None = None
) -> dict[str, Any]:
    return (registry or ProspectiveRegistry()).get_entry(entry_id, now=now)


def append_evaluation(
    entry_id: str,
    evaluation: Mapping[str, Any],
    *,
    registry: ProspectiveRegistry | None = None,
) -> dict[str, Any]:
    return (registry or ProspectiveRegistry()).append_evaluation(entry_id, evaluation)


def verify_frozen(
    entry_id: str, *, registry: ProspectiveRegistry | None = None
) -> dict[str, Any]:
    return (registry or ProspectiveRegistry()).verify_frozen(entry_id)


def evaluate_against_ledger(
    entry_id: str,
    ledger: ObservationLedger | None = None,
    now: Any | None = None,
    *,
    registry: ProspectiveRegistry | None = None,
) -> dict[str, Any]:
    return (registry or ProspectiveRegistry()).evaluate_against_ledger(
        entry_id, ledger, now
    )
