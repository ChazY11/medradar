#!/usr/bin/env python3
"""Alpha acceptance smoke test: the three PRODUCT-002 user tasks, executed against the real product.

Task 1 - understand a competitor (search Medtronic, coverage, verified share, recent events, official page)
Task 2 - compare two companies with one window and one basis, then export a report identical in scope
Task 3 - review and correct one attribution, prove the change and prove unrelated counts did not move

Runs in-process with FastAPI's TestClient, so it needs no server and no network. Exit code 0 = all
checks passed.

    python scripts/alpha_smoke.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, str, bool, str]] = []


def check(check_id: str, description: str, passed: bool, evidence: str = "") -> None:
    CHECKS.append((check_id, description, bool(passed), evidence))
    print(("PASS " if passed else "FAIL ") + check_id + "  " + description + ("  [" + evidence[:160] + "]" if evidence else ""))


def main() -> int:
    from fastapi.testclient import TestClient

    from medradar.product.api import create_app
    from medradar.product.review.admin import create_admin_app

    client = TestClient(create_app())

    # ---------------------------------------------------------------- Task 1
    search = client.get("/api/search", params={"q": "Medtronic"}).json()
    hit = next((row for row in search["results"] if row["key"] == "medtronic"), None)
    check("T1-1", "searching Medtronic returns the tracked organization", hit is not None, json.dumps(hit["match"]) if hit else "")
    profile = client.get("/api/organizations/medtronic").json()
    coverage = client.get("/api/meta").json()["coverage"]
    check(
        "T1-2",
        "the organization page states FDA activity coverage (source split and date window)",
        bool(profile["coverage"]["sources"]) and profile["coverage"]["window"]["to"] is not None,
        "window " + str(profile["coverage"]["window"]["from"]) + ".." + str(profile["coverage"]["window"]["to"]),
    )
    verification = profile["verification"]
    check(
        "T1-3",
        "the page states the trusted-attribution share separately from the attributed share",
        verification["curated_share"] is not None and 0 <= verification["curated_share"] < 1,
        "curated share " + str(round(verification["curated_share"] * 100, 1)) + "% of " + str(verification["attributed_records"]) + " records",
    )
    events = client.get("/api/organizations/medtronic/events", params={"types": "recall", "page_size": 10}).json()
    check("T1-4", "recent regulatory events can be filtered", events["total"] > 0 and len(events["items"]) <= 10, str(events["total"]) + " recall records")
    detail = client.get("/api/events/" + events["items"][0]["event_id"]).json()
    check(
        "T1-5",
        "every record links to the official FDA page",
        detail["provenance"]["official_url"].startswith("https://"),
        detail["provenance"]["official_url"],
    )

    # ---------------------------------------------------------------- Task 2
    compare = client.get("/api/compare", params={"orgs": "medtronic,ge_healthcare"}).json()
    sides = {side["key"]: side for side in compare["organizations"]}
    same_window = {side["coverage"]["window"]["from"] + ".." + side["coverage"]["window"]["to"] for side in compare["organizations"]}
    check("T2-1", "both organizations use one shared window", len(same_window) == 1, same_window.pop() if same_window else "")
    check(
        "T2-2",
        "the same event types and counting unit apply to both sides",
        compare["comparability"]["event_types_shared"] and compare["comparability"]["counting_unit"].startswith("one regulatory record"),
        compare["comparability"]["verdict"],
    )
    check(
        "T2-3",
        "the ownership basis is stated",
        compare["comparability"]["ownership_basis"] == "current_group",
        compare["comparability"]["ownership_basis"],
    )
    check(
        "T2-4",
        "differences and coverage limits are surfaced as warnings",
        any(warning["code"] in ("coverage_mismatch", "verification_asymmetry", "provisional_attribution_present") for warning in compare["warnings"]),
        ", ".join(warning["code"] for warning in compare["warnings"]),
    )
    markdown = client.get("/api/export/compare.md", params={"orgs": "medtronic,ge_healthcare"})
    body = markdown.text
    check(
        "T2-5",
        "the exported report matches the screen (window, basis, disclaimer, verification table)",
        markdown.status_code == 200
        and compare["window"]["effective"]["from"] in body
        and "Ownership basis: current_group" in body
        and "Attribution verification" in body
        and "not a measure of innovation" in body,
        str(len(body)) + " bytes",
    )

    # ---------------------------------------------------------------- Task 3
    review_db = Path(tempfile.mkdtemp()) / "review.db"
    admin = TestClient(create_admin_app(review_db=review_db, token="smoke-token"))
    headers = {"X-MedRadar-Review-Token": "smoke-token"}
    applicant = "Abbott Vascular-Cardiac Therapies dba Guidant Corporation"
    case = admin.get("/api/review/case/" + applicant, headers=headers).json()
    check(
        "T3-1",
        "the reviewer can see the original evidence and the current mapping",
        case["record_count"] > 0 and case["sample_records"] and case["current"]["status"] in ("proposed", "unattributed"),
        str(case["record_count"]) + " records, flags " + ",".join(flag["code"] for flag in case["risk_flags"]),
    )
    before = admin.get("/api/review/impact", headers=headers).json()
    decision = admin.post(
        "/api/review/decisions",
        headers=headers,
        json={
            "applicant_name": applicant,
            "action": "approve",
            "status": "evidence_verified",
            "organization_key": "abbott",
            "reviewer": "smoke-reviewer",
            "evidence_type": "regulator_record",
            "evidence": [{"evidence_type": "regulator_record", "url": case["sample_records"][0]["official_url"], "title": "openFDA record naming the applicant", "quote": "applicant: " + applicant}],
            "note": "the applicant string names Abbott Vascular (dba Guidant Corporation)",
        },
    ).json()
    uid = decision["decision"]["decision_uid"]
    check("T3-2", "the reviewer can record a decision with evidence and a reason", decision["ok"] and bool(uid), uid[:12])
    after = admin.get("/api/review/impact", headers=headers).json()
    changed = {row["organization_key"]: row for row in after["changed_organizations"]}
    check("T3-3", "the correction changes the target organization and only that one", list(changed) == ["abbott"], json.dumps(changed))
    check("T3-4", "every other organization's count is unchanged", after["unchanged_organizations"] >= 50, str(after["unchanged_organizations"]) + " organizations unchanged")
    case_after = admin.get("/api/review/case/" + applicant, headers=headers).json()
    check(
        "T3-5",
        "the old decision record is preserved in the history",
        len(case_after["history"]) == 1 and case_after["history"][0]["decision_uid"] == uid,
        str(len(case_after["history"])) + " history entry",
    )
    revoke = admin.post("/api/review/decisions/" + uid + "/revoke", headers=headers, json={"reviewer": "smoke-reviewer", "note": "smoke test withdrawal"})
    case_restored = admin.get("/api/review/case/" + applicant, headers=headers).json()
    check(
        "T3-6",
        "a review decision can be withdrawn without deleting history",
        revoke.status_code == 200 and case_restored["current"]["organization_key"] is None and len(case_restored["history"]) == 2,
        str(len(case_restored["history"])) + " history entries",
    )

    # ---------------------------------------------------------------- summary
    passed = sum(1 for _id, _description, ok, _evidence in CHECKS if ok)
    print("\n" + str(passed) + "/" + str(len(CHECKS)) + " alpha checks passed")
    report = {
        "suite": "medradar-product-002-alpha-smoke",
        "checks": [{"id": i, "description": d, "passed": ok, "evidence": e} for i, d, ok, e in CHECKS],
        "passed": passed,
        "total": len(CHECKS),
    }
    out = ROOT / "build" / "alpha-smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
