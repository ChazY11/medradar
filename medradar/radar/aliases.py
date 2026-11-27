"""Chinese names for the manufacturers a reader is most likely to type, and what to search instead.

The defect this fixes
--------------------
Measured in the browser: `/device?query=美敦力` and `/company?q=美敦力` both answer "没有找到「美敦力」
… 这个标识不在设备注册表里". The register stores manufacturers' English legal names as filed with the
FDA, so a Chinese name cannot match - but the page said the *identifier* was not in the register, which
reads as "this product has never heard of Medtronic". For a Chinese-speaking medical-device engineer
that is the most likely first action and it was a dead end with a misleading reason.

What this table is, and is not
------------------------------
It is a convenience: a handful of well-known companies' Chinese names next to the English name their
FDA filings use. It is **not** register data, it is not complete, and it is not a translation service.
The page says so where it is used. Anything not in the table still gets the honest advice - the
register is in English - rather than a guess.
"""

from __future__ import annotations

from typing import Any

#: (Chinese name, what to search, the English name a reader will recognise)
ALIASES: tuple[tuple[str, str, str], ...] = (
    ("美敦力", "Medtronic", "Medtronic"),
    ("捷迈", "Zimmer", "Zimmer Biomet"),
    ("邦美", "Biomet", "Zimmer Biomet"),
    ("史赛克", "Stryker", "Stryker"),
    ("强生", "Johnson", "Johnson & Johnson"),
    ("德普伊", "DePuy", "DePuy Synthes"),
    ("辛迪思", "Synthes", "DePuy Synthes"),
    ("施乐辉", "Smith & Nephew", "Smith & Nephew"),
    ("百特", "Baxter", "Baxter"),
    ("贝朗", "B. Braun", "B. Braun"),
    ("费森尤斯", "Fresenius", "Fresenius"),
    ("飞利浦", "Philips", "Philips"),
    ("西门子", "Siemens", "Siemens Healthineers"),
    ("通用电气", "GE Healthcare", "GE HealthCare"),
    ("雅培", "Abbott", "Abbott"),
    ("波士顿科学", "Boston Scientific", "Boston Scientific"),
    ("碧迪", "Becton", "Becton Dickinson"),
    ("柯惠", "Covidien", "Covidien"),
    ("泰尔茂", "Terumo", "Terumo"),
    ("欧姆龙", "Omron", "Omron"),
    ("迈瑞", "Mindray", "Mindray"),
    ("威高", "Weigao", "Weigao"),
    ("乐普", "Lepu", "Lepu Medical"),
    ("微创", "MicroPort", "MicroPort"),
    ("联影", "United Imaging", "United Imaging"),
)


def has_cjk(text: str) -> bool:
    """True when the query contains CJK characters, i.e. it cannot be an FDA legal name."""
    return any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in str(text or ""))


def lookup(text: str) -> list[dict[str, Any]]:
    """Aliases whose Chinese name appears in the query, longest match first."""
    query = str(text or "")
    hits = []
    for chinese, search_as, english in ALIASES:
        if chinese and chinese in query:
            hits.append({"chinese": chinese, "search_as": search_as, "english": english,
                         "length": len(chinese)})
    return sorted(hits, key=lambda item: -item["length"])


__all__ = ["ALIASES", "has_cjk", "lookup"]
