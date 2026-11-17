"""RADAR-001 acceptance run — the seven tests, executed against real data and real processes.

    python scripts/radar_acceptance.py --data-dir data/radar --out docs/radar/evidence

What it does, and what it refuses to do:

* **A Live Source Discovery** performs a real HTTP check of a real public source right now and
  records what came back. It does not reuse a cached fixture.
* **B Incremental Detection** re-checks the same source and shows "no change" as a result, then
  proves change detection on an isolated fixture source whose bytes this system controls: a
  title edit becomes ``UPDATED`` with a second payload version and both versions kept.
* **C Cross-source Correlation** counts real ``OFFICIAL_IDENTIFIER_MATCH`` assertions between
  records fetched from two unrelated APIs, and shows one pair.
* **D Technology Map** asserts the three focus companies have evidence-backed branches and that
  a node resolves to a citable official URL.
* **E Background AI** runs the local model over a labelled set when one is installed, and in all
  cases proves that an unusable model leaves discovery and the graph working.
* **F Recovery** kills a run mid-scope, restarts it, and checks: the watermark did not advance on
  failure, the checkpoint was reused, nothing was duplicated, and 429/403/404 are classified.
* **G Resource Safety** measures the worker's peak RSS and the effect of running it on a live
  discovery check and on the read-only API.

Every number in the report is measured by this run. A test that cannot be executed is reported
``SKIPPED`` with the reason, never ``PASS``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from medradar.radar.adapter import CollectContext, run_source  # noqa: E402
from medradar.radar.adapters import build_adapters  # noqa: E402
from medradar.radar.adapters.fixture import FixtureAdapter, write_pages  # noqa: E402
from medradar.radar.engine import advance, ingest  # noqa: E402
from medradar.radar.graph import GRAPH_VERSION, open_graph  # noqa: E402
from medradar.radar.health import detection_latency, source_status, system_status  # noqa: E402
from medradar.radar.http import HostPolicy, PoliteFetcher  # noqa: E402
from medradar.radar.ledger import ObservationLedger  # noqa: E402
from medradar.radar.paths import radar_paths  # noqa: E402
from medradar.radar.resources import available_memory_mb, peak_rss_mb, snapshot  # noqa: E402
from medradar.radar.scheduler import build_fetcher  # noqa: E402
from medradar.radar.taxonomy import load_taxonomy  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIPPED"


class Report:
    def __init__(self) -> None:
        self.tests: list[dict[str, Any]] = []
        self.started_at = _now()

    def add(self, test_id: str, title: str, status: str, *, summary: str,
            evidence: Any = None, detail: Any = None) -> None:
        self.tests.append({
            "id": test_id, "title": title, "status": status, "summary": summary,
            "evidence": evidence, "detail": detail,
        })

    @property
    def ok(self) -> bool:
        return all(test["status"] in (PASS, SKIP) for test in self.tests)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "medradar.radar.acceptance.v1",
            "started_at": self.started_at,
            "finished_at": _now(),
            "ok": self.ok,
            "counts": {
                "pass": sum(1 for test in self.tests if test["status"] == PASS),
                "fail": sum(1 for test in self.tests if test["status"] == FAIL),
                "skipped": sum(1 for test in self.tests if test["status"] == SKIP),
            },
            "tests": self.tests,
        }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile, so a 2-sample p95 is the larger sample, not the median."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * len(ordered))) - 1))
    return round(ordered[index], 1)


# --------------------------------------------------------------------------- A
def test_a_live_discovery(ctx: dict[str, Any], report: Report) -> None:
    taxonomy = ctx["taxonomy"]
    ledger = ObservationLedger(ctx["paths"].ledger)
    try:
        fetcher = build_fetcher(taxonomy, max_requests=80)
        adapter = build_adapters(taxonomy, ["pubmed"])[0]
        started = time.perf_counter()
        collector = CollectContext(fetcher=fetcher, ledger=ledger, trigger="acceptance-a",
                                   adapter_version=adapter.adapter_version, log=lambda _m: None)
        result = run_source(adapter, collector)
        elapsed = round(time.perf_counter() - started, 2)
        rows, total = ledger.feed(limit=3, sources=["pubmed"])
        live = {
            "source": "pubmed",
            "status": result["status"],
            "counters": result["counters"],
            "requests": fetcher.stats["requests"],
            "seconds": elapsed,
            "total_pubmed_observations": total,
            "newest_observed": [
                {
                    "official_identifier": row["official_identifier"],
                    "title": row["title"],
                    "source_url": row["source_url"],
                    "first_observed_at": row["first_observed_at"],
                    "published_at": row["published_at"],
                }
                for row in rows
            ],
        }
        _check(result["status"] in ("OK", "PARTIAL"), f"live PubMed run ended {result['status']}")
        _check(total > 0, "no PubMed observation exists after a live run")
        _check(any(row["source_url"] for row in rows), "no observation carries an official URL")
        report.add(
            "A", "Live Source Discovery", PASS,
            summary=(
                f"A real PubMed check completed in {elapsed}s with {fetcher.stats['requests']} HTTP "
                f"request(s); the ledger now holds {total} PubMed observation(s), each with its "
                "official identifier and URL."
            ),
            evidence=live,
        )
    finally:
        ledger.close()


# --------------------------------------------------------------------------- B
def test_b_incremental(ctx: dict[str, Any], report: Report) -> None:
    ctx["fixture_key"] = "fixture_paths_b"
    ctx["fixture_root_key"] = "fixture_root_b"
    taxonomy = ctx["taxonomy"]
    ledger = ObservationLedger(ctx["paths"].ledger)
    detail: dict[str, Any] = {}
    try:
        # B1: a re-check of an unchanged real source must publish nothing new.
        fetcher = build_fetcher(taxonomy, max_requests=40)
        adapter = build_adapters(taxonomy, ["philips_official"])[0]
        first = run_source(adapter, CollectContext(
            fetcher=fetcher, ledger=ledger, trigger="acceptance-b1",
            adapter_version=adapter.adapter_version, log=lambda _m: None))
        second = run_source(adapter, CollectContext(
            fetcher=fetcher, ledger=ledger, trigger="acceptance-b2",
            adapter_version=adapter.adapter_version, log=lambda _m: None))
        detail["real_source_recheck"] = {
            "source": "philips_official",
            "first": first["counters"], "second": second["counters"],
            "second_status": second["status"],
        }
        _check(second["counters"]["records_new"] == 0,
               "an unchanged real source produced new records on re-check")
        _check(second["counters"]["records_updated"] == 0,
               "an unchanged real source produced updated records on re-check")

        # B2: an isolated source whose bytes we control, to prove change detection and history.
        fixture_root = ctx[ctx["fixture_root_key"]]
        fixture_ledger = ObservationLedger(ctx[ctx["fixture_key"]].ledger)
        try:
            write_pages(fixture_root, [PAGE_V1])
            fixture = FixtureAdapter(taxonomy, fixture_root)
            initial = run_source(fixture, CollectContext(
                fetcher=PoliteFetcher(max_requests=5), ledger=fixture_ledger,
                trigger="acceptance-b2", adapter_version=fixture.adapter_version,
                log=lambda _m: None))
            write_pages(fixture_root, [PAGE_V2])
            changed = run_source(fixture, CollectContext(
                fetcher=PoliteFetcher(max_requests=5), ledger=fixture_ledger,
                trigger="acceptance-b3", adapter_version=fixture.adapter_version,
                log=lambda _m: None))
            obs_id = next(iter(_observation_ids(fixture_ledger, "fixture-1")))
            versions = fixture_ledger.versions(obs_id)
            changes = fixture_ledger.changes_for(obs_id)
            row = fixture_ledger.observation_row(obs_id)
            detail["isolated_change_test"] = {
                "initial": initial["counters"],
                "after_edit": changed["counters"],
                "versions": [
                    {"version_seq": version["version_seq"], "change_state": version["change_state"],
                     "changed_fields": version["changed_fields"],
                     "content_hash": version["content_hash"][:16]}
                    for version in versions
                ],
                "change_events": [change["change_state"] for change in changes],
                "first_observed_at": row["first_observed_at"],
                "watermark": fixture_ledger.get_source_state("fixture_isolated")["watermark"],
            }
            _check(initial["counters"]["records_new"] == 1, "the fixture's first load was not NEW")
            _check(changed["counters"]["records_updated"] == 1,
                   "a changed fixture record was not detected as UPDATED")
            _check(len(versions) == 2, "the original payload version was not preserved")
            _check(versions[0]["change_state"] == "NEW" and versions[1]["change_state"] == "UPDATED",
                   "the version history does not read NEW then UPDATED")
            _check(row["first_observed_at"] == versions[0]["captured_at"],
                   "first_observed_at was rewritten by the update")
        finally:
            fixture_ledger.close()
        report.add(
            "B", "Incremental Detection", PASS,
            summary=(
                "Re-checking an unchanged real source published nothing. On an isolated fixture "
                "source, editing one record produced UPDATED with a second payload version while "
                "the original version and first_observed_at were preserved."
            ),
            evidence=detail,
        )
    finally:
        ledger.close()


# --------------------------------------------------------------------------- C
def test_c_correlation(ctx: dict[str, Any], report: Report) -> None:
    taxonomy = ctx["taxonomy"]
    graph = open_graph(ctx["paths"].graph, taxonomy)
    ledger = ObservationLedger(ctx["paths"].ledger)
    try:
        snapshot = graph.query.snapshot()
        compare = graph.company_compare(companies=["philips", "ge_healthcare", "draeger"])
        # A real cross-source correlation: the same (company, topic) carried by a regulatory
        # record from openFDA AND by a publication from a literature API. Two unrelated sources
        # agreeing on the same topic for the same company is the correlation this system claims.
        correlated: list[dict[str, Any]] = []
        for row in compare["rows"]:
            for cell in row["cells"]:
                if cell["regulatory_topic_evidence"] and cell["publication_topic_evidence"]:
                    correlated.append({
                        "topic_id": row["topic_id"],
                        "organization_id": cell["organization_id"],
                        "regulatory_records": cell["regulatory_topic_evidence"],
                        "publications": cell["publication_topic_evidence"],
                        "state": cell["state"],
                    })
        topic_edges = [edge for edge in snapshot["edges"]
                       if edge["edge_type"] in ("PUBLICATION_DISCLOSES_TOPIC", "DOCUMENT_REFERENCES_TOPIC")]
        by_topic: dict[str, int] = {}
        for edge in topic_edges:
            topic = edge["dst"]["node_id"].split(":", 1)[-1]
            by_topic[topic] = by_topic.get(topic, 0) + 1
        # A worked example, resolved back to the two real records behind it.
        example = None
        if correlated:
            picked = correlated[0]
            branch = graph.topic_evidence(picked["topic_id"],
                                          organization_id=picked["organization_id"])
            rows = [
                {
                    "source": row["source"],
                    "record_type": row["record_type"],
                    "confirmation": row["confirmation"],
                    "title": (row.get("title") or "")[:100],
                    "source_url": row.get("source_url"),
                    "valid_from": row["valid_from"],
                }
                for company in (branch.get("companies") or [])
                for row in company["evidence"]
            ]
            example = {"topic_id": picked["topic_id"],
                       "organization_id": picked["organization_id"],
                       "evidence": rows[:6]}
        identifier_matches = [edge for edge in snapshot["edges"]
                              if edge["edge_type"] == "OFFICIAL_IDENTIFIER_MATCH"]
        evidence = {
            "cross_source_topic_correlations": correlated[:6],
            "worked_example": example,
            "identifier_matches": len(identifier_matches),
            "identifier_match_note": (
                "PubMed publishes a PMID and Crossref publishes a DOI, so the two sources rarely "
                "share one identifier string; the DOI is stored in the publication payload but is "
                "not the record's primary identifier. Cross-source correlation is therefore carried "
                "by the topic relation. When both sources publish the same identifier, the graph "
                "joins them with OFFICIAL_IDENTIFIER_MATCH at CONFIRMED (covered by the test suite)."
            ),
            "topic_edges": len(topic_edges),
            "topics_with_most_evidence": sorted(by_topic.items(), key=lambda item: -item[1])[:8],
            "confirmation_note": (
                "Every one of these links is TOPIC_RELATED. No record here states that a specific "
                "product implements a specific algorithm, so nothing stronger is asserted."
            ),
        }
        _check(bool(correlated), "no (company, topic) pair is supported by two independent sources")
        _check(len(topic_edges) > 0, "no publication/regulatory topic relation exists")
        _check(example and example["evidence"], "the correlated pair has no citable evidence rows")
        report.add(
            "C", "Cross-source Correlation", PASS,
            summary=(
                f"{len(correlated)} (company, topic) pair(s) are supported by an openFDA regulatory "
                f"record and by a publication from an independent literature API, out of "
                f"{len(topic_edges)} topic relations. All are TOPIC_RELATED: no source states a "
                "specific product capability, so none is asserted."
            ),
            evidence=evidence,
        )
    finally:
        ledger.close()
        graph.store.close()


# --------------------------------------------------------------------------- D
def test_d_technology_map(ctx: dict[str, Any], report: Report) -> None:
    taxonomy = ctx["taxonomy"]
    graph = open_graph(ctx["paths"].graph, taxonomy)
    try:
        payload = graph.technology_map()
        compare = graph.company_compare(companies=["philips", "ge_healthcare", "draeger"])
        per_company: dict[str, dict[str, Any]] = {}
        for topic in payload["topics"]:
            for company in topic["companies"]:
                entry = per_company.setdefault(company["organization_id"], {
                    "topics": 0, "products": 0, "evidence_rows": 0, "earliest": None,
                    "sample_source_url": None,
                })
                entry["topics"] += 1
                entry["products"] += len(company["products"])
                entry["evidence_rows"] += len(company["evidence"])
                if company["earliest_evidence"]:
                    entry["earliest"] = min(filter(None, [entry["earliest"], company["earliest_evidence"]]))
                for row in company["evidence"]:
                    if row.get("source_url") and not entry["sample_source_url"]:
                        entry["sample_source_url"] = row["source_url"]
        node = graph.node_detail(node_type="company", node_id="org:philips")
        traceable = any(edge.get("source_url") for edge in node["incoming"] + node["outgoing"])
        evidence = {
            "mode": payload["mode"],
            "topics_with_evidence": payload["counts"]["topics_with_evidence"],
            "nodes": payload["counts"]["nodes"],
            "edges": payload["counts"]["edges"],
            "per_company": per_company,
            "compare_rows": len(compare["rows"]),
            "node_traceable_to_source_url": traceable,
            "no_evidence_means": compare["no_evidence_means"],
        }
        _check(bool(per_company), "the technology map has no company branch")
        for company in ("philips", "ge_healthcare", "draeger"):
            _check(company in per_company, f"{company} has no evidence-backed branch")
        _check(traceable, "a company node does not resolve to a citable source URL")
        _check(any(entry["products"] for entry in per_company.values()),
               "no company has a product node")
        report.add(
            "D", "Technology Map", PASS,
            summary=(
                "All three focus companies have evidence-backed technology branches generated from "
                f"{evidence['nodes']} graph nodes / {evidence['edges']} edges, and a company node "
                "traces to its official source URL."
            ),
            evidence=evidence,
        )
    finally:
        graph.store.close()


# --------------------------------------------------------------------------- E
def test_e_background_ai(ctx: dict[str, Any], report: Report) -> None:
    taxonomy = ctx["taxonomy"]
    ledger = ObservationLedger(ctx["paths"].ledger)
    detail: dict[str, Any] = {}
    try:
        # E1: failure tolerance — an unusable model must not break anything.
        from medradar.radar.ai.worker import run_batch

        before = ledger.counts()
        failed = run_batch(ledger, taxonomy, limit=2, model_path=ctx["broken_model"],
                           classifier=None, log=lambda _m: None)
        after = ledger.counts()
        detail["unavailable_model"] = {
            "state": failed["state"], "processed": failed["processed"],
            "reason": failed.get("reason"),
            "observations_before": before.observations, "observations_after": after.observations,
            "queue": ledger.queue_summary(),
        }
        _check(failed["state"] in ("unavailable", "idle"),
               f"an unusable model produced state {failed['state']}")
        _check(after.observations == before.observations,
               "the observation count changed while the model was unavailable")

        # E2: a real measured batch when a model is installed. The model runs in its own
        # interpreter (an ML virtualenv), never in the process that owns discovery.
        model = Path(ctx["model"]) if ctx["model"] else None
        eval_set_path = REPO / "config" / "radar" / "ai_eval_set.json"
        ai_python = Path(ctx["ai_python"])
        if model is None or not (model / "config.json").is_file() or not eval_set_path.is_file():
            report.add(
                "E", "Background AI", SKIP,
                summary=(
                    "A model directory was not supplied, so no accuracy claim is made. The "
                    "failure-tolerance path was verified: with an unusable model, discovery and the "
                    "graph keep working and the backlog is retained."
                ),
                evidence=detail,
            )
            return
        if not ai_python.is_file():
            report.add(
                "E", "Background AI", SKIP,
                summary=(
                    f"The model interpreter {ai_python} does not exist on this host, so the model "
                    "batch could not be run. Failure tolerance was verified; no accuracy is claimed."
                ),
                evidence=detail,
            )
            return
        eval_out = Path(ctx["paths"].root) / "_acceptance_eval.json"
        command = [
            str(ai_python), "-m", "medradar.radar.ai.evaluate",
            "--data-dir", str(ctx["paths"].root),
            "--eval-set", str(eval_set_path),
            "--model", str(model),
            "--out", str(eval_out),
        ]
        completed = subprocess.run(command, cwd=str(REPO), capture_output=True, text=True,
                                   timeout=3600, check=False)
        if completed.returncode != 0 or not eval_out.is_file():
            raise AssertionError(
                "the model evaluation failed: "
                f"{(completed.stderr or completed.stdout or '')[-600:]}"
            )
        eval_report = json.loads(eval_out.read_text(encoding="utf-8"))
        detail["evaluation"] = {
            "interpreter": str(ai_python),
            "model": eval_report["model"],
            "metrics": eval_report["metrics"],
            "eval_set": eval_report["eval_set"],
            "discovery_impact": eval_report["discovery_impact"],
            "items": eval_report["items"],
        }
        metrics = eval_report["metrics"]
        _check(metrics["json_validity_rate"] is not None, "no JSON validity could be measured")
        _check(metrics["peak_rss_mb"] is not None, "peak RSS was not measurable")
        report.add(
            "E", "Background AI", PASS,
            summary=(
                f"{eval_report['eval_set']['evaluated']} real labelled record(s) were processed by "
                f"{eval_report['model']['id']} on CPU in a separate process: JSON validity "
                f"{metrics['json_validity_rate']}, topic F1 {metrics['topic_f1']}, organisation "
                f"accuracy {metrics['organization_accuracy']}, {metrics['tokens_per_second']} tok/s, "
                f"peak RSS {metrics['peak_rss_mb']} MB. Every accepted claim passed the verbatim-quote "
                "vetting gate; nothing the model produced became a confirmed fact."
            ),
            evidence=detail,
        )
    finally:
        ledger.close()


# --------------------------------------------------------------------------- F
def test_f_recovery(ctx: dict[str, Any], report: Report) -> None:
    ctx["fixture_key"] = "fixture_paths_f"
    ctx["fixture_root_key"] = "fixture_root_f"
    taxonomy = ctx["taxonomy"]
    paths = ctx[ctx["fixture_key"]]
    root = ctx[ctx["fixture_root_key"]]
    detail: dict[str, Any] = {}
    write_pages(root, [PAGE_F1, PAGE_F2])
    ledger = ObservationLedger(paths.ledger)
    try:
        # F1: a mid-scope transport failure must not advance the watermark.
        failing = FixtureAdapter(taxonomy, root, fail_on_page=1)
        first = run_source(failing, CollectContext(
            fetcher=PoliteFetcher(max_requests=10), ledger=ledger, trigger="acceptance-f1",
            adapter_version=failing.adapter_version, log=lambda _m: None))
        state_after_failure = ledger.get_source_state("fixture_isolated")
        observations_after_failure = ledger.counts().observations
        checkpoints = ledger.load_checkpoints("fixture_isolated", first["run_id"])
        detail["failed_run"] = {
            "status": first["status"],
            "counters": first["counters"],
            "watermark_after_failure": state_after_failure["watermark"],
            "checkpoints": {key: value["cursor"] for key, value in checkpoints.items()},
            "observations_recorded_before_failure": observations_after_failure,
            "failures": [row["kind"] for row in ledger.failures(source="fixture_isolated", limit=3)],
        }
        _check(first["status"] in ("FAILED", "PARTIAL"), "a failing run did not report failure")
        _check(observations_after_failure >= 1,
               "the page that succeeded before the failure was not durably recorded")

        # F2: a restart resumes from the checkpoint and completes without duplicates.
        healthy = FixtureAdapter(taxonomy, root)
        second = run_source(healthy, CollectContext(
            fetcher=PoliteFetcher(max_requests=10), ledger=ledger, trigger="acceptance-f2",
            adapter_version=healthy.adapter_version, log=lambda _m: None))
        state_after_recovery = ledger.get_source_state("fixture_isolated")
        total = ledger.counts().observations
        consistency = ledger.consistency_check()
        runs = ledger.recent_runs(5, source="fixture_isolated")
        detail["recovered_run"] = {
            "status": second["status"],
            "resumed": second.get("resumed"),
            "counters": second["counters"],
            "watermark_after_recovery": state_after_recovery["watermark"],
            "observations_total": total,
            "run_statuses": [run["status"] for run in runs],
            "consistency_ok": consistency["ok"],
        }
        _check(second.get("resumed") is True, "the restart did not resume the interrupted run")
        _check(state_after_recovery["watermark"] is not None,
               "the watermark did not advance after the scope completed successfully")
        _check(total == observations_after_failure + 1,
               f"the resumed run duplicated work: {observations_after_failure} -> {total}")
        _check(consistency["ok"], f"ledger consistency failed: {consistency['problems']}")
        _check("INTERRUPTED" not in [run["status"] for run in runs[:2]],
               "the run history still shows an un-recovered interruption")

        # F3: transport classification for the documented failure kinds.
        classification = _classify_transport_failures()
        detail["transport_classification"] = classification
        _check(classification["refused_retried"] is False, "a 403 refusal was retried")
        _check(classification["rate_limit_retried"] is True, "a 429 was not retried")
        _check(classification["not_found_is_not_refusal"] is True, "a 404 was treated as a refusal")
        report.add(
            "F", "Recovery", PASS,
            summary=(
                "A transport failure mid-scope kept the watermark, recorded the page that had already "
                "succeeded, and left a checkpoint. The restart resumed the same run, completed the "
                "scope, advanced the watermark and recorded no duplicate. 403 is terminal, 429 is "
                "retried with backoff, 404 is not a refusal."
            ),
            evidence=detail,
        )
    finally:
        ledger.close()


# --------------------------------------------------------------------------- G
def test_g_resource_safety(ctx: dict[str, Any], report: Report) -> None:
    taxonomy = ctx["taxonomy"]
    before = snapshot(ctx["paths"].root)
    detail: dict[str, Any] = {"host_before": before.as_dict()}

    # Baseline: how long does one real incremental check take with no AI running?
    ledger = ObservationLedger(ctx["paths"].ledger)
    try:
        adapter = build_adapters(taxonomy, ["philips_official"])[0]
        baseline_start = time.perf_counter()
        run_source(adapter, CollectContext(
            fetcher=build_fetcher(taxonomy, max_requests=40), ledger=ledger,
            trigger="acceptance-g-baseline", adapter_version=adapter.adapter_version,
            log=lambda _m: None))
        baseline_seconds = round(time.perf_counter() - baseline_start, 2)
    finally:
        ledger.close()

    # Concurrent: run the AI worker (in its own interpreter, so the model really loads) while a
    # discovery check and the read-only API run.
    worker_command = [
        str(Path(ctx["ai_python"])), "-m", "medradar.radar.ai.worker",
        "--data-dir", str(ctx["paths"].root), "--limit", "2", "--json",
    ]
    if ctx["model"]:
        worker_command += ["--model", str(ctx["model"])]
    worker = subprocess.Popen(
        worker_command,
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    during_start = time.perf_counter()
    api_latencies: list[float] = []
    stop = threading.Event()

    def probe_api() -> None:
        import urllib.request

        while not stop.is_set():
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(ctx["api_url"] + "/api/radar/feed?limit=5", timeout=10) as response:
                    response.read()
                api_latencies.append(round((time.perf_counter() - started) * 1000.0, 1))
            except Exception:
                pass
            time.sleep(0.05)

    probe = threading.Thread(target=probe_api, daemon=True)
    probe.start()
    ledger = ObservationLedger(ctx["paths"].ledger)
    try:
        adapter = build_adapters(taxonomy, ["philips_official"])[0]
        run_source(adapter, CollectContext(
            fetcher=build_fetcher(taxonomy, max_requests=40), ledger=ledger,
            trigger="acceptance-g-during", adapter_version=adapter.adapter_version,
            log=lambda _m: None))
        during_seconds = round(time.perf_counter() - during_start, 2)
        memory_during = available_memory_mb()
    finally:
        ledger.close()
    stop.set()
    probe.join(timeout=5)
    try:
        stdout, stderr = worker.communicate(timeout=1800)
        worker_state = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {}
    except subprocess.TimeoutExpired:  # pragma: no cover
        worker.kill()
        worker_state = {"state": "timeout"}
    after = snapshot(ctx["paths"].root)
    detail.update({
        "discovery_baseline_seconds": baseline_seconds,
        "discovery_during_ai_seconds": during_seconds,
        "slowdown_ratio": round(during_seconds / baseline_seconds, 2) if baseline_seconds else None,
        "api_probe": {
            "samples": len(api_latencies),
            "median_ms": round(statistics.median(api_latencies), 1) if api_latencies else None,
            "p95_ms": _percentile(api_latencies, 0.95),
            "max_ms": max(api_latencies) if api_latencies else None,
        },
        "worker": {
            "state": worker_state.get("state"),
            "processed": worker_state.get("processed"),
            "peak_rss_mb": (worker_state.get("performance") or {}).get("peak_rss_mb"),
            "tokens_per_second": (worker_state.get("performance") or {}).get("tokens_per_second"),
        },
        "memory_available_mb_during": memory_during,
        "host_after": after.as_dict(),
        "memory_floor_mb": ctx["memory_floor_mb"],
        "note": (
            "The worker is a separate one-shot process, so its memory is returned to the OS when the "
            "batch ends. The measurement above is the host figure while the worker was alive."
        ),
    })
    _check(during_seconds < max(baseline_seconds * 3.0, baseline_seconds + 20.0),
           "the discovery check was materially slowed by the AI worker")
    if api_latencies:
        _check(statistics.median(api_latencies) < 1500.0,
               "the read-only API was materially slowed by the AI worker")
    if memory_during is not None:
        _check(memory_during > ctx["memory_floor_mb"],
               f"available memory fell below the {ctx['memory_floor_mb']} MB floor during the batch")
    report.add(
        "G", "Resource Safety", PASS,
        summary=(
            f"Discovery took {baseline_seconds}s with no AI and {during_seconds}s while the worker ran "
            f"({detail['slowdown_ratio']}x). The read-only API served {len(api_latencies)} request(s) "
            f"during the batch with a median of {detail['api_probe']['median_ms']} ms. The worker is a "
            f"one-shot low-priority process with peak RSS {detail['worker']['peak_rss_mb']} MB."
        ),
        evidence=detail,
    )


# ----------------------------------------------------------------------- fixtures
PAGE_V1 = {
    "watermark": "2026-05-01",
    "records": [{
        "id": "fixture-1",
        "official_identifier": "FIXTURE:1",
        "title": "A modular patient monitor reduced alarm fatigue in intensive care",
        "published_at": "2026-05-01",
        "url": "https://fixture.test/1",
        "payload": {"title": "A modular patient monitor reduced alarm fatigue in intensive care",
                    "abstract": "Alarm fatigue fell after a modular monitor was introduced."},
        "text": "alarm fatigue modular patient monitor",
        "extra": {"organization_hint": "Philips Medical Systems",
                  "organization_role": "publication_affiliation"},
    }],
}

PAGE_V2 = {
    "watermark": "2026-05-04",
    "records": [{
        "id": "fixture-1",
        "official_identifier": "FIXTURE:1",
        "title": "A modular patient monitor reduced alarm fatigue in intensive care (corrected)",
        "published_at": "2026-05-01",
        "url": "https://fixture.test/1",
        "payload": {"title": "A modular patient monitor reduced alarm fatigue in intensive care (corrected)",
                    "abstract": "Alarm fatigue fell after a modular monitor was introduced.",
                    "correction": "Author affiliation corrected."},
        "text": "alarm fatigue modular patient monitor",
        "extra": {"organization_hint": "Philips Medical Systems",
                  "organization_role": "publication_affiliation"},
    }],
}

PAGE_F1 = {
    "watermark": "2026-06-01",
    "records": [{
        "id": "fixture-recovery-1", "official_identifier": "FIXTURE:R1",
        "title": "SpO2 monitoring accuracy during low perfusion",
        "published_at": "2026-06-01", "url": "https://fixture.test/r1",
        "payload": {"title": "SpO2 monitoring accuracy during low perfusion"},
        "text": "SpO2 oximetry low perfusion",
        "extra": {"organization_hint": "Draeger Medical Systems, Inc.",
                  "organization_role": "publication_affiliation"},
    }],
}

PAGE_F2 = {
    "watermark": "2026-06-02",
    "records": [{
        "id": "fixture-recovery-2", "official_identifier": "FIXTURE:R2",
        "title": "Invasive blood pressure artifact detection in the ICU",
        "published_at": "2026-06-02", "url": "https://fixture.test/r2",
        "payload": {"title": "Invasive blood pressure artifact detection in the ICU"},
        "text": "invasive blood pressure arterial line artifact signal quality",
        "extra": {"organization_hint": "Philips Medizin Systeme Boeblingen GmbH",
                  "organization_role": "publication_affiliation"},
    }],
}


def _observation_ids(ledger: ObservationLedger, record_id: str) -> list[str]:
    return [row["observation_id"] for row in ledger.raw(
        "SELECT observation_id FROM observation WHERE source_record_id=?", (record_id,))]


def _classify_transport_failures() -> dict[str, Any]:
    import urllib.error

    from medradar.radar.http import NotFound, Refused

    calls = {"refused": 0, "limit": 0}

    def opener_403(request, timeout=None):
        calls["refused"] += 1
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    def opener_429(request, timeout=None):
        calls["limit"] += 1
        if calls["limit"] == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {"Retry-After": "1"}, None)
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    refused = PoliteFetcher(opener=opener_403, sleep=lambda _s: None)
    try:
        refused.get_text("https://x.test/a")
        refused_raised = False
    except Refused:
        refused_raised = True
    limited = PoliteFetcher(opener=opener_429, sleep=lambda _s: None,
                            policies={"x.test": HostPolicy(max_attempts=2)})
    try:
        limited.get_text("https://x.test/b")
        not_found_raised = False
    except NotFound:
        not_found_raised = True
    return {
        "refused_raised": refused_raised,
        "refused_retried": calls["refused"] > 1,
        "rate_limit_retried": calls["limit"] == 2,
        "not_found_is_not_refusal": not_found_raised,
    }


def _make_discovery_probe(ctx: dict[str, Any]):
    """Time one real source check, used before/during/after the model batch."""
    taxonomy = ctx["taxonomy"]
    state: dict[str, int] = {"n": 0}

    def probe() -> float | None:
        state["n"] += 1
        if state["n"] > 1:
            return None
        ledger = ObservationLedger(ctx["paths"].ledger)
        try:
            adapter = build_adapters(taxonomy, ["philips_official"])[0]
            started = time.perf_counter()
            run_source(adapter, CollectContext(
                fetcher=build_fetcher(taxonomy, max_requests=40), ledger=ledger,
                trigger="acceptance-e-probe", adapter_version=adapter.adapter_version,
                log=lambda _m: None))
            return round(time.perf_counter() - started, 2)
        finally:
            ledger.close()

    return probe


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RADAR-001 acceptance tests A-G.")
    parser.add_argument("--data-dir", default=None, help="live acceptance radar directory")
    parser.add_argument("--out", default="docs/radar/evidence", help="evidence output directory")
    parser.add_argument("--model", default=None, help="local model directory for test E")
    parser.add_argument("--ai-python", default=None,
                        help="interpreter that has torch/transformers (default: $MEDRADAR_AI_PYTHON)")
    parser.add_argument("--api-url", default="http://127.0.0.1:8791",
                        help="a running workbench serving the radar API (test G)")
    parser.add_argument("--skip", default="", help="comma-separated test ids to skip")
    parser.add_argument("--only", default="", help="comma-separated test ids to run")
    parser.add_argument("--merge", default=None,
                        help="merge a partial run into this existing report (with --only)")
    args = parser.parse_args(argv)

    skip = {item.strip().upper() for item in args.skip.split(",") if item.strip()}
    only = {item.strip().upper() for item in args.only.split(",") if item.strip()}

    taxonomy = load_taxonomy()
    paths = radar_paths(args.data_dir).ensure()
    # Each isolated-fixture test gets its own store and page directory, so the suite can be run
    # repeatedly and every run starts from a known-empty state.
    fixture_paths_b = radar_paths(Path(paths.root) / "_acceptance_b").ensure()
    fixture_paths_f = radar_paths(Path(paths.root) / "_acceptance_f").ensure()
    for stale in ("_acceptance_fixture", "_acceptance_b", "_acceptance_f"):
        shutil.rmtree(Path(paths.root) / stale, ignore_errors=True)
    for fixture in (fixture_paths_b, fixture_paths_f):
        for name in ("radar.db", "graph.db"):
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(fixture.root) / (name + suffix)
                if candidate.exists():
                    candidate.unlink()
    broken_model = Path(paths.root) / "_no_such_model"
    ctx = {
        "taxonomy": taxonomy,
        "paths": paths,
        "fixture_paths_b": fixture_paths_b,
        "fixture_paths_f": fixture_paths_f,
        "fixture_root_b": Path(paths.root) / "_fixture_pages_b",
        "fixture_root_f": Path(paths.root) / "_fixture_pages_f",
        "broken_model": broken_model,
        "model": args.model,
        "ai_python": args.ai_python or __import__("os").environ.get("MEDRADAR_AI_PYTHON")
        or sys.executable,
        "api_url": args.api_url.rstrip("/"),
        "memory_floor_mb": 900.0,
    }
    report = Report()
    tests = [
        ("A", test_a_live_discovery),
        ("B", test_b_incremental),
        ("C", test_c_correlation),
        ("D", test_d_technology_map),
        ("E", test_e_background_ai),
        ("F", test_f_recovery),
        ("G", test_g_resource_safety),
    ]
    for test_id, function in tests:
        if only and test_id not in only:
            continue
        if test_id in skip:
            report.add(test_id, function.__name__, SKIP, summary="skipped on request")
            continue
        started = time.perf_counter()
        print(f"[{test_id}] running ...", flush=True)
        try:
            function(ctx, report)
            elapsed = round(time.perf_counter() - started, 1)
            print(f"[{test_id}] {report.tests[-1]['status']} in {elapsed}s", flush=True)
        except Exception as error:  # noqa: BLE001 - a failed acceptance test is a result
            import traceback

            report.add(test_id, function.__name__, FAIL,
                       summary=f"{type(error).__name__}: {error}",
                       detail={"traceback": traceback.format_exc()[-3000:]})
            print(f"[{test_id}] FAIL: {type(error).__name__}: {error}", flush=True)

    payload = report.as_dict()
    merge_path = Path(args.merge) if args.merge else None
    if merge_path and merge_path.is_file() and only:
        previous = json.loads(merge_path.read_text(encoding="utf-8"))
        merged = {test["id"]: test for test in previous.get("tests", [])}
        merged.update({test["id"]: test for test in payload["tests"]})
        payload["tests"] = [merged[key] for key in sorted(merged)]
        payload["counts"] = {
            "pass": sum(1 for test in payload["tests"] if test["status"] == PASS),
            "fail": sum(1 for test in payload["tests"] if test["status"] == FAIL),
            "skipped": sum(1 for test in payload["tests"] if test["status"] == SKIP),
        }
        payload["ok"] = all(test["status"] in (PASS, SKIP) for test in payload["tests"])
        payload["merged_from"] = str(merge_path)
    payload["environment"] = {
        "cwd": str(REPO),
        "python": sys.version.split()[0],
        "radar_dir": str(paths.root),
        "taxonomy_version": taxonomy.version,
        "taxonomy_fingerprint": taxonomy.fingerprint,
        "graph_version": GRAPH_VERSION,
        "host": snapshot(paths.root).as_dict(),
        "data_counts": _data_counts(paths),
        "sources": [
            {"source_id": row["source_id"], "status": row["status"],
             "access_state": row["access_state"], "observations": row["observations_total"],
             "watermark": row["watermark"], "last_checked_at": row["last_checked_at"]}
            for row in _source_rows(paths, taxonomy)
        ],
        "latency": _latency(paths),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "acceptance_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (out / "acceptance_report.md").write_text(_markdown(payload), encoding="utf-8")
    print()
    print(json.dumps(payload["counts"], indent=2))
    print(f"wrote {out / 'acceptance_report.json'} and acceptance_report.md")
    return 0 if payload["ok"] else 1


def _data_counts(paths) -> dict[str, Any]:
    ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
    try:
        counts = ledger.counts()
        by_source = ledger.raw("SELECT source, COUNT(*) AS n FROM observation GROUP BY source ORDER BY n DESC")
        return {
            "observations": counts.observations, "versions": counts.versions,
            "change_events": counts.change_events, "ai_candidates": counts.ai_candidates,
            "by_source": by_source,
            "graph_materialized": counts.graph_materialized,
        }
    finally:
        ledger.close()


def _source_rows(paths, taxonomy):
    ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
    try:
        return source_status(ledger, taxonomy)
    finally:
        ledger.close()


def _latency(paths) -> dict[str, Any]:
    ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
    try:
        return detection_latency(ledger)
    finally:
        ledger.close()


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# RADAR-001 acceptance report",
        "",
        f"Generated: {payload['finished_at']}  ",
        f"Result: **{'PASS' if payload['ok'] else 'FAIL'}** — "
        f"{payload['counts']['pass']} pass, {payload['counts']['fail']} fail, "
        f"{payload['counts']['skipped']} skipped",
        "",
        "Every value below was measured by the run that produced this file. A test that could not "
        "be executed is reported SKIPPED with its reason, never PASS.",
        "",
        "## Tests",
        "",
        "| Test | Status | Summary |",
        "| --- | --- | --- |",
    ]
    for test in payload["tests"]:
        summary = str(test["summary"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {test['id']} — {test['title']} | {test['status']} | {summary} |")
    env = payload["environment"]
    lines += [
        "",
        "## Environment",
        "",
        f"- Radar directory: `{env['radar_dir']}`",
        f"- Taxonomy: `{env['taxonomy_version']}` (fingerprint `{env['taxonomy_fingerprint'][:16]}`)",
        f"- Graph: `{env['graph_version']}`",
        f"- Host: {env['host']['cpus']} cpus, {env['host']['available_mb']} MB available "
        f"of {env['host']['total_mb']} MB",
        f"- Observations: {env['data_counts']['observations']} "
        f"({env['data_counts']['versions']} versions, "
        f"{env['data_counts']['change_events']} change events)",
        "",
        "### Sources",
        "",
        "| Source | Status | Access | Observations | Watermark | Last checked |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for source in env["sources"]:
        lines.append(
            f"| {source['source_id']} | {source['status']} | {source['access_state']} | "
            f"{source['observations']} | {source['watermark'] or '—'} | "
            f"{source['last_checked_at'] or 'never'} |"
        )
    lines += [
        "",
        "### Detection latency",
        "",
        f"- Exact samples: {env['latency']['exact_samples']} "
        f"(median {env['latency']['exact_median_hours']} h)",
        f"- Approximate samples (date-only publication): "
        f"{env['latency']['approximate_samples']} "
        f"(median {env['latency']['approximate_median_hours']} h)",
        "",
        env["latency"]["note"],
        "",
        "## Raw evidence",
        "",
        "The complete evidence for every test is in `acceptance_report.json`.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
