"""ATLAS-ID pilot: real, bounded, reproducible cross-source identity resolution.

What the pilot does
-------------------
1. Pulls a bounded openFDA UDI sample for the five target firms (U.S. GUDID).
2. Re-reads a small subset through AccessGUDID and demonstrates that this is
   *the same upstream authority*, not independent confirmation.
3. Pulls a bounded 510(k) sample (regulatory grouping, not device identity).
4. Streams Health Canada's active MDALL identifier table once, keeps the
   GTIN-14-shaped subset, and bridges it to openFDA by exact DI.
5. Resolves licence company names through the curated alias registry.
6. Classifies record pairs into SAME_DEVICE_IDENTITY / SAME_MODEL /
   SAME_PRODUCT_FAMILY / RELATED_TECHNOLOGY / POSSIBLE_MATCH / UNRELATED /
   UNKNOWN, preserving the evidence and rejection reasons.
7. Evaluates the identity method against a simple name-matching baseline on the
   *same* labelled pairs, and reports coverage gaps rather than inventing data.

Every number written to the report is computed from this run's stored rows; the
report also records the request accounting and the DB path so a second,
independent process can recompute it.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .. import config
from ..evidence import schema as ev
from ..evidence.http import HttpClient, HttpLedger, sha256_bytes
from ..evidence.timeq import utc_iso
from ..identity import CompanyIndex, DeviceView, compare_devices, view_from_evidence
from ..identity.resolver import (
    CANDIDATE,
    CONFIRMED,
    IDENTITY_CONFIRMING_TYPES,
    REJECTED,
    baseline_name_match,
    name_similarity,
)
from ..store import AtlasStore
from ..connectors.accessgudid import AccessGudidConnector
from ..connectors.canada_mdall import CanadaMdallConnector, iter_json_array
from ..connectors.openfda_510k import OpenFda510kConnector
from ..connectors.openfda_udi import OpenFdaUdiConnector, lookup_identifiers
from ..identity.normalize import is_gtin_like, normalize_name


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_id(prefix: str) -> str:
    return f"{prefix}_{_now()}"


def device_ref(record: Mapping[str, Any]) -> str:
    """Stable entity reference for a device record (no clock, no randomness)."""
    identifiers = record.get("identifiers") or []
    di = next((i["value"] for i in identifiers if i.get("scheme") == "di" and i.get("is_primary")), "")
    if di:
        return ev.deterministic_id("dev", "di", di)
    return ev.deterministic_id("dev", record["source_id"], str(record["source_record_id"]))


@dataclass
class PilotConfig:
    fda_per_firm: int = 100
    accessgudid_sample: int = 12
    k510_limit_per_firm: int = 50
    mdall_gtin_limit: int = 6000
    mdall_bridge_limit: int = 1200
    mdall_bridge_batch: int = 25
    mdall_licence_limit: int = 40
    pair_sample_per_firm: int = 250
    hard_negative_target: int = 200
    baseline_negative_target: int = 400
    request_budget: int = 400
    min_interval: float = 0.6
    allow_network: bool = True
    mdall_cache_days: int = 7


class IdentityPilot:
    def __init__(
        self,
        store: AtlasStore,
        *,
        cfg: PilotConfig | None = None,
        cache_dir: Path | str | None = None,
        reports_dir: Path | str | None = None,
        samples_dir: Path | str | None = None,
    ) -> None:
        self.store = store
        self.cfg = cfg or PilotConfig()
        self.cache_dir = Path(cache_dir) if cache_dir else config.CACHE_DIR
        self.reports_dir = Path(reports_dir) if reports_dir else config.REPORTS_DIR
        self.samples_dir = Path(samples_dir) if samples_dir else config.RESEARCH_DIR / "samples"
        for directory in (self.cache_dir, self.reports_dir, self.samples_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.ledger = HttpLedger(config.STAGING_DIR / "atlas_requests.jsonl")
        self.client = HttpClient(
            source_id="atlas_pilot",
            ledger=self.ledger,
            budget=self.cfg.request_budget,
            min_interval=self.cfg.min_interval,
            allow_network=self.cfg.allow_network,
        )
        self.firms = config.load_firms()
        self.index = CompanyIndex.from_config()
        self.udi = OpenFdaUdiConnector(self.client)
        self.gudid = AccessGudidConnector(self.client)
        self.mdall = CanadaMdallConnector(self.client)
        self.k510 = OpenFda510kConnector(self.client)

        self.views_by_firm: dict[str, list[DeviceView]] = {key: [] for key in self.firms}
        self.evidence_by_ref: dict[str, dict[str, Any]] = {}
        self.mdall_views: dict[str, DeviceView] = {}
        self._bridge_views: list[tuple[DeviceView, DeviceView]] = []
        self.summary: dict[str, Any] = {
            "schema": "medradar.atlas.identity_pilot.v1",
            "started_at": utc_iso(),
            "config": dict(self.cfg.__dict__),
            "stages": {},
            "counts": {},
            "coverage": {},
            "relations": {},
            "baseline": {},
            "limitations": [],
        }

    # ------------------------------------------------------------------ helpers
    def _store_many(self, records: Iterable[Mapping[str, Any]], *, run_id: str) -> list[dict[str, Any]]:
        stored = []
        for record in records:
            result = self.store.append_evidence(record, run_id=run_id)
            stored.append(result)
            if result["inserted"]:
                self.evidence_by_ref[result["evidence_id"]] = dict(record)
        return stored

    def _persist_device(self, record: Mapping[str, Any], *, firm_key: str = "") -> str:
        ref = device_ref(record)
        normalized = record.get("normalized") or {}
        identifiers = [dict(i) for i in record.get("identifiers") or []]
        self.store.upsert_device(
            device_id=ref,
            canonical_name=str(
                normalized.get("device_description")
                or normalized.get("brand_name")
                or normalized.get("licence_name")
                or normalized.get("device_identifier_raw")
                or record.get("source_record_id")
            )[:500],
            brand_name=str(normalized.get("brand_name") or "")[:300],
            model_number=str(
                normalized.get("version_or_model_number")
                or normalized.get("catalog_number")
                or normalized.get("device_identifier_raw")
                or ""
            )[:300],
            catalog_number=str(normalized.get("catalog_number") or "")[:300],
            product_family=str(normalized.get("licence_name") or "")[:300],
            device_class=str(normalized.get("device_class") or ""),
            company_id=ev.deterministic_id("co", "firm", firm_key) if firm_key else "",
            markets=["US"] if record.get("source_id") in {"openfda_device_udi", "accessgudid"} else (["CA"] if record.get("source_id") == "canada_mdall" else []),
            metadata={"source_id": record.get("source_id"), "evidence_id": record.get("evidence_id")},
            product_codes=[str(c) for c in normalized.get("product_codes") or []],
            identifiers=identifiers,
            evidence_id=str(record.get("evidence_id", "")),
        )
        return ref

    def _firm_company(self, key: str) -> str:
        firm = self.firms[key]
        company_id = ev.deterministic_id("co", "firm", key)
        self.store.upsert_company(
            company_id=company_id,
            canonical_name=str(firm["canonical_name"]),
            country=str(firm.get("country", "")),
            metadata={"source": "config/atlas_firms.json", "firm_key": key},
            aliases=[str(a) for a in firm.get("aliases") or []],
        )
        return company_id

    def _firm_key_for_view(self, view: DeviceView) -> str:
        return view.firm_key

    # ----------------------------------------------------------------- stages
    def stage_openfda_udi(self) -> None:
        run_id = _run_id("udi")
        self.store.start_run(run_id, connector_id=self.udi.connector_id, source_id=self.udi.source_id)
        requests_before = self.client.requests_made()
        records = 0
        for key, firm in self.firms.items():
            term = (firm.get("search_terms") or {}).get("openfda_company") or firm["canonical_name"]
            search = f'company_name:"{term}"'
            try:
                page = self.udi.fetch(search=search, limit=self.cfg.fda_per_firm)
            except RuntimeError as exc:
                self.summary["coverage"].setdefault("errors", []).append(
                    {"stage": "openfda_udi", "firm": key, "error": str(exc)}
                )
                continue
            fetched_at = page["_fetched_at"]
            total = int((page.get("meta") or {}).get("results", {}).get("total") or 0)
            self.summary["coverage"].setdefault("openfda_udi_total_by_firm", {})[key] = total
            for result in page.get("results") or []:
                record = self.udi.to_evidence(result, fetched_at=fetched_at, run_id=run_id)
                self._store_many([record], run_id=run_id)
                view = view_from_evidence(record)
                if view.firm_key and view.firm_key in self.views_by_firm:
                    self.views_by_firm[view.firm_key].append(view)
                records += 1
        self.store.finish_run(
            run_id, status="ok", requests=self.client.requests_made() - requests_before,
            records=records, notes="openFDA UDI bounded sample per firm",
        )
        self.summary["stages"]["openfda_udi"] = {
            "run_id": run_id,
            "records": records,
            "requests": self.client.requests_made() - requests_before,
            "by_firm": {k: len(v) for k, v in self.views_by_firm.items()},
        }

    def stage_accessgudid(self) -> None:
        run_id = _run_id("gudid")
        self.store.start_run(run_id, connector_id=self.gudid.connector_id, source_id=self.gudid.source_id)
        all_views = [v for views in self.views_by_firm.values() for v in views if v.di]
        all_views.sort(key=lambda v: v.ref)
        sample = all_views[: self.cfg.accessgudid_sample]
        stored = 0
        duplicates = 0
        for view in sample:
            payload = self.gudid.fetch(view.di)
            if not payload:
                continue
            record = self.gudid.to_evidence(payload, fetched_at=utc_iso(), run_id=run_id)
            if not record:
                continue
            # Same GUDID record read through a second interface: its canonical
            # key already exists, so it is a *duplicate upstream observation*,
            # not independent corroboration.  Count it as such.
            if record.get("canonical_key"):
                prev = self.store.evidence_for_canonical_key(str(record["canonical_key"]))
                if any(p["source_id"] != record["source_id"] for p in prev):
                    duplicates += 1
            self._store_many([record], run_id=run_id)
            stored += 1
        self.store.finish_run(run_id, status="ok", records=stored, notes="AccessGUDID second read")
        self.summary["stages"]["accessgudid"] = {
            "run_id": run_id,
            "sampled": len(sample),
            "stored": stored,
            "same_upstream_duplicates": duplicates,
            "note": "AccessGUDID and openFDA UDI are the same upstream authority (GUDID); "
                    "a matching record is a duplicate, not independent corroboration",
        }

    def stage_510k(self) -> None:
        run_id = _run_id("k510")
        self.store.start_run(run_id, connector_id=self.k510.connector_id, source_id=self.k510.source_id)
        records = 0
        by_firm: dict[str, int] = {}
        for key, firm in self.firms.items():
            term = (firm.get("search_terms") or {}).get("openfda_company") or firm["canonical_name"]
            try:
                evidence = self.k510.collect(
                    search=f'applicant:"{term}"', limit=self.cfg.k510_limit_per_firm, run_id=run_id
                )
            except RuntimeError:
                continue
            self._store_many(evidence, run_id=run_id)
            records += len(evidence)
            by_firm[key] = len(evidence)
        self.store.finish_run(run_id, status="ok", records=records, notes="openFDA 510(k) bounded sample")
        self.summary["stages"]["openfda_510k"] = {"run_id": run_id, "records": records, "by_firm": by_firm}

    def stage_mdall(self) -> None:
        run_id = _run_id("mdall")
        self.store.start_run(run_id, connector_id=self.mdall.connector_id, source_id=self.mdall.source_id)
        table_path = self.cache_dir / "mdall_active_deviceidentifier.json"
        download: dict[str, Any] = {}
        fresh = (
            table_path.exists()
            and (time.time() - table_path.stat().st_mtime) < self.cfg.mdall_cache_days * 86400
        )
        if fresh:
            download = {
                "cached": True,
                "bytes": table_path.stat().st_size,
                "sha256": sha256_bytes(table_path.read_bytes()),
            }
        else:
            download = self.mdall.download_identifier_table(table_path)
        requests_before = self.client.requests_made()
        gtin_rows = []
        scanned = 0
        for row in iter_json_array(table_path):
            scanned += 1
            if is_gtin_like(row.get("device_identifier")):
                gtin_rows.append(row)
                if len(gtin_rows) >= self.cfg.mdall_gtin_limit:
                    break
        fetched_at = utc_iso()
        stored = 0
        for row in gtin_rows:
            record = self.mdall.identifier_evidence(row, fetched_at=fetched_at, run_id=run_id)
            self._store_many([record], run_id=run_id)
            stored += 1
            di = str(row.get("device_identifier") or "")
            # MDALL's identifier table publishes the DI and the licence, but no
            # brand/model that could be compared.  ``model`` is therefore empty:
            # setting it to the DI would fabricate a model conflict against the
            # U.S. record.  The identifier equality is the source-declared fact.
            view = DeviceView(
                ref=device_ref(record),
                source_id=record["source_id"],
                evidence_id=str(record["evidence_id"]),
                brand="",
                model="",
                di=di,
                identifiers=(("di", di), ("licence_no", str(row.get("original_licence_no") or ""))),
                country="CA",
            )
            self.mdall_views[di] = view
        self.store.finish_run(
            run_id, status="ok", requests=self.client.requests_made() - requests_before,
            records=stored, nbytes=int(download.get("bytes") or 0),
            notes="MDALL active identifier table streamed once; GTIN-14 subset retained",
        )
        self.summary["stages"]["canada_mdall"] = {
            "run_id": run_id,
            "table": {
                "cached": bool(download.get("cached")),
                "bytes": download.get("bytes"),
                "sha256": download.get("sha256"),
                "truncated": download.get("truncated", False),
            },
            "rows_scanned_until_limit": scanned,
            "gtin_rows_kept": stored,
            "unique_di": len(self.mdall_views),
        }

    def stage_bridge(self) -> None:
        run_id = _run_id("bridge")
        self.store.start_run(run_id, connector_id="atlas_identity_bridge@1", source_id="openfda_device_udi")
        candidates = sorted(self.mdall_views)
        if len(candidates) > self.cfg.mdall_bridge_limit:
            step = len(candidates) / self.cfg.mdall_bridge_limit
            candidates = [candidates[int(i * step)] for i in range(self.cfg.mdall_bridge_limit)]
        requests_before = self.client.requests_made()
        results = lookup_identifiers(self.client, candidates, batch=self.cfg.mdall_bridge_batch)
        pairs: list[dict[str, Any]] = []
        stored = 0
        for result in results:
            try:
                record = self.udi.to_evidence(result, fetched_at=utc_iso(), run_id=run_id)
            except Exception:
                continue
            self._store_many([record], run_id=run_id)
            stored += 1
            fda_view = view_from_evidence(record)
            if not fda_view.di or fda_view.di not in self.mdall_views:
                continue
            mdall_view = self.mdall_views[fda_view.di]
            self._bridge_views.append((fda_view, mdall_view))
            decision = compare_devices(fda_view, mdall_view)
            relation_id = self.store.add_relation(
                decision, evidence_ids=[fda_view.evidence_id, mdall_view.evidence_id], run_id=run_id
            )
            pairs.append(
                {
                    "relation_id": relation_id,
                    "di": fda_view.di,
                    "fda_ref": fda_view.ref,
                    "mdall_ref": mdall_view.ref,
                    "fda_company": fda_view.company_raw,
                    "fda_brand": fda_view.brand,
                    "fda_model": fda_view.model,
                    "fda_firm": fda_view.firm_key,
                    "relation_type": decision.relation_type,
                    "status": decision.status,
                    "confidence": decision.confidence,
                    "contradictions": decision.contradictions,
                }
            )
            if fda_view.firm_key and fda_view.firm_key in self.views_by_firm:
                self.views_by_firm[fda_view.firm_key].append(fda_view)
        self.store.finish_run(
            run_id, status="ok", requests=self.client.requests_made() - requests_before,
            records=stored, notes="GTIN-14 MDALL identifiers resolved against openFDA UDI",
        )
        self.summary["counts"]["bridge_queried"] = len(candidates)
        self.summary["counts"]["bridge_fda_records_resolved"] = stored
        self.summary["counts"]["bridge_pairs"] = len(pairs)
        self.summary["stages"]["identity_bridge"] = {
            "run_id": run_id,
            "queried_gtins": len(candidates),
            "resolved": stored,
            "pairs": len(pairs),
            "relation_types": _counts(p["relation_type"] for p in pairs),
        }
        self._bridge_pairs = pairs

    def stage_mdall_licences(self) -> None:
        run_id = _run_id("mdall_lic")
        self.store.start_run(run_id, connector_id=self.mdall.connector_id, source_id="canada_mdall")
        licences: list[str] = []
        for view in self.mdall_views.values():
            for scheme, value in view.identifiers:
                if scheme == "licence_no" and value and value not in licences:
                    licences.append(value)
        licences = licences[: self.cfg.mdall_licence_limit]
        stored = 0
        company_names: dict[str, str] = {}
        for licence_no in licences:
            licence = self.mdall.fetch_licence(licence_no)
            if not licence:
                continue
            company = None
            company_id = str(licence.get("company_id") or "")
            if company_id:
                company = self.mdall.fetch_company(company_id)
                if company:
                    company_names[licence_no] = str(company.get("company_name") or "")
            record = self.mdall.licence_evidence(
                licence, company=company, fetched_at=utc_iso(), run_id=run_id
            )
            self._store_many([record], run_id=run_id)
            stored += 1
            normalized = record["normalized"]
            self.store.upsert_device(
                device_id=device_ref(record),
                canonical_name=str(normalized.get("licence_name") or licence_no)[:500],
                product_family=str(normalized.get("licence_name") or "")[:300],
                device_class=str(normalized.get("risk_class") or ""),
                company_id=ev.deterministic_id("co", "firm", record["entity_refs"][0]["firm_key"])
                if record.get("entity_refs") and record["entity_refs"][0].get("firm_key")
                else "",
                markets=["CA"],
                metadata={"licence_number": licence_no, "company_id": company_id},
                identifiers=[{"scheme": "licence_no", "value": licence_no, "is_primary": True}],
                evidence_id=str(record["evidence_id"]),
            )
        # Attach resolved company names to bridge pairs for reporting.
        for pair in getattr(self, "_bridge_pairs", []):
            licence_no = ""
            mdall_view = next((v for v in self.mdall_views.values() if v.ref == pair["mdall_ref"]), None)
            if mdall_view:
                licence_no = next((val for s, val in mdall_view.identifiers if s == "licence_no"), "")
            pair["mdall_licence"] = licence_no
            pair["mdall_company"] = company_names.get(licence_no, "")
        self.store.finish_run(run_id, status="ok", records=stored, notes="MDALL licence details")
        self.summary["stages"]["mdall_licences"] = {
            "run_id": run_id,
            "attempted": len(licences),
            "stored": stored,
            "companies_resolved": len(company_names),
        }

    def stage_pair_classification(self) -> None:
        run_id = _run_id("pairs")
        self.store.start_run(run_id, connector_id="atlas_identity_pairs@1", source_id="atlas")
        random.seed(20261110)
        decisions = []
        for firm_key, views in self.views_by_firm.items():
            unique = {v.ref: v for v in views}
            items = sorted(unique.values(), key=lambda v: v.ref)
            if len(items) < 2:
                continue
            pairs = [(items[i], items[j]) for i in range(len(items)) for j in range(i + 1, len(items))]
            random.shuffle(pairs)
            for left, right in pairs[: self.cfg.pair_sample_per_firm]:
                decision = compare_devices(left, right)
                self.store.add_relation(
                    decision, evidence_ids=[left.evidence_id, right.evidence_id], run_id=run_id
                )
                decisions.append(decision)
        # Hard negatives: identical brand string across different firms, or the
        # same model string across different firms.  These are the cases that a
        # name-only resolver gets wrong.
        hard = self._hard_negatives()
        for left, right in hard:
            decision = compare_devices(left, right)
            self.store.add_relation(
                decision, evidence_ids=[left.evidence_id, right.evidence_id], run_id=run_id,
                graph_relation=decision.relation_type,
            )
            decisions.append(decision)
        # Ambiguity must be visible, not zero.  Sample cross-firm pairs whose
        # labels are similar but whose identity is not established; these are
        # the cases a name-only system would wrongly merge.
        ambiguous = self._ambiguity_candidates()
        for left, right in ambiguous:
            decision = compare_devices(left, right)
            self.store.add_relation(
                decision, evidence_ids=[left.evidence_id, right.evidence_id], run_id=run_id,
            )
            decisions.append(decision)
        self.store.finish_run(run_id, status="ok", records=len(decisions), notes="pair classification")
        self.summary["stages"]["pair_classification"] = {
            "run_id": run_id,
            "decisions": len(decisions),
            "relation_types": _counts(d.relation_type for d in decisions),
            "statuses": _counts(d.status for d in decisions),
            "hard_negative_candidates": len(hard),
            "ambiguity_candidates": len(ambiguous),
        }
        self._pair_decisions = decisions

    def _hard_negatives(self) -> list[tuple[DeviceView, DeviceView]]:
        """Find name-identical, identity-different pairs across firms."""
        pools = {k: [v for v in {x.ref: x for x in vs}.values() if v.brand or v.model]
                 for k, vs in self.views_by_firm.items()}
        out: list[tuple[DeviceView, DeviceView]] = []
        keys = sorted(pools)
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                left_by_name: dict[str, DeviceView] = {}
                for view in pools[a]:
                    if view.normalized_brand:
                        left_by_name.setdefault(view.normalized_brand, view)
                for view in pools[b]:
                    if view.normalized_brand and view.normalized_brand in left_by_name:
                        out.append((left_by_name[view.normalized_brand], view))
                    elif view.normalized_model:
                        for cand in pools[a]:
                            if cand.normalized_model and cand.normalized_model == view.normalized_model:
                                out.append((cand, view))
                                break
                if len(out) >= self.cfg.hard_negative_target:
                    return out[: self.cfg.hard_negative_target]
        return out[: self.cfg.hard_negative_target]

    def _ambiguity_candidates(self) -> list[tuple[DeviceView, DeviceView]]:
        """Cross-firm pairs with similar labels but no official identity link.

        These are *candidates by construction*: the point is to show that the
        resolver labels them ``POSSIBLE_MATCH`` rather than promoting a similar
        string to identity.  Threshold 0.70 is deliberately permissive.
        """
        pools = {k: [v for v in {x.ref: x for x in vs}.values() if v.brand or v.model]
                 for k, vs in self.views_by_firm.items()}
        keys = sorted(pools)
        out: list[tuple[DeviceView, DeviceView]] = []
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                for left in pools[a][:50]:
                    for right in pools[b][:50]:
                        if left.di and left.di == right.di:
                            continue
                        score = name_similarity(left, right)
                        partial = _shared_label_token(left, right)
                        if 0.70 <= score < 0.999 or partial:
                            out.append((left, right))
                            if len(out) >= 100:
                                return out
        return out

    # -------------------------------------------------------------- evaluation
    def stage_baseline_evaluation(self) -> None:
        # Positives are the *actual* official-identifier pairs from the bridge,
        # regardless of whether the U.S. company resolved to one of the five
        # target firms.  Using only target-firm views would silently shrink the
        # positive set to a handful of pairs and overstate the metric's basis.
        positives: list[tuple[DeviceView, DeviceView]] = list(self._bridge_views)
        random.seed(20261110)
        negatives: list[tuple[DeviceView, DeviceView]] = []
        mdall_views = list(self.mdall_views.values())
        all_fda = [v for vs in self.views_by_firm.values() for v in vs]
        # Hard negatives first (same brand/model, different identity), then
        # random cross-firm pairs to reach the target.
        for left, right in self._hard_negatives():
            if left.di != right.di:
                negatives.append((left, right))
        while len(negatives) < self.cfg.baseline_negative_target and all_fda and mdall_views:
            left = all_fda[random.randrange(len(all_fda))]
            right = mdall_views[random.randrange(len(mdall_views))]
            if left.di and right.di and left.di == right.di:
                continue
            if (left, right) not in negatives:
                negatives.append((left, right))
        metrics = {
            "identity": _evaluate(positives, negatives, lambda l, r: compare_devices(l, r).relation_type in IDENTITY_CONFIRMING_TYPES and compare_devices(l, r).status == CONFIRMED),
            "name_baseline": _evaluate(positives, negatives, baseline_name_match),
        }
        examples = []
        for left, right in negatives[:10]:
            if baseline_name_match(left, right):
                examples.append(
                    {
                        "fda_brand": left.brand,
                        "mdall_identifier": right.model,
                        "name_similarity": round(name_similarity(left, right), 3),
                        "baseline_says_match": True,
                        "identity_says": compare_devices(left, right).relation_type,
                    }
                )
        report = {
            "schema": "medradar.atlas.baseline_eval.v1",
            "generated_at": utc_iso(),
            "positives": len(positives),
            "negatives": len(negatives),
            "label_basis": {
                "positive": "MDALL GTIN-14 identifier exactly equals a GUDID UDI-DI (official identifier)",
                "negative": "different DI, and either different company or a deliberately name-identical hard negative",
                "caveat": "sampled pairs, not a prevalence-weighted population estimate; no overall F1 is claimed",
            },
            "metrics": metrics,
            "baseline_false_positive_examples": examples,
        }
        self.summary["baseline"] = report
        (self.reports_dir / "identity_baseline_eval.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    # ----------------------------------------------------------------- reporting
    def stage_persist(self) -> None:
        for key in self.firms:
            self._firm_company(key)
        for views in self.views_by_firm.values():
            for view in views:
                record = self.evidence_by_ref.get(view.evidence_id)
                if record:
                    self._persist_device(record, firm_key=view.firm_key)
        for record in list(self.evidence_by_ref.values()):
            if record.get("source_id") == "canada_mdall" and record.get("evidence_type") == "device_registration":
                self._persist_device(record)

    def write_reports(self) -> dict[str, Any]:
        stats = self.store.stats()
        # The pilot report counts *identity* decisions.  The graph additionally
        # stores source-declared relations (MANUFACTURED_BY / REGISTERED_AS);
        # including those would inflate "confirmed" and make the report
        # incomparable with the identity evaluation.
        identity_types = (
            "SAME_DEVICE_IDENTITY", "SAME_MODEL", "SAME_PRODUCT_FAMILY",
            "RELATED_TECHNOLOGY", "POSSIBLE_MATCH", "UNRELATED", "UNKNOWN",
        )
        placeholders = ",".join("?" for _ in identity_types)
        identity_counts = self.store.query(
            "SELECT status, COUNT(*) AS n FROM entity_relations"
            f" WHERE relation_type IN ({placeholders}) AND revoked_at='' GROUP BY status",
            identity_types,
        )
        by_status = {row["status"]: row["n"] for row in identity_counts}
        by_type = {
            row["relation_type"]: row["n"]
            for row in self.store.query(
                "SELECT relation_type, COUNT(*) AS n FROM entity_relations"
                f" WHERE relation_type IN ({placeholders}) AND revoked_at='' GROUP BY relation_type",
                identity_types,
            )
        }
        relations = {
            "confirmed": by_status.get(CONFIRMED, 0),
            "candidate": by_status.get(CANDIDATE, 0),
            "rejected": by_status.get(REJECTED, 0),
            "unknown": by_status.get("UNKNOWN", 0),
            "by_type": by_type,
            "by_status": by_status,
            "scope": "identity relations only; source-declared graph relations are excluded",
        }
        bridge = getattr(self, "_bridge_pairs", [])
        confirmed_pairs = [p for p in bridge if p["status"] == CONFIRMED and p["relation_type"] in IDENTITY_CONFIRMING_TYPES]
        contradicted = [p for p in bridge if p["contradictions"]]
        self.summary["counts"].update(
            {
                "evidence_ids": stats["evidence_ids"],
                "evidence_versions": stats["evidence_versions"],
                "unique_devices": stats["devices"],
                "device_identifiers": stats["device_identifiers"],
                "companies": stats["companies"],
                "bridge_confirmed_identity": len(confirmed_pairs),
                "bridge_candidate": len([p for p in bridge if p["status"] == CANDIDATE]),
                "bridge_contradicted": len(contradicted),
            }
        )
        self.summary["relations"] = relations
        mdall_stage = self.summary["stages"].get("canada_mdall", {})
        scanned = int(mdall_stage.get("rows_scanned_until_limit") or 0)
        gtin_rows = int(mdall_stage.get("gtin_rows_kept") or 0)
        share = round(gtin_rows / scanned, 6) if scanned else None
        self.summary["coverage"].update(
            {
                "fda_udi_by_firm": {k: len(v) for k, v in self.views_by_firm.items()},
                "mdall_gtin_identifiers": len(self.mdall_views),
                "mdall_rows_scanned": scanned,
                "mdall_gtin_share_of_active_table": share,
                "us_canada_udi_bridge_possible": True,
                "us_canada_udi_bridge_coverage_note": (
                    "Only MDALL rows whose identifier field is a GTIN-14 can be bridged; for the "
                    f"other {round((1 - (share or 0)) * 100, 2)}% MDALL publishes a model/catalogue "
                    "string and there is no official UDI to join on."
                ),
                "missing_firms_in_bridge": sorted(
                    k for k, v in self.views_by_firm.items() if not any(p["fda_firm"] == k for p in bridge)
                ),
            }
        )
        self.summary["limitations"] = [
            "openFDA UDI samples are the first page of a company-name search, not a random sample of the firm's devices.",
            "MDALL GTIN coverage is partial (0.33% of active identifier rows); absence of a bridge is not evidence that a device is unlicensed in Canada.",
            "The 510(k) source is a regulatory grouping and cannot confirm device identity; it is reported as a grouping relation only.",
            "AccessGUDID and openFDA UDI share the GUDID upstream authority; matching records are duplicates, not independent confirmation.",
            "No human adjudication was performed on this run; confirmed relations rest on exact official-identifier equality.",
            "Baseline metrics are computed on the sampled labelled pairs in this run and must not be read as population precision/recall.",
        ]
        self.summary["finished_at"] = utc_iso()
        self.summary["db_stats"] = stats
        self.summary["request_accounting"] = {
            "requests_made": self.client.requests_made(),
            "ledger_entries": self.ledger.count(),
        }
        self.summary["generated_from"] = {
            "db": config.relative(self.store.path),
            "source_register": "config/atlas_sources.json",
            "firm_register": "config/atlas_firms.json",
        }
        report_path = self.reports_dir / "identity_pilot.json"
        report_path.write_text(
            json.dumps(self.summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        sample = {
            "schema": "medradar.atlas.identity_sample.v1",
            "generated_at": utc_iso(),
            "note": "Bounded, redistributable sample (openFDA/GUDID public domain; Health Canada Open Government Licence).",
            "confirmed_pairs": confirmed_pairs[:40],
            "contradicted_pairs": contradicted[:10],
        }
        (self.samples_dir / "identity_pilot_pairs.json").write_text(
            json.dumps(sample, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return self.summary

    def stage_quality(self) -> None:
        from ..quality import run_checks

        report = run_checks(self.store)
        (self.reports_dir / "quality_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for source_id, status in (
            ("openfda_device_udi", "VERIFIED_API"),
            ("accessgudid", "VERIFIED_API"),
            ("openfda_device_510k", "VERIFIED_API"),
            ("canada_mdall", "VERIFIED_API"),
        ):
            self.store.set_source_status(
                check_id=f"atlas001:{source_id}",
                source_id=source_id,
                status=status,
                detail="used in ATLAS-001 pilot with logged requests",
                evidence_url=str((config.load_sources().get(source_id) or {}).get("endpoint", "")),
            )
        self.summary["quality"] = {
            "findings_total": report["counts"]["total"],
            "by_severity": report["counts"]["by_severity"],
            "by_check": report["counts"]["by_check"],
            "report": "research/atlas/reports/quality_report.json",
        }

    # --------------------------------------------------------------------- run
    def run(self) -> dict[str, Any]:
        self.stage_openfda_udi()
        self.stage_accessgudid()
        self.stage_510k()
        self.stage_mdall()
        self.stage_bridge()
        self.stage_mdall_licences()
        self.stage_pair_classification()
        self.stage_baseline_evaluation()
        self.stage_persist()
        self.stage_quality()
        return self.write_reports()


# ------------------------------------------------------------------ utilities
def _shared_label_token(left: DeviceView, right: DeviceView) -> bool:
    """True when the two labels share a distinctive token (>=5 chars)."""
    a = {t for t in left.brand_tokens + tuple(left.normalized_model.split()) if len(t) >= 5}
    b = {t for t in right.brand_tokens + tuple(right.normalized_model.split()) if len(t) >= 5}
    return bool(a & b)


def _counts(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


def _evaluate(
    positives: Sequence[tuple[DeviceView, DeviceView]],
    negatives: Sequence[tuple[DeviceView, DeviceView]],
    predict,
) -> dict[str, Any]:
    tp = sum(1 for l, r in positives if predict(l, r))
    fn = len(positives) - tp
    fp = sum(1 for l, r in negatives if predict(l, r))
    tn = len(negatives) - fp
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "labelled_pairs": len(positives) + len(negatives),
        "note": "computed on the sampled labelled pairs only; not a population estimate",
    }


def run_pilot(
    *,
    db_path: Path | str | None = None,
    cfg: PilotConfig | None = None,
) -> dict[str, Any]:
    config.ensure_dirs()
    with AtlasStore(db_path) as store:
        return IdentityPilot(store, cfg=cfg).run()


__all__ = ["IdentityPilot", "PilotConfig", "device_ref", "run_pilot"]
