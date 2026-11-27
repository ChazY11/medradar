"""EXP-H3 — publication-time observability.

Answers three questions for the pre-registered anchor set, and one bonus
question that the four-clock model needs:

1. For each source, what share of records exposes an **explicit public-visible
   date** (a date that claims when the work was published)?
2. What share of anchors has databases that **disagree** on that date, and by
   how many days?
3. What share of records has **only a current-snapshot date** — i.e. a
   publication date but no creation / index / first-seen timestamp, so the
   record's own history is unavailable?
4. (bonus) For the sources that *do* expose a creation/index timestamp, how long
   after the nominal publication date did the record become visible? That lag is
   the only quantity that can honestly separate "published" from "observable".

Reads only saved datasets; no network.

    python experiments/scholarly/analyze_exp_h3.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from CONNECTORS.scholarly import _util as U  # noqa: E402
from hz.timeq import parse_iso  # noqa: E402

EXP = os.path.dirname(os.path.abspath(__file__))

PUB_SOURCES = ["openalex", "crossref", "europepmc", "pubmed_eutils",
               "semantic_scholar", "openaire"]

SOURCE_LABEL = {
    "openalex": "OpenAlex", "crossref": "Crossref", "europepmc": "Europe PMC",
    "pubmed_eutils": "PubMed (E-utilities)", "semantic_scholar": "Semantic Scholar",
    "openaire": "OpenAIRE Graph", "clinicaltrials_gov": "ClinicalTrials.gov",
    "nih_reporter": "NIH RePORTER", "eu_cordis": "CORDIS", "eu_ctis": "EU CTIS",
}

# What each source actually exposes. Every entry here was read off a saved
# response; nothing is assumed from documentation alone.
FIELD_INVENTORY = {
    "openalex": {
        "public_visible_date": ["publication_date"],
        "creation_or_index_date": ["created_date"],
        "mutable_snapshot_date": ["updated_date"],
        "source_of_creation_date": "the API returns created_date per work",
    },
    "crossref": {
        "public_visible_date": ["issued", "published", "published_online",
                                "published_print"],
        "creation_or_index_date": ["created"],
        "mutable_snapshot_date": ["deposited", "indexed"],
        "source_of_creation_date": "message.created is the DOI registration timestamp "
                                   "with a full UTC date-time",
    },
    "europepmc": {
        "public_visible_date": ["firstPublicationDate", "electronicPublicationDate",
                                "publicationDate"],
        "creation_or_index_date": ["firstIndexDate", "dateOfCreation",
                                   "fullTextReceivedDate"],
        "mutable_snapshot_date": ["dateOfRevision"],
        "source_of_creation_date": "firstIndexDate / dateOfCreation are indexing-history "
                                   "fields, distinct from the publication date",
    },
    "pubmed_eutils": {
        "public_visible_date": ["pub_date", "article_date_electronic"],
        "creation_or_index_date": [],
        "mutable_snapshot_date": [],
        "source_of_creation_date": "NONE - efetch output carries no record-creation or "
                                   "index timestamp, which is why first_observed_at is "
                                   "left None on PubMed records",
    },
    "semantic_scholar": {
        "public_visible_date": ["publicationDate"],
        "creation_or_index_date": [],
        "mutable_snapshot_date": [],
        "source_of_creation_date": "NONE - the Graph API exposes no creation timestamp",
    },
    "openaire": {
        "public_visible_date": ["publicationDate", "instances[].publicationDate"],
        "creation_or_index_date": [],
        "mutable_snapshot_date": ["lastUpdateTimeStamp"],
        "source_of_creation_date": "NONE - lastUpdateTimeStamp is a mutable marker, not "
                                   "a creation date",
    },
    "clinicaltrials_gov": {
        "public_visible_date": ["study_first_post_date"],
        "creation_or_index_date": ["study_first_submit_date",
                                   "study_first_submit_qc_date"],
        "mutable_snapshot_date": ["last_update_submit_date", "last_update_post_date"],
        "source_of_creation_date": "submit date and QC date are recorded separately from "
                                   "the post date, so the submission->publication lag is "
                                   "measurable for trials",
    },
    "nih_reporter": {
        "public_visible_date": ["award_notice_date"],
        "creation_or_index_date": [],
        "mutable_snapshot_date": [],
        "source_of_creation_date": "award_notice_date is preserved; no separate "
                                   "record-creation timestamp in the projected fields",
    },
    "eu_cordis": {
        "public_visible_date": [],
        "creation_or_index_date": [],
        "mutable_snapshot_date": ["lastUpdateDate"],
        "source_of_creation_date": "NONE usable - dates arrive as template strings such "
                                   "as '1 {{month_08}} 2014'",
    },
    "eu_ctis": {
        "public_visible_date": [],
        "creation_or_index_date": [],
        "mutable_snapshot_date": [],
        "source_of_creation_date": "NONE - no record was ever served (HTTP 403)",
    },
}


def load_records(source_id: str) -> list[dict]:
    path = os.path.join(U.DATASETS, source_id, "records.jsonl")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def pub_date(rec: dict) -> str | None:
    """The source's single best public-visible date for this record."""
    a = rec.get("attributes") or {}
    s = rec.get("source_id")
    if s == "openalex":
        return a.get("publication_date")
    if s == "crossref":
        d = a.get("dates") or {}
        return d.get("issued") or d.get("published") or d.get("published_online") \
            or d.get("published_print")
    if s == "europepmc":
        d = a.get("dates") or {}
        return d.get("firstPublicationDate") or d.get("electronicPublicationDate")
    if s == "pubmed_eutils":
        d = a.get("dates") or {}
        return d.get("article_date_electronic") or d.get("pub_date")
    if s == "semantic_scholar":
        return (a.get("dates") or {}).get("publicationDate")
    if s == "openaire":
        return a.get("publicationDate")
    if s == "clinicaltrials_gov":
        d = a.get("dates") or {}
        return d.get("study_first_post_date")
    if s == "nih_reporter":
        return a.get("award_notice_date")
    return None


def creation_date(rec: dict) -> str | None:
    a = rec.get("attributes") or {}
    s = rec.get("source_id")
    if s == "openalex":
        return a.get("created_date")
    if s == "crossref":
        d = a.get("dates") or {}
        return d.get("created")
    if s == "europepmc":
        d = a.get("dates") or {}
        return d.get("firstIndexDate") or d.get("dateOfCreation")
    if s == "clinicaltrials_gov":
        d = a.get("dates") or {}
        return d.get("study_first_submit_date")
    return None


def mutable_date(rec: dict) -> str | None:
    a = rec.get("attributes") or {}
    s = rec.get("source_id")
    if s == "openalex":
        return a.get("updated_date")
    if s == "crossref":
        d = a.get("dates") or {}
        return d.get("indexed") or d.get("deposited")
    if s == "europepmc":
        d = a.get("dates") or {}
        return d.get("dateOfRevision")
    if s == "openaire":
        return a.get("lastUpdateTimeStamp")
    if s == "clinicaltrials_gov":
        d = a.get("dates") or {}
        return d.get("last_update_post_date")
    return None


def doi_of(rec: dict) -> str | None:
    for i in rec.get("identifiers") or []:
        if i.get("scheme") == "doi" and i.get("is_primary"):
            return U.norm_doi(i["value"])
    for i in rec.get("identifiers") or []:
        if i.get("scheme") == "doi":
            return U.norm_doi(i["value"])
    return None


def bucket(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "creation_before_publication"
    if days == 0:
        return "same_day"
    if days <= 7:
        return "1-7_days"
    if days <= 30:
        return "8-30_days"
    if days <= 180:
        return "31-180_days"
    if days <= 730:
        return "181-730_days"
    return "over_730_days"


def main() -> int:
    anchors = U.read_json(U.ANCHORS_PATH)["anchors"]
    anchor_dois = {a["doi"] for a in anchors}

    per_source = {s: load_records(s) for s in PUB_SOURCES}

    # ---------------- (1)+(3) per-source date availability ------------------
    availability = {}
    for s in PUB_SOURCES:
        recs = per_source[s]
        n = len(recs)
        with_pub = sum(1 for r in recs if parse_iso(pub_date(r)))
        with_creation = sum(1 for r in recs if parse_iso(creation_date(r)))
        with_mutable = sum(1 for r in recs if parse_iso(mutable_date(r)))
        snapshot_only = sum(
            1 for r in recs
            if parse_iso(pub_date(r)) and not parse_iso(creation_date(r))
        )
        availability[s] = {
            "source_label": SOURCE_LABEL[s],
            "records": n,
            "explicit_public_visible_date": with_pub,
            "share_with_explicit_public_date": round(with_pub / n, 4) if n else None,
            "creation_or_index_date": with_creation,
            "share_with_creation_date": round(with_creation / n, 4) if n else None,
            "mutable_snapshot_date": with_mutable,
            "current_snapshot_only": snapshot_only,
            "share_current_snapshot_only": round(snapshot_only / n, 4) if n else None,
            "field_inventory": FIELD_INVENTORY[s],
        }

    # ---------------- (2) cross-source publication-date disagreement --------
    # index each source's date per anchor
    date_by_anchor: dict[str, dict[str, str]] = defaultdict(dict)
    for s in PUB_SOURCES:
        for r in per_source[s]:
            d = doi_of(r)
            if d in anchor_dois and parse_iso(pub_date(r)):
                date_by_anchor[d].setdefault(s, pub_date(r))

    pairwise = Counter()
    pairwise_examples: list[dict] = []
    per_anchor_spread = []
    for doi, ds in date_by_anchor.items():
        if len(ds) < 2:
            continue
        for a, b in combinations(sorted(ds), 2):
            pa, pb = parse_iso(ds[a]), parse_iso(ds[b])
            if not pa or not pb:
                continue
            delta = abs((pa - pb).days)
            pkey = f"{a}|{b}"
            pairwise[pkey] += 1
            if delta:
                pairwise[f"{pkey}|disagree"] += 1
            if delta and len(pairwise_examples) < 40:
                pairwise_examples.append({
                    "anchor_doi": doi, "source_a": a, "source_b": b,
                    "date_a": ds[a], "date_b": ds[b], "delta_days": delta,
                })
        values = [parse_iso(v) for v in ds.values() if parse_iso(v)]
        spread = (max(values) - min(values)).days
        per_anchor_spread.append({
            "anchor_doi": doi,
            "sources_with_date": sorted(ds),
            "dates": ds,
            "spread_days": spread,
            "bucket": bucket(spread),
        })

    spread_buckets = Counter(x["bucket"] for x in per_anchor_spread)
    anchors_with_2plus = len(per_anchor_spread)
    anchors_disagreeing = sum(1 for x in per_anchor_spread if x["spread_days"] > 0)

    pair_rates = {}
    for key in sorted({k.rsplit("|", 1)[0] for k in pairwise if "|disagree" in k}):
        total = pairwise.get(key, 0)
        dis = pairwise.get(f"{key}|disagree", 0)
        a, b = key.split("|")
        pair_rates[key] = {
            "source_a": SOURCE_LABEL[a], "source_b": SOURCE_LABEL[b],
            "anchors_compared": total,
            "anchors_disagreeing": dis,
            "disagreement_rate": round(dis / total, 4) if total else None,
        }

    # ---------------- (4) index-lag distribution ---------------------------
    # Only publication sources: for these, creation/index time is when the record
    # became *visible*, whereas for a trial the submit date precedes the post date
    # by construction and means something different (see the trial section below).
    lag = {}
    for s in ("openalex", "crossref", "europepmc"):
        vals = []
        rows = per_source[s]
        for r in rows:
            p, c = parse_iso(pub_date(r)), parse_iso(creation_date(r))
            if p and c:
                vals.append((c - p).days)
        buckets = Counter(bucket(v) for v in vals)
        lag[s] = {
            "source_label": SOURCE_LABEL[s],
            "records_with_both_dates": len(vals),
            "median_days_creation_minus_publication": (
                sorted(vals)[len(vals) // 2] if vals else None),
            "min_days": min(vals) if vals else None,
            "max_days": max(vals) if vals else None,
            "buckets": dict(sorted(buckets.items())),
            "note": (
                "positive = the record became visible AFTER the nominal publication "
                "date, i.e. a measurable observability lag; negative = the 'publication "
                "date' is later than the record's creation (issue-date vs e-pub effects)"
            ),
        }

    # trial-specific lag: submission -> first posting
    trial_lag = {}
    trial_recs = load_records("clinicaltrials_gov")
    tv = []
    for r in trial_recs:
        d = (r.get("attributes") or {}).get("dates") or {}
        sub, post = parse_iso(d.get("study_first_submit_date")), \
            parse_iso(d.get("study_first_post_date"))
        if sub and post:
            tv.append((post - sub).days)
    trial_lag["clinicaltrials_gov"] = {
        "source_label": SOURCE_LABEL["clinicaltrials_gov"],
        "records_with_both_dates": len(tv),
        "median_days_posting_minus_submission": (sorted(tv)[len(tv) // 2] if tv else None),
        "min_days": min(tv) if tv else None,
        "max_days": max(tv) if tv else None,
        "buckets": dict(sorted(Counter(bucket(v) for v in tv).items())),
        "note": (
            "This is NOT an indexing lag. It is the registry's own queue: the gap "
            "between a sponsor submitting the record and ClinicalTrials.gov first "
            "posting it. It is a genuine four-clock quantity because the event (the "
            "trial starting) is a third, earlier date again."
        ),
    }

    # ---------------- non-publication entity clocks (secondary) ------------
    secondary = {}
    for s in ("clinicaltrials_gov", "nih_reporter", "eu_cordis", "eu_ctis"):
        rows = load_records(s)
        n = len(rows)
        secondary[s] = {
            "source_label": SOURCE_LABEL[s],
            "records": n,
            "explicit_public_visible_date": sum(
                1 for r in rows if r.get("source_public_at")),
            "event_date": sum(1 for r in rows if r.get("event_at")),
            "creation_or_index_date": sum(
                1 for r in rows if parse_iso(creation_date(r))),
            "field_inventory": FIELD_INVENTORY[s],
        }

    doc = {
        "experiment": "EXP-H3",
        "title": "Publication-time observability: explicit public dates, cross-database "
                 "date disagreement, and current-snapshot-only dates",
        "selection_rule": "experiments/scholarly/EXP_H1_SELECTION_RULE.md",
        "generated_at": U.utc_now(),
        "anchor_count": len(anchors),
        "sources": PUB_SOURCES,
        "date_availability": availability,
        "cross_source_date_disagreement": {
            "anchors_with_at_least_two_dates": anchors_with_2plus,
            "anchors_disagreeing": anchors_disagreeing,
            "share_disagreeing": (
                round(anchors_disagreeing / anchors_with_2plus, 4)
                if anchors_with_2plus else None),
            "spread_buckets": dict(sorted(spread_buckets.items())),
            "pairwise": pair_rates,
            "pairwise_examples": pairwise_examples,
            "per_anchor": sorted(per_anchor_spread,
                                 key=lambda x: -x["spread_days"])[:60],
        },
        "index_lag": lag,
        "trial_submission_to_posting_lag": trial_lag,
        "non_publication_entity_clocks": secondary,
        "headline": {
            "share_anchors_with_cross_db_date_disagreement": (
                round(anchors_disagreeing / anchors_with_2plus, 4)
                if anchors_with_2plus else None),
            "share_anchors_disagreeing_by_more_than_30_days": (
                round(sum(1 for x in per_anchor_spread if x["spread_days"] > 30)
                      / anchors_with_2plus, 4) if anchors_with_2plus else None),
            "sources_with_creation_date": [
                s for s in PUB_SOURCES if availability[s]["creation_or_index_date"] > 0],
            "sources_current_snapshot_only": [
                s for s in PUB_SOURCES if availability[s]["records"] and
                availability[s]["creation_or_index_date"] == 0],
        },
    }
    U.write_json(os.path.join(EXP, "EXP_H3_PUB_TIME.json"), doc)
    print(json.dumps(doc["headline"], indent=2))
    print("spread buckets:", dict(sorted(spread_buckets.items())))
    for s in PUB_SOURCES:
        a = availability[s]
        print(f"  {s:20s} n={a['records']:3d} pub={a['explicit_public_visible_date']:3d} "
              f"creation={a['creation_or_index_date']:3d} snapshot_only={a['current_snapshot_only']:3d}")
    for s, v in lag.items():
        print(f"  lag {s:20s} n={v['records_with_both_dates']:3d} "
              f"median={v['median_days_creation_minus_publication']} "
              f"buckets={v['buckets']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
