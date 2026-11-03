"""S-029 step 05 — company mention mapping (identity, roles, anachronism).

This is the step where a *string* becomes (or fails to become) an *entity*. It is
deliberately mechanical and auditable: every decision is a named rule with a date
check, and every rejection is kept.

The corporate facts are **not** encoded from memory. They are read from
`artifacts/company_entity_register.json`, which the independent entity auditor built
from primary documents (SEC 10-K/8-K, GLEIF, exchange filings) with verbatim excerpts.
Where the register expresses a fact as evidence text rather than as a first-class date
(e.g. "Medtronic completed the acquisition of Covidien plc on January 26, 2015"), the
ownership date is recorded in `OWNERSHIP` below **with the register entity_key and the
exact event it comes from**, so the date is traceable and the register remains the
authority.

Three mechanisms are measured rather than assumed:

1. **Operating-unit strings.** A trial sponsor is very often an internal business unit
   ("Medtronic Cardiac Rhythm and Heart Failure", 280 records), not the legal parent.
   Mapping a unit to its group is a real inference and is flagged as such.
2. **Subsidiary and former-parent strings must pass a date test.** A string that names
   an entity *before* it belonged to the group must NOT produce a group claim. The
   register corrected two provisional assumptions in this study: Mindray bought only
   Datascope's Patient Monitoring business (Datascope Corp. was never acquired), and
   "MiniMed" was independent before 2001.
3. **Free-text name collisions.** Europe PMC affiliation search returns papers by
   authors surnamed Draeger whose *email* contains `draeger@...`, and substring matches
   such as `Colle(ge Healthcare)` / `Oran(ge healthcare)`. Mentions are classified by
   context and weak ones are recorded as REJECTED with their reason.

Run:  python research/studies/relation_network_s029/code/s029_05_company_map.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, read_json, read_jsonl, utcnow_iso,
                         write_json, write_jsonl)

EXTRACTION_VERSION = "s029-1.0.0"
REGISTER_PATH = ARTIFACT_DIR / "company_entity_register.json"

# ---------------------------------------------------------------------------
# Group membership: string family -> register entity, with the date the group came to
# own it. `ownership_from = None` means the register attests membership but no date is
# established; such a mapping is downgraded to CANDIDATE and flagged, never silently
# treated as always-true.
# ---------------------------------------------------------------------------
OWNERSHIP: dict[str, list[dict]] = {
    "medtronic": [
        {"entity_key": "covidien_plc", "ownership_from": "2015-01-26",
         "event": "Medtronic completed the acquisition of Covidien plc on January 26, 2015 "
                  "(MDT FY2015 10-K, verbatim excerpt in the register)",
         "match": ["covidien"]},
        {"entity_key": "covidien_ltd", "ownership_from": "2015-01-26",
         "event": "predecessor of Covidien plc (replaced 2009-06-04); group ownership only "
                  "from the 2015-01-26 acquisition",
         "match": ["covidien ltd"], "historical_name_only": True},
        {"entity_key": "tyco_healthcare", "ownership_from": "2015-01-26",
         "event": "Tyco Healthcare became Covidien in 2007 and was acquired by Medtronic only "
                  "on 2015-01-26, so the 'Tyco Healthcare' name itself is always pre-ownership",
         "match": ["tyco healthcare", "tyco international"], "historical_name_only": True},
        {"entity_key": "minimed_inc", "ownership_from": "2001-08-28",
         "event": "MiniMed Inc. acquired by Medtronic (register: minimed_inc ceased 2001-08-28; "
                  "successor entity medtronic_minimed_inc)",
         "match": ["minimed"]},
        {"entity_key": "medtronic_minimed_inc", "ownership_from": None,
         "event": "operating subsidiary of Medtronic plc", "match": ["medtronic minimed"]},
        {"entity_key": "medtronic_vascular_inc", "ownership_from": None,
         "event": "operating subsidiary of Medtronic plc",
         "match": ["medtronic vascular", "medtronic endovascular"]},
        {"entity_key": "medtronic_sofamor_danek_usa_inc", "ownership_from": None,
         "event": "operating subsidiary of Medtronic plc", "match": ["medtronic sofamor danek"]},
    ],
    "ge_healthcare": [
        {"entity_key": "ge_healthcare_division", "ownership_from": None,
         "membership_to": "2023-01-03",
         "event": "GE Healthcare was a division of General Electric until the spin-off "
                  "completed 2023-01-03 (register valid_to_event)",
         "match": ["ge healthcare", "ge health care", "ge healthcare technologies",
                   "ge medical systems", "general electric healthcare"]},
    ],
    "philips": [
        {"entity_key": "philips_healthcare_division", "ownership_from": None,
         "event": "division of Koninklijke Philips N.V.",
         "match": ["philips healthcare", "philips medical systems",
                   "philips clinical medical affairs global", "philips oral healthcare",
                   "philips electronics nederland", "epd solutions"]},
        {"entity_key": "respironics_inc", "ownership_from": "2008-03-17",
         "event": "Respironics became a Philips company on 2008-03-17 (register valid_from)",
         "match": ["respironics"]},
    ],
    "draeger": [
        {"entity_key": "draeger_medical_gmbh", "ownership_from": None,
         "event": "Dräger Medical was the medical division/subsidiary of Drägerwerk; the "
                  "register cannot date its start (UNKNOWN)",
         "match": ["draeger medical", "dr\u00e4ger medical"]},
        {"entity_key": "draeger_safety_ag_co_kgaa", "ownership_from": "2001-05-21",
         "event": "register valid_from", "match": ["draeger safety", "dr\u00e4ger safety"]},
        {"entity_key": "draeger_medical_systems_inc", "ownership_from": "2003-04-03",
         "event": "register valid_from",
         "match": ["draeger medical systems", "dr\u00e4ger medical systems"]},
    ],
    "mindray": [
        {"entity_key": "mindray_ds_usa_inc", "ownership_from": None,
         "event": "operating subsidiary (Mindray DS USA)", "match": ["mindray ds usa"]},
        {"entity_key": "datascope_patient_monitoring_business", "ownership_from": "2008-05-14",
         "event": "the Patient Monitoring business was sold to Mindray and the sale closed "
                  "2008-05-14 (register valid_from / valid_to_event)",
         "match": ["datascope patient monitoring"]},
        {"entity_key": "zonare_medical_systems_inc", "ownership_from": "2013-07-17",
         "event": "register valid_from", "match": ["zonare"]},
    ],
}

# Strings that must NOT produce a claim for the company, with the reason. Kept explicit
# because these are the measured collision/former-parent cases.
NOT_GROUP: dict[str, list[dict]] = {
    "medtronic": [],
    "ge_healthcare": [
        {"match": ["general electric", "ge global research", "general electric research"],
         "reason": "General Electric was the PARENT of the GE Healthcare division and became a "
                   "different company after the 2023-01-03 spin-off; a GE-sponsored record is "
                   "not a GE HealthCare record",
         "entity_key": "general_electric", "status": "NOT_MAPPED"},
        {"match": ["imperial college healthcare", "orange healthcare"],
         "reason": "substring collision: 'Colle(ge Healthcare)' / 'Oran(ge healthcare)' is not "
                   "GE HealthCare", "entity_key": None, "status": "REJECTED"},
    ],
    "philips": [],
    "draeger": [],
    "mindray": [
        {"match": ["datascope corp", "datascope"],
         "reason": "Datascope Corp. was NOT acquired by Mindray: only its Patient Monitoring "
                   "business was sold, closing 2008-05-14 (register: datascope_corp "
                   "former_parent, not a group member)",
         "entity_key": "datascope_corp", "status": "NOT_MAPPED"},
        {"match": ["mindray medical international"],
         "reason": "Cayman holding company of the group until its 2016 delisting; a relation to "
                   "the holding is not automatically a relation to the SZSE parent after 2016",
         "entity_key": "mindray_medical_international_ltd", "status": "AMBIGUOUS"},
    ],
}

# Parent brand tokens. These are brand/group tokens, not legal names; an exact string
# equal to the token is EXACT, a longer string starting with it is an operating unit.
PARENT_TOKENS: dict[str, list[str]] = {
    "medtronic": ["medtronic"],
    "ge_healthcare": ["ge healthcare", "ge health care"],
    "philips": ["philips", "koninklijke philips", "royal philips"],
    "draeger": ["dr\u00e4gerwerk", "draegerwerk", "draeger", "dr\u00e4ger"],
    "mindray": ["mindray", "shenzhen mindray"],
}

EMAIL_DOMAINS: dict[str, list[str]] = {
    "medtronic": ["medtronic.com", "medtronic.nl", "medtronic.ca", "covidien.com"],
    "ge_healthcare": ["gehealthcare.com", "med.ge.com"],
    "philips": ["philips.com", "philips.nl", "philipsresearch.com", "respironics.com"],
    "draeger": ["draeger.com", "draegerwerk.com"],
    "mindray": ["mindray.com", "mindray.cn"],
}

AMBIGUOUS_FREE_TEXT: dict[str, list[str]] = {
    "draeger": ["draeger", "dr\u00e4ger"],   # common German surname
    "philips": [], "medtronic": [], "ge_healthcare": [], "mindray": [],
}

COMPANY_KEYS = list(OWNERSHIP)

# Division era: before this date the string denotes a division of a former parent,
# which is the same business but not the same legal entity.
DIVISION_ERA = {
    "ge_healthcare": {"from": "2023-01-03",
                      "event": "GE HealthCare Technologies Inc. became an independent company "
                               "when the spin-off completed on 2023-01-03"},
}


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def token_regex(token: str) -> re.Pattern:
    """Word-boundary token match on folded text.

    The boundary test is what kills 'Colle(ge Healthcare)' and 'Oran(ge healthcare)':
    a token must not be preceded or followed by another alphanumeric character.
    """
    t = re.escape(fold(token))
    return re.compile(r"(?<![a-z0-9])" + t + r"(?![a-z0-9])")


def norm_org(s: str) -> str:
    s = fold(s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


ORG_KEYWORDS = re.compile(
    r"univers|hospital|clinic|institut|college|school|centre|center|foundation|academy|"
    r"akademi|laborator|klinik|krankenhaus|trust|faculty|fakult|department|ministry|"
    r"council|agency|health system|medical center|medical centre|nhs|va medical|"
    r"dept|division|unit|group|gmbh|inc\b|ltd\b|llc|corp|company|co\b|ag\b|bv\b|sarl|s\.a\.",
    re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
INITIALS_RE = re.compile(r"(?:[A-Z]\.[A-Z]?\.?\s*){1,3}$")
MD_SUFFIX_RE = re.compile(r"^\s*,?\s*(MD|M\.D\.|PhD|Ph\.D\.|Jr|Sr|MPH|RN|MS|MSc)\b")
PERSONAL_NAME_RE = re.compile(r"^\s+[A-Z]\.\s+[A-Z][a-z]+")
AWARD_RE = re.compile(r"award|grant|fellowship|scholarship|prize|professorship|"
                      r"endowed|chair|development award|sponsor(ed)? by|provide[sd]? the|"
                      r"unrestricted", re.I)
CORPORATE_SUFFIX_RE = re.compile(r"\b(inc|ltd|llc|gmbh|ag|kgaa|bv|nv|sarl|sa|corp|"
                                 r"corporation|company|co|limited)\b", re.I)


def classify_hits(text: str, token: str) -> list[dict]:
    """Locate every occurrence of a company token in free text and classify it."""
    folded = fold(text)
    hits = []
    for m in token_regex(token).finditer(folded):
        start, end = m.start(), m.end()
        ctx_before = text[max(0, start - 14):start]
        ctx_after = text[end:end + 14]
        in_email = None
        for em in EMAIL_RE.finditer(text):
            if em.start() <= start < em.end():
                at = text.find("@", em.start(), em.end())
                in_email = "EMAIL_DOMAIN" if start > at else "EMAIL_LOCALPART"
                break
        span = text[max(0, start - 40):min(len(text), end + 40)]
        if in_email:
            hits.append({"token": token, "class": in_email, "start": start, "end": end,
                         "evidence_span": span})
            continue
        if (INITIALS_RE.search(ctx_before) or MD_SUFFIX_RE.match(ctx_after)
                or PERSONAL_NAME_RE.match(ctx_after)):
            hits.append({"token": token, "class": "SURNAME", "start": start, "end": end,
                         "evidence_span": span})
            continue
        segment = next((s for s in text.split(";") if fold(token) in fold(s)), text)
        fseg = fold(segment)
        hits.append({"token": token, "class": "ORG_NAME", "start": start, "end": end,
                     "segment": segment.strip()[:300],
                     "has_org_keyword": bool(ORG_KEYWORDS.search(fseg)
                                             or CORPORATE_SUFFIX_RE.search(segment)),
                     "award_context": bool(AWARD_RE.search(segment)),
                     "evidence_span": span})
    return hits


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def load_register() -> dict:
    if not REGISTER_PATH.exists():
        return {}
    try:
        return read_json(REGISTER_PATH)
    except Exception:
        return {}


def register_entity(reg: dict, company: str, entity_key: str) -> dict:
    for e in ((reg.get("companies") or {}).get(company) or {}).get("entities") or []:
        if e.get("entity_key") == entity_key:
            return e
    return {}


def not_company_strings(reg: dict) -> dict[str, list[dict]]:
    """Strings measured to look like a company but be free text or another thing."""
    out: dict[str, list[dict]] = defaultdict(list)
    for row in reg.get("not_company_registry") or []:
        ck = row.get("company")
        for s in row.get("strings") or []:
            out[ck].append({"string": s.get("string"), "note": s.get("note")})
    return out


def _as_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Mapping decision
# ---------------------------------------------------------------------------

def map_string(raw: str, context: str, claim_date: str | None, reg: dict,
               nc_strings: dict | None = None) -> dict:
    """Map one source string to a company, with a named rule and a date check.

    context: "structured_org" (sponsor/collaborator/facility/funder field) or
             "free_text" (publication affiliation string).
    """
    if not raw or not raw.strip():
        return {"company_key": None, "mapping_status": "UNMAPPED", "confidence": 0.0,
                "rule": "empty_string", "reason": "no string"}
    n = norm_org(raw)
    cd = _as_date(claim_date)
    matches: list[dict] = []

    # 0. strings the register explicitly measured as free text, not entities
    for ck, rows in (nc_strings or {}).items():
        for row in rows:
            if row.get("string") and norm_org(row["string"]) == n:
                matches.append({"company_key": ck, "mapping_status": "REJECTED",
                                "confidence": 0.0, "rule": "register_not_company_string",
                                "reason": row.get("note") or "not an entity name"})

    # 1. explicit non-group / collision strings
    for ck, rows in NOT_GROUP.items():
        for row in rows:
            if any(token_regex(x).search(n) for x in row["match"]):
                matches.append({"company_key": ck, "mapping_status": row["status"],
                                "confidence": 0.0, "rule": "not_group_member",
                                "entity_key": row.get("entity_key"),
                                "reason": row["reason"]})

    # 2. group members (subsidiaries / divisions) with an ownership date test
    for ck, rows in OWNERSHIP.items():
        for row in rows:
            if not any(token_regex(x).search(n) for x in row["match"]):
                continue
            ent = register_entity(reg, ck, row["entity_key"])
            of = row.get("ownership_from")
            date_source = "REGISTER_OWNERSHIP_EVENT" if of else "REGISTER_NO_DATE"
            if ent.get("valid_from") and row.get("ownership_from") is None \
                    and not row.get("membership_to"):
                of = ent["valid_from"]
                date_source = "REGISTER_VALID_FROM"
            if row.get("membership_to"):
                mt = _as_date(row["membership_to"])
                if cd and mt and cd >= mt:
                    matches.append({"company_key": ck, "mapping_status": "NOT_MAPPED",
                                    "confidence": 0.0, "rule": "division_ended",
                                    "entity_key": row["entity_key"],
                                    "reason": f"the division left the former parent on "
                                              f"{row['membership_to']}; after that the string "
                                              f"names a different legal entity"})
                    continue
                matches.append({"company_key": ck, "mapping_status": "ALIAS",
                                "confidence": 0.75, "rule": "division_of_parent_group",
                                "entity_key": row["entity_key"],
                                "division_era": True,
                                "date_source": date_source,
                                "reason": f"division of the parent group ({row['event']})"})
                continue
            ofd = _as_date(of)
            if row.get("historical_name_only"):
                # the name existed only before group ownership -> never a group claim
                matches.append({"company_key": ck, "mapping_status": "NOT_MAPPED",
                                "confidence": 0.0, "rule": "historical_name_pre_ownership",
                                "entity_key": row["entity_key"],
                                "reason": row["event"]})
                continue
            if cd and ofd and cd < ofd:
                matches.append({"company_key": ck, "mapping_status": "AMBIGUOUS",
                                "confidence": 0.25, "rule": "subsidiary_not_yet_owned",
                                "entity_key": row["entity_key"], "date_source": date_source,
                                "ownership_from": of,
                                "reason": f"string names an entity before the group owned it "
                                          f"(claim date {claim_date} < ownership {of}); "
                                          f"{row['event']}"})
            elif ofd:
                matches.append({"company_key": ck, "mapping_status": "ALIAS",
                                "confidence": 0.85, "rule": "group_member_current",
                                "entity_key": row["entity_key"], "date_source": date_source,
                                "ownership_from": of,
                                "reason": f"group member from {of} ({row['event']})"})
            else:
                matches.append({"company_key": ck, "mapping_status": "ALIAS",
                                "confidence": 0.70, "rule": "group_member_undated",
                                "entity_key": row["entity_key"],
                                "date_source": "REGISTER_NO_DATE",
                                "dates_unknown": True,
                                "reason": f"group member, ownership start not established: "
                                          f"{row['event']}"})

    # 3. parent brand tokens
    for ck, tokens in PARENT_TOKENS.items():
        for tok in tokens:
            if not token_regex(tok).search(n):
                continue
            exact = n == norm_org(tok)
            ambiguous_free = (context == "free_text"
                              and fold(tok) in [fold(x) for x in AMBIGUOUS_FREE_TEXT.get(ck, [])])
            de = DIVISION_ERA.get(ck)
            if de and cd and cd < _as_date(de["from"]):
                matches.append({"company_key": ck, "mapping_status": "ALIAS",
                                "confidence": 0.80, "rule": "division_of_former_parent",
                                "anachronism_if_mapped": True,
                                "reason": f"before {de['from']} this was a division of a former "
                                          f"parent, not the current legal entity "
                                          f"({de['event']})"})
            if exact:
                matches.append({"company_key": ck,
                                "mapping_status": "EXACT" if not ambiguous_free else "FUZZY",
                                "confidence": 1.0 if not ambiguous_free else 0.5,
                                "rule": "canonical_token_exact" if not ambiguous_free
                                        else "ambiguous_surname_token",
                                "reason": "string equals the group name" if not ambiguous_free
                                          else "token is also a personal surname; free-text match "
                                                 "alone is insufficient"})
            else:
                matches.append({"company_key": ck,
                                "mapping_status": "FUZZY" if ambiguous_free else "ALIAS",
                                "confidence": 0.5 if ambiguous_free else 0.90,
                                "rule": "ambiguous_surname_token" if ambiguous_free
                                        else "operating_unit_of_parent",
                                "reason": "operating unit / brand extension of the parent group"
                                          if not ambiguous_free
                                          else "token is also a personal surname; free-text match "
                                               "alone is insufficient"})

    seen = set()
    uniq = []
    for m in matches:
        k = (m["company_key"], m["rule"], m.get("entity_key"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(m)

    if not uniq:
        return {"company_key": None, "mapping_status": "UNMAPPED", "confidence": 0.0,
                "rule": "no_rule_matched", "reason": "string matches no register rule"}

    rank = {"EXACT": 5, "ALIAS": 4, "FUZZY": 3, "AMBIGUOUS": 2, "NOT_MAPPED": 1, "REJECTED": 0}
    pos = [m for m in uniq if m["mapping_status"] not in ("NOT_MAPPED", "REJECTED")]
    if not pos:
        return uniq[0]
    pos.sort(key=lambda m: (rank[m["mapping_status"]], m["confidence"]), reverse=True)
    best = dict(pos[0])
    companies = {m["company_key"] for m in pos}
    if len(companies) > 1:
        best["mapping_status"] = "AMBIGUOUS"
        best["confidence"] = 0.3
        best["rule"] = "multi_company_collision"
        best["reason"] = f"string matches multiple companies: {sorted(companies)}"
    if any(m.get("anachronism_if_mapped") for m in uniq):
        best["anachronism_if_mapped"] = True
        best["anachronism_rules"] = [m["rule"] for m in uniq if m.get("anachronism_if_mapped")]
    best["alternatives"] = [m for m in uniq if m is not best]
    return best


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    reg = load_register()
    nc_strings = not_company_strings(reg)
    trials = list(read_jsonl(DATA_DIR / "ctgov_trials.jsonl"))
    sites = list(read_jsonl(DATA_DIR / "ctgov_sites.jsonl"))
    pubs = list(read_jsonl(DATA_DIR / "epmc_pubs.jsonl"))

    mentions: list[dict] = []
    counters: dict = defaultdict(Counter)
    date_sources: Counter = Counter()

    def add(mention: dict) -> None:
        mentions.append(mention)
        date_sources[mention.get("date_source") or "NONE"] += 1
        counters[mention["role"]][mention["mapping_status"]] += 1
        if mention.get("company_key"):
            counters[f"company:{mention['company_key']}"][mention["mapping_status"]] += 1

    for t in trials:
        claim_date = (t["study_first_post_date"] or {}).get("date")
        for role, raw in [("lead_sponsor", t["lead_sponsor"]["name"])] + \
                [("collaborator", c["name"]) for c in t["collaborators"]] + \
                [("responsible_party", (t["responsible_party"] or {}).get("investigator_affiliation"))]:
            if not raw:
                continue
            m = map_string(raw, "structured_org", claim_date, reg, nc_strings)
            add({"mention_id": f"m:ctgov:{role}:{t['nct_id']}:{abs(hash(raw)) % 10**8}",
                 "source": "clinicaltrials_gov_api_v2", "record_kind": "trial",
                 "record_id": t["nct_id"], "role": role, "raw_string": raw,
                 "context": "structured_org", "claim_date": claim_date,
                 "claim_date_field": "studyFirstPostDate",
                 "company_key": m.get("company_key"), "mapping_status": m["mapping_status"],
                 "confidence": m.get("confidence"), "rule": m.get("rule"),
                 "reason": m.get("reason"), "entity_key": m.get("entity_key"),
                 "date_source": m.get("date_source"),
                 "ownership_from": m.get("ownership_from"),
                 "dates_unknown": m.get("dates_unknown", False),
                 "anachronism_if_mapped": m.get("anachronism_if_mapped", False),
                 "evidence_id": t["evidence_id"], "extraction_version": EXTRACTION_VERSION})

    for s in sites:
        if not s["facility"]:
            continue
        m = map_string(s["facility"], "structured_org", None, reg, nc_strings)
        if m.get("company_key"):
            add({"mention_id": f"m:ctgov:site:{s['nct_id']}:{abs(hash(s['facility'])) % 10**8}",
                 "source": "clinicaltrials_gov_api_v2", "record_kind": "trial",
                 "record_id": s["nct_id"], "role": "site_facility",
                 "raw_string": s["facility"], "context": "structured_org",
                 "claim_date": None, "company_key": m.get("company_key"),
                 "mapping_status": m["mapping_status"], "confidence": m.get("confidence"),
                 "rule": m.get("rule"), "reason": m.get("reason"),
                 "entity_key": m.get("entity_key"),
                 "date_source": m.get("date_source"),
                 "anachronism_if_mapped": m.get("anachronism_if_mapped", False),
                 "evidence_id": s["evidence_id"], "extraction_version": EXTRACTION_VERSION})

    for p in pubs:
        claim_date = p.get("first_publication_date") or p.get("first_index_date")
        for ai, au in enumerate(p["authors"]):
            for aff in au["affiliations"]:
                for ck, tokens in PARENT_TOKENS.items():
                    hits: list[dict] = []
                    for tok in tokens:
                        hits.extend(classify_hits(aff, tok))
                    # also group-member strings (e.g. "Philips Respironics", "Datascope Patient Monitoring")
                    for row in OWNERSHIP.get(ck, []):
                        for ms in row["match"]:
                            hits.extend(classify_hits(aff, ms))
                    if not hits:
                        continue
                    classes = {h["class"] for h in hits}
                    ambiguous_free = any(
                        fold(h["token"]) in [fold(x) for x in AMBIGUOUS_FREE_TEXT.get(ck, [])]
                        for h in hits)
                    dom_hit = next((h for h in hits if h["class"] == "EMAIL_DOMAIN"
                                    and any(d in fold(h["evidence_span"])
                                            for d in EMAIL_DOMAINS.get(ck, []))), None)
                    org_hits = [h for h in hits if h["class"] == "ORG_NAME"]
                    org_hit = next((h for h in org_hits if h.get("has_org_keyword")), None)
                    award_only = bool(org_hits) and all(h.get("award_context") for h in org_hits)
                    surname_only = classes <= {"SURNAME"}
                    localpart_only = classes <= {"EMAIL_LOCALPART"}
                    if dom_hit:
                        status, conf, rule = "ORG_EMAIL", 0.95, "corporate_email_domain"
                        reason = ("author email domain is a corporate domain "
                                  f"({dom_hit['evidence_span'][:120]})")
                        ctx = "structured_org"
                    elif award_only:
                        status, conf, rule = "WEAK_TEXT", 0.30, "award_or_programme_title"
                        reason = "token appears inside an award/programme title, not an affiliation"
                        ctx = "free_text"
                    elif ambiguous_free and not org_hit:
                        status, conf, rule = "REJECTED", 0.0, "ambiguous_surname_or_email_only"
                        reason = ("token is a personal surname / company name collision "
                                  f"(classes={sorted(classes)}); no organisational evidence")
                        ctx = "free_text"
                    elif org_hits:
                        status, conf, rule = "ORG_TEXT", 0.80, "organisational_affiliation_segment"
                        reason = ("affiliation names the company as the author's organisation "
                                  f"({org_hits[0]['evidence_span'][:120]})")
                        ctx = "structured_org"
                    elif surname_only:
                        status, conf, rule = "REJECTED", 0.0, "personal_surname_only"
                        reason = f"surname occurrence only ({sorted(classes)})"
                        ctx = "free_text"
                    elif localpart_only:
                        status, conf, rule = "REJECTED", 0.0, "email_localpart_only"
                        reason = "token appears only in an email local part"
                        ctx = "free_text"
                    else:
                        status, conf, rule = "WEAK_TEXT", 0.45, "free_text_no_org_context"
                        reason = f"mention in free text without organisational context ({sorted(classes)})"
                        ctx = "free_text"
                    add({"mention_id": f"m:epmc:aff:{p['pub_key']}:{ai}:{abs(hash(aff)) % 10**8}",
                         "source": "europepmc", "record_kind": "publication",
                         "record_id": p["pub_key"], "role": "author_affiliation",
                         "raw_string": aff[:2000], "context": ctx,
                         "claim_date": claim_date, "claim_date_field": "firstPublicationDate",
                         "company_key": ck, "mapping_status": status, "confidence": conf,
                         "rule": rule, "reason": reason,
                         "hit_classes": sorted(classes),
                         "evidence_id": p["evidence_id"],
                         "extraction_version": EXTRACTION_VERSION})

    mentions.sort(key=lambda m: m["mention_id"])
    n = write_jsonl(DATA_DIR / "company_mentions.jsonl", mentions)

    summary = {
        "generated_at": utcnow_iso(),
        "extraction_version": EXTRACTION_VERSION,
        "register_loaded": bool(reg),
        "register_entities": sum(len((c or {}).get("entities") or [])
                                 for c in (reg.get("companies") or {}).values()),
        "mentions": n,
        "date_source_counts": dict(date_sources),
        "by_role_and_status": {k: dict(v) for k, v in counters.items() if ":" not in k},
        "by_company": {k.split(":")[1]: dict(v) for k, v in counters.items()
                       if k.startswith("company:")},
        "accepted_statuses": ["EXACT", "ALIAS", "ORG_TEXT", "ORG_EMAIL"],
        "note": "REJECTED/WEAK_TEXT/AMBIGUOUS mentions are retained in "
                "data/company_mentions.jsonl; they are the false-positive measurement, "
                "not discarded rows.",
    }
    write_json(ARTIFACT_DIR / "company_mapping.json", summary)
    print(json.dumps({k: summary[k] for k in ("register_loaded", "register_entities",
                                              "mentions", "date_source_counts",
                                              "by_company")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
