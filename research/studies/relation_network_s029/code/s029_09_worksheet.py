"""S-029 step 09 — build the human adjudication worksheet (~100 stratified rows).

This script produces `S029_HUMAN_REVIEW_WORKSHEET.csv`. It does **not** adjudicate.
Every human field is written empty. The machine's own label is kept in a clearly
separated column so that a reviewer can disagree with it, and the sampling is
stratified and declared so that a future reviewer cannot be handed only easy
positives.

Strata (declared before sampling, deterministic seed):

* relation family — company/trial sponsor, company/trial collaborator, institution/trial,
  company/publication, institution/publication, co-affiliation, trial→publication reference,
  company-funded publication;
* company — all five, with the small companies deliberately over-weighted per claim;
* machine confidence band — high (exact/email-domain), medium (alias/text), low (fuzzy/undated);
* period — before 2016 vs from 2016;
* expected-negative candidates — the measured collisions (surname/email, personal names,
  substring, former parent, non-group company). These are *required*: a worksheet made only
  of successful matches cannot estimate precision.

The file is regenerated from the artefacts, so the review sheet can be rebuilt after a
re-collection without hand editing.

Run:  python research/studies/relation_network_s029/code/s029_09_worksheet.py
Writes: S029_HUMAN_REVIEW_WORKSHEET.csv, artifacts/worksheet_provenance.json
"""

from __future__ import annotations

import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, read_jsonl, stable_seed, utcnow_iso,
                         write_json)

STUDY_DIR = ARTIFACT_DIR.parent
CSV_PATH = STUDY_DIR / "S029_HUMAN_REVIEW_WORKSHEET.csv"
TARGET_ROWS = 100
SEED = stable_seed("s029", "worksheet", "v1")

FIELDS = [
    "candidate_id", "relation_type", "entity_a", "entity_b", "evidence_url",
    "evidence_excerpt", "machine_label", "machine_confidence",
    "human_label", "reviewer_id", "review_date", "review_reason", "adjudication_status",
    # machine-kept context (read-only for the reviewer)
    "stratum_expected", "source", "source_record_id", "claim_id", "evidence_id",
    "company_key", "published_at", "event_at", "time_basis", "timestamp_precision",
    "mapping_status", "claim_status", "machine_reason", "human_label_guide",
]

HUMAN_GUIDE = ("RELATION_SUPPORTED | RELATION_NOT_SUPPORTED | AMBIGUOUS | INSUFFICIENT_EVIDENCE")


def main() -> None:
    claims = list(read_jsonl(DATA_DIR / "claims.jsonl"))
    evidence = {e["evidence_id"]: e for e in read_jsonl(DATA_DIR / "evidence.jsonl")}
    entities = {e["entity_id"]: e for e in read_jsonl(DATA_DIR / "entities.jsonl")}
    rejects = list(read_jsonl(DATA_DIR / "claim_rejects.jsonl"))
    rng = random.Random(SEED)

    def entity_label(eid: str) -> str:
        ent = entities.get(eid) or {}
        sid = ent.get("stable_external_ids") or {}
        ident = next((f"{k}:{v}" for k, v in sid.items() if v), "")
        return f"{ent.get('canonical_name') or eid} [{eid}{'; ' + ident if ident else ''}]"

    def band(c: dict) -> str:
        conf = c.get("confidence") or 0
        if conf >= 0.9:
            return "HIGH"
        if conf >= 0.7:
            return "MEDIUM"
        return "LOW"

    def period(c: dict) -> str:
        y = (c.get("published_at") or "")[:4]
        return "PRE_2016" if y.isdigit() and int(y) < 2016 else "FROM_2016"

    def family(c: dict) -> str:
        p = c["predicate"]
        role = c.get("relation_role")
        if p == "SPONSORS_TRIAL":
            return "company_trial_lead" if role == "lead_sponsor" else "company_trial_collab"
        if p == "RESPONSIBLE_FOR_TRIAL":
            return "company_trial_responsible"
        if p == "HOSTS_TRIAL_SITE":
            return "institution_trial_site"
        if p == "REFERENCES_PUBLICATION":
            return "trial_references_publication"
        if p == "AFFILIATED_WITH":
            return ("company_publication" if c["subject_id"].startswith("ent:company:")
                    else "institution_publication")
        if p == "CO_AFFILIATED_ON":
            return "company_institution_coaffiliation"
        if p == "FUNDED_BY":
            return "company_funded_publication"
        if p == "HAS_TOPIC":
            return "publication_topic"
        return "other"

    def excerpt(c: dict) -> str:
        ev = evidence.get(c["evidence_id"]) or {}
        return (ev.get("original_text_reference") or "")[:300]

    def url_of(c: dict) -> str:
        ev = evidence.get(c["evidence_id"]) or {}
        return ev.get("original_url") or ""

    rows: list[dict] = []
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for c in claims:
        if c["predicate"] == "HAS_TOPIC":
            continue  # index terms are not a relation the brief asks to adjudicate
        key = (family(c), (c["subject_id"].split(":")[-1] if c["subject_id"].startswith("ent:company:")
                           else "institution"), band(c), period(c))
        buckets[key].append(c)

    # Quota scheme: emphasise small companies and low-confidence cells, but keep every
    # family represented. Quotas are shares of TARGET_ROWS.
    family_quota = {
        "company_trial_lead": 14, "company_trial_collab": 10, "institution_trial_site": 10,
        "company_publication": 14, "institution_publication": 10,
        "company_institution_coaffiliation": 12, "trial_references_publication": 8,
        "company_funded_publication": 8, "company_trial_responsible": 2,
    }
    negatives_quota = 14

    def pick(cands: list[dict], n: int) -> list[dict]:
        if not cands:
            return []
        rng.shuffle(cands)
        # prefer a spread of companies when available
        by_co: dict[str, list[dict]] = defaultdict(list)
        for c in cands:
            sid = c.get("subject_id") or ""
            co = (sid.split(":")[-1] if sid.startswith("ent:company:")
                  else (c.get("company_key") or "other"))
            by_co[co].append(c)
        out = []
        cos = sorted(by_co)
        i = 0
        while len(out) < n and any(by_co[x] for x in cos):
            co = cos[i % len(cos)]
            if by_co[co]:
                out.append(by_co[co].pop())
            i += 1
        return out

    for fam, quota in family_quota.items():
        pool = [c for k, v in buckets.items() if k[0] == fam for c in v]
        # low confidence first, then medium, then high - so the sheet is not all easy rows
        low = [c for c in pool if band(c) == "LOW"]
        med = [c for c in pool if band(c) == "MEDIUM"]
        high = [c for c in pool if band(c) == "HIGH"]
        chosen = pick(low, max(quota // 2, 2)) + pick(med, quota // 3) + pick(high, quota)
        # top up when a family's confidence bands collapse (e.g. every funded-publication row is
        # MEDIUM), so the declared family quota is met rather than silently under-filled
        if len(chosen) < quota:
            picked_ids = {c["relation_id"] for c in chosen}
            rest = [c for c in pool if c["relation_id"] not in picked_ids]
            chosen += pick(rest, quota - len(chosen))
        seen = set()
        for c in chosen:
            if len([r for r in rows if r["relation_type"] == fam]) >= quota:
                break
            if c["relation_id"] in seen:
                continue
            seen.add(c["relation_id"])
            rows.append({
                "candidate_id": "", "relation_type": fam,
                "entity_a": entity_label(c["subject_id"]),
                "entity_b": (entity_label(c["object_id"]) if c.get("object_id")
                             else f"UNRESOLVED:{c.get('object_external_id')}"),
                "evidence_url": url_of(c), "evidence_excerpt": excerpt(c),
                "machine_label": c["claim_status"], "machine_confidence": c["confidence"],
                "human_label": "", "reviewer_id": "", "review_date": "", "review_reason": "",
                "adjudication_status": "",
                "stratum_expected": "expect_relation_present",
                "source": (evidence.get(c["evidence_id"]) or {}).get("source", ""),
                "source_record_id": c["source_record_id"], "claim_id": c["relation_id"],
                "evidence_id": c["evidence_id"],
                "company_key": (c["subject_id"].split(":")[-1]
                                if c["subject_id"].startswith("ent:company:") else ""),
                "published_at": c.get("published_at") or "", "event_at": c.get("event_at") or "",
                "time_basis": c.get("time_basis") or "",
                "timestamp_precision": c.get("timestamp_precision") or "",
                "mapping_status": c.get("mapping_status") or "",
                "claim_status": c["claim_status"],
                "machine_reason": (c.get("mapping_method") or "")[:160],
                "human_label_guide": HUMAN_GUIDE,
            })

    # Expected-negative candidates: the measured collisions and refusals. A reviewer must
    # see these, otherwise precision is measured only on favourable rows.
    neg_pool = [r for r in rejects if r.get("raw_string")]
    # also add ambiguous claims and anachronism-flagged claims as negative/uncertain strata
    neg_pool_claims = [c for c in claims
                       if c["claim_status"] in ("AMBIGUOUS", "CONFLICTED")
                       or c.get("anachronism")]
    chosen_neg = pick(neg_pool, negatives_quota - 3) if neg_pool else []
    for r in chosen_neg:
        rows.append({
            "candidate_id": "", "relation_type": "expected_negative:" + str(r.get("record_kind")),
            "entity_a": f"UNMAPPED STRING: {r.get('raw_string','')[:160]}",
            "entity_b": r.get("record_id") or "",
            "evidence_url": "", "evidence_excerpt": (r.get("reason") or "")[:300],
            "machine_label": "REJECTED", "machine_confidence": 0.0,
            "human_label": "", "reviewer_id": "", "review_date": "", "review_reason": "",
            "adjudication_status": "",
            "stratum_expected": "expect_relation_absent",
            "source": r.get("source", ""), "source_record_id": r.get("record_id") or "",
            "claim_id": "", "evidence_id": r.get("evidence_id") or "",
            "company_key": r.get("company_key") or "",
            "published_at": "", "event_at": "", "time_basis": "", "timestamp_precision": "",
            "mapping_status": r.get("mapping_status") or "",
            "claim_status": "REJECTED", "machine_reason": (r.get("rule") or "")[:160],
            "human_label_guide": HUMAN_GUIDE})
    for c in pick(neg_pool_claims, 3):
        rows.append({
            "candidate_id": "", "relation_type": "expected_negative:" + family(c),
            "entity_a": entity_label(c["subject_id"]), "entity_b": entity_label(c.get("object_id") or ""),
            "evidence_url": url_of(c), "evidence_excerpt": excerpt(c),
            "machine_label": c["claim_status"], "machine_confidence": c["confidence"],
            "human_label": "", "reviewer_id": "", "review_date": "", "review_reason": "",
            "adjudication_status": "",
            "stratum_expected": "expect_machine_mapping_wrong_or_uncertain",
            "source": (evidence.get(c["evidence_id"]) or {}).get("source", ""),
            "source_record_id": c["source_record_id"], "claim_id": c["relation_id"],
            "evidence_id": c["evidence_id"],
            "company_key": (c["subject_id"].split(":")[-1]
                            if c["subject_id"].startswith("ent:company:") else ""),
            "published_at": c.get("published_at") or "", "event_at": c.get("event_at") or "",
            "time_basis": c.get("time_basis") or "",
            "timestamp_precision": c.get("timestamp_precision") or "",
            "mapping_status": c.get("mapping_status") or "",
            "claim_status": c["claim_status"], "machine_reason": (c.get("mapping_method") or "")[:160],
            "human_label_guide": HUMAN_GUIDE})

    # order: positive strata first, grouped, then negatives; stable candidate ids
    rows.sort(key=lambda r: (r["stratum_expected"], r["relation_type"], r["source_record_id"]))
    rows = rows[:TARGET_ROWS + 6]
    for i, r in enumerate(rows, 1):
        r["candidate_id"] = f"S029-HR-{i:03d}"

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

    prov = {
        "generated_at": utcnow_iso(),
        "csv": CSV_PATH.name,
        "rows": len(rows),
        "seed": SEED,
        "strata_counts": dict(Counter(r["relation_type"] for r in rows)),
        "stratum_expected_counts": dict(Counter(r["stratum_expected"] for r in rows)),
        "company_counts": dict(Counter(r["company_key"] for r in rows)),
        "machine_label_counts": dict(Counter(r["machine_label"] for r in rows)),
        "human_fields_written": [],
        "human_fields_blank_verified": all(
            not (r["human_label"] or r["reviewer_id"] or r["review_date"] or r["review_reason"])
            for r in rows),
        "note": "human_label / reviewer_id / review_date / review_reason / adjudication_status are "
                "EMPTY BY CONSTRUCTION. No precision, recall or human-truth statistic may be "
                "computed from this file until a real reviewer fills them.",
    }
    write_json(ARTIFACT_DIR / "worksheet_provenance.json", prov)
    print(f"wrote {CSV_PATH} rows={len(rows)}")
    print(prov["strata_counts"])
    print("blank human fields verified:", prov["human_fields_blank_verified"])


if __name__ == "__main__":
    main()
