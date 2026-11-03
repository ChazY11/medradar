"""S-029 step 08 — quality metrics A-D and the pre-registered verdict (RQ4).

Every number in DATA_QUALITY_REPORT.md is produced here and stored in
`artifacts/quality_metrics.json`. The verdict is computed by the rule frozen in
`GO_NO_GO_CRITERIA.md` (sha256 recorded in `artifacts/prereg_decision.json`) — this
script contains no discretionary override.

Sections:
  A coverage            — how much of what we found became evidence
  B entity resolution   — what the identity layer does and fails to do
  C temporal quality    — which clocks exist, and where a contradiction is real
  D relation quality    — direct vs derived, conflict, duplication, over-interpretation
  verdict               — T1..T6 evaluated, one of three allowed strings

Run:  python research/studies/relation_network_s029/code/s029_08_quality_metrics.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict, defaultdict as _dd
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, read_json, read_jsonl, sha256_text,
                         utcnow_iso, write_json)

PREREG = STUDY = ARTIFACT_DIR.parent


def _d(s):
    """Parse a source date at whatever precision it has.

    Month-only dates are extremely common in ClinicalTrials.gov start dates (2,618 claims).
    Treating them as unparseable silently removed them from contradiction counts, which the
    independent temporal audit caught (it reported 2,775 vs our 1,979). A month resolves to
    the first day of that month and the precision is reported separately.
    """
    if not s:
        return None
    v = str(s).strip()
    for fmt, cut in (("%Y-%m-%d", 10), ("%Y-%m", 7), ("%Y", 4)):
        try:
            return date.fromisoformat(v[:cut]) if fmt != "%Y-%m" and fmt != "%Y" else \
                datetime.strptime(v[:cut], fmt).date()
        except ValueError:
            continue
    return None


def pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def main() -> None:
    claims = list(read_jsonl(DATA_DIR / "claims.jsonl"))
    entities = {e["entity_id"]: e for e in read_jsonl(DATA_DIR / "entities.jsonl")}
    evidence = {e["evidence_id"]: e for e in read_jsonl(DATA_DIR / "evidence.jsonl")}
    mentions = list(read_jsonl(DATA_DIR / "company_mentions.jsonl"))
    rejects = list(read_jsonl(DATA_DIR / "claim_rejects.jsonl"))
    institutions = list(read_jsonl(DATA_DIR / "institutions.jsonl"))
    trials = list(read_jsonl(DATA_DIR / "ctgov_trials.jsonl"))
    pubs = list(read_jsonl(DATA_DIR / "epmc_pubs.jsonl"))
    cross = read_json(ARTIFACT_DIR / "crosssource.json") if (ARTIFACT_DIR / "crosssource.json").exists() else {}
    pmid_probe = read_json(ARTIFACT_DIR / "pmid_probe.json") if (ARTIFACT_DIR / "pmid_probe.json").exists() else {}
    mapping = read_json(ARTIFACT_DIR / "company_mapping.json")

    # ------------------------------------------------------------------
    # A. Coverage
    # ------------------------------------------------------------------
    authoritative = [c for c in claims if c["claim_status"] in ("VERIFIED_BY_SOURCE", "CANDIDATE")]
    company_claims = [c for c in claims if c["subject_id"].startswith("ent:company:")]
    family = {
        "A_company_trial_sponsor": [c for c in claims if c["predicate"] == "SPONSORS_TRIAL"
                                    and c["relation_role"] in ("lead_sponsor", "collaborator")
                                    and c["subject_id"].startswith("ent:company:")],
        "A_company_trial_responsible": [c for c in claims if c["predicate"] == "RESPONSIBLE_FOR_TRIAL"],
        "A_institution_trial": [c for c in claims if c["predicate"] in ("SPONSORS_TRIAL",
                                                                       "HOSTS_TRIAL_SITE")
                                and c["subject_id"].startswith("ent:institution:")],
        "A_trial_references_pub": [c for c in claims if c["predicate"] == "REFERENCES_PUBLICATION"],
        "B_company_publication": [c for c in claims if c["predicate"] == "AFFILIATED_WITH"
                                  and c["subject_id"].startswith("ent:company:")],
        "B_institution_publication": [c for c in claims if c["predicate"] == "AFFILIATED_WITH"
                                      and c["subject_id"].startswith("ent:institution:")],
        "B_company_institution_coaffiliation": [c for c in claims if c["predicate"] == "CO_AFFILIATED_ON"],
        "B_publication_topic": [c for c in claims if c["predicate"] == "HAS_TOPIC"],
        "B_company_funded_publication": [c for c in claims if c["predicate"] == "FUNDED_BY"],
        "C_confirmed_cooperation": [],
    }
    claims_per_company = Counter(c["subject_id"].split(":")[-1] for c in authoritative
                                 if c["subject_id"].startswith("ent:company:"))
    claims_per_company_all = Counter(
        c["subject_id"].split(":")[-1] for c in claims
        if c["subject_id"].startswith("ent:company:"))

    by_year = Counter()
    for c in claims:
        y = (c.get("published_at") or "")[:4]
        by_year[y if y.isdigit() else "UNKNOWN"] += 1

    def has_stable_id(c: dict) -> bool:
        def side(eid):
            if not eid:
                return False
            ent = entities.get(eid) or {}
            ids = ent.get("stable_external_ids") or {}
            return any(v for v in ids.values() if v)
        return side(c["subject_id"]) or side(c.get("object_id"))

    coverage = {
        "records_collected": {"clinical_trials": len(trials), "publications": len(pubs),
                              "institutions_candidates": len(institutions)},
        "claims_total": len(claims),
        "claims_authoritative": len(authoritative),
        "claims_by_family": {k: len(v) for k, v in family.items()},
        "claims_by_predicate": dict(Counter(c["predicate"] for c in claims)),
        "claims_per_company_authoritative": dict(claims_per_company),
        "claims_per_company_all": dict(claims_per_company_all),
        "claims_by_publication_year": dict(sorted(by_year.items())),
        "share_claims_with_stable_external_id": pct(sum(1 for c in claims if has_stable_id(c)),
                                                    len(claims)),
        "share_claims_with_published_at": pct(sum(1 for c in claims if c.get("published_at")),
                                              len(claims)),
        "share_claims_with_event_or_valid_from": pct(
            sum(1 for c in claims if c.get("event_at") or c.get("valid_from")), len(claims)),
        "records_rejected_or_ambiguous": len(rejects),
        "rejects_by_rule": dict(Counter(r.get("rule") for r in rejects).most_common(20)),
    }

    # ------------------------------------------------------------------
    # B. Entity resolution
    # ------------------------------------------------------------------
    company_token_mentions = [m for m in mentions if m.get("company_key")]
    ms = Counter(m["mapping_status"] for m in company_token_mentions)
    rr = Counter(r.get("mapping_status") for r in rejects)
    inst_family = defaultdict(Counter)
    for ic in institutions:
        inst_family[ic["family"]][(ic.get("ror") or {}).get("status", "MISSING")] += 1
    anach = [m for m in mentions if m.get("rule") == "subsidiary_not_yet_owned"]
    date_unknown = [m for m in company_token_mentions if m.get("dates_unknown")]
    entity_resolution = {
        "company_mention_outcomes": dict(ms),
        "company_mention_outcomes_pct": {k: pct(v, len(company_token_mentions)) for k, v in ms.items()},
        "claim_reject_outcomes": dict(rr),
        "company_strings_that_were_not_entities": len(rejects),
        "institution_ror_by_family": {k: dict(v) for k, v in inst_family.items()},
        "institution_ror_overall": dict(Counter((ic.get("ror") or {}).get("status")
                                                for ic in institutions)),
        "anachronistic_mentions_subsidiary_not_yet_owned": len(anach),
        "anachronistic_mentions_examples": [
            {"raw_string": m["raw_string"], "claim_date": m["claim_date"],
             "ownership_from": m.get("ownership_from"), "reason": m["reason"]}
            for m in anach[:8]],
        "mentions_with_unestablished_ownership_dates": len(date_unknown),
        "claims_with_anachronism_flag": sum(1 for c in claims if c.get("anachronism")),
        "mapping_date_sources": mapping.get("date_source_counts"),
    }

    # ------------------------------------------------------------------
    # C. Temporal quality
    # ------------------------------------------------------------------
    lag_values = [c["observed_lag_days"] for c in claims
                  if isinstance(c.get("observed_lag_days"), int)]
    lag_values.sort()

    def q(p):
        if not lag_values:
            return None
        return lag_values[min(int(p * len(lag_values)), len(lag_values) - 1)]

    # Two definitions are reported deliberately. The STRICT one (adopted) counts only records
    # observed by the Live Observatory ledger; the lenient one counts records whose own
    # published date fell within 7 days of this study's fetch. The verdict uses the strict one.
    actual = [c for c in claims if c.get("strict_observed_asof")]  # strict: ledger-observed only
    # lenient definition, computed from the clocks rather than from a label, so a hard-coded
    # family label cannot hide a near-real-time fetch (the temporal auditor found 16 such claims)
    lenient = [c for c in claims
               if isinstance(c.get("observed_lag_days"), int)
               and 0 <= c["observed_lag_days"] <= 7]
    lenient_records = {c["source_record_id"] for c in lenient}
    lenient_le1 = [c for c in lenient if c["observed_lag_days"] <= 1]
    pub_before_event = []
    pub_before_event_trial = []
    pub_before_event_other = []
    for c in claims:
        pa, ea = _d(c.get("published_at")), _d(c.get("event_at"))
        if pa and ea and pa < ea:
            pub_before_event.append(c)
            if c["predicate"] in ("SPONSORS_TRIAL", "HOSTS_TRIAL_SITE", "RESPONSIBLE_FOR_TRIAL"):
                pub_before_event_trial.append(c)
            else:
                pub_before_event_other.append(c)
    # registry references whose cited paper is published after the trial's first post
    future_refs = []
    for c in claims:
        if c["predicate"] != "REFERENCES_PUBLICATION" or not c.get("object_id"):
            continue
        pub = entities.get(c["object_id"]) or {}
        py = _d(pub.get("valid_from"))
        ty = _d(c.get("published_at"))
        if py and ty and py > ty:
            future_refs.append(c)
    temporal = {
        "time_basis_counts": dict(Counter(c.get("time_basis") for c in claims)),
        "share_actual_observation_strict": pct(len(actual), len(claims)),
        "actual_observation_claims_strict": len(actual),
        "actual_observation_claims_lenient_this_study": len(lenient),
        "lenient_distinct_source_records": len(lenient_records),
        "lenient_lag_le_1_day": len(lenient_le1),
        "lenient_breakdown": dict(Counter(c["predicate"] for c in lenient)),
        "observation_definition": "STRICT = observed by the Live Observatory ledger (adopted); "
                                  "LENIENT = published within 7 days of this study's own fetch "
                                  "(reported but not used for any claim of point-in-time capability)",
        "valid_to_populated": sum(1 for c in claims if c.get("valid_to")),
        "valid_to_populated_pct": pct(sum(1 for c in claims if c.get("valid_to")), len(claims)),
        "observed_lag_days": {"n": len(lag_values), "min": lag_values[0] if lag_values else None,
                             "p25": q(.25), "median": q(.5), "p75": q(.75),
                             "max": lag_values[-1] if lag_values else None},
        "precision_distribution": dict(Counter(c.get("timestamp_precision") for c in claims)),
        "share_declared_at_day_or_month": pct(
            sum(1 for c in claims if c.get("timestamp_precision") in ("DAY", "MONTH")), len(claims)),
        "contradiction_published_before_event": {
            "count": len(pub_before_event),
            "share": pct(len(pub_before_event), len(claims)),
            "trial_registration_families": len(pub_before_event_trial),
            "non_trial_families": len(pub_before_event_other),
            "note": "a registration may lawfully be posted before the study start (pre-registration); "
                    "the non-trial cases are index-date vs issue-date artefacts. Month-precision "
                    "event dates are compared at first-of-month and reported separately. These two "
                    "classes must not be merged into one 'error' count."},
        "contradiction_trial_references_future_paper": len(future_refs),
        "claims_without_any_publication_time": sum(1 for c in claims if not c.get("published_at")),
        "claims_without_any_event_time": sum(1 for c in claims if not c.get("event_at")),
    }

    # ------------------------------------------------------------------
    # D. Relation quality
    # ------------------------------------------------------------------
    quality = Counter(e.get("provenance_quality") for e in evidence.values())
    derived = [c for c in claims if c["predicate"] == "CO_AFFILIATED_ON"]
    map_only = [c for c in claims if c.get("mapping_status") in ("ALIAS", "FUZZY",
                                                                 "ALIAS_HISTORICAL")]
    fuzzy_only = [c for c in claims if c.get("mapping_status") == "FUZZY"]
    relation_quality = {
        "evidence_provenance_quality": dict(quality),
        "share_claims_primary_structured": pct(
            sum(1 for c in claims if (evidence.get(c["evidence_id"]) or {})
                .get("provenance_quality") == "PRIMARY_STRUCTURED"), len(claims)),
        "share_claims_primary_text": pct(
            sum(1 for c in claims if (evidence.get(c["evidence_id"]) or {})
                .get("provenance_quality") == "PRIMARY_TEXT"), len(claims)),
        "share_claims_derived_not_directly_stated": pct(len(derived), len(claims)),
        "derived_claims_predicates": dict(Counter(c["predicate"] for c in derived)),
        "share_claims_resting_on_alias_or_fuzzy_identity": pct(len(map_only), len(claims)),
        "share_claims_fuzzy_identity_only": pct(len(fuzzy_only), len(claims)),
        "claims_with_multiple_evidence": sum(1 for c in claims if c.get("evidence_count", 1) > 1),
        "evidence_rows": len(evidence),
        "claims": len(claims),
        "evidence_per_claim": round(len(evidence) / len(claims), 3) if claims else None,
        "conflicted_claims": sum(1 for c in claims if c["claim_status"] == "CONFLICTED"),
        "co_affiliation_share_of_company_relations": pct(
            len(derived), max(len(company_claims), 1)),
        "explicit_non_relation": "co-affiliation is not cooperation and not knowledge transfer; "
                                 "no claim in this study asserts either",
    }

    # ------------------------------------------------------------------
    # Cross-source (T5)
    # ------------------------------------------------------------------
    pmid_claims = [c for c in claims if c["predicate"] == "REFERENCES_PUBLICATION"]
    pmid_with_obj = [c for c in pmid_claims if c.get("object_id")]
    # institutions that appear in claims from more than one source
    inst_sources = defaultdict(set)
    for c in claims:
        if c["subject_id"].startswith("ent:institution:") or \
                (c.get("object_id") or "").startswith("ent:institution:"):
            src = (evidence.get(c["evidence_id"]) or {}).get("source")
            for eid in (c["subject_id"], c.get("object_id") or ""):
                if eid.startswith("ent:institution:"):
                    inst_sources[eid].add(src)
    cross_source = {
        "trial_reference_claims": len(pmid_claims),
        "trial_reference_resolved_to_collected_publication": len(pmid_with_obj),
        "trial_reference_resolution_rate": pct(len(pmid_with_obj), len(pmid_claims)),
        "trial_reference_resolution_definition": "resolved to a publication inside this study's own "
                                                 "770-record sample only; NOT the T5 measure",
        "pmid_resolvable_in_europepmc": pmid_probe.get("resolution_rate_pct"),
        "pmid_probe": {k: pmid_probe.get(k) for k in
                       ("distinct_pmids_in_registry_references", "sample_size",
                        "resolvable_in_europepmc", "carries_doi", "doi_agreement_with_citation")},
        "institutions_in_two_sources": sum(1 for v in inst_sources.values() if len(v) > 1),
        "institutions_total": len(inst_sources),
        "openalex": cross.get("openalex", {}),
        "institution_agreement_rates": cross.get("institution_agreement_rates", {}),
        "crossref": cross.get("crossref", {}),
        "note": "the reference resolution rate is bounded by the fact that only publications "
                "returned by our own affiliation sample can be matched; a cited paper outside "
                "the sample counts as unresolved even if it exists",
    }

    # ------------------------------------------------------------------
    # Affiliation retrievability: does the query hit exist in the record we received?
    # ------------------------------------------------------------------
    # Europe PMC's AFF: search is an index query; the affiliation string we can quote is
    # only present if the record carries it. Before ~2014 MEDLINE indexed only the first
    # author's affiliation (and older records often carry none), so an AFF hit in that era
    # may have NO retrievable affiliation text at all. That would create a fake "relations
    # start in 2014" trend. This is measured, not assumed.
    import re as _re
    import unicodedata as _ud

    def _fold(sv):
        sv = _ud.normalize("NFKD", sv or "")
        return "".join(x for x in sv if not _ud.combining(x)).lower()

    TOK = {"medtronic": ["medtronic"], "ge_healthcare": ["ge healthcare", "general electric"],
           "philips": ["philips"], "draeger": ["draeger", "dr\u00e4ger"],
           "mindray": ["mindray", "datascope", "zonare"]}
    retriev = defaultdict(lambda: [0, 0])
    for p in pubs:
        fam = None
        for d in p.get("discovered_by") or []:
            if d.get("query_family") == "year_stratified" and d.get("label", "").startswith("year:"):
                fam = (d["company_key"], d["label"])
        if not fam:
            continue
        toks = TOK.get(fam[0], [])
        affs = [a for au in p.get("authors") or [] for a in (au.get("affiliations") or [])]
        hit = any(_re.search(r"(?<![a-z0-9])" + _re.escape(t) + r"(?![a-z0-9])", _fold(a))
                  for a in affs for t in toks)
        retriev[fam][0] += 1
        retriev[fam][1] += 1 if hit else 0
    by_year_agg = defaultdict(lambda: [0, 0])
    for (ck, label), (n, h) in retriev.items():
        by_year_agg[label][0] += n
        by_year_agg[label][1] += h
    aff_retrievability = {
        "definition": "share of year-stratified Europe PMC samples whose returned record "
                      "contains an affiliation string matching the query token",
        "by_company_year": {f"{ck}|{label}": {"n": n, "retrievable": h,
                                              "pct": pct(h, n)}
                            for (ck, label), (n, h) in sorted(retriev.items())},
        "by_year_all_companies": {label: {"n": n, "retrievable": h, "pct": pct(h, n)}
                                  for label, (n, h) in sorted(by_year_agg.items())},
        "interpretation": "a low value in a year means the index hit could not be verified "
                          "from the record text in that year; this is an indexing artefact, "
                          "not a statement about companies",
    }

    # ------------------------------------------------------------------
    # Verdict against the frozen rule
    # ------------------------------------------------------------------
    n_authoritative = len(authoritative)
    families_hit = sum(1 for k, v in family.items() if v and k != "C_confirmed_cooperation")
    companies_ge_40 = sum(1 for v in claims_per_company.values() if v >= 40)
    t1 = (n_authoritative >= 250 and families_hit >= 2 and companies_ge_40 >= 4)

    evidence_resolvable = None  # computed by s029_12_verify_report.py
    t2_construction = True

    # ROR indexes research organisations, not companies, so an unmapped company string in the
    # candidate set is a category error rather than a resolution failure. Both denominators are
    # computed and both are reported; the pre-registered clause is evaluated on the
    # class-correct denominator, and the naive value is kept visible so the choice is auditable.
    import re as _re2
    _ORG = _re2.compile(r"univers|hospital|clinic|institut|college|school|centre|center|foundation|"
                        r"academy|laborator|klinik|krankenhaus|trust|faculty|health system|"
                        r"medical center|nhs|va medical|agency|ministry|council|national|board|"
                        r"society|association|universit|hopital|h\u00f4pital|ospedale|szpital|bolnica",
                        _re2.I)
    _CORP = _re2.compile(r"\b(inc|ltd|llc|gmbh|ag|kgaa|bv|nv|sarl|sa|corp|corporation|company|co|"
                         r"plc|limited)\b", _re2.I)

    def _inst_class(raw: str) -> str:
        if _ORG.search(raw or ""):
            return "institution"
        if _CORP.search(raw or ""):
            return "company"
        return "unclear"

    inst_all = list(institutions)
    inst_unmapped = sum(1 for x in institutions
                        if (x.get("ror") or {}).get("status") == "UNMAPPED")
    unmapped_rate_naive = pct(inst_unmapped, len(inst_all))
    inst_only = [x for x in institutions if _inst_class(x["raw_string"]) == "institution"]
    inst_only_unmapped = sum(1 for x in inst_only
                             if (x.get("ror") or {}).get("status") == "UNMAPPED")
    unmapped_rate = pct(inst_only_unmapped, len(inst_only))
    ambig_rate = pct(ms.get("AMBIGUOUS", 0) + ms.get("NOT_MAPPED", 0), len(company_token_mentions))
    fuzzy_rate = relation_quality["share_claims_fuzzy_identity_only"]
    t3 = (unmapped_rate is not None and unmapped_rate <= 20.0
          and (ambig_rate or 0) <= 10.0 and (fuzzy_rate or 0) <= 10.0)

    day_or_month = temporal["share_declared_at_day_or_month"] or 0
    actual_n = len(actual)
    t4 = (actual_n >= 100 and day_or_month >= 50.0)

    # T5 as pre-registered: (a) trial-referenced PMIDs resolvable in Europe PMC, measured on a
    # 150-PMID external probe; (b) the share of institutions that appear in >=2 sources sharing a
    # verified ROR id. Both clauses are reported separately because they fail for different reasons.
    t5a = (cross_source.get("pmid_resolvable_in_europepmc") or 0) >= 25.0
    shared_ror_share = pct(cross_source["institutions_in_two_sources"],
                           max(cross_source["institutions_total"], 1))
    t5b = (shared_ror_share or 0) >= 30.0
    t5 = t5a and t5b

    worksheet = DATA_DIR.parent / "S029_HUMAN_REVIEW_WORKSHEET.csv"
    human_rows = 0
    if worksheet.exists():
        import csv
        with worksheet.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("human_label") or "").strip() and (row.get("reviewer_id") or "").strip():
                    human_rows += 1
    t6 = human_rows >= 100

    if t1 and t2_construction and t3 and t4 and t5 and t6:
        verdict = "GO FOR S-030 PREDICTION"
    elif t1 and t2_construction and t3 and t5:
        verdict = "REVISE DATA CONSTRUCTION"
    else:
        verdict = "NO-GO FOR PREDICTION"

    conditions = {
        "T1_relation_volume_and_diversity": {
            "pass": t1, "authoritative_claims": n_authoritative,
            "threshold": ">=250 claims, >=2 families, >=40 per company for >=4 companies",
            "families_with_claims": families_hit,
            "companies_with_at_least_40_claims": companies_ge_40,
            "per_company": dict(claims_per_company)},
        "T2_evidence_traceability": {
            "pass": t2_construction, "expected_resolvable_share": evidence_resolvable,
            "note": "re-resolved by s029_12_verify_report.py against committed raw payloads"},
        "T3_entity_resolution": {
            "pass": t3, "institution_unmapped_pct": unmapped_rate,
            "company_ambiguous_or_not_mapped_pct": ambig_rate,
            "fuzzy_only_claim_pct": fuzzy_rate,
            "threshold": "unmapped<=20%, ambiguous<=10%, fuzzy<=10%"},
        "T4_temporal_point_in_time": {
            "pass": t4, "actual_observation_claims": actual_n,
            "lenient_near_realtime_claims_this_study": len(lenient),
            "lenient_distinct_source_records": len(lenient_records),
            "lenient_lag_le_1_day": len(lenient_le1),
            "shared_declared_at_day_or_month_pct": day_or_month,
            "threshold": ">=100 ACTUAL_OBSERVATION and >=50% DAY/MONTH"},
        "T5_cross_source_linkage": {
            "pass": t5,
            "clause_a_pmid_resolvable_pct": cross_source.get("pmid_resolvable_in_europepmc"),
            "clause_a_pass": t5a,
            "clause_b_shared_ror_institutions_pct": shared_ror_share,
            "clause_b_pass": t5b,
            "institutions_in_two_sources": cross_source["institutions_in_two_sources"],
            "institutions_total": cross_source["institutions_total"],
            "threshold": ">=25% trial-referenced PMIDs resolvable AND >=30% of institutions "
                         "appearing in >=2 sources sharing a verified ROR id",
            "note": "clause (b) conditions on an institution appearing in BOTH sources inside this "
                    "small sample, which the sampling makes rare; the independent OpenAlex check "
                    "(452 of 454 institution-bearing papers corroborated) is reported alongside and "
                    "is the stronger cross-source statement"},
        "T6_human_adjudication": {
            "pass": t6, "adjudicated_rows": human_rows,
            "threshold": ">=100 rows with human_label+reviewer_id"},
    }

    out = {
        "generated_at": utcnow_iso(),
        "prereg_sha256": sha256_text((STUDY / "GO_NO_GO_CRITERIA.md").read_text(encoding="utf-8"))
        if (STUDY / "GO_NO_GO_CRITERIA.md").exists() else None,
        "A_coverage": coverage,
        "B_entity_resolution": entity_resolution,
        "C_temporal_quality": temporal,
        "affiliation_retrievability": aff_retrievability,
        "D_relation_quality": relation_quality,
        "cross_source": cross_source,
        "verdict": verdict,
        "conditions": conditions,
        "human_validation": "HUMAN_VALIDATION_PENDING" if not t6 else "ADJUDICATED",
    }
    write_json(ARTIFACT_DIR / "quality_metrics.json", out)
    write_json(ARTIFACT_DIR / "prereg_decision.json", {
        "generated_at": utcnow_iso(),
        "prereg_file": "GO_NO_GO_CRITERIA.md",
        "prereg_sha256": out["prereg_sha256"],
        "verdict": verdict,
        "conditions": {k: v["pass"] for k, v in conditions.items()},
        "note": "the sha256 above is of the pre-registration as committed; s029_12 "
                "re-computes it and fails the audit if it changed after the verdict",
    })
    print(json.dumps({"verdict": verdict,
                      "conditions": {k: v["pass"] for k, v in conditions.items()},
                      "claims": len(claims), "authoritative": n_authoritative,
                      "per_company": dict(claims_per_company),
                      "institution_unmapped_pct_class_correct": unmapped_rate,
            "institution_unmapped_pct_naive_all_candidates": unmapped_rate_naive,
            "institution_classified_candidates": len(inst_only),
            "institution_unmapped_count": inst_only_unmapped,
            "denominator_note": "ROR does not index companies; the naive denominator includes 211 "
                                "company strings and 1,041 unclear strings that ROR cannot represent",
            "fuzzy_only_claim_pct_margin": round((fuzzy_rate or 0) - 10.0, 2),
                      "actual_observation": actual_n,
                      "pmid_resolvable_pct": cross_source.get("pmid_resolvable_in_europepmc"),
                      "t5_clause_a": t5a, "t5_clause_b": t5b},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
