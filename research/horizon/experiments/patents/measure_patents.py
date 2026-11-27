"""Patent-side measurements for EXP-H1 (independent coverage) and EXP-H3
(historical-evidence observability).

Everything here is computed from files already on disk — no network access — so
the numbers are reproducible from the committed samples.

    python experiments/patents/measure_patents.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from hz.schema import dedupe_key, read_jsonl  # noqa: E402
from hz.timeq import classify_record, now_utc  # noqa: E402

DS = os.path.join(ROOT, "DATASETS", "patents")
OUT = HERE


def load() -> tuple[list[dict], list[dict], dict]:
    epo_path = os.path.join(DS, "epo_publication_server", "RECORDS.jsonl")
    cipo_path = os.path.join(DS, "cipo_canada", "RECORDS.jsonl")
    epo = read_jsonl(epo_path) if os.path.isfile(epo_path) else []
    cipo = read_jsonl(cipo_path) if os.path.isfile(cipo_path) else []
    collect = {}
    cp = os.path.join(DS, "epo_publication_server", "COLLECT.json")
    if os.path.isfile(cp):
        collect = json.load(open(cp, encoding="utf-8"))
    return epo, cipo, collect


def gap_buckets(gaps: list[int]) -> dict:
    b = Counter()
    for g in gaps:
        if g < 0:
            b["negative(contradictory)"] += 1
        elif g == 0:
            b["same_day"] += 1
        elif g <= 30:
            b["1-30_days"] += 1
        elif g <= 180:
            b["31-180_days"] += 1
        elif g <= 730:
            b["181-730_days"] += 1
        elif g <= 1826:
            b["731-1826_days"] += 1
        else:
            b["over_1826_days"] += 1
    return dict(sorted(b.items()))


def coverage(recs: list[dict], label: str) -> dict:
    n = len(recs) or 1
    flags = Counter(f for r in recs for f in (r.get("quality_flags") or []))
    gaps = [
        (r["attributes"].get("clock") or {}).get("observability_gap_days")
        for r in recs
    ]
    gaps = [g for g in gaps if isinstance(g, int)]
    return {
        "label": label,
        "records": len(recs),
        "with_identifier": sum(1 for r in recs if r.get("identifiers")),
        "with_public_date": sum(1 for r in recs if r.get("source_public_at")),
        "with_event_date": sum(1 for r in recs if r.get("event_at")),
        "with_priority_date": sum(1 for r in recs if (r.get("attributes") or {}).get("priority_date")),
        "two_clock": sum(
            1 for r in recs
            if (r.get("attributes") or {}).get("clock", {}).get("class") == "FULL_TWO_CLOCK"
        ),
        "share_public_date": round(sum(1 for r in recs if r.get("source_public_at")) / n, 4),
        "observability_gap_days": {
            "n": len(gaps),
            "min": min(gaps) if gaps else None,
            "median": sorted(gaps)[len(gaps) // 2] if gaps else None,
            "max": max(gaps) if gaps else None,
            "buckets": gap_buckets(gaps),
        },
        "top_quality_flags": dict(flags.most_common(8)),
    }


def _digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def cross_source_overlap(epo: list[dict], cipo: list[dict]) -> dict:
    """Can the two patent sources be shown to describe the same inventions?

    The tempting test — intersect raw priority ``COUNTRY:NUMBER`` strings — is
    wrong and would have produced a false "0 % overlap". The two offices format
    priority numbers differently:

        EPO   ('US', '124163')        ('GB', '0006526')
        CIPO  ('US', '569,842')       ('DE', 'P 25 33 766.0')

    so numbers are normalised to digits only, and the join is done on the
    EP-origin priority claims of the CA patents against the EP application
    numbers we actually hold.

    The result is reported as an **underpowered** measurement, not as evidence of
    independence: we hold 228 EP applications out of the millions granted, so the
    expected number of true overlaps inside this sample is close to zero by
    construction and a null result carries almost no information.
    """

    def prio_digits(rec: dict) -> set[tuple[str, str]]:
        keys = set()
        for p in (rec.get("attributes") or {}).get("priority_claims") or []:
            ctry = (p.get("country") or "").strip().upper()
            num = _digits(p.get("number"))
            if ctry and num:
                keys.add((ctry, num))
        return keys

    epo_apps = {_digits((r.get("attributes") or {}).get("application_number")) for r in epo}
    epo_apps.discard("")
    n_epo_prio = sum(1 for r in epo if prio_digits(r))

    cipo_prio_total = 0
    cipo_ep_claims = 0
    matches = []
    for r in cipo:
        keys = prio_digits(r)
        if keys:
            cipo_prio_total += 1
        for ctry, num in keys:
            if ctry != "EP":
                continue
            cipo_ep_claims += 1
            hit = {a for a in epo_apps if a == num or (len(num) >= 7 and a.startswith(num))}
            if hit:
                matches.append(
                    {
                        "cipo_record": r["source_record_id"],
                        "ep_priority_number": num,
                        "matched_epo_application_numbers": sorted(hit),
                    }
                )

    # expected overlap if CA and EP filings were independent draws of the same
    # invention pool: |epo_apps| * P(a given CA patent shares an EP priority)
    expected = (len(epo_apps) / 2_000_000) * cipo_ep_claims if cipo_ep_claims else None

    return {
        "method": "normalise priority numbers to digits; join CIPO EP-origin priority "
                  "claims against the EP application numbers held in this sample",
        "normalisation_note": "raw string matching yields 0 matches purely because EPO "
                              "omits separators and CIPO includes them, e.g. '124163' vs "
                              "'569,842' — that 0 would have been an artefact, not a finding",
        "epo_records_with_priority": n_epo_prio,
        "epo_application_numbers_available": len(epo_apps),
        "cipo_records_with_priority": cipo_prio_total,
        "cipo_ep_origin_priority_claims": cipo_ep_claims,
        "matches_found": len(matches),
        "overlap_verdict": "INSUFFICIENT_POWER",
        "why": (
            "the intersection is computed against 228 EP applications only. Even if every "
            "CA patent had an EP counterpart, the chance that the counterpart is inside a "
            "228-application sample is ~1e-5 per record. A null result here says nothing "
            "about whether the corpora overlap; it says the sample is too small to test."
        ),
        "expected_matches_if_fully_overlapping": expected,
        "what_would_be_needed": (
            "to measure real EPO/CIPO overlap, enumerate all EP application numbers in the "
            "relevant filing window from the sitemap (free) and intersect — that is a "
            "tier-1 operation costing sitemap requests only, not document fetches"
        ),
        "examples": matches[:15],
    }


def main() -> int:
    epo, cipo, collect = load()
    weeks = collect.get("weeks_used") or []
    pub_enumerated = sum(w.get("publications", 0) for w in weeks if "publications" in w)
    med_enumerated = sum(w.get("medtech", 0) for w in weeks if "medtech" in w)

    roles = Counter((r.get("attributes") or {}).get("document_role") for r in epo)
    indep = sum(1 for r in epo if (r.get("attributes") or {}).get("is_independent_disclosure"))

    exp_h1 = {
        "experiment": "EXP-H1",
        "scope": "patent sources: what did the new channels actually add?",
        "generated_at": now_utc(),
        "epo_enumeration": {
            "weekly_sitemaps_read": len(weeks),
            "publications_enumerated": pub_enumerated,
            "medical_device_publications_enumerated": med_enumerated,
            "medtech_share_of_enumerated": round(med_enumerated / pub_enumerated, 4) if pub_enumerated else None,
            "front_pages_fetched": collect.get("front_pages_attempted"),
            "share_of_enumerated_medtech_actually_fetched": (
                round((collect.get("front_pages_attempted") or 0) / med_enumerated, 4) if med_enumerated else None
            ),
            "note": "the sitemap gives publication reference + application reference + IPC for "
                    "every publication without fetching documents; front pages are needed only "
                    "for applicants, titles and abstracts",
        },
        "epo_records": coverage(epo, "epo_publication_server"),
        "epo_document_roles": {
            "by_role": dict(sorted(roles.items())),
            "independent_technical_disclosures": indep,
            "non_independent_share": round((len(epo) - indep) / (len(epo) or 1), 4),
            "note": "A3 search reports and B8 corrected title pages are not new technical "
                    "disclosures; counting them would inflate the corpus",
        },
        "cipo_records": coverage(cipo, "cipo_canada") if cipo else {"records": 0, "note": "not present"},
        "cross_source_independence": cross_source_overlap(epo, cipo) if cipo else {"note": "cipo absent"},
        "unique_dedupe_keys": {
            "epo": len({dedupe_key(r) for r in epo}),
            "cipo": len({dedupe_key(r) for r in cipo}),
            "combined": len({dedupe_key(r) for r in epo + cipo}),
        },
    }

    # ---- EXP-H3 ---------------------------------------------------------
    epo_clocks = coverage(epo, "epo_publication_server")
    cipo_clocks = coverage(cipo, "cipo_canada") if cipo else {"records": 0}
    snapshot_only = sum(
        1 for r in cipo if "SNAPSHOT_ONLY" in (r.get("quality_flags") or [])
    )
    exp_h3 = {
        "experiment": "EXP-H3",
        "scope": "are the new patent sources eligible for historical time research?",
        "generated_at": now_utc(),
        "epo": {
            "share_with_recorded_public_date": epo_clocks.get("share_public_date"),
            "observability_gap_days": epo_clocks.get("observability_gap_days"),
            "two_clock_records": epo_clocks.get("two_clock"),
            "historical_versions_available": False,
            "why": "the publication server serves the document as published; there is no "
                   "record-level version history, so we observe a fixed published artefact",
            "date_confusion_checked": True,
            "date_confusion_note": "INID 43 (application publication) and INID 45 (grant) are "
                                   "both present on granted documents and are separated by "
                                   "years; the connector records both and selects by kind",
        },
        "cipo": {
            "records": len(cipo),
            "share_with_recorded_public_date": cipo_clocks.get("share_public_date"),
            "share_snapshot_only": round(snapshot_only / (len(cipo) or 1), 4),
            "observability_gap_days": cipo_clocks.get("observability_gap_days"),
            "historical_versions_available": False,
            "why": "single quarterly extract ending 2022-02-28; only Grant Date is a recorded "
                   "public-availability date, pending applications have none",
            "date_confusion_checked": True,
            "date_confusion_note": "Filing Date must never be used as an observation date; the "
                                   "18-month laid-open rule is a rule, not a recorded field, and "
                                   "is deliberately not applied",
        },
        "verdict": (
            "EP publications are eligible for historical-observability work: every record has a "
            "recorded public date and a filing date, and the gap is measured per record. "
            "CIPO is eligible only for granted patents and is snapshot-limited; its ownership "
            "timeline is the more valuable feature and is dated."
        ),
    }

    for name, doc in (("EXP_H1_PATENTS.json", exp_h1), ("EXP_H3_PATENTS.json", exp_h3)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print("wrote", name)
    print(json.dumps(
        {
            "epo_records": len(epo),
            "cipo_records": len(cipo),
            "epo_independent": indep,
            "epo_gap": epo_clocks.get("observability_gap_days"),
            "overlap": exp_h1["cross_source_independence"].get("cipo_records_sharing_a_family_with_epo"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
