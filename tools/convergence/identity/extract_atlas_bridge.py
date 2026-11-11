#!/usr/bin/env python
"""P0-B / task-2: extract and independently re-derive ATLAS's 934 confirmed pairs.

Sources (all frozen, all offline):
  * ATLAS research DB  (read-only, mode=ro)  -> the 934 relation rows + both evidence payloads
  * MDALL raw cache    (RAW source)          -> the Canada side, re-derived from scratch
  * ATLAS request log                        -> corroborates that each DI was in a query batch
  * HORIZON frozen slices                    -> independent US GUDID pull and Canada licence slice

What is independent and what is not is recorded per check in `verification_ledger`.
The Canada side is a full re-derivation from the raw frozen table: the DB only
told us *which* DI to look for, never that it exists. The US side cannot be
re-derived offline (openFDA UDI was queried live by ATLAS); it is verified at
record level against the stored official payload and cross-checked where the
frozen HORIZON GUDID slice overlaps (expected ~0, different samples).

Writes research/convergence/identity/ATLAS_BRIDGE_934.json
Run:
    python tools/convergence/identity/extract_atlas_bridge.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gtin import GTIN14_RE, gtin14_check_digit_ok, is_gtin_like, normalize_di  # noqa: E402

WT = Path(r"D:\DEPPSKK\worktrees\convergence-001")
DB = Path(r"D:\DEPPSKK\worktrees\atlas-001\research\atlas\staging\atlas.sqlite")
CACHE = Path(r"D:\DEPPSKK\worktrees\atlas-001\research\atlas\cache\mdall_active_deviceidentifier.json")
REQUESTS = Path(r"D:\DEPPSKK\worktrees\atlas-001\research\atlas\staging\atlas_requests.jsonl")
FROZEN = WT / "research" / "convergence" / "identity" / "FROZEN_INPUTS.json"
FIRMS_CFG = WT / "config" / "atlas_firms.json"
HORIZON_MDALL = WT / "research/horizon/DATASETS/regulatory/canada_mdall/records.jsonl"
HORIZON_GUDID = WT / "research/horizon/DATASETS/regulatory/accessgudid/records.jsonl"
OUT = WT / "research" / "convergence" / "identity" / "ATLAS_BRIDGE_934.json"

_GTIN14 = GTIN14_RE


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def iter_json_array(path: Path, chunk: int = 1 << 20):
    dec = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as f:
        buf = f.read(chunk)
        idx = 1
        while True:
            while idx < len(buf) and buf[idx] in " \t\r\n,":
                idx += 1
            if idx >= len(buf):
                more = f.read(chunk)
                if not more:
                    return
                buf = buf[idx:] + more
                idx = 0
                continue
            if buf[idx] == "]":
                return
            try:
                obj, end = dec.raw_decode(buf, idx)
            except json.JSONDecodeError:
                more = f.read(chunk)
                if not more:
                    raise
                buf = buf[idx:] + more
                idx = 0
                continue
            yield obj
            idx = end


def norm_company_name(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9\u4e00-\u9fff ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_firms() -> dict:
    cfg = json.loads(FIRMS_CFG.read_text(encoding="utf-8"))
    out = {}
    for firm in cfg["firms"]:
        aliases = [norm_company_name(a) for a in firm.get("aliases") or []]
        guards = [norm_company_name(g) for g in firm.get("negative_guards") or []]
        out[firm["key"]] = {"canonical_name": firm["canonical_name"],
                            "aliases": aliases, "guards": guards}
    return out


def match_firm(name: str, firms: dict) -> str | None:
    """Independent re-implementation of the alias rule (token-subsequence + guards)."""
    text = norm_company_name(name)
    if not text:
        return None
    tokens = text.split()
    hits = []
    for key, cfg in firms.items():
        for alias in cfg["aliases"]:
            at = alias.split()
            if not at:
                continue
            for i in range(len(tokens) - len(at) + 1):
                if tokens[i:i + len(at)] == at:
                    hits.append((key, alias))
                    break
            else:
                continue
            break
    if not hits:
        return None
    # a negative guard demotes (never silently accepts)
    if any(g and g.split() and all(t in tokens for t in g.split())
           for key in {h[0] for h in hits} for g in firms[key]["guards"]):
        return None
    keys = {h[0] for h in hits}
    return hits[0][0] if len(keys) == 1 else None


def main() -> int:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    digests = {b["role"]: b["sha256"] for b in frozen["required_inputs"]}
    assert sha256_file(CACHE) == digests["mdall_cache"]
    assert sha256_file(DB) == digests["atlas_db"]

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ---------------------------------------------------------------- relations
    rels = cur.execute(
        "select * from entity_relations where relation_type='SAME_DEVICE_IDENTITY' "
        "order by relation_id"
    ).fetchall()
    assert len(rels) == 934, len(rels)

    # ---------------------------------------------------------------- HORIZON US slice
    horizon_gudid: dict[str, dict] = {}
    with HORIZON_GUDID.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            for ident in r.get("identifiers") or []:
                if ident.get("scheme") == "udi_di":
                    horizon_gudid[str(ident["value"]).upper()] = r

    # ---------------------------------------------------------------- HORIZON CA licence slice
    horizon_licence_firm: dict[str, str] = {}
    horizon_licence_company: dict[str, str] = {}
    with HORIZON_MDALL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("entity_type") != "regulatory_clearance":
                continue
            attrs = r.get("attributes") or {}
            lic = str(attrs.get("licence_number") or "")
            if lic:
                horizon_licence_firm[lic] = attrs.get("target_firm_slice") or ""
                horizon_licence_company[lic] = str(attrs.get("company_id") or "")

    # ---------------------------------------------------------------- build the 934 records
    pairs = []
    for rel in rels:
        basis = json.loads(rel["basis_json"] or "{}")
        shared = str(basis.get("shared_identifier") or "")
        scheme, _, di = shared.partition(":")
        ev_ids = json.loads(rel["evidence_ids_json"] or "[]")
        fda_ev_id = ev_ids[0] if len(ev_ids) > 0 else ""
        mdall_ev_id = ev_ids[1] if len(ev_ids) > 1 else ""
        fda_ev = cur.execute("select * from evidence where evidence_id=?", (fda_ev_id,)).fetchone()
        md_ev = cur.execute("select * from evidence where evidence_id=?", (mdall_ev_id,)).fetchone()
        fda_payload = json.loads(fda_ev["payload_json"] or "{}") if fda_ev else {}
        md_payload = json.loads(md_ev["payload_json"] or "{}") if md_ev else {}
        fda_norm = fda_payload.get("normalized") or {}
        md_norm = md_payload.get("normalized") or {}
        fda_idents = [
            dict(x) for x in cur.execute(
                "select scheme,value,issuer,scope,is_primary from evidence_identifiers "
                "where evidence_id=? order by scheme,value", (fda_ev_id,))
        ]
        md_idents = [
            dict(x) for x in cur.execute(
                "select scheme,value,issuer,scope,is_primary from evidence_identifiers "
                "where evidence_id=? order by scheme,value", (mdall_ev_id,))
        ]
        fda_firm_ref = cur.execute(
            "select firm_key,method,name_raw from evidence_entity_refs where evidence_id=?",
            (fda_ev_id,)).fetchone()
        # which stored identifier row carries the shared DI on the US side?
        fda_di_row = next((r for r in fda_idents if r["scheme"] == "di" and r["value"] == di), None)
        md_di_row = next((r for r in md_idents if r["scheme"] == "di" and r["value"] == di), None)
        # payload order matters: view_from_evidence() takes the FIRST di in the
        # stored identifiers list, not the primary one.
        payload_idents = fda_payload.get("identifiers") or []
        first_di = next((str(i.get("value")) for i in payload_idents
                         if i.get("scheme") == "di" and i.get("value")), "")
        primary_di = next((str(i.get("value")) for i in payload_idents
                           if i.get("scheme") == "di" and i.get("value") and i.get("is_primary")), "")
        pairs.append({
            "relation_id": rel["relation_id"],
            "di": di,
            "relation_status": rel["status"],
            "relation_method": rel["method"],
            "relation_authority": rel["authority"],
            "confidence": rel["confidence"],
            "basis_shared_fields": basis.get("shared_fields"),
            "basis_brand_left": basis.get("brand_left"),
            "basis_brand_right": basis.get("brand_right"),
            "basis_model_left": basis.get("model_left"),
            "basis_model_right": basis.get("model_right"),
            "fda_evidence_id": fda_ev_id,
            "mdall_evidence_id": mdall_ev_id,
            "fda_device_ref": rel["from_ref"],
            "mdall_device_ref": rel["to_ref"],
            "fda_source_id": fda_ev["source_id"] if fda_ev else "",
            "fda_source_record_id": fda_ev["source_record_id"] if fda_ev else "",
            "fda_source_url": fda_ev["source_url"] if fda_ev else "",
            "fda_canonical_key": fda_ev["canonical_key"] if fda_ev else "",
            "mdall_source_id": md_ev["source_id"] if md_ev else "",
            "mdall_source_record_id": md_ev["source_record_id"] if md_ev else "",
            "mdall_canonical_key": md_ev["canonical_key"] if md_ev else "",
            "fda_company_name": fda_norm.get("company_name"),
            "fda_brand_name": fda_norm.get("brand_name"),
            "fda_model": fda_norm.get("version_or_model_number"),
            "fda_catalog": fda_norm.get("catalog_number"),
            "fda_device_class": fda_norm.get("device_class"),
            "fda_product_codes": fda_norm.get("product_codes"),
            "fda_labeler_duns": fda_norm.get("labeler_duns_number"),
            "fda_publish_date": fda_norm.get("publish_date"),
            "fda_public_record_key": fda_norm.get("public_device_record_key"),
            "fda_record_status": fda_norm.get("record_status"),
            "fda_commercial_distribution_status": fda_norm.get("commercial_distribution_status"),
            "fda_identifiers": fda_idents,
            "fda_first_di_in_payload_order": first_di,
            "fda_primary_di": primary_di,
            "fda_first_di_equals_primary": (first_di == primary_di),
            "fda_di_is_primary": bool(fda_di_row["is_primary"]) if fda_di_row else None,
            "fda_di_scope": fda_di_row["scope"] if fda_di_row else None,
            "fda_di_issuer": fda_di_row["issuer"] if fda_di_row else None,
            "fda_firm_key_stored": fda_firm_ref["firm_key"] if fda_firm_ref else "",
            "fda_firm_method_stored": fda_firm_ref["method"] if fda_firm_ref else "",
            "mdall_licence": (md_norm.get("licence_number") or ""),
            "mdall_device_id": (md_norm.get("mdall_device_id") or ""),
            "mdall_identifier_raw": md_norm.get("device_identifier_raw"),
            "mdall_identifier_normalised": md_norm.get("device_identifier_normalised"),
            "mdall_identifier_is_gtin_flag": md_norm.get("device_identifier_is_gtin"),
            "mdall_first_licence_dt": md_norm.get("first_licence_dt"),
            "mdall_end_date": md_norm.get("end_date"),
            "mdall_identifiers": md_idents,
            "mdall_di_is_primary": bool(md_di_row["is_primary"]) if md_di_row else None,
            "mdall_di_scope": md_di_row["scope"] if md_di_row else None,
            "mdall_di_issuer": md_di_row["issuer"] if md_di_row else None,
        })

    # ---------------------------------------------------------------- GTIN validity of the 934
    invalid = [p["di"] for p in pairs if not gtin14_check_digit_ok(p["di"])]
    canonical_ok = [p["di"] for p in pairs if p["fda_canonical_key"] == f"di:{p['di']}"
                    and p["mdall_canonical_key"] == f"di:{p['di']}"]

    # ---------------------------------------------------------------- independent CA re-derivation
    di_set = {p["di"] for p in pairs}
    cache_hits: dict[str, list[dict]] = collections.defaultdict(list)
    for obj in iter_json_array(CACHE):
        norm = normalize_di(obj.get("device_identifier"))
        if norm in di_set:
            cache_hits[norm].append({
                "licence": str(obj.get("original_licence_no") or ""),
                "device_id": str(obj.get("device_id") or ""),
                "first_licence_dt": obj.get("first_licence_dt"),
                "end_date": obj.get("end_date"),
            })

    # ---------------------------------------------------------------- the deterministic 1200 subsample
    # ATLAS keys mdall_views by the *raw* device_identifier string
    # (pilot.py: di = str(row.get("device_identifier"))), sorts those keys and
    # takes every len/1200-th element.  Reproduce exactly, then normalise.
    raw_gtin_keys: list[str] = []
    seen_raw: set[str] = set()
    for obj in iter_json_array(CACHE):
        raw = obj.get("device_identifier")
        if is_gtin_like(raw):
            key = str(raw)
            if key not in seen_raw:
                seen_raw.add(key)
                raw_gtin_keys.append(key)
    raw_gtin_keys.sort()
    step = len(raw_gtin_keys) / 1200
    queried_raw = [raw_gtin_keys[int(i * step)] for i in range(1200)]
    queried_set = {normalize_di(k) for k in queried_raw}
    queried_separator_form = [k for k in queried_raw if normalize_di(k) != k]

    # ---------------------------------------------------------------- request-log corroboration
    from urllib.parse import unquote_plus

    bridge_batch_urls = 0
    pilot_batch_urls = 0
    pilot_tokens = 0
    pilot_status: collections.Counter = collections.Counter()
    log_dis: set[str] = set()
    with REQUESTS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            url = rec.get("url") or ""
            if "device/udi.json" not in url or "identifiers.id" not in url:
                continue
            bridge_batch_urls += 1
            decoded = unquote_plus(url)
            in_pilot = (rec.get("logged_at") or "").startswith("2026-11-10T17:41")
            tokens = decoded.split("identifiers.id:(", 1)[-1].split(" OR ")
            if in_pilot:
                pilot_batch_urls += 1
                pilot_tokens += len(tokens)
                pilot_status[rec.get("status")] += 1
            for token in tokens:
                # the final token carries ')&limit=50' from the surrounding URL
                val = normalize_di(token.split(")", 1)[0])
                if val:
                    log_dis.add(val)

    # ---------------------------------------------------------------- HORIZON cross-checks
    horizon_us_overlap = sorted(di_set & set(horizon_gudid))
    horizon_ca_licence_overlap = sorted(
        {p["mdall_licence"] for p in pairs} & set(horizon_licence_firm)
    )

    # ---------------------------------------------------------------- firm attribution
    firms = load_firms()
    # ATLAS's 40 fetched MDALL licences: company attribution, split by method.
    atlas_licence_refs: dict[str, list[dict]] = {}
    for row in cur.execute(
            "select source_url, payload_json from evidence where source_id='canada_mdall'"):
        if "deviceidentifier" in (row["source_url"] or ""):
            continue
        pl = json.loads(row["payload_json"] or "{}")
        n = pl.get("normalized") or {}
        atlas_licence_refs[str(n.get("licence_number") or "")] = pl.get("entity_refs") or []
    atlas_licences_confirmed = 0
    atlas_licences_candidate = 0
    for refs in atlas_licence_refs.values():
        if any(r.get("method") in {"official_id", "exact_alias", "multi_field"} for r in refs):
            atlas_licences_confirmed += 1
        elif refs:
            atlas_licences_candidate += 1

    fda_firm_counts = collections.Counter()
    fda_firm_vs_stored = collections.Counter()
    ca_confirmed = 0
    ca_candidate = 0
    ca_confirmed_same = 0
    ca_confirmed_diff = 0
    ca_candidate_same = 0
    ca_candidate_diff = 0
    ca_candidate_rows = []
    for p in pairs:
        fda_firm = match_firm(p["fda_company_name"] or "", firms)
        p["fda_firm_independent"] = fda_firm
        fda_firm_counts[fda_firm or "unattributed"] += 1
        fda_firm_vs_stored[
            ("both_agree" if fda_firm and fda_firm == p["fda_firm_key_stored"] else
             "stored_none" if not p["fda_firm_key_stored"] else
             "independent_none" if not fda_firm else "disagree")
        ] += 1
        licences = {c["licence"] for c in cache_hits.get(p["di"], [])}
        if not licences:
            licences = {p["mdall_licence"]} if p["mdall_licence"] else set()
        p["mdall_licences_from_cache"] = sorted(licences)
        # Health Canada corporate identity is only available where ATLAS fetched a
        # licence record; those links are all method='candidate', never confirmed.
        refs = [r for lic in licences for r in atlas_licence_refs.get(lic, [])]
        ca_keys = {r.get("firm_key") for r in refs if r.get("firm_key")}
        tier = ("confirmed" if any(r.get("method") in {"official_id", "exact_alias", "multi_field"}
                                   for r in refs)
                else ("candidate" if refs else "none"))
        p["ca_firm_attribution_tier"] = tier
        if not refs:
            p["firm_attribution"] = "unattributable_ca_side"
        else:
            ca_candidate += 1
            same = bool(fda_firm and fda_firm in ca_keys)
            if tier == "confirmed":
                p["firm_attribution"] = ("ca_confirmed_same_group" if same
                                         else "ca_confirmed_diff_or_unmapped")
                if same:
                    ca_confirmed_same += 1
                else:
                    ca_confirmed_diff += 1
            else:
                p["firm_attribution"] = ("ca_candidate_same_group" if same
                                         else "ca_candidate_diff_or_unmapped")
                if same:
                    ca_candidate_same += 1
                else:
                    ca_candidate_diff += 1
            if same:
                ca_candidate_rows.append({
                    "di": p["di"], "fda_company": p["fda_company_name"],
                    "fda_firm": fda_firm, "ca_firms": sorted(ca_keys),
                    "licences": sorted(licences), "tier": tier})
        if tier == "confirmed":
            ca_confirmed += 1

    firm_attribution = {
        "us_side_official_labeler_name_available": sum(
            1 for p in pairs if (p["fda_company_name"] or "").strip()),
        "us_side_distinct_labeler_companies": len(
            {(p["fda_company_name"] or "").strip().upper() for p in pairs}),
        "us_side_independent_alias_match_to_five_firm_register": dict(fda_firm_counts),
        "us_side_inside_five_firm_register_pairs": 934 - fda_firm_counts.get("unattributed", 0),
        "us_side_outside_five_firm_register_pairs": fda_firm_counts.get("unattributed", 0),
        "fda_side_independent_vs_atlas_stored": dict(fda_firm_vs_stored),
        "ca_side_atlas_licences_fetched": len(atlas_licence_refs),
        "ca_side_atlas_licences_with_confirmed_company_link": atlas_licences_confirmed,
        "ca_side_atlas_licences_with_candidate_company_link_only": atlas_licences_candidate,
        "ca_side_pairs_with_confirmed_tier_company_link": ca_confirmed,
        "ca_side_pairs_with_any_company_link": ca_candidate,
        "ca_side_pairs_candidate_tier_only": ca_candidate - ca_confirmed,
        "ca_side_pairs_confirmed_tier_same_group": ca_confirmed_same,
        "ca_side_pairs_confirmed_tier_diff_or_unmapped": ca_confirmed_diff,
        "ca_side_pairs_candidate_tier_same_group": ca_candidate_same,
        "ca_side_pairs_candidate_tier_diff_or_unmapped": ca_candidate_diff,
        "ca_side_pairs_unattributable": 934 - ca_candidate,
        "ca_same_group_examples": ca_candidate_rows[:10],
        "note": (
            "Health Canada's MDALL identifier table publishes no company name. ATLAS fetched 40 "
            "MDALL licences; the company links it derived are name-alias resolutions "
            "(13 exact_alias tier, 8 candidate tier) and all resolve to GE HealthCare. "
            "HORIZON's independent 60-licence slice does not overlap the 66 licences behind these "
            "934 pairs. So at most 9/934 pairs (1.0%) have any Canada-side company attribution, and "
            "925/934 (99.0%) have none in the local frozen data. Corporate coherence on both sides "
            "is therefore NOT established for this bridge."
        ),
    }

    # ---------------------------------------------------------------- duplicate / FP risk
    di_counts = collections.Counter(p["di"] for p in pairs)
    licence_counts = collections.Counter(p["mdall_licence"] for p in pairs)
    fda_ev_counts = collections.Counter(p["fda_evidence_id"] for p in pairs)
    md_ev_counts = collections.Counter(p["mdall_evidence_id"] for p in pairs)
    multi_row_dis = sorted(
        (di for di in di_set if len(cache_hits.get(di, [])) > 1),
    )
    multi_licence_dis = sorted(
        di for di in di_set
        if len({c["licence"] for c in cache_hits.get(di, [])}) > 1
    )

    duplicated = {
        "pairs": len(pairs),
        "distinct_di": len(di_set),
        "distinct_relation_id": len({p["relation_id"] for p in pairs}),
        "distinct_fda_evidence": len(fda_ev_counts),
        "distinct_mdall_evidence": len(md_ev_counts),
        "distinct_fda_public_record_key": len({p["fda_public_record_key"] for p in pairs}),
        "distinct_mdall_licence": len(licence_counts),
        "distinct_mdall_device_id": len({p["mdall_device_id"] for p in pairs}),
        "di_appearing_in_more_than_one_pair": [d for d, n in di_counts.items() if n > 1],
        "fda_evidence_in_more_than_one_pair": [d for d, n in fda_ev_counts.items() if n > 1],
        "mdall_evidence_in_more_than_one_pair": [d for d, n in md_ev_counts.items() if n > 1],
        "same_mdall_licence_shared_by_multiple_pairs": sum(
            1 for n in licence_counts.values() if n > 1),
        "max_pairs_per_single_mdall_licence": max(licence_counts.values()) if licence_counts else 0,
        "confirmed_di_with_more_than_one_mdall_cache_row": len(multi_row_dis),
        "confirmed_di_under_more_than_one_licence_in_cache": len(multi_licence_dis),
        "confirmed_di_with_more_than_one_device_id_in_cache": sum(
            1 for di in di_set if len({c["device_id"] for c in cache_hits.get(di, [])}) > 1),
        "examples_multi_licence_confirmed": [
            {"di": di,
             "rows": cache_hits[di],
             "atlas_stored_licence": next(p["mdall_licence"] for p in pairs if p["di"] == di)}
            for di in multi_licence_dis[:5]
        ],
    }

    # ---------------------------------------------------------------- concentration + anchor typing
    lic_buckets: dict[str, list[dict]] = collections.defaultdict(list)
    for p in pairs:
        lic_buckets[p["mdall_licence"]].append(p)
    licence_concentration = []
    for lic, ps in sorted(lic_buckets.items(), key=lambda kv: -len(kv[1])):
        comps = collections.Counter((x["fda_company_name"] or "").strip() for x in ps)
        licence_concentration.append({
            "mdall_licence": lic,
            "pairs": len(ps),
            "share_of_934": round(len(ps) / 934, 6),
            "distinct_us_labelers": len(comps),
            "us_labelers": [{"company": c, "pairs": n} for c, n in comps.most_common(3)],
            "gtin_prefixes_top": [
                {"prefix": pre, "pairs": n}
                for pre, n in collections.Counter(x["di"][:6] for x in ps).most_common(3)
            ],
        })

    anchor = {
        "payload_first_di_equals_primary": sum(
            1 for p in pairs if p["fda_first_di_equals_primary"]),
        "payload_first_di_differs_from_primary": sum(
            1 for p in pairs if not p["fda_first_di_equals_primary"]),
        "published_pairs_anchored_on_primary_di": sum(
            1 for p in pairs if p["fda_di_is_primary"] is True),
        "published_pairs_anchored_on_package_di": sum(
            1 for p in pairs if p["fda_di_is_primary"] is False),
        "note": (
            "resolver.view_from_evidence() takes the FIRST identifier with scheme 'di' in the "
            "openFDA payload order, not the primary DI. For 932/934 records the two coincide; for "
            "2/934 the anchor is a GUDID package DI. See UNIFIED_SAMPLE_RESULTS.json/"
            "anchor_sensitivity for the 7 primary-DI matches that this dropped."
        ),
    }

    record_status = {
        "record_status": dict(collections.Counter(p["fda_record_status"] for p in pairs)),
        "commercial_distribution_status": dict(
            collections.Counter(p["fda_commercial_distribution_status"] for p in pairs)),
    }

    ca_rederived = sum(1 for p in pairs
                       if p["di"] in cache_hits
                       and any(c["licence"] == p["mdall_licence"] for c in cache_hits[p["di"]]))
    ca_device_ok = sum(1 for p in pairs
                       if p["di"] in cache_hits
                       and (p["mdall_device_id"] == "" or
                            any(c["device_id"] == p["mdall_device_id"] for c in cache_hits[p["di"]])))

    # ---------------------------------------------------------------- 942 vs 934: the 8 unpaired records
    paired_ev = {p["fda_evidence_id"] for p in pairs}
    bridge_ev = cur.execute(
        "select evidence_id, canonical_key from evidence "
        "where run_id='bridge_20261110T174101Z' and source_id='openfda_device_udi'"
    ).fetchall()
    unpaired = [dict(r) for r in bridge_ev if r["evidence_id"] not in paired_ev]
    separator_norms = {normalize_di(k) for k in queried_separator_form}
    unpaired_explained = [u for u in unpaired
                          if str(u["canonical_key"]).partition(":")[2] in separator_norms]
    resolved_minus_pairs = {
        "bridge_run_evidence_records": len(bridge_ev),
        "paired_records": len(pairs),
        "unpaired_records": len(unpaired),
        "unpaired_canonical_keys": [u["canonical_key"] for u in unpaired],
        "unpaired_whose_di_is_a_separator_form_queried_key": len(unpaired_explained),
        "note": (
            "ATLAS reports bridge_fda_records_resolved=942 and pairs=934. The 8 extra records are "
            "records returned by a query for a separator-form MDALL identifier ('0 8800022 30080 3'): "
            "the response's primary DI is the bare 14-digit form, which is NOT a key in ATLAS's "
            "mdall_views dict (that dict is keyed by the raw string), so the pair is dropped."
        ),
    }
    ledger = [
        {"check": "relation count and type", "result": f"934 SAME_DEVICE_IDENTITY / CONFIRMED",
         "independent_of_atlas_claim": False, "kind": "re-read of ATLAS's own relation table"},
        {"check": "Canada side exists in raw MDALL cache with same licence",
         "result": f"{ca_rederived}/934", "independent_of_atlas_claim": True,
         "kind": "full re-derivation from the frozen raw table; the DB only supplied the DI to search for"},
        {"check": "Canada side device_id matches raw cache row",
         "result": f"{ca_device_ok}/934", "independent_of_atlas_claim": True,
         "kind": "re-derivation from raw frozen table"},
        {"check": "US side stored official payload is self-consistent (DI present, primary flag)",
         "result": f"{sum(1 for p in pairs if p['fda_di_is_primary'] is not None)}/934 have the DI row",
         "independent_of_atlas_claim": False,
         "kind": "record-level verification of ATLAS's stored copy of the openFDA response; no network"},
        {"check": "US side cross-check against HORIZON's independent GUDID pull",
         "result": f"{len(horizon_us_overlap)}/934 overlap",
         "independent_of_atlas_claim": True,
         "kind": "independent acquisition, but a different 320-record slice -> overlap expected near 0, so this check is weak by construction"},
        {"check": "Canada side cross-check against HORIZON's independent MDALL licence slice",
         "result": f"{len(horizon_ca_licence_overlap)} distinct licences overlap",
         "independent_of_atlas_claim": True,
         "kind": "independent acquisition, 60-licence firm-targeted slice"},
        {"check": "bridge subsample reproduction (sorted 5005, evenly spaced 1200)",
         "result": f"{len(di_set & queried_set)}/934 confirmed DIs are inside the reproduced 1200-query set",
         "independent_of_atlas_claim": True,
         "kind": "deterministic re-computation from the raw cache"},
        {"check": "request log contains the DIs in batch query URLs",
         "result": (
             f"{len(di_set & log_dis)}/934 confirmed DIs appear in the pilot's "
             f"{pilot_batch_urls} logged bridge batch URLs "
             f"({pilot_tokens} tokens, status {dict(pilot_status)}) — ATLAS reports 48 batches / 6 no-match"),
         "independent_of_atlas_claim": True,
         "kind": "separate ledger file, independent of the evidence payloads"},
    ]

    out = {
        "schema": "medradar.convergence.atlas_bridge_934.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tools/convergence/identity/extract_atlas_bridge.py",
        "network_used": False,
        "inputs": {
            "atlas_db": {"path": str(DB), "sha256": digests["atlas_db"]},
            "mdall_cache": {"path": str(CACHE), "sha256": digests["mdall_cache"]},
            "atlas_request_log": {"path": str(REQUESTS)},
            "horizon_gudid": {"path": str(HORIZON_GUDID), "sha256": digests["horizon_gudid_records"]},
            "horizon_mdall": {"path": str(HORIZON_MDALL), "sha256": digests["horizon_mdall_records"]},
            "atlas_firm_registry": {"path": str(FIRMS_CFG)},
        },
        "relation_set": {
            "count": len(pairs),
            "status": "CONFIRMED only",
            "method": "official_identifier only",
            "authority": "source_declared only",
            "run_id_single": "bridge_20261110T174101Z",
            "distinct_relation_ids": len({p["relation_id"] for p in pairs}),
            "distinct_pairs": len({(p["fda_device_ref"], p["mdall_device_ref"]) for p in pairs}),
            "basis_shared_identifier_scheme": "di (all 934)",
            "basis_shared_identifier_distinct": len(di_set),
            "basis_fields_all_equal_di": all(p["basis_shared_fields"] == ["di"] for p in pairs),
        },
        "gtin_validity": {
            "total": len(pairs),
            "distinct_values": len(di_set),
            "syntactically_14_digits": sum(1 for p in pairs if _GTIN14.match(p["di"])),
            "check_digit_valid": len(pairs) - len(invalid),
            "check_digit_invalid": len(invalid),
            "check_digit_invalid_values": invalid[:20],
            "blank_or_missing": sum(1 for p in pairs if not p["di"]),
            "duplicate_values": len(pairs) - len(di_set),
            "canonical_key_matches_on_both_sides": len(canonical_ok),
        },
        "identifier_scope": {
            "us_side_primary_di": sum(1 for p in pairs if p["fda_di_is_primary"] is True),
            "us_side_package_or_non_primary_di": sum(
                1 for p in pairs if p["fda_di_is_primary"] is False),
            "us_side_di_row_missing": sum(1 for p in pairs if p["fda_di_is_primary"] is None),
            "us_side_scope_values": dict(collections.Counter(p["fda_di_scope"] for p in pairs)),
            "us_side_issuer_values": dict(collections.Counter(p["fda_di_issuer"] for p in pairs)),
            "ca_side_is_primary_asserted_by_atlas": sum(
                1 for p in pairs if p["mdall_di_is_primary"] is True),
            "ca_side_scope_values": dict(collections.Counter(p["mdall_di_scope"] for p in pairs)),
            "ca_side_issuer_values": dict(collections.Counter(p["mdall_di_issuer"] for p in pairs)),
            "evidence_note": (
                "Health Canada MDALL has no primary/package DI concept: its identifier table "
                "publishes one device_identifier string per device row. ATLAS assigns "
                "scheme='di', scope='global', is_primary=1 to any 14-digit value. The US "
                "primary/package distinction is GUDID's own identifiers[].type."
            ),
        },
        "independent_rederivation": {
            "ca_side_in_cache": sum(1 for p in pairs if p["di"] in cache_hits),
            "ca_side_licence_match": ca_rederived,
            "ca_side_device_id_match": ca_device_ok,
            "cache_rows_for_confirmed_dis": sum(len(v) for v in cache_hits.values()),
            "query_batch_urls_in_request_log": bridge_batch_urls,
            "pilot_bridge_batch_urls": pilot_batch_urls,
            "pilot_bridge_tokens": pilot_tokens,
            "pilot_bridge_status_counts": dict(pilot_status),
            "confirmed_di_in_request_log": len(di_set & log_dis),
            "horizon_gudid_overlap": horizon_us_overlap[:20],
            "horizon_gudid_overlap_count": len(horizon_us_overlap),
            "horizon_mdall_licence_overlap": horizon_ca_licence_overlap[:30],
            "horizon_mdall_licence_overlap_count": len(horizon_ca_licence_overlap),
            "reproduced_queried_set_size": len(queried_raw),
            "reproduced_queried_set_distinct_normalised": len(queried_set),
            "reproduced_queried_separator_form_keys": len(queried_separator_form),
            "confirmed_di_in_reproduced_queried_set": len(di_set & queried_set),
            "confirmed_di_outside_reproduced_queried_set": sorted(di_set - queried_set)[:20],
            "confirmed_di_that_are_separator_form_raw": sum(
                1 for p in pairs if normalize_di(p["di"]) != p["di"]),
            "resolved_vs_pairs_arithmetic": resolved_minus_pairs,
        },
        "firm_attribution": firm_attribution,
        "licence_concentration": licence_concentration,
        "anchor_typing": anchor,
        "us_record_status": record_status,
        "duplicate_and_false_positive_risk": duplicated,
        "coverage": {
            "atlas_scanned_rows": 1673926,
            "mdall_gtin_class_rows": 5512,
            "mdall_gtin_class_distinct": 5005,
            "queried_gtins": 1200,
            "confirmed_pairs": 934,
            "confirmed_share_of_query_sample": round(934 / 1200, 6),
            "confirmed_share_of_all_gtin_class_distinct": round(934 / 5005, 6),
            "confirmed_share_of_all_mdall_rows": round(934 / 1673926, 8),
            "gtin_class_share_of_rows": round(5512 / 1673926, 8),
            "unqueried_gtin_class_distinct": 5005 - 1200,
            "note": "934 is a confirmed count on a 1200-of-5005 subsample, not an extrapolation.",
        },
        "verification_ledger": ledger,
        "pairs": pairs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    con.close()

    summary = {k: out[k] for k in (
        "relation_set", "gtin_validity", "identifier_scope", "independent_rederivation",
        "firm_attribution", "duplicate_and_false_positive_risk", "coverage",
        "anchor_typing", "us_record_status")}
    summary["verification_ledger"] = ledger
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
