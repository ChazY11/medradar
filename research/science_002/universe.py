"""Universe construction and cross-source entity resolution for SCIENCE-002.

The unit of the study is one **SEC registrant (issuer)**; its FDA outcomes are the
510(k) clearances attributable to it. Attribution is the most fragile step in the
design, so it is rule-based, auditable and tiered, and no tier is ever inferred
from name similarity.

Attribution tiers (every tier requires *exact* equality of normalised token
strings - see entity.normalise_name)
------------------------------------
T_A   the 510(k) applicant string normalises to the registrant's current SEC title;
T_A2  ... to a *former* name SEC publishes in the registrant's own submissions
      record (SEC asserts the name and the rename interval);
T_B   the applicant string equals an FDA **establishment registration** name whose
      FDA-published **owner/operator firm name** normalises to the registrant's
      SEC title. Both hops are exact string equality; the corporate relation is
      FDA's own statement, not ours.

Tier B carries a temporal limitation stated wherever it is used: the
registration/listing export is a **2026 snapshot**, so a 2015 clearance is
attributed to whoever owns that establishment *now*. The attribution is held
constant across the whole panel, so it never changes inside a firm's time series
(there is no attribution jump at an acquisition date), but the group composition
is the 2026 one. Sensitivity S1 reruns the main analysis on T_A+T_A2 only.

Nothing here decides that two *similar* names are one company. An applicant
string that could belong to more than one universe firm is dropped from all of
them and recorded in the exclusion ledger.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import fda, sec
from .entity import SecRegistrant, normalise_name
from .sources import Cache

#: SEC SIC codes accepted as "medical device / IVD instrument" primary business.
#: Pre-declared; never adjusted after looking at outcomes.
DEVICE_SIC: dict[str, str] = {
    "3841": "Surgical & Medical Instruments & Apparatus",
    "3842": "Orthopedic, Prosthetic & Surgical Appliances & Supplies",
    "3843": "Dental Equipment & Supplies",
    "3844": "X-Ray Apparatus & Tubes & Related Irradiation Apparatus",
    "3845": "Electromedical & Electrotherapeutic Apparatus",
    "3851": "Ophthalmic Goods",
    "3826": "Laboratory Analytical Instruments (IVD analysers)",
}
DEVICE_SIC_WITHOUT_3826: dict[str, str] = {k: v for k, v in DEVICE_SIC.items() if k != "3826"}

WINDOW_START = "2015-01-01"
WINDOW_END = "2026-08-31"
MIN_WINDOW_CLEARANCES = 8


@dataclass
class UniverseFirm:
    key: str
    cik: str
    ticker: str
    sec_title: str
    sic: str
    sic_description: str
    applicants: list[dict[str, Any]] = field(default_factory=list)
    n_window_clearances: int = 0
    former_names: tuple = ()

    @property
    def tiers(self) -> set[str]:
        return {str(a["tier"]) for a in self.applicants}

    @property
    def tier_str(self) -> str:
        return "+".join(sorted(self.tiers))

    def as_row(self) -> dict[str, str]:
        return {
            "key": self.key, "cik": self.cik, "ticker": self.ticker,
            "sec_title": self.sec_title, "sic": self.sic,
            "sic_description": self.sic_description,
            "tiers": self.tier_str,
            "n_window_clearances": str(self.n_window_clearances),
            "applicants": "|".join(sorted({str(a["applicant"]) for a in self.applicants})),
        }


def load_tickers(cache: Cache) -> dict[str, list[dict[str, Any]]]:
    payload = cache.get_json(sec.TICKERS_URL)
    roots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.values():
        root = normalise_name(row["title"])
        if root:
            roots[root].append({"cik": "%010d" % int(row["cik_str"]),
                                "title": row["title"], "ticker": row["ticker"]})
    return roots


def load_owner_map(path: Path) -> dict[str, set[str]]:
    """registration-name root -> set of owner-firm roots (as FDA publishes them)."""
    owners: dict[str, set[str]] = defaultdict(set)
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            reg_root = normalise_name(row["registration_name"])
            own_root = normalise_name(row["owner_firm"])
            if reg_root and own_root:
                owners[reg_root].add(own_root)
    return owners


def window_clearance_counts(records: Iterable[Mapping[str, str]],
                            start: str = WINDOW_START,
                            end: str = WINDOW_END) -> Counter:
    counts: Counter = Counter()
    for row in records:
        day = row.get("decision_date") or ""
        if not day or not (start <= day <= end):
            continue
        if (row.get("decision_code") or "") not in fda.CLEARED_DECISION_CODES:
            continue
        root = normalise_name(row.get("applicant") or "")
        if root:
            counts[root] += 1
    return counts


def candidate_roots(counts: Mapping[str, int], sec_roots: Mapping[str, Any],
                    owners: Mapping[str, set[str]], min_clearances: int) -> set[str]:
    """SEC registrant roots that could own >= min_clearances clearances.

    Candidate only: this filter decides which registrants to *investigate*, not
    which mappings are accepted.
    """
    out: set[str] = set()
    for root, n in counts.items():
        if n < min_clearances:
            continue
        if root in sec_roots:
            out.add(root)
        for owner in owners.get(root, ()):
            if owner in sec_roots:
                out.add(owner)
    return out


def propose_matches(registrants: Sequence[SecRegistrant],
                    counts: Mapping[str, int],
                    owners: Mapping[str, set[str]],
                    include_tier_b: bool = True) -> list[dict[str, Any]]:
    """Every attribution a rule can propose, before ambiguity resolution."""
    out: list[dict[str, Any]] = []
    for reg in registrants:
        current = normalise_name(reg.title)
        formers = {normalise_name(name): name for name, _frm, _to in reg.former_names
                   if normalise_name(name)}
        for art_root, n in counts.items():
            if art_root == current:
                out.append({"cik": reg.cik, "sec_title": reg.title, "tier": "T_A",
                            "applicant_root": art_root, "applicant": art_root,
                            "owner_root": current,
                            "evidence": "FDA applicant name == SEC registrant name",
                            "n_window_clearances": n})
            elif art_root in formers:
                out.append({"cik": reg.cik, "sec_title": reg.title, "tier": "T_A2",
                            "applicant_root": art_root, "applicant": art_root,
                            "owner_root": current,
                            "evidence": "FDA applicant name == SEC former name: " + formers[art_root],
                            "n_window_clearances": n})
            elif include_tier_b:
                for owner in sorted(owners.get(art_root, ())):
                    if owner == current:
                        out.append({"cik": reg.cik, "sec_title": reg.title, "tier": "T_B",
                                    "applicant_root": art_root, "applicant": art_root,
                                    "owner_root": current,
                                    "evidence": "FDA registration owner/operator == SEC registrant name",
                                    "n_window_clearances": n})
    return out


def resolve_ambiguity(proposals: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Drop any applicant string claimed by more than one registrant."""
    claims: dict[str, set[str]] = defaultdict(set)
    for row in proposals:
        claims[str(row["applicant_root"])].add(str(row["cik"]))
    accepted: list[dict[str, Any]] = []
    ledger: list[dict[str, str]] = []
    for row in proposals:
        owners = claims[str(row["applicant_root"])]
        if len(owners) > 1:
            ledger.append({"applicant_root": str(row["applicant_root"]),
                           "cik": str(row["cik"]), "sec_title": str(row["sec_title"]),
                           "tier": str(row["tier"]), "status": "ambiguous_applicant",
                           "reason": "claimed by CIKs " + ",".join(sorted(owners))})
        else:
            accepted.append(dict(row))
    return accepted, ledger


def firms_from_matches(matches: Sequence[Mapping[str, Any]],
                       subs: Mapping[str, sec.Submissions],
                       tickers: Mapping[str, str]) -> dict[str, UniverseFirm]:
    by_cik: dict[str, UniverseFirm] = {}
    for row in matches:
        cik = str(row["cik"])
        firm = by_cik.get(cik)
        if firm is None:
            sub = subs.get(cik)
            title = str(row["sec_title"])
            key = normalise_name(title).lower().replace(" ", "-") or cik
            firm = UniverseFirm(key=key, cik=cik, ticker=tickers.get(cik, ""),
                                sec_title=title,
                                sic=sub.sic if sub else "",
                                sic_description=sub.sic_description if sub else "",
                                former_names=sub.former_names if sub else ())
            by_cik[cik] = firm
        firm.applicants.append(dict(row))
        firm.n_window_clearances += int(row["n_window_clearances"])
    return by_cik


def eligibility(firm: UniverseFirm, subs: sec.Submissions | None,
                facts: sec.CompanyFacts | None, sic_set: Mapping[str, str],
                min_clearances: int = MIN_WINDOW_CLEARANCES,
                coverage_floor: str = "2020-01-01") -> tuple[bool, str]:
    """Apply the pre-declared inclusion rules; return (included, reason)."""
    if subs is None:
        return False, "no SEC submissions record"
    if firm.sic not in sic_set:
        return False, "SIC " + firm.sic + " (" + firm.sic_description + ") not in the pre-declared device set"
    if firm.n_window_clearances < min_clearances:
        return False, str(firm.n_window_clearances) + " attributable clearances in window < " + str(min_clearances)
    if facts is None or not facts.rd:
        return False, "no XBRL ResearchAndDevelopmentExpense facts"
    if not any(f.form in sec.EIGHT_K_FORMS and f.acceptance_utc is not None for f in subs.filings):
        return False, "no 8-K with a verified acceptance instant"
    return True, "included"


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(fields)]
    for row in rows:
        cells = []
        for name in fields:
            value = str(row.get(name, ""))
            if any(ch in value for ch in ',"\n'):
                value = '"' + value.replace('"', '""') + '"'
            cells.append(value)
        lines.append(",".join(cells))
    data = ("\n".join(lines) + "\n").encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()