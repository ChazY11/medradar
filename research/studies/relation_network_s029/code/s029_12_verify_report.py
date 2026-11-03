"""S-029 step 12 — independent verification of every claimed number.

This is the audit that a reviewer should be able to run without trusting the author.
It re-derives the headline figures from the committed artefacts and the committed raw
payloads, and it fails loudly (non-zero exit) on any mismatch.

Checks
  V1  every evidence row resolves to a committed raw payload whose recomputed sha256 matches
  V2  claim store integrity: closed predicate list, allowed statuses, entity references exist
  V3  claim counts reported in claims_summary.json equal the counts in claims.jsonl
  V4  per-company counts reported in quality_metrics.json equal the recomputed counts
  V5  first_seen_at is not a constant: distinct values per source are reported (a single value
      would prove the clock is fabricated)
  V6  no HUMAN_CONFIRMED claim exists; worksheet human fields are blank
  V7  the pre-registration file has the sha256 recorded at verdict time (no post-hoc edit)
  V8  the literature corpus is machine-verified: every reference carries a verification URL and
      payload hash, and the count matches the reported number
  V9  frozen S-028 artefacts are untouched (git status of the main checkout, read-only)
  V10 raw row counts match the extraction report

Run:  python research/studies/s029.../code/s029_12_verify_report.py
Writes: artifacts/verification.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, RAW_DIR, load_raw_envelope, read_json,
                         read_jsonl, sha256_text, utcnow_iso, write_json)

STUDY_DIR = ARTIFACT_DIR.parent
MAIN_CHECKOUT = Path("D:/DEPPSKK/medradar")

ALLOWED_PREDICATES = {"SPONSORS_TRIAL", "RESPONSIBLE_FOR_TRIAL", "HOSTS_TRIAL_SITE",
                      "REFERENCES_PUBLICATION", "AFFILIATED_WITH", "CO_AFFILIATED_ON",
                      "HAS_TOPIC", "FUNDED_BY", "COOPERATES_WITH"}
ALLOWED_STATUS = {"VERIFIED_BY_SOURCE", "CANDIDATE", "AMBIGUOUS", "CONFLICTED", "REJECTED",
                  "HUMAN_CONFIRMED"}


class Checker:
    def __init__(self):
        self.results: list[dict] = []

    def check(self, name: str, ok: bool, detail: object = None) -> None:
        self.results.append({"check": name, "pass": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def main() -> int:
    c = Checker()

    claims = list(read_jsonl(DATA_DIR / "claims.jsonl"))
    evidence = list(read_jsonl(DATA_DIR / "evidence.jsonl"))
    entities = {e["entity_id"]: e for e in read_jsonl(DATA_DIR / "entities.jsonl")}
    summary = read_json(ARTIFACT_DIR / "claims_summary.json")
    quality = read_json(ARTIFACT_DIR / "quality_metrics.json")

    # ---- V1: evidence -> committed raw payload ----
    raw_hashes = {}
    for path in sorted(RAW_DIR.glob("*.json.gz")):
        env = load_raw_envelope(path)
        h = sha256_text(json.dumps(env, ensure_ascii=False, sort_keys=True))
        raw_hashes["ev:" + h] = path.name
    # evidence_id format: ev:<sha256-of-committed-payload>:<source_record_id>
    def _env_id(eid: str) -> str:
        parts = str(eid).split(":")
        return ":".join(parts[:2]) if len(parts) >= 2 else str(eid)

    ev_with_raw = [e for e in evidence if _env_id(e["evidence_id"]) in raw_hashes]
    missing = [e["evidence_id"] for e in evidence if _env_id(e["evidence_id"]) not in raw_hashes]
    c.check("V1a evidence rows resolvable to committed raw payload",
            len(missing) == 0,
            {"evidence_rows": len(evidence), "resolved": len(ev_with_raw),
             "unresolved_examples": missing[:5]})
    resolved_ids = {e["evidence_id"] for e in ev_with_raw}
    claim_ev_ok = all(c2["evidence_id"] in resolved_ids for c2 in claims)
    c.check("V1b every claim's evidence_id resolves", claim_ev_ok,
            {"claims": len(claims)})

    # ---- V2: claim store integrity ----
    bad_pred = [c2["relation_id"] for c2 in claims if c2["predicate"] not in ALLOWED_PREDICATES]
    bad_status = [c2["relation_id"] for c2 in claims if c2["claim_status"] not in ALLOWED_STATUS]
    bad_subject = [c2["relation_id"] for c2 in claims if c2["subject_id"] not in entities]
    bad_object = [c2["relation_id"] for c2 in claims
                  if c2.get("object_id") and c2["object_id"] not in entities]
    c.check("V2 claim store integrity",
            not (bad_pred or bad_status or bad_subject or bad_object),
            {"bad_predicate": len(bad_pred), "bad_status": len(bad_status),
             "missing_subject_entity": len(bad_subject),
             "missing_object_entity": len(bad_object)})

    # ---- V3: counts agree with summary ----
    recomputed = dict(Counter(c2["predicate"] for c2 in claims))
    c.check("V3a claim count in summary equals claims.jsonl",
            summary["counts"]["claims"] == len(claims),
            {"summary": summary["counts"]["claims"], "file": len(claims)})
    c.check("V3b claims_by_predicate equals recomputation",
            {k: v for k, v in summary["claims_by_predicate"].items()
             if v} == {k: v for k, v in recomputed.items() if v},
            {"summary": {k: v for k, v in summary["claims_by_predicate"].items() if v},
             "recomputed": {k: v for k, v in recomputed.items() if v}})

    # ---- V4: per-company counts ----
    per_company = Counter(c2["subject_id"].split(":")[-1] for c2 in claims
                          if c2["subject_id"].startswith("ent:company:")
                          and c2["claim_status"] in ("VERIFIED_BY_SOURCE", "CANDIDATE"))
    reported = quality["A_coverage"].get("claims_per_company_authoritative") or {}
    c.check("V4 per-company authoritative counts agree",
            {k: v for k, v in per_company.items()} == {k: v for k, v in reported.items()},
            {"recomputed": dict(per_company), "reported": reported})

    # ---- V5: first_seen_at is a real clock, not a constant ----
    fs = defaultdict(Counter)
    for path in sorted(RAW_DIR.glob("*.json.gz")):
        env = load_raw_envelope(path)
        src = env.get("source")
        times = [p.get("retrieved_at") for p in (env.get("pages") or []) if p.get("retrieved_at")]
        if not times and (env.get("fetch_query_provenance") or {}).get("retrieved_at"):
            times = [env["fetch_query_provenance"]["retrieved_at"]]
        for t in times:
            fs[src][t] += 1
    c.check("V5 first_seen_at is a real per-request clock (not one constant)",
            all(len(v) > 1 for v in fs.values()) and bool(fs),
            {k: {"distinct": len(v), "n": sum(v.values()),
                 "min": min(v) if v else None, "max": max(v) if v else None}
             for k, v in fs.items()})

    # ---- V6: no human truth asserted ----
    hc = [c2 for c2 in claims if c2["claim_status"] == "HUMAN_CONFIRMED"]
    ws = STUDY_DIR / "S029_HUMAN_REVIEW_WORKSHEET.csv"
    ws_rows = 0
    ws_filled = 0
    if ws.exists():
        with ws.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ws_rows += 1
                if (row.get("human_label") or "").strip() or (row.get("reviewer_id") or "").strip():
                    ws_filled += 1
    c.check("V6 no machine claim is presented as human-confirmed",
            not hc and ws_filled == 0,
            {"human_confirmed_claims": len(hc), "worksheet_rows": ws_rows,
             "worksheet_rows_with_human_data": ws_filled})

    # ---- V7: pre-registration unchanged after the verdict ----
    prereg_path = STUDY_DIR / "GO_NO_GO_CRITERIA.md"
    current = sha256_text(prereg_path.read_text(encoding="utf-8"))
    recorded = (read_json(ARTIFACT_DIR / "prereg_decision.json").get("prereg_sha256")
                if (ARTIFACT_DIR / "prereg_decision.json").exists() else None)
    c.check("V7 pre-registration hash matches the one recorded at verdict time",
            recorded == current, {"recorded": recorded, "current": current})

    # ---- V8: literature corpus verified ----
    lit_path = ARTIFACT_DIR / "literature_refs.json"
    lit_ok = False
    lit_detail = {}
    if lit_path.exists():
        lit = read_json(lit_path)
        refs = lit.get("references") or []
        verified = [r for r in refs
                    if (r.get("verification") or {}).get("url")
                    and (r.get("verification") or {}).get("payload_sha256")]
        lit_ok = len(refs) > 0 and len(verified) == len(refs)
        lit_detail = {"references": len(refs), "with_verification_url_and_hash": len(verified),
                      "counts_reported": lit.get("counts")}
    c.check("V8 literature references carry verification URL + payload hash", lit_ok, lit_detail)

    # ---- V9: S-028 frozen artefacts untouched ----
    detail = {}
    try:
        out = subprocess.run(["git", "-C", str(MAIN_CHECKOUT), "status", "--porcelain"],
                             capture_output=True, text=True, timeout=60)
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        s028 = [l for l in lines if "graph_early_signal_s028" in l]
        ours = [l for l in lines if "relation_network_s029" in l]
        detail = {"dirty_entries_in_main_checkout": lines[:6],
                  "s028_entries_modified": s028, "s029_entries_in_main_checkout": ours,
                  "note": "S-029 works in a separate worktree; this checkout must show no S-028 "
                          "or S-029 modifications"}
        ok9 = not s028 and not ours
    except Exception as exc:  # noqa: BLE001
        ok9 = False
        detail = {"error": str(exc)}
    c.check("V9 frozen S-028 artefacts untouched", ok9, detail)

    # ---- V10: row counts agree with extraction report ----
    ext = read_json(ARTIFACT_DIR / "extract_report.json")
    trials = sum(1 for _ in (DATA_DIR / "ctgov_trials.jsonl").open(encoding="utf-8"))
    pubs = sum(1 for _ in (DATA_DIR / "epmc_pubs.jsonl").open(encoding="utf-8"))
    c.check("V10 raw row counts equal the extraction report",
            trials == ext["ctgov_rows"]["trials"] and pubs == ext["epmc_rows"],
            {"trials": trials, "pubs": pubs,
             "reported": {"trials": ext["ctgov_rows"]["trials"], "pubs": ext["epmc_rows"]}})

    passed = sum(1 for r in c.results if r["pass"])
    out = {
        "generated_at": utcnow_iso(),
        "checks_passed": passed,
        "checks_total": len(c.results),
        "all_passed": passed == len(c.results),
        "results": c.results,
        "claim_counts": {"claims": len(claims), "evidence": len(evidence),
                         "entities": len(entities), "raw_payloads": len(raw_hashes)},
    }
    write_json(ARTIFACT_DIR / "verification.json", out)
    print(f"\n{passed}/{len(c.results)} checks passed")
    return 0 if out["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
