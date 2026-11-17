"""The deterministic rule layer: what a single record can be attributed to, and how surely.

This module is the *first* layer of the intelligence engine. It uses rules, official
identifiers and the committed taxonomy - no model, no guessing, no fuzzy matching.

Three separate questions are answered separately, because collapsing them is what turns an
evidence system into a rumour system:

``organization_candidates``
    Which organisations does the *published text* name? A regulatory applicant, a vendor
    page, or a paper affiliation are three different roles. ``role`` records which one, so
    a publication affiliation can never be promoted into a product capability.

``product_candidates``
    Which product or device does the record itself name? Derived from an official device
    name or a product identifier the source published.

``technology_topics``
    Which technology topics is the record *about*? Two independent signals are kept
    separate: an official FDA product code (strong, but regulatory) and a text match
    (weaker, and only ever ``TOPIC_RELATED``).

Every candidate carries ``method``, ``confidence`` and ``confirmation`` so the graph layer
can decide what may be asserted, and the UI can show why.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .records import (
    CANDIDATE,
    CONFIRMED,
    MAPPING_VERSION,
    METHOD_MODEL,
    METHOD_OFFICIAL_ID,
    METHOD_RULE_ALIAS,
    METHOD_RULE_PRODUCT_CODE,
    METHOD_RULE_TEXT,
    TOPIC_RELATED,
    UNKNOWN_RELATION,
    MappingResult,
    RawRecord,
)
from .taxonomy import Taxonomy

#: The role a published organisation name plays in the record.
ROLE_APPLICANT = "regulatory_applicant"
ROLE_VENDOR = "official_publisher"
ROLE_AFFILIATION = "publication_affiliation"
ROLE_PRODUCER = "document_producer"

#: Roles that may support a product/company capability assertion.
CAPABILITY_ROLES = (ROLE_APPLICANT, ROLE_VENDOR, ROLE_PRODUCER)

#: A vendor headline that names a product it is launching. Deliberately narrow: only an
#: explicit launch/introduction verb, then a capitalised name. If the pattern does not match,
#: no product is invented.
_HEADLINE_PRODUCT = re.compile(
    r"\b(?:launches|introduces|unveils|announces|releases|expands|debuts|presents|present)\s+"
    r"(?:the\s+|its\s+|a\s+|an\s+)?"
    r"(?:new\s+|all-new\s+|next-generation\s+)?"
    r"([A-Z][A-Za-z0-9\-]*(?:\s+(?:[A-Z0-9][A-Za-z0-9\-]*|3D|4D)){0,3})"
)
#: Words that are never a product name on their own.
_HEADLINE_STOPWORDS = {
    "The", "A", "An", "Its", "New", "United", "US", "U.S.", "First", "This", "Our",
    "Philips", "Dräger", "Draeger", "GE", "HealthCare", "Healthcare",
}


def extract_vendor_product(title: str | None) -> str | None:
    """The product a vendor headline explicitly names, or ``None``.

    ``"Philips launches HyperVue integrated system in the U.S."`` -> ``"HyperVue"``.
    A headline with no launch verb (``"Philips to nominate ..."``) yields ``None``: a regulatory
    or governance announcement is not a product launch, and guessing would poison the graph.
    """
    if not title:
        return None
    for match in _HEADLINE_PRODUCT.finditer(str(title)):
        candidate = " ".join(match.group(1).split())
        words = [word for word in candidate.split() if word not in _HEADLINE_STOPWORDS]
        if not words:
            continue
        candidate = " ".join(words)
        if len(candidate) < 3:
            continue
        return candidate[:80]
    return None


#: Technology families whose evidence is about a *measuring device or its platform* rather than
#: about a clinical decision made from measurements. Used only by the publication admission gate.
DEVICE_FAMILIES = frozenset({
    "electrocardiography", "oxygenation", "haemodynamics", "ventilation", "alarms", "platform",
})
#: A topic inside an otherwise clinical family that is still explicitly about the device chain.
DEVICE_TOPICS = frozenset({"data_interoperability"})


def publication_relevance(mapping: MappingResult) -> tuple[bool, str]:
    """Decide whether a paper is about monitoring *technology* or merely uses monitoring data.

    The distinction the first batch got wrong: a study that predicts sepsis from ICU vital signs
    is a clinical study that *consumes* monitoring data. It is not evidence that a monitor vendor
    developed a technique, and admitting it inflates every downstream topic count.

    Admission requires one of:

    * a monitored vendor affiliation (the paper is authored inside the industry);
    * a technology topic in a device family - ECG, oximetry, blood pressure, ventilation,
      alarms/signal quality, or a monitor platform;
    * the device-connectivity topic (``data_interoperability``), which is about the device chain.

    A decision-support-only paper is rejected with a reason that says so, and the reason is
    recorded in the run's out-of-scope samples. Nothing is silently dropped.
    """
    if mapping.organization_candidates:
        return True, ""
    topics = list(mapping.technology_topics or ())
    device_topics = [
        topic for topic in topics
        if topic.get("family") in DEVICE_FAMILIES or topic.get("topic_id") in DEVICE_TOPICS
    ]
    if device_topics:
        return True, ""
    if topics:
        names = ", ".join(sorted(str(topic.get("topic_id")) for topic in topics))
        return False, (
            "out of scope: a clinical study that uses monitoring data but does not study "
            f"monitoring technology (only decision-support/topic signals: {names})"
        )
    return False, (
        "out of scope: the record matches no monitored technology topic and no monitored vendor "
        "affiliation"
    )


class RuleMapper:
    """Turn one :class:`RawRecord` into a :class:`MappingResult` using config only."""

    def __init__(self, taxonomy: Taxonomy) -> None:
        self.taxonomy = taxonomy

    # ------------------------------------------------------------------ helpers
    def _organization(self, name: str | None, role: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for match in self.taxonomy.resolve_organization(name):
            candidates.append({**match, "role": role})
        return candidates

    def _products(self, record: RawRecord) -> list[dict[str, Any]]:
        hint = record.extra.get("product_hint")
        if not hint:
            return []
        name = " ".join(str(hint).split())
        if not name:
            return []
        identifier = record.extra.get("product_identifier") or record.source_record_id
        # A regulatory record names the device in its official device_name field; a vendor's own
        # document names the product it launches. Both are the source stating the product exists,
        # so both are CONFIRMED product mentions - not a capability claim.
        if record.record_type == "regulatory_record":
            confidence = 0.9
        elif record.record_type in ("press_release", "product_document"):
            confidence = 0.92
        else:
            confidence = 0.7
        return [{
            "product_key": _product_key(name),
            "name": name,
            "method": METHOD_OFFICIAL_ID if record.record_type == "regulatory_record" else METHOD_RULE_TEXT,
            "confirmation": CONFIRMED if confidence >= 0.9 else CANDIDATE,
            "confidence": confidence,
            "identifier": str(identifier),
            "source": record.source,
            "record_type": record.record_type,
        }]

    def _topics(self, record: RawRecord, text: str) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        codes = [str(code) for code in (record.extra.get("product_codes") or []) if code]
        for entry in self.taxonomy.topics_for_product_codes(codes):
            merged[entry["topic_id"]] = dict(entry)
        for entry in self.taxonomy.match_text(text):
            existing = merged.get(entry["topic_id"])
            if existing is None:
                merged[entry["topic_id"]] = dict(entry)
                continue
            # Both signals fired: keep the stronger method, record both spans.
            existing_terms = list(existing.get("matched_terms") or [])
            for term in entry.get("matched_terms") or []:
                if term not in existing_terms:
                    existing_terms.append(term)
            existing["matched_terms"] = existing_terms
            existing["confidence"] = round(min(0.95, max(existing["confidence"], entry["confidence"]) + 0.05), 3)
            existing["text_supported"] = True
        for entry in merged.values():
            entry.setdefault("text_supported", False)
        return sorted(merged.values(), key=lambda item: (-item["confidence"], item["topic_id"]))

    # -------------------------------------------------------------------- public
    def map(self, record: RawRecord) -> MappingResult:
        text = " ".join(filter(None, [
            record.title,
            str(record.extra.get("summary") or ""),
            record.text,
        ]))
        organizations: list[dict[str, Any]] = []
        seen_orgs: set[tuple[str, str]] = set()
        for name, role in (
            (record.extra.get("organization_hint"), str(record.extra.get("organization_role") or ROLE_APPLICANT)),
            (record.extra.get("publisher_hint"), ROLE_VENDOR),
        ):
            for candidate in self._organization(name, role):
                key = (candidate["organization_id"], role)
                if key not in seen_orgs:
                    seen_orgs.add(key)
                    organizations.append(candidate)
        # Affiliations are recorded, but never as a producer of a product.
        for affiliation in record.extra.get("affiliations") or []:
            for candidate in self._organization(affiliation, ROLE_AFFILIATION):
                key = (candidate["organization_id"], ROLE_AFFILIATION)
                if key not in seen_orgs:
                    seen_orgs.add(key)
                    organizations.append(candidate)

        products = self._products(record)
        topics = self._topics(record, text)

        # A regulatory product code supports the company->product link, but a *text* topic
        # hit on a regulatory record stays TOPIC_RELATED: a clearance is not an algorithm.
        for entry in topics:
            entry["confirmation"] = TOPIC_RELATED

        note = None
        if not organizations and not topics:
            note = "no organisation or topic rule matched this record"

        return MappingResult(
            organization_candidates=tuple(organizations),
            product_candidates=tuple(products),
            technology_topics=tuple(topics),
            method_version=MAPPING_VERSION,
            note=note,
        )

    # ------------------------------------------------------- model-candidate vetting
    def vet_model_claim(
        self,
        claim: Mapping[str, Any],
        *,
        source_text: str,
        allowed: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Independently verify one model proposal against the record's own text.

        A model proposal is never trusted on its own. It is promoted only when an
        independent, deterministic check supports it:

        * for a topic: the quoted evidence must appear in the source text **and** the claim
          must match a taxonomy topic id;
        * for an organisation: the published name must resolve through the committed alias
          table.

        The verdict is always recorded, including a rejection and the reason.
        """
        kind = str(claim.get("kind") or "").strip()
        value = str(claim.get("value") or "").strip()
        quote = str(claim.get("evidence_quote") or "").strip()
        verdict: dict[str, Any] = {
            "kind": kind,
            "value": value,
            "model_confidence": claim.get("confidence"),
            "accepted": False,
            "method": METHOD_MODEL,
            "reason": None,
            "evidence_quote_verified": False,
        }
        if not value:
            verdict["reason"] = "empty value"
            return verdict
        if kind == "topic":
            topic = self.taxonomy.topic(value)
            if topic is None:
                verdict["reason"] = f"unknown topic id {value!r}"
                return verdict
            if allowed is not None and value not in set(allowed):
                verdict["reason"] = "topic outside the caller's allowed set"
                return verdict
            if not quote or quote.lower() not in source_text.lower():
                verdict["reason"] = "the quoted evidence is not present verbatim in the source text"
                return verdict
            verdict.update({
                "accepted": True,
                "reason": "topic id is in the taxonomy and the quoted evidence is verbatim in the source",
                "evidence_quote_verified": True,
                "confirmation": TOPIC_RELATED,
            })
            return verdict
        if kind == "organization":
            if not quote or quote.lower() not in source_text.lower():
                verdict["reason"] = "the quoted evidence is not present verbatim in the source text"
                return verdict
            matches = self.taxonomy.resolve_organization(value)
            if not matches:
                verdict["reason"] = f"the organisation {value!r} does not resolve through the alias table"
                return verdict
            verdict.update({
                "accepted": True,
                "reason": "the organisation resolves through the alias table and the quote is verbatim",
                "evidence_quote_verified": True,
                "confirmation": matches[0]["confirmation"],
                "organization_id": matches[0]["organization_id"],
            })
            return verdict
        verdict["reason"] = f"unsupported claim kind {kind!r}"
        return verdict


def _product_key(name: str) -> str:
    import hashlib
    import re

    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not normalized:
        normalized = "unnamed"
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{normalized[:80]}:{digest}"


def empty_mapping(note: str) -> MappingResult:
    return MappingResult(note=note)
