"""Probe: can this environment reach ClinicalTrials.gov API v2 from Python?

B-040 needs lawful, rate-limited collection of device trials. This probe checks connectivity
and the response shape only — one request, no bulk download.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

BASE = "https://clinicaltrials.gov/api/v2/studies"


def main() -> int:
    params = {
        "query.spons": "Medtronic",
        "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
        "pageSize": "3",
        "fields": ("NCTId,BriefTitle,LeadSponsorName,StudyFirstPostDate,"
                   "InterventionType,InterventionName,InterventionDescription,OverallStatus"),
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    print("GET", url)
    request = urllib.request.Request(url, headers={"User-Agent": "MedRadar-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print("status:", response.status)
            payload = json.load(response)
    except Exception as exc:  # noqa: BLE001
        print("REQUEST FAILED:", type(exc).__name__, exc)
        return 1
    studies = payload.get("studies", [])
    print("studies returned:", len(studies), "| totalCount:", payload.get("totalCount"))
    for study in studies:
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        sponsor = protocol.get("sponsorCollaboratorsModule", {})
        status = protocol.get("statusModule", {})
        arms = protocol.get("armsInterventionsModule", {})
        interventions = arms.get("interventions", []) or []
        print(f"\n  {ident.get('nctId')} | {ident.get('briefTitle', '')[:70]}")
        print(f"    sponsor: {(sponsor.get('leadSponsor') or {}).get('name')}")
        print(f"    firstPost: {status.get('studyFirstPostDateStruct')}")
        for item in interventions[:4]:
            print(f"    intervention: {item.get('type')} | {item.get('name')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
