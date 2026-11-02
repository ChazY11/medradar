"""Check whether the now-reachable patents endpoints return usable JSON, and what a small firm query yields."""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request

ENDPOINTS = {
    "patentsview_legacy": "https://api.patentsview.org/patents/query",
    "patentsview_new": "https://search.patentsview.org/api/v1/patent/",
}


def fetch(url: str, timeout: int = 25) -> tuple[int | None, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "medradar-study/1.0 (research)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=ssl.create_default_context()) as response:
            body = response.read(2000).decode("utf-8", "replace")
            return response.status, body
    except Exception as error:  # noqa: BLE001 - diagnostic probe
        return None, f"{type(error).__name__}: {error}"[:300]


print("== simple GET on the legacy query endpoint ==")
status, body = fetch(ENDPOINTS["patentsview_legacy"])
print("status:", status)
print("body[:300]:", body[:300].replace("\n", " "))

print("\n== simple GET on the new search endpoint (no key) ==")
status, body = fetch(ENDPOINTS["patentsview_new"])
print("status:", status)
print("body[:300]:", body[:300].replace("\n", " "))

print("\n== POST-style query via GET with assignee filter (legacy) ==")
query = json.dumps({"_and": [{"_contains": {"assignee_organization": "MEDTRONIC"}}],
                    "_fields": ["patent_number", "patent_date", "assignee_organization"],
                    "size": 2})
url = ENDPOINTS["patentsview_legacy"] + "?q=" + urllib.parse.quote(query)
status, body = fetch(url)
print("status:", status)
print("body[:400]:", body[:400].replace("\n", " "))
