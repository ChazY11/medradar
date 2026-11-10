"""Shared primitives for the independent verifier.

Nothing here imports application code. Every recomputation is written from the
raw bytes and the published schema documents, so a defect in the developer's
code cannot hide behind a shared helper.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess

PASS = "PASS"
FAIL = "FAIL"
UNVERIFIABLE = "UNVERIFIABLE"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# --------------------------------------------------------------------------- io
def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def load_jsonl(path: str) -> list:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def scan_jsonl(path: str) -> dict:
    """Byte length, line statistics and parsed record count for one jsonl file."""
    size = os.path.getsize(path)
    total = 0
    nonempty = 0
    bad = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            total += 1
            if line.strip():
                nonempty += 1
                try:
                    json.loads(line)
                except ValueError:
                    bad += 1
    return {
        "bytes": size,
        "lines_total": total,
        "lines_nonempty": nonempty,
        "lines_blank": total - nonempty,
        "records_parsed": nonempty - bad,
        "unparseable_lines": bad,
    }


def iter_json_array(path: str, chunk: int = 1 << 22):
    """Stream the elements of a top-level JSON array without holding it in memory."""
    decoder = json.JSONDecoder()
    with open(path, "r", encoding="utf-8") as fh:
        buf = fh.read(chunk)
        start = buf.find("[")
        if start < 0:
            return
        buf = buf[start + 1:]
        pos = 0
        while True:
            n = len(buf)
            while pos < n and buf[pos] in " \t\r\n,":
                pos += 1
            if pos >= n:
                more = fh.read(chunk)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            if buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except ValueError:
                more = fh.read(chunk)
                if not more:
                    raise
                buf = buf[pos:] + more
                pos = 0
                continue
            yield obj
            pos = end


# ------------------------------------------------------------------- hashing
def canonical_json(payload) -> str:
    """Same canonicalisation ATLAS documents for its content hashes."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(payload) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def atlas_make_evidence_id(source_id: str, evidence_type: str, source_record_id: str) -> str:
    """Reimplementation of the documented deterministic evidence id.

    ``ev_`` + first 32 hex of sha256("source_id|evidence_type|source_record_id").
    """
    raw = "|".join([source_id, evidence_type, source_record_id])
    return "ev_" + sha256_bytes(raw.encode("utf-8"))[:32]


def horizon_content_hash(record: dict) -> str:
    """Reimplementation of horizon.evidence.v1 ``content_key`` / ``compute_hash``.

    Documented at research/horizon/hz/schema.py:146-173: a fixed canonical subset,
    identifiers reduced to (scheme, value) and sorted, json.dumps(sort_keys=True,
    ensure_ascii=False, separators=(',', ':')).
    """
    ids = record.get("identifiers") or []
    key = {
        "schema_version": record.get("schema_version"),
        "source_id": record.get("source_id"),
        "source_record_id": record.get("source_record_id"),
        "entity_type": record.get("entity_type"),
        "original_name": record.get("original_name"),
        "identifiers": sorted(
            ({"scheme": i.get("scheme"), "value": i.get("value")} for i in ids),
            key=lambda d: (d["scheme"], d["value"]),
        ),
        "manufacturer": record.get("manufacturer"),
        "attributes": record.get("attributes"),
        "event_at": record.get("event_at"),
        "source_public_at": record.get("source_public_at"),
        "source_url": record.get("source_url"),
    }
    return sha256_json(key)


def horizon_dedupe_key(record: dict) -> str:
    """Reimplementation of the documented cross-source dedupe precedence."""
    strength = [
        "udi_di", "gtin", "doi", "patent_family_id", "epo_publication_number",
        "uspto_patent_number", "uspto_510k", "uspto_pma", "hc_device_licence",
        "nct", "pmid", "pmcid",
    ]
    ids = record.get("identifiers") or []
    present = {(i.get("scheme"), i.get("value")) for i in ids if i.get("scheme") and i.get("value")}
    for scheme in strength:
        for s, v in sorted(present):
            if s == scheme:
                return "%s:%s" % (scheme, v)
    if present:
        s, v = sorted(present)[0]
        return "%s:%s" % (s, v)
    return "hash:%s" % (record.get("content_hash") or "")


def atlas_canonical_key(identifiers) -> str | None:
    """Reimplementation of the documented ATLAS canonical-key precedence."""
    priority = [
        "di", "basic_udi_di", "licence_no", "510k", "pma", "denovo",
        "recall_number", "nct", "doi", "pmid", "patent_no", "ocid",
    ]
    by_scheme = {}
    for ident in identifiers or []:
        scheme = str(ident.get("scheme", "")).strip().lower()
        value = str(ident.get("value", "")).strip()
        if not scheme or not value:
            continue
        if scheme == "doi":
            value = value.lower()
        if scheme == "di" and ident.get("is_primary"):
            by_scheme["di"] = value
        else:
            by_scheme.setdefault(scheme, value)
    for scheme in priority:
        if scheme in by_scheme:
            return "%s:%s" % (scheme, by_scheme[scheme])
    return None


# ------------------------------------------------------------------- GTIN
def gtin_check_digit_ok(value: str, length: int = 14) -> bool:
    """GS1 Mod-10 check digit for a fixed-length numeric GTIN."""
    if not isinstance(value, str) or len(value) != length or not value.isdigit():
        return False
    body, check = value[:-1], int(value[-1])
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10 == check


def is_gtin14(value: str) -> bool:
    return gtin_check_digit_ok(value, 14)


# ------------------------------------------------------------------- dates
def parse_date(value):
    """Tolerant ISO date/datetime -> date, mirrowing the documented tolerance."""
    import datetime as dt

    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    if len(v) == 8 and v.isdigit():
        try:
            return dt.date(int(v[0:4]), int(v[4:6]), int(v[6:8]))
        except ValueError:
            return None
    try:
        return dt.date.fromisoformat(v[:10])
    except ValueError:
        return None


def days_between(a, b):
    da, db = parse_date(a), parse_date(b)
    if da is None or db is None:
        return None
    return (db - da).days


def is_iso(value: str) -> bool:
    return bool(_DATE_RE.match(value) or _DATETIME_RE.match(value))


def is_hex64(value) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


# ------------------------------------------------------------------- results
class Check:
    """One claim, one independent recomputation, one verdict."""

    def __init__(self, check_id, group, title, claim, claim_source, status,
                 expected=None, actual=None, detail="", evidence=None):
        self.check_id = check_id
        self.group = group
        self.title = title
        self.claim = claim
        self.claim_source = claim_source
        self.status = status
        self.expected = expected
        self.actual = actual
        self.detail = detail
        self.evidence = evidence or {}

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "group": self.group,
            "title": self.title,
            "claim": self.claim,
            "claim_source": self.claim_source,
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def compare(check_id, group, title, claim, claim_source, expected, actual,
            detail="", evidence=None, status_on_equal=PASS, status_on_diff=FAIL):
    status = status_on_equal if expected == actual else status_on_diff
    return Check(check_id, group, title, claim, claim_source, status,
                 expected=expected, actual=actual, detail=detail, evidence=evidence)


def unverifiable(check_id, group, title, claim, claim_source, reason, expected=None, actual=None):
    return Check(check_id, group, title, claim, claim_source, UNVERIFIABLE,
                 expected=expected, actual=actual, detail=reason)


def passed(check_id, group, title, claim, claim_source, actual, detail="", evidence=None):
    return Check(check_id, group, title, claim, claim_source, PASS,
                 expected=actual, actual=actual, detail=detail, evidence=evidence)


def failed(check_id, group, title, claim, claim_source, expected, actual,
           detail="", evidence=None):
    return Check(check_id, group, title, claim, claim_source, FAIL,
                 expected=expected, actual=actual, detail=detail, evidence=evidence)


# ------------------------------------------------------------------- git
def git(root: str, *args) -> str:
    """Read-only git helper. Never mutates refs, index or worktree."""
    try:
        out = subprocess.run(
            ["git", "-C", root] + list(args),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return "GIT-UNAVAILABLE: %s" % exc
    return out.stdout


def contextualise(path: str, root: str) -> str:
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        rel = path
    return rel.replace("\\", "/")
