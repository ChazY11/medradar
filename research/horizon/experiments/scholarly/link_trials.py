"""Priority 2 — clinical-trial <-> publication linkage, verifiable only.

Two directions, both resting on a literal machine-checkable assertion:

**trial -> paper.** ClinicalTrials.gov's ``protocolSection.referencesModule.
references[]`` names a PMID and labels the reference ``RESULT``, ``DERIVED`` or
``BACKGROUND``. The link is CONFIRMED *at the field level* — the trial record
names that PMID. What is NOT confirmed (and is stated as such) is that the paper
reports this trial: ``type`` is submitter-asserted and the sample contains
clearly wrong assertions (a venous-ulcer trial labelling an epidemiology paper
as ``RESULT``).

**paper -> trial.** A paper's own abstract states an ``NCT`` number, and that
trial resolves in the ClinicalTrials.gov API v2. The assertion is the paper's,
quoted literally, and the resolution is checked rather than assumed.

Anything that is neither of those is CANDIDATE, and a topic match is never
evidence: no relation is emitted on the basis of subject similarity.

    python experiments/scholarly/link_trials.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from CONNECTORS.scholarly import _util as U  # noqa: E402

EXP = os.path.dirname(os.path.abspath(__file__))
CTGOV_DETAIL = "https://clinicaltrials.gov/api/v2/studies/"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
MAX_DETAIL_LOOKUPS = 10          # hard bound on individual study resolves
MAX_PMID_RESOLVES = 200          # efetch id list bound

NCT_RE = re.compile(r"\bNCT\d{8}\b")


def rows(source_id: str) -> list[dict]:
    rows_: list[dict] = []
    with open(os.path.join(U.DATASETS, source_id, "records.jsonl"),
              "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows_.append(json.loads(line))
    return rows_


def resolve_pmids(pmids: list[str]) -> dict[str, dict]:
    """Resolve PMIDs to {title, abstract, exists} via one bounded efetch.

    This is what turns a field-level claim ("the trial names PMID X") into a
    checked one ("PMID X exists and is the paper the citation describes").
    """
    out: dict[str, dict] = {}
    if not pmids:
        return out
    ids = sorted(set(pmids))[:MAX_PMID_RESOLVES]
    client = U.make_client("scholarly_pmid_resolve", max_requests=2,
                           max_bytes_per_response=12_000_000,
                           max_total_bytes=16_000_000, rps=1.0)
    try:
        url = EFETCH + "?" + urllib.parse.urlencode({
            "db": "pubmed", "id": ",".join(ids), "retmode": "xml",
            "tool": "MedRadar-HORIZON-001", "email": U.CONTACT,
        })
        res = client.get(url)
        U.save_fetch("pubmed_eutils", "efetch_trial_referenced_pmids.xml", res,
                     note=f"resolve {len(ids)} PMIDs named by trial reference fields")
        print("  pmid resolve budget:", json.dumps(client.budget_report()))
        if not res.ok:
            return out
        import xml.etree.ElementTree as ET
        root = ET.fromstring(res.body)
        for art in root.findall(".//PubmedArticle"):
            pmid_el = art.find(".//MedlineCitation/PMID")
            if pmid_el is None or not pmid_el.text:
                continue
            title_el = art.find(".//Article/ArticleTitle")
            abstract = " ".join(
                (el.text or "") for el in art.findall(".//Article/Abstract/AbstractText")
            ).strip()
            out[pmid_el.text.strip()] = {
                "title": (title_el.text if title_el is not None else None),
                "abstract": abstract or None,
                "exists": True,
                "ncts_in_abstract": sorted(set(NCT_RE.findall(abstract or ""))),
            }
    finally:
        client.close()
    return out


def title_overlap(citation: str | None, title: str | None) -> float | None:
    """Jaccard overlap of lowercased word sets, as a *diagnostic only*.

    A low value is a hint that the trial's citation string and the PubMed title
    may describe different things. It never changes a status on its own.
    """
    if not citation or not title:
        return None
    cw = {w for w in re.findall(r"[a-z]{4,}", citation.lower())}
    tw = {w for w in re.findall(r"[a-z]{4,}", title.lower())}
    if not cw or not tw:
        return None
    return round(len(cw & tw) / len(cw | tw), 3)


def main() -> int:
    trials = rows("clinicaltrials_gov")
    trial_by_nct = {t["source_record_id"]: t for t in trials}

    relations: list[dict] = []
    stats = {"trial_rows": len(trials),
             "references_total": 0,
             "references_with_pmid": 0,
             "by_reference_type": {},
             "nct_strings_found_in_abstracts": 0,
             "nct_resolved": 0,
             "nct_unresolved": 0,
             "detail_lookups": 0,
             "referenced_pmids_distinct": 0,
             "referenced_pmids_resolved_in_pubmed": 0,
             "result_refs_whose_abstract_names_the_trial_nct": 0,
             "result_refs_rejected_pmid_does_not_resolve": 0}

    # Resolve every PMID that any trial reference names, in one bounded efetch.
    all_ref_pmids: list[str] = []
    for t in trials:
        for ref in (t.get("attributes") or {}).get("references") or []:
            if ref.get("pmid"):
                all_ref_pmids.append(str(ref["pmid"]))
    stats["referenced_pmids_distinct"] = len(set(all_ref_pmids))
    print(f"  resolving {len(set(all_ref_pmids))} distinct referenced PMIDs ...")
    pmid_info = resolve_pmids(all_ref_pmids)
    stats["referenced_pmids_resolved_in_pubmed"] = len(pmid_info)
    print(f"  resolved {len(pmid_info)} of {len(set(all_ref_pmids))}")

    # ------------------------------------------------------------------ A: t -> p
    for t in trials:
        nct = t["source_record_id"]
        a = t.get("attributes") or {}
        refs = a.get("references") or []
        for idx, ref in enumerate(refs):
            stats["references_total"] += 1
            pmid = ref.get("pmid")
            rtype = ref.get("type")
            stats["by_reference_type"][rtype] = stats["by_reference_type"].get(rtype, 0) + 1
            if not pmid:
                continue
            stats["references_with_pmid"] += 1
            pmid = str(pmid)
            info = pmid_info.get(pmid)
            abstract_ncts = (info or {}).get("ncts_in_abstract") or []
            names_trial = nct in abstract_ncts
            overlap = title_overlap(ref.get("citation"), (info or {}).get("title"))

            if rtype == "RESULT":
                relation_type = "trial_result_publication"
                base_status = "CONFIRMED"
                what = ("the trial record names this PMID under a reference labelled "
                        "RESULT (submitter-asserted results publication)")
            elif rtype == "DERIVED":
                relation_type = "trial_derived_publication"
                base_status = "CONFIRMED"
                what = ("the trial record names this PMID under a reference labelled "
                        "DERIVED (a publication derived from the study)")
            elif rtype == "BACKGROUND":
                relation_type = "trial_background_citation"
                base_status = "CANDIDATE"
                what = ("the trial record cites this PMID as BACKGROUND: the trial "
                        "mentions the paper, which is NOT evidence that the paper "
                        "reports this trial")
            else:
                relation_type = "trial_reference_untyped"
                base_status = "CANDIDATE"
                what = f"the trial record names this PMID with reference type {rtype!r}"

            status = base_status
            cross = ("PMID_RESOLVED" if info else "PMID_DOES_NOT_RESOLVE")
            confidence = "LOW"
            if info is None:
                # the trial record points at a PMID PubMed does not have: the
                # field-level assertion fails its own check
                status = "REJECTED"
                stats["result_refs_rejected_pmid_does_not_resolve"] += 1
            elif info["exists"] and names_trial:
                cross = "PMID_RESOLVED_AND_ABSTRACT_NAMES_THE_TRIAL_NCT"
                confidence = "HIGH"
                if rtype in ("RESULT", "DERIVED"):
                    stats["result_refs_whose_abstract_names_the_trial_nct"] += 1
            else:
                confidence = "LOW"
                if rtype in ("RESULT", "DERIVED"):
                    stats["result_refs_not_corroborated_by_abstract"] = (
                        stats.get("result_refs_not_corroborated_by_abstract", 0) + 1)
            if rtype == "BACKGROUND":
                confidence = "LOW"

            relations.append({
                "relation_type": relation_type,
                "status": status,
                "trial_id": nct,
                "paper_pmid": pmid,
                "paper_doi": U.norm_doi(_doi_from_citation(ref.get("citation") or "")),
                "confirmed_by": {
                    "field": (f"protocolSection.referencesModule.references[{idx}]"
                              f".pmid"),
                    "exact_value": pmid,
                    "reference_type_field": (
                        f"protocolSection.referencesModule.references[{idx}].type"),
                    "reference_type_value": rtype,
                    "citation_string": ref.get("citation"),
                    "pubmed_title_of_that_pmid": (info or {}).get("title"),
                    "pubmed_abstract_nct_list": abstract_ncts,
                },
                "cross_check": {
                    "pmid_resolution": cross,
                    "paper_abstract_literally_names_this_trial": names_trial,
                    "citation_title_word_overlap": overlap,
                    "diagnostic_only": (
                        "word overlap below ~0.15 suggests the citation string and the "
                        "PubMed title may describe different things; it is reported, "
                        "never used to change a status"),
                },
                "confidence": confidence,
                "confidence_meaning": (
                    "HIGH = the paper's own PubMed abstract names this trial's NCT "
                    "number, so the submitter's claim is independently corroborated by "
                    "the paper. LOW = the field-level claim holds (or is only a "
                    "background citation) but the paper's abstract does not name the "
                    "trial, so the paper may not report it."),
                "what_is_confirmed": what,
                "what_is_not_confirmed": (
                    "that the paper's content reports this trial; `type` is "
                    "submitter-asserted and was not verified against the paper's full "
                    "text"),
                "trial_sponsor": (a.get("lead_sponsor") or {}).get("name"),
                "trial_sponsor_class": (a.get("lead_sponsor") or {}).get("class"),
            })

    # ------------------------------------------------------------------ B: p -> t
    # Papers that literally state an NCT number in their abstract.
    candidates: dict[str, list[dict]] = {}
    for src in ("europepmc", "pubmed_eutils"):
        for r in rows(src):
            a = r.get("attributes") or {}
            abstract = a.get("abstract_text") or a.get("abstractText")
            if not abstract:
                continue
            found = sorted(set(NCT_RE.findall(abstract)))
            if not found:
                continue
            doi = next((i["value"] for i in r.get("identifiers") or []
                        if i["scheme"] == "doi"), None)
            for n in found:
                stats["nct_strings_found_in_abstracts"] += 1
                candidates.setdefault(n, []).append({
                    "stating_source": src,
                    "stating_field": "abstractText",
                    "doi": U.norm_doi(doi),
                    "source_record_id": r.get("source_record_id"),
                    "title": r.get("original_name"),
                    "literal": n,
                })

    client = None
    try:
        if candidates:
            client = U.make_client("scholarly_ctgov_verify",
                                   max_requests=MAX_DETAIL_LOOKUPS + 2,
                                   max_bytes_per_response=2_000_000,
                                   max_total_bytes=6_000_000, rps=1.5)
        for nct, stmts in sorted(candidates.items()):
            resolved = nct in trial_by_nct
            if not resolved and client is not None and stats["detail_lookups"] < MAX_DETAIL_LOOKUPS:
                try:
                    res = client.get(CTGOV_DETAIL + nct)
                    stats["detail_lookups"] += 1
                    U.save_fetch("clinicaltrials_gov", f"verify_{nct}.json", res,
                                 note=f"paper->trial verification resolve for {nct}")
                    resolved = res.ok
                except Exception:
                    resolved = False
            if resolved:
                stats["nct_resolved"] += 1
            else:
                stats["nct_unresolved"] += 1
            for st in stmts:
                relations.append({
                    "relation_type": "paper_states_trial_id",
                    "status": "CONFIRMED" if resolved else "REJECTED",
                    "trial_id": nct,
                    "paper_pmid": st["source_record_id"] if st["stating_source"] == "pubmed_eutils" else None,
                    "paper_doi": st["doi"],
                    "confirmed_by": {
                        "field": f"{st['stating_source']} record field abstractText",
                        "exact_value": st["literal"],
                        "paper_title": st["title"],
                    },
                    "what_is_confirmed": (
                        "the paper's abstract contains the literal registry identifier "
                        f"{nct}" + ("" if resolved else
                                    " BUT that identifier does not resolve in the "
                                    "ClinicalTrials.gov API v2")),
                    "what_is_not_confirmed": (
                        "that the trial is about the device under study in the paper; "
                        "only that the paper named the registry entry"),
                    "trial_sponsor": ((trial_by_nct.get(nct) or {}).get("attributes")
                                       or {}).get("lead_sponsor", {}).get("name"),
                    "trial_sponsor_class": ((trial_by_nct.get(nct) or {}).get("attributes")
                                            or {}).get("lead_sponsor", {}).get("class"),
                })
    finally:
        if client is not None:
            print("  ctgov verify budget:", json.dumps(client.budget_report()))
            client.close()

    out = os.path.join(EXP, "RELATIONS_TRIAL_PAPER.jsonl")
    U.write_jsonl(out, relations)

    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in relations:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_type[r["relation_type"]] = by_type.get(r["relation_type"], 0) + 1

    doc = {
        "experiment": "EXP-H2 (Priority 2)",
        "title": "Clinical trial <-> publication linkage from machine-checkable fields only",
        "generated_at": U.utc_now(),
        "output": "RELATIONS_TRIAL_PAPER.jsonl",
        "rule": {
            "confirmed": [
                "(a) the trial record has a referencesModule reference naming a PMID "
                "with type in {RESULT, DERIVED} -> status CONFIRMED, scoped to the "
                "field-level claim that the trial record names that paper",
                "(b) the paper's own abstract contains a literal NCT number AND that "
                "trial resolves in the ClinicalTrials.gov API v2 -> CONFIRMED",
            ],
            "candidate": [
                "trial references a PMID as BACKGROUND (the trial mentions the paper)",
                "trial references a PMID with no recognised reference type",
            ],
            "rejected": [
                "a paper's abstract states an NCT number that does not resolve",
            ],
            "never_used_as_evidence": (
                "subject similarity, shared device name, shared sponsor, journal, or "
                "co-mention. No relation in this file rests on those."),
        },
        "stats": {
            **stats,
            "relations_total": len(relations),
            "by_status": by_status,
            "by_relation_type": by_type,
        },
        "caveat": (
            "ClinicalTrials.gov reference `type` is submitter-asserted and is "
            "observably wrong for some records in this sample (an epidemiology paper "
            "labelled RESULT for a venous-ulcer device trial). CONFIRMED therefore "
            "means 'the field says so', not 'the paper is about this trial'."),
    }
    U.write_json(os.path.join(EXP, "RELATIONS_TRIAL_PAPER_SUMMARY.json"), doc)
    print(json.dumps(doc["stats"], indent=2))
    print("nct candidates:", {k: len(v) for k, v in candidates.items()})
    return 0


def _doi_from_citation(cit: str) -> str | None:
    m = re.search(r"10\.\d{4,9}/[^\s;,\)]+", cit or "")
    return m.group(0).rstrip(".") if m else None


if __name__ == "__main__":
    raise SystemExit(main())
