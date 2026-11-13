"""Independent verifier utilities for PHOENIX-003.

Deliberately does NOT import anything from experiments/phoenix003/code/. Everything here is
re-derived from the frozen specification files and the raw inputs:

  * FROZEN_RULES.json       (numeric parameters)
  * dataset/firm_lineage.json (brand token -> firm mapping / qualifier rule)
  * dataset/frozen_vocab.json (generic vocabulary + brand token list; a frozen DATA input)
  * data/medradar.sqlite    (opened read-only)
  * dataset/ctgov_compact.jsonl.gz, dataset/epmc_compact.jsonl.gz (when present)

The token *selection* rule is the author's frozen rule (protocol 4.5); the implementation and all
matching decisions below are the verifier's own.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent                     # experiments/phoenix003
REPO = EXP.parents[1]
DATASET = EXP / "dataset"
RESULTS = EXP / "results"
SNAP = HERE / "committed_snapshot"
DB_PATH = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")

# The author re-ran the pipeline while verification was in progress. The artefacts as they
# stood when verification started were snapshotted under verify/committed_snapshot/. Set
# PHOENIX_VERIFY_MODE=snapshot to verify that frozen copy, or leave it unset ("live") to
# verify whatever currently sits in results/ and the experiment root.
import os
MODE = os.environ.get("PHOENIX_VERIFY_MODE", "live")


def artifacts_dir() -> Path:
    return SNAP if MODE == "snapshot" else EXP


def results_dir() -> Path:
    return SNAP if MODE == "snapshot" else RESULTS


def result_json(name: str):
    return load_json(results_dir() / name)



def load_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(p):
    rows = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_jsonl_gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def connect_ro():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------------------ text / dates
_NON = re.compile(r"[^A-Z0-9]+")
_ROMAN = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}
_UNITS = {
    "MM", "CM", "M", "KG", "G", "MG", "ML", "L", "FR", "F", "GA", "KV", "MA", "MHZ", "HZ",
    "HOUR", "HOURS", "MIN", "WATT", "VOLT", "AMP", "PSI", "BAR", "DEG", "CELSIUS", "NM",
}
_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def norm(value) -> str:
    if not value:
        return ""
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return _NON.sub(" ", s.upper()).strip()


def tokens(value) -> list:
    t = norm(value)
    return t.split() if t else []


def parse_date(value):
    """YYYY[-MM[-DD]] -> date; month=1, day=1 when truncated."""
    from datetime import date
    if value is None:
        return None
    if hasattr(value, "year") and not isinstance(value, str):
        return value if not hasattr(value, "hour") else value.date()
    m = _DATE_RE.match(str(value).strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def years_before(d, years: int):
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


# ------------------------------------------------------------------ attribution
class Resolver:
    """My own implementation of the frozen brand-token lineage rule.

    Token equality only (never substring). GE needs a qualifier token; BOSTON needs
    SCIENTIFIC. Core firms are tried before extension firms (stable order from the lineage
    file), exactly like any deterministic multi-label disambiguation must.
    """

    def __init__(self):
        lineage = load_json(DATASET / "firm_lineage.json")
        self.brand = lineage["brand_tokens"]
        self.stratum = lineage["stratum"]
        order = [f for f, s in self.stratum.items() if s == "core"]
        order += [f for f, s in self.stratum.items() if s == "extension"]
        order += [f for f in self.brand if f not in order]
        self.order = order
        # lineage v3: per-firm exclusion substrings (e.g. ZIMMER + MEDIZINSYSTEME is a
        # different company). Matched against the normalised applicant string.
        self.exclusions = {}
        for f, spec in self.brand.items():
            ex = [norm(x) for x in (spec.get("exclude_if_contains") or []) if x]
            if ex:
                self.exclusions[f] = ex

    def resolve(self, applicant):
        tokset = set(tokens(applicant))
        if not tokset:
            return None, None
        ntext = " " + norm(applicant) + " "
        for firm in self.order:
            spec = self.brand[firm]
            hits = tokset & set(spec.get("any_token", []))
            if not hits:
                continue
            quals = spec.get("qualifier_tokens")
            if quals and not (tokset & set(quals)):
                continue
            excluded = False
            for x in self.exclusions.get(firm, []):
                if (" " + x + " ") in ntext:
                    excluded = True
                    break
            if excluded:
                continue
            return firm, sorted(hits)[0]
        return None, None

    def all_matching_firms(self, applicant):
        tokset = set(tokens(applicant))
        ntext = " " + norm(applicant) + " "
        out = []
        for firm in self.order:
            spec = self.brand[firm]
            hits = tokset & set(spec.get("any_token", []))
            if not hits:
                continue
            quals = spec.get("qualifier_tokens")
            if quals and not (tokset & set(quals)):
                continue
            if any((" " + x + " ") in ntext for x in self.exclusions.get(firm, [])):
                continue
            out.append(firm)
        return out


class Tokenizer:
    """My own implementation of the frozen distinctive-token rule (protocol 4.5).

    Uses the frozen DATA files for the generic vocabulary and the brand-token list. Also
    applies the extra stoplist file named in FROZEN_RULES.json (the author's code ignores it;
    see report).
    """

    def __init__(self):
        rules = load_json(EXP / "FROZEN_RULES.json")
        vocab = load_json(DATASET / "frozen_vocab.json")
        self.min_len = int(rules["anchor"]["min_token_length"])
        self.stop_a = {t.upper() for t in rules["name_vocab"]["stoplist_part_a"]}
        self.generic = {t.upper() for t in vocab["generic_vocabulary"]}
        self.brand = {t.upper() for t in vocab["brand_tokens"]}
        extra_path = DATASET / "name_stoplist_extra.txt"
        self.extra = set()
        if extra_path.exists():
            self.extra = {ln.strip().upper() for ln in extra_path.read_text(encoding="utf-8").splitlines()
                          if ln.strip() and not ln.startswith("#")}
        self.applicant_df = {k: int(v) for k, v in vocab.get("applicant_df", {}).items()}
        self.bands = vocab.get("specificity_bands", {})
        self.rule_high = int(vocab.get("band_rule", {}).get("high_max_applicants", 1))
        self.rule_mid = int(vocab.get("band_rule", {}).get("medium_max_applicants", 100))
        self.product_specific_max = int(rules["name_vocab"]["product_specific_max_applicant_df"])

    def all_tokens(self, name):
        return tokens(name)

    def distinctive(self, name, use_extra=True):
        out, seen = [], set()
        for tok in tokens(name):
            if len(tok) < self.min_len:
                continue
            if not tok.isalpha():
                continue
            if tok in _ROMAN or tok in _UNITS:
                continue
            if tok in self.stop_a or tok in self.generic or tok in self.brand:
                continue
            if use_extra and tok in self.extra:
                continue
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
        return out

    def band(self, tok):
        df = self.applicant_df.get(tok, 0)
        if df == 0:
            return "unseen"
        if df <= self.rule_high:
            return "high"
        if df <= self.rule_mid:
            return "medium"
        return "low"

    def is_product_specific(self, tok):
        df = self.applicant_df.get(tok, 0)
        return 0 < df <= self.product_specific_max


# ------------------------------------------------------------------ committed files
def committed_anchors():
    return load_jsonl(artifacts_dir() / "REGULATORY_ANCHORS.jsonl")


def committed_links():
    return load_jsonl(artifacts_dir() / "EVIDENCE_LINKS.jsonl")


# ----------------------------------------------------------------- DB milestones
MILESTONE_SQL = """
select event_id, kind, event_date, applicant_raw, product_code, url,
       json_extract(payload,'$.k_number')          as k_number,
       json_extract(payload,'$.pma_number')        as pma_number,
       json_extract(payload,'$.supplement_number') as supplement_number,
       json_extract(payload,'$.decision_code')     as decision_code,
       json_extract(payload,'$.date_received')     as date_received,
       json_extract(payload,'$.device_name')       as device_name,
       json_extract(payload,'$.trade_name')        as trade_name,
       json_extract(payload,'$.generic_name')      as generic_name,
       json_extract(payload,'$.applicant')         as payload_applicant
from events where kind in ('510k','pma')
"""


def load_milestones(con):
    """Return (milestones, supplements, raw_counts, missing)."""
    ms, supp, raw, missing = [], [], {"510k": 0, "pma": 0}, {"missing_identifier": 0}
    for r in con.execute(MILESTONE_SQL):
        kind = r["kind"]
        raw[kind] += 1
        is_pma = kind == "pma"
        s = (r["supplement_number"] or "").strip()
        ident = (r["pma_number"] if is_pma else r["k_number"]) or ""
        ident = ident.strip()
        if not ident:
            missing["missing_identifier"] += 1
            continue
        rec = {
            "event_id": r["event_id"],
            "kind": kind,
            "source": "openfda_device_pma" if is_pma else "openfda_device_510k",
            "milestone_key": ("P" if is_pma else "K") + ident,
            "official_id": ident,
            "supplement_number": s or None,
            "decision_date": r["event_date"],
            "date_received": r["date_received"],
            "decision_code": r["decision_code"],
            "applicant_raw": (r["applicant_raw"] or r["payload_applicant"] or "").strip(),
            "product_code": (r["product_code"] or "").strip(),
            "name_raw": ((r["trade_name"] if is_pma else r["device_name"]) or "").strip(),
            "name_source": ("pma.trade_name" if is_pma else "510k.device_name"),
        }
        if is_pma and not rec["name_raw"]:
            rec["name_raw"] = (r["generic_name"] or "").strip()
            rec["name_source"] = "pma.generic_name"
        if is_pma and s:
            supp.append(rec)
            continue
        ms.append(rec)
    return ms, supp, raw, missing
