"""PHOENIX-003 shared library.

Everything here is deterministic and side-effect free apart from the explicit writers.
No network access. The only external input is a read-only SQLite store plus the frozen
JSON/JSONL/YAML-free artefacts under experiments/phoenix003/.

Frozen rules are loaded from FROZEN_RULES.json; no numeric threshold is hard-coded in the
analysis code. If a number must be a constant here, it is structural (e.g. the number of
days in a year) and it is named as such.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXPERIMENT_DIR.parents[1]
DATASET = EXPERIMENT_DIR / "dataset"
RESULTS = EXPERIMENT_DIR / "results"
FETCH = EXPERIMENT_DIR / "fetch"

DAYS_PER_YEAR = 365  # structural, used only for window arithmetic fallbacks


# --------------------------------------------------------------------------- io
def load_rules() -> dict:
    with open(EXPERIMENT_DIR / "FROZEN_RULES.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_lineage() -> dict:
    with open(DATASET / "firm_lineage.json", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
            n += 1
    os.replace(tmp, path)
    return n


def read_jsonl_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------------ dates
_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def parse_date(value) -> date | None:
    """Parse 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD' into a date.

    A month-only value resolves to the FIRST day of the month and a year-only value to
    January 1: for a *publication* date this is the earliest day on which the record could
    be public, which is the conservative choice for claiming a lead time. The convention is
    recorded in the returned tuple by `precision`.
    """
    parsed = parse_date_precision(value)
    return parsed[0] if parsed else None


def parse_date_precision(value):
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return (value, "day")
    text = str(value).strip()
    if not text:
        return None
    m = _DATE_RE.match(text)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2) or 1)
    day = int(m.group(3) or 1)
    precision = "day" if m.group(3) else ("month" if m.group(2) else "year")
    try:
        return (date(year, month, day), precision)
    except ValueError:
        return None


def years_before(d: date, years: int) -> date:
    """Calendar-year subtraction that clamps 29 Feb to 28 Feb."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


# ------------------------------------------------------------------- text utils
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_ROMAN = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}
_UNITS = {
    "MM", "CM", "M", "KG", "G", "MG", "ML", "L", "FR", "F", "GA", "KV", "MA", "MHZ", "HZ",
    "HOUR", "HOURS", "MIN", "WATT", "VOLT", "AMP", "PSI", "BAR", "DEG", "CELSIUS", "NM",
}


def normalise_text(value: str) -> str:
    """Uppercase, strip diacritics, collapse every non-alphanumeric run to one space."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_like = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", ascii_like.upper()).strip()


def token_list(value: str) -> list[str]:
    text = normalise_text(value)
    return text.split() if text else []


def token_set(value: str) -> set[str]:
    return set(token_list(value))


# -------------------------------------------------------------- firm resolution
class FirmResolver:
    """Token-equality brand lineage resolver (see dataset/firm_lineage.json).

    Resolution uses ``qualifier_tokens`` when a brand word is too weak on its own
    (GE, BOSTON). The stratum (core / extension) is carried on the result so the analysis can
    keep the pre-registered extension sample separate from the core five.
    """

    def __init__(self, lineage: dict, rules: dict):
        self.lineage = lineage
        self.rules = rules
        self.core = list(rules["firms"]["core"])
        self.brands = lineage["brand_tokens"]
        self.stratum = lineage.get("stratum", {})
        # core firms first, then extension, both in a stable order
        order = [f for f in self.stratum if self.stratum[f] == "core"]
        order += [f for f in self.stratum if self.stratum[f] == "extension"]
        order += [f for f in self.brands if f not in order]
        self.order = order

    def resolve(self, applicant: str) -> dict:
        tokens = set(token_list(applicant))
        if not tokens:
            return {"firm": None, "rule": "empty_applicant", "matched_token": None,
                    "stratum": None}
        text = normalise_text(applicant)
        for firm in self.order:
            spec = self.brands[firm]
            hits = tokens & set(spec.get("any_token", []))
            if not hits:
                continue
            excludes = spec.get("exclude_if_contains") or []
            if excludes and any(pc_excl in text for pc_excl in
                                [normalise_text(x) for x in excludes]):
                continue
            qualifiers = spec.get("qualifier_tokens")
            if qualifiers:
                # a weak brand word needs a domain qualifier (GE + HEALTHCARE, BOSTON + SCIENTIFIC)
                if not (tokens & set(qualifiers)):
                    continue
            return {"firm": firm, "rule": "brand_token", "matched_token": sorted(hits)[0],
                    "stratum": self.stratum.get(firm)}
        return {"firm": None, "rule": "no_brand_token", "matched_token": None, "stratum": None}


# --------------------------------------------------------------------- database
def connect_db(path: str | os.PathLike) -> sqlite3.Connection:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"database not found: {p}\n"
                         f"pass --db or set MEDRADAR_DB")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------------------ vocab freeze
def load_frozen_vocab() -> dict:
    path = DATASET / "frozen_vocab.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class DistinctiveTokenizer:
    """Frozen tokenizer: token is distinctive iff length>=min, alphabetic, not a stoplist
    word, not in the generic device vocabulary derived from the static product-code
    catalogue, not a brand token of any core firm (Amendment 1), and not a measure/model
    pattern."""

    def __init__(self, rules: dict, vocab: dict):
        cfg = rules["name_vocab"]
        self.min_len = int(rules["anchor"]["min_token_length"])
        self.stop_a = {t.upper() for t in cfg["stoplist_part_a"]}
        self.generic = {t.upper() for t in vocab["generic_vocabulary"]}
        self.brand = {t.upper() for t in vocab.get("brand_tokens", [])}
        self.applicant_df = vocab.get("applicant_df", {})
        rule = vocab.get("band_rule", {"high_max_applicants": 1, "medium_max_applicants": 100})
        self._band_high = int(rule.get("high_max_applicants", 1))
        self._band_mid = int(rule.get("medium_max_applicants", 100))
        self.product_specific_max = int(
            rules["name_vocab"].get("product_specific_max_applicant_df", 3))
        self.vocab_meta = vocab
        self._rare = None
        self.literature_rare_max = int(
            rules["name_vocab"].get("literature_rare_max_epmc_df", 200))

    def candidates(self, name: str) -> list[str]:
        out = []
        for tok in token_list(name):
            if len(tok) < self.min_len:
                continue
            if not tok.isalpha():
                continue
            if tok in _ROMAN or tok in _UNITS:
                continue
            if tok in self.stop_a or tok in self.generic or tok in self.brand:
                continue
            out.append(tok)
        seen, ordered = set(), []
        for tok in out:
            if tok not in seen:
                seen.add(tok)
                ordered.append(tok)
        return ordered

    def band(self, token: str) -> str:
        df = int(self.applicant_df.get(token, 0))
        if df == 0:
            return "unseen"
        if df <= self._band_high:
            return "high"
        if df <= self._band_mid:
            return "medium"
        return "low"

    def applicant_df_of(self, token: str) -> int:
        return int(self.applicant_df.get(token, 0))

    def is_product_specific(self, token: str) -> bool:
        """True when at most `product_specific_max` distinct applicants use the token in a
        device name, i.e. the token can actually discriminate one firm's product from
        another's clinical vocabulary (Amendment 2)."""
        df = self.applicant_df_of(token)
        return 0 < df <= self.product_specific_max

    def _load_rare(self) -> set:
        if self._rare is None:
            path = DATASET / "epmc_rare_tokens.txt"
            if path.exists():
                self._rare = {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
                              if ln.strip()}
            else:  # fail open in the sense of "unknown", never silently rare
                self._rare = set()
        return self._rare

    def is_literature_rare(self, token: str) -> bool:
        """Amendment 5: the token must not be an ordinary word of the field's literature."""
        return token in self._load_rare()

    def all_tokens(self, name: str) -> list[str]:
        return token_list(name)


# ---------------------------------------------------------------- small helpers
def cp_interval(k: int, n: int, confidence: float) -> tuple[float, float]:
    """Clopper-Pearson interval without scipy: beta quantiles via bisection on the
    regularised incomplete beta function."""
    if n <= 0:
        return (0.0, 1.0)
    alpha = 1.0 - confidence
    lo = 0.0 if k == 0 else _beta_ppf(alpha / 2.0, k, n - k + 1)
    hi = 1.0 if k == n else _beta_ppf(1.0 - alpha / 2.0, k + 1, n - k)
    return (lo, hi)


def _betacf(a: float, b: float, x: float) -> float:
    MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _log_gamma(z: float) -> float:
    """Lanczos approximation (g=7, n=9), accurate to ~1e-13 for z>0."""
    if z < 0.5:
        import math
        return math.log(math.pi / math.sin(math.pi * z)) - _log_gamma(1.0 - z)
    g = 7.0
    coef = [
        0.99999999999980993, 676.5203681218851, -1259.1392167224028,
        771.32342877765313, -176.61502916214059, 12.507343278686905,
        -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
    ]
    z -= 1.0
    x = coef[0]
    for i in range(1, int(g) + 2):
        x += coef[i] / (z + i)
    t = z + g + 0.5
    import math
    return 0.5 * math.log(2.0 * math.pi) + (z + 0.5) * math.log(t) - t + math.log(x)


def _beta_cdf(x: float, a: float, b: float) -> float:
    import math
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = _log_gamma(a) + _log_gamma(b) - _log_gamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _beta_ppf(p: float, a: float, b: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _beta_cdf(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile on an already sorted list, q in [0,1]."""
    if not sorted_values:
        raise ValueError("empty")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return float(sorted_values[lo]) * (1.0 - frac) + float(sorted_values[hi]) * frac


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
