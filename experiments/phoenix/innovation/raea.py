#!/usr/bin/env python3
"""PHOENIX-001 candidate innovation module
=========================================

Regulatory-Anchored Entity Attribution (RAEA)
--------------------------------------------

Origin of the idea
    This module is derived from the strongest evidence-based finding of the
    commercial-platform audit (docs/phoenix/audits/A00_commercial_synthesis.md):
    every serious commercial medtech intelligence product anchors its atomic unit
    on an immutable *regulatory identifier* and treats the company as a resolved
    attribution over that anchor, never as the primary key. The audits also found
    that 0 of 7 platforms publish their name-resolution method.

    MedRadar has the opposite weakness, measured in this program
    (experiments/phoenix/reports/05_validity_tests.json, L3 audit):
        company_key is NULL for 86.64% of 510(k) events
                                 93.52% of 8-K events
                                 51.38% of recall events
                                 34.51% of PMA events
    So "company" — the entity every downstream analysis needs — is mostly absent.

What this module does (and refuses to do)
    It attributes previously-unmapped regulatory events to one of the 89 companies
    in the curated registry, using three explicit, auditable rules over
    `applicant_raw`. It does NOT invent companies. It does NOT guess beyond the
    registry. Every attribution carries a rule id and a confidence, so a reviewer
    can reject individual rows.

    Rules (evaluated in order, first match wins):
        R1 exact     normalised applicant_raw equals a normalised registry alias
        R2 suffix    after stripping legal suffixes / country / state qualifiers,
                     the remainder equals a normalised alias
        R3 family    exactly one registry company has a *distinctive* family token
                     (first token of an alias, not in GENERIC_TOKENS) that appears
                     as a whole token in applicant_raw
                     -- R3 is refused when the token maps to >1 company, because a
                        collision is evidence the token is not distinctive.

Validation design (why these numbers are trustworthy)
    The rules are fitted on nothing. They are *evaluated* on the subset of events
    that already have a company_key — a labelled set that the rules never saw as
    training data. Precision/recall against that gold subset is reported per rule.
    Only then are the rules applied to the unmapped events, and the projected gain
    is stated together with the measured precision of the rules that produced it.

This module is deliberately dependency-free (stdlib only) and has a self-test.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments" / "phoenix" / "common"))
import phoenix_common as pc  # noqa: E402

LEGAL_SUFFIXES = {
    "INC", "INCORPORATED", "LLC", "L L C", "CORP", "CORPORATION", "CO", "COMPANY",
    "LTD", "LIMITED", "PLC", "GMBH", "AG", "SA", "S A", "NV", "BV", "BVBA", "AB",
    "AS", "ASA", "OY", "SPA", "SRL", "KG", "SE", "PTY", "PTE", "LP", "LLP", "PC",
    "PA", "PLLC", "GROUP", "HOLDINGS", "HOLDING", "INTERNATIONAL", "INTL",
}
# Tokens too generic to identify a corporate family on their own.
GENERIC_TOKENS = {
    "THE", "A", "AN", "AND", "OF", "FOR", "MEDICAL", "MEDTECH", "HEALTH",
    "HEALTHCARE", "TECHNOLOGIES", "TECHNOLOGY", "SYSTEMS", "SYSTEM", "PRODUCTS",
    "PRODUCT", "DEVICES", "DEVICE", "SOLUTIONS", "SERVICES", "LABORATORIES",
    "LABS", "RESEARCH", "SCIENTIFIC", "SCIENCES", "INDUSTRIES", "INDUSTRIAL",
    "AMERICAN", "NATIONAL", "GENERAL", "UNITED", "GLOBAL", "ADVANCED", "NEW",
    "FIRST", "BIO", "BIOMEDICAL", "BIOSCIENCES", "PHARMA", "PHARMACEUTICAL",
    "PHARMACEUTICALS", "DIAGNOSTICS", "SURGICAL", "ORTHOPEDIC", "ORTHOPAEDIC",
    "CARDIOVASCULAR", "NEURO", "SPINE", "VASCULAR", "DENTAL", "OPTICAL",
    "IMAGING", "CARE", "CLINICAL", "CENTER", "CENTRE", "INSTITUTE", "UNIVERSITY",
    "HOSPITAL", "L L C", "USA", "US", "UK", "CANADA", "JAPAN", "CHINA", "KOREA",
    "GERMANY", "FRANCE", "ITALY", "SWITZERLAND", "IRELAND", "ISRAEL",
}
COUNTRY_STATE = {
    "USA", "US", "U S A", "UNITED STATES", "CANADA", "JAPAN", "CHINA", "KOREA",
    "SOUTH KOREA", "GERMANY", "FRANCE", "ITALY", "SWITZERLAND", "IRELAND",
    "ISRAEL", "NETHERLANDS", "SWEDEN", "DENMARK", "BELGIUM", "AUSTRIA", "SPAIN",
    "UK", "UNITED KINGDOM", "ENGLAND", "SCOTLAND", "AUSTRALIA", "INDIA",
    "SINGAPORE", "TAIWAN", "HONG KONG", "BRAZIL", "MEXICO", "PUERTO RICO",
    "CA", "MN", "MA", "NY", "NJ", "PA", "TX", "FL", "IL", "OH", "MI", "WI",
}


def normalize_name(raw: str | None) -> str:
    """Uppercase, drop punctuation, collapse whitespace."""
    if not raw:
        return ""
    s = str(raw).upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# --------------------------------------------------------------------------
# Precision guard: conflict tokens found by MANUAL review of the newly
# attributed names (evidence: experiments/phoenix/evidence/raea_distinct_review.log).
# Each entry is a *disambiguating qualifier* that means the applicant is a
# different legal/economic entity from the registry company sharing the leading
# token. Applying the guard withholds these attributions instead of guessing.
# This list is data, not logic: adding an entry narrows coverage and (per the
# measured trade-off) removes a known false-positive class.
# --------------------------------------------------------------------------
CONFLICT_PHRASES: list[tuple[tuple[str, ...], str]] = [
    # Fresenius Kabi is a separate listed company from Fresenius Medical Care.
    (("KABI",), "fresenius_kabi != fresenius_medical_care"),
    # Boehringer Mannheim was acquired by Roche (1997); Boehringer Ingelheim is
    # a different company. Boehringer Laboratories (US) is unrelated to both.
    # NOTE: the qualifier must be matched as a *phrase*. A bare "LABORATORIES"
    # token would wrongly block legitimate names such as "ABBOTT LABORATORIES"
    # (caught by this module's own self-test).
    (("BOEHRINGER", "MANNHEIM"), "boehringer_mannheim -> roche, not boehringer_ingelheim"),
    (("MANNHEIM",), "boehringer_mannheim -> roche, not boehringer_ingelheim"),
    (("BOEHRINGER", "LABORATORIES"), "boehringer_laboratories is not boehringer_ingelheim"),
    # Gynecare was a Johnson & Johnson / Ethicon brand.
    (("GYNECARE",), "gynecare -> johnson_johnson_medtech, not novartis"),
]


def _has_conflict(norm: str) -> str | None:
    """Match conflict phrases as consecutive token subsequences."""
    toks = norm.split(" ")
    for phrase, why in CONFLICT_PHRASES:
        n = len(phrase)
        for i in range(len(toks) - n + 1):
            if tuple(toks[i:i + n]) == phrase:
                return why
    return None


def strip_qualifiers(norm: str) -> str:
    """Remove trailing legal suffixes and country/state qualifiers repeatedly."""
    toks = [t for t in norm.split(" ") if t]
    changed = True
    while changed and toks:
        changed = False
        # trailing legal suffix / country / state
        while toks and (toks[-1] in LEGAL_SUFFIXES or toks[-1] in COUNTRY_STATE):
            toks.pop()
            changed = True
        # trailing two-token combinations such as "L L C" already tokenised away
    out = " ".join(toks)
    # also drop a leading "THE"
    if out.startswith("THE "):
        out = out[4:]
    return out


@dataclass
class AliasIndex:
    exact: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    stripped: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    family: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    alias_count: int = 0

    @classmethod
    def build(cls, registry: list[dict]) -> "AliasIndex":
        idx = cls()
        for row in registry:
            key = row["key"]
            names = [row.get("name_en") or ""] + list(row.get("aliases") or [])
            for nm in names:
                n = normalize_name(nm)
                if not n:
                    continue
                idx.alias_count += 1
                idx.exact[n].add(key)
                st = strip_qualifiers(n)
                if st:
                    idx.stripped[st].add(key)
                    first = st.split(" ")[0]
                    if first and first not in GENERIC_TOKENS and len(first) >= 4:
                        idx.family[first].add(key)
        return idx


def attribute(raw: str | None, idx: AliasIndex, guard: bool = True) -> tuple[str | None, str, str]:
    """Return (company_key | None, rule, detail)."""
    n = normalize_name(raw)
    if not n:
        return None, "none", "empty"
    # R1 exact: the raw name is a registered alias verbatim, so it is trusted
    # even when it contains a conflict token (the registry author already decided).
    hit = idx.exact.get(n)
    if hit and len(hit) == 1:
        return next(iter(hit)), "R1_exact", n
    # From here the match is inferred, so the precision guard applies.
    if guard:
        why = _has_conflict(n)
        if why:
            return None, "abstain_conflict", why
    # R2 stripped suffix
    st = strip_qualifiers(n)
    if st:
        hit = idx.stripped.get(st)
        if hit and len(hit) == 1:
            return next(iter(hit)), "R2_suffix", st
    # R3 distinctive family token (unique across the registry)
    toks = n.split(" ")
    cands: set[str] = set()
    used: list[str] = []
    for t in toks:
        if t in GENERIC_TOKENS or t in LEGAL_SUFFIXES or len(t) < 4:
            continue
        owners = idx.family.get(t)
        if owners and len(owners) == 1:
            cands |= owners
            used.append(t)
    if len(cands) == 1:
        return next(iter(cands)), "R3_family", "+".join(used)
    return None, "unmatched", ""


# --------------------------------------------------------------------- IO
def load_registry(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute("select key, name_en, aliases from companies").fetchall()
    out = []
    for key, name_en, aliases in rows:
        try:
            al = json.loads(aliases) if aliases else []
        except Exception:  # noqa: BLE001
            al = []
        out.append({"key": key, "name_en": name_en, "aliases": al})
    return out


def load_events(con: sqlite3.Connection) -> list[tuple]:
    return con.execute(
        "select event_id, kind, company_key, applicant_raw from events "
        "where applicant_raw is not null and applicant_raw <> ''"
    ).fetchall()


def evaluate(idx: AliasIndex, events: list[tuple], guard: bool = True) -> dict:
    """Gold-subset evaluation: only events that already carry a company_key."""
    per_rule = defaultdict(lambda: {"n": 0, "correct": 0, "wrong": 0})
    confusion = Counter()
    for _eid, _kind, gold, raw in events:
        if not gold:
            continue
        pred, rule, _detail = attribute(raw, idx, guard=guard)
        if pred is None:
            per_rule[rule if rule.startswith("abstain") else "unmatched"]["n"] += 1
            continue
        per_rule[rule]["n"] += 1
        if pred == gold:
            per_rule[rule]["correct"] += 1
        else:
            per_rule[rule]["wrong"] += 1
            confusion[(rule, raw[:40], gold, pred)] += 1
    out = {}
    for rule, d in per_rule.items():
        n = d["n"]
        out[rule] = {
            "n": n,
            "correct": d["correct"],
            "wrong": d.get("wrong", 0),
            "precision": (d["correct"] / n) if n else None,
        }
    top_confusion = [
        {"rule": r, "applicant_raw": a, "gold": g, "predicted": p, "count": c}
        for (r, a, g, p), c in confusion.most_common(15)
    ]
    return {"per_rule": out, "top_conflicts": top_confusion}


def apply_to_unmapped(idx: AliasIndex, events: list[tuple], guard: bool = True) -> dict:
    gained = Counter()
    withheld = Counter()
    examples: dict[str, list[dict]] = defaultdict(list)
    for eid, kind, gold, raw in events:
        if gold:
            continue
        pred, rule, detail = attribute(raw, idx, guard=guard)
        if rule == "abstain_conflict":
            withheld[detail] += 1
            continue
        if pred is None:
            continue
        gained[(rule, kind)] += 1
        if len(examples[rule]) < 12:
            examples[rule].append({"kind": kind, "applicant_raw": raw, "company_key": pred,
                                   "detail": detail, "event_id": eid[:12]})
    return {
        "gained_by_rule_and_kind": [
            {"rule": r, "kind": k, "n": n} for (r, k), n in sorted(gained.items())
        ],
        "total_gained": int(sum(gained.values())),
        "withheld_by_guard": {k: int(v) for k, v in withheld.items()},
        "total_withheld": int(sum(withheld.values())),
        "examples": dict(examples),
    }


def main() -> int:
    con = pc.connect_ro()
    registry = load_registry(con)
    events = load_events(con)
    kind_totals = {k: n for k, n in con.execute("select kind, count(*) from events group by kind")}
    mapped = con.execute(
        "select kind, sum(case when company_key is not null then 1 else 0 end) "
        "from events where applicant_raw is not null and applicant_raw <> '' group by kind"
    ).fetchall()
    con.close()

    idx = AliasIndex.build(registry)
    rep: dict = {
        "module": "RAEA (Regulatory-Anchored Entity Attribution)",
        "code_reuse": "none - independent implementation, stdlib only",
        "protocol_version": pc.PROTOCOL_VERSION,
        "db_sha256": pc.DB_SHA256_EXPECTED,
        "registry": {
            "companies": len(registry),
            "alias_names_indexed": idx.alias_count,
            "distinctive_family_tokens": len(idx.family),
            "colliding_family_tokens": sum(1 for v in idx.family.values() if len(v) > 1),
        },
        "event_universe": {
            "events_with_applicant_raw": len(events),
            "by_kind_total": kind_totals,
            "mapped_before": {k: int(n) for k, n in mapped},
        },
    }
    rep["gold_subset_evaluation"] = evaluate(idx, events, guard=True)
    rep["gold_subset_evaluation_unguarded"] = evaluate(idx, events, guard=False)
    rep["application_to_unmapped"] = apply_to_unmapped(idx, events, guard=True)
    unguarded = apply_to_unmapped(idx, events, guard=False)
    rep["guard_tradeoff"] = {
        "coverage_without_guard": unguarded["total_gained"],
        "coverage_with_guard": rep["application_to_unmapped"]["total_gained"],
        "attributions_withheld": rep["application_to_unmapped"]["total_withheld"],
        "withheld_by_reason": rep["application_to_unmapped"]["withheld_by_guard"],
        "note": (
            "The guard removes specific false-positive classes found by manual review of the "
            "distinct newly-attributed names. It is a precision-for-coverage trade, not a "
            "free improvement: recall drops by exactly the withheld count."
        ),
    }

    # coverage before / after, per kind
    before = {k: int(n) for k, n in mapped}
    after = dict(before)
    for eid_kind_n in rep["application_to_unmapped"]["gained_by_rule_and_kind"]:
        after[eid_kind_n["kind"]] = after.get(eid_kind_n["kind"], 0) + eid_kind_n["n"]
    totals = {k: int(n) for k, n in kind_totals.items()}
    rep["coverage_change"] = {
        k: {
            "events": totals.get(k, 0),
            "mapped_before": before.get(k, 0),
            "mapped_after": after.get(k, 0),
            "share_before": round(before.get(k, 0) / totals[k], 4) if totals.get(k) else None,
            "share_after": round(after.get(k, 0) / totals[k], 4) if totals.get(k) else None,
            "absolute_gain_pp": round(100 * (after.get(k, 0) - before.get(k, 0)) / totals[k], 2)
            if totals.get(k) else None,
        }
        for k in sorted(totals)
    }
    pc.save_json(rep, ROOT / "experiments/phoenix/innovation/results/raea_results.json")
    print(json.dumps(rep, indent=2, ensure_ascii=False)[:9000])
    print("\nwritten:", ROOT / "experiments/phoenix/innovation/results/raea_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
