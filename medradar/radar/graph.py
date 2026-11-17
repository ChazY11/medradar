"""The Company Technology Graph: evidence-backed assertions with two clocks.

The graph is stored in the in-tree bitemporal assertion store (:mod:`medradar.tkg`), which is
reused rather than re-implemented. That gives three properties the product needs and that a
hand-rolled "company -> technology" table cannot offer:

1. **Append-only history.** A later correction adds a revision; it never rewrites the earlier
   one. The store physically rejects ``UPDATE``/``DELETE`` on assertion tables.
2. **Two independent clocks.** ``recorded_at`` is when *MedRadar* recorded the assertion
   (knowledge time, assigned inside the store, never backdatable). ``valid_from``/``public_time``
   is when the evidence says the thing was true/public. So "what did we know on 1 October"
   and "what was publicly true on 1 October" are two different questions with two different
   answers - and the retrospective view can be labelled as a reconstruction.
3. **Evidence on every edge.** Each assertion carries the evidence id, the observation id, the
   source, the URL, the rule/taxonomy version and a confirmation level. An edge with no
   evidence cannot be written: the store requires a non-empty ``source_locator``.

Confirmation levels, and what may *not* be concluded:

``CONFIRMED``
    The source states the thing directly: an FDA record names this applicant and this device;
    a vendor press release names this product and this capability; two sources publish the same
    official identifier.

``CANDIDATE``
    A rule supports the link but identity or intent is not established (a broad legal name, a
    product name that only appears in a paper title).

``TOPIC_RELATED``
    The record is *about* the topic. This is what a keyword hit or an FDA product code can
    establish, and it is deliberately weaker than "the product has this capability". An FDA
    clearance is never promoted to an algorithm claim.

``UNKNOWN``
    Recorded as a state, with the reason, instead of being silently dropped.

Nothing in this module scores a company. ``compare_companies`` reports counts of *evidence of
a kind*, and states in the payload that a publication count is research activity, not product
capability, and that "no evidence found" is not "no technology".
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from ..tkg import TKGQuery, TKGStore
from ..tkg.store import TKGError
from .records import (
    CANDIDATE,
    CONFIRMED,
    TOPIC_RELATED,
    UNKNOWN_RELATION,
    canonical_json,
    normalize_moment,
    parse_moment,
)
from .taxonomy import Taxonomy

GRAPH_VERSION = "radar-graph-2"

# ---------------------------------------------------------------- node/edge types
NODE_COMPANY = "company"
NODE_ORGANIZATION = "organization"
NODE_PRODUCT = "product"
NODE_TOPIC = "technology_topic"
NODE_REGULATORY = "regulatory_record"
NODE_PUBLICATION = "publication"
NODE_DOCUMENT = "document"
NODE_EVIDENCE = "evidence"

RECORD_NODE_TYPES = (NODE_REGULATORY, NODE_PUBLICATION, NODE_DOCUMENT)

EDGE_COMPANY_PRODUCT = "COMPANY_HAS_PRODUCT"
EDGE_PRODUCT_CAPABILITY = "PRODUCT_HAS_REPORTED_CAPABILITY"
EDGE_REGULATORY_PRODUCT = "REGULATORY_RECORD_REFERENCES_PRODUCT"
EDGE_PUBLICATION_TOPIC = "PUBLICATION_DISCLOSES_TOPIC"
EDGE_DOCUMENT_COMPANY = "DOCUMENT_MENTIONS_COMPANY"
EDGE_IDENTIFIER_MATCH = "OFFICIAL_IDENTIFIER_MATCH"
EDGE_CANDIDATE_PRODUCT = "CANDIDATE_PRODUCT_RELATION"
EDGE_RELATED_TOPIC = "RELATED_TECHNOLOGY_TOPIC"
EDGE_ORGANIZATION_COMPANY = "ORGANIZATION_PART_OF_COMPANY"
EDGE_RECORD_TOPIC = "DOCUMENT_REFERENCES_TOPIC"

EDGE_TYPES = (
    EDGE_COMPANY_PRODUCT, EDGE_PRODUCT_CAPABILITY, EDGE_REGULATORY_PRODUCT,
    EDGE_PUBLICATION_TOPIC, EDGE_DOCUMENT_COMPANY, EDGE_IDENTIFIER_MATCH,
    EDGE_CANDIDATE_PRODUCT, EDGE_RELATED_TOPIC, EDGE_ORGANIZATION_COMPANY,
    EDGE_RECORD_TOPIC,
)

CONFIRMATION_RANK = {CONFIRMED: 3, TOPIC_RELATED: 2, CANDIDATE: 1, UNKNOWN_RELATION: 0}

#: Coverage states for a (company, topic) cell. They are never collapsed into a boolean.
EVIDENCE_PRESENT = "EVIDENCE_PRESENT"
NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"
NOT_MONITORED = "NOT_MONITORED"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


def _entity(node_type: str, node_id: str) -> tuple[str, str]:
    return (node_type, node_id)


def organization_node_id(name: str) -> str:
    normalized = " ".join(str(name).lower().split())
    return "legal:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def product_node_id(product_key: str) -> str:
    return f"product:{product_key}"


def topic_node_id(topic_id: str) -> str:
    return f"topic:{topic_id}"


def company_node_id(org_id: str) -> str:
    return f"org:{org_id}"


def record_node_id(observation_id: str) -> str:
    return f"obs:{observation_id}"


class TechnologyGraph:
    """Write and query the company-technology graph."""

    def __init__(self, store: TKGStore, taxonomy: Taxonomy) -> None:
        self.store = store
        self.taxonomy = taxonomy
        self.query = TKGQuery(store)

    # ------------------------------------------------------------------ writing
    def materialize(self, ledger, *, limit: int = 200, log: Any = print) -> dict[str, Any]:
        """Turn newly observed evidence into assertions. Idempotent and incremental."""
        pending = ledger.graph_pending(graph_version=GRAPH_VERSION, limit=limit)
        created = 0
        duplicates = 0
        materialized = 0
        errors: list[dict[str, str]] = []
        for row in pending:
            observation_id = row["observation_id"]
            version_id = row["latest_version_id"]
            try:
                specs = self._specs_for(ledger, row)
            except Exception as error:  # noqa: BLE001 - one record must not stop the graph
                if len(errors) < 20:
                    errors.append({"observation_id": observation_id,
                                   "error": f"{type(error).__name__}: {error}"[:400]})
                continue
            if not specs:
                ledger.mark_graph_materialized(observation_id, version_id=version_id,
                                               graph_version=GRAPH_VERSION, assertions=0)
                materialized += 1
                continue
            try:
                results = self._apply(specs)
            except TKGError as error:
                errors.append({"observation_id": observation_id, "error": f"TKG: {error}"[:400]})
                continue
            for result in results:
                if result.get("status") == "created":
                    created += 1
                else:
                    duplicates += 1
            ledger.mark_graph_materialized(observation_id, version_id=version_id,
                                           graph_version=GRAPH_VERSION, assertions=len(results))
            materialized += 1
        try:
            log(f"[graph] materialized {materialized} observation(s): {created} new assertion(s), "
                f"{duplicates} duplicate(s), {len(errors)} error(s)")
        except Exception:  # pragma: no cover
            pass
        return {
            "pending": len(pending),
            "materialized": materialized,
            "assertions_created": created,
            "assertions_duplicate": duplicates,
            "errors": errors,
            "graph_version": GRAPH_VERSION,
        }

    def _apply(self, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply node specs before edge specs so endpoint entities exist first."""
        nodes = [spec for spec in specs if spec["record"] == "node"]
        edges = [spec for spec in specs if spec["record"] == "edge"]
        results: list[dict[str, Any]] = []
        if nodes:
            results.extend(self.store.apply(nodes))
        if edges:
            results.extend(self.store.apply(edges))
        return results

    def _specs_for(self, ledger, row: Mapping[str, Any]) -> list[dict[str, Any]]:
        observation_id = row["observation_id"]
        version_id = row["latest_version_id"]
        facets = ledger.facets_for(observation_id)
        record_type = row["record_type"]
        node_type = {
            "regulatory_record": NODE_REGULATORY,
            "publication": NODE_PUBLICATION,
            "press_release": NODE_DOCUMENT,
            "product_document": NODE_DOCUMENT,
        }.get(record_type, NODE_DOCUMENT)
        rec_id = record_node_id(observation_id)
        # A graph assertion needs one ordering anchor. Year/year-month publication dates are
        # anchored to their first day for ordering only; the record keeps its own precision.
        valid_from = _record_valid_from(row)
        public_time, public_basis = _public_time(row)
        evidence = {
            "evidence_id": version_id,
            "observation_id": observation_id,
            "content_hash": row.get("content_hash"),
            "source": row.get("source"),
            "source_url": row.get("source_url"),
            "record_type": record_type,
        }
        # The evidence node describes the source bytes, so its identity must not depend on the
        # taxonomy or the rule version. Those belong on the *edges* whose confidence they derive:
        # otherwise a taxonomy edit would make the same evidence a "different" assertion.
        base = {
            "source_locator": row.get("source_url") or f"radar://observation/{observation_id}",
            "evidence_kind": "source_observed",
            "public_time": public_time,
            "public_time_basis": public_basis,
        }
        # Shared entity nodes (company, topic, product) are the *same assertion* every time any
        # record supports them. Their content must therefore be identical across records - a
        # per-record URL or public_time would make the same key carry different content, which
        # the store (correctly) rejects as an idempotency conflict.
        entity_base = {
            "source_locator": f"radar://taxonomy/{self.taxonomy.version}",
            "evidence_kind": "source_observed",
        }
        specs: list[dict[str, Any]] = [
            self._record_node_spec(row, node_type),
            {
                "record": "node", "node_type": NODE_EVIDENCE, "node_id": f"ev:{version_id}",
                "attrs": evidence,
                "valid_from": valid_from,
                "idempotency_key": f"evidence:{version_id}",
                **base,
                "confidence": 1.0,
            },
        ]
        pending_duplicates: list[dict[str, Any]] = []

        # ------------------------------------------------ organisation assertions
        company_ids: list[str] = []
        for candidate in facets.get("organization", []):
            org_id = candidate["value"]
            organization = self.taxonomy.organization(org_id)
            confirmation = candidate["confirmation"]
            if organization is None:
                continue
            if confirmation in (CONFIRMED, CANDIDATE):
                company_ids.append(org_id)
                specs.append(self._node_company(organization, entity_base))
                specs.append(self._edge(
                    EDGE_DOCUMENT_COMPANY, node_type, rec_id, NODE_COMPANY,
                    company_node_id(org_id), valid_from, base, evidence,
                    confirmation=confirmation, method=candidate["method"],
                    extra={"matched_alias": candidate.get("matched_alias"),
                           "published_name": candidate.get("published_name"),
                           "role": "document_mentions_company"},
                ))
            else:
                specs.append(self._node_company(organization, entity_base))

        # ------------------------------------------------------ product assertions
        products: list[dict[str, Any]] = []
        for candidate in facets.get("product", []):
            products.append(candidate)
            product_id = product_node_id(candidate["value"])
            specs.append({
                "record": "node", "node_type": NODE_PRODUCT, "node_id": product_id,
                # Only the stable identity is stored on the shared product node; the human name
                # is carried by the record node that cites it.
                "attrs": {"product_key": candidate["value"]},
                "valid_from": "1970-01-01",
                "idempotency_key": f"node:{product_id}",
                **entity_base, "confidence": float(candidate.get("confidence") or 0.5),
            })
            relation = EDGE_REGULATORY_PRODUCT if node_type == NODE_REGULATORY else EDGE_CANDIDATE_PRODUCT
            specs.append(self._edge(
                relation, node_type, rec_id, NODE_PRODUCT, product_id, valid_from, base, evidence,
                confirmation=candidate["confirmation"], method=candidate["method"],
                extra={"identifier": candidate.get("identifier")},
            ))
            for org_id in company_ids:
                attributed = self._company_confirmation(facets, org_id)
                edge_type = EDGE_COMPANY_PRODUCT if attributed == CONFIRMED else EDGE_CANDIDATE_PRODUCT
                specs.append(self._edge(
                    edge_type, NODE_COMPANY, company_node_id(org_id), NODE_PRODUCT, product_id,
                    valid_from, base, evidence, confirmation=attributed,
                    method="official_identifier" if attributed == CONFIRMED else "rule_alias",
                    extra={"via_observation": observation_id},
                ))

        # -------------------------------------------------------- topic assertions
        topics: list[str] = []
        for candidate in facets.get("topic", []):
            topic_id = candidate["value"]
            topic = self.taxonomy.topic(topic_id)
            if topic is None:
                continue
            topics.append(topic_id)
            topic_id_node = topic_node_id(topic_id)
            specs.append({
                "record": "node", "node_type": NODE_TOPIC, "node_id": topic_id_node,
                "attrs": {"label_en": topic.label_en, "label_zh": topic.label_zh,
                          "family": topic.family, "description": topic.description},
                "valid_from": "1970-01-01",
                "idempotency_key": f"node:{topic_id_node}",
                **entity_base, "confidence": 1.0,
            })
            if node_type == NODE_PUBLICATION:
                specs.append(self._edge(
                    EDGE_PUBLICATION_TOPIC, node_type, rec_id, NODE_TOPIC, topic_id_node,
                    valid_from, base, evidence, confirmation=TOPIC_RELATED,
                    method=candidate["method"],
                    extra={"matched_terms": candidate.get("matched_terms") or []},
                ))
            else:
                specs.append(self._edge(
                    EDGE_RECORD_TOPIC, node_type, rec_id, NODE_TOPIC, topic_id_node,
                    valid_from, base, evidence, confirmation=TOPIC_RELATED,
                    method=candidate["method"],
                    extra={"matched_terms": candidate.get("matched_terms") or []},
                ))
                # A vendor's own document may support a *reported* capability. A regulatory
                # record or a paper may not: they are topic-related only.
                if node_type == NODE_DOCUMENT:
                    for product in products:
                        specs.append(self._edge(
                            EDGE_PRODUCT_CAPABILITY, NODE_PRODUCT, product_node_id(product["value"]),
                            NODE_TOPIC, topic_id_node, valid_from, base, evidence,
                            confirmation=CONFIRMED, method=candidate["method"],
                            extra={"basis": "vendor_document_states_topic",
                                   "matched_terms": candidate.get("matched_terms") or []},
                        ))
                for company_id in company_ids:
                    attributed = self._company_confirmation(facets, company_id)
                    if attributed == CONFIRMED and node_type == NODE_DOCUMENT:
                        for product in products:
                            specs.append(self._edge(
                                EDGE_PRODUCT_CAPABILITY, NODE_PRODUCT,
                                product_node_id(product["value"]), NODE_TOPIC, topic_id_node,
                                valid_from, base, evidence, confirmation=CONFIRMED,
                                method=candidate["method"],
                                extra={"basis": "vendor_document_states_topic",
                                       "matched_terms": candidate.get("matched_terms") or []},
                            ))

        # --------------------------------------------- cross-source identifier match
        official = row.get("official_identifier")
        matched_siblings: set[str] = set()
        if official:
            pending_duplicates, matched_siblings = self._identifier_edges(
                ledger, observation_id, official, valid_from, base, evidence, node_type, rec_id)
            specs.extend(pending_duplicates)

        # ------------------------------------------- cross-source same-work DOI match
        # A PMID record and a Crossref record never share ``official_identifier`` (one is a
        # PMID, the other a DOI), so the identifier above cannot join them. The DOI that PubMed
        # states in its own metadata can: normalised DOI equality across two independent APIs is
        # a verifiable same-work relation, and it is deliberately the *only* basis used here -
        # title similarity is never consulted.
        for identifier in ledger.identifiers(observation_id):
            if identifier["kind"] != "DOI":
                continue
            specs.extend(self._doi_match_edges(
                ledger, observation_id, identifier["value"], valid_from, base, evidence, node_type,
                rec_id, exclude=matched_siblings,
            ))

        # -------------------------------------------------- related technology topics
        # Sorted so the edge direction is a property of the topic pair, not of the order the
        # rule layer happened to emit.
        ordered_topics = sorted(set(topics))
        for left_index, left in enumerate(ordered_topics):
            for right in ordered_topics[left_index + 1:]:
                specs.append(self._edge(
                    EDGE_RELATED_TOPIC, NODE_TOPIC, topic_node_id(left), NODE_TOPIC,
                    topic_node_id(right), valid_from, base, evidence,
                    confirmation=TOPIC_RELATED, method="rule_cooccurrence",
                    extra={"basis": "both topics supported by the same evidence record"},
                ))
        return specs

    def _record_node_spec(self, row: Mapping[str, Any], node_type: str) -> dict[str, Any]:
        """The one canonical spec for a record node.

        Both the record's own materialisation and a cross-source sibling reference must build
        the *identical* assertion, otherwise the shared idempotency key would carry two
        different contents (which the store rejects, correctly). The evidence locator and the
        public time are therefore derived from the record row, never from the caller.
        """
        observation_id = row["observation_id"]
        rec_id = record_node_id(observation_id)
        public_time, public_basis = _public_time(row)
        base = {
            "source_locator": row.get("source_url") or f"radar://observation/{observation_id}",
            "evidence_kind": "source_observed",
            "public_time": public_time,
            "public_time_basis": public_basis,
        }
        return {
            "record": "node", "node_type": node_type, "node_id": rec_id,
            "attrs": {
                "observation_id": observation_id,
                "title": row.get("title"),
                "official_url": row.get("source_url"),
                "source": row.get("source"),
                "record_type": row.get("record_type"),
                "first_observed_at": row.get("first_observed_at"),
                "event_at": row.get("event_at"),
                "published_at": row.get("published_at"),
            },
            "valid_from": _record_valid_from(row),
            "idempotency_key": f"node:{rec_id}",
            **base,
            "confidence": 1.0,
        }

    def _node_company(self, organization, entity_base: Mapping[str, Any]) -> dict[str, Any]:
        node_id = company_node_id(organization.id)
        return {
            "record": "node", "node_type": NODE_COMPANY, "node_id": node_id,
            "attrs": {"id": organization.id, "canonical_name": organization.canonical_name,
                      "display_name": organization.display_name, "label_zh": organization.label_zh,
                      "country": organization.country},
            "valid_from": "1970-01-01",
            "idempotency_key": f"node:{node_id}",
            **entity_base, "confidence": 1.0,
        }

    def _edge(self, edge_type: str, src_type: str, src_id: str, dst_type: str, dst_id: str,
              valid_from: str, base: Mapping[str, Any], evidence: Mapping[str, Any], *,
              confirmation: str, method: str, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        attrs = {
            **dict(evidence),
            "taxonomy_version": self.taxonomy.version,
            "taxonomy_fingerprint": self.taxonomy.fingerprint,
            "graph_version": GRAPH_VERSION,
            "confirmation": confirmation,
            "method": method,
            **dict(extra or {}),
        }
        digest = hashlib.sha256(canonical_json(attrs).encode("utf-8")).hexdigest()[:16]
        return {
            "record": "edge",
            "edge_type": edge_type,
            "src_type": src_type, "src_id": src_id,
            "dst_type": dst_type, "dst_id": dst_id,
            "attrs": attrs,
            "valid_from": valid_from,
            "idempotency_key": f"edge:{edge_type}:{src_type}:{src_id}->{dst_type}:{dst_id}#{digest}",
            "source_locator": base["source_locator"],
            "evidence_kind": base["evidence_kind"],
            "public_time": base.get("public_time"),
            "public_time_basis": base.get("public_time_basis"),
            "confidence": 1.0 if confirmation == CONFIRMED else 0.7 if confirmation == TOPIC_RELATED else 0.45,
        }

    def _identifier_edges(self, ledger, observation_id: str, official: str, valid_from: str,
                          base: Mapping[str, Any], evidence: Mapping[str, Any],
                          node_type: str, rec_id: str) -> tuple[list[dict[str, Any]], set[str]]:
        siblings = ledger.raw(
            "SELECT observation_id, source, record_type, title, source_url, first_observed_at,"
            " event_at, published_at FROM observation"
            " WHERE official_identifier=? AND observation_id<>? ORDER BY observation_id LIMIT 8",
            (official, observation_id),
        )
        specs: list[dict[str, Any]] = []
        sibling_ids: set[str] = set()
        for sibling in siblings:
            sibling_type = {
                "regulatory_record": NODE_REGULATORY,
                "publication": NODE_PUBLICATION,
                "press_release": NODE_DOCUMENT,
                "product_document": NODE_DOCUMENT,
            }.get(sibling["record_type"], NODE_DOCUMENT)
            sibling_id = record_node_id(sibling["observation_id"])
            sibling_ids.add(sibling["observation_id"])
            specs.append(self._record_node_spec(sibling, sibling_type))
            # One deterministic direction so the assertion is stable across runs.
            if rec_id < sibling_id:
                specs.append(self._edge(
                    EDGE_IDENTIFIER_MATCH, node_type, rec_id, sibling_type, sibling_id,
                    valid_from, base, evidence, confirmation=CONFIRMED, method="official_identifier",
                    extra={"official_identifier": official, "other_source": sibling["source"]},
                ))
        return specs, sibling_ids

    def _doi_match_edges(self, ledger, observation_id: str, doi: str, valid_from: str,
                         base: Mapping[str, Any], evidence: Mapping[str, Any],
                         node_type: str, rec_id: str, *, exclude: set[str]) -> list[dict[str, Any]]:
        """Join two observations of the *same work* through an exact, normalised DOI.

        The relation is recorded as ``OFFICIAL_IDENTIFIER_MATCH`` with an explicit
        ``identifier_kind=DOI`` and its own method, so a reader can tell a PMID/DOI bridge from
        an identical-identifier match. Only observations from a different source qualify: two
        rows from one API sharing a DOI are one observation recorded twice, not corroboration.
        """
        specs: list[dict[str, Any]] = []
        peers = ledger.identifier_peers("DOI", doi, exclude=observation_id, limit=8)
        own_source = None
        for peer in peers:
            if peer["observation_id"] in exclude or peer["observation_id"] == observation_id:
                continue
            row = ledger.observation_row(peer["observation_id"])
            if row is None:
                continue
            if own_source is None:
                own = ledger.observation_row(observation_id) or {}
                own_source = own.get("source")
            if row.get("source") == own_source:
                continue
            sibling_type = {
                "regulatory_record": NODE_REGULATORY,
                "publication": NODE_PUBLICATION,
                "press_release": NODE_DOCUMENT,
                "product_document": NODE_DOCUMENT,
            }.get(row["record_type"], NODE_DOCUMENT)
            sibling_id = record_node_id(row["observation_id"])
            specs.append(self._record_node_spec(row, sibling_type))
            if rec_id < sibling_id:
                specs.append(self._edge(
                    EDGE_IDENTIFIER_MATCH, node_type, rec_id, sibling_type, sibling_id,
                    valid_from, base, evidence, confirmation=CONFIRMED, method="doi_exact_match",
                    extra={
                        "official_identifier": f"DOI:{doi}",
                        "identifier_kind": "DOI",
                        "identifier_value": doi,
                        "other_source": row.get("source"),
                        "basis": "normalised DOI equality across two independent sources",
                    },
                ))
        return specs

    def _company_confirmation(self, facets: Mapping[str, Any], org_id: str) -> str:
        for candidate in facets.get("organization", []):
            if candidate["value"] == org_id:
                return str(candidate["confirmation"])
        return UNKNOWN_RELATION

    # ------------------------------------------------------------------ querying
    def _cut(self, known_at: Any, valid_at: Any) -> tuple[dict[str, Any], bool]:
        """Return the as-of snapshot plus whether it is a public-time reconstruction.

        ``valid_at`` set  -> "what was publicly true on that date", computed from today's
        knowledge; the caller must label it a reconstruction.

        ``known_at`` only -> "what had MedRadar recorded by then", **without** the bitemporal
        store's implicit ``valid_at = known_at`` default. The distinction matters: an assertion
        recorded in 2026 about an event dated 2027 is still something MedRadar knew in 2026.
        """
        reconstructed = valid_at is not None
        if reconstructed or known_at is None:
            return self.query.snapshot(known_at=known_at, valid_at=valid_at), reconstructed
        known, _ = normalize_moment(known_at)
        nodes = self.query.latest_node_revisions(known, None)
        node_keys = {(node["node_type"], node["node_id"]) for node in nodes}
        edges = [
            edge for edge in self.query.latest_edge_revisions(known, None)
            if (edge["src"]["node_type"], edge["src"]["node_id"]) in node_keys
            and (edge["dst"]["node_type"], edge["dst"]["node_id"]) in node_keys
        ]
        return {"known_at": known, "valid_at": None, "nodes": nodes, "edges": edges}, reconstructed

    def technology_map(self, *, companies: Sequence[str] | None = None,
                       known_at: Any = None, valid_at: Any = None,
                       max_products: int = 25, max_evidence: int = 10) -> dict[str, Any]:
        """The company technology tree, computed from assertions - never from a static list."""
        snapshot, reconstructed = self._cut(known_at, valid_at)
        nodes = snapshot["nodes"]
        edges = snapshot["edges"]
        company_nodes = {n["node_id"]: n for n in nodes if n["node_type"] == NODE_COMPANY}
        topic_nodes = {n["node_id"]: n for n in nodes if n["node_type"] == NODE_TOPIC}
        product_nodes = {n["node_id"]: n for n in nodes if n["node_type"] == NODE_PRODUCT}
        record_nodes = {n["node_id"]: n for n in nodes if n["node_type"] in RECORD_NODE_TYPES}

        selected = list(companies or sorted(
            key.split(":", 1)[1] for key in company_nodes
        ))
        selected_ids = {company_node_id(company) for company in selected}
        if not companies:
            selected_ids = set(company_nodes)

        # company -> product
        company_products: dict[str, dict[str, dict[str, Any]]] = {}
        for edge in edges:
            if edge["edge_type"] not in (EDGE_COMPANY_PRODUCT, EDGE_CANDIDATE_PRODUCT):
                continue
            if edge["src"]["node_type"] != NODE_COMPANY:
                continue
            if edge["src"]["node_id"] not in selected_ids:
                continue
            product_id = edge["dst"]["node_id"]
            bucket = company_products.setdefault(edge["src"]["node_id"], {})
            existing = bucket.get(product_id)
            confirmation = edge["attrs"].get("confirmation", UNKNOWN_RELATION)
            if existing is None or CONFIRMATION_RANK.get(confirmation, 0) > CONFIRMATION_RANK.get(
                existing["confirmation"], 0
            ):
                bucket[product_id] = {
                    "product_id": product_id,
                    "name": _product_display(product_id),
                    "confirmation": confirmation,
                    "edge_type": edge["edge_type"],
                    "evidence_id": edge["attrs"].get("evidence_id"),
                    "source": edge["attrs"].get("source"),
                    "source_url": edge["attrs"].get("source_url"),
                    "first_recorded_at": edge["recorded_at"],
                    "valid_from": edge["valid_from"],
                }

        # product -> topic, from evidence that a *product* is filed under that topic. Two bases,
        # kept separate: a vendor statement (a reported capability) and a regulatory record whose
        # product code places the device in the topic (weaker, and labelled as such).
        product_topics: dict[str, list[dict[str, Any]]] = {}
        record_products: dict[str, set[str]] = {}
        for edge in edges:
            if edge["edge_type"] in (EDGE_REGULATORY_PRODUCT, EDGE_CANDIDATE_PRODUCT):
                if edge["src"]["node_type"] in RECORD_NODE_TYPES:
                    record_products.setdefault(edge["src"]["node_id"], set()).add(edge["dst"]["node_id"])
            if edge["edge_type"] != EDGE_PRODUCT_CAPABILITY:
                continue
            product_topics.setdefault(edge["src"]["node_id"], []).append({
                "topic_id": edge["dst"]["node_id"].split(":", 1)[1],
                "confirmation": edge["attrs"].get("confirmation", UNKNOWN_RELATION),
                "basis": edge["attrs"].get("basis"),
                "evidence_id": edge["attrs"].get("evidence_id"),
                "source": edge["attrs"].get("source"),
                "valid_from": edge["valid_from"],
                "recorded_at": edge["recorded_at"],
            })

        # record -> topic (publications and regulatory records)
        topic_evidence: dict[str, list[dict[str, Any]]] = {}
        record_companies: dict[str, set[str]] = {}
        for edge in edges:
            if edge["edge_type"] in (EDGE_DOCUMENT_COMPANY,) and edge["src"]["node_type"] in RECORD_NODE_TYPES:
                record_companies.setdefault(edge["src"]["node_id"], set()).add(edge["dst"]["node_id"])
        for edge in edges:
            if edge["edge_type"] not in (EDGE_PUBLICATION_TOPIC, EDGE_RECORD_TOPIC):
                continue
            topic_id = edge["dst"]["node_id"].split(":", 1)[1]
            src_id = edge["src"]["node_id"]
            for company_id in record_companies.get(src_id, set()):
                if company_id not in selected_ids:
                    continue
                topic_evidence.setdefault(f"{company_id}|{topic_id}", []).append({
                    "record_node": src_id,
                    "record_type": edge["src"]["node_type"],
                    "confirmation": edge["attrs"].get("confirmation", UNKNOWN_RELATION),
                    "method": edge["attrs"].get("method"),
                    "matched_terms": edge["attrs"].get("matched_terms") or [],
                    "evidence_id": edge["attrs"].get("evidence_id"),
                    "source": edge["attrs"].get("source"),
                    "source_url": edge["attrs"].get("source_url"),
                    "title": (record_nodes.get(src_id, {}).get("attrs") or {}).get("title"),
                    "valid_from": edge["valid_from"],
                    "public_time": edge.get("public_time"),
                    "recorded_at": edge["recorded_at"],
                })

        # Assemble the tree: topic -> company -> evidence.
        tree: list[dict[str, Any]] = []
        for topic_node_id_value, topic_node in sorted(topic_nodes.items()):
            topic_id = topic_node_id_value.split(":", 1)[1]
            topic = self.taxonomy.topic(topic_id)
            company_branches: list[dict[str, Any]] = []
            for company_id in sorted(selected_ids):
                company = company_nodes.get(company_id)
                if company is None:
                    continue
                org_id = company_id.split(":", 1)[1]
                products: list[dict[str, Any]] = []
                seen_products: set[str] = set()
                for product in (company_products.get(company_id) or {}).values():
                    capabilities = [
                        entry for entry in product_topics.get(product["product_id"], [])
                        if entry["topic_id"] == topic_id
                    ]
                    if capabilities:
                        products.append({
                            **product,
                            "capabilities": [
                                {key: value for key, value in capability.items() if key != "topic_id"}
                                for capability in capabilities
                            ],
                        })
                        seen_products.add(product["product_id"])
                evidence_rows = topic_evidence.get(f"{company_id}|{topic_id}", [])
                # A product may also sit under a topic because a regulatory record for that
                # product was filed under the topic. That is evidence of a filed device, not of a
                # capability, so it is added at TOPIC_RELATED and labelled by its basis.
                for row in evidence_rows:
                    for product_id in record_products.get(row["record_node"], set()):
                        if product_id in seen_products:
                            continue
                        seen_products.add(product_id)
                        products.append({
                            "product_id": product_id,
                            "name": _product_display(product_id),
                            "confirmation": TOPIC_RELATED,
                            "edge_type": EDGE_REGULATORY_PRODUCT,
                            "evidence_id": row["evidence_id"],
                            "source": row["source"],
                            "source_url": row["source_url"],
                            "valid_from": row["valid_from"],
                            "first_recorded_at": row["recorded_at"],
                            "capabilities": [{
                                "confirmation": TOPIC_RELATED,
                                "basis": "regulatory_record_topic",
                                "evidence_id": row["evidence_id"],
                                "source": row["source"],
                                "valid_from": row["valid_from"],
                                "recorded_at": row["recorded_at"],
                            }],
                        })
                if not products and not evidence_rows:
                    continue
                sorted_products = sorted(products, key=lambda item: (item["name"] or ""))
                sorted_evidence = sorted(
                    evidence_rows,
                    key=lambda item: (item.get("valid_from") or "", item.get("evidence_id") or ""),
                    reverse=True,
                )
                # A first-load topic branch can carry hundreds of regulatory products. Return a
                # bounded page plus the totals, so a phone does not download megabytes to render
                # a tree, and so a truncated list can never be mistaken for the complete set.
                company_branches.append({
                    "organization_id": org_id,
                    "display_name": (company.get("attrs") or {}).get("display_name", org_id),
                    "label_zh": (company.get("attrs") or {}).get("label_zh"),
                    "products": sorted_products[:max_products],
                    "products_total": len(sorted_products),
                    "evidence": sorted_evidence[:max_evidence],
                    "evidence_total": len(sorted_evidence),
                    "truncated": (
                        len(sorted_products) > max_products or len(sorted_evidence) > max_evidence
                    ),
                    "earliest_evidence": min(
                        (row.get("valid_from") or "" for row in evidence_rows + [
                            {key: value for key, value in product.items() if key == "valid_from"}
                            for product in products
                        ] if row),
                        default=None,
                    ) or None,
                    "latest_change": max(
                        (row.get("recorded_at") or "" for row in evidence_rows), default=None
                    ) or None,
                })
            if not company_branches:
                continue
            tree.append({
                "topic_id": topic_id,
                "family": topic.family if topic else (topic_node.get("attrs") or {}).get("family"),
                "label_en": (topic_node.get("attrs") or {}).get("label_en", topic_id),
                "label_zh": (topic_node.get("attrs") or {}).get("label_zh", topic_id),
                "description": (topic_node.get("attrs") or {}).get("description"),
                "companies": company_branches,
            })

        return {
            "known_at": snapshot["known_at"],
            "valid_at": snapshot["valid_at"],
            "mode": "public_time_reconstruction" if reconstructed else "knowledge_time",
            "reconstructed": reconstructed,
            "companies": selected,
            "topics": tree,
            "counts": {
                "topics_with_evidence": len(tree),
                "nodes": len(nodes),
                "edges": len(edges),
            },
            "time_semantics": _time_semantics(reconstructed),
        }

    def company_compare(self, *, companies: Sequence[str] | None = None,
                        topics: Sequence[str] | None = None,
                        known_at: Any = None, valid_at: Any = None) -> dict[str, Any]:
        """Evidence coverage per (company, topic). Never a capability score."""
        snapshot, reconstructed = self._cut(known_at, valid_at)
        nodes = snapshot["nodes"]
        edges = snapshot["edges"]
        company_nodes = {n["node_id"]: n for n in nodes if n["node_type"] == NODE_COMPANY}
        selected = list(companies) if companies else sorted(
            key.split(":", 1)[1] for key in company_nodes
        )
        selected_ids = {company_node_id(company) for company in selected}
        all_topics = [topic.id for topic in self.taxonomy.topics]
        wanted_topics = list(topics) if topics else all_topics

        record_companies: dict[str, set[str]] = {}
        for edge in edges:
            if edge["edge_type"] == EDGE_DOCUMENT_COMPANY and edge["src"]["node_type"] in RECORD_NODE_TYPES:
                record_companies.setdefault(edge["src"]["node_id"], set()).add(edge["dst"]["node_id"])

        capability: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for edge in edges:
            if edge["edge_type"] != EDGE_PRODUCT_CAPABILITY:
                continue
            topic_id = edge["dst"]["node_id"].split(":", 1)[1]
            product_id = edge["src"]["node_id"]
            for company_id in selected_ids:
                owned = {
                    e["dst"]["node_id"] for e in edges
                    if e["edge_type"] in (EDGE_COMPANY_PRODUCT,) and e["src"]["node_id"] == company_id
                }
                if product_id in owned:
                    capability.setdefault((company_id, topic_id), []).append({
                        "product_id": product_id,
                        "evidence_id": edge["attrs"].get("evidence_id"),
                        "source": edge["attrs"].get("source"),
                        "source_url": edge["attrs"].get("source_url"),
                        "basis": edge["attrs"].get("basis"),
                        "valid_from": edge["valid_from"],
                    })

        regulatory: dict[tuple[str, str], int] = {}
        publications: dict[tuple[str, str], int] = {}
        documents: dict[tuple[str, str], int] = {}
        for edge in edges:
            if edge["edge_type"] not in (EDGE_PUBLICATION_TOPIC, EDGE_RECORD_TOPIC):
                continue
            topic_id = edge["dst"]["node_id"].split(":", 1)[1]
            src_id = edge["src"]["node_id"]
            kind = edge["src"]["node_type"]
            for company_id in record_companies.get(src_id, set()):
                key = (company_id, topic_id)
                if kind == NODE_PUBLICATION:
                    publications[key] = publications.get(key, 0) + 1
                elif kind == NODE_REGULATORY:
                    regulatory[key] = regulatory.get(key, 0) + 1
                else:
                    documents[key] = documents.get(key, 0) + 1

        rows: list[dict[str, Any]] = []
        for topic_id in wanted_topics:
            topic = self.taxonomy.topic(topic_id)
            cells: list[dict[str, Any]] = []
            for company_id in sorted(selected_ids):
                org_id = company_id.split(":", 1)[1]
                caps = capability.get((company_id, topic_id), [])
                reg = regulatory.get((company_id, topic_id), 0)
                pub = publications.get((company_id, topic_id), 0)
                doc = documents.get((company_id, topic_id), 0)
                if caps or reg or pub or doc:
                    state = EVIDENCE_PRESENT
                else:
                    state = NO_EVIDENCE_FOUND
                cells.append({
                    "organization_id": org_id,
                    "display_name": (company_nodes.get(company_id, {}).get("attrs") or {}).get(
                        "display_name", org_id),
                    "label_zh": (company_nodes.get(company_id, {}).get("attrs") or {}).get(
                        "label_zh"),
                    "state": state,
                    "reported_capability_evidence": len(caps),
                    "regulatory_topic_evidence": reg,
                    "publication_topic_evidence": pub,
                    "official_document_topic_evidence": doc,
                    "evidence_ids": [row["evidence_id"] for row in caps][:10],
                    "statement": _cell_statement(state, caps, reg, pub, doc),
                })
            rows.append({
                "topic_id": topic_id,
                "label_en": topic.label_en if topic else topic_id,
                "label_zh": topic.label_zh if topic else topic_id,
                "family": topic.family if topic else None,
                "cells": cells,
            })

        return {
            "known_at": snapshot["known_at"],
            "valid_at": snapshot["valid_at"],
            "mode": "public_time_reconstruction" if reconstructed else "knowledge_time",
            "reconstructed": reconstructed,
            "rows": rows,
            "not_comparable_warning": (
                "These are counts of evidence of a stated kind, reported separately on purpose. "
                "A publication count is research activity by an affiliated author, not product "
                "capability. A regulatory record shows that a device was cleared, not which "
                "algorithm it runs. MedRadar does not rank companies by these numbers."
            ),
            "no_evidence_means": (
                "NO_EVIDENCE_FOUND means MedRadar holds no evidence of that kind in the sources it "
                "monitors. It does not mean the company lacks the technology, the product, or the "
                "research. Absence of evidence is not evidence of absence."
            ),
            "time_semantics": _time_semantics(reconstructed),
        }

    def node_detail(self, *, node_type: str, node_id: str, known_at: Any = None,
                    valid_at: Any = None) -> dict[str, Any]:
        """Evidence for one node, with citations that resolve to the observation ledger."""
        snapshot, reconstructed = self._cut(known_at, valid_at)
        node = next((n for n in snapshot["nodes"]
                     if n["node_type"] == node_type and n["node_id"] == node_id), None)
        incoming = [e for e in snapshot["edges"]
                    if e["dst"]["node_type"] == node_type and e["dst"]["node_id"] == node_id]
        outgoing = [e for e in snapshot["edges"]
                    if e["src"]["node_type"] == node_type and e["src"]["node_id"] == node_id]
        earliest = min((e["valid_from"] for e in incoming + outgoing if e.get("valid_from")),
                       default=None)
        latest = max((e["recorded_at"] for e in incoming + outgoing if e.get("recorded_at")),
                     default=None)
        return {
            "node_type": node_type,
            "node_id": node_id,
            "node": node,
            "known_at": snapshot["known_at"],
            "valid_at": snapshot["valid_at"],
            "mode": "public_time_reconstruction" if reconstructed else "knowledge_time",
            "reconstructed": reconstructed,
            "earliest_evidence": earliest,
            "latest_change": latest,
            "incoming": [self._edge_public(edge) for edge in incoming],
            "outgoing": [self._edge_public(edge) for edge in outgoing],
            "time_semantics": _time_semantics(reconstructed),
        }

    def changes_between(self, *, earlier: Any, later: Any = None) -> dict[str, Any]:
        """What the graph gained between two knowledge times. A diff of assertions."""
        before, _ = self._cut(earlier, None)
        after, _ = self._cut(later, None)
        before_map = {_edge_key(edge): edge for edge in before["edges"]}
        after_map = {_edge_key(edge): edge for edge in after["edges"]}
        added = [after_map[key] for key in sorted(set(after_map) - set(before_map))]
        removed = [before_map[key] for key in sorted(set(before_map) - set(after_map))]
        changed = [
            after_map[key] for key in sorted(set(after_map) & set(before_map))
            if after_map[key]["recorded_at"] != before_map[key]["recorded_at"]
        ]
        return {
            "earlier": before["known_at"],
            "later": after["known_at"],
            "added": [self._edge_public(edge) for edge in added],
            "removed": [self._edge_public(edge) for edge in removed],
            "changed": [self._edge_public(edge) for edge in changed],
            "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)},
            "note": (
                "A knowledge-time diff. Added means MedRadar recorded the assertion in this "
                "window; it does not mean the underlying event happened in this window."
            ),
        }

    def topic_evidence(self, topic_id: str, *, organization_id: str | None = None,
                       known_at: Any = None, valid_at: Any = None) -> dict[str, Any]:
        technology_map = self.technology_map(known_at=known_at, valid_at=valid_at)
        branch = next((topic for topic in technology_map["topics"]
                       if topic["topic_id"] == topic_id), None)
        if branch is None:
            return {"topic_id": topic_id, "found": False, "companies": []}
        if organization_id:
            branch = {**branch, "companies": [
                company for company in branch["companies"]
                if company["organization_id"] == organization_id
            ]}
        return {**branch, "found": True, "mode": technology_map["mode"],
                "reconstructed": technology_map["reconstructed"]}

    def _edge_public(self, edge: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "edge_type": edge["edge_type"],
            "src": edge["src"],
            "dst": edge["dst"],
            "confirmation": edge["attrs"].get("confirmation", UNKNOWN_RELATION),
            "method": edge["attrs"].get("method"),
            "evidence_id": edge["attrs"].get("evidence_id"),
            "observation_id": edge["attrs"].get("observation_id"),
            "source": edge["attrs"].get("source"),
            "source_url": edge["attrs"].get("source_url"),
            "matched_terms": edge["attrs"].get("matched_terms"),
            "valid_from": edge["valid_from"],
            "public_time": edge.get("public_time"),
            "public_time_basis": edge.get("public_time_basis"),
            "recorded_at": edge["recorded_at"],
            "rule_version": edge["attrs"].get("taxonomy_version"),
            "confidence": edge.get("confidence"),
        }

    # ------------------------------------------------------------------- summary
    def summary(self) -> dict[str, Any]:
        snapshot = self.query.snapshot()
        by_type: dict[str, int] = {}
        for node in snapshot["nodes"]:
            by_type[node["node_type"]] = by_type.get(node["node_type"], 0) + 1
        edges_by_type: dict[str, int] = {}
        confirmations: dict[str, int] = {}
        for edge in snapshot["edges"]:
            edges_by_type[edge["edge_type"]] = edges_by_type.get(edge["edge_type"], 0) + 1
            level = edge["attrs"].get("confirmation", UNKNOWN_RELATION)
            confirmations[level] = confirmations.get(level, 0) + 1
        return {
            "graph_version": GRAPH_VERSION,
            "taxonomy_version": self.taxonomy.version,
            "taxonomy_fingerprint": self.taxonomy.fingerprint,
            "known_at": snapshot["known_at"],
            "nodes": len(snapshot["nodes"]),
            "edges": len(snapshot["edges"]),
            "nodes_by_type": by_type,
            "edges_by_type": edges_by_type,
            "confirmations": confirmations,
            "store_counts": {
                "node_assertions": self.store.count("nodes"),
                "edge_assertions": self.store.count("edges"),
            },
        }


def _product_display(product_id: str) -> str:
    """A readable label from a product node id.

    The product node stores only its normalised key (storing the raw published name there made the
    shared node's content depend on which record materialised it first, which the assertion store
    rejects - correctly). The label is therefore derived from the key, and the exact published
    device name remains on the record node that states it.
    """
    key = product_id.split(":", 1)[1] if product_id.startswith("product:") else product_id
    slug = key.rsplit(":", 1)[0] if ":" in key else key
    text = " ".join(part for part in slug.replace("-", " ").split() if part)
    return text[:1].upper() + text[1:] if text else key


def _public_time(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """When the source made the record public, as a full instant - or nothing.

    A year or year-month publication date (``2026``, ``2026-11``) is a period, not a timestamp.
    ``public_time`` is therefore omitted for those precisions instead of being anchored to a day
    the source never stated. The record keeps the period in its own ``published_at`` and
    ``published_at_precision`` fields.
    """
    value = row.get("published_at")
    if not value:
        return None, None
    normalized, precision = normalize_moment(value)
    if not normalized or precision not in ("datetime", "date"):
        return None, None
    moment = parse_moment(normalized)
    if moment is None:
        return None, None
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z", "observed"


def _record_valid_from(row: Mapping[str, Any]) -> str:
    """The earliest date the record itself states, as a full instant.

    The record keeps its own precision (date/year) in the ledger; a graph assertion needs a
    single ordering anchor, so a year or year-month publication date is anchored to its first
    day *for interval ordering only*. That is the same convention the record layer uses for
    arithmetic, and it never changes what the record claims.
    """
    for field in ("published_at", "event_at", "first_observed_at"):
        value = row.get(field)
        if value:
            moment = parse_moment(value)
            if moment is not None:
                return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return normalize_moment("1970-01-01")[0]


def _edge_key(edge: Mapping[str, Any]) -> str:
    return (
        f"{edge['edge_type']}|{edge['src']['node_type']}:{edge['src']['node_id']}"
        f"->{edge['dst']['node_type']}:{edge['dst']['node_id']}"
    )


def _time_semantics(reconstructed: bool) -> dict[str, Any]:
    return {
        "recorded_at": "when MedRadar recorded the assertion (knowledge time, assigned by the store)",
        "valid_from": "the earliest date the evidence supports for the assertion (public/valid time)",
        "mode": "public_time_reconstruction" if reconstructed else "knowledge_time",
        "statement": (
            "This view was reconstructed from today's knowledge at a past public-date cutoff. It "
            "shows what was publicly true then, not what MedRadar knew then."
            if reconstructed else
            "This view is limited to assertions MedRadar had actually recorded at the cutoff. "
            "Evidence discovered later is excluded, even if it describes an earlier event."
        ),
        "cannot_do": (
            "A record is never backdated into a past knowledge state. If MedRadar discovered a "
            "2016 clearance in 2026, the 2026 knowledge view is the only one where it appears."
        ),
    }


def _cell_statement(state: str, caps: list, regulatory: int, publications: int, documents: int) -> str:
    if state == EVIDENCE_PRESENT:
        parts = []
        if caps:
            parts.append(f"{len(caps)} official product-capability statement(s)")
        if regulatory:
            parts.append(f"{regulatory} regulatory record(s) filed under this topic")
        if publications:
            parts.append(f"{publications} affiliated publication(s)")
        if documents:
            parts.append(f"{documents} official document(s)")
        return "Evidence present: " + ", ".join(parts) + "."
    return (
        "No evidence found in the monitored sources. This is not a claim that the company lacks "
        "the technology."
    )


def open_graph(path: str | Any, taxonomy: Taxonomy) -> TechnologyGraph:
    store = TKGStore(str(path))
    return TechnologyGraph(store, taxonomy)


def close_graph(graph: TechnologyGraph) -> None:
    try:
        graph.store.close()
    except Exception:  # pragma: no cover
        pass
