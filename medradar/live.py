"""Live, event-driven paper trading on **real** US market data.

Two lanes, different physics
----------------------------
* **Slow lane** (``analyze`` + ``report``): openFDA is 2-12 days behind the FDA
  decision, so it answers "what is the industry doing" - never "what just happened".
* **Fast lane** (this module): SEC EDGAR publishes 8-K filings seconds after they
  are accepted, FDA press releases land in an RSS feed, and ClinicalTrials.gov
  reflects status changes within a day. Those are the only public signals fast
  enough to act on.

Every 5-15 minutes the loop does: poll catalysts -> classify -> simulate an order
at the latest real quote -> mark the book -> alert. Orders fill at the *latest
Yahoo Finance quote plus a slippage haircut*; nothing is sent to a broker, no
money is at risk.

Honest boundaries
-----------------
* **Not HFT.** Free quotes are delayed ~15 minutes for US equities; polling is
  minutes. This is "same-hour", not "same-second".
* **Long-only.** Shorting a trial failure is exactly where borrow fees and
  squeeze-outs destroy naive backtests, so the live lane does not pretend to
  model it (yet). ``direction = -1`` alerts are recorded and alerted, not traded.
* **No pending-queue visibility.** The FDA does not publish submissions under
  review; a 510(k) is invisible until its decision is published. No tool can
  change that.
* **Not investment advice.** Simulation for research and education only.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .config import CACHE_DIR, DEFAULT_DB, load_companies
from .db import DB
from .http import Fetcher
from .llm import make_judge
from .util import ensure_dir, read_json, sha1, truncate, write_json

EDGAR_CURRENT = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
    "&type=8-K&company=&dateb=&owner=include&count=100&output=atom"
)
EDGAR_TICKERS = "https://www.sec.gov/files/company_tickers.json"
FDA_PRESS_RSS = (
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/"
    "press-releases/rss.xml"
)
CTGOV_STUDIES = "https://clinicaltrials.gov/api/v2/studies"
EDGAR_FTS = "https://efts.sec.gov/LATEST/search-index"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

SEC_UA = os.environ.get(
    "MEDRADAR_SEC_UA", "MedRadar research (open-source; contact: medradar@example.com)"
)

# ---------------------------------------------------------------- classification
NEGATIVE_PHRASES = (
    "complete response letter",
    "did not meet",
    "failed to meet",
    "did not achieve",
    "fails to meet",
    "discontinued",
    "terminated the",
    "clinical hold",
    "serious adverse",
    "safety signal",
    "voluntary recall",
    "does not support approval",
)
POSITIVE_PHRASES = (
    "fda approval",
    "approved by the fda",
    "fda has approved",
    "met the primary endpoint",
    "achieved the primary endpoint",
    "positive topline",
    "statistically significant",
    "breakthrough therapy designation",
    "priority review",
    "granted accelerated approval",
)
TERMINAL_TRIAL_STATUSES = ("TERMINATED", "SUSPENDED", "WITHDRAWN")

# Only the fresh EDGAR 8-K feed may open a position. FDA RSS is days stale,
# full-text backfill is by definition in the past, and trial status changes are
# informational - allowing any of them to fill would be lookahead bias.
TRADEABLE_SOURCES = {"sec_edgar"}
MAX_QUOTE_AGE_SECONDS = 1_800.0  # 30 minutes; older quotes are "stale"
# Yahoo returns these market states; only a continuous session may fill an order.
MARKET_OPEN_STATES = {"REGULAR"}
# A pending order that cannot fill for this long is dropped (news is stale by then).
PENDING_TTL_HOURS = 24.0

# EDGAR item codes that can carry a clinical/regulatory catalyst
CATALYST_ITEMS = ("8.01", "7.01", "1.01", "2.02", "2.05")


@dataclass
class LiveParams:
    capital: float = 100_000.0
    max_position: float = 0.05
    max_track: float = 0.25
    slippage_bps: float = 10.0
    max_buys: int = 5
    max_hold_days: int = 84  # ~60 trading days
    stop_loss: float = -0.20
    since_hours: float = 24.0
    backfill_days: float = 0.0
    no_trade: bool = False
    fetch_text: bool = True
    use_llm: bool = True
    llm_budget: int = 4
    webhook: str | None = None


# --------------------------------------------------------------------- EDGAR atom
_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.S)
_LINK_RE = re.compile(r'<link[^>]*href="([^"]+)"')
_UPDATED_RE = re.compile(r"<updated>(.*?)</updated>")
_SUMMARY_RE = re.compile(r"<summary[^>]*>(.*?)</summary>", re.S)
_ACC_RE = re.compile(r"accession-number=([0-9-]+)")
_ITEM_RE = re.compile(r"Item\s+(\d\.\d\d):\s*([^<&]+)")
_CIK_IN_TITLE_RE = re.compile(r"\((\d{10})\)")


def parse_edgar_atom(xml: str) -> list[dict[str, Any]]:
    """Parse the EDGAR current-filings Atom feed into plain dicts."""
    entries: list[dict[str, Any]] = []
    for block in _ENTRY_RE.findall(xml):
        title_match = _TITLE_RE.search(block)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
        cik_match = _CIK_IN_TITLE_RE.search(title)
        if not cik_match:
            continue
        link_match = _LINK_RE.search(block)
        updated_match = _UPDATED_RE.search(block)
        acc_match = _ACC_RE.search(block)
        if not (acc_match and link_match):
            continue
        items = [code for code, _label in _ITEM_RE.findall(block)]
        entries.append(
            {
                "form": (title.split(" - ", 1)[0] or "8-K").strip(),
                "company_name": re.sub(r"\s*\(\d{10}\)\s*\(Filer\)\s*$", "", title).split(" - ", 1)[-1].strip(),
                "cik": int(cik_match.group(1)),
                "accession": acc_match.group(1),
                "url": link_match.group(1),
                "event_time": updated_match.group(1) if updated_match else "",
                "items": items,
            }
        )
    return entries


def classify_text(text: str) -> tuple[int, float, list[str]]:
    """Headline-level catalyst classifier: (-1/0/+1, score, matched phrases)."""
    haystack = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    negative = [phrase for phrase in NEGATIVE_PHRASES if phrase in haystack]
    positive = [phrase for phrase in POSITIVE_PHRASES if phrase in haystack]
    matched = negative + positive
    if not negative and not positive:
        return 0, 0.0, []
    direction = 1 if len(positive) > len(negative) else (-1 if len(negative) > len(positive) else 0)
    strength = abs(len(positive) - len(negative))
    score = min(0.95, 0.45 + 0.1 * strength + 0.05 * len(matched))
    return direction, round(score, 3), matched


# ----------------------------------------------------------------------- market data
def quote(fetcher: Fetcher, ticker: str, max_age_seconds: float = MAX_QUOTE_AGE_SECONDS) -> dict[str, Any] | None:
    """Latest real quote: last 1-minute bar, falling back to the previous close.

    Returns ``stale=True`` when the quote is older than ``max_age_seconds``
    (market closed, halted ticker, delayed feed). Stale quotes may be used to
    mark the book but never to fill an order.
    """
    try:
        payload = fetcher.get_json(
            YAHOO_CHART.format(ticker=ticker), {"range": "1d", "interval": "1m"}
        )
        result = (payload.get("chart") or {}).get("result") or [{}]
        meta = result[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        timestamp = meta.get("regularMarketTime")
        if price is None:
            quotes = ((result[0].get("indicators") or {}).get("quote") or [{}])[0]
            closes = [value for value in (quotes.get("close") or []) if value is not None]
            price = closes[-1] if closes else None
        if price is None:
            return None
        age_seconds: float | None = None
        if timestamp is not None:
            try:
                age_seconds = max(0.0, datetime.now(timezone.utc).timestamp() - float(timestamp))
            except (TypeError, ValueError):
                age_seconds = None
        return {
            "ticker": ticker,
            "price": float(price),
            "quote_time": _iso_from_epoch(timestamp),
            "market_state": meta.get("marketState"),
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "stale": bool(age_seconds is not None and age_seconds > max_age_seconds),
        }
    except Exception:
        return None


def _iso_from_epoch(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


# ------------------------------------------------------------------------ decision
def size_order(
    cash: float,
    equity: float,
    price: float,
    track_exposure: float,
    params: LiveParams,
    materiality: float = 1.0,
) -> float:
    """Fractional share count for a new long, respecting per-name and per-track caps.

    ``materiality`` (0-1, from the LLM judge) scales the position between 20% and
    100% of the per-name cap: a first-in-class approval gets 5%, a routine label
    tweak gets 1%.
    """
    if price <= 0 or cash <= 0 or equity <= 0:
        return 0.0
    scale = min(1.0, max(0.2, float(materiality or 0.0)))
    budget = min(equity * params.max_position * scale, cash)
    track_room = equity * params.max_track - track_exposure
    budget = min(budget, max(0.0, track_room))
    return math.floor((budget / price) * 10_000) / 10_000


def fill_price(price: float, side: str, slippage_bps: float) -> float:
    """Apply a slippage haircut so simulated P&L is not free."""
    edge = price * (slippage_bps / 10_000.0)
    return price + edge if side == "buy" else price - edge


# ------------------------------------------------------------------------- polling
def poll_edgar(
    db: DB,
    fetcher: Fetcher,
    watchlist: Mapping[int, tuple[str, str]],
    since: datetime,
    params: LiveParams,
    judge: Any = None,
) -> list[dict[str, Any]]:
    xml = fetcher.get_text(EDGAR_CURRENT)
    alerts: list[dict[str, Any]] = []
    text_budget = 6
    for entry in parse_edgar_atom(xml):
        if entry["cik"] not in watchlist:
            continue
        detected = _parse_iso(entry["event_time"])
        if detected and detected < since:
            continue
        company_key, ticker = watchlist[entry["cik"]]
        direction, score, matched = 0, 0.0, []
        verdict: dict[str, Any] = {}
        item_hit = [item for item in entry["items"] if item in CATALYST_ITEMS]
        headline = f"{entry['company_name']} 8-K（Item {','.join(entry['items']) or 'n/a'}）"
        if params.fetch_text and item_hit and text_budget > 0:
            text_budget -= 1
            body = fetch_filing_text(fetcher, entry["cik"], entry["accession"])
            if body:
                if judge is not None:
                    verdict = judge.judge_filing(headline, body)
                    direction = int(verdict.get("direction") or 0)
                    score = float(verdict.get("materiality") or verdict.get("confidence") or 0.4)
                    matched = list(verdict.get("evidence_quotes") or [])
                else:
                    direction, score, matched = classify_text(body)
        if not item_hit and direction == 0:
            continue  # routine 8-K (officer changes, exhibits) - not a catalyst
        alerts.append(
            {
                "alert_id": "edgar-" + entry["accession"],
                "source": "sec_edgar",
                "kind": "8k_catalyst",
                "ticker": ticker,
                "company_key": company_key,
                "direction": direction,
                "score": score if score else 0.4,
                "materiality": float(verdict.get("materiality") or 0.0),
                "catalyst_type": verdict.get("catalyst_type", ""),
                "headline": headline,
                "url": entry["url"],
                "event_time": entry["event_time"],
                "payload": {
                    "items": entry["items"],
                    "matched": matched,
                    "cik": entry["cik"],
                    "verdict": verdict or None,
                },
            }
        )
    return alerts


def poll_edgar_fts(
    db: DB,
    fetcher: Fetcher,
    watchlist: Mapping[int, tuple[str, str]],
    since: datetime,
    params: LiveParams,
) -> list[dict[str, Any]]:
    """Recent catalyst filings via EDGAR full-text search (first run / backfill).

    Used only to seed the alert log on the first cycle and for demos. These
    alerts are tagged ``backfill`` and the broker refuses to trade them: filling
    a week-old catalyst at today's quote would be lookahead bias dressed up as
    live trading.
    """
    if params.backfill_days <= 0:
        return []
    queries = (
        ("complete response letter", -1, 0.62),
        ("did not meet", -1, 0.55),
        ("fda approval", 1, 0.6),
        ("primary endpoint met", 1, 0.65),
    )
    start = (datetime.now(timezone.utc) - timedelta(days=params.backfill_days)).date().isoformat()
    end = datetime.now(timezone.utc).date().isoformat()
    alerts: list[dict[str, Any]] = []
    for query, direction, score in queries:
        try:
            payload = fetcher.get_json(
                EDGAR_FTS,
                {
                    "q": query,
                    "forms": "8-K",
                    "dateRange": "custom",
                    "startdt": start,
                    "enddt": end,
                    "hits": 100,
                },
            )
        except Exception:
            continue
        for hit in ((payload.get("hits") or {}).get("hits") or []):
            source = hit.get("_source") or {}
            ciks = [int(value) for value in (source.get("ciks") or []) if str(value).isdigit()]
            match = next((cik for cik in ciks if cik in watchlist), None)
            if not match:
                continue
            company_key, ticker = watchlist[match]
            accession, _, document = str(hit.get("_id") or "").partition(":")
            if not document:
                continue
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{match}/"
                f"{accession.replace('-', '')}/{document}"
            )
            alerts.append(
                {
                    "alert_id": "edgar-fts-" + sha1(accession + document)[:16],
                    "source": "sec_edgar_fts",
                    "kind": "8k_catalyst",
                    "ticker": ticker,
                    "company_key": company_key,
                    "direction": direction,
                    "score": score,
                    "headline": f"{(source.get('display_names') or [''])[0][:80]} · {query}",
                    "url": url,
                    "event_time": str(source.get("file_date") or ""),
                    "payload": {"query": query, "backfill": True},
                }
            )
    return alerts


def fetch_filing_text(fetcher: Fetcher, cik: int, accession: str, max_chars: int = 200_000) -> str:

    """Primary document of one filing (2 requests max, capped)."""
    accession_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}"
    try:
        index = fetcher.get_json(base + "/index.json")
    except Exception:
        return ""
    items = ((index.get("directory") or {}).get("item") or [])
    docs = [
        item
        for item in items
        if str(item.get("name", "")).lower().endswith((".htm", ".html", ".txt"))
        and "index" not in str(item.get("name", "")).lower()
    ]
    docs.sort(key=lambda item: -int(item.get("size") or 0))
    for doc in docs[:2]:
        try:
            text = fetcher.get_text(f"{base}/{doc['name']}")
        except Exception:
            continue
        if text:
            return text[:max_chars]
    return ""


def poll_fda_rss(
    db: DB, fetcher: Fetcher, registry, since: datetime
) -> list[dict[str, Any]]:
    """FDA press releases (approvals, CRLs, safety) - the fastest official feed."""
    import xml.etree.ElementTree as ET

    try:
        raw = fetcher.get_text(FDA_PRESS_RSS)
        root = ET.fromstring(raw)
    except Exception:
        return []
    alerts: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = _parse_rfc822(item.findtext("pubDate") or "")
        if pub and pub < since:
            continue
        direction, score, matched = classify_text(title + " " + (item.findtext("description") or ""))
        if direction == 0 and not matched:
            continue
        company_key, ticker = _match_company(registry, title)
        alerts.append(
            {
                "alert_id": "fda-" + sha1(link or title)[:16],
                "source": "fda_press",
                "kind": "fda_press",
                "ticker": ticker,
                "company_key": company_key,
                "direction": direction,
                "score": score or 0.4,
                "headline": truncate(title, 200),
                "url": link,
                "event_time": pub.isoformat() if pub else "",
                "payload": {"matched": matched},
            }
        )
    return alerts


def poll_trials(
    db: DB, fetcher: Fetcher, registry, since: datetime
) -> list[dict[str, Any]]:
    """ClinicalTrials.gov status changes (terminations are the tradeable part)."""
    fields = "NCTId,BriefTitle,OverallStatus,LastUpdatePostDate,LeadSponsorName,Phase"
    try:
        payload = fetcher.get_json(
            CTGOV_STUDIES,
            {
                "pageSize": 100,
                "sort": "LastUpdatePostDate:desc",
                "fields": fields,
            },
        )
    except Exception:
        return []
    alerts: list[dict[str, Any]] = []
    for study in payload.get("studies") or []:
        section = study.get("protocolSection") or {}
        status_module = section.get("statusModule") or {}
        ident = section.get("identificationModule") or {}
        sponsor_module = section.get("sponsorCollaboratorsModule") or {}
        sponsor = (sponsor_module.get("leadSponsor") or {}).get("name") or ""
        updated = _parse_iso((status_module.get("lastUpdatePostDateStruct") or {}).get("date", ""))
        if updated and updated < since:
            continue
        status = (status_module.get("overallStatus") or "").upper()
        company_key, ticker = _match_company(registry, sponsor)
        if not ticker and not company_key:
            continue
        direction = -1 if status in TERMINAL_TRIAL_STATUSES else 0
        alerts.append(
            {
                "alert_id": "ctgov-" + sha1((ident.get("nctId") or "") + status)[:16],
                "source": "ctgov",
                "kind": "trial_update",
                "ticker": ticker,
                "company_key": company_key,
                "direction": direction,
                "score": 0.5 if direction else 0.3,
                "headline": f"{sponsor}: {ident.get('briefTitle', '')} [{status}]",
                "url": f"https://clinicaltrials.gov/study/{ident.get('nctId', '')}",
                "event_time": updated.isoformat() if updated else "",
                "payload": {"status": status, "phase": (section.get("designModule") or {}).get("phases")},
            }
        )
    return alerts


# ---------------------------------------------------------------- quote validity
def quote_verdict(alert: Mapping[str, Any], market: Mapping[str, Any] | None, now: datetime) -> tuple[bool, str]:
    """Decide whether a quote is usable for a **new** fill, and say why not.

    Four independent conditions, each of which has caused a real bad fill or a
    silent no-trade bug: the market must be open, the quote must carry a
    timestamp, that timestamp must not predate the news, and it must be fresh.
    """
    market = market or {}
    price = market.get("price")
    if not price or float(price) <= 0:
        return False, "no_price"
    state = str(market.get("market_state") or "").upper()
    if not state:
        return False, "market_state_missing"
    if state not in MARKET_OPEN_STATES:
        return False, "market_closed"
    quote_time = _parse_iso(str(market.get("quote_time") or ""))
    if quote_time is None:
        return False, "quote_time_missing"
    if (now - quote_time).total_seconds() > MAX_QUOTE_AGE_SECONDS:
        return False, "stale_quote"
    news_time = _parse_iso(str(alert.get("event_time") or ""))
    if news_time is not None and quote_time < news_time:
        return False, "quote_before_news"
    if market.get("stale"):
        return False, "stale_quote"
    return True, ""


def _record_skip(db: DB, alert: Mapping[str, Any], reason: str) -> None:
    db.execute(
        "INSERT INTO live_skips(ts, alert_id, ticker, reason) VALUES (?,?,?,?)",
        (
            datetime.now(timezone.utc).isoformat(),
            alert.get("alert_id") or "",
            (alert.get("ticker") or "").upper(),
            reason,
        ),
    )


def _queue_pending(db: DB, alert: Mapping[str, Any], ticker: str, reason: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO live_pending(alert_id, ticker, created_at, attempts, last_attempt_at, last_reason, status)"
        " VALUES (?,?,?,0,?,?,'pending')"
        " ON CONFLICT(alert_id) DO UPDATE SET attempts = attempts + 1,"
        " last_attempt_at = excluded.last_attempt_at, last_reason = excluded.last_reason",
        (alert.get("alert_id") or "", ticker, now, now, reason),
    )
    db.conn.commit()


def _resolve_pending(db: DB, alert_id: str, commit: bool = True) -> None:
    db.execute("UPDATE live_pending SET status = 'done' WHERE alert_id = ?", (alert_id,))
    if commit:
        db.conn.commit()


def _expire_pending(db: DB, now: datetime) -> None:
    """Expire by *first queued* time.

    Using ``last_attempt_at`` would let a news item that keeps failing to quote
    stay tradeable forever (each retry refreshes the clock). The TTL is about the
    age of the news, so it must anchor on ``created_at``.
    """
    cutoff = (now - timedelta(hours=PENDING_TTL_HOURS)).isoformat()
    db.execute("UPDATE live_pending SET status = 'expired', last_reason = 'pending_expired'"
               " WHERE status = 'pending' AND created_at < ?", (cutoff,))
    db.conn.commit()


def pending_alerts(db: DB) -> list[dict[str, Any]]:
    """Rehydrate queued orders from the alert table, oldest first."""
    rows = db.query(
        "SELECT p.alert_id FROM live_pending p WHERE p.status = 'pending' ORDER BY p.created_at"
    )
    alerts: list[dict[str, Any]] = []
    for row in rows:
        stored = db.query("SELECT * FROM live_alerts WHERE alert_id = ?", (row["alert_id"],))
        if not stored:
            continue
        item = dict(stored[0])
        try:
            item["payload"] = json.loads(item.get("payload") or "{}")
        except (TypeError, ValueError):
            item["payload"] = {}
        item["materiality"] = item["payload"].get("materiality") or item.get("materiality")
        item["catalyst_type"] = item["payload"].get("catalyst_type") or item.get("catalyst_type")
        alerts.append(item)
    return alerts


def _assert_book_invariant(db: DB, params: LiveParams, context: str = "") -> dict[str, float]:
    """Fail closed unless cash is explained by the fills ledger and never negative.

    The original bug (buys created positions without debiting cash) is invisible to
    a naive "cash + holdings = equity" check because equity is *defined* that way.
    Comparing ``live.cash`` against ``capital ± every recorded fill`` catches it.
    A manually seeded book (tests, migrations) has no ledger and is exempt.
    """
    cash = float(db.meta_get("live.cash", params.capital))
    positions = db.query("SELECT ticker, qty, last_price FROM positions WHERE status = 'open'")
    market_value = 0.0
    for position in positions:
        market_value += float(position["qty"] or 0) * float(position["last_price"] or 0)
    orders = db.query("SELECT side, qty, fill_price FROM paper_orders")
    seeded = bool(db.meta_get("live.seeded"))
    if seeded:
        # Explicitly imported/test book: its opening ledger is unknown.
        pass
    else:
        ledger_cash = float(params.capital)
        for order in orders:
            signed = 1.0 if order["side"] == "sell" else -1.0
            ledger_cash += signed * float(order["qty"] or 0) * float(order["fill_price"] or 0)
        if abs(ledger_cash - cash) > 1e-6:
            raise RuntimeError(
                f"live invariant violated after {context}: cash={cash:.6f} != ledger={ledger_cash:.6f}"
            )
    if cash < -1e-6:
        raise RuntimeError(f"live invariant violated after {context}: cash={cash:.6f} < 0")
    if market_value < -1e-6:
        raise RuntimeError(f"live invariant violated after {context}: market_value={market_value:.6f} < 0")
    return {"cash": cash, "market_value": market_value, "equity": cash + market_value}


# -------------------------------------------------------------------- execution
def run_once(
    db_path: str | Path = DEFAULT_DB,
    params: LiveParams | None = None,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
    quote_fn: Callable[[Fetcher, str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """One full cycle: poll -> alert -> trade -> mark. Safe to run from cron."""
    params = params or LiveParams()
    now = now or datetime.now(timezone.utc)
    quote_fn = quote_fn or quote
    # SEC's fair-access policy rejects generic user agents (HTTP 403); the UA
    # must carry a contact. The same UA is harmless for FDA RSS / CT.gov.
    fetcher = fetcher or Fetcher(
        cache_dir=None, min_interval=0.35, max_requests=200, ua=SEC_UA
    )
    registry = load_companies("device")
    registry_drug = load_companies("drug")

    with DB(db_path) as db:
        _init_state(db, params)
        watchlist = _watchlist(db, fetcher, registry, registry_drug)
        judge = make_judge(db, use_llm=params.use_llm, budget=params.llm_budget)
        since = _since(db, params, now)
        fresh: list[dict[str, Any]] = []

        for source, poller in (
            ("edgar", lambda: poll_edgar(db, fetcher, watchlist, since, params, judge)),
            ("edgar_fts", lambda: poll_edgar_fts(db, fetcher, watchlist, since, params)),
            ("fda_rss", lambda: poll_fda_rss(db, fetcher, registry_drug, since)),
            ("ctgov", lambda: poll_trials(db, fetcher, registry_drug, since)),
        ):
            try:
                fresh.extend(poller())
            except Exception as exc:  # one flaky feed must not kill the cycle
                db.meta_set(f"live.error.{source}", f"{type(exc).__name__}: {exc}")
        new_alerts = _store_alerts(db, fresh)

        orders, skipped = _handle_exits(db, fetcher, quote_fn, params)
        if not params.no_trade:
            entry_orders, entry_skips = _handle_entries(db, fetcher, quote_fn, params, new_alerts, watchlist)
            orders.extend(entry_orders)
            for reason, count in entry_skips.items():
                skipped[reason] = skipped.get(reason, 0) + count
        book = _mark(db, fetcher, quote_fn, params, now)
        _assert_book_invariant(db, params, context="cycle")
        db.meta_set("live.last_cycle", now.isoformat())
        db.log_run("live", {"alerts": len(new_alerts), "orders": len(orders), "skipped": skipped, **book})

    result = {
        "cycle_at": now.isoformat(),
        "alerts_new": len(new_alerts),
        "alerts": new_alerts,
        "orders": orders,
        "skipped": skipped,
        "book": book,
        "params": {
            "capital": params.capital,
            "max_position": params.max_position,
            "slippage_bps": params.slippage_bps,
            "long_only": True,
        },
        "disclaimer_zh": "模拟盘：按真实行情成交并计滑点，不构成投资建议；v1 仅做多。",
    }
    notify(result, params)
    return result


def _init_state(db: DB, params: LiveParams) -> None:
    if db.meta_get("live.cash") is None:
        db.meta_set("live.cash", params.capital)
    # Seeded books are declared explicitly (tests/importers set live.seeded).
    # Never infer it from "cash != capital and no orders": that is exactly what a
    # crashed half-fill looks like, and silently exempting it would hide the bug.
    if db.meta_get("live.started_at") is None:
        db.meta_set("live.started_at", datetime.now(timezone.utc).isoformat())


def _since(db: DB, params: LiveParams, now: datetime) -> datetime:
    last = db.meta_get("live.last_cycle")
    if last:
        try:
            return max(_parse_iso(last), now - timedelta(hours=params.since_hours))
        except Exception:
            pass
    return now - timedelta(hours=params.since_hours)


def _watchlist(db: DB, fetcher: Fetcher, *registries) -> dict[int, tuple[str, str]]:
    """CIK -> (company_key, ticker) for every watchlist name SEC knows about."""
    try:
        payload = fetcher.get_json(EDGAR_TICKERS)
    except Exception as exc:
        # A silent empty watchlist is the worst failure mode: every source then
        # reports "no news" while actually being blind. Surface it.
        db.meta_set("live.error.edgar_tickers", f"{type(exc).__name__}: {exc}")
        return {}
    ticker_to_cik: dict[str, int] = {}
    for item in payload.values() if isinstance(payload, dict) else []:
        try:
            ticker_to_cik[str(item["ticker"]).upper()] = int(item["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
    mapping: dict[int, tuple[str, str]] = {}
    for registry in registries:
        for key, ticker in registry.tickers().items():
            cik = ticker_to_cik.get(str(ticker).upper())
            if cik:
                mapping[cik] = (key, ticker)
    return mapping


def _store_alerts(db: DB, alerts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    fresh: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for alert in alerts:
        if db.scalar("SELECT 1 FROM live_alerts WHERE alert_id = ?", (alert["alert_id"],)):
            continue
        # Cross-source dedupe: one approval usually shows up as the EDGAR feed
        # item, a full-text hit, and often an FDA press release on the same day.
        # Those are one event, not three independent opportunities.
        ticker = (alert.get("ticker") or "").upper()
        event_day = (alert.get("event_time") or "")[:10]
        if ticker and event_day:
            duplicate = db.scalar(
                "SELECT 1 FROM live_alerts WHERE ticker = ? AND kind = ?"
                " AND substr(event_time, 1, 10) = ? LIMIT 1",
                (ticker, alert.get("kind") or "", event_day),
            )
            if duplicate:
                continue
        db.execute(
            "INSERT OR REPLACE INTO live_alerts(alert_id, source, kind, ticker, company_key,"
            " direction, score, headline, url, event_time, detected_at, payload)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                alert["alert_id"],
                alert["source"],
                alert["kind"],
                alert.get("ticker") or "",
                alert.get("company_key") or "",
                int(alert.get("direction") or 0),
                float(alert.get("score") or 0.0),
                alert.get("headline") or "",
                alert.get("url") or "",
                alert.get("event_time") or "",
                now,
                json.dumps(
                    {
                        **(alert.get("payload") or {}),
                        "materiality": alert.get("materiality"),
                        "catalyst_type": alert.get("catalyst_type") or "",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        db.conn.commit()
        fresh.append(alert)
    return fresh


def _handle_entries(
    db: DB,
    fetcher: Fetcher,
    quote_fn: Callable,
    params: LiveParams,
    alerts: list[dict[str, Any]],
    watchlist: Mapping[int, tuple[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Open long positions, debiting cash, and queue anything that cannot fill yet."""
    orders: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    now = datetime.now(timezone.utc)
    _expire_pending(db, now)
    cash = float(db.meta_get("live.cash", params.capital))
    book = _book_state(db)
    track_exposure = dict(book["track_exposure"])
    registry = load_companies("device")
    traded = 0

    def skip(alert: Mapping[str, Any], reason: str, queue: bool = False) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1
        _record_skip(db, alert, reason)
        if queue:
            _queue_pending(db, alert, (alert.get("ticker") or "").upper(), reason)

    candidates = pending_alerts(db) + list(alerts)
    seen: set[str] = set()
    for alert in candidates:
        alert_id = str(alert.get("alert_id") or "")
        if not alert_id or alert_id in seen:
            continue
        seen.add(alert_id)
        if traded >= params.max_buys:
            break
        ticker = (alert.get("ticker") or "").upper()
        if not ticker:
            skip(alert, "no_ticker")
            continue
        if int(alert.get("direction") or 0) <= 0:
            skip(alert, "not_long_catalyst")
            continue
        if alert.get("source") not in TRADEABLE_SOURCES:
            skip(alert, "non_tradeable_source")
            continue
        if (alert.get("payload") or {}).get("backfill"):
            skip(alert, "backfill_lookahead")
            continue
        if (alert.get("catalyst_type") or "") == "earnings":
            skip(alert, "earnings_not_tradeable")
            continue
        if db.scalar("SELECT qty FROM positions WHERE ticker = ? AND status = 'open'", (ticker,)):
            skip(alert, "already_open")
            continue
        market = quote_fn(fetcher, ticker) or {}
        ok, reason = quote_verdict(alert, market, now)
        if not ok:
            # Transient conditions are queued and retried next cycle.
            queue = reason in {"no_price", "market_closed", "market_state_missing",
                               "quote_time_missing", "stale_quote", "quote_before_news"}
            skip(alert, reason, queue=queue)
            continue
        price = float(market["price"])
        company_key = alert.get("company_key") or ""
        entry = registry.get(company_key) or {}
        track_id = entry.get("sector") or "device"
        equity_now = cash + book["market_value"]
        # Size on the *filled* price so slippage can never push cash negative.
        price_filled = fill_price(price, "buy", params.slippage_bps)
        qty = size_order(
            cash,
            equity_now,
            price_filled,
            track_exposure.get(track_id, 0.0),
            params,
            materiality=float(alert.get("materiality") or 1.0),
        )
        cost = qty * price_filled
        if qty <= 0:
            skip(alert, "size_zero")
            continue
        if cost > cash + 1e-9:
            skip(alert, "insufficient_cash")
            continue

        before_equity = cash + book["market_value"]
        new_cash = cash - cost  # the actual debit; its absence was the release-blocking bug
        if new_cash < -1e-9:
            skip(alert, "insufficient_cash")
            continue
        # Cash, position, fill record and pending state commit as one unit. A crash
        # anywhere inside must leave the book exactly as it was, with the alert
        # still queued for the next cycle.
        try:
            with db.transaction():
                db.meta_set("live.cash", round(new_cash, 6), commit=False)
                db.execute(
                    "INSERT OR REPLACE INTO positions(ticker, qty, avg_price, opened_at, track_id,"
                    " last_price, last_quote_time, market_value, unrealized_pnl, status)"
                    " VALUES (?,?,?,?,?,?,?,?,?, 'open')",
                    (
                        ticker,
                        qty,
                        price_filled,
                        now.isoformat(),
                        track_id,
                        price,
                        market.get("quote_time") or "",
                        qty * price,
                        0.0,
                    ),
                )
                order = _record_order(db, alert, ticker, "buy", qty, price_filled, market, params, commit=False)
                _resolve_pending(db, alert_id, commit=False)
        except Exception:
            # The fill transaction rolled back; queue the alert durably (outside the
            # rolled-back tx) so the next cycle retries instead of losing the trade.
            _queue_pending(db, alert, ticker, "fill_failed")
            raise
        cash = new_cash
        orders.append(order)
        traded += 1
        track_exposure[track_id] = track_exposure.get(track_id, 0.0) + qty * price
        book["market_value"] = book["market_value"] + qty * price

        # Money-conservation check: equity may only change by the slippage cost.
        after = _assert_book_invariant(db, params, context=f"buy {ticker}")
        expected = before_equity - qty * (price_filled - price)
        if abs(after["equity"] - expected) > 1e-6:
            raise RuntimeError(
                f"live invariant violated after buy {ticker}: equity={after['equity']:.6f}"
                f" expected={expected:.6f}"
            )
    _assert_book_invariant(db, params, context="entries")
    return orders, skipped


def _handle_exits(
    db: DB,
    fetcher: Fetcher,
    quote_fn: Callable,
    params: LiveParams,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if params.no_trade:
        return [], {}  # --no-trade must freeze the whole book, exits included
    orders: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    cash = float(db.meta_get("live.cash", params.capital))
    now = datetime.now(timezone.utc)
    positions = db.query("SELECT * FROM positions WHERE status = 'open'")
    for position in positions:
        ticker = position["ticker"]
        market = quote_fn(fetcher, ticker) or {}
        ok, reason = quote_verdict({"event_time": position.get("opened_at")}, market, now)
        if not ok:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        price = float(market["price"])
        change = price / float(position["avg_price"]) - 1 if position["avg_price"] else 0.0
        held_days = _days_held(position.get("opened_at"), now)
        reason = ""
        if change <= params.stop_loss:
            reason = "stop_loss"
        elif held_days >= params.max_hold_days:
            reason = "time_exit"
        if not reason:
            continue
        price_filled = fill_price(price, "sell", params.slippage_bps)
        qty = float(position["qty"])
        new_cash = cash + qty * price_filled
        alert = {"alert_id": f"exit-{ticker}-{int(now.timestamp())}", "headline": reason, "score": 0.5}
        with db.transaction():
            db.execute(
                "UPDATE positions SET status = 'closed', last_price = ?, last_quote_time = ?,"
                " unrealized_pnl = ? WHERE ticker = ?",
                (price, market.get("quote_time") or "", qty * (price_filled - float(position["avg_price"])), ticker),
            )
            db.meta_set("live.cash", round(new_cash, 6), commit=False)
            order = _record_order(db, alert, ticker, "sell", qty, price_filled, market, params, note=reason, commit=False)
        cash = new_cash
        orders.append(order)
    db.meta_set("live.cash", round(cash, 6))
    _assert_book_invariant(db, params, context="exits")
    return orders, skipped


def _record_order(
    db: DB,
    alert: Mapping[str, Any],
    ticker: str,
    side: str,
    qty: float,
    price: float,
    market: Mapping[str, Any],
    params: LiveParams,
    note: str = "",
    commit: bool = True,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    order_id = sha1(f"{alert.get('alert_id')}|{ticker}|{side}|{now}")[:20]
    db.execute(
        "INSERT OR REPLACE INTO paper_orders(order_id, alert_id, ticker, side, qty, fill_price,"
        " fill_time, quote_time, slippage_bps, status, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            order_id,
            alert.get("alert_id") or "",
            ticker,
            side,
            qty,
            price,
            now,
            market.get("quote_time") or "",
            params.slippage_bps,
            "filled",
            note or alert.get("headline") or "",
        ),
    )
    if commit:
        db.conn.commit()
    return {
        "order_id": order_id,
        "ticker": ticker,
        "side": side,
        "qty": qty,
        "fill_price": round(price, 4),
        "quote_time": market.get("quote_time"),
        "alert_id": alert.get("alert_id"),
        "note": note or alert.get("headline"),
    }


def _book_state(db: DB) -> dict[str, Any]:
    cash = float(db.meta_get("live.cash", 0.0))
    positions = db.query("SELECT * FROM positions WHERE status = 'open'")
    market_value = sum((p["market_value"] or 0.0) for p in positions)
    track_exposure: dict[str, float] = {}
    for position in positions:
        track_exposure[position["track_id"] or "device"] = (
            track_exposure.get(position["track_id"] or "device", 0.0) + (position["market_value"] or 0.0)
        )
    return {
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "equity": round(cash + market_value, 2),
        "n_positions": len(positions),
        "track_exposure": track_exposure,
    }


def _mark(
    db: DB,
    fetcher: Fetcher,
    quote_fn: Callable,
    params: LiveParams,
    now: datetime,
) -> dict[str, Any]:
    cash = float(db.meta_get("live.cash", params.capital))
    market_value = 0.0
    positions = db.query("SELECT * FROM positions WHERE status = 'open'")
    for position in positions:
        market = quote_fn(fetcher, position["ticker"]) or {}
        price = market.get("price")
        if price:
            qty = float(position["qty"])
            unrealized = qty * (float(price) - float(position["avg_price"]))
            db.execute(
                "UPDATE positions SET last_price = ?, last_quote_time = ?, market_value = ?,"
                " unrealized_pnl = ? WHERE ticker = ?",
                (
                    float(price),
                    market.get("quote_time") or "",
                    qty * float(price),
                    unrealized,
                    position["ticker"],
                ),
            )
            market_value += qty * float(price)
        else:
            market_value += position["market_value"] or 0.0
    equity = cash + market_value
    peak = db.meta_get("live.peak_equity", equity) or equity
    peak = max(float(peak), equity)
    db.meta_set("live.peak_equity", peak)
    db.execute(
        "INSERT OR REPLACE INTO live_equity(ts, cash, market_value, equity, n_positions, note)"
        " VALUES (?,?,?,?,?,?)",
        (
            now.replace(second=0, microsecond=0).isoformat(),
            round(cash, 2),
            round(market_value, 2),
            round(equity, 2),
            len(positions),
            f"drawdown={(equity / peak - 1):.4f}" if peak else "",
        ),
    )
    db.conn.commit()
    return {
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "equity": round(equity, 2),
        "drawdown": round(equity / peak - 1, 4) if peak else 0.0,
        "n_positions": len(positions),
    }


# ---------------------------------------------------------------------- plumbing
def notify(result: Mapping[str, Any], params: LiveParams) -> None:
    out_dir = ensure_dir(Path(DEFAULT_DB).parent.parent / "out")
    line = json.dumps(result, ensure_ascii=False, default=str)
    with open(out_dir / "live_alerts.jsonl", "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if result.get("alerts_new") or result.get("orders"):
        print(
            f"[live] {result['cycle_at']}  alerts={result['alerts_new']}"
            f" orders={len(result.get('orders') or [])} equity={result['book'].get('equity')}"
        )
        for alert in result.get("alerts") or []:
            print(f"   {alert.get('direction'):+d} {alert.get('ticker') or '-':6} {alert.get('headline')}")
    webhook = params.webhook or os.environ.get("MEDRADAR_WEBHOOK_URL")
    if webhook:
        try:
            request = urllib.request.Request(
                webhook,
                data=line.encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "medradar-live/0.1"},
                method="POST",
            )
            urllib.request.urlopen(request, timeout=10).read()
        except Exception as exc:
            print(f"[live] webhook failed: {exc}")


def reset(db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    """Wipe the simulated book (keeps the collected event history)."""
    with DB(db_path) as db:
        for table in ("positions", "paper_orders", "live_equity", "live_alerts"):
            db.execute(f"DELETE FROM {table}")
        db.conn.commit()
        for key in ("live.cash", "live.peak_equity", "live.last_cycle", "live.started_at"):
            db.execute("DELETE FROM meta WHERE key = ?", (key,))
        db.conn.commit()
    return {"status": "reset"}


# ------------------------------------------------------------------------ helpers
def _match_company(registry, text: str) -> tuple[str, str]:
    key, confidence, _alias = registry.resolve(text)
    if key and confidence >= 0.82:
        entry = registry.get(key) or {}
        return key, entry.get("ticker", "")
    return "", ""


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_rfc822(value: str) -> datetime | None:
    from email.utils import parsedate_to_datetime

    try:
        parsed = parsedate_to_datetime(value.strip())
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _days_held(opened_at: str | None, now: datetime) -> float:
    parsed = _parse_iso(opened_at or "")
    if not parsed:
        return 0.0
    return (now - parsed).total_seconds() / 86_400.0
