"""Command line entry point for SCIENCE-001.

    python research/science_001/cli.py fetch      # network: submissions + filings
    python research/science_001/cli.py verify     # offline: parse, grade, extract
    python research/science_001/cli.py build      # offline: dataset + labels
    python research/science_001/cli.py experiment # offline: baselines, permutation
    python research/science_001/cli.py figures    # offline: the two figures
    python research/science_001/cli.py all        # fetch -> figures in order

Every step is resumable: downloads are cached per URL, and each step writes its
own artifact so a later step can be re-run without touching the network.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Sequence

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.science_001 import dataset, edgar, features, sample  # noqa: E402
from research.science_001 import timesemantics as ts  # noqa: E402

ARTIFACTS = _HERE / "artifacts"
DATA = _HERE / "data"

EXTRACTED = DATA / "extracted.json"
FRAME_FULL = DATA / "frame_full.json"
FETCH_INDEX = DATA / "fetch_index.json"


def _ensure_dirs() -> None:
    for path in (ARTIFACTS, ARTIFACTS / "figures", DATA):
        path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    # newline="\n" is deliberate: .gitattributes normalises this repository to LF,
    # so a file hashed here must already be LF or the recorded SHA-256 would not
    # survive a fresh checkout.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8",
                    newline="\n")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _client(args: argparse.Namespace) -> edgar.EdgarClient:
    return edgar.EdgarClient(
        cache_dir=DATA / "cache",
        offline=args.offline,
        min_interval=args.min_interval,
        max_requests=args.max_requests,
    )


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def cmd_fetch(args: argparse.Namespace) -> int:
    _ensure_dirs()
    client = _client(args)
    print("[fetch] reading submissions indexes for %d issuers" % len(edgar.ISSUERS))
    frame = sample.build_frame(client, edgar.ISSUERS)
    print("[fetch] panel=%d  verification_pool=%d  excluded=%d  ledger=%s"
          % (len(frame["panel"]), len(frame["verification_pool"]),
             len(frame["excluded"]), frame["exclusion_ledger"]))
    verification_rows = sample.select_verification_sample(frame, per_stratum=args.per_stratum)
    print("[fetch] verification strata sample=%d" % len(verification_rows))
    rows = sample.fetch_set(frame, verification_rows)
    if args.limit:
        rows = rows[: args.limit]
    _write_json(FRAME_FULL, {
        "frame": {k: v for k, v in frame.items() if k != "excluded"},
        "verification_rows": verification_rows,
    })
    print("[fetch] downloading %d full submissions (.txt, cached)" % len(rows))

    index: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    issuer_by_key = {issuer.key: issuer for issuer in edgar.ISSUERS}
    for position, row in enumerate(rows, 1):
        issuer = issuer_by_key[row["issuer"]]
        try:
            response = client.full_submission(issuer, row["accession"], refresh=args.refresh)
            index.append({
                "issuer": row["issuer"], "accession": row["accession"],
                "url": response.url, "status": response.status,
                "bytes": len(response.body), "sha256": response.sha256,
                "last_modified": response.last_modified(),
                "fetched_at_utc": response.fetched_at_utc,
                "from_cache": response.from_cache,
            })
        except Exception as exc:  # noqa: BLE001 - one bad filing must not stop the run
            failures.append({"issuer": row["issuer"], "accession": row["accession"],
                             "error": "%s: %s" % (type(exc).__name__, exc)})
        if position % 50 == 0 or position == len(rows):
            print("   %d/%d  (requests=%d cache_hits=%d retries=%d errors=%d)"
                  % (position, len(rows), client.stats["requests"],
                     client.stats["cache_hits"], client.stats["retries"], client.stats["errors"]))
    _write_json(FETCH_INDEX, {"index": index, "failures": failures, "stats": client.stats})
    report = sample.sample_report(frame, verification_rows, index)
    report["fetch_failures"] = len(failures)
    report["network_stats"] = client.stats
    _write_json(ARTIFACTS / "sample_report.json", report)
    _write_json(ARTIFACTS / "issuer_identity.json", frame["identities"])
    _write_csv(ARTIFACTS / "panel_filings.csv", frame["panel"])
    _write_csv(ARTIFACTS / "verification_sample.csv", verification_rows)
    print("[fetch] done: %d filings cached, %d failures" % (len(index), len(failures)))
    return 0


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def cmd_verify(args: argparse.Namespace) -> int:
    _ensure_dirs()
    client = _client(args)
    if not FRAME_FULL.exists():
        print("[verify] missing %s - run fetch first" % FRAME_FULL)
        return 2
    payload = _read_json(FRAME_FULL)
    frame = payload["frame"]
    verification_rows = payload["verification_rows"]
    rows = sample.fetch_set(frame, verification_rows)
    issuer_by_key = {issuer.key: issuer for issuer in edgar.ISSUERS}

    extracted: dict[str, dict[str, Any]] = {}
    verification: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in rows:
        issuer = issuer_by_key[row["issuer"]]
        try:
            response = client.full_submission(issuer, row["accession"])
        except Exception as exc:  # noqa: BLE001
            failures.append({"accession": row["accession"], "error": repr(exc)})
            continue
        text = response.text()
        header = edgar.parse_header(text)
        grade = ts.grade_filing(header.present, header.acceptance_raw,
                                row["acceptance_api"], row["filing_date"])
        documents = edgar.parse_documents(text)
        prose = edgar.content_documents(documents)
        feature_row = features.extract_features(documents)

        acceptance_utc = None
        last_modified = ts.parse_http_date(response.last_modified())
        bounds: dict[str, Any] = {}
        if grade.get("acceptance_utc"):
            acceptance_utc = ts.parse_api_acceptance(grade["acceptance_utc"])
        if acceptance_utc is not None:
            bounds = ts.availability_bounds(acceptance_utc, last_modified,
                                            row["filing_date"]).as_dict()

        record = {
            "issuer": row["issuer"],
            "accession": row["accession"],
            "form": row["form"],
            "filing_date": row["filing_date"],
            "acceptance_utc": grade.get("acceptance_utc"),
            "acceptance_raw": header.acceptance_raw,
            "acceptance_source": header.header_format,
            "offset_hours": grade.get("offset_hours"),
            "local_time_status": grade.get("local_time_status"),
            "api_acceptance_utc": grade.get("api_acceptance_utc"),
            "residual_seconds": grade.get("residual_seconds"),
            "tier": grade["tier"],
            "tier_reason": grade.get("reason"),
            "header_present": header.present,
            "header_items": header.items,
            "conformed_type": header.conformed_type,
            "header_cik": header.cik,
            "header_company": header.company,
            "header_accession": header.accession,
            "header_matches_row": int(header.accession == row["accession"]),
            "n_raw_documents": len(documents),
            "n_content_documents": len(prose),
            "content_sha256": response.sha256,
            "content_bytes": len(response.body),
            "last_modified": response.last_modified(),
            "last_modified_utc": (last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")
                                  if last_modified else None),
            "collected_at_utc": response.fetched_at_utc,
            "collected_from_cache": response.from_cache,
            **feature_row,
            **bounds,
        }
        # Keep the first ~2000 characters of prose so a human reviewer can audit
        # the extractor without the archive (never the whole document).
        record["prose_head"] = (features.to_text(prose[0].text)[:400] if prose else "")
        extracted[row["accession"]] = record
        verification.append(record)

    _write_json(EXTRACTED, extracted)
    _write_csv(ARTIFACTS / "time_verification.csv", verification)
    summary = _verification_summary(verification, failures)
    _write_json(ARTIFACTS / "time_verification_summary.json", summary)
    print("[verify] parsed %d filings, %d failures" % (len(extracted), len(failures)))
    print("[verify] tiers: %s" % summary["tier_counts"])
    print("[verify] offset hours: %s" % summary["offset_counts"])
    print("[verify] residual seconds: %s" % summary["residual_counts"])
    return 0


def _verification_summary(verification: Sequence[dict[str, Any]],
                          failures: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def tally(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in verification:
            value = row.get(key)
            label = "None" if value is None else str(value)
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items()))

    residuals = [row["residual_seconds"] for row in verification
                 if row.get("residual_seconds") is not None]
    lags = [row["public_interval_seconds"] for row in verification
            if row.get("public_interval_seconds") is not None]
    bounded = sum(1 for row in verification if row.get("public_interval_bounded"))
    return {
        "n_filings": len(verification),
        "failures": len(failures),
        "tier_counts": tally("tier"),
        "offset_counts": tally("offset_hours"),
        "local_time_status_counts": tally("local_time_status"),
        "header_format_counts": tally("acceptance_source"),
        "header_match_rate": (sum(row["header_matches_row"] for row in verification)
                              / len(verification)) if verification else 0.0,
        "residual_counts": {str(k): v for k, v in tally("residual_seconds").items()},
        "residual_seconds_max_abs": max((abs(v) for v in residuals), default=None),
        "public_interval_bounded": bounded,
        "public_interval_bounded_share": (bounded / len(verification)) if verification else 0.0,
        "public_interval_seconds": _describe(lags),
        "after_hours_deferral": _after_hours_deferral(verification),
        "identity_agreement": _identity_agreement(verification),
        "tier_semantics": ts.TIERS,
    }


def _identity_agreement(verification: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Does the archived document agree with the index row that pointed at it?

    Required by the study design: accession, CIK, form type and filing date must
    be shown to describe the same filing on both sides, not assumed to.
    """
    import datetime as _dt
    total = len(verification)
    if not total:
        return {"n": 0}
    accession = sum(1 for r in verification if int(r.get("header_matches_row") or 0) == 1)
    form = sum(1 for r in verification
               if (r.get("conformed_type") or "").strip() == (r.get("form") or "").strip())
    displacement: dict[str, int] = {}
    same_day = 0
    after_cutoff = 0
    after_cutoff_displaced = 0
    for row in verification:
        stamp = row.get("acceptance_utc")
        offset = row.get("offset_hours")
        filing_date = row.get("filing_date")
        if not stamp or offset is None or not filing_date:
            continue
        try:
            utc = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
            eastern = utc + _dt.timedelta(hours=int(offset))
            filed = _dt.date.fromisoformat(filing_date)
        except ValueError:
            continue
        gap = (filed - eastern.date()).days
        displacement[str(gap)] = displacement.get(str(gap), 0) + 1
        if gap == 0:
            same_day += 1
        if eastern.hour * 60 + eastern.minute > 17 * 60 + 30:
            after_cutoff += 1
            if gap != 0:
                after_cutoff_displaced += 1
    return {
        "n": total,
        "accession_agreement": accession / total,
        "form_type_agreement": form / total,
        "filing_date_equals_eastern_acceptance_date": same_day / total,
        "filing_date_displacement_days": dict(sorted(displacement.items(), key=lambda kv: int(kv[0]))),
        "accepted_after_1730": after_cutoff,
        "accepted_after_1730_with_displaced_filing_date": after_cutoff_displaced,
    }


def _after_hours_deferral(verification: Sequence[dict[str, Any]],
                          cutoff_hour: int = 17, cutoff_minute: int = 30) -> dict[str, Any]:
    """Split the acceptance -> archival-write interval at the 17:30 ET cut-off.

    17 CFR 232.13(a)(2) and Filer Manual Vol. II p. 3-34 state that a filing
    received after 17:30 Eastern receives the next business day's filing date
    and is not disseminated until that day. The archival Last-Modified lets us
    *measure* that deferral instead of assuming it, which is exactly what a
    point-in-time study needs to know before treating acceptance as availability.
    """
    import datetime as _dt
    cutoff = cutoff_hour * 60 + cutoff_minute
    buckets: dict[str, list[int]] = {"before_cutoff": [], "after_cutoff": []}
    for row in verification:
        stamp = row.get("acceptance_utc")
        offset = row.get("offset_hours")
        lag = row.get("public_interval_seconds")
        if not stamp or offset is None or lag is None:
            continue
        try:
            utc = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
        eastern = utc + _dt.timedelta(hours=int(offset))
        key = ("after_cutoff" if eastern.hour * 60 + eastern.minute > cutoff
               else "before_cutoff")
        buckets[key].append(int(lag))
    summary: dict[str, Any] = {"cutoff": "17:30 US/Eastern", "cutoff_basis":
                               "17 CFR 232.13(a)(2); EDGAR Filer Manual Vol. II p. 3-34"}
    for key, values in buckets.items():
        summary[key] = _describe(sorted(values))
        summary[key]["over_one_hour"] = sum(1 for v in values if v > 3600)
        summary[key]["over_one_day"] = sum(1 for v in values if v > 86400)
    total = len(buckets["before_cutoff"]) + len(buckets["after_cutoff"])
    summary["after_cutoff_share"] = (len(buckets["after_cutoff"]) / total) if total else None
    return summary


def _describe(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    count = len(ordered)

    def quantile(q: float) -> float:
        index = min(count - 1, max(0, int(round(q * (count - 1)))))
        return float(ordered[index])

    return {
        "n": count,
        "min": float(ordered[0]),
        "p05": quantile(0.05),
        "median": quantile(0.5),
        "p95": quantile(0.95),
        "max": float(ordered[-1]),
        "mean": float(sum(ordered) / count),
    }


# --------------------------------------------------------------------------- #
# build / experiment / figures
# --------------------------------------------------------------------------- #
def cmd_build(args: argparse.Namespace) -> int:
    _ensure_dirs()
    if not EXTRACTED.exists() or not FRAME_FULL.exists():
        print("[build] missing extracted.json or frame_full.json - run fetch, verify first")
        return 2
    extracted = _read_json(EXTRACTED)
    frame = _read_json(FRAME_FULL)["frame"]
    panel_rows = frame["panel"]
    prose = {accession: record.get("prose_head", "") for accession, record in extracted.items()}
    # For amendment linking we need more than the head; re-read the cached text.
    client = _client(args)
    issuer_by_key = {issuer.key: issuer for issuer in edgar.ISSUERS}
    for row in panel_rows:
        if row["form"] != "8-K/A":
            continue
        try:
            response = client.full_submission(issuer_by_key[row["issuer"]], row["accession"])
            prose[row["accession"]] = response.text()
        except Exception:  # noqa: BLE001
            prose[row["accession"]] = ""
    links = dataset.link_amendments(panel_rows, prose)
    built = dataset.build_dataset(panel_rows, extracted,
                                  frame_end=dt_date(frame["frame_end"]))
    rows = built["rows"]
    for row in rows:
        link = links.get(row["accession"])
        row["amends_accession"] = link["amends_accession"] if link else None
    _write_csv(ARTIFACTS / "dataset.csv", rows)
    amendment_report = _amendment_summary(panel_rows, links)
    report = {
        "rows": len(rows),
        "dropped": built["drop_ledger"],
        "horizon_days": built["horizon_days"],
        "per_issuer": _counts(row["issuer"] for row in rows),
        "prevalence_tech_event": (sum(r["label_tech_event"] for r in rows) / len(rows))
        if rows else None,
        "prevalence_placebo": (sum(r["label_placebo"] for r in rows) / len(rows))
        if rows else None,
        "amendments": amendment_report,
    }
    _write_json(ARTIFACTS / "dataset_summary.json", report)
    print("[build] dataset rows=%d dropped=%s" % (len(rows), built["drop_ledger"]))
    print("[build] prevalence tech-event=%.3f placebo=%.3f"
          % (report["prevalence_tech_event"] or 0.0, report["prevalence_placebo"] or 0.0))
    print("[build] 8-K/A links: %s" % amendment_report["by_basis"])
    return 0


def _amendment_summary(panel_rows: Sequence[dict[str, Any]],
                       links: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Report the amendment graph honestly, by evidence strength.

    'resolved' means a *textual* reference pinned the original (accession quoted
    or a filing date named). Item-set proximity and bare fallbacks are counted
    separately and never presented as established links.
    """
    amendments = [row for row in panel_rows if row["form"] == "8-K/A"]
    by_basis: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    items_match = 0
    textual = 0
    for row in amendments:
        link = links.get(row["accession"]) or {}
        basis = link.get("basis", "unresolved")
        by_basis[basis] = by_basis.get(basis, 0) + 1
        confidence = link.get("confidence", "none")
        by_confidence[confidence] = by_confidence.get(confidence, 0) + 1
        if link.get("amends_accession"):
            if link.get("items_match"):
                items_match += 1
            if confidence in ("high", "medium"):
                textual += 1
    resolved = sum(1 for row in amendments
                   if (links.get(row["accession"]) or {}).get("amends_accession"))
    return {
        "n_amendments": len(amendments),
        "originals": sum(1 for row in panel_rows if row["form"] == "8-K"),
        "linked_to_a_preceding_8k": resolved,
        "linked_with_textual_evidence": textual,
        "textual_resolution_rate": (textual / len(amendments)) if amendments else None,
        "linked_and_item_sets_agree": items_match,
        "by_basis": dict(sorted(by_basis.items())),
        "by_confidence": dict(sorted(by_confidence.items())),
        "note": ("EDGAR does not publish an amendment-to-original key; the link is "
                 "reconstructed from the amendment's own text and SEC item codes. "
                 "Only by_confidence high/medium constitute evidence of the link."),
    }


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def dt_date(text: str):
    import datetime as _dt
    return _dt.date.fromisoformat(text)


def cmd_experiment(args: argparse.Namespace) -> int:
    _ensure_dirs()
    from research.science_001 import experiment
    return experiment.run(ARTIFACTS, seed=args.seed, permutations=args.permutations,
                          train_end=args.train_end)


def cmd_figures(args: argparse.Namespace) -> int:
    _ensure_dirs()
    from research.science_001 import figures
    return figures.run(ARTIFACTS)


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8", newline="\n")
        return
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    lines = [",".join(_csv_cell(c) for c in columns)]
    for row in rows:
        lines.append(",".join(_csv_cell(row.get(c)) for c in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if any(ch in text for ch in [',', '"', "\n", "\r"]):
        return '"' + text.replace('"', '""') + '"'
    return text


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="science_001", description=__doc__)
    parser.add_argument("command", choices=["fetch", "verify", "build", "experiment",
                                            "figures", "all"])
    parser.add_argument("--offline", action="store_true",
                        help="replay from cache only; never touch the network")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cache and refetch (use sparingly)")
    parser.add_argument("--limit", type=int, default=0, help="fetch at most N filings")
    parser.add_argument("--per-stratum", type=int, default=2,
                        help="filings selected per verification stratum")
    parser.add_argument("--min-interval", type=float, default=0.35,
                        help="minimum seconds between requests (SEC allows 10/s)")
    parser.add_argument("--max-requests", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--train-end", default="2024-12-31")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "all":
        for step in ("fetch", "verify", "build", "experiment", "figures"):
            args.command = step
            code = main_step(args, step)
            if code != 0:
                return code
        return 0
    return main_step(args, args.command)


def main_step(args: argparse.Namespace, step: str) -> int:
    handlers = {"fetch": cmd_fetch, "verify": cmd_verify, "build": cmd_build,
                "experiment": cmd_experiment, "figures": cmd_figures}
    try:
        return handlers[step](args)
    except Exception:  # noqa: BLE001 - a CLI must report, not vanish
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
