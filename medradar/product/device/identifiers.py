"""Stable identifiers for the device model.

Two rules:

1. Every MedRadar identifier carries a type prefix (app:, device:, family:) so it can never be
   mistaken for an FDA identifier. The official identifier is always available separately and is what
   the UI shows first.
2. Identifiers are derived deterministically from official data (source + official number), so a
   rebuild of the index produces the same ids and the same relations.
"""
from __future__ import annotations

import re

APPLICATION_PREFIX = "app:"
DEVICE_PREFIX = "device:"
FAMILY_PREFIX = "family:"

#: Relation types and the status they can have. A type never silently changes status.
RELATION_TYPES: dict[str, str] = {
    "application_has_supplement": "confirmed",
    "device_has_version": "confirmed",
    "recall_references_application": "confirmed",
    "candidate_same_device": "candidate",
    "candidate_recall_application": "candidate",
}

#: Relation types deliberately NOT modelled in this release, with the reason.
NOT_MODELLED = {
    "application_references_predicate": (
        "openFDA exposes no predicate identifier for 510(k) submissions, and the 510(k) summary "
        "documents were not collected. A predicate relation cannot be established from this data, so "
        "it is not invented."
    ),
    "record_mentions_device": (
        "every application record names a device by definition; emitting a relation for it would be "
        "tautological. The device name is shown on the record and on the device page instead."
    ),
    "manufacturer_of_device": (
        "the applicant field is a record claim, not proof of current manufacture. It is shown as the "
        "applicant, with its PRODUCT-002 attribution status, rather than modelled as a device relation."
    ),
}


def application_id(source_id: str, official_id: str) -> str:
    return APPLICATION_PREFIX + source_id + ":" + official_id


def device_id(source_id: str, official_id: str) -> str:
    return DEVICE_PREFIX + source_id + ":" + official_id


def family_id(pma_number: str) -> str:
    return FAMILY_PREFIX + "pma:" + pma_number


def external_application_id(k_number: str) -> str:
    return APPLICATION_PREFIX + "openfda_510k:" + k_number


_K_NUMBER = re.compile(r"\b(K\d{6})\b", re.IGNORECASE)
_PMA_NUMBER = re.compile(r"\b([NP]\d{5,6})\b", re.IGNORECASE)


def normalise_k_number(value: str) -> str | None:
    match = _K_NUMBER.search(str(value or ""))
    return match.group(1).upper() if match else None


def normalise_pma_number(value: str) -> str | None:
    text = str(value or "").strip().upper()
    match = _PMA_NUMBER.fullmatch(text)
    return match.group(1) if match else None


def relation_types() -> dict[str, str]:
    return dict(RELATION_TYPES)
