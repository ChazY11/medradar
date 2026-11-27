"""Priority 3 — grant <-> work linkage, verifiable only.

A grant is linked to a work **only** when the work's own funding metadata declares
that grant number, and the grant then resolves in an open grant registry:

* NIH RePORTER v2 (POST ``/v2/projects/search`` with ``criteria.project_nums``)
  echoes ``core_project_num``, so the match is confirmed by the registry, not by
  string similarity.
* EU CORDIS: a work that declares a Horizon-2020 grant agreement number is looked
  up in CORDIS's project index. CORDIS has **no publication index** (probe
  ``cordis_no_publication_index``), so the reverse direction — start from a
  CORDIS project and list its papers — is not buildable. The work must declare
  the grant.

Declared grant numbers that belong to funders with no queryable open registry
(Chinese NSFC, Brazilian CNPq, Japanese AMED, Danish funders, and industry
funders such as GE Healthcare) are emitted as CANDIDATE with the reason stated.
They are never dropped, because "a work declares a grant we cannot resolve" is
itself the measurement.

    python experiments/scholarly/link_grants.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from CONNECTORS.scholarly import _util as U  # noqa: E402

EXP = os.path.dirname(os.path.abspath(__file__))
CORDIS = "https://cordis.europa.eu/api/search/results"
EU_HINTS = ("horizon", "h2020", "european commission", "eu ")


def _slug(s: str) -> str:
    import re as _re
    return _re.sub(r"[^A-Za-z0-9]+", "_", s)[:40].strip("_")


def rows(source_id: str) -> list[dict]:
    out: list[dict] = []
    with open(os.path.join(U.DATASETS, source_id, "records.jsonl"),
              "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> int:
    idx = U.read_json(os.path.join(U.DATASETS, "nih_reporter", "REPORTER_INDEX.json"))
    declared = idx["declared_grant_rows"]
    reporter_recs = rows("nih_reporter")
    cordis_recs = rows("eu_cordis")

    # ---------------------------------------------------------------- NIH side
    core_to_projects: dict[str, list[dict]] = {}
    for g in reporter_recs:
        a = g.get("attributes") or {}
        core = a.get("core_project_num")
        if not core:
            continue
        core_to_projects.setdefault(core, []).append({
            "appl_id": g.get("source_record_id"),
            "project_num": a.get("project_num"),
            "core_project_num": core,
            "fiscal_year": a.get("fiscal_year"),
            "agency_ic_admin": (a.get("agency_ic_admin") or {}).get("abbreviation"),
            "organization": (a.get("organization") or {}).get("org_name"),
            "project_title": a.get("project_title"),
            "project_start_date": a.get("project_start_date"),
            "award_notice_date": a.get("award_notice_date"),
        })

    # ---------------------------------------------------------------- EU side
    eu_declared = sorted({
        (d["grant_id_normalised"], d["grant_id_raw"], d["agency"])
        for d in declared
        if d["grant_id_normalised"] and d["agency"]
        and any(h in str(d["agency"]).lower() for h in EU_HINTS)
    })
    cordis_by_reference = {}
    for g in cordis_recs:
        a = g.get("attributes") or {}
        ref = str(a.get("reference") or "")
        if ref:
            cordis_by_reference[ref] = {
                "rcn": a.get("rcn"), "reference": ref,
                "acronym": a.get("acronym"), "title": a.get("title"),
                "programme": a.get("programme"),
            }
    print(f"  EU-declared grant ids: {eu_declared}")

    eu_relations: list[dict] = []
    attempts: list[dict] = []
    lookup_client = None
    try:
        if eu_declared:
            lookup_client = U.make_client(
                "scholarly_cordis_verify", max_requests=16,
                max_bytes_per_response=1_500_000, max_total_bytes=8_000_000, rps=1.0)
        for norm, raw, agency in eu_declared:
            hit = cordis_by_reference.get(norm)
            source_field = None
            if hit is None and lookup_client is not None:
                # Bounded targeted lookup by grant agreement number.
                # CORDIS's undocumented search parser rejects numeric-only tokens:
                #   q=685648                        -> HTTP 500 "Unknown filter type"
                #   q=contenttype='project' AND 685648 -> HTTP 500 "Query is not valid"
                # because a bare number is interpreted as a filter expression. Three
                # forms are tried in order, each response saved verbatim; the first
                # non-error form is used and the results are filtered locally on
                # payload.results[].reference.
                forms = [
                    str(raw),
                    f"contenttype='project' AND {raw}",
                    f'"{raw}"',
                ]
                for form in forms:
                    url = CORDIS + "?" + urllib.parse.urlencode(
                        {"q": form, "num": 25})
                    res = lookup_client.get(url)
                    U.save_fetch("eu_cordis", f"verify_{norm}_{_slug(form)}.json", res,
                                 note=(f"CORDIS targeted lookup for declared EU grant "
                                       f"{raw}; query form {form!r}"))
                    body_head = res.text()[:220]
                    attempts.append({"grant": norm, "query": form,
                                     "status": res.status, "bytes": len(res.body),
                                     "body_head": body_head})
                    if not res.ok:
                        continue
                    try:
                        payload = (res.json() or {}).get("payload") or {}
                    except Exception:
                        payload = {}
                    for p in payload.get("results") or []:
                        if str(p.get("reference") or "") == norm:
                            hit = {"rcn": p.get("rcn"), "reference": norm,
                                   "acronym": p.get("acronym"), "title": p.get("title"),
                                   "programme": p.get("programme"),
                                   "found_by": (f"targeted CORDIS lookup with query form "
                                                f"{form!r}, filtered on "
                                                f"payload.results[].reference")}
                            source_field = "cordis api/search/results -> payload.results[]"
                            break
                    if hit:
                        break
            if hit:
                source_field = source_field or (
                    "cordis api/search/results -> payload.results[] (already in sample)")
            eu_relations.append({"norm": norm, "raw": raw, "agency": agency,
                                 "hit": hit, "source_field": source_field})
    finally:
        if lookup_client is not None:
            print("  cordis verify budget:", json.dumps(lookup_client.budget_report()))
            lookup_client.close()

    # ------------------------------------------------------------- relations
    relations: list[dict] = []
    stats = Counter()
    seen: set[tuple[str, str]] = set()

    for d in declared:
        work_doi = U.norm_doi(d.get("work_doi"))
        work_src = d.get("declared_by_source")
        raw = d.get("grant_id_raw")
        norm = d.get("grant_id_normalised")
        agency = d.get("agency")
        if not work_doi or not (norm or raw):
            stats["declared_rows_skipped_no_work_or_id"] += 1
            continue
        key = (work_doi, norm or raw)
        if key in seen:
            stats["declared_rows_deduplicated"] += 1
            continue
        seen.add(key)

        base = {
            "work_doi": work_doi,
            "grant_id_declared_raw": raw,
            "grant_id_normalised": norm,
            "funder_as_declared": agency,
            "declared_by_source": work_src,
            "declared_field": d.get("declared_field"),
            "declared_work_source_record_id": d.get("work_source_record_id"),
        }

        # --- NIH
        if d.get("nih_core"):
            projects = core_to_projects.get(d["nih_core"])
            if projects:
                stats["nih_confirmed"] += 1
                relations.append({
                    **base,
                    "relation_type": "work_declares_nih_grant",
                    "status": "CONFIRMED",
                    "grant_registry": "nih_reporter",
                    "grant_id_resolved": d["nih_core"],
                    "confirmed_by": {
                        "work_side": {
                            "field": d.get("declared_field"),
                            "exact_value": raw,
                            "source": work_src,
                        },
                        "grant_side": {
                            "field": "criteria.project_nums -> core_project_num",
                            "exact_value": d["nih_core"],
                            "note": "RePORTER echoes core_project_num, so the match is "
                                    "made by the registry, not by us",
                        },
                    },
                    "projects": projects[:12],
                    "project_count": len(projects),
                    "confidence": "FIELD_LEVEL_NUMBER_MATCH",
                    "what_is_confirmed": (
                        "this publication's own funding metadata declares this grant "
                        "number, and NIH RePORTER holds a project with that core number"),
                    "what_is_not_confirmed": (
                        "that the grant paid for the specific work described in the "
                        "paper; RePORTER does not carry publication-level attribution"),
                })
            else:
                stats["nih_declared_but_not_resolved"] += 1
                relations.append({
                    **base,
                    "relation_type": "work_declares_nih_grant",
                    "status": "REJECTED",
                    "grant_registry": "nih_reporter",
                    "grant_id_resolved": None,
                    "confirmed_by": {
                        "work_side": {"field": d.get("declared_field"),
                                      "exact_value": raw, "source": work_src},
                        "grant_side": {"field": "criteria.project_nums",
                                       "exact_value": d["nih_core"],
                                       "note": "query returned zero projects"},
                    },
                    "projects": [],
                    "project_count": 0,
                    "rejection_reason": (
                        "the declared number looks like an NIH core project number but "
                        "RePORTER holds no project with that core"),
                })
            continue

        # --- EU / CORDIS
        eu = next((x for x in eu_relations if x["norm"] == norm), None)
        if eu is not None:
            if eu.get("hit"):
                stats["eu_confirmed"] += 1
                relations.append({
                    **base,
                    "relation_type": "work_declares_eu_grant",
                    "status": "CONFIRMED",
                    "grant_registry": "eu_cordis",
                    "grant_id_resolved": norm,
                    "confirmed_by": {
                        "work_side": {"field": d.get("declared_field"),
                                      "exact_value": raw, "source": work_src},
                        "grant_side": {
                            "field": eu["source_field"],
                            "exact_value": eu["hit"].get("reference") or norm,
                            "cordis_rcn": eu["hit"].get("rcn"),
                            "cordis_title": eu["hit"].get("title"),
                        },
                    },
                    "projects": [eu["hit"]],
                    "project_count": 1,
                    "confidence": "FIELD_LEVEL_NUMBER_MATCH",
                    "what_is_confirmed": (
                        "the publication declares this EU grant agreement number and "
                        "CORDIS holds the matching project record"),
                    "what_is_not_confirmed": (
                        "that the project produced the paper; CORDIS has no publication "
                        "index, so the reverse direction cannot be checked"),
                })
            else:
                stats["eu_declared_but_not_found_in_cordis"] += 1
                relations.append({
                    **base,
                    "relation_type": "work_declares_eu_grant",
                    "status": "CANDIDATE",
                    "grant_registry": "eu_cordis",
                    "grant_id_resolved": None,
                    "confirmed_by": {
                        "work_side": {"field": d.get("declared_field"),
                                      "exact_value": raw, "source": work_src},
                        "grant_side": {"field": "cordis api/search/results",
                                       "exact_value": None,
                                       "note": "targeted CORDIS lookup returned no "
                                               "project with this grant agreement id"},
                    },
                    "projects": [],
                    "project_count": 0,
                    "unresolved_reason": (
                        "the paper declares an EU grant agreement number that the "
                        "CORDIS project index did not return for that value"),
                    "blocker": ("CORDIS keeps project/result/article indices but no "
                                "publication index (HTTP 500 index_not_found_exception "
                                "for contenttype='publication'), so EU grant->paper "
                                "linkage cannot be built from the CORDIS side at all"),
                })
            continue

        # --- other funders: no queryable open registry
        stats["other_funder_candidate"] += 1
        relations.append({
            **base,
            "relation_type": "work_declares_other_grant",
            "status": "CANDIDATE",
            "grant_registry": None,
            "grant_id_resolved": None,
            "confirmed_by": {
                "work_side": {"field": d.get("declared_field"),
                              "exact_value": raw, "source": work_src},
                "grant_side": {"field": None, "exact_value": None,
                               "note": "no open grant registry was queried for this "
                                       "funder"},
            },
            "projects": [],
            "project_count": 0,
            "unresolved_reason": (
                f"funder {agency!r} has no open, keyless grant registry in this "
                "workstream's source set; the declaration is real but unverifiable here"),
        })

    out = os.path.join(EXP, "RELATIONS_GRANT_WORK.jsonl")
    U.write_jsonl(out, relations)

    by_status = Counter(r["status"] for r in relations)
    by_type = Counter(r["relation_type"] for r in relations)
    doc = {
        "experiment": "EXP-H4 (Priority 3)",
        "title": "Grant <-> work linkage where the work declares the grant and an open "
                 "registry resolves it",
        "generated_at": U.utc_now(),
        "output": "RELATIONS_GRANT_WORK.jsonl",
        "rule": {
            "confirmed": (
                "the publication's own funding metadata (Europe PMC grantsList, PubMed "
                "GrantList, or Crossref funder[].award[]) declares a grant number, AND "
                "that number resolves in NIH RePORTER (core_project_num echoed by the "
                "registry) or in the CORDIS project index"),
            "candidate": (
                "declared but not resolvable: the funder has no open registry in this "
                "source set, or the CORDIS lookup found nothing"),
            "rejected": (
                "declared as an NIH-style number but RePORTER holds no project with that "
                "core"),
            "reverse_direction_blocked": (
                "starting from a grant and listing its publications is NOT possible: "
                "NIH RePORTER does not carry publication identifiers in the v2 search "
                "response, and CORDIS has no publication index (probe "
                "cordis_no_publication_index: HTTP 500 'no such index [publication]')"),
        },
        "stats": {
            "declared_grant_rows": len(declared),
            "distinct_declared_ids": len({d.get("grant_id_normalised") for d in declared}),
            "nih_cores_declared": len(idx.get("declared_nih_cores") or []),
            "nih_projects_resolved": len(core_to_projects),
            "eu_declared_ids": len(eu_declared),
            "eu_resolved_in_cordis": sum(1 for x in eu_relations if x.get("hit")),
            "eu_lookup_attempts": attempts,
            "relations_total": len(relations),
            "by_status": dict(by_status),
            "by_relation_type": dict(by_type),
            "detail": dict(stats),
        },
        "sources_used": {
            "declaration_side": ["europepmc", "pubmed_eutils", "crossref"],
            "resolution_side": ["nih_reporter", "eu_cordis"],
            "blocked": {"eu_ctis": "HTTP 403 AWS authorizer - requires EMA credential"},
        },
        "worked_example_of_why_confidence_matters": {
            "work_doi": "10.1093/ageing/afab278",
            "grant": "831644",
            "declared_by": "Europe PMC grantsList, PubMed GrantList AND Crossref "
                           "funder[].award[] - all three agree the paper declares "
                           "H2020 grant 831644",
            "resolved_to": "CORDIS RCN 221882, project title 'EOSCsecretariat.eu'",
            "why_it_matters": (
                "the number match is machine-verified, yet an ageing/ICU paper is "
                "improbably funded by the EOSC secretariat project. That is a "
                "publication-metadata error, and no amount of identifier matching "
                "fixes it. This is why every CONFIRMED here is scoped to "
                "'the number matches', never to 'the grant funded this work'."),
        },
    }
    U.write_json(os.path.join(EXP, "RELATIONS_GRANT_WORK_SUMMARY.json"), doc)
    print(json.dumps(doc["stats"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
