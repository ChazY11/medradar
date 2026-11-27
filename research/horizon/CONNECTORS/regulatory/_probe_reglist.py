"""Find the working openFDA registrationlisting search field, then quit."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from CONNECTORS.regulatory._util import make_client, fetch_or_load  # noqa: E402


def main() -> int:
    with make_client("regulatory-reglist-probe", max_requests=4,
                     max_bytes_per_response=2_000_000, max_total_bytes=4_000_000,
                     rps=1.0) as c:
        for name, url in [
            ("reglist_sample.json", "https://api.fda.gov/device/registrationlisting.json?limit=1"),
            ("reglist_q_firm.json",
             'https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name%3A%22MEDTRONIC%22&limit=3'),
        ]:
            rec, body = fetch_or_load(c, "openfda_device_registrationlisting", name, url, "field probe")
            print(name, rec["status"], rec["bytes"], "from_disk" if rec.get("from_disk") else "fetched")
            doc = json.loads(body.decode("utf-8"))
            if "error" in doc:
                print("  ERROR:", doc["error"])
                continue
            res = doc.get("results") or []
            print("  results:", len(res), "total:", (doc.get("meta") or {}).get("results", {}).get("total"))
            if res:
                r = res[0]
                print("  top keys:", sorted(r))
                reg = r.get("registration") or {}
                print("  registration keys:", sorted(reg))
                print("  owner_operator:", json.dumps(reg.get("owner_operator"), ensure_ascii=False)[:300])
                if len(res) > 1:
                    print("  firm:", (res[1].get("registration") or {}).get("owner_operator", {}).get("firm_name"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
