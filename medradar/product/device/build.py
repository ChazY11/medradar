"""Deterministic builder for the device index (PRODUCT-003).

Input: the committed openFDA snapshot (via the product Dataset). Output: applications, device
identities, PMA product families, recall records and every relation, each with its evidence.

Rules that are deliberately NOT applied here:

* a recall record never becomes a device identity: its product description is not an identity;
* two different K numbers are never merged into one device because they share a product code, an
  applicant or a similar name - that only produces a *candidate* relation;
* predicate relations are not created (openFDA exposes no predicate identifier);
* no relation is created from a fuzzy score alone, and no candidate is promoted to confirmed.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Sequence

from .identifiers import (
    NOT_MODELLED,
    RELATION_TYPES,
    application_id,
    device_id,
    external_application_id,
    family_id,
    normalise_pma_number,
)
from .model import (
    Application,
    DeviceRelation,
    DeviceIdentity,
    EvidenceRef,
    ProductFamily,
    RecallRecord,
)

CANDIDATE_CAP_PER_RECALL = 3
CANDIDATE_CLUSTER_MAX = 10
MIN_NAME_CHARS_FOR_CANDIDATE = 8

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+")


def _norm(value: str | None) -> str:
    return " ".join(_WS.split(str(value or "").casefold())).strip()


def _name_key(value: str | None) -> str:
    return " ".join(_TOKEN.findall(_norm(value)))


def _tokens(value: str | None) -> set[str]:
    return {token for token in _TOKEN.findall(_norm(value)) if len(token) >= 4}


def _split_models(trade_name: str | None) -> tuple[str, ...]:
    """FDA trade-name fields often list several models separated by commas."""
    text = str(trade_name or "").strip()
    if not text:
        return ()
    parts = [part.strip(" /;\t") for part in re.split(r",|;", text)]
    out: list[str] = []
    seen = set()
    for part in parts:
        if len(part) < 2:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return tuple(out[:40])


@dataclass
class DeviceIndex:
    snapshot_id: str
    applications: dict[str, Application]
    devices: dict[str, DeviceIdentity]
    families: dict[str, ProductFamily]
    recalls: dict[str, RecallRecord]
    relations: list[DeviceRelation]
    recall_k_references: dict[str, tuple[str, ...]] = field(default_factory=dict)
    external_k_references: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _by_official: dict[str, str] = field(default_factory=dict)
    _relations_by_source: dict[str, list[DeviceRelation]] = field(default_factory=dict)
    _relations_by_target: dict[str, list[DeviceRelation]] = field(default_factory=dict)
    _devices_by_org: dict[str, list[str]] = field(default_factory=dict)
    _devices_by_category: dict[str, list[str]] = field(default_factory=dict)
    _devices_by_product_code: dict[str, list[str]] = field(default_factory=dict)
    device_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------------- lookups
    def application(self, identifier: str) -> Application | None:
        if identifier in self.applications:
            return self.applications[identifier]
        target = self._by_official.get(identifier.upper())
        return self.applications.get(target) if target else None

    def device(self, identifier: str) -> DeviceIdentity | None:
        if identifier in self.devices:
            return self.devices[identifier]
        target = self._by_official.get(identifier.upper())
        return self.devices.get(target) if target else None

    def family(self, identifier: str) -> ProductFamily | None:
        return self.families.get(identifier)

    def relations_for(self, identifier: str) -> list[DeviceRelation]:
        """Relations touching an entity.

        For a device, the relations of its own application are included: a recall whose official
        K-number field names the application is a confirmed relation *about that device*, and hiding
        it would understate what is known.
        """
        seen: dict[str, DeviceRelation] = {}
        application_owner = None
        device = self.devices.get(identifier)
        if device is not None:
            application_owner = device.application_id
        for key in (identifier, application_owner):
            if not key:
                continue
            for relation in self._relations_by_source.get(key, []):
                seen[relation.relation_id] = relation
            for relation in self._relations_by_target.get(key, []):
                seen[relation.relation_id] = relation
        return sorted(seen.values(), key=lambda item: (item.status != "confirmed", item.relation_type, item.target_id))

    def confirmed(self, identifier: str) -> list[DeviceRelation]:
        return [relation for relation in self.relations_for(identifier) if relation.status == "confirmed"]

    def candidates(self, identifier: str) -> list[DeviceRelation]:
        return [relation for relation in self.relations_for(identifier) if relation.status == "candidate"]

    def devices_for_organization(self, organization_key: str) -> list[DeviceIdentity]:
        return [self.devices[item] for item in self._devices_by_org.get(organization_key, [])]

    def recalls_referencing(self, application_identifier: str) -> list[RecallRecord]:
        out = []
        for relation in self._relations_by_target.get(application_identifier, []):
            if relation.relation_type == "recall_references_application" and relation.source_id in self.recalls:
                out.append(self.recalls[relation.source_id])
        out.sort(key=lambda item: (item.initiated_date is None, item.initiated_date or ""), reverse=True)
        return out

    def family_versions(self, family_identifier: str) -> list[Application]:
        family = self.families.get(family_identifier)
        if not family:
            return []
        apps = [self.applications[item] for item in family.version_application_ids if item in self.applications]
        apps.sort(key=lambda item: (item.decision_date is None, item.decision_date or "", item.official_id))
        return apps

    def unlinked_recalls(self) -> list[RecallRecord]:
        out = [
            recall
            for event_id, recall in self.recalls.items()
            if not self.recall_k_references.get(event_id) and event_id in self.external_k_references
        ]
        return out

    def categories(self) -> list[dict[str, str]]:
        seen: dict[str, str] = {}
        for device in self.devices.values():
            if device.category_id:
                seen.setdefault(device.category_id, device.category_label or device.category_id)
        return [{"id": key, "label": label} for key, label in sorted(seen.items(), key=lambda item: item[1])]


def _app_from_event(event: Any, dataset: Any) -> Application | None:
    if event.event_type not in ("510k", "pma", "pma_supplement"):
        return None
    raw = event.raw or {}
    if event.event_type == "510k":
        official = str(raw.get("k_number") or event.official_id).strip().upper()
        return Application(
            application_id=application_id("openfda_510k", official),
            source_id="openfda_510k",
            official_id=official,
            kind="510k",
            official_url=event.official_url,
            event_id=event.event_id,
            applicant_name=event.applicant_name,
            organization_key=event.organization_key,
            product_code=event.product_code,
            advisory_committee=raw.get("advisory_committee_description"),
            device_name=event.device_name,
            trade_name=None,
            decision_date=event.event_date,
            decision_code=raw.get("decision_code"),
        )
    pma_number = normalise_pma_number(raw.get("pma_number") or "") or str(raw.get("pma_number") or "").strip().upper()
    if event.event_type == "pma":
        return Application(
            application_id=application_id("openfda_pma", pma_number),
            source_id="openfda_pma",
            official_id=pma_number,
            kind="pma",
            official_url=event.official_url,
            event_id=event.event_id,
            applicant_name=event.applicant_name,
            organization_key=event.organization_key,
            product_code=event.product_code,
            advisory_committee=raw.get("advisory_committee_description"),
            device_name=raw.get("generic_name") or event.device_name,
            trade_name=raw.get("trade_name"),
            decision_date=event.event_date,
            decision_code=raw.get("decision_code"),
            pma_number=pma_number,
        )
    supplement = str(raw.get("supplement_number") or "").strip().upper()
    parent = application_id("openfda_pma", pma_number)
    return Application(
        application_id=application_id("openfda_pma", pma_number + ":" + supplement),
        source_id="openfda_pma",
        official_id=pma_number + ":" + supplement,
        kind="pma_supplement",
        official_url=event.official_url,
        event_id=event.event_id,
        applicant_name=event.applicant_name,
        organization_key=event.organization_key,
        product_code=event.product_code,
        advisory_committee=raw.get("advisory_committee_description"),
        device_name=raw.get("generic_name") or event.device_name,
        trade_name=raw.get("trade_name"),
        decision_date=event.event_date,
        decision_code=raw.get("decision_code"),
        pma_number=pma_number,
        supplement_number=supplement,
        supplement_type=raw.get("supplement_type"),
        supplement_reason=raw.get("supplement_reason"),
        parent_application_id=parent,
    )


def _recall_from_event(event: Any) -> RecallRecord:
    raw = event.raw or {}
    k_numbers = tuple(
        sorted({str(item).strip().upper() for item in (raw.get("k_numbers") or []) if str(item).strip()})
    )
    return RecallRecord(
        event_id=event.event_id,
        official_id=str(raw.get("product_res_number") or event.official_id),
        official_url=event.official_url,
        applicant_name=event.applicant_name,
        organization_key=event.organization_key,
        product_code=event.product_code,
        product_description=event.device_name or raw.get("product_description"),
        reason_for_recall=raw.get("reason_for_recall"),
        root_cause=raw.get("root_cause_description"),
        recall_status=raw.get("recall_status"),
        initiated_date=raw.get("event_date_initiated") or event.event_date,
        posted_date=raw.get("event_date_posted") or event.published_at,
        res_event_number=str(raw.get("res_event_number") or "") or None,
        product_res_number=str(raw.get("product_res_number") or "") or None,
        k_numbers=k_numbers,
    )


def build_index(dataset: Any) -> DeviceIndex:
    snapshot_id = dataset.snapshot_id
    applications: dict[str, Application] = {}
    devices: dict[str, DeviceIdentity] = {}
    recalls: dict[str, RecallRecord] = {}
    families: dict[str, ProductFamily] = {}
    relations: list[DeviceRelation] = []
    by_official: dict[str, str] = {}
    device_applications: dict[str, list[str]] = defaultdict(list)
    events_by_application: dict[str, list[Any]] = defaultdict(list)

    # ---- records -> applications / recalls
    for event in dataset.events:
        if event.event_type == "recall":
            recalls[event.event_id] = _recall_from_event(event)
            continue
        application = _app_from_event(event, dataset)
        if application is None:
            continue
        applications[application.application_id] = application
        by_official[application.official_id.upper()] = application.application_id
        if application.kind == "510k":
            by_official["K" + application.official_id.lstrip("K")] = application.application_id
        events_by_application[application.application_id].append(event)
        if application.kind in ("510k", "pma"):
            device_applications[application.application_id].append(application.application_id)

    # ---- device identities (one per 510(k) clearance / PMA approval; never per recall)
    for app in applications.values():
        if app.kind not in ("510k", "pma"):
            continue
        first_event = events_by_application[app.application_id][0]
        identity_device_id = device_id(app.source_id, app.official_id)
        models = _split_models(app.trade_name) if app.kind == "pma" else ()
        name = (app.trade_name or app.device_name or app.official_id).strip()
        category = first_event.category
        devices[identity_device_id] = DeviceIdentity(
            device_id=identity_device_id,
            identity_basis="510k_clearance" if app.kind == "510k" else "pma_approval",
            application_id=app.application_id,
            kind=app.kind,
            official_id=app.official_id,
            name=name,
            applicant_name=app.applicant_name,
            organization_key=app.organization_key,
            product_code=app.product_code,
            category_id=category.id if category else None,
            category_label=category.label if category else None,
            device_class=first_event.device_class,
            first_event_date=app.decision_date,
            application_ids=(app.application_id,),
            models=models,
            record_count=1,
        )
        by_official[app.official_id.upper()] = identity_device_id

    # ---- PMA application families (official hierarchy: supplements share the PMA number)
    pma_groups: dict[str, list[Application]] = defaultdict(list)
    for app in applications.values():
        if app.kind in ("pma", "pma_supplement"):
            pma_groups[app.pma_number].append(app)
    for pma_number, group in pma_groups.items():
        original = next((item for item in group if item.kind == "pma"), None)
        versions = sorted((item for item in group if item.kind == "pma_supplement"), key=lambda item: (item.decision_date or "", item.official_id))
        family_identifier = family_id(pma_number)
        family_device = (
            device_id("openfda_pma", pma_number)
            if application_id("openfda_pma", pma_number) in applications
            else None
        )
        models: list[str] = []
        if original is not None:
            models.extend(_split_models(original.trade_name))
        for version in versions:
            for model in _split_models(version.trade_name):
                if model not in models:
                    models.append(model)
        dates = [item.decision_date for item in group if item.decision_date]
        families[family_identifier] = ProductFamily(
            family_id=family_identifier,
            kind="pma_application",
            name=(original.trade_name if original and original.trade_name else (original.device_name if original else pma_number)) or pma_number,
            organization_key=(original or group[0]).organization_key,
            applicant_name=(original or group[0]).applicant_name,
            device_id=family_device,
            application_id=application_id("openfda_pma", pma_number) if original else None,
            version_application_ids=tuple(item.application_id for item in versions),
            supplement_count=len(versions),
            first_event_date=min(dates) if dates else None,
            last_event_date=max(dates) if dates else None,
            models=tuple(models[:60]),
            original_in_snapshot=original is not None,
            basis="FDA PMA number: the original approval and every supplement that carries the same PMA number",
        )
        if family_device and family_device in devices:
            # frozen+slots dataclass: copy through replace(), never through __dict__
            devices[family_device] = replace(
                devices[family_device],
                family_id=family_identifier,
                models=tuple(models[:60]),
            )
        # confirmed application_has_supplement relations, only between endpoints present in the snapshot
        if original is not None:
            for version in versions:
                relations.append(
                    DeviceRelation(
                        relation_id="rel:supp:" + version.official_id,
                        relation_type="application_has_supplement",
                        status="confirmed",
                        source_id=original.application_id,
                        source_kind="application",
                        target_id=version.application_id,
                        target_kind="application",
                        rule="same_official_pma_number_v1",
                        evidence=(
                            EvidenceRef(kind="official_identifier", field="pma_number", value=pma_number, official_url=original.official_url, event_id=original.event_id),
                            EvidenceRef(kind="official_identifier", field="supplement_number", value=version.supplement_number or "", official_url=version.official_url, event_id=version.event_id),
                        ),
                        snapshot_id=snapshot_id,
                    )
                )
                # device_has_version is derived from this same relation on read (device detail), not
                # stored: duplicating 37k identical edges would only slow every build and query.

    # ---- recall -> application references (official k_numbers field only)
    k_applications = {
        app.official_id.upper(): app.application_id for app in applications.values() if app.kind == "510k"
    }
    recall_k_references: dict[str, tuple[str, ...]] = {}
    external_k_references: dict[str, tuple[str, ...]] = {}
    for recall in recalls.values():
        inside: list[str] = []
        outside: list[str] = []
        for k_number in recall.k_numbers:
            target = k_applications.get(k_number)
            if target:
                inside.append(target)
                relations.append(
                    DeviceRelation(
                        relation_id="rel:recall:" + recall.event_id + ":" + k_number,
                        relation_type="recall_references_application",
                        status="confirmed",
                        source_id=recall.event_id,
                        source_kind="recall",
                        target_id=target,
                        target_kind="application",
                        rule="official_k_numbers_field_v1",
                        evidence=(
                            EvidenceRef(kind="record_field", field="k_numbers", value=k_number, official_url=recall.official_url, event_id=recall.event_id),
                        ),
                        snapshot_id=snapshot_id,
                    )
                )
            else:
                outside.append(k_number)
                # The reference is official but the target 510(k) is not in this snapshot. It is
                # counted in external_k_references and shown on the recall, not materialised as an
                # edge to a record we do not have.
        if inside:
            recall_k_references[recall.event_id] = tuple(inside)
        if outside:
            external_k_references[recall.event_id] = tuple(outside)

    # ---- candidates: same applicant + product code + normalised device name (510(k) only)
    clusters: dict[tuple[str, str, str], list[Application]] = defaultdict(list)
    for app in applications.values():
        if app.kind != "510k":
            continue
        name_key = _name_key(app.device_name)
        if len(name_key) < MIN_NAME_CHARS_FOR_CANDIDATE:
            continue
        clusters[(_norm(app.applicant_name), app.product_code or "", name_key)].append(app)
    candidate_clusters = 0
    for (applicant_norm, product_code, name_key), members in clusters.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda item: (item.decision_date or "", item.official_id))
        anchor = members[0]
        candidate_clusters += 1
        for other in members[1:CANDIDATE_CLUSTER_MAX]:
            relations.append(
                DeviceRelation(
                    relation_id="rel:cand_dev:" + anchor.official_id + ":" + other.official_id,
                    relation_type="candidate_same_device",
                    status="candidate",
                    source_id=device_id("openfda_510k", anchor.official_id),
                    source_kind="device",
                    target_id=device_id("openfda_510k", other.official_id),
                    target_kind="device",
                    rule="same_applicant_product_code_normalised_device_name_v1",
                    evidence=(
                        EvidenceRef(kind="similarity_rule", field="applicant", value=anchor.applicant_name),
                        EvidenceRef(kind="similarity_rule", field="product_code", value=product_code),
                        EvidenceRef(kind="similarity_rule", field="device_name", value=name_key),
                    ),
                    snapshot_id=snapshot_id,
                    score=1.0,
                    note="identical applicant, product code and normalised device name; this is a candidate, not proof that the two clearances cover the same commercial device",
                )
            )

    # ---- candidates: recalls with no official K reference, same registry group + product code
    by_org_code: dict[tuple[str, str], list[Application]] = defaultdict(list)
    for app in applications.values():
        if app.kind == "510k" and app.organization_key and app.product_code:
            by_org_code[(app.organization_key, app.product_code)].append(app)
    candidate_recall_relations = 0
    for recall in recalls.values():
        if recall.event_id in recall_k_references:
            continue
        if not recall.organization_key or not recall.product_code:
            continue
        pool = by_org_code.get((recall.organization_key, recall.product_code), [])
        if not pool:
            continue
        recall_tokens = _tokens(recall.product_description)
        scored = []
        for app in pool:
            overlap = len(recall_tokens & _tokens(app.device_name))
            scored.append((overlap, app))
        scored.sort(key=lambda item: (-item[0], item[1].decision_date or "", item[1].official_id))
        for overlap, app in scored[:CANDIDATE_CAP_PER_RECALL]:
            candidate_recall_relations += 1
            relations.append(
                DeviceRelation(
                    relation_id="rel:cand_recall:" + recall.event_id + ":" + app.official_id,
                    relation_type="candidate_recall_application",
                    status="candidate",
                    source_id=recall.event_id,
                    source_kind="recall",
                    target_id=app.application_id,
                    target_kind="application",
                    rule="same_registry_group_product_code_v1",
                    evidence=(
                        EvidenceRef(kind="similarity_rule", field="organization_key", value=recall.organization_key or ""),
                        EvidenceRef(kind="similarity_rule", field="product_code", value=recall.product_code or ""),
                        EvidenceRef(kind="similarity_rule", field="device_name_token_overlap", value=str(overlap)),
                    ),
                    snapshot_id=snapshot_id,
                    score=round(min(1.0, 0.4 + 0.2 * overlap), 3),
                    note="the recall has no official K-number reference; this is a candidate based on the tracked group and product code, not evidence that the recall concerns this device",
                )
            )

    # ---- indexes
    by_source: dict[str, list[DeviceRelation]] = defaultdict(list)
    by_target: dict[str, list[DeviceRelation]] = defaultdict(list)
    for relation in relations:
        by_source[relation.source_id].append(relation)
        by_target[relation.target_id].append(relation)
    devices_by_org: dict[str, list[str]] = defaultdict(list)
    devices_by_category: dict[str, list[str]] = defaultdict(list)
    devices_by_product_code: dict[str, list[str]] = defaultdict(list)
    for device in devices.values():
        if device.organization_key:
            devices_by_org[device.organization_key].append(device.device_id)
        if device.category_id:
            devices_by_category[device.category_id].append(device.device_id)
        if device.product_code:
            devices_by_product_code[device.product_code].append(device.device_id)
    for bucket in (devices_by_org, devices_by_category, devices_by_product_code):
        for key in bucket:
            bucket[key].sort()

    confirmed_by_device: dict[str, int] = defaultdict(int)
    candidate_by_device: dict[str, int] = defaultdict(int)
    recalls_by_application: dict[str, list[str]] = defaultdict(list)
    # application -> owning device, so a relation about the application is a relation about the device
    app_to_device = {device.application_id: device.device_id for device in devices.values()}
    confirmed_ids: dict[str, set[str]] = defaultdict(set)
    candidate_ids: dict[str, set[str]] = defaultdict(set)
    for relation in relations:
        device_endpoints = set()
        if relation.source_kind == "device":
            device_endpoints.add(relation.source_id)
        if relation.target_kind == "device":
            device_endpoints.add(relation.target_id)
        if relation.source_kind == "application" and relation.source_id in app_to_device:
            device_endpoints.add(app_to_device[relation.source_id])
        if relation.target_kind == "application" and relation.target_id in app_to_device:
            device_endpoints.add(app_to_device[relation.target_id])
        for device_endpoint in device_endpoints:
            if relation.status == "confirmed":
                confirmed_ids[device_endpoint].add(relation.relation_id)
            elif relation.status == "candidate":
                candidate_ids[device_endpoint].add(relation.relation_id)
        if relation.status == "confirmed" and relation.relation_type == "recall_references_application":
            recalls_by_application[relation.target_id].append(relation.source_id)
    for device_identifier, relation_ids in confirmed_ids.items():
        confirmed_by_device[device_identifier] = len(relation_ids)
    for device_identifier, relation_ids in candidate_ids.items():
        candidate_by_device[device_identifier] = len(relation_ids)
    device_stats: dict[str, dict[str, int]] = {}
    for device in devices.values():
        family = families.get(device.family_id) if device.family_id else None
        versions = family.supplement_count if family else 0
        application_ids = [device.application_id]
        if family:
            application_ids.extend(family.version_application_ids)
        recall_count = len({recall_id for application_identifier in application_ids for recall_id in recalls_by_application.get(application_identifier, [])})
        device_stats[device.device_id] = {
            "applications": 1 + versions,
            "versions": versions,
            "recalls": recall_count,
            "confirmed_relations": confirmed_by_device.get(device.device_id, 0),
            "candidate_relations": candidate_by_device.get(device.device_id, 0),
        }

    stats = {
        "applications": len(applications),
        "applications_by_kind": {
            kind: sum(1 for app in applications.values() if app.kind == kind)
            for kind in ("510k", "pma", "pma_supplement")
        },
        "devices": len(devices),
        "families": len(families),
        "families_without_original": sum(1 for family in families.values() if not family.original_in_snapshot),
        "recalls": len(recalls),
        "recalls_with_confirmed_application": len(recall_k_references),
        "recalls_with_external_reference_only": sum(
            1 for event_id in external_k_references if event_id not in recall_k_references
        ),
        "recalls_without_any_reference": sum(
            1 for event_id in recalls if event_id not in recall_k_references and event_id not in external_k_references
        ),
        "candidate_device_clusters": candidate_clusters,
        "candidate_recall_relations": candidate_recall_relations,
        "relation_types": dict(RELATION_TYPES),
        "not_modelled": dict(NOT_MODELLED),
    }
    index = DeviceIndex(
        snapshot_id=snapshot_id,
        applications=applications,
        devices=devices,
        families=families,
        recalls=recalls,
        relations=relations,
        recall_k_references=recall_k_references,
        external_k_references=external_k_references,
        _by_official=by_official,
        _relations_by_source={key: list(value) for key, value in by_source.items()},
        _relations_by_target={key: list(value) for key, value in by_target.items()},
        _devices_by_org={key: list(value) for key, value in devices_by_org.items()},
        _devices_by_category={key: list(value) for key, value in devices_by_category.items()},
        _devices_by_product_code={key: list(value) for key, value in devices_by_product_code.items()},
        device_stats=device_stats,
        stats=stats,
    )
    return index
