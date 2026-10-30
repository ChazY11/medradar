"""Dependency-free helpers shared by every MedRadar module.

Pure standard library on purpose: the analysis stage must be reproducible on a
plain Python 3.10+ interpreter (no numpy/pandas required, no network).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

ISO_DATE = "%Y-%m-%d"
_WS = re.compile(r"[^A-Z0-9]+")


# --------------------------------------------------------------------------- dates
def parse_date(value: Any) -> date | None:
    """Parse the many date shapes published by FDA / CT.gov / NMPA.

    Accepts ``20240115``, ``2024-01-15``, ``2024/01/15``, ``2024-01``,
    ``2024``, ``Jan 15, 2024`` and date/datetime objects.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("/", "-").replace(".", "-")
    for fmt in (ISO_DATE, "%Y-%m", "%Y%m%d", "%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def iso(value: Any) -> str:
    """Render any supported date shape as ``YYYY-MM-DD`` (``""`` when unparsable)."""
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


def iso_moment(value: Any) -> str:
    """Render a date **or** an ISO datetime, preserving time-of-day when present.

    The trading lane needs minute-level availability (an 8-K is public at 16:05,
    not "today"), while openFDA only offers dates. ``iso()`` truncates to the day
    and would silently destroy that precision.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        return iso(value)


def month_key(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%Y-%m") if parsed else ""


def quarter_index(value: Any) -> int | None:
    """Absolute quarter number, useful for window arithmetic."""
    parsed = parse_date(value)
    if not parsed:
        return None
    return parsed.year * 4 + (parsed.month - 1) // 3


def quarter_label(index: int) -> str:
    return f"{index // 4}Q{index % 4 + 1}"


def quarter_start(index: int) -> date:
    return date(index // 4, (index % 4) * 3 + 1, 1)


def add_months(day: date, months: int) -> date:
    year = day.year + (day.month - 1 + months) // 12
    month = (day.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


# --------------------------------------------------------------------------- files
def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: str | Path, obj: Any, indent: int = 1) -> Path:
    """Atomically write UTF-8 JSON (Chinese stays readable, not \\uXXXX)."""
    target = Path(path)
    ensure_dir(target.parent)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(target.parent), delete=False, suffix=".tmp"
    )
    try:
        json.dump(obj, handle, ensure_ascii=False, indent=indent, default=str)
        handle.write("\n")
        handle.close()
        os.replace(handle.name, target)
    finally:
        if not handle.closed:
            handle.close()
        if os.path.exists(handle.name):
            os.unlink(handle.name)
    return target


def read_text(path: str | Path, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return default


def write_text(path: str | Path, text: str) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(text, encoding="utf-8")
    return target


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def truncate(text: Any, limit: int = 400) -> str:
    value = "" if text is None else str(text)
    return value if len(value) <= limit else value[: limit - 1] + "…"


# --------------------------------------------------------------------------- text
def norm_text(value: Any) -> str:
    """Upper-case, punctuation-free token string used for fuzzy name matching."""
    return _WS.sub(" ", str(value or "").upper()).strip()


def tokens(value: Any) -> list[str]:
    return [t for t in norm_text(value).split(" ") if t]


def token_similarity(left: Any, right: Any) -> float:
    """Jaccard similarity over normalized tokens."""
    a, b = set(tokens(left)), set(tokens(right))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def contains_alias(applicant: Any, alias: Any) -> bool:
    """True when the alias tokens appear **contiguously** in the applicant tokens.

    A plain subset test would let ``JOHNSON CONTROLS INC`` match the alias
    ``JOHNSON & JOHNSON`` (both reduce to the token ``JOHNSON``), silently
    assigning unrelated companies to a parent. Requiring a contiguous run keeps
    "DEPUY SYNTHES" working while rejecting that class of false positive.
    """
    applicant_tokens = tokens(applicant)
    alias_tokens = tokens(alias)
    if not alias_tokens or len(alias_tokens) > len(applicant_tokens):
        return False
    width = len(alias_tokens)
    return any(
        applicant_tokens[index : index + width] == alias_tokens
        for index in range(len(applicant_tokens) - width + 1)
    )


# --------------------------------------------------------------------------- stats
def summarize(values: Iterable[float | None]) -> dict[str, Any]:
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if not n:
        return {"n": 0, "mean": None, "median": None, "std": None, "min": None, "max": None}
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
    ordered = sorted(vals)
    mid = n // 2
    median = ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])
    return {
        "n": n,
        "mean": mean,
        "median": median,
        "std": math.sqrt(var),
        "min": ordered[0],
        "max": ordered[-1],
    }


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float] | None = None,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 7,
) -> dict[str, Any] | None:
    """Percentile bootstrap CI. Returns ``None`` when fewer than 3 observations."""
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n < 3:
        return None
    fn = stat or (lambda xs: sum(xs) / len(xs))
    rng = random.Random(seed)
    sampled = []
    for _ in range(n_boot):
        drawn = [vals[rng.randrange(n)] for _ in range(n)]
        sampled.append(fn(drawn))
    sampled.sort()
    low = sampled[max(0, int(alpha / 2 * n_boot))]
    high = sampled[min(n_boot - 1, int((1 - alpha / 2) * n_boot) - 1)]
    return {"point": fn(vals), "lo": low, "hi": high, "n": n, "n_boot": n_boot}


def t_stat(values: Sequence[float]) -> float | None:
    """One-sample t statistic against zero."""
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n < 2:
        return None
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    if var <= 0:
        return None
    return mean / math.sqrt(var / n)


def _gamma_draws(shape: float, rate: float, draws: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    scale = 1.0 / rate
    return sorted(rng.gammavariate(shape, scale) for _ in range(draws))


def gamma_poisson(
    count: float,
    exposure: float,
    prior_rate: float,
    prior_strength: float,
    draws: int = 4000,
    seed: int = 7,
) -> dict[str, float]:
    """Empirical-Bayes Gamma-Poisson posterior for an event rate.

    ``count`` events observed over ``exposure`` (in the same unit as
    ``prior_rate``). The ``Gamma(prior_rate * prior_strength, prior_strength)``
    prior shrinks small-sample companies towards their peer group instead of
    letting a single clearance masquerade as a trend.
    """
    count = max(0.0, float(count))
    exposure = max(0.0, float(exposure))
    prior_rate = max(1e-9, float(prior_rate))
    prior_strength = max(1e-9, float(prior_strength))
    shape = prior_rate * prior_strength + count
    rate = prior_strength + exposure
    sampled = _gamma_draws(shape, rate, draws, seed)
    return {
        "mean": shape / rate,
        "lo": sampled[int(0.025 * draws)],
        "hi": sampled[min(draws - 1, int(0.975 * draws) - 1)],
        "shape": shape,
        "rate": rate,
    }


def prob_rate_above(
    count: float,
    exposure: float,
    prior_rate: float,
    prior_strength: float,
    threshold: float,
    draws: int = 4000,
    seed: int = 11,
) -> float:
    """Posterior probability that the true rate exceeds ``threshold``."""
    count = max(0.0, float(count))
    exposure = max(0.0, float(exposure))
    shape = max(1e-9, float(prior_rate)) * max(1e-9, float(prior_strength)) + count
    rate = max(1e-9, float(prior_strength)) + exposure
    sampled = _gamma_draws(shape, rate, draws, seed)
    return sum(1 for value in sampled if value > threshold) / draws


def normalize_dist(weights: Mapping[str, float], eps: float = 1e-9) -> dict[str, float]:
    total = sum(max(0.0, float(v)) for v in weights.values())
    if total <= 0:
        return {key: 0.0 for key in weights}
    return {key: max(0.0, float(value)) / total for key, value in weights.items()}


def js_divergence(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    """Jensen-Shannon divergence (nats, ``[0, ln 2]``) with additive smoothing.

    We use it to ask "did this company's portfolio mix really move?" rather than
    "did the absolute count change?" - a company can clear fewer devices while
    shifting decisively into a new category.
    """
    keys = sorted(set(left) | set(right))
    if not keys:
        return 0.0
    eps = 1e-9
    p = normalize_dist({k: max(0.0, left.get(k, 0.0)) + eps for k in keys})
    q = normalize_dist({k: max(0.0, right.get(k, 0.0)) + eps for k in keys})

    def _kl(a: Mapping[str, float], b: Mapping[str, float]) -> float:
        total = 0.0
        for key in keys:
            if a[key] > 0:
                total += a[key] * math.log(a[key] / b[key])
        return total

    mid = {k: 0.5 * (p[k] + q[k]) for k in keys}
    return max(0.0, 0.5 * _kl(p, mid) + 0.5 * _kl(q, mid))


def share(count: float, total: float) -> float:
    return float(count) / float(total) if total else 0.0
