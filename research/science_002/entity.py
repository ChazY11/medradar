"""Deterministic cross-source entity resolution: SEC registrant <-> FDA 510(k) applicant.

Design rule: an automated rule may *propose* a pair; it may never *decide* that two
similar names are one company. Every accepted pair therefore carries the literal
evidence strings, the rule that fired, and a confidence tier, and only the
highest tier enters the primary experiment. Everything else is written to an
exclusion ledger with the reason.

Normalisation (deliberately blunt and fully reversible)
-------------------------------------------------------
1. upper-case;
2. '&' -> ' AND ';
3. every non-alphanumeric character -> single space;
4. drop corporate-form / jurisdiction tokens (INC, CORP, LLC, PLC, ... and the
   state-of-incorporation tokens firms append: DE, MD, NJ, ...);
5. drop pure generic tokens (THE, HOLDINGS, GROUP, ...). These are dropped from
   *both* sides, so 'ZIMMER BIOMET HOLDINGS' and 'ZIMMER BIOMET' agree;
6. collapse whitespace.

Two names match only when the surviving token strings are *identical*. No fuzzy
ratio, no token-subset rule, no edit distance: 'BAXTER HEALTHCARE' and 'BAXTER
INTERNATIONAL' do not match, and are reported as unmatched rather than guessed.

Tiers
-----
T_A  applicant root == the registrant's current SEC title root
T_A2 applicant root == a *former* name root published by SEC in the registrant's
     own submissions record (SEC asserts the identity and the rename date)
T_C  applicant root == the registrant's title root but more than one CIK claims
     that root -> ambiguous, excluded

Only T_A and T_A2 are eligible for the primary experiment. T_C and unmatched
applicants are retained in the ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

#: Corporate-form and generic tokens that carry no identity on either side.
SUFFIX_TOKENS = frozenset(
    """
    INC INCORPORATED CORP CORPORATION CO COMPANY LLC LLP LP LTD LIMITED PLC
    GMBH MBH AG SA SAS SPA NV BV AB ASA OY OYJ KK PTY PTE SARL SRL KG
    HOLDINGS HOLDING GROUP GRP THE USA US NA
    DE MD NJ PA NY CA MA IL MN IN OH WI MI FL TX GA MO CT
    """.split()
)

_TOKEN = re.compile(r"[^A-Z0-9]+")


def _raw_tokens(text: str) -> list[str]:
    up = (text or "").upper().replace("&", " AND ")
    up = _TOKEN.sub(" ", up)
    return [t for t in up.split() if t]


def normalise_name(text: str) -> str:
    tokens = [t for t in _raw_tokens(text) if t not in SUFFIX_TOKENS]
    return " ".join(tokens)


def name_tokens(text: str) -> frozenset[str]:
    return frozenset(normalise_name(text).split())


@dataclass(frozen=True)
class SecRegistrant:
    cik: str
    title: str
    ticker: str = ""
    sic: str = ""
    sic_description: str = ""
    former_names: tuple[tuple[str, str, str], ...] = ()  # (name, from, to) as SEC publishes


@dataclass
class Match:
    cik: str
    sec_title: str
    applicant: str
    applicant_root: str
    sec_root: str
    tier: str
    rule: str
    n_510k: int = 0
    first_decision: str = ""
    last_decision: str = ""
    note: str = ""
    matched_via: str = ""  # which SEC name produced the match

    def as_row(self) -> dict[str, str]:
        return {
            "cik": self.cik, "sec_title": self.sec_title, "applicant": self.applicant,
            "applicant_root": self.applicant_root, "sec_root": self.sec_root,
            "tier": self.tier, "rule": self.rule, "n_510k": str(self.n_510k),
            "first_decision": self.first_decision, "last_decision": self.last_decision,
            "matched_via": self.matched_via, "note": self.note,
        }


def match_registrant(reg: SecRegistrant, applicants: Mapping[str, Mapping[str, object]]) -> list[Match]:
    """Return every FDA applicant string this registrant can claim, with its tier."""
    out: list[Match] = []
    current_root = normalise_name(reg.title)
    for key, entry in applicants.items():
        applicant = str(entry.get("applicant") or key)
        root = normalise_name(applicant)
        if not root:
            continue
        if root == current_root:
            out.append(Match(reg.cik, reg.title, applicant, root, current_root, "T_A",
                             "applicant root == current SEC title root",
                             int(entry.get("n", 0)),
                             str(entry.get("first_decision") or ""),
                             str(entry.get("last_decision") or ""),
                             matched_via=reg.title))
            continue
        for former, _frm, _to in reg.former_names:
            froot = normalise_name(former)
            if froot and root == froot:
                out.append(Match(reg.cik, reg.title, applicant, root, froot, "T_A2",
                                 "applicant root == SEC-published former name root",
                                 int(entry.get("n", 0)),
                                 str(entry.get("first_decision") or ""),
                                 str(entry.get("last_decision") or ""),
                                 matched_via=former))
                break
    return out


def resolve(registrants: Sequence[SecRegistrant],
            applicants: Mapping[str, Mapping[str, object]]) -> tuple[list[Match], list[dict[str, str]]]:
    """Match every registrant; return (accepted matches, exclusion ledger)."""
    accepted: list[Match] = []
    ledger: list[dict[str, str]] = []
    # reverse map: root -> cik(s) claiming it, to detect ambiguity
    claim: dict[str, set[str]] = {}
    per_reg: dict[str, list[Match]] = {}
    for reg in registrants:
        matches = match_registrant(reg, applicants)
        per_reg[reg.cik] = matches
        roots = {normalise_name(reg.title)} | {normalise_name(n) for n, _a, _b in reg.former_names}
        for root in roots:
            if root:
                claim.setdefault(root, set()).add(reg.cik)

    for reg in registrants:
        for match in per_reg.get(reg.cik, []):
            owners = claim.get(match.applicant_root, set())
            if len(owners) > 1:
                match.tier = "T_C"
                match.rule = "root claimed by %d CIKs" % len(owners)
                match.note = "ambiguous: " + ",".join(sorted(owners))
                ledger.append({**match.as_row(), "status": "ambiguous_root",
                               "reason": match.note})
            else:
                accepted.append(match)
    return accepted, ledger
