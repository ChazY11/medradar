#!/usr/bin/env python3
"""E1b source-recovery experiment — openFDA / ClinicalTrials.gov / SEC EDGAR.

Small sample only (5–10 records per source, one page each). Respects terms:
  * openFDA  : public domain / CC0; documented API; no key needed for low volume.
  * CT.gov   : public domain; v2 API, pageSize<=10 here.
  * SEC EDGAR: public filings; real User-Agent with contact, <=10 req/s (we sleep).

Produces, under --out:
  collection.jsonl     one line per HTTP request (true collection timestamps)
  retrospective.json   public-availability fields recoverable from the sources
  prospective.json     observation record starting NOW (never back-dated)
  summary.json         machine-readable per-source verdicts

Key discipline:
  * `event_date` (what happened) and `first_public_*` (when the world could know)
    are separate fields, populated only from source-provided fields.
  * `first_observed_at_utc` is the time WE fetched it. It is never used as a
    proxy for first-public. The two live in different files on purpose.
  * anything the source does not provide is null + an explicit `basis` marker
    (unknown / unverifiable / not_applicable).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "MedRadar-research (" + os.environ.get("MEDRADAR_CONTACT", "https://github.com/ChazY11/medradar") + ")"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def fetch(url: str, accept: str = "application/json", timeout: int = 45) -> dict:
    """One polite GET; returns body bytes + full provenance for the log."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    rec = {"url": url, "fetched_at_utc": now_utc(), "accept": accept}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            hd = dict(r.headers)
            rec.update({"status": r.status, "bytes": len(body),
                        "sha256": hashlib.sha256(body).hexdigest()})
    except urllib.error.HTTPError as e:
        body = e.read()
        hd = dict(e.headers)
        rec.update({"status": e.code, "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "error": "HTTPError"})
    except Exception as e:  # noqa: BLE001
        body, hd = b"", {}
        rec.update({"status": None, "bytes": 0, "sha256": None, "error": repr(e)})
    rec["response_headers"] = {k: hd.get(k) for k in
                               ("Date", "Last-Modified", "ETag", "Content-Type")}
    rec["body"] = body
    return rec


def log(records: list, entry: dict, purpose: str, record_id: str | None = None) -> None:
    row = {k: v for k, v in entry.items() if k != "body"}
    row["purpose"] = purpose
    row["record_id"] = record_id
    records.append(row)


# --------------------------------------------------------------------------- #
# openFDA
# --------------------------------------------------------------------------- #

def openfda(records: list, out_dir: str, n: int) -> dict:
    base = "https://api.fda.gov/device/{}.json"
    res = {}
    for kind, search, id_field in [
        ("510k", 'decision_date:[2024-01-01+TO+2024-12-31]', "k_number"),
        ("pma", 'decision_date:[2024-01-01+TO+2024-12-31]', "pma_number"),
    ]:
        url = f"{base.format(kind)}?search={search}&limit={n}"
        r = fetch(url)
        log(records, r, f"openfda/{kind} list page 1")
        samples, meta = [], {}
        if r["status"] == 200:
            j = json.loads(r["body"])
            meta = j.get("meta", {})
            for rec in j.get("results", [])[:n]:
                samples.append({
                    "record_id": rec.get(id_field),
                    "event_date": rec.get("decision_date"),
                    "date_received": rec.get("date_received"),
                    "applicant": rec.get("applicant"),
                    "product_code": rec.get("product_code"),
                    "decision_code": rec.get("decision_code"),
                    "device_name": rec.get("device_name"),
                })
        # re-fetch ONE record by its stable id, twice, to test re-fetchability
        refetch = []
        if samples:
            rid = samples[0]["record_id"]
            single = f"{base.format(kind)}?search={id_field}:{rid}&limit=1"
            for attempt in (1, 2):
                time.sleep(0.4)
                r2 = fetch(single)
                log(records, r2, f"openfda/{kind} refetch attempt {attempt}", rid)
                refetch.append({"http_status": r2["status"], "sha256": r2["sha256"],
                                "bytes": r2["bytes"],
                                "fetched_at_utc": r2["fetched_at_utc"]})
        res[kind] = {
            "endpoint": base.format(kind),
            "sample_size": len(samples),
            "dataset_meta": {"last_updated": meta.get("last_updated"),
                             "terms": meta.get("terms")},
            "samples": samples,
            "refetch": refetch,
            "revision_endpoint": "none — openFDA exposes no per-record version/history API",
        }
        time.sleep(0.4)
    return res


# --------------------------------------------------------------------------- #
# ClinicalTrials.gov v2
# --------------------------------------------------------------------------- #

def ctgov(records: list, out_dir: str, n: int) -> dict:
    url = ("https://clinicaltrials.gov/api/v2/studies?pageSize="
           f"{min(n, 10)}&sort=LastUpdatePostDate:desc")
    r = fetch(url)
    log(records, r, "ctgov studies page 1")
    samples, nct = [], None
    if r["status"] == 200:
        j = json.loads(r["body"])
        for s in j.get("studies", [])[:n]:
            ps = s.get("protocolSection", {})
            idm = ps.get("identificationModule", {})
            sm = ps.get("statusModule", {})
            spon = ps.get("sponsorCollaboratorsModule", {})
            samples.append({
                "record_id": idm.get("nctId"),
                "brief_title": idm.get("briefTitle"),
                "event_date_start": (sm.get("startDateStruct") or {}).get("date"),
                "first_public_date": (sm.get("studyFirstPostDateStruct") or {}).get("date"),
                "first_public_date_type": (sm.get("studyFirstPostDateStruct") or {}).get("type"),
                "first_submit_date": sm.get("studyFirstSubmitDate"),
                "first_submit_qc_date": sm.get("studyFirstSubmitQcDate"),
                "last_public_update": (sm.get("lastUpdatePostDateStruct") or {}).get("date"),
                "last_update_submit_date": sm.get("lastUpdateSubmitDate"),
                "overall_status": sm.get("overallStatus"),
                "sponsor": ((spon.get("leadSponsor") or {}).get("name")),
                "sponsor_class": ((spon.get("leadSponsor") or {}).get("class")),
            })
            nct = nct or idm.get("nctId")
    # version-history endpoint probes (informative: proves absence, not tested blindly)
    history = {}
    if nct:
        for suffix in ("/history", "/versions", "?history=true"):
            time.sleep(0.4)
            url_h = f"https://clinicaltrials.gov/api/v2/studies/{nct}{suffix}"
            rh = fetch(url_h)
            log(records, rh, f"ctgov history probe {suffix}", nct)
            history[suffix] = {"url": url_h, "http_status": rh["status"],
                               "bytes": rh["bytes"], "sha256": rh["sha256"]}
    # re-fetch the same study twice
    refetch = []
    if nct:
        for attempt in (1, 2):
            time.sleep(0.4)
            ru = fetch(f"https://clinicaltrials.gov/api/v2/studies/{nct}")
            log(records, ru, f"ctgov refetch attempt {attempt}", nct)
            refetch.append({"http_status": ru["status"], "sha256": ru["sha256"],
                            "bytes": ru["bytes"], "fetched_at_utc": ru["fetched_at_utc"]})
    return {
        "endpoint": "https://clinicaltrials.gov/api/v2/studies",
        "sample_size": len(samples),
        "samples": samples,
        "history_endpoint_probes": history,
        "refetch": refetch,
        "revision_endpoint": ("v2 API has no public version-history endpoint; "
                              "website shows a change history but it is not machine-readable"),
    }


# --------------------------------------------------------------------------- #
# SEC EDGAR
# --------------------------------------------------------------------------- #

def edgar(records: list, out_dir: str, n: int) -> dict:
    cik = "0001613103"  # Medtronic plc — 1 issuer, small sample
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    time.sleep(0.4)
    r = fetch(url)
    log(records, r, "edgar submissions")
    out = {"cik": cik, "endpoint": url, "sample_size": 0, "filings": [],
           "amendments_seen": 0, "entity": None}
    if r["status"] != 200:
        return out
    j = json.loads(r["body"])
    out["entity"] = {"name": j.get("name"), "cik": j.get("cik"),
                     "tickers": j.get("tickers"), "sic": j.get("sic")}
    rec = j["filings"]["recent"]
    forms = rec["form"]
    out["recent_window_size"] = len(forms)
    out["amendments_seen"] = sum(1 for f in forms if f.endswith("/A"))
    idxs = [i for i, f in enumerate(forms) if f in ("8-K", "8-K/A")][:n]
    for i in idxs:
        acc = rec["accessionNumber"][i]
        nodash = acc.replace("-", "")
        primary = rec["primaryDocument"][i]
        row = {
            "accession_number": acc,
            "form": forms[i],
            "filing_date": rec["filingDate"][i],
            "acceptance_datetime_utc": rec["acceptanceDateTime"][i],
            "report_date": rec["reportDate"][i],
            "primary_document": primary,
            "archive_dir": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nodash}",
        }
        time.sleep(0.4)
        ri = fetch(f"{row['archive_dir']}/index.json")
        log(records, ri, "edgar filing index", acc)
        row["index_json"] = {"http_status": ri["status"], "sha256": ri["sha256"],
                             "bytes": ri["bytes"]}
        time.sleep(0.4)
        rp = fetch(f"{row['archive_dir']}/{primary}", accept="text/html")
        log(records, rp, "edgar primary document", acc)
        row["primary_doc"] = {"http_status": rp["status"], "sha256": rp["sha256"],
                              "bytes": rp["bytes"],
                              "last_modified": rp["response_headers"].get("Last-Modified")}
        # re-fetch primary doc once more to test immutability of the archived bytes
        time.sleep(0.4)
        rp2 = fetch(f"{row['archive_dir']}/{primary}", accept="text/html")
        log(records, rp2, "edgar primary document refetch", acc)
        row["refetch"] = {"http_status": rp2["status"], "sha256": rp2["sha256"],
                          "identical_to_first": rp2["sha256"] == rp["sha256"],
                          "fetched_at_utc": rp2["fetched_at_utc"]}
        out["filings"].append(row)
        out["sample_size"] = len(out["filings"])
    return out


# --------------------------------------------------------------------------- #
# build retrospective / prospective outputs
# --------------------------------------------------------------------------- #

def build_outputs(openfda_res, ctgov_res, edgar_res, records):
    retrospective = {
        "contract": ("what could have been PUBLIC on date D, reconstructed ONLY from "
                     "source-provided publication fields; never from event_date or "
                     "from our collection time"),
        "sources": {
            "openfda_device": {
                "event_date_field": "decision_date",
                "second_event_field": "date_received",
                "first_public_field": None,
                "first_public_basis": ("unknown — the device endpoints expose the FDA "
                                       "decision date but no public-posting date; "
                                       "dataset-level meta.last_updated only"),
                "dataset_last_updated": openfda_res["510k"]["dataset_meta"].get("last_updated"),
                "revision_visibility": "none per record; no version API",
                "samples": openfda_res["510k"]["samples"],
                "pma_samples": openfda_res["pma"]["samples"],
            },
            "clinicaltrials_gov": {
                "event_date_field": "statusModule.startDateStruct.date",
                "first_public_field": "statusModule.studyFirstPostDateStruct.date",
                "first_public_type": ("ACTUAL or ESTIMATED — ESTIMATED must NOT be "
                                      "treated as observed"),
                "supporting_fields": ["studyFirstSubmitDate", "studyFirstSubmitQcDate"],
                "revision_visibility": "lastUpdatePostDateStruct only; no version list",
                "samples": ctgov_res["samples"],
            },
            "sec_edgar": {
                "event_date_field": "reportDate (period of the reported event)",
                "first_public_field": "acceptanceDateTime (UTC timestamp)",
                "supporting_fields": ["filingDate", "accessionNumber"],
                "revision_visibility": "amendments appear as separate filings (8-K/A)",
                "amendments_in_recent_window": edgar_res.get("amendments_seen"),
                "recent_window_size": edgar_res.get("recent_window_size"),
                "entity": edgar_res.get("entity"),
                "samples": edgar_res["filings"],
            },
        },
    }
    prospective = {
        "contract": ("observation starts at the first fetch WE performed; "
                     "first_observed_at_utc is a collection timestamp and is NOT a "
                     "public-availability timestamp"),
        "sources": {},
    }
    by_req = [r for r in records if r.get("status") == 200]
    for src, key in (("openfda_device", "openfda/"), ("clinicaltrials_gov", "ctgov "),
                     ("sec_edgar", "edgar ")):
        firsts = [r for r in by_req if r["purpose"].startswith(key)]
        prospective["sources"][src] = {
            "first_observation_utc": min((r["fetched_at_utc"] for r in firsts), default=None),
            "record_count_observed": len(firsts),
            "observation_basis": "first successful fetch performed by this experiment",
            "note": "no earlier observation exists in this system for these records",
        }
    return retrospective, prospective


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/refoundation/phase2/_evidence/e1b")
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    records: list = []

    of = openfda(records, args.out, args.samples)
    cg = ctgov(records, args.out, min(args.samples, 10))
    ed = edgar(records, args.out, min(args.samples, 5))

    retro, prosp = build_outputs(of, cg, ed, records)
    summary = {
        "generated_at_utc": now_utc(),
        "samples_per_source": args.samples,
        "requests": len(records),
        "per_source": {
            "openfda_device": {"records": len(of["510k"]["samples"]) + len(of["pma"]["samples"]),
                               "refetch": of["510k"]["refetch"]},
            "clinicaltrials_gov": {"records": len(cg["samples"]),
                                   "history_probes": cg["history_endpoint_probes"],
                                   "refetch": cg["refetch"]},
            "sec_edgar": {"records": len(ed["filings"]),
                          "entity": ed.get("entity")},
        },
    }
    for name, obj in (("collection.jsonl", None), ("retrospective.json", retro),
                      ("prospective.json", prosp), ("summary.json", summary)):
        p = os.path.join(args.out, name)
        if name == "collection.jsonl":
            with open(p, "w", encoding="utf-8") as fh:
                for r in records:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        else:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, indent=1, ensure_ascii=False)
    print(f"requests={len(records)} -> {args.out}")
    print("openfda records:", len(of["510k"]["samples"]), "510k /",
          len(of["pma"]["samples"]), "pma; refetch hashes:",
          [x["sha256"][:12] for x in of["510k"]["refetch"]])
    print("ctgov records:", len(cg["samples"]), "history:",
          {k: v["http_status"] for k, v in cg["history_endpoint_probes"].items()})
    print("edgar filings:", len(ed["filings"]),
          "amendments in recent window:", ed["amendments_seen"])
    print("first-observation:", {k: v["first_observation_utc"]
                                 for k, v in prosp["sources"].items()})


if __name__ == "__main__":
    main()
