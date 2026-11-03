"""S-029 step 07 — assemble the evidenced claim store (the scientific object of S-029).

Inputs are the tables produced by steps 04-06. This step creates the three logical
entities of RELATION_ONTOLOGY.md — `Entity`, `Evidence`, `RelationClaim` — and
writes them as JSONL so that every downstream number can be recomputed.

Design choices that matter for honesty
--------------------------------------
* Nothing is inferred that a source did not state. A trial sponsor string is a
  statement by the registrant; an affiliation string is a statement by the authors.
  Both are `SHA256`-addressed evidence rows.
* A rejected or ambiguous mapping still produces a row (in `claim_rejects`), so the
  error rate is measurable instead of invisible.
* `HUMAN_CONFIRMED` is never emitted by this script. Only a real adjudication file
  could produce it.
* Four clocks are carried separately (`event_at`, `published_at`, `declared_at`,
  `first_seen_at`), each with its own precision, plus `valid_from/valid_to` for the
  relation. `first_seen_at` is the real collection wall clock; a huge
  `observed_lag_days` is the honest signature of a historical backfill and is what
  makes a point-in-time claim impossible.
* Co-affiliation is emitted as its own predicate with an explicit
  `interpretation_limit`, because it is the easiest place in this project to
  accidentally claim knowledge transfer.

Run:  python research/studies/relation_network_s029/code/s029_07_claims.py
Writes: data/entities.jsonl, data/evidence.jsonl, data/claims.jsonl,
        data/claim_rejects.jsonl, artifacts/claims_summary.json
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, classify_date_precision, norm_name,
                         read_jsonl, sha256_text, utcnow_iso, write_json, write_jsonl)

# The company mapping rules live in a numbered module; import them by path so the
# claim builder uses exactly the same identity decisions as step 05.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "s029_company_map", Path(__file__).resolve().parent / "s029_05_company_map.py")
_company_map = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_company_map)
map_string = _company_map.map_string
load_register = _company_map.load_register
not_company_strings = _company_map.not_company_strings

EXTRACTION_VERSION = "s029-1.0.0"
COMPANY_DISPLAY = {
    "medtronic": ("Medtronic", "Medtronic plc"),
    "ge_healthcare": ("GE HealthCare", "GE HealthCare Technologies Inc."),
    "philips": ("Philips", "Royal Philips (Koninklijke Philips N.V.)"),
    "draeger": ("Dräger", "Drägerwerk AG & Co. KGaA"),
    "mindray": ("Mindray", "Shenzhen Mindray Bio-Medical Electronics Co., Ltd."),
}
ACCEPTED_COMPANY = {"EXACT", "ALIAS", "ORG_TEXT", "ORG_EMAIL"}

DOI_IN_CITATION = re.compile(r"doi:\s*(10\.\d{4,9}/[^\s,;)\]]+)", re.I)
PMID_IN_CITATION = re.compile(r"PMID:?\s*(\d{6,9})", re.I)


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26] if "T" in s else s[:10], fmt)
        except ValueError:
            continue
    return None


def lag_days(first_seen_at: str | None, published_at: str | None) -> int | None:
    a, b = parse_dt(first_seen_at), parse_dt(published_at)
    if not a or not b:
        return None
    return (a - b).days


def time_basis(published_at: str | None, first_seen_at: str | None) -> tuple[str, int | None]:
    """Classify how the relation's public date was obtained.

    ACTUAL_OBSERVATION is only granted when we observed the record within a week of
    its own public date. In a historical sweep this is expected to be almost never,
    and the artefact reports the count rather than assuming it.
    """
    lag = lag_days(first_seen_at, published_at)
    if not published_at:
        return "TIME_UNKNOWN", lag
    if lag is not None and 0 <= lag <= 7:
        return "ACTUAL_OBSERVATION", lag
    return "HISTORICAL_PROXY", lag


def claim_id(predicate: str, subject: str, obj: str, source_record: str, role: str) -> str:
    h = sha256_text(f"{predicate}|{subject}|{obj}|{source_record}|{role}")[:20]
    return f"rel:{predicate}:{h}"


def main() -> None:
    trials = {t["nct_id"]: t for t in read_jsonl(DATA_DIR / "ctgov_trials.jsonl")}
    sites = list(read_jsonl(DATA_DIR / "ctgov_sites.jsonl"))
    pubs = {p["pub_key"]: p for p in read_jsonl(DATA_DIR / "epmc_pubs.jsonl")}
    mentions = list(read_jsonl(DATA_DIR / "company_mentions.jsonl"))
    institutions = list(read_jsonl(DATA_DIR / "institutions.jsonl"))

    entities: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    claims: list[dict] = []
    rejects: list[dict] = []
    counters: dict = defaultdict(Counter)

    # ------------------------------------------------------------------
    # Companies
    # ------------------------------------------------------------------
    for ck, (disp, legal) in COMPANY_DISPLAY.items():
        eid = f"ent:company:{ck}"
        entities[eid] = {"entity_id": eid, "entity_type": "company_legal",
                         "canonical_name": legal, "display_name": disp,
                         "known_aliases": [], "stable_external_ids": {},
                         "identity_confidence": 0.95 if ck in ("medtronic", "philips") else 0.9,
                         "identity_evidence": ["artifacts/company_entity_register.json"],
                         "valid_from": None, "valid_to": None, "parent_entity_id": None,
                         "register_source": "ENTITY_HISTORY_REGISTER.md (entity auditor)"}
    seen_aliases: dict[str, set] = defaultdict(set)
    for m in mentions:
        ck = m.get("company_key")
        if not ck:
            continue
        eid = f"ent:company:{ck}"
        a = (m["raw_string"] or "").strip()
        if a and a not in seen_aliases[eid] and len(seen_aliases[eid]) < 400:
            seen_aliases[eid].add(a)
            entities[eid]["known_aliases"].append(
                {"string": a, "mapping_status": m["mapping_status"],
                 "rule": m["rule"], "source": m["source"]})

    # ------------------------------------------------------------------
    # Institutions (ROR entities)
    # ------------------------------------------------------------------
    inst_by_candidate: dict[str, str] = {}
    for ic in institutions:
        ror = ic.get("ror") or {}
        if ror.get("status") in ("EXACT", "FUZZY") and ror.get("ror_id"):
            eid = f"ent:institution:{ror['ror_id'].rsplit('/', 1)[-1]}"
            inst_by_candidate[ic["candidate_id"]] = eid
            if eid not in entities:
                entities[eid] = {
                    "entity_id": eid, "entity_type": "research_institution",
                    "canonical_name": ror.get("matched_name") or ic["raw_string"],
                    "known_aliases": [], "stable_external_ids": {"ror": ror["ror_id"]},
                    "identity_confidence": ror.get("confidence"),
                    "identity_evidence": [f"ROR lookup for '{ic['raw_string']}' "
                                          f"(matched field: {ror.get('matched_field')})"],
                    "country": ror.get("country"),
                    "valid_from": None, "valid_to": None, "parent_entity_id": None,
                    "ror_match_status": ror.get("status")}
            entities[eid]["known_aliases"].append(
                {"string": ic["raw_string"], "mapping_status": ror.get("status"),
                 "rule": ror.get("matched_field"), "source": "ROR resolution"})

    # ------------------------------------------------------------------
    # Trials, publications, topics as entities
    # ------------------------------------------------------------------
    for nct, t in trials.items():
        entities[f"ent:trial:{nct}"] = {
            "entity_id": f"ent:trial:{nct}", "entity_type": "clinical_trial",
            "canonical_name": t.get("brief_title") or nct,
            "known_aliases": [], "stable_external_ids": {"nct": nct},
            "identity_confidence": 1.0,
            "identity_evidence": ["ClinicalTrials.gov registry record"],
            "valid_from": (t.get("start_date") or {}).get("date"),
            "valid_to": (t.get("completion_date") or {}).get("date"),
            "parent_entity_id": None,
            "org_study_id": t.get("org_study_id"),
            "overall_status": t.get("overall_status")}
    for pk, p in pubs.items():
        eid = f"ent:publication:{pk}"
        ids = {}
        for k in ("doi", "pmid", "pmcid"):
            if p.get(k):
                ids[k] = p[k]
        entities[eid] = {
            "entity_id": eid, "entity_type": "publication",
            "canonical_name": (p.get("title") or pk)[:200],
            "known_aliases": [], "stable_external_ids": ids,
            "identity_confidence": 1.0 if ids else 0.6,
            "identity_evidence": ["Europe PMC record"],
            "valid_from": p.get("first_publication_date"),
            "valid_to": None, "parent_entity_id": None,
            "source_db": p.get("source_db")}
        for m in p.get("mesh_terms") or []:
            d = m.get("descriptor")
            if not d:
                continue
            tid = "ent:topic:" + re.sub(r"[^a-z0-9]+", "-", norm_name(d))[:80]
            if tid not in entities:
                entities[tid] = {"entity_id": tid, "entity_type": "topic",
                                 "canonical_name": d, "known_aliases": [],
                                 "stable_external_ids": ({"mesh": m["ui"]} if m.get("ui") else {}),
                                 "identity_confidence": 0.9,
                                 "identity_evidence": ["Europe PMC MeSH heading"],
                                 "valid_from": None, "valid_to": None, "parent_entity_id": None}
            pk_claim = claim_id("HAS_TOPIC", eid, tid, pk, "mesh_index_term")
            claims.append({
                "relation_id": pk_claim, "subject_id": eid, "predicate": "HAS_TOPIC",
                "object_id": tid, "relation_role": "mesh_index_term",
                "statement_status": "SOURCE_STATES_IT", "mapping_status": "EXACT",
                "claim_status": "VERIFIED_BY_SOURCE", "confidence": 0.9,
                "mapping_method": "mesh_descriptor_identity",
                "source_record_id": pk,
                "evidence_id": f"{p['evidence_id']}:{pk}",
                "relation_temporal_type": "POINT",
                "valid_from": p.get("first_publication_date"), "valid_to": None,
                "declared_at": p.get("first_publication_date"),
                "event_at": p.get("first_publication_date"),
                "published_at": p.get("first_index_date") or p.get("first_publication_date"),
                "first_seen_at": p.get("first_seen_at"),
                "observed_lag_days": lag_days(p.get("first_seen_at"),
                                              p.get("first_index_date") or p.get("first_publication_date")),
                "time_basis": "SOURCE_PUBLISHED",
                "timestamp_precision": classify_date_precision(p.get("first_publication_date")),
                "extraction_version": EXTRACTION_VERSION})

    # ------------------------------------------------------------------
    # Evidence rows
    # ------------------------------------------------------------------
    def add_evidence(eid: str, source: str, url: str | None, record_id: str,
                     payload_hash: str, text_ref: str, published_at: str | None,
                     source_updated_at: str | None, first_seen_at: str | None,
                     precision: str, quality: str) -> str:
        # One evidence row per (retrieved payload, source record). The payload hash stays the
        # verifiable address of the committed bytes; the record id is appended so that a claim's
        # original_text_reference can never point at a different record from the same payload.
        # (A payload-level-only key silently did that: one query payload holds up to 200 studies.)
        if eid and not eid.endswith(":" + record_id):
            eid = f"{eid}:{record_id}"
        if eid in evidence:
            return eid
        evidence[eid] = {
            "evidence_id": eid, "source": source, "original_url": url,
            "source_record_id": record_id, "payload_hash": payload_hash,
            "original_text_reference": text_ref[:600],
            "published_at": published_at, "source_updated_at": source_updated_at,
            "first_seen_at": first_seen_at, "ingested_at": utcnow_iso(),
            "timestamp_precision": precision, "provenance_quality": quality}
        return eid

    # Every collected record gets an evidence row, even if no relation claim is built from
    # it: a claim must never point at an evidence id that the evidence table cannot resolve
    # (verification check V1b). This is a construction guarantee, not an empirical finding.
    for nct, t in trials.items():
        add_evidence(t["evidence_id"], "clinicaltrials_gov_api_v2", t.get("source_url"), nct,
                     t["evidence_id"].replace("ev:", ""),
                     f"ClinicalTrials.gov study record {nct}",
                     (t.get("study_first_post_date") or {}).get("date"),
                     (t.get("last_update_post_date") or {}).get("date"),
                     t.get("first_seen_at"),
                     classify_date_precision((t.get("study_first_post_date") or {}).get("date")),
                     "PRIMARY_STRUCTURED")
    for pk, p in pubs.items():
        add_evidence(p["evidence_id"], "europepmc", p.get("source_url"), pk,
                     p["evidence_id"].replace("ev:", ""),
                     f"Europe PMC record {pk}",
                     p.get("first_index_date") or p.get("first_publication_date"),
                     p.get("date_of_revision"), p.get("first_seen_at"),
                     classify_date_precision(p.get("first_publication_date")),
                     "PRIMARY_TEXT")

    # ------------------------------------------------------------------
    # Relation A: company -> trial, from structured registry fields
    # ------------------------------------------------------------------
    for m in mentions:
        if m["record_kind"] != "trial" or not m.get("company_key"):
            continue
        if m["role"] not in ("lead_sponsor", "collaborator", "responsible_party"):
            continue
        t = trials.get(m["record_id"])
        if not t:
            continue
        eid = add_evidence(m["evidence_id"], "clinicaltrials_gov_api_v2",
                           t.get("source_url"), t["nct_id"],
                           m["evidence_id"].replace("ev:", ""),
                           f"protocolSection.sponsorCollaboratorsModule.{m['role']}"
                           f" = {m['raw_string']!r}",
                           (t.get("study_first_post_date") or {}).get("date"),
                           (t.get("last_update_post_date") or {}).get("date"),
                           t.get("first_seen_at"),
                           classify_date_precision((t.get("study_first_post_date") or {}).get("date")),
                           "PRIMARY_STRUCTURED")
        subject = f"ent:company:{m['company_key']}"
        role = m["role"]
        if m["mapping_status"] not in ACCEPTED_COMPANY:
            rejects.append({"reject_id": "rej:" + sha256_text(m["mention_id"])[:16],
                            "source": m["source"], "record_kind": "trial",
                            "record_id": m["record_id"], "role": role,
                            "raw_string": m["raw_string"], "company_key": m.get("company_key"),
                            "mapping_status": m["mapping_status"], "rule": m["rule"],
                            "reason": m["reason"], "evidence_id": m["evidence_id"],
                            "kept_for": "false-positive / ambiguity measurement"})
            counters["trial_company_rejects"][m["mapping_status"]] += 1
            continue
        basis, lag = time_basis((t.get("study_first_post_date") or {}).get("date"),
                                t.get("first_seen_at"))
        cid = claim_id("SPONSORS_TRIAL" if role != "responsible_party" else "RESPONSIBLE_FOR_TRIAL",
                       subject, f"ent:trial:{t['nct_id']}", t["nct_id"], role)
        claims.append({
            "relation_id": cid, "subject_id": subject,
            "predicate": "SPONSORS_TRIAL" if role != "responsible_party" else "RESPONSIBLE_FOR_TRIAL",
            "object_id": f"ent:trial:{t['nct_id']}", "relation_role": role,
            "statement_status": "SOURCE_STATES_IT",
            "mapping_status": m["mapping_status"],
            "claim_status": "CANDIDATE" if m["mapping_status"] == "ALIAS" else "VERIFIED_BY_SOURCE",
            "confidence": m["confidence"], "mapping_method": m["rule"],
            "source_record_id": t["nct_id"], "evidence_id": eid,
            "relation_temporal_type": "INTERVAL",
            "valid_from": (t.get("study_first_post_date") or {}).get("date"),
            "valid_to": None,
            "declared_at": (t.get("study_first_post_date") or {}).get("date"),
            "event_at": (t.get("start_date") or {}).get("date"),
            "event_at_type": (t.get("start_date") or {}).get("type"),
            "published_at": (t.get("study_first_post_date") or {}).get("date"),
            "first_seen_at": t.get("first_seen_at"),
            "observed_lag_days": lag, "time_basis": basis,
            "observation_system": ("THIS_STUDY_COLLECTION" if basis == "ACTUAL_OBSERVATION"
                                   else "NONE"),
            "timestamp_precision": classify_date_precision(
                (t.get("study_first_post_date") or {}).get("date")),
            "anachronism": bool(m.get("anachronism_if_mapped")),
            "extraction_version": EXTRACTION_VERSION})
        counters["trial_company_claims"][f"{role}:{m['mapping_status']}"] += 1

    # ------------------------------------------------------------------
    # Relation A': institution -> trial (sponsor, collaborator, site)
    # ------------------------------------------------------------------
    cand_index = {}
    for ic in institutions:
        cand_index[(ic["family"], norm_name(ic["raw_string"]))] = ic
    used_facility_keys = set()
    for s in sites:
        key = ("trial_site_facility", norm_name(s["facility"] or ""))
        if key not in cand_index:
            continue
        ic = cand_index[key]
        eid_inst = inst_by_candidate.get(ic["candidate_id"])
        if not eid_inst:
            continue
        t = trials.get(s["nct_id"])
        # Evidence must be the payload envelope the facility string came from, so that the
        # claim resolves back to committed bytes (verified by step 12).
        ev = add_evidence(s["evidence_id"], "clinicaltrials_gov_api_v2",
                          t.get("source_url") if t else None, s["nct_id"],
                          s["evidence_id"].replace("ev:", ""),
                          f"protocolSection.contactsLocationsModule.locations[].facility = "
                          f"{s['facility']!r}",
                          (t.get("study_first_post_date") or {}).get("date") if t else None,
                          (t.get("last_update_post_date") or {}).get("date") if t else None,
                          t.get("first_seen_at") if t else None,
                          "DAY", "PRIMARY_STRUCTURED")
        status = ic["ror"]["status"]
        cid = claim_id("HOSTS_TRIAL_SITE", eid_inst, f"ent:trial:{s['nct_id']}",
                       s["nct_id"], "site_facility")
        claims.append({
            "relation_id": cid, "subject_id": eid_inst,
            "predicate": "HOSTS_TRIAL_SITE", "object_id": f"ent:trial:{s['nct_id']}",
            "relation_role": "site_facility", "statement_status": "SOURCE_STATES_IT",
            "mapping_status": status,
            "claim_status": "VERIFIED_BY_SOURCE" if status == "EXACT" else "CANDIDATE",
            "confidence": ic["ror"]["confidence"], "mapping_method": "ror_" + str(ic["ror"].get("matched_field")),
            "source_record_id": s["nct_id"], "evidence_id": ev,
            "relation_temporal_type": "INTERVAL",
            "valid_from": (t.get("study_first_post_date") or {}).get("date") if t else None,
            "valid_to": None,
            "declared_at": (t.get("study_first_post_date") or {}).get("date") if t else None,
            "event_at": (t.get("start_date") or {}).get("date") if t else None,
            "published_at": (t.get("study_first_post_date") or {}).get("date") if t else None,
            "first_seen_at": t.get("first_seen_at") if t else None,
            "observed_lag_days": lag_days(t.get("first_seen_at") if t else None,
                                          (t.get("study_first_post_date") or {}).get("date") if t else None),
            "time_basis": time_basis((t.get("study_first_post_date") or {}).get("date") if t else None,
                                      t.get("first_seen_at") if t else None)[0],
            "timestamp_precision": "DAY",
            "interpretation_limit": "site participation is not evidence of cooperation with the sponsor",
            "extraction_version": EXTRACTION_VERSION})
        counters["site_claims"][status] += 1

    # trial organisation fields -> institution claims
    for m in mentions:
        if m["record_kind"] != "trial" or m.get("company_key"):
            continue
        if m["role"] not in ("lead_sponsor", "collaborator"):
            continue
        key = ("trial_organisation", norm_name(m["raw_string"]))
        ic = cand_index.get(key)
        if not ic:
            continue
        eid_inst = inst_by_candidate.get(ic["candidate_id"])
        if not eid_inst:
            counters["trial_institution_rejects"]["UNMAPPED"] += 1
            continue
        t = trials.get(m["record_id"])
        if not t:
            continue
        status = ic["ror"]["status"]
        ev = add_evidence(m["evidence_id"], "clinicaltrials_gov_api_v2", t.get("source_url"),
                          t["nct_id"], m["evidence_id"].replace("ev:", ""),
                          f"protocolSection.sponsorCollaboratorsModule.{m['role']} = "
                          f"{m['raw_string']!r}",
                          (t.get("study_first_post_date") or {}).get("date"),
                          (t.get("last_update_post_date") or {}).get("date"),
                          t.get("first_seen_at"),
                          classify_date_precision((t.get("study_first_post_date") or {}).get("date")),
                          "PRIMARY_STRUCTURED")
        pred = "SPONSORS_TRIAL" if m["role"] == "lead_sponsor" else "SPONSORS_TRIAL"
        cid = claim_id(pred, eid_inst, f"ent:trial:{t['nct_id']}", t["nct_id"], m["role"])
        claims.append({
            "relation_id": cid, "subject_id": eid_inst, "predicate": pred,
            "object_id": f"ent:trial:{t['nct_id']}", "relation_role": m["role"],
            "statement_status": "SOURCE_STATES_IT", "mapping_status": status,
            "claim_status": "VERIFIED_BY_SOURCE" if status == "EXACT" else "CANDIDATE",
            "confidence": ic["ror"]["confidence"],
            "mapping_method": "ror_" + str(ic["ror"].get("matched_field")),
            "source_record_id": t["nct_id"], "evidence_id": ev,
            "relation_temporal_type": "INTERVAL",
            "valid_from": (t.get("study_first_post_date") or {}).get("date"),
            "valid_to": None,
            "declared_at": (t.get("study_first_post_date") or {}).get("date"),
            "event_at": (t.get("start_date") or {}).get("date"),
            "published_at": (t.get("study_first_post_date") or {}).get("date"),
            "first_seen_at": t.get("first_seen_at"),
            "observed_lag_days": lag_days(t.get("first_seen_at"),
                                          (t.get("study_first_post_date") or {}).get("date")),
            "time_basis": time_basis((t.get("study_first_post_date") or {}).get("date"),
                                     t.get("first_seen_at"))[0],
            "timestamp_precision": classify_date_precision(
                (t.get("study_first_post_date") or {}).get("date")),
            "extraction_version": EXTRACTION_VERSION})
        counters["trial_institution_claims"][f"{m['role']}:{status}"] += 1

    # ------------------------------------------------------------------
    # Relation A'': trial -> publication (registry references)
    # ------------------------------------------------------------------
    for nct, t in trials.items():
        for ref in t.get("references") or []:
            pmid = ref.get("pmid")
            cit = ref.get("citation") or ""
            doi_m = DOI_IN_CITATION.search(cit)
            doi = doi_m.group(1).rstrip(".") if doi_m else None
            if not pmid and not doi:
                continue
            obj_key = None
            if doi:
                obj_key = f"doi:{doi.lower()}"
            elif pmid:
                obj_key = f"pmid:{pmid}"
            obj_id = f"ent:publication:{obj_key}" if obj_key in pubs else None
            ev = add_evidence(t["evidence_id"], "clinicaltrials_gov_api_v2", t.get("source_url"),
                              nct, t["evidence_id"].replace("ev:", ""),
                              f"protocolSection.referencesModule.references[] = {cit[:240]!r}",
                              (t.get("study_first_post_date") or {}).get("date"),
                              (t.get("last_update_post_date") or {}).get("date"),
                              t.get("first_seen_at"), "DAY", "PRIMARY_STRUCTURED")
            cid = claim_id("REFERENCES_PUBLICATION", f"ent:trial:{nct}",
                           obj_id or f"ext:publication:{obj_key}", nct, ref.get("type") or "reference")
            claims.append({
                "relation_id": cid, "subject_id": f"ent:trial:{nct}",
                "predicate": "REFERENCES_PUBLICATION", "object_id": obj_id,
                "object_external_id": {"pmid": pmid, "doi": doi},
                "relation_role": (ref.get("type") or "reference").lower(),
                "statement_status": "SOURCE_STATES_IT",
                "mapping_status": "EXACT" if obj_id else "UNMAPPED",
                "claim_status": "VERIFIED_BY_SOURCE" if obj_id else "CANDIDATE",
                "confidence": 0.9 if obj_id else 0.6,
                "mapping_method": "registry_reference_pmid_doi" if obj_id else "registry_reference_only",
                "source_record_id": nct, "evidence_id": ev,
                "relation_temporal_type": "POINT",
                "valid_from": (t.get("study_first_post_date") or {}).get("date"),
                "valid_to": None,
                "declared_at": (t.get("study_first_post_date") or {}).get("date"),
                "event_at": None,
                "published_at": (t.get("study_first_post_date") or {}).get("date"),
                "first_seen_at": t.get("first_seen_at"),
                "observed_lag_days": lag_days(t.get("first_seen_at"),
                                              (t.get("study_first_post_date") or {}).get("date")),
                "time_basis": time_basis((t.get("study_first_post_date") or {}).get("date"),
                                         t.get("first_seen_at"))[0],
                "timestamp_precision": "DAY",
                "extraction_version": EXTRACTION_VERSION})
            counters["reference_claims"]["mapped" if obj_id else "unmapped"] += 1

    # ------------------------------------------------------------------
    # Relation B: company -> publication (affiliation), institution -> publication
    # ------------------------------------------------------------------
    company_pubs: dict[str, set] = defaultdict(set)
    pub_institutions: dict[str, set] = defaultdict(set)

    for m in mentions:
        if m["record_kind"] != "publication":
            continue
        if not m.get("company_key"):
            continue
        p = pubs.get(m["record_id"])
        if not p:
            continue
        # Europe PMC indexes patent records too (source_db == 'PAT'); a patent is not a
        # scientific publication, so it cannot carry a publication-affiliation claim.
        if p.get("source_db") == "PAT":
            rejects.append({"reject_id": "rej:" + sha256_text(m["mention_id"])[:16],
                            "source": m["source"], "record_kind": "patent_record",
                            "record_id": m["record_id"], "role": "author_affiliation",
                            "raw_string": m["raw_string"], "company_key": m.get("company_key"),
                            "mapping_status": "REJECTED",
                            "rule": "not_a_publication_record",
                            "reason": "Europe PMC returned a PATENT record (source=PAT) for an "
                                      "affiliation query; excluded from publication relations",
                            "evidence_id": m["evidence_id"],
                            "kept_for": "source-composition measurement"})
            counters["pub_company_rejects"]["PATENT_RECORD_EXCLUDED"] += 1
            continue
        if m["mapping_status"] not in ("ORG_TEXT", "ORG_EMAIL"):
            rejects.append({"reject_id": "rej:" + sha256_text(m["mention_id"])[:16],
                            "source": m["source"], "record_kind": "publication",
                            "record_id": m["record_id"], "role": "author_affiliation",
                            "raw_string": m["raw_string"], "company_key": m.get("company_key"),
                            "mapping_status": m["mapping_status"], "rule": m["rule"],
                            "reason": m["reason"], "evidence_id": m["evidence_id"],
                            "kept_for": "name-collision measurement"})
            counters["pub_company_rejects"][f"{m.get('company_key')}:{m['rule']}"] += 1
            continue
        eid = add_evidence(m["evidence_id"], "europepmc", p.get("source_url"),
                           m["record_id"], m["evidence_id"].replace("ev:", ""),
                           f"authorList.author[].authorAffiliationDetailsList.affiliation = "
                           f"{m['raw_string'][:300]!r}",
                           p.get("first_index_date") or p.get("first_publication_date"),
                           p.get("date_of_revision"),
                           p.get("first_seen_at"),
                           classify_date_precision(p.get("first_publication_date")),
                           "PRIMARY_TEXT" if m["mapping_status"] == "ORG_TEXT" else "PRIMARY_TEXT")
        subject = f"ent:company:{m['company_key']}"
        cid = claim_id("AFFILIATED_WITH", subject, f"ent:publication:{p['pub_key']}",
                       p["pub_key"], "author_affiliation")
        claims.append({
            "relation_id": cid, "subject_id": subject, "predicate": "AFFILIATED_WITH",
            "object_id": f"ent:publication:{p['pub_key']}",
            "relation_role": "author_affiliation", "statement_status": "SOURCE_STATES_IT",
            "mapping_status": m["mapping_status"],
            "claim_status": "VERIFIED_BY_SOURCE" if m["mapping_status"] == "ORG_EMAIL"
                            else "CANDIDATE",
            "confidence": m["confidence"], "mapping_method": m["rule"],
            "source_record_id": p["pub_key"], "evidence_id": eid,
            "relation_temporal_type": "POINT", "valid_from": p.get("first_publication_date"),
            "valid_to": None, "declared_at": p.get("first_index_date") or p.get("first_publication_date"),
            "event_at": p.get("first_publication_date"),
            "published_at": p.get("first_index_date") or p.get("first_publication_date"),
            "first_seen_at": p.get("first_seen_at"),
            "observed_lag_days": lag_days(p.get("first_seen_at"),
                                          p.get("first_index_date") or p.get("first_publication_date")),
            "time_basis": time_basis(p.get("first_index_date") or p.get("first_publication_date"),
                                     p.get("first_seen_at"))[0],
            "timestamp_precision": classify_date_precision(p.get("first_publication_date")),
            "interpretation_limit": "author affiliation at publication; not employment history, "
                                    "not knowledge transfer",
            "extraction_version": EXTRACTION_VERSION})
        company_pubs[subject].add(p["pub_key"])
        counters["pub_company_claims"][f"{m['mapping_status']}"] += 1

    for ic in institutions:
        if ic["family"] != "publication_affiliation":
            continue
        eid_inst = inst_by_candidate.get(ic["candidate_id"])
        if not eid_inst:
            counters["pub_institution_rejects"]["UNMAPPED"] += 1
            continue
        for pub_key in ic["example_records"]:
            p = pubs.get(pub_key)
            if not p:
                continue
            ev = add_evidence(p["evidence_id"], "europepmc", p.get("source_url"), pub_key,
                              p["evidence_id"].replace("ev:", ""),
                              f"affiliation string ({ic['raw_string'][:200]!r}) resolved to "
                              f"{ic['ror'].get('ror_id')}",
                              p.get("first_index_date") or p.get("first_publication_date"),
                              p.get("date_of_revision"), p.get("first_seen_at"),
                              classify_date_precision(p.get("first_publication_date")),
                              "PRIMARY_TEXT")
            cid = claim_id("AFFILIATED_WITH", eid_inst, f"ent:publication:{pub_key}",
                           pub_key, "author_affiliation")
            claims.append({
                "relation_id": cid, "subject_id": eid_inst, "predicate": "AFFILIATED_WITH",
                "object_id": f"ent:publication:{pub_key}",
                "relation_role": "author_affiliation", "statement_status": "SOURCE_STATES_IT",
                "mapping_status": ic["ror"]["status"],
                "claim_status": "VERIFIED_BY_SOURCE" if ic["ror"]["status"] == "EXACT" else "CANDIDATE",
                "confidence": ic["ror"]["confidence"], "mapping_method": "ror_" + str(ic["ror"].get("matched_field")),
                "source_record_id": pub_key, "evidence_id": ev,
                "relation_temporal_type": "POINT", "valid_from": p.get("first_publication_date"),
                "valid_to": None,
                "declared_at": p.get("first_index_date") or p.get("first_publication_date"),
                "event_at": p.get("first_publication_date"),
                "published_at": p.get("first_index_date") or p.get("first_publication_date"),
                "first_seen_at": p.get("first_seen_at"),
                "observed_lag_days": lag_days(p.get("first_seen_at"),
                                              p.get("first_index_date") or p.get("first_publication_date")),
                "time_basis": time_basis(p.get("first_index_date") or p.get("first_publication_date"),
                                         p.get("first_seen_at"))[0],
                "timestamp_precision": classify_date_precision(p.get("first_publication_date")),
                "extraction_version": EXTRACTION_VERSION})
            pub_institutions[pub_key].add(eid_inst)
            counters["pub_institution_claims"][ic["ror"]["status"]] += 1

    # ------------------------------------------------------------------
    # Relation B': company <-> institution co-affiliation on one publication
    # ------------------------------------------------------------------
    for ck_eid, plist in company_pubs.items():
        for pub_key in plist:
            for eid_inst in pub_institutions.get(pub_key, ()):
                p = pubs[pub_key]
                cid = claim_id("CO_AFFILIATED_ON", ck_eid, eid_inst, pub_key, "co_affiliation")
                claims.append({
                    "relation_id": cid, "subject_id": ck_eid,
                    "predicate": "CO_AFFILIATED_ON", "object_id": eid_inst,
                    "relation_role": "co_affiliation",
                    "statement_status": "SOURCE_IMPLIES_IT",
                    "mapping_status": "DERIVED_FROM_EXACT", "claim_status": "CANDIDATE",
                    "confidence": 0.7, "mapping_method": "same_publication_two_affiliations",
                    "source_record_id": pub_key,
                    "evidence_id": f"{p['evidence_id']}:{pub_key}",
                    "relation_temporal_type": "POINT",
                    "valid_from": p.get("first_publication_date"), "valid_to": None,
                    "declared_at": p.get("first_index_date") or p.get("first_publication_date"),
                    "event_at": p.get("first_publication_date"),
                    "published_at": p.get("first_index_date") or p.get("first_publication_date"),
                    "first_seen_at": p.get("first_seen_at"),
                    "observed_lag_days": lag_days(p.get("first_seen_at"),
                                                  p.get("first_index_date") or p.get("first_publication_date")),
                    "time_basis": time_basis(p.get("first_index_date") or p.get("first_publication_date"),
                                             p.get("first_seen_at"))[0],
                    "timestamp_precision": classify_date_precision(p.get("first_publication_date")),
                    "interpretation_limit": "co-authorship is not collaboration, not knowledge "
                                            "transfer, and has no direction",
                    "extraction_version": EXTRACTION_VERSION})
                counters["co_affiliation_claims"]["derived"] += 1

    # ------------------------------------------------------------------
    # Relation B'': publication funded by a company (self-declared acknowledgement)
    # ------------------------------------------------------------------
    register = load_register()
    nc_strings = not_company_strings(register)
    for pk, p in pubs.items():
        if p.get("source_db") == "PAT":
            continue
        for g in p.get("grants") or []:
            agency = (g.get("agency") or "").strip()
            if not agency:
                continue
            m = map_string(agency, "structured_org",
                           p.get("first_publication_date"), register, nc_strings)
            if not m.get("company_key") or m["mapping_status"] not in ACCEPTED_COMPANY:
                continue
            ev = add_evidence(p["evidence_id"], "europepmc", p.get("source_url"), pk,
                              p["evidence_id"].replace("ev:", ""),
                              f"grantsList.grant[].agency = {agency!r}",
                              p.get("first_index_date") or p.get("first_publication_date"),
                              p.get("date_of_revision"), p.get("first_seen_at"),
                              classify_date_precision(p.get("first_publication_date")),
                              "PRIMARY_TEXT")
            cid = claim_id("FUNDED_BY", f"ent:company:{m['company_key']}",
                           f"ent:publication:{pk}", pk, "grant_funder")
            claims.append({
                "relation_id": cid, "subject_id": f"ent:company:{m['company_key']}",
                "predicate": "FUNDED_BY", "object_id": f"ent:publication:{pk}",
                "relation_role": "grant_funder", "statement_status": "SOURCE_STATES_IT",
                "mapping_status": m["mapping_status"],
                "claim_status": "CANDIDATE", "confidence": min(m["confidence"], 0.8),
                "mapping_method": m["rule"],
                "source_record_id": pk, "evidence_id": ev,
                "relation_temporal_type": "POINT",
                "valid_from": p.get("first_publication_date"), "valid_to": None,
                "declared_at": p.get("first_index_date") or p.get("first_publication_date"),
                "event_at": p.get("first_publication_date"),
                "published_at": p.get("first_index_date") or p.get("first_publication_date"),
                "first_seen_at": p.get("first_seen_at"),
                "observed_lag_days": lag_days(p.get("first_seen_at"),
                                              p.get("first_index_date") or p.get("first_publication_date")),
                "time_basis": time_basis(p.get("first_index_date") or p.get("first_publication_date"),
                                         p.get("first_seen_at"))[0],
                "timestamp_precision": classify_date_precision(p.get("first_publication_date")),
                "funder_string": agency,
                "interpretation_limit": "a funding acknowledgement is a declared support "
                                        "relation; it is not evidence of collaboration or influence",
                "extraction_version": EXTRACTION_VERSION})
            counters["funder_claims"][f"{m['company_key']}:{m['mapping_status']}"] += 1

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    ent_rows = sorted(entities.values(), key=lambda e: e["entity_id"])
    claim_rows = sorted(claims, key=lambda c: c["relation_id"])
    ev_rows = sorted(evidence.values(), key=lambda e: e["evidence_id"])
    reject_rows = sorted(rejects, key=lambda r: r["reject_id"])

    # de-duplicate claims on relation_id (same statement found via two queries)
    dedup: dict[str, dict] = {}
    for c in claim_rows:
        dedup.setdefault(c["relation_id"], c)
    claim_rows = sorted(dedup.values(), key=lambda c: c["relation_id"])

    # STRICT standard (adopted from the independent temporal audit): a claim counts as a genuine
    # observed-as-of record ONLY if its first_seen_at was recorded by the MedRadar Live Observatory
    # ledger. This study's collection wall clock is not that — it is a backfill fetch of an
    # already-published record. The lenient label (published within 7 days of our own fetch) is kept
    # in time_basis for transparency but never used for a point-in-time claim.
    for c2 in claim_rows:
        near = c2.get("time_basis") == "ACTUAL_OBSERVATION"
        c2["near_realtime_this_study"] = bool(near)
        c2["observation_system"] = "THIS_STUDY_COLLECTION" if near else "NONE"
        # The ontology's ACTUAL_OBSERVATION is reserved for a record whose appearance the
        # observing system actually recorded. A backfill fetch that happens to fall within 7 days
        # of the record's own publication date is NOT that (independent audit, TEMPORAL_PROVENANCE
        # §4.3): it is downgraded to HISTORICAL_PROXY and kept visible only as a flag.
        if near:
            c2["time_basis"] = "HISTORICAL_PROXY"
        c2["strict_observed_asof"] = False

    write_jsonl(DATA_DIR / "entities.jsonl", ent_rows)
    write_jsonl(DATA_DIR / "evidence.jsonl", ev_rows)
    write_jsonl(DATA_DIR / "claims.jsonl", claim_rows)
    write_jsonl(DATA_DIR / "claim_rejects.jsonl", reject_rows)

    by_pred = Counter(c["predicate"] for c in claim_rows)
    by_status = Counter(c["claim_status"] for c in claim_rows)
    by_basis = Counter(c["time_basis"] for c in claim_rows)
    by_subject_type = Counter(
        entities.get(c["subject_id"], {}).get("entity_type", "MISSING") for c in claim_rows)
    by_company = Counter(c["subject_id"] for c in claim_rows if c["subject_id"].startswith("ent:company:"))

    summary = {
        "generated_at": utcnow_iso(),
        "extraction_version": EXTRACTION_VERSION,
        "counts": {"entities": len(ent_rows), "evidence": len(ev_rows),
                   "claims": len(claim_rows), "rejects": len(reject_rows)},
        "claims_by_predicate": dict(by_pred),
        "claims_by_status": dict(by_status),
        "claims_by_time_basis": dict(by_basis),
        "claims_this_study_near_realtime": sum(
            1 for c2 in claim_rows if c2.get("time_basis") == "ACTUAL_OBSERVATION"),
        "claims_strict_observed_asof": sum(1 for c2 in claim_rows if c2["strict_observed_asof"]),
        "claims_by_subject_type": dict(by_subject_type),
        "claims_by_company": dict(by_company),
        "claim_rows_per_company_excluding_institution_side": {
            k: v for k, v in by_company.items()},
        "counters": {k: dict(v) for k, v in counters.items()},
        "human_confirmed_rows": sum(1 for c in claim_rows if c["claim_status"] == "HUMAN_CONFIRMED"),
        "note": "no claim is HUMAN_CONFIRMED; machine labels only",
    }
    write_json(ARTIFACT_DIR / "claims_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("counts", "claims_by_predicate",
                                              "claims_by_status", "claims_by_time_basis",
                                              "claims_by_company")},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
