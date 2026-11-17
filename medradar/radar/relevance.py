"""Compatibility facade for the relevance assessment.

REFOUNDATION-004 moved the judgement into medradar.radar.assessment, which separates source
authenticity, medical domain, monitoring relevance, entity linkage, freshness, importance,
confidence and the feed decision instead of overloading one tier.

This module stays because the ledger, the engine, the API, the CLI and the tests import the
names here. There is exactly one implementation (assessment); nothing is re-implemented here.
A new data source or a new rule changes assessment.py and the taxonomy config, not this file
and not the callers.

The tier vocabulary is unchanged so that historical observation_admission rows and the
user-facing feed views keep their meaning:

* HIGH_RELEVANCE - the record is in the default monitoring-intelligence feed (decision FEED);
* NEEDS_REVIEW  - plausibly monitoring, evidence not settled;
* LOW_RELEVANCE - medical but not monitoring technology, or a clinical study using it;
* IRRELEVANT    - not about patients at all.

The authoritative judgement is the dimension set on the decision, not the tier.
"""

from __future__ import annotations

from .assessment import (
    ADMISSION_VERSION,
    ASSESSMENT_VERSION,
    AUTHORITATIVE_RECORD_TYPES,
    DECISION_EXCLUDED,
    DECISION_FEED,
    DECISION_REVIEW,
    DECISIONS,
    DEVICE_FAMILIES,
    DEVICE_TOPICS,
    DIRECT,
    HIGH_RELEVANCE,
    IRRELEVANT,
    LOW_RELEVANCE,
    MEDICAL_UNRELATED,
    MONITORING_RELEVANCE_CLASSES,
    NEEDS_REVIEW,
    NON_MEDICAL,
    OFFICIAL_VENDOR,
    PRIMARY_RECORD_TYPES,
    PRIMARY_REGULATORY,
    SCHOLARLY,
    RULES_VERSION,
    TIER_LABELS_ZH,
    TIER_ORDER,
    TRANSFER,
    Admission,
    assess_observation,
    assess_publication,
    classify_observation,
    classify_publication,
    index_text,
    now_iso,
    rules_digest,
    subject_text,
    summarize,
    tier_for_label,
    venue_text,
)

__all__ = [
    "ADMISSION_VERSION",
    "ASSESSMENT_VERSION",
    "RULES_VERSION",
    "rules_digest",
    "Admission",
    "HIGH_RELEVANCE",
    "NEEDS_REVIEW",
    "LOW_RELEVANCE",
    "IRRELEVANT",
    "TIER_ORDER",
    "TIER_LABELS_ZH",
    "PRIMARY_RECORD_TYPES",
    "PRIMARY_REGULATORY",
    "OFFICIAL_VENDOR",
    "SCHOLARLY",
    "AUTHORITATIVE_RECORD_TYPES",
    "DECISION_FEED",
    "DECISION_REVIEW",
    "DECISION_EXCLUDED",
    "DECISIONS",
    "DIRECT",
    "TRANSFER",
    "CLINICAL",
    "MEDICAL_UNRELATED",
    "NON_MEDICAL",
    "MONITORING_RELEVANCE_CLASSES",
    "DEVICE_FAMILIES",
    "DEVICE_TOPICS",
    "assess_observation",
    "assess_publication",
    "classify_observation",
    "classify_publication",
    "subject_text",
    "venue_text",
    "index_text",
    "summarize",
    "now_iso",
    "tier_for_label",
]
