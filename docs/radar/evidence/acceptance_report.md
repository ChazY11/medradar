# RADAR-001 acceptance report

Generated: 2026-11-16T23:19:59Z  
Result: **PASS** — 7 pass, 0 fail, 0 skipped

Every value below was measured by the run that produced this file. A test that could not be executed is reported SKIPPED with its reason, never PASS.

## Tests

| Test | Status | Summary |
| --- | --- | --- |
| A — Live Source Discovery | PASS | A real PubMed check completed in 8.05s with 15 HTTP request(s); the ledger now holds 484 PubMed observation(s), each with its official identifier and URL. |
| B — Incremental Detection | PASS | Re-checking an unchanged real source published nothing. On an isolated fixture source, editing one record produced UPDATED with a second payload version while the original version and first_observed_at were preserved. |
| C — Cross-source Correlation | PASS | 6 (company, topic) pair(s) are supported by an openFDA regulatory record and by a publication from an independent literature API, out of 10285 topic relations. All are TOPIC_RELATED: no source states a specific product capability, so none is asserted. |
| D — Technology Map | PASS | All three focus companies have evidence-backed technology branches generated from 23619 graph nodes / 18184 edges, and a company node traces to its official source URL. |
| E — Background AI | PASS | 11 real labelled record(s) were processed by Qwen3-0.6B on CPU in a separate process: JSON validity 1.0, topic F1 0.1818, organisation accuracy 0.7273, 9.57 tok/s, peak RSS 3169.1 MB. Every accepted claim passed the verbatim-quote vetting gate; nothing the model produced became a confirmed fact. |
| F — Recovery | PASS | A transport failure mid-scope kept the watermark, recorded the page that had already succeeded, and left a checkpoint. The restart resumed the same run, completed the scope, advanced the watermark and recorded no duplicate. 403 is terminal, 429 is retried with backoff, 404 is not a refusal. |
| G — Resource Safety | PASS | Discovery took 0.23s with no AI and 0.2s while the worker ran (0.87x). The read-only API served 3 request(s) during the batch with a median of 23.3 ms. The worker is a one-shot low-priority process with peak RSS 3095.0 MB. |

## Environment

- Radar directory: `D:\DEPPSKK\worktrees\radar-001\data\radar`
- Taxonomy: `radar-icu-2026.11.1` (fingerprint `50d9a75720743adc`)
- Graph: `radar-graph-1`
- Host: 16 cpus, 12262.5 MB available of 32189.3 MB
- Observations: 8593 (8593 versions, 8593 change events)

### Sources

| Source | Status | Access | Observations | Watermark | Last checked |
| --- | --- | --- | --- | --- | --- |
| crossref | OK | ENABLED | 1137 | 2027-02 | 2026-11-16T22:47:20+00:00 |
| draeger_official | OK | ENABLED | 31 | 2026-11-09T12:41:36+00:00 | 2026-11-16T22:24:00+00:00 |
| gehealthcare_official | BLOCKED_BY_ACCESS_POLICY | BLOCKED | 0 | — | never |
| openfda_device | OK | ENABLED | 6936 | 2026-11-02 | 2026-11-16T22:20:39+00:00 |
| philips_official | OK | ENABLED | 5 | 2026-11-16T07:30:00+00:00 | 2026-11-16T23:19:26+00:00 |
| pubmed | OK | ENABLED | 484 | 2026-11-17 | 2026-11-16T23:08:45+00:00 |

### Detection latency

- Exact samples: 5 (median 445.36 h)
- Approximate samples (date-only publication): 1621 (median 16798.35 h)

Detection latency is first_observed_at - published_at. It is only exact when the source states a timestamp with time-of-day. Date-only publication dates are reported separately as approximate and are never mixed into the exact figure.

## Raw evidence

The complete evidence for every test is in `acceptance_report.json`.
