# HORIZON-001 — starting brief for every data workstream

You are working inside the isolated git worktree

```
D:\DEPPSKK\worktrees\horizon-001        (branch research/horizon-001)
```

**Read this whole file before touching anything.**

---

## 1. Hard rules (violating these breaks the project)

1. **Never run any `git` command.** The Lead owns all commits. Writers only write files.
2. **Never touch anything outside your assigned write scope** (given in your task brief).
3. **Never write outside** `research/horizon/`.
4. **Never modify** `medradar/`, `research/studies/`, `research/RESULTS/`, `tests/`, `docs/` or any top-level repo file. Those belong to ATLAS-001 or are frozen history.
5. **No fabricated data.** If a source cannot be fetched, record the failure. A
   `BLOCKED_*` outcome is a valid, valuable deliverable. An invented row is not.
6. **No guessing identifiers.** Only put a value in `identifiers` if it appears in
   the source response you saved. Otherwise omit it and add `MISSING_IDENTIFIER`.
7. **Respect access controls.** No key bypassing, no WAF circumvention, no
   credential use, no crawling of sites whose robots.txt/ToS forbids it. If it
   needs a key → mark `REQUIRES_REGISTRATION` and record the official signup URL.
8. **Bound everything.** Every HTTP client gets `max_requests`, a per-response
   byte cap and a total byte cap. No unbounded loops over paginated APIs.
9. **Python 3.12**, standard library + `requests` only (plus `lxml`/`pandas` which
   are installed). Do not `pip install` anything.
10. **Windows paths.** Use `os.path`, always `encoding="utf-8"`, always
    `newline="\n"`. Never write non-ASCII into a file without UTF-8.

---

## 2. The engineering core you must build on

Everything lives in `research/horizon/hz/`. Read these files first — they are
short and they are the contract:

| module | what it does |
|---|---|
| `hz/schema.py` | `horizon.evidence.v1` record + `build_record()` + `dedupe_key()` |
| `hz/timeq.py` | the four clocks, `audit_clocks()`, `classify_record()` |
| `hz/http.py` | `BoundedClient` — budget, retries, byte caps, request log |
| `hz/probe.py` | `Probe` / `run_probes()` → `SOURCE_PROBES/<suite>/PROBES.json` |
| `hz/registry.py` | `SourceEntry` → `registry/sources/<id>.json` |
| `hz/export.py` | `write_export()` → `exports/<id>/` with `MANIFEST.json` |
| `hz/verify.py` | offline self-check |
| `hz/suites.py` | auto-discovers `hz/suites_<name>.py` probe suites |

### Running it

```powershell
cd D:\DEPPSKK\worktrees\horizon-001\research\horizon
python -m hz.cli sources
python -m hz.cli probe --suite <your_suite>
python -m hz.cli verify
```

### Adding a probe suite (no conflict risk)

Create `hz/suites_<yourname>.py`:

```python
from .probe import Probe

def probes() -> list[Probe]:
    return [
        Probe(
            probe_id="my_source_001",
            source_id="my_source",
            url="https://example.org/api/search?q=test",
            question="Does the public endpoint return JSON without an API key?",
            expect_marker='"results"',
            note="documented at https://example.org/docs",
        ),
    ]
```

Then `python -m hz.cli probe --suite <yourname>` writes
`SOURCE_PROBES/<yourname>/PROBES.json` + `REQUEST_LOG.jsonl` automatically.

### Emitting records

```python
from hz.schema import build_record, write_jsonl
from hz.timeq import classify_record

rec = build_record(
    source_id="accessgudid",
    source_record_id="00643169718425",
    entity_type="product_identifier",
    original_name="INVOS 5100C CEREBRAL OXIMETER",
    identifiers=[{"scheme": "udi_di", "value": "00643169718425"}],
    manufacturer="Medtronic",
    attributes={"brand_name": "...", "model": "..."},
    event_at=None,
    source_public_at=None,
    first_observed_at=None,
    fetched_at="2026-11-10T00:00:00Z",
    source_url="https://accessgudid.nlm.nih.gov/...",
    licence_status="public_domain",
    identity_status="UNKNOWN",
    evidence_status="CANDIDATE",
    quality_flags=["MISSING_PUBLICATION_DATE"],
)
rec.validate()
```

---

## 3. Evidence discipline — the part that actually matters

Four separate success levels. **State which one you achieved, per source.**

| level | meaning | how it is proven |
|---|---|---|
| **ACCESS** | the endpoint answered | a `PROBES.json` entry with status + bytes + sha256 |
| **DATA** | the body has stable structure and the fields we need | a saved raw sample under `DATASETS/` + a parser that reproduces a record |
| **IDENTITY** | evidence pins down a specific company/device | an official identifier from the source, not a name match |
| **RESEARCH** | the new data adds verifiable independent information | measured in an experiment against a fixed baseline |

Never promote one to the next. A 200 response is not a dataset. A name match is
not an identity. A bigger row count is not research value.

### Time semantics (non-negotiable)

- `event_at` = when the thing happened (filing date, approval date, award date).
- `source_public_at` = when a human could first have seen this record.
- Never use `event_at` as `source_public_at`. That is the single error that
  fabricates retrospective foresight.
- If you only have one of them, leave the other `None` and add the matching
  `MISSING_*_DATE` quality flag.

### Licence

Every source gets a `licence_status` from the closed vocabulary in
`hz/schema.py`. Quote the licence URL and the exact sentence you relied on in
the registry entry's `licence_note`. If the licence is unclear, say
`open_no_explicit_licence` — do not invent permissiveness.

---

## 4. Deliverable shape per source

```
CONNECTORS/<source_id>.py            # runnable, parses raw -> horizon.evidence.v1
SOURCE_PROBES/<your_suite>/PROBES.json
SOURCE_PROBES/<your_suite>/REQUEST_LOG.jsonl
DATASETS/<source_id>/raw/...         # bounded raw response(s), exactly as received
DATASETS/<source_id>/PROVENANCE.json # url, sha256, bytes, fetched_at, licence
registry/sources/<source_id>.json    # SourceEntry
```

Raw files under `DATASETS/` must be **verbatim** server responses (no reformatting)
so a third party can re-hash them and compare with `PROVENANCE.json`.

---

## 5. Reporting back to the Lead

When you stop, send the Lead a compact message containing:

1. Per source: final `access_state`, `licence_status`, and **exactly** which of
   ACCESS / DATA / IDENTITY / RESEARCH you achieved.
2. Row counts: fetched, parsed, deduplicated, with-identifier, with-public-date.
3. Anything blocked, with the precise blocker (HTTP code + body signature) and the
   legitimate unlock route.
4. Absolute paths of every file you created.
5. Anything the Lead must know before writing the reports.

Keep it factual. Under-promise. If you got nothing usable from a source, say so
plainly — a clean negative is worth more than a padded positive.
