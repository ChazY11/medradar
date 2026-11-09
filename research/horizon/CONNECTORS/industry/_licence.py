"""Licence evidence collector.

``registry/sources/<id>.json`` must contain a ``licence_note`` that quotes the
actual sentence relied on. This module fetches the one page per source that
carries that sentence, stores it verbatim under
``DATASETS/industry/<source_id>/raw/`` and extracts candidate sentences so the
quote in the registry is human-verified against a stored byte sequence rather
than recalled from memory.

Run:

    python CONNECTORS/industry/_licence.py
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from _util import (  # noqa: E402
    make_client, save_fetch, write_json, utc_now, DATASETS,
)

# One page per source: the licence/terms statement we will quote.
TARGETS: list[tuple[str, str, str]] = [
    ("un_comtrade", "https://comtradeplus.un.org/TermsOfUse", "terms_of_use.html"),
    ("un_comtrade", "https://comtradeapi.un.org/", "api_root.html"),
    ("eurostat_comext", "https://ec.europa.eu/eurostat/help/copyright-notice", "copyright_notice.html"),
    ("uk_hmrc_trade", "https://www.uktradeinfo.com/", "portal_home.html"),
    ("usaspending", "https://www.usaspending.gov/about", "about.html"),
    ("eu_ted", "https://docs.ted.europa.eu/api/latest/index.html", "api_docs_index.html"),
    ("us_census_trade", "https://www.census.gov/foreign-trade/index.html", "foreign_trade_index.html"),
    ("sam_gov", "https://open.gsa.gov/api/sam-entity-extracts-api/", "sam_extracts_docs.html"),
    ("usitc_dataweb", "https://dataweb.usitc.gov/", "landing.html"),
    ("importyeti", "https://www.importyeti.com/policies", "policies.html"),
    ("importgenius", "https://www.importgenius.com/utilities/legal/terms-of-use", "terms_of_use.html"),
    ("panjiva", "https://panjiva.com/", "home.html"),
    ("descartes_datamyne", "https://www.descartes.com/legal-compliance", "legal_compliance.html"),
]

# Sentences we want to see, per source. Purely a grep aid for the analyst.
PATTERNS = {
    "un_comtrade": r"(?i)(free of charge|non-commercial|cite|citation|licen[cs]e|terms)",
    "eurostat_comext": r"(?i)(reuse|re-use|licen[cs]e|CC BY|copyright|free of charge)",
    "uk_hmrc_trade": r"(?i)(licen[cs]e|Open Government|OGL|copyright|re-?use|terms)",
    "usaspending": r"(?i)(public domain|copyright|licen[cs]e|data\.gov|free)",
    "eu_ted": r"(?i)(re-?use|licen[cs]e|decision|open data|copyright)",
    "us_census_trade": r"(?i)(public domain|copyright|licen[cs]e|free)",
    "sam_gov": r"(?i)(public domain|licen[cs]e|terms|api key|registration|role)",
    "importyeti": r"(?i)(automated|scrap|robot|crawl|resell|redistribut|licen[cs]e|commercial)",
    "importgenius": r"(?i)(automated|scrap|robot|crawl|reproduce|licen[cs]e|commercial)",
    "panjiva": r"(?i)(subscription|licen[cs]e|automated|scrap|commercial|terms)",
    "descartes_datamyne": r"(?i)(subscription|licen[cs]e|terms|EULA|commercial)",
}


def _plain(html: str) -> str:
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;?", " ", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def main() -> int:
    prov: list[dict] = []
    out: dict[str, dict] = {}
    with make_client("industry_licence", max_requests=20, max_total_bytes=12_000_000) as client:
        for source_id, url, name in TARGETS:
            try:
                res = client.get(url)
            except Exception as exc:  # transport / budget
                out.setdefault(source_id, {"pages": []})["pages"].append(
                    {"url": url, "status": None, "error": f"{type(exc).__name__}: {exc}"}
                )
                continue
            p = save_fetch(source_id, name, res, note=f"licence evidence for {source_id}")
            prov.append(p)
            entry = {
                "url": url,
                "final_url": res.final_url,
                "status": res.status,
                "bytes": len(res.body),
                "sha256": p["sha256"],
                "raw_path": p["path"],
                "sentences": [],
            }
            if res.ok:
                text = _plain(res.text())
                pat = re.compile(PATTERNS.get(source_id, r"(?i)licen[cs]e"))
                seen: set[str] = set()
                for m in pat.finditer(text):
                    s = max(0, m.start() - 260)
                    frag = text[s:m.start() + 320].strip()
                    key = frag[:80]
                    if key in seen:
                        continue
                    seen.add(key)
                    entry["sentences"].append(frag)
                    if len(entry["sentences"]) >= 6:
                        break
            out.setdefault(source_id, {"pages": []})["pages"].append(entry)

    doc = {
        "generated_at": utc_now(),
        "purpose": (
            "Raw licence/terms pages plus extracted candidate sentences. The "
            "registry's licence_note must quote one of these strings; the "
            "sha256 lets a reviewer confirm the page has not changed."
        ),
        "by_source": out,
    }
    path = os.path.join(DATASETS, "LICENCE_EVIDENCE.json")
    os.makedirs(DATASETS, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"written {path}")
    for sid, d in sorted(out.items()):
        for pg in d["pages"]:
            print(f"  {sid:20} {pg.get('status')}  {len(pg.get('sentences', []))} sentences  {pg['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
