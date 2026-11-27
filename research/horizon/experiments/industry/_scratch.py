"""Scratch reconnaissance for the INDUSTRY workstream.

Not a deliverable: this is the exploratory tool used to find out which
endpoints actually answer before they are frozen into
``hz/suites_industry.py``.  It still goes through ``hz.http.BoundedClient`` and
still appends to the industry request log, so the audit trail is complete.

    python experiments/industry/_scratch.py get <url> [--bytes N]
    python experiments/industry/_scratch.py post <url> <json-file>
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # research/horizon
sys.path.insert(0, ROOT)

from hz.http import BoundedClient  # noqa: E402

LOG = os.path.join(ROOT, "SOURCE_PROBES", "industry", "REQUEST_LOG.jsonl")


def client(max_bytes: int = 4_000_000) -> BoundedClient:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    return BoundedClient(
        name="industry_scratch",
        max_requests=8,
        max_bytes_per_response=max_bytes,
        max_total_bytes=40_000_000,
        requests_per_second=1.5,
        log_path=LOG,
    )


def show(res, head: int = 1200) -> None:
    print(f"STATUS {res.status}  bytes={len(res.body)}  ct={res.headers.get('content-type')}")
    print(f"FINAL  {res.final_url}")
    txt = res.text()
    print("---- head ----")
    print(txt[:head])
    print("---- tail ----")
    print(txt[-400:])


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    mode, url = argv[1], argv[2]
    nbytes = 4_000_000
    if "--bytes" in argv:
        nbytes = int(argv[argv.index("--bytes") + 1])
    if mode == "get":
        with client(nbytes) as c:
            res = c.get(url)
            show(res)
        return 0
    if mode == "post":
        path = argv[3]
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        import requests

        s = requests.Session()
        from hz.http import DEFAULT_UA

        s.headers.update({"User-Agent": DEFAULT_UA, "Content-Type": "application/json"})
        r = s.post(url, json=payload, timeout=60)
        body = r.content
        print(f"STATUS {r.status_code}  bytes={len(body)}  ct={r.headers.get('content-type')}")
        txt = body.decode("utf-8", errors="replace")
        print(txt[:2000])
        print("...TAIL...")
        print(txt[-500:])
        import hashlib

        entry = {
            "client": "industry_scratch_post",
            "url": url,
            "status": r.status_code,
            "outcome": "OK" if 200 <= r.status_code < 300 else "HTTP_ERROR",
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "method": "POST",
            "request_body_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
        }
        with open(LOG, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return 0
    print(f"unknown mode {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
