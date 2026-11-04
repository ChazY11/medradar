"""Job posting identity, versioning and duplicate rules (pure functions).

Why this module exists
----------------------
The recruitment lane publishes numbers like "company X added 12 postings this
month". That number is only a research asset if three different questions are
kept apart:

1. **Is this the same posting as before?** A Workday job posting has an opaque id
   that survives re-publication. Its URL slug embeds the job title, so a retitle
   changes the slug; its requisition id can span several postings/cities. Using
   the slug as identity would turn an edit into a "new job", and using the
   requisition as identity would merge unrelated cities into one job.
2. **Did the posting's content change?** An edited description is a *revision* of
   the same posting (``records.content_hash`` changes), not a new posting.
3. **Did the posting disappear?** A missing posting is a *removal from the
   source*, not a hire, and an absence from an incomplete snapshot is not even a
   removal.

This module encodes those rules as code and applies them in
:func:`diff_snapshots`, which turns two observations of the same career site into
per-posting change events with the evidence needed to audit each one. It mirrors
the append-only discipline of :mod:`medradar.observatory.records`: a closed change
vocabulary, ``first_seen_at`` write-once, and "no change" as a check result rather
than a manufactured event.

Identity rule table (also available programmatically as ``IDENTITY_RULE_TABLE``)
-------------------------------------------------------------------------------
======================  ==================  ============================================
source field            role                why
======================  ==================  ============================================
``posting_id``          **IDENTITY**         opaque Workday ``detail.id``; stable and
                                            does not embed title or location
``raw.jobpostingid``    secondary slug key  embeds the title; a retitle changes it, so
(``jobPostingId``)      (not identity)      it must never be identity
``raw.jobreqid``        duplicate key       one requisition can appear as several
(``jobReqId``)          (not identity)      postings: multi-city, re-advertisement
``content_hash``        **VERSION SIGNATURE** title+location+description; changes mean
                                            REVISION on the same identity
title+description       duplicate key       same role advertised again under a new id
``job_location``        version component   parts of one posting's version signature and
                        + city discriminator the multi-city discriminator
``first_seen_at``       **OURS, write-once** never overwritten by a later snapshot
``source_posted_at``    source claim        the source's own date, not our first sight
======================  ==================  ============================================

Change vocabulary (closed; ``DEDUP_VOCABULARY``)
-------------------------------------------------
``NEW_POSTING``               no earlier posting matches; the only state that counts as
                              new posting demand (and even then it is demand *as posted*,
                              not a hire)
``REVISION``                  same identity, changed content hash
``REPOST_OF_SAME_REQUISITION`` new identity, same requisition, same (or unknown) city
``MULTI_CITY_COPY``           new identity, same role/requisition in a different city
``DUPLICATE_REPUBLICATION``   new identity, byte-identical normalised content
``MULTI_SITE_COPY``           new identity, another career-site platform
``REAPPEARANCE``              same identity returns after being absent from a snapshot
``REMOVAL``                   posting absent from a *complete* current snapshot
``UNCHANGED``                 same identity, same version signature
``ABSENCE_UNATTRIBUTED``      absent from an incomplete snapshot: not a removal

``counts_as_new_demand`` is ``True`` **only** for ``NEW_POSTING`` seen from a
complete previous snapshot. No other state increments demand: a repost is not new
demand and a disappearance is not a hire.

Purity and the store
--------------------
No network, no database, no clock, and **no persistence**: append-only storage with
write-once ``first_seen_at`` is ``medradar.recruitment.store``'s job, and this module
never touches its files. ``observed_at`` is a parameter; when a caller does not
supply one it is recorded as ``None`` rather than invented. ``diff_snapshots`` is
the deduplication-aware analytical diff the store may call; ``STORE_STATE_MAP``
translates its states onto the store's own vocabulary so a second, conflicting
state machine is not created. File access is none (unlike ``taxonomy.py``, this
module needs no configuration).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from . import records as rec

SCHEMA_VERSION = "recruitment-identity-v1"
#: Version of the identity/versioning logic. Bump when a *rule* changes.
RULES_VERSION = "recruitment_identity_rules_2026-11-04"

#: The one field that constitutes identity. Everything else is a duplicate key.
IDENTITY_FIELD = "posting_id"
#: Version signature function; the same one ``records`` uses for content hashing.
VERSION_SIGNATURE_FIELD = "content_sha256"
VERSION_SIGNATURE_RULE = "records.content_hash over normalised (title, location, description)"

# ----------------------------------------------------------------------- states
STATE_NEW = "NEW_POSTING"
STATE_REVISION = "REVISION"
STATE_REPOST = "REPOST_OF_SAME_REQUISITION"
STATE_MULTI_CITY = "MULTI_CITY_COPY"
STATE_DUPLICATE = "DUPLICATE_REPUBLICATION"
STATE_MULTI_SITE = "MULTI_SITE_COPY"
STATE_REAPPEARANCE = "REAPPEARANCE"
STATE_REMOVAL = "REMOVAL"
STATE_UNCHANGED = "UNCHANGED"
STATE_ABSENCE_UNATTRIBUTED = "ABSENCE_UNATTRIBUTED"

CHANGE_STATES = (
    STATE_NEW,
    STATE_REVISION,
    STATE_REPOST,
    STATE_MULTI_CITY,
    STATE_DUPLICATE,
    STATE_MULTI_SITE,
    STATE_REAPPEARANCE,
    STATE_REMOVAL,
    STATE_UNCHANGED,
    STATE_ABSENCE_UNATTRIBUTED,
)

#: Duplicate-cluster vocabulary (a snapshot-level view, not a change event).
CLUSTER_SAME_POSTING_ID = "SAME_POSTING_ID"
CLUSTER_SAME_REQUISITION = "SAME_REQUISITION"
CLUSTER_MULTI_CITY = "MULTI_CITY_COPY"
CLUSTER_MULTI_SITE = "MULTI_SITE_COPY"
CLUSTER_DUPLICATE = "DUPLICATE_REPUBLICATION"
CLUSTER_KINDS = (
    CLUSTER_SAME_POSTING_ID,
    CLUSTER_SAME_REQUISITION,
    CLUSTER_MULTI_CITY,
    CLUSTER_MULTI_SITE,
    CLUSTER_DUPLICATE,
)

#: Mapping onto the persistence vocabulary already owned by
#: ``medradar.recruitment.store`` (NEW_POSTING / UNCHANGED / REVISION / REMOVED /
#: REAPPEARED / UNREADABLE). ``identity`` does not persist anything: the store
#: owns the append-only files and its own state machine. This mapping exists so a
#: caller that feeds identity's deduplication-aware diff into the store does not
#: invent a *second* state vocabulary; the duplicate states are written as
#: NEW_POSTING by the store (they are new identities) while identity's
#: ``counts_as_new_demand`` stays False, so a demand series must read identity's
#: flag and never the store's NEW counter alone.
STORE_STATE_MAP = {
    STATE_NEW: "NEW_POSTING",
    STATE_REVISION: "REVISION",
    STATE_UNCHANGED: "UNCHANGED",
    STATE_REMOVAL: "REMOVED",
    STATE_REAPPEARANCE: "REAPPEARED",
    STATE_ABSENCE_UNATTRIBUTED: "UNREADABLE",
    STATE_REPOST: "NEW_POSTING",
    STATE_MULTI_CITY: "NEW_POSTING",
    STATE_DUPLICATE: "NEW_POSTING",
    STATE_MULTI_SITE: "NEW_POSTING",
}

#: Human-readable Chinese labels, for the review report (the store owns its own copy).
STATE_LABELS_ZH = {
    STATE_NEW: "新增观察",
    STATE_REVISION: "描述修订",
    STATE_REPOST: "同一需求重发（非新增）",
    STATE_MULTI_CITY: "多城市副本（非新增）",
    STATE_DUPLICATE: "重复发布（非新增）",
    STATE_MULTI_SITE: "多站点镜像（非新增）",
    STATE_REAPPEARANCE: "重新出现（非新增）",
    STATE_REMOVAL: "本次未见（下架/关闭/迁移，原因未知；不代表已招聘）",
    STATE_UNCHANGED: "无变化",
    STATE_ABSENCE_UNATTRIBUTED: "不完整快照中不可归因的缺失（不是下架）",
}

#: Every state except ``NEW_POSTING`` is a reason a count is *not* new demand.
#: ``NEW_POSTING`` itself is only new demand when the previous snapshot was complete.
DEMAND_STATES = (STATE_NEW,)
NON_DEMAND_STATES = tuple(state for state in CHANGE_STATES if state not in DEMAND_STATES)

INTERPRETATIONS = {
    STATE_NEW: (
        "A posting not matched to any earlier observation. Counts as new posting demand only when the "
        "previous snapshot was complete; this is demand as advertised, not a hire."
    ),
    STATE_REVISION: (
        "The same posting identity with changed content (description/title/location edit). A revision, "
        "not a new posting; the posting was already counted when first seen."
    ),
    STATE_REPOST: (
        "A new posting identity for a requisition already observed. A re-advertisement of the same "
        "requisition, not new demand."
    ),
    STATE_MULTI_CITY: (
        "The same role advertised under a new identity in a different city. Treated as a multi-city copy "
        "of one role, NOT new demand. Ambiguity: when the city copies carry different requisitions the "
        "source does not distinguish one role advertised in several cities from several simultaneous "
        "openings; the conservative reading (one role) is recorded and the ambiguity is flagged."
    ),
    STATE_DUPLICATE: (
        "Byte-identical normalised content (title+location+description) under a new posting identity. "
        "Treated as a duplicate re-publication, NOT new demand. Ambiguity: when the duplicate carries a "
        "different requisition it may instead be several simultaneous openings for the same role "
        "(multiple headcount); the source does not distinguish these, so it is not counted as new demand "
        "and is flagged as undecidable."
    ),
    STATE_MULTI_SITE: (
        "The same posting served by a different career-site platform. A mirror copy, not new demand."
    ),
    STATE_REAPPEARANCE: (
        "The same posting identity returns after being absent from an earlier snapshot. It was already "
        "counted at first sight; reappearance is not new demand."
    ),
    STATE_REMOVAL: (
        "The posting is absent from a complete current snapshot. Removal from the source is NOT a hire: "
        "the person may or may not have been hired, the role may have been withdrawn or reposted "
        "elsewhere. No hire is inferred."
    ),
    STATE_UNCHANGED: (
        "The posting is present with the same version signature. A check result, not a change event."
    ),
    STATE_ABSENCE_UNATTRIBUTED: (
        "The posting is absent from an incomplete snapshot (truncated collection, failed details). An "
        "absence that cannot be attributed is not a removal and must not be counted as one."
    ),
}

#: Programmatic version of the identity rule table (field, role, why).
IDENTITY_RULE_TABLE = (
    {
        "field": "posting_id",
        "role": "IDENTITY",
        "source": "Workday jobPostingInfo.id (opaque)",
        "why": "opaque and stable across re-publication; it does not embed the job title or location",
        "is_identity": True,
    },
    {
        "field": "raw.job_posting_id_slug (jobPostingId)",
        "role": "SECONDARY_SLUG_KEY",
        "source": "Workday jobPostingId",
        "why": "the slug embeds the job title (e.g. 'R-D-Engineer-I_R77874-1'), so retitling the same "
               "posting changes the slug; using it as identity would report an edit as a new job",
        "is_identity": False,
    },
    {
        "field": "raw.job_req_id (jobReqId)",
        "role": "DUPLICATE_KEY_REQUISITION",
        "source": "Workday jobReqId (or the trailing _R<digits> of the slug/path)",
        "why": "one requisition can appear as several postings (multi-city, re-advertisement); using it "
               "as identity would merge distinct postings",
        "is_identity": False,
    },
    {
        "field": "content_sha256",
        "role": "VERSION_SIGNATURE",
        "source": "records.content_hash(title, location, description)",
        "why": "a whitespace-only re-render is not a revision while a changed requirement sentence is; "
               "the version signature decides REVISION vs UNCHANGED on a stable identity",
        "is_identity": False,
    },
    {
        "field": "job_location (+ additional_locations)",
        "role": "VERSION_COMPONENT_AND_CITY_DISCRIMINATOR",
        "source": "Workday location",
        "why": "part of the version signature and the discriminator between 'same role, different city' "
               "and a straight duplicate",
        "is_identity": False,
    },
    {
        "field": "first_seen_at",
        "role": "OURS_WRITE_ONCE",
        "source": "collector clock",
        "why": "ours, written once; a later snapshot that observes the same posting is a re-observation "
               "and must never move the first-seen date, and never becomes the source posting date",
        "is_identity": False,
    },
    {
        "field": "source_posted_at",
        "role": "SOURCE_CLAIM",
        "source": "Workday startDate with a stated quality",
        "why": "the source's own claim about when the advert went live; it is not our first sight and "
               "must not be conflated with it",
        "is_identity": False,
    },
)

DEDUP_VOCABULARY = {
    state: {"interpretation": INTERPRETATIONS[state], "counts_as_new_demand": state in DEMAND_STATES}
    for state in CHANGE_STATES
}
CLUSTER_VOCABULARY = {
    CLUSTER_SAME_POSTING_ID: "the same opaque posting id appears more than once in one snapshot",
    CLUSTER_SAME_REQUISITION: "several postings share a requisition (re-advertisement / split posting)",
    CLUSTER_MULTI_CITY: "one role/requisition advertised in more than one city",
    CLUSTER_MULTI_SITE: "the same posting content served by more than one career-site platform",
    CLUSTER_DUPLICATE: "byte-identical normalised content under different posting ids",
}

# ---------------------------------------------------------------------- helpers
_SLUG_REQ_RE = re.compile(r"[_-](R\d{4,})(?:[_-]\d+)?$", re.IGNORECASE)
_SLUG_STRIP_RE = re.compile(r"[_-]R\d{4,}(?:[_-]\d+)?$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def _value(job: Any, *names: str) -> Any:
    for name in names:
        value = job.get(name) if isinstance(job, Mapping) else getattr(job, name, None)
        if value not in (None, "", []):
            return value
    return None


def _raw(job: Any) -> Mapping[str, Any]:
    raw = _value(job, "raw")
    return raw if isinstance(raw, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return rec.normalise_text(str(value))


def _collapse_lower(value: Any) -> str:
    return _WS_RE.sub(" ", _text(value)).strip().lower()


def _require(value: Any, field: str, job: Any) -> str:
    if value in (None, ""):
        raise ValueError(
            f"cannot establish {field} for observation: {IDENTITY_FIELD} is required and a synthetic or "
            f"missing id is not an identity ({type(job).__name__})"
        )
    return str(value)


# ------------------------------------------------------------------- identity
def canonical_posting_key(job: Any) -> str:
    """The stable identity key: ``platform:company:posting_id``.

    The opaque ``posting_id`` is the identity. The slug (which embeds the title),
    the requisition (which spans cities) and the content hash are explicitly *not*
    identity; they are duplicate/version keys used below.
    """
    company = _require(_value(job, "company_key"), "company_key", job)
    platform = _require(_value(job, "source_platform"), "source_platform", job)
    posting_id = _require(_value(job, "posting_id"), "posting_id", job)
    return f"{platform}|{company}|{posting_id}"


def identity_basis(job: Any) -> dict[str, Any]:
    """Which field supplied identity, and whether any fallback was involved.

    Identity is only ever the opaque posting id. A posting with no id cannot be
    given an identity; this function never falls back to the title slug silently.
    """
    posting_id = _value(job, "posting_id")
    opaque = _raw(job).get("opaque_posting_id")
    kind = _raw(job).get("posting_id_kind")
    return {
        "field": IDENTITY_FIELD,
        "value": str(posting_id) if posting_id else None,
        "source": "opaque source id (Workday jobPostingInfo.id)",
        "opaque_field_agrees": (str(posting_id) == str(opaque)) if opaque else None,
        "collector_identity_kind": kind,
        "fallback_used": bool(kind and kind != "id"),
        "canonical_posting_key": canonical_posting_key(job) if posting_id else None,
        "note": (
            "identity is the opaque id only; jobPostingId (a title-bearing slug) and jobReqId (a "
            "requisition) are duplicate-detection keys and never identity"
        ),
    }


def requisition_key(job: Any) -> dict[str, Any]:
    """The requisition (``jobReqId``) or the slug's trailing ``_R<digits>``, if any."""
    raw = _raw(job)
    direct = raw.get("job_req_id")
    if direct not in (None, ""):
        return {"key": str(direct).strip(), "source": "raw.job_req_id", "value": str(direct).strip()}
    for field in ("job_posting_id_slug", "external_path"):
        candidate = raw.get(field)
        if candidate:
            match = _SLUG_REQ_RE.search(str(candidate))
            if match:
                return {
                    "key": match.group(1).upper(),
                    "source": f"slug_suffix:{field}",
                    "value": match.group(1).upper(),
                }
    return {"key": None, "source": None, "value": None}


def slug_title(job: Any) -> str | None:
    """The title as embedded in the posting slug, normalised — a duplicate key only."""
    raw = _raw(job)
    slug = raw.get("job_posting_id_slug")
    if not slug:
        external = raw.get("external_path")
        if external:
            slug = str(external).rstrip("/").rsplit("/", 1)[-1]
    if not slug:
        return None
    stem = _SLUG_STRIP_RE.sub("", str(slug))
    return _collapse_lower(stem.replace("-", " "))


def normalised_title(job: Any) -> str:
    return _collapse_lower(_value(job, "job_title", "title"))


def location_set(job: Any) -> set[str]:
    """Normalised main + additional locations of one posting."""
    values: list[Any] = [_value(job, "job_location", "location")]
    extra = _value(job, "additional_locations", "additionalLocations") or []
    if isinstance(extra, (list, tuple)):
        values.extend(extra)
    return {_collapse_lower(value) for value in values if _collapse_lower(value)}


def _location_comparison(left: Any, right: Any) -> str:
    """``different`` / ``same`` / ``unknown`` for the multi-city discriminator."""
    left_set = location_set(left)
    right_set = location_set(right)
    if not left_set or not right_set:
        return "unknown"
    return "same" if left_set & right_set else "different"


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def body_signature(job: Any) -> str:
    """Title+description signature, deliberately excluding location.

    Two city copies of one role normally share this signature; that is what makes
    them a multi-city copy rather than two independent postings. It is a duplicate
    key, never an identity.
    """
    return _digest({"title": normalised_title(job), "description": _collapse_lower(_value(job, "job_description", "description"))})


def current_hash_rule_version() -> str:
    """The ``records`` content-hash rule version (a one-line normalisation change is a rule change)."""
    return str(getattr(rec, "HASH_RULE_VERSION", "UNSTATED"))


def version_evidence(job: Any) -> dict[str, Any]:
    """The version signature, the hash rule it is computed under, and what it came from.

    The signature is **always recomputed from the fields under the current
    ``records.content_hash`` rule**. That is deliberate: if the rule changes, a
    naive comparison of *stored* hashes would report every posting as edited, and a
    naive comparison of *computed* hashes across two rule versions is impossible to
    express — but recomputation makes both snapshots comparable in the only way that
    matters (same text, same signature), while the recorded rule version is carried
    so nobody can silently cross a rule change.

    ``hash_rule_version`` is the rule the *source artifact* recorded (``None`` when
    the artifact predates the field). ``hash_rule_inferred`` reconstructs the
    effective rule from the data: ``current`` when the stored hash equals a current
    recomputation, ``superseded`` when it does not, ``unstated`` when there is no
    stored hash at all. It is inference about the artifact, not a licence to compare
    stored hashes across a rule change.
    """
    title = _value(job, "job_title", "title")
    location = _value(job, "job_location", "location")
    description = _value(job, "job_description", "description")
    computed = rec.content_hash(title=title, location=location, description=description)
    recorded = _value(job, VERSION_SIGNATURE_FIELD)
    recorded_rule = _value(job, "hash_rule_version")
    current_rule = current_hash_rule_version()
    if not recorded:
        inferred = "unstated"
    elif str(recorded) == computed:
        inferred = "current"
    else:
        inferred = "superseded"
    return {
        "signature": computed,
        "rule": VERSION_SIGNATURE_RULE,
        "hash_rule_version": str(recorded_rule) if recorded_rule else None,
        "current_hash_rule_version": current_rule,
        "hash_rule_matches_current": (str(recorded_rule) == current_rule) if recorded_rule else None,
        "hash_rule_inferred": inferred,
        "computed_from": {
            "title_chars": len(_text(title)),
            "location_chars": len(_text(location)),
            "description_chars": len(_text(description)),
        },
        "recorded_signature": str(recorded) if recorded else None,
        "recorded_agrees": (str(recorded) == computed) if recorded else None,
    }


def version_signature(job: Any) -> str:
    """The content hash that decides REVISION vs UNCHANGED on a stable identity.

    The signature is recomputed from the fields, always under the *current* hash
    rule; :func:`version_evidence` carries the hash-rule version so a comparison
    across a rule change is visible instead of silent.
    """
    return version_evidence(job)["signature"]


def version_signature_rule() -> dict[str, Any]:
    """The version-signature definition, including the hash rule version."""
    return {
        "rule": VERSION_SIGNATURE_RULE,
        "hash_rule_version": current_hash_rule_version(),
        "recomputed_from_fields": True,
        "note": ("signatures are recomputed from title/location/description under the current records rule, "
                 "so two snapshots collected under different rules are content-comparable; stored hashes "
                 "are NOT comparable across a rule change and the diff reports the comparison as such"),
    }


def content_hash_agreement(observations: Iterable[Any]) -> dict[str, Any]:
    """Does each stored ``content_sha256`` equal a recomputation under the *current* rule?

    This is an integrity check, not a version rule: the version signature is always
    recomputed from the fields (so a rules change cannot silently turn every posting
    into a revision), while the stored hash is what the collector wrote. A disagreeing
    stored hash means the snapshot was hashed under a different ``records.content_hash``
    version (e.g. ``records.py`` changed during a running collection) or the fields were
    edited after hashing. A *mixture* of agreeing and disagreeing rows is corruption.
    """
    agree = disagree = missing = 0
    for job in observations:
        recorded = _value(job, VERSION_SIGNATURE_FIELD)
        if not recorded:
            missing += 1
            continue
        if version_signature(job) == str(recorded):
            agree += 1
        else:
            disagree += 1
    checked = agree + disagree
    recorded_versions: set[str] = set()
    inferred: dict[str, int] = {}
    for job in observations:
        record = _value(job, "hash_rule_version")
        recorded_versions.add(str(record) if record else "unstated")
        evidence = version_evidence(job)
        inferred[evidence["hash_rule_inferred"]] = inferred.get(evidence["hash_rule_inferred"], 0) + 1
    return {
        "checked": checked,
        "agree": agree,
        "disagree": disagree,
        "missing": missing,
        "agreement_rate": (round(agree / checked, 6) if checked else None),
        "uniform": (agree == 0 or disagree == 0),
        "current_hash_rule_version": current_hash_rule_version(),
        "recorded_hash_rule_versions": sorted(recorded_versions),
        "inferred_rules": dict(sorted(inferred.items())),
        "inferred_rule": ("current" if inferred.get("current") == checked and checked
                          else "superseded" if inferred.get("superseded") == checked and checked
                          else "unstated" if inferred.get("unstated") == checked
                          else "mixed"),
        "note": (
            "The version signature is always recomputed from title/location/description with the current "
            "records.content_hash, so identity/version logic is unaffected by a stored-hash mismatch; a "
            "uniform disagreement indicates the snapshot was collected under a different records version. "
            "A recorded hash_rule_version that is not the current one makes STORED hashes incomparable, "
            "not the recomputed signatures."
        ),
    }


def hash_rule_comparability(previous: Iterable[Any], current: Iterable[Any]) -> dict[str, Any]:
    """May stored content hashes from these two snapshots be compared at all?

    The diff never compares stored hashes (it recomputes version signatures from
    the fields under the current rule), so a *content* comparison across a rule
    change is valid. What is not valid — and is refused here — is treating a stored
    ``content_sha256`` difference as a description edit when the two artifacts were
    hashed under different rules (the run-1 → run-2 case: 992 stored hashes moved
    while zero descriptions changed).
    """
    previous_report = content_hash_agreement(previous)
    current_report = content_hash_agreement(current)
    problems: list[str] = []
    for label, report in (("previous", previous_report), ("current", current_report)):
        if report["inferred_rule"] == "superseded":
            problems.append(f"{label} snapshot stored hashes were produced under a superseded rule")
        elif report["inferred_rule"] == "mixed":
            problems.append(f"{label} snapshot mixes hash rules")
        recorded = [v for v in report["recorded_hash_rule_versions"] if v != "unstated"]
        if recorded and any(v != report["current_hash_rule_version"] for v in recorded):
            problems.append(f"{label} snapshot records hash_rule_version(s) {recorded}, "
                            f"current is {report['current_hash_rule_version']}")
    comparable = not problems
    return {
        "stored_hash_comparable": comparable,
        "reason": ("stored content hashes are comparable" if comparable else "; ".join(problems)),
        "previous": previous_report,
        "current": current_report,
        "recomputed_signatures_comparable": True,
        "note": (
            "version signatures are recomputed from fields under the current records rule, so content can "
            "be compared across a hash-rule change; stored content_sha256 values cannot, and are not used "
            "for the comparison. Never report stored-hash movement as a description revision across a rule "
            "change (the store records HASH_RULE_REBASELINED instead)."
        ),
    }


def _changed_fields(previous: Any, current: Any) -> list[str]:
    changed: list[str] = []
    if _text(_value(previous, "job_title", "title")) != _text(_value(current, "job_title", "title")):
        changed.append("title")
    if _collapse_lower(_value(previous, "job_location", "location")) != _collapse_lower(
        _value(current, "job_location", "location")
    ):
        changed.append("location")
    if _text(_value(previous, "job_description", "description")) != _text(
        _value(current, "job_description", "description")
    ):
        changed.append("description")
    if _raw(previous).get("job_posting_id_slug") != _raw(current).get("job_posting_id_slug"):
        changed.append("job_posting_id_slug")
    return changed


# --------------------------------------------------------------- duplicate view
def _cluster_members(observations: Sequence[Any], key) -> list[list[Any]]:
    groups: dict[str, list[Any]] = {}
    for job in observations:
        key_value = key(job)
        if key_value is None:
            continue
        groups.setdefault(str(key_value), []).append(job)
    return [members for members in groups.values() if len(members) > 1]


def _cluster_record(kind: str, members: Sequence[Any], *, basis: Mapping[str, Any]) -> dict[str, Any]:
    posting_ids = [str(_value(job, "posting_id")) for job in members]
    locations = sorted({part for job in members for part in location_set(job)})
    platforms = sorted({str(_value(job, "source_platform")) for job in members})
    titles = sorted({normalised_title(job) for job in members})
    requisitions = sorted(
        {requisition_key(job)["key"] for job in members if requisition_key(job)["key"]}
    )
    same_requisition = len(requisitions) == 1 and len(
        {str(_value(job, "posting_id")) for job in members}
    ) > 0
    ambiguity = None
    if kind in (CLUSTER_DUPLICATE, CLUSTER_MULTI_CITY) and not same_requisition:
        ambiguity = (
            "The copies carry different requisitions. The source does not distinguish one advert "
            "re-published/multi-city from several simultaneous openings for the same role (multiple "
            "headcount); this is treated as a copy (not new demand) and the ambiguity is recorded."
        )
    return {
        "cluster_kind": kind,
        "definition": CLUSTER_VOCABULARY[kind],
        "posting_ids": posting_ids,
        "canonical_posting_keys": [canonical_posting_key(job) for job in members],
        "source_platforms": platforms,
        "locations": locations,
        "titles": titles,
        "requisitions": requisitions,
        "same_requisition": same_requisition,
        "ambiguity": ambiguity,
        "hash_rule_versions": sorted(
            {str(_value(job, "hash_rule_version")) if _value(job, "hash_rule_version") else "unstated"
             for job in members}
        ),
        "members": [
            {
                "posting_id": str(_value(job, "posting_id")),
                "canonical_posting_key": canonical_posting_key(job),
                "source_platform": _value(job, "source_platform"),
                "job_location": _value(job, "job_location", "location"),
                "additional_locations": list(_value(job, "additional_locations") or []),
                "location_set": sorted(location_set(job)),
                "requisition": requisition_key(job)["key"],
                "version_signature": version_signature(job),
                "body_signature": body_signature(job),
            }
            for job in members
        ],
        "counts_as_new_demand": False,
        "basis": dict(basis),
    }


def duplicate_clusters(observations: Iterable[Any]) -> list[dict[str, Any]]:
    """Duplicate clusters inside one snapshot, with the evidence that formed them.

    Kinds (``CLUSTER_VOCABULARY``):

    * ``SAME_POSTING_ID`` — the same opaque id observed twice in one snapshot;
    * ``SAME_REQUISITION`` — one requisition split into several postings, same city;
    * ``MULTI_CITY_COPY`` — one role/requisition in more than one city;
    * ``MULTI_SITE_COPY`` — the same content served by more than one platform;
    * ``DUPLICATE_REPUBLICATION`` — byte-identical content under different ids.

    No cluster is a new posting and none counts as demand; this function exists so
    duplicate counts can be *removed* from a demand number rather than inflate it.
    """
    jobs = list(observations)
    clusters: list[dict[str, Any]] = []

    # 1. same opaque id twice
    for members in _cluster_members(jobs, lambda job: _value(job, "posting_id")):
        clusters.append(
            _cluster_record(
                CLUSTER_SAME_POSTING_ID,
                members,
                basis={"key": "posting_id", "value": str(_value(members[0], "posting_id"))},
            )
        )

    # 2. one requisition, several postings
    for members in _cluster_members(jobs, lambda job: requisition_key(job)["key"]):
        comparisons = [
            _location_comparison(left, right)
            for index, left in enumerate(members)
            for right in members[index + 1:]
        ]
        multi_city = any(comparison == "different" for comparison in comparisons)
        platforms = {str(_value(job, "source_platform")) for job in members}
        if len(platforms) > 1:
            kind = CLUSTER_MULTI_SITE
        elif multi_city:
            kind = CLUSTER_MULTI_CITY
        else:
            kind = CLUSTER_SAME_REQUISITION
        clusters.append(
            _cluster_record(
                kind,
                members,
                basis={
                    "key": "job_req_id",
                    "value": requisition_key(members[0])["key"],
                    "location_comparisons": sorted(set(comparisons)),
                    "distinct_locations": len({part for job in members for part in location_set(job)}),
                },
            )
        )

    # 3. identical title+description; city / site decide the kind
    for members in _cluster_members(jobs, body_signature):
        comparisons = [
            _location_comparison(left, right)
            for index, left in enumerate(members)
            for right in members[index + 1:]
        ]
        platforms = {str(_value(job, "source_platform")) for job in members}
        if len(platforms) > 1:
            kind = CLUSTER_MULTI_SITE
        elif any(comparison == "different" for comparison in comparisons):
            kind = CLUSTER_MULTI_CITY
        else:
            kind = CLUSTER_DUPLICATE
        clusters.append(
            _cluster_record(
                kind,
                members,
                basis={
                    "key": "body_signature(title+description)",
                    "value": body_signature(members[0]),
                    "location_comparisons": sorted(set(comparisons)),
                },
            )
        )

    # 4. identical full version signature under different ids
    for members in _cluster_members(jobs, version_signature):
        if len({str(_value(job, "posting_id")) for job in members}) < 2:
            continue  # already covered by SAME_POSTING_ID
        platforms = {str(_value(job, "source_platform")) for job in members}
        kind = CLUSTER_MULTI_SITE if len(platforms) > 1 else CLUSTER_DUPLICATE
        clusters.append(
            _cluster_record(
                kind,
                members,
                basis={"key": "content_hash", "value": version_signature(members[0])},
            )
        )

    # A pair discovered by two keys (e.g. same requisition AND identical content)
    # must be one cluster, not two: keep the first, most specific basis (append
    # order is same-identity, requisition, body, version).
    unique: list[dict[str, Any]] = []
    seen_members: set[frozenset[str]] = set()
    for cluster in clusters:
        members = frozenset(cluster["canonical_posting_keys"])
        if members in seen_members:
            continue
        seen_members.add(members)
        unique.append(cluster)
    unique.sort(key=lambda cluster: (cluster["cluster_kind"], tuple(cluster["posting_ids"])))
    return unique


def deduplicated_count(observations: Iterable[Any]) -> dict[str, Any]:
    """Raw count vs distinct-posting count after duplicate clusters are collapsed.

    This is the number a demand series should use: duplicates inside a snapshot
    must not be counted as separate postings.
    """
    jobs = list(observations)
    keys = [canonical_posting_key(job) for job in jobs]
    clusters = duplicate_clusters(jobs)
    # union the posting ids that belong to the same duplicate cluster
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for cluster in clusters:
        for canonical in cluster["canonical_posting_keys"][1:]:
            union(cluster["canonical_posting_keys"][0], canonical)
    distinct = len({find(key) for key in keys})
    return {
        "raw_observations": len(jobs),
        "distinct_posting_ids": len(set(keys)),
        "distinct_after_dedup": distinct,
        "duplicate_observations": len(set(keys)) - distinct,
        "duplicate_clusters": len(clusters),
        "cluster_kind_counts": _count([cluster["cluster_kind"] for cluster in clusters]),
    }


def _count(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


# --------------------------------------------------------------- snapshot diff
def _index(jobs: Sequence[Any], *, label: str) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """Index a snapshot by identity, and by each duplicate key (first occurrence)."""
    by_key: dict[str, Any] = {}
    warnings: list[str] = []
    duplicate_keys: dict[str, str] = {}
    for job in jobs:
        key = canonical_posting_key(job)
        if key in by_key:
            warnings.append(f"duplicate identity inside {label} snapshot ignored for diff: {key}")
            continue
        by_key[key] = job
    return by_key, warnings, duplicate_keys


def _matches(jobs_by_key: Mapping[str, Any], job: Any, key_name: str) -> list[tuple[str, Any]]:
    target = {
        "requisition": lambda item: requisition_key(item)["key"],
        "body": body_signature,
        "version": version_signature,
        "identity": lambda item: canonical_posting_key(item),
    }[key_name]
    wanted = target(job)
    if wanted in (None, ""):
        return []
    matches = []
    for key, candidate in jobs_by_key.items():
        if canonical_posting_key(candidate) == canonical_posting_key(job):
            continue
        if target(candidate) == wanted:
            matches.append((key, candidate))
    return matches


def _first_seen(job: Any) -> str | None:
    value = _value(job, "first_seen_at")
    return str(value) if value else None


def _event(
    *,
    state: str,
    job: Any,
    first_seen_at: str | None,
    first_seen_source: str | None,
    previous_version_signature: str | None = None,
    matched: Mapping[str, Any] | None = None,
    duplicate: Mapping[str, Any] | None = None,
    changed_fields: Sequence[str] = (),
    first_seen_conflict: Mapping[str, Any] | None = None,
    counts_as_new_demand: bool = False,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    evidence = version_evidence(job)
    return {
        "state": state,
        "counts_as_new_demand": bool(counts_as_new_demand),
        "interpretation": INTERPRETATIONS[state],
        "canonical_posting_key": canonical_posting_key(job),
        "company_key": _value(job, "company_key"),
        "posting_id": str(_value(job, "posting_id")),
        "source_platform": _value(job, "source_platform"),
        "posting_id_kind": _raw(job).get("posting_id_kind"),
        "job_title": _value(job, "job_title", "title"),
        "job_location": _value(job, "job_location", "location"),
        "additional_locations": list(_value(job, "additional_locations") or []),
        "source_posted_at": _value(job, "source_posted_at"),
        "source_posted_quality": _value(job, "source_posted_quality"),
        "source_url": _value(job, "source_url"),
        "collection_status": _value(job, "collection_status"),
        "first_seen_at": first_seen_at,
        "first_seen_at_source": first_seen_source,
        "first_seen_at_conflict": dict(first_seen_conflict) if first_seen_conflict else None,
        "version_signature": evidence["signature"],
        "version_rule": evidence["rule"],
        "hash_rule_version": evidence["hash_rule_version"],
        "current_hash_rule_version": evidence["current_hash_rule_version"],
        "hash_rule_matches_current": evidence["hash_rule_matches_current"],
        "hash_rule_inferred": evidence["hash_rule_inferred"],
        "recorded_content_sha256": evidence["recorded_signature"],
        "recorded_content_sha256_agrees": evidence["recorded_agrees"],
        "previous_version_signature": previous_version_signature,
        "changed_fields": list(changed_fields),
        "matched": dict(matched) if matched else None,
        "duplicate": dict(duplicate) if duplicate else None,
        "requisition": requisition_key(job),
        "body_signature": body_signature(job),
        "notes": list(notes),
    }


def _duplicate_flags(previous: Any, current: Any, *, match_basis: str) -> dict[str, Any]:
    comparison = _location_comparison(previous, current)
    platform_previous = str(_value(previous, "source_platform"))
    platform_current = str(_value(current, "source_platform"))
    same_requisition = requisition_key(previous)["key"] is not None and (
        requisition_key(previous)["key"] == requisition_key(current)["key"]
    )
    same_body = body_signature(previous) == body_signature(current)
    same_version = version_signature(previous) == version_signature(current)
    return {
        "match_basis": match_basis,
        "same_requisition": same_requisition,
        "same_body_signature": same_body,
        "same_version_signature": same_version,
        "location_comparison": comparison,
        "multi_city": comparison == "different",
        "multi_site": platform_previous != platform_current,
        "platform_previous": platform_previous,
        "platform_current": platform_current,
    }


def _state_for_new_identity(flags: Mapping[str, Any]) -> str:
    if flags["multi_site"]:
        return STATE_MULTI_SITE
    if flags["multi_city"]:
        return STATE_MULTI_CITY
    if flags["same_requisition"]:
        return STATE_REPOST
    return STATE_DUPLICATE


def _history_snapshots(history: Any) -> list[dict[str, Any]]:
    """Normalise the optional history argument to ordered {observed_at, observations}."""
    if not history:
        return []
    entries: list[dict[str, Any]] = []
    for item in history:
        if isinstance(item, Mapping) and "observations" in item:
            entries.append({"observed_at": item.get("observed_at"), "observations": list(item["observations"])})
        elif isinstance(item, (list, tuple)):
            entries.append({"observed_at": None, "observations": list(item)})
        else:  # pragma: no cover - defensive
            raise TypeError("history entries must be snapshots or {'observed_at', 'observations'} mappings")
    return entries


def diff_snapshots(
    previous: Sequence[Any],
    current: Sequence[Any],
    *,
    observed_at: str | None = None,
    current_complete: bool = True,
    previous_complete: bool = True,
    history: Any = None,
    include_clusters: bool = True,
) -> dict[str, Any]:
    """Diff two snapshots of the same source into per-posting change events.

    Parameters
    ----------
    previous, current
        Lists of ``JobObservation`` (or their ``to_dict()`` rows). Identity is the
        opaque ``posting_id``; content is the ``records.content_hash``.
    observed_at
        Our observation time for the *current* snapshot. Recorded verbatim; if not
        given it is stored as ``None`` and never invented.
    current_complete, previous_complete
        Whether each snapshot enumerated the source. Absence from a complete
        current snapshot is ``REMOVAL``; absence from an incomplete one is
        ``ABSENCE_UNATTRIBUTED``. ``NEW_POSTING`` counts as new demand only when
        the *previous* snapshot was complete.
    history
        Optional earlier snapshots (oldest .. newest), each either a list of
        observations or ``{"observed_at": ..., "observations": [...]}``. Used to
        distinguish a *repost after removal* / a same-identity *reappearance* from
        genuinely new demand. With only two snapshots the function honestly cannot
        see a removal, so it does not claim one.
    include_clusters
        Also report duplicate clusters inside the current snapshot.

    Returns
    -------
    dict with ``events``, per-state ``counters``, a ``demand`` block that states
    what may and may not be counted, ``first_seen_conflicts`` and the rule versions.

    Guarantees
    ----------
    * ``first_seen_at`` in an event is the earliest value ever recorded for that
      identity (previous / history / current in that order), never the current
      snapshot's rewrite; a disagreement is surfaced as
      ``first_seen_at_conflict`` instead of overwriting.
    * Every non-``NEW_POSTING`` state has ``counts_as_new_demand = False``.
    * No event infers a hire from a removal.
    """
    previous_jobs = list(previous)
    current_jobs = list(current)
    previous_by_key, warnings_previous, _ = _index(previous_jobs, label="previous")
    current_by_key, warnings_current, _ = _index(current_jobs, label="current")
    history_entries = _history_snapshots(history)
    history_indexes = [
        (entry["observed_at"], _index(entry["observations"], label="history")[0]) for entry in history_entries
    ]

    events: list[dict[str, Any]] = []
    first_seen_conflicts: list[dict[str, Any]] = []

    def previous_first_seen(job: Any, key: str) -> tuple[str | None, str | None, dict[str, Any] | None]:
        existing = previous_by_key.get(key)
        current_value = _first_seen(job)
        if existing is not None:
            prior = _first_seen(existing)
            if prior and current_value and prior != current_value:
                conflict = {
                    "canonical_posting_key": key,
                    "previous_first_seen_at": prior,
                    "current_first_seen_at": current_value,
                }
                first_seen_conflicts.append(conflict)
                return prior, "previous", conflict
            return (prior or current_value,
                    "previous" if prior else ("current" if current_value else None),
                    None)
        for history_observed_at, history_index in reversed(history_indexes):
            if key in history_index:
                prior = _first_seen(history_index[key])
                return prior or current_value, "history", None
        return current_value, "current" if current_value else None, None

    # ---- current snapshot: unchanged / revision / repost / new
    for key, job in current_by_key.items():
        previous_job = previous_by_key.get(key)
        if previous_job is not None:
            previous_signature = version_signature(previous_job)
            current_signature = version_signature(job)
            first_seen, first_seen_source, first_seen_conflict = previous_first_seen(job, key)
            if previous_signature == current_signature:
                events.append(
                    _event(
                        state=STATE_UNCHANGED,
                        job=job,
                        first_seen_at=first_seen,
                        first_seen_source=first_seen_source,
                        previous_version_signature=previous_signature,
                        first_seen_conflict=first_seen_conflict,
                    )
                )
            else:
                events.append(
                    _event(
                        state=STATE_REVISION,
                        job=job,
                        first_seen_at=first_seen,
                        first_seen_source=first_seen_source,
                        previous_version_signature=previous_signature,
                        changed_fields=_changed_fields(previous_job, job),
                        first_seen_conflict=first_seen_conflict,
                    )
                )
            continue

        # not in the immediately previous snapshot: established identity may have
        # been observed before and disappeared -> reappearance, never a new posting.
        first_seen, first_seen_source, first_seen_conflict = previous_first_seen(job, key)
        if first_seen_source == "history":
            events.append(
                _event(
                    state=STATE_REAPPEARANCE,
                    job=job,
                    first_seen_at=first_seen,
                    first_seen_source=first_seen_source,
                    first_seen_conflict=first_seen_conflict,
                    matched={"canonical_posting_key": key, "match_basis": "same_identity_in_history"},
                    duplicate={"reappeared_after_absence": True},
                )
            )
            continue

        # A genuinely new identity can still be a duplicate of an existing posting:
        # same requisition (multi-city / repost) or identical content (duplicate).
        match = None
        match_basis = None
        for key_name in ("requisition", "body", "version"):
            found = _matches(previous_by_key, job, key_name)
            if found:
                matched_key, matched_job = found[0]
                match = (matched_key, matched_job)
                match_basis = {
                    "requisition": "same_requisition",
                    "body": "same_body_signature",
                    "version": "same_version_signature",
                }[key_name]
                break

        repost_after_removal = False
        removed_since = None
        if match is None:
            for history_observed_at, history_index in reversed(history_indexes):
                for key_name in ("requisition", "body", "version"):
                    found = _matches(history_index, job, key_name)
                    if not found:
                        continue
                    # only a history match that is absent from the previous snapshot
                    # is a repost after removal; otherwise it is still active and the
                    # previous snapshot already contained it (handled above).
                    active_keys = {canonical_posting_key(candidate) for candidate in previous_by_key.values()}
                    if any(canonical_posting_key(candidate) in active_keys for _, candidate in found):
                        continue
                    matched_key, matched_job = found[0]
                    match = (matched_key, matched_job)
                    match_basis = {
                        "requisition": "same_requisition",
                        "body": "same_body_signature",
                        "version": "same_version_signature",
                    }[key_name]
                    repost_after_removal = True
                    removed_since = history_observed_at
                    break
                if match is not None:
                    break

        if match is not None:
            matched_key, matched_job = match
            flags = _duplicate_flags(matched_job, job, match_basis=match_basis)
            flags["repost_after_removal"] = repost_after_removal
            flags["last_seen_before_removal_at"] = removed_since
            state = _state_for_new_identity(flags)
            notes = ["this identity is new but its requisition/content was observed before; it is "
                     "not new demand"]
            if repost_after_removal:
                notes.append("the earlier posting was absent from the previous snapshot: repost after removal")
            if not flags["same_requisition"] and state in (STATE_DUPLICATE, STATE_MULTI_CITY):
                notes.append(
                    "the copy carries a different requisition: the source does not distinguish a duplicated "
                    "advert from several simultaneous openings for the same role (multiple headcount); it is "
                    "treated as a copy and not counted as new demand"
                )
            events.append(
                _event(
                    state=state,
                    job=job,
                    first_seen_at=first_seen,
                    first_seen_source=first_seen_source,
                    matched={"canonical_posting_key": matched_key, "match_basis": match_basis},
                    duplicate=flags,
                    notes=notes,
                )
            )
            continue

        # genuinely new: counts as new demand only against a complete snapshot
        counts_as_demand = bool(previous_complete)
        events.append(
            _event(
                state=STATE_NEW,
                job=job,
                first_seen_at=first_seen,
                first_seen_source=first_seen_source,
                counts_as_new_demand=counts_as_demand,
                notes=(
                    []
                    if previous_complete
                    else ["the previous snapshot was incomplete, so this observation cannot establish new "
                          "demand and counts_as_new_demand is False"]
                ),
            )
        )

    # ---- postings present before but absent now
    for key, job in previous_by_key.items():
        if key in current_by_key:
            continue
        first_seen = _first_seen(job)
        if not current_complete:
            events.append(
                _event(
                    state=STATE_ABSENCE_UNATTRIBUTED,
                    job=job,
                    first_seen_at=first_seen,
                    first_seen_source="previous" if first_seen else None,
                    notes=["the current snapshot is incomplete; absence cannot be attributed and is not a "
                           "removal"],
                )
            )
            continue
        events.append(
            _event(
                state=STATE_REMOVAL,
                job=job,
                first_seen_at=first_seen,
                first_seen_source="previous" if first_seen else None,
                notes=["removal from the source is not a hire; no hire is inferred from a disappearance"],
            )
        )

    events.sort(key=lambda event: (event["state"], event["canonical_posting_key"]))
    counters = {state: 0 for state in CHANGE_STATES}
    for event in events:
        counters[event["state"]] += 1
    demand_events = sum(1 for event in events if event["counts_as_new_demand"])
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "identity_field": IDENTITY_FIELD,
        "version_signature_rule": version_signature_rule(),
        "observed_at": observed_at,
        "snapshots": {
            "previous_n": len(previous_jobs),
            "current_n": len(current_jobs),
            "previous_complete": bool(previous_complete),
            "current_complete": bool(current_complete),
            "history_snapshots": len(history_entries),
        },
        "events": events,
        "counters": counters,
        "changed_event_count": len(events) - counters[STATE_UNCHANGED],
        "demand": {
            "new_demand_events": demand_events,
            "repost_or_copy_events": counters[STATE_REPOST]
            + counters[STATE_MULTI_CITY]
            + counters[STATE_DUPLICATE]
            + counters[STATE_MULTI_SITE]
            + counters[STATE_REAPPEARANCE],
            "revision_events": counters[STATE_REVISION],
            "removal_events": counters[STATE_REMOVAL],
            "unattributed_absence_events": counters[STATE_ABSENCE_UNATTRIBUTED],
            "statement": (
                "Only NEW_POSTING against a complete previous snapshot counts as new posting demand. A "
                "repost, multi-city copy, duplicate, mirror copy or reappearance is not new demand; a "
                "REMOVAL is not a hire."
            ),
        },
        "first_seen_conflicts": first_seen_conflicts,
        "content_hash_integrity": content_hash_agreement(previous_jobs + current_jobs),
        "hash_rule": hash_rule_comparability(previous_jobs, current_jobs),
        "warnings": warnings_previous + warnings_current,
    }
    if include_clusters:
        result["current_clusters"] = duplicate_clusters(current_jobs)
        result["current_dedup"] = deduplicated_count(current_jobs)
    return result


def reconcile_first_seen(previous: Sequence[Any], current: Sequence[Any]) -> list[dict[str, Any]]:
    """Return the current snapshot with ``first_seen_at`` carried forward, write-once.

    The collector may re-observe a posting and stamp a new ``first_seen_at``; that
    must never reach storage. For every identity already known, the stored
    ``first_seen_at`` wins. The returned rows are copies and are otherwise exactly
    the current snapshot.
    """
    known = {
        canonical_posting_key(job): _first_seen(job)
        for job in previous
        if _first_seen(job) is not None
    }
    reconciled: list[dict[str, Any]] = []
    for job in current:
        row = job.to_dict() if hasattr(job, "to_dict") else dict(job)  # type: ignore[arg-type]
        key = canonical_posting_key(row)
        if key in known and known[key]:
            row["first_seen_at"] = known[key]
        reconciled.append(row)
    return reconciled


# --------------------------------------------------------------------- report
def identity_rule_table_markdown() -> str:
    """The identity rule table as markdown, for a research report or DECISIONS entry."""
    lines = ["| source field | role | identity? | why |", "|---|---|---|---|"]
    for rule in IDENTITY_RULE_TABLE:
        lines.append(
            f"| `{rule['field']}` | {rule['role']} | {'YES' if rule['is_identity'] else 'no'} | {rule['why']} |"
        )
    return "\n".join(lines)


def change_vocabulary_markdown() -> str:
    """The closed change vocabulary and its demand interpretation, as markdown."""
    lines = ["| state | counts as new demand? | interpretation |", "|---|---|---|"]
    for state in CHANGE_STATES:
        lines.append(
            f"| `{state}` | {'yes' if state in DEMAND_STATES else 'no'} | {INTERPRETATIONS[state]} |"
        )
    return "\n".join(lines)
