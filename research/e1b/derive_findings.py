#!/usr/bin/env python3
"""Derive E1b findings from the collected evidence (no network).

Reads retrospective.json / prospective.json / collection.jsonl and writes
findings.json with per-source, machine-readable verdicts used by the memo.
"""
import json
import os
import statistics
from datetime import date

E = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                 "docs", "refoundation", "phase2", "_evidence", "e1b")


def load(name):
    with open(os.path.join(E, name), encoding="utf-8") as fh:
        return json.load(fh)


def d(s):
    return date.fromisoformat(s[:10]) if s else None


def lag(a, b):
    if not a or not b:
        return None
    return (d(b) - d(a)).days


retro = load("retrospective.json")
prosp = load("prospective.json")
summ = load("summary.json")
coll = [json.loads(l) for l in open(os.path.join(E, "collection.jsonl"), encoding="utf-8")]

of = retro["sources"]["openfda_device"]
cg = retro["sources"]["clinicaltrials_gov"]
ed = retro["sources"]["sec_edgar"]

of_findings = {"510k": [], "pma": []}
for key, kind in (("samples", "510k"), ("pma_samples", "pma")):
    for x in of[key]:
        of_findings[kind].append({
            "record_id": x["record_id"],
            "decision_date": x["event_date"],
            "date_received": x["date_received"],
            "received_to_decision_days": lag(x["date_received"], x["event_date"]),
            "applicant": x["applicant"],
        })
lags = [r["received_to_decision_days"] for k in of_findings
        for r in of_findings[k] if r["received_to_decision_days"] is not None]

cg_findings = []
for x in cg["samples"]:
    cg_findings.append({
        **x,
        "submit_to_post_days": lag(x["first_submit_date"], x["first_public_date"]),
        "post_to_last_update_days": lag(x["first_public_date"], x["last_public_update"]),
        "estimated_type": x["first_public_date_type"] != "ACTUAL",
    })

ed_findings = []
for f in ed["samples"]:
    lm = f["primary_doc"].get("last_modified")
    delta = None
    if lm and f.get("acceptance_datetime_utc"):
        from email.utils import parsedate_to_datetime
        try:
            lm_dt = parsedate_to_datetime(lm)
            acc_dt = __import__("datetime").datetime.fromisoformat(
                f["acceptance_datetime_utc"].replace("Z", "+00:00"))
            delta = (lm_dt - acc_dt).total_seconds()
        except Exception:
            delta = None
    ed_findings.append({
        "accession_number": f["accession_number"],
        "form": f["form"],
        "filing_date": f["filing_date"],
        "acceptance_datetime_utc": f["acceptance_datetime_utc"],
        "report_date": f["report_date"],
        "report_to_acceptance_days": lag(f["report_date"], f["acceptance_datetime_utc"]),
        "primary_doc_sha256": f["primary_doc"]["sha256"],
        "last_modified": lm,
        "acceptance_to_last_modified_seconds": delta,
        "refetch_identical": f["refetch"]["identical_to_first"],
    })

findings = {
    "generated_from": ["retrospective.json", "prospective.json", "collection.jsonl"],
    "requests_total": len(coll),
    "requests_by_status": {str(s): sum(1 for r in coll if r.get("status") == s)
                           for s in sorted({r.get("status") for r in coll},
                                           key=lambda x: (x is None, x))},
    "openfda_device": {
        "event_date_field": "decision_date",
        "second_event_field": "date_received",
        "first_public_field": None,
        "first_public_basis": "UNKNOWN — no public-posting date is exposed by /device/510k or /device/pma",
        "dataset_last_updated": of.get("dataset_last_updated"),
        "received_to_decision_days": {
            "n": len(lags), "min": min(lags) if lags else None,
            "median": statistics.median(lags) if lags else None,
            "max": max(lags) if lags else None},
        "revision_visibility": "NONE per record (no version/history endpoint)",
        "refetch": {"http_status": summ["per_source"]["openfda_device"]["refetch"][0]["http_status"]
                    if summ["per_source"]["openfda_device"]["refetch"] else None,
                    "identical_hashes": len({r["sha256"] for r in
                                             summ["per_source"]["openfda_device"]["refetch"]}) == 1,
                    "sha256": summ["per_source"]["openfda_device"]["refetch"][0]["sha256"]
                    if summ["per_source"]["openfda_device"]["refetch"] else None},
        "identity_signal": "applicant string + product_code; no registrant id; PMA ids include N-numbers and supplements",
        "records": of_findings,
    },
    "clinicaltrials_gov": {
        "event_date_field": "statusModule.startDateStruct.date",
        "first_public_field": "statusModule.studyFirstPostDateStruct.date (+ .type ACTUAL|ESTIMATED)",
        "supporting_fields": ["studyFirstSubmitDate", "studyFirstSubmitQcDate",
                              "lastUpdatePostDateStruct", "lastUpdateSubmitDate"],
        "first_post_types_in_sample": sorted({x["first_public_date_type"] for x in cg["samples"]}),
        "estimated_in_sample": sum(1 for x in cg["samples"] if x["first_public_date_type"] != "ACTUAL"),
        "revision_visibility": "lastUpdatePostDateStruct only; NO version-history API "
                               "(/history 404, /versions 404, ?history=true 400)",
        "history_probes": summ["per_source"]["clinicaltrials_gov"]["history_probes"],
        "refetch_identical": len({r["sha256"] for r in
                                  summ["per_source"]["clinicaltrials_gov"]["refetch"]}) == 1,
        "identity_signal": "NCTId (stable) + leadSponsor.name + class (name is display text)",
        "records": cg_findings,
    },
    "sec_edgar": {
        "event_date_field": "reportDate (period of reported event)",
        "first_public_field": "acceptanceDateTime (UTC instant; corroborated by HTTP Last-Modified)",
        "supporting_fields": ["filingDate (ET calendar date)", "accessionNumber"],
        "amendments_in_recent_window": ed.get("amendments_in_recent_window"),
        "recent_window_size": ed.get("recent_window_size"),
        "revision_visibility": "amendments are separate filings (8-K/A) with their own accession; "
                               "original filing remains retrievable",
        "refetch_all_identical": all(f["refetch_identical"] for f in ed_findings),
        "identity_signal": {"cik": ed.get("entity", {}).get("cik"),
                            "name": ed.get("entity", {}).get("name"),
                            "tickers": ed.get("entity", {}).get("tickers"),
                            "sic": ed.get("entity", {}).get("sic"),
                            "lei": None},
        "acceptance_minus_last_modified_seconds": None,
        "records": ed_findings,
    },
    "prospective": prosp,
}

with open(os.path.join(E, "findings.json"), "w", encoding="utf-8") as fh:
    json.dump(findings, fh, indent=1, ensure_ascii=False)
print("wrote findings.json")
print("openFDA lag days:", findings["openfda_device"]["received_to_decision_days"])
print("CT.gov estimate count:", findings["clinicaltrials_gov"]["estimated_in_sample"])
print("EDGAR refetch all identical:", findings["sec_edgar"]["refetch_all_identical"])
print("EDGAR amendments in window:", findings["sec_edgar"]["amendments_in_recent_window"])
