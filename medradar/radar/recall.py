"""Monitoring-device screening for FDA device-recall records (V1-001).

Why this module exists
----------------------
The radar lane had no recall channel at all: config/radar/sources.json named
/device/recall.json as a read path and no adapter implemented it, so the ledger held 0
recall rows while openFDA held hundreds for the same monitored product codes. Adding the
adapter is not enough - a recall feed is only useful if the product in it can be classified
as a monitoring device, and that classification must be inspectable and testable.

Two identities, deliberately separate
-------------------------------------
* A **product record** (product_res_number, e.g. Z-0034-2026) is one recalled product.
  That is what openFDA publishes as a row, and it is what the observation is identified by,
  so re-collecting the same row is the same observation.
* A **recall event** (res_event_number) is the FDA action that may cover several products.
  Counting rows as events overstates what happened: the 2026 monitoring recalls are 42 rows
  but 19 events. The event number is stored as an official identifier, so an event-level
  count is a GROUP BY over the existing identifier table - not a second table and not a
  second fact store.

Screening tiers
---------------
No single signal decides on its own, and nothing is silently dropped:

PRODUCT_CODE     the row's official FDA product code is one the committed taxonomy maps to
                 a monitored device family. Strong: it is FDA's own classification.
DEVICE_TEXT      the code is not monitored, but the official product description or the
                 reason for recall names a monitoring device or measurement. Real evidence,
                 but the classification is ours, so it goes to REVIEW.
UNCONFIRMED      the recalling firm resolves to a monitoring vendor and the text names a
                 monitoring word only vaguely. A vendor name is never sufficient, so this
                 goes to REVIEW instead of being counted as monitoring intelligence.
OUT_OF_SCOPE     none of the above. Stored, excluded with a reason, and counted in the
                 out-of-scope block of the report. Never deleted.

The screening is a *rule*, not stored in the record payload: the payload is what the source
said and its hash is the observation identity, so re-running a later version of these rules
must not read as a source correction. Callers re-derive the verdict from the payload.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

#: Identifier kinds written to observation_identifier for recall rows.
RECALL_EVENT_IDENTIFIER = "FDA_RECALL_EVENT"
RECALL_PRODUCT_IDENTIFIER = "FDA_RECALL_PRODUCT"

#: Basis values (closed vocabulary: callers and tests switch on them).
BASIS_PRODUCT_CODE = "PRODUCT_CODE"
BASIS_DEVICE_TEXT = "DEVICE_TEXT"
BASIS_UNCONFIRMED = "UNCONFIRMED"
BASIS_OUT_OF_SCOPE = "OUT_OF_SCOPE"
BASES = (BASIS_PRODUCT_CODE, BASIS_DEVICE_TEXT, BASIS_UNCONFIRMED, BASIS_OUT_OF_SCOPE)

#: Text that names a monitored device class in a regulatory product description.
#: Deliberately narrower than the publication vocabulary in assessment.py: the genre is an
#: official product line ("Patient Monitor, Model X"), not a research title.
DEVICE_TEXT = re.compile("|".join("(?:%s)" % pattern for pattern in (
    r"\bpatient monitors?\b", r"\bphysiological monitors?\b", r"\bphysiologic monitors?\b",
    r"\bcardiac monitors?\b", r"\bbedside monitors?\b", r"\bcentral (?:station|monitoring)\b",
    r"\bcentral station\b", r"\bmonitoring (?:system|network|platform|station)\b",
    r"\btelemetry\b", r"\b(?:pulse )?oximet(?:er|ers|ry)\b", r"\bspo2\b",
    r"\boxygen saturation\b", r"\bcapnogra(?:ph|phy|phic)\b", r"\bend[- ]tidal\b",
    r"\belectrocardiogra(?:ph|m|phy|phic)s?\b", r"\becg\b", r"\bekg\b",
    r"\barrhythmia\b", r"\bholter\b",
    r"\bblood pressure (?:monitor|monitoring|cuff|transducer|sensor)\b",
    r"\bsphygmomanometer\b", r"\bnibp\b", r"\binvasive blood pressure\b",
    r"\bha?emodynamic (?:monitor|monitoring|system)\b", r"\bcerebral oximet",
    r"\bnear[- ]infrared spectroscopy\b", r"\bcerebral (?:oxygen|oxygenation)\b",
    r"\bcontinuous eeg\b", r"\belectroencephalogra", r"\bintracranial pressure\b",
    r"\bapnea monitor\b", r"\brespiratory (?:monitor|rate monitor)\b",
    r"\btemperature monitor\b", r"\bmulti-?parameter\b", r"\bvital signs? monitor",
    r"\bclinical (?:monitor|information system)\b", r"\barrhythmia (?:detector|alarm)\b",
)), re.IGNORECASE)
#: A monitoring word that is too generic to confirm a device on its own.
VAGUE_MONITORING = re.compile(r"\bmonitor(?:ing|s|ed)?\b", re.IGNORECASE)
#: Text that names a device family the V1 scope deliberately excludes, used only to explain
#: an exclusion (never to delete the row).
NON_MONITORING_HINT = re.compile(
    r"\b(?:catheter|stent|implant|surgical (?:instrument|mesh)|orthop(?:a|e)dic|dental|"
    r"wheelchair|condom|contact lens|infusion (?:set|pump)|syringe|needle|scalpel|"
    r"endoscope|x-?ray|mri|ct scanner|ultrasound (?:system|probe)|mammograph|"
    r"in vitro diagnostic|reagent|test kit)",
    re.IGNORECASE,
)

#: Fields of one openFDA recall row that constitute its content.
RECALL_PAYLOAD_FIELDS = (
    "cfres_id", "product_res_number", "res_event_number", "recalling_firm", "product_code",
    "product_description", "reason_for_recall", "root_cause_description", "action",
    "recall_status", "event_date_initiated", "event_date_posted", "event_date_terminated",
    "k_numbers", "distribution_pattern", "code_info", "product_quantity", "city", "state",
)


def is_recall_payload(payload: Mapping[str, Any] | None) -> bool:
    """True when a regulatory_record payload is an FDA recall row.

    The discriminator is the source's own event number. It is stable content, so a rule
    change can never make a 510(k) look like a recall.
    """
    return bool((payload or {}).get("res_event_number"))


def recall_event_id(payload: Mapping[str, Any] | None) -> str | None:
    value = str((payload or {}).get("res_event_number") or "").strip()
    return value or None


def recall_product_id(payload: Mapping[str, Any] | None) -> str | None:
    value = str((payload or {}).get("product_res_number") or "").strip()
    return value or None


def monitoring_codes(taxonomy: Any | None) -> dict[str, dict[str, Any]]:
    """Official product code -> the committed taxonomy topics that classify it as monitoring.

    This is the *only* place the code list comes from, so the recall screen cannot drift away
    from the taxonomy the rest of the system uses. A registry failure yields an empty map, and
    every row then falls back to text screening instead of being treated as confirmed.
    """
    codes: dict[str, dict[str, Any]] = {}
    if taxonomy is None:
        return codes
    try:
        topics = list(getattr(taxonomy, "topics", ()) or ())
    except Exception:  # noqa: BLE001 - a registry failure must not invent a classification
        return codes
    for topic in topics:
        topic_id = str(getattr(topic, "id", None) or getattr(topic, "topic_id", "") or "")
        for entry in getattr(topic, "product_codes", ()) or ():
            # topics.json carries objects, Taxonomy normalises them to code strings; accept both
            # so the screen keeps working if the registry shape changes.
            code = str(
                entry.get("code") if isinstance(entry, Mapping) else entry
            ).strip().upper()
            if not code:
                continue
            bucket = codes.setdefault(code, {"topics": []})
            if topic_id and topic_id not in bucket["topics"]:
                bucket["topics"].append(topic_id)
    return codes


def _text(payload: Mapping[str, Any]) -> str:
    official = payload.get("openfda_device")
    device_name = ""
    if isinstance(official, Mapping):
        device_name = str(official.get("device_name") or "")
    return " ".join(filter(None, [
        device_name,
        *(str(payload.get(field) or "") for field in
          ("product_description", "reason_for_recall", "action", "code_info")),
    ]))


def screen_recall(payload: Mapping[str, Any] | None, *,
                  codes: Mapping[str, Any] | None = None,
                  taxonomy: Any | None = None) -> dict[str, Any]:
    """Classify one recall row against the monitoring scope.

    Returns a plain dict so it can be logged, asserted on and rendered:

    basis          one of BASES
    in_scope       true for PRODUCT_CODE and DEVICE_TEXT (DEVICE_TEXT needs review)
    needs_review   true when the classification is ours rather than the FDA's
    code_topics    taxonomy topic ids for the product code
    matched_terms  device-text terms that fired
    reason         one human-readable sentence
    """
    payload = dict(payload or {})
    code = str(payload.get("product_code") or "").strip().upper()
    code_map = dict(codes) if codes is not None else monitoring_codes(taxonomy)
    text = _text(payload)
    matched = sorted({match.group(0).lower() for match in DEVICE_TEXT.finditer(text)})

    if code and code in code_map:
        return {
            "basis": BASIS_PRODUCT_CODE,
            "in_scope": True,
            "needs_review": False,
            "code": code,
            "code_topics": list(code_map[code].get("topics") or ()),
            "matched_terms": matched[:8],
            "reason": (
                "product code " + code + " is classified by the committed taxonomy as a "
                "monitoring device family"
            ),
        }
    if matched:
        return {
            "basis": BASIS_DEVICE_TEXT,
            "in_scope": True,
            "needs_review": True,
            "code": code or None,
            "code_topics": [],
            "matched_terms": matched[:8],
            "reason": (
                "the product code is not a monitored family, but the official product "
                "description or reason for recall names a monitoring device or measurement "
                "(" + ", ".join(matched[:4]) + ")"
            ),
        }
    firm = str(payload.get("recalling_firm") or "").strip()
    organization = None
    if firm and taxonomy is not None:
        try:
            resolved = list(taxonomy.resolve_organization(firm) or ())
        except Exception:  # noqa: BLE001
            resolved = []
        organization = resolved[0] if resolved else None
    if organization is not None and VAGUE_MONITORING.search(text):
        return {
            "basis": BASIS_UNCONFIRMED,
            "in_scope": True,
            "needs_review": True,
            "code": code or None,
            "code_topics": [],
            "matched_terms": [],
            "reason": (
                "the recalling firm resolves to " + str(organization.get("organization_id"))
                + ", but neither the product code nor the device text confirms a monitoring "
                "device"
            ),
        }
    non_monitoring = NON_MONITORING_HINT.search(text)
    return {
        "basis": BASIS_OUT_OF_SCOPE,
        "in_scope": False,
        "needs_review": False,
        "code": code or None,
        "code_topics": [],
        "device_names": [],
        "matched_terms": [],
        "reason": (
            "not a monitoring device: the product code is not a monitored family and the "
            "official text names no monitoring device or measurement"
            + (" (" + non_monitoring.group(0).lower() + ")" if non_monitoring else "")
        ),
    }


def event_groups(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group scored rows by FDA recall event: one event, all of its product rows.

    Used by the brief and the coverage report so that "how many recalls" means events, not
    database rows.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        event = recall_event_id(payload) or str(row.get("observation_id") or "")
        bucket = grouped.setdefault(event, {"event_id": event, "products": []})
        bucket["products"].append(row)
    return sorted(grouped.values(), key=lambda item: str(item["event_id"]))
