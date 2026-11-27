"""Step 2 — CIPO ETL: firm-scoped patent records from the open bulk CSVs.

Strategy (deliberately cheap on memory and honest about what it selects):

1. Scan ``PT_Interested_Party`` once per range file and keep only rows whose
   ``Party Name`` matches a **documented** alias of one of the five target firms.
   That yields the candidate patent-number set.
2. Scan ``PT_Main`` / ``PT_IPC_Classification`` / ``PT_Priority_Claim`` keeping
   only rows for that set.
3. Emit ``horizon.evidence.v1`` records.

A name-fragment match is **not** an identity proof. Every firm attribution is
emitted as ``identity_status = CANDIDATE`` with an explicit
``applicant_group_candidate`` relation naming the alias that fired, so ATLAS-001
can accept or reject it with its own rules. The raw party name is always kept.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import cipo_canada as C  # noqa: E402
from hz.schema import write_jsonl  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

# The CIPO party table contains at least one very long field (concatenated
# address block); the csv module's 128 KiB default raises. Raise the parser
# limit rather than truncating evidence.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

RAW = os.path.join(ROOT, "DATASETS", "patents", "cipo_canada", "raw")
OUT = os.path.join(ROOT, "DATASETS", "patents", "cipo_canada")

# Documented alias -> firm. Each alias carries the reason it is believed to map.
# These are *candidate* attributions by construction: they say "this applicant
# name is a plausible member of the group", not "this patent belongs to X".
FIRM_ALIASES: dict[str, list[tuple[str, str]]] = {
    "Medtronic": [
        ("MEDTRONIC", "canonical name"),
        ("COVIDIEN", "Medtronic subsidiary (acquired 2015)"),
        ("ST. JUDE", "St. Jude Medical, Medtronic subsidiary (acquired 2017)"),
        ("ST JUDE", "St. Jude Medical, Medtronic subsidiary (acquired 2017)"),
        ("KANGHUI", "Medtronic subsidiary (acquired 2012)"),
        ("TYCO HEALTHCARE", "predecessor entity of Covidien, later Medtronic"),
        ("ARTERIAL VASCULAR", "acquired by Medtronic (1999)"),
    ],
    "GE HealthCare": [
        ("GE HEALTHCARE", "canonical name"),
        ("GE MEDICAL SYSTEMS", "GE HealthCare predecessor name"),
        ("GENERAL ELECTRIC MEDICAL", "GE HealthCare predecessor name"),
        ("DATEX-OHMEDA", "GE Medical Systems subsidiary"),
        ("DATEX OHMEDA", "GE Medical Systems subsidiary"),
        ("OHMEDA", "GE Medical Systems subsidiary"),
        ("INSTRUMENTARIUM", "GE Medical Systems subsidiary (acquired 2003)"),
    ],
    "Philips": [
        ("PHILIPS", "canonical name"),
        ("RESPIRONICS", "Philips subsidiary (acquired 2008)"),
        ("VOLCANO", "Volcano Corporation, Philips subsidiary (acquired 2015)"),
        ("SPECTRANETICS", "Spectranetics, Philips subsidiary (acquired 2017)"),
    ],
    "Draeger": [
        ("DRAGER", "ASCII rendering of Dräger"),
        ("DRAEGER", "ASCII rendering of Dräger"),
        ("DRÄGER", "canonical name (umlaut)"),
        ("DRAGERWERK", "canonical legal name"),
        ("DRÄGERWERK", "canonical legal name (umlaut)"),
    ],
    "Mindray": [
        ("MINDRAY", "canonical name"),
    ],
}


def norm_header(h: str) -> str:
    """Normalise a bilingual CIPO header to an ASCII key.

    'Patent Number - Numéro du brevet' -> 'patentnumber'
    """
    en = C.english_header(h)
    return re.sub(r"[^a-z0-9]+", "", (en or "").lower())


HEADER_KEYS = {
    "patent_number": ["patentnumber"],
    "party_name": ["partyname"],
    "party_type": ["interestedpartytype"],
    "enable_date": ["ownerenabledate"],
    "end_date": ["ownershipenddate"],
    "party_country": ["partycountrycode"],
    "filing_date": ["fillingdate", "filingdate"],
    "grant_date": ["grantdate"],
    "status_code": ["applicationstatuscode"],
    "app_type_code": ["applicationtypecode"],
    "title_en": ["applicationpatenttitleenglish", "applicationtitleenglish"],
    "title_fr": ["applicationpatenttitlefrench", "applicationtitlefrench"],
    "extract_date": ["bibliographicfileextractdate"],
    "pub_country": ["countryofpublicationcode"],
    "doc_kind": ["documentkindtype"],
    "exam_request_date": ["examinationrequestdate"],
    "filing_country": ["fillingcountrycode", "filingcountrycode"],
    "filing_lang": ["languageoffilingcode"],
    "pct_app": ["pctapplicationnumber"],
    "pct_pub": ["pctpublicationnumber"],
    "pct_pub_date": ["pctpublicationdate"],
    "parent_app": ["parentapplicationnumber"],
    "pub_kind": ["publicationkindtype"],
    "ipc_section": ["ipcsectioncode"],
    "ipc_class": ["ipcclasscode"],
    "ipc_subclass": ["ipcsubclasscode"],
    "ipc_group": ["ipcmaingroupcode", "ipcgroupcode"],
    "ipc_subgroup": ["ipcsubgroupcode"],
    "prio_number": ["foreignapplicationpatentnumber", "foreignapplicationnumber"],
    "prio_country": ["priorityclaimcountrycode"],
    "prio_country_name": ["priorityclaimcountry"],
    "prio_date": ["priorityclaimcalendardt"],
    "prio_kind": ["priorityclaimkindcode"],
}


def resolve_headers(fieldnames: list[str]) -> dict[str, str]:
    norm = {norm_header(h): h for h in fieldnames if h}
    out: dict[str, str] = {}
    for key, cands in HEADER_KEYS.items():
        for cand in cands:
            if cand in norm:
                out[key] = norm[cand]
                break
    return out


def rows_of(path: str):
    """Yield (header map, row) with the pipe delimiter already handled."""
    with C.open_csv(path) as fh:
        delim = C.sniff_delimiter(path)
        reader = csv.DictReader(fh, delimiter=delim)
        hmap = resolve_headers([C.english_header(h) for h in (reader.fieldnames or [])])
        for row in reader:
            yield hmap, {(C.english_header(k) if k else k): v for k, v in row.items()}


def g(row: dict, hmap: dict, key: str):
    col = hmap.get(key)
    return row.get(col) if col else None


def compile_alias_patterns():
    pats = []
    for firm, aliases in FIRM_ALIASES.items():
        for alias, basis in aliases:
            pats.append((firm, alias, basis, re.compile(re.escape(alias), re.IGNORECASE)))
    return pats


def main() -> int:
    t0 = time.time()
    prov_path = os.path.join(RAW, "PROVENANCE.json")
    prov = json.load(open(prov_path, encoding="utf-8"))
    files = {f["table"]: [] for f in prov["files"]}
    for f in prov["files"]:
        files.setdefault(f["table"], []).append(os.path.join(RAW, f["file"]))

    pats = compile_alias_patterns()
    print(f"alias patterns: {len(pats)}")

    # ---- pass 1: interested parties -------------------------------------
    party_by_patent: dict[str, list[dict]] = defaultdict(list)
    alias_hits: dict[str, set] = defaultdict(set)
    scanned = 0
    for path in files.get("PT_interested_party", []):
        print("scan party:", os.path.basename(path))
        for hmap, row in rows_of(path):
            scanned += 1
            name = g(row, hmap, "party_name") or ""
            if not name:
                continue
            hit = None
            for firm, alias, basis, rx in pats:
                if rx.search(name):
                    hit = (firm, alias, basis)
                    break
            if not hit:
                continue
            pn = C._norm_num(g(row, hmap, "patent_number"))
            if not pn:
                continue
            firm, alias, basis = hit
            alias_hits[alias].add(pn)
            party_by_patent[pn].append(
                {
                    "party_name": name,
                    "party_type": (g(row, hmap, "party_type") or "").strip(),
                    "enable_date": C._iso(g(row, hmap, "enable_date")),
                    "end_date": C._iso(g(row, hmap, "end_date")),
                    "country": (g(row, hmap, "party_country") or "").strip() or None,
                    "matched_firm": firm,
                    "matched_alias": alias,
                    "match_basis": basis,
                }
            )
            if scanned % 500000 == 0:
                print(f"  rows={scanned} matched_patents={len(party_by_patent)}")
    print(f"party rows scanned={scanned} matched patents={len(party_by_patent)}")

    target = set(party_by_patent)

    # ---- pass 2: main ---------------------------------------------------
    main_rows: dict[str, dict] = {}
    for path in files.get("PT_main", []):
        print("scan main:", os.path.basename(path))
        for hmap, row in rows_of(path):
            pn = C._norm_num(g(row, hmap, "patent_number"))
            if pn in target and pn not in main_rows:
                main_rows[pn] = {
                    "patent_number": pn,
                    "filing_date": C._iso(g(row, hmap, "filing_date")),
                    "grant_date": C._iso(g(row, hmap, "grant_date")),
                    "status_code": (g(row, hmap, "status_code") or "").strip() or None,
                    "app_type_code": (g(row, hmap, "app_type_code") or "").strip() or None,
                    "title_en": (g(row, hmap, "title_en") or "").strip() or None,
                    "title_fr": (g(row, hmap, "title_fr") or "").strip() or None,
                    "extract_date": C._iso(g(row, hmap, "extract_date")),
                    "pub_country": (g(row, hmap, "pub_country") or "").strip() or None,
                    "doc_kind": (g(row, hmap, "doc_kind") or "").strip() or None,
                    "exam_request_date": C._iso(g(row, hmap, "exam_request_date")),
                    "filing_country": (g(row, hmap, "filing_country") or "").strip() or None,
                    "filing_lang": (g(row, hmap, "filing_lang") or "").strip() or None,
                    "pct_app": (g(row, hmap, "pct_app") or "").strip() or None,
                    "pct_pub": (g(row, hmap, "pct_pub") or "").strip() or None,
                    "pct_pub_date": C._iso(g(row, hmap, "pct_pub_date")),
                    "parent_app": (g(row, hmap, "parent_app") or "").strip() or None,
                    "pub_kind": (g(row, hmap, "pub_kind") or "").strip() or None,
                }
    print(f"main rows matched={len(main_rows)}")

    # ---- pass 3: IPC ----------------------------------------------------
    ipc_by_patent: dict[str, list[dict]] = defaultdict(list)
    for path in files.get("PT_IPC_classification", []):
        print("scan ipc:", os.path.basename(path))
        for hmap, row in rows_of(path):
            pn = C._norm_num(g(row, hmap, "patent_number"))
            if pn in target:
                ipc_by_patent[pn].append(
                    {
                        "section": (g(row, hmap, "ipc_section") or "").strip(),
                        "class": (g(row, hmap, "ipc_class") or "").strip(),
                        "subclass": (g(row, hmap, "ipc_subclass") or "").strip(),
                        "group": (g(row, hmap, "ipc_group") or "").strip(),
                        "subgroup": (g(row, hmap, "ipc_subgroup") or "").strip(),
                    }
                )
    print(f"ipc patents matched={len(ipc_by_patent)}")

    # ---- pass 4: priority claims ---------------------------------------
    prio_by_patent: dict[str, list[dict]] = defaultdict(list)
    for path in files.get("PT_priority_claim", []):
        print("scan priority:", os.path.basename(path))
        for hmap, row in rows_of(path):
            pn = C._norm_num(g(row, hmap, "patent_number"))
            if pn in target:
                prio_by_patent[pn].append(
                    {
                        "number": (g(row, hmap, "prio_number") or "").strip() or None,
                        "country": (g(row, hmap, "prio_country") or "").strip() or None,
                        "country_name": (g(row, hmap, "prio_country_name") or "").strip() or None,
                        "date": C._iso(g(row, hmap, "prio_date")),
                        "kind": (g(row, hmap, "prio_kind") or "").strip() or None,
                    }
                )
    print(f"priority patents matched={len(prio_by_patent)}")

    # ---- assemble -------------------------------------------------------
    fetched = now_utc()
    records = []
    skipped_no_main = 0
    for pn in sorted(target):
        m = main_rows.get(pn)
        if not m:
            skipped_no_main += 1
            continue
        parties = party_by_patent[pn]
        ipc_rows = ipc_by_patent.get(pn, [])
        ipc_codes = C.ipc_full(ipc_rows)
        ipc_subs = []
        for r in ipc_rows:
            sc = (r["subclass"] or "")
            if len(sc) >= 4:
                sc = sc[:4].upper()
                if re.match(r"^[A-H]\d\d[A-Z]$", sc) and sc not in ipc_subs:
                    ipc_subs.append(sc)
        rec = C.to_record(
            C.MainRow(**m),
            [C.PartyRow(
                patent_number=pn,
                party_name=p["party_name"],
                party_type=p["party_type"],
                enable_date=p["enable_date"],
                end_date=p["end_date"],
                country=p["country"],
            ) for p in parties],
            ipc_subs,
            ipc_codes,
            prio_by_patent.get(pn, []),
            fetched,
        )
        # candidate firm attribution, explicitly not an identity claim
        attributed = sorted({p["matched_firm"] for p in parties})
        rec["attributes"]["firm_group_candidates"] = attributed
        rec["attributes"]["alias_matches"] = sorted(
            {(p["matched_firm"], p["matched_alias"]) for p in parties}
        )
        if attributed:
            rec["identity_status"] = "CANDIDATE"
            for firm in attributed:
                rec["relations"].append(
                    {
                        "type": "applicant_group_candidate",
                        "firm": firm,
                        "basis": "party_name_fragment_match",
                        "status": "CANDIDATE",
                        "note": "candidate attribution only; not an identity proof",
                    }
                )
        records.append(rec)

    out_jsonl = os.path.join(OUT, "RECORDS.raw.jsonl")
    write_jsonl(out_jsonl, records)

    summary = {
        "source_id": C.SOURCE_ID,
        "generated_at": fetched,
        "party_rows_scanned": scanned,
        "matched_patents": len(target),
        "patents_with_main_row": len(main_rows),
        "patents_without_main_row": skipped_no_main,
        "patents_with_ipc": len(ipc_by_patent),
        "patents_with_priority": len(prio_by_patent),
        "records_written": len(records),
        "by_firm": {f: sorted(alias_hits.get(a, set()), key=str)[:5] and len(alias_hits.get(a, set()))
                    for f in FIRM_ALIASES for a, _ in FIRM_ALIASES[f]},
        "by_firm_total_patents": {
            firm: len({pn for alias, _ in FIRM_ALIASES[firm] for pn in alias_hits.get(alias, set())})
            for firm in FIRM_ALIASES
        },
        "alias_hit_counts": {a: len(v) for a, v in sorted(alias_hits.items())},
        "elapsed_s": round(time.time() - t0, 1),
        "licence": C.LICENCE_NAME,
        "coverage": C.COVERAGE_NOTE,
    }
    with open(os.path.join(OUT, "ETL_SUMMARY.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({k: summary[k] for k in (
        "matched_patents", "patents_with_main_row", "patents_with_ipc",
        "patents_with_priority", "records_written", "by_firm_total_patents", "elapsed_s")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
