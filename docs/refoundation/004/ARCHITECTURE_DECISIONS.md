# REFOUNDATION-004 - Architecture decisions

Each decision states the problem, the options considered, the choice, what it costs, and how a
future reader can reverse it. The decisions are ordered by blast radius.

## ADR-001 Relevance is a dimension set, not a tier

**Problem.** One label (HIGH_RELEVANCE) answered eight questions at once (audit D1). A press
release could be HIGH because the source was official (D2); a paper could be rejected because its
journal name contained a non-medical word (D3).

**Options.**
1. Keep one tier and add more exclusion keywords. Rejected: this is the mechanism that produced
   D2-D5; tightening keywords trades false accepts for false rejects and cannot distinguish
   "official" from "about monitoring".
2. Replace the tier with a model. Rejected: no labelled training set, no explainability, and the
   project's evidence standard requires deterministic, auditable rules.
3. Separate the judgements, keep the rule layer deterministic, and derive the tier from a policy.

**Decision (3).** `medradar/radar/assessment.py` produces:

source_authenticity (PRIMARY_REGULATORY | OFFICIAL_VENDOR | SCHOLARLY | SECONDARY),
medical_domain (MEDICAL | NON_MEDICAL | UNCERTAIN),
monitoring_relevance (DIRECT | TRANSFER | CLINICAL | MEDICAL_UNRELATED | NON_MEDICAL),
entity_link (NONE | AFFILIATION | VENDOR | APPLICANT), freshness, importance, confidence,
and decision (FEED | REVIEW | EXCLUDED).

The feed decision is a policy: FEED iff monitoring_relevance is DIRECT, or TRANSFER **with an
explicit patient-monitoring purpose in the title**. Nothing else enters the default feed. The tier
(HIGH/NEEDS_REVIEW/LOW/IRRELEVANT) is kept as a compatibility projection of the decision so the
ledger, API, UI views and historical rows keep their meaning.

Text roles are separated: subject text (title, abstract, official summary) alone can establish
what a record is about; venue text (journal) can only add a positive engineering signal; index
text (MeSH/Crossref subject) is a weak positive; entity text (applicant, publisher) establishes
linkage, never relevance. This is what fixes D2 and D3 structurally rather than by exception.

**Cost.** The engine is larger (889 lines) than the old scoring module (421) and has more
vocabulary to maintain. **Mitigation:** single entry point, versioned (`radar-assessment-2026.11.19`),
and every decision stores its reasons, features, dimensions, rules digest and judged version.

**Reversal.** The tier projection is unchanged, so a caller can ignore dimensions. Dropping the
dimensions would mean rewriting one module and one schema column set.

## ADR-002 Admission decisions are append-only; the current view is a derived projection

**Problem.** `observation_admission` was keyed by (observation_id, admission_version) and written
with INSERT OR REPLACE, so a re-judgement overwrote history (audit D6, QA-002).

**Options.** (a) Add an audit table beside the existing one: two sources of truth, and the bug
stays in the main table. (b) Append-only history plus a rebuildable current projection: history is
the source of truth, reads are cheap. (c) Event sourcing with an external log: over-engineering for
one SQLite file.

**Decision (b).**
- `observation_admission` (v3): one row per judgement, surrogate key, `evidence_key` (digest of
  judged version + mapped facets + rule digest), `rules_digest`, `judged_version_id`, `decision`,
  `dimensions`; triggers reject UPDATE and DELETE.
- `admission_current`: derived projection of the newest row per (observation, version), rebuilt
  automatically if it is behind the history.
- `admission_workqueue`: mutable work state (which observations need a decision and why). A new
  version/mapping queues the observation; a changed rules digest re-queues it.

Idempotency: same evidence + same rules => same evidence_key => `INSERT OR IGNORE` writes nothing.
Migration: v2 tables are renamed, copied forward row by row (decision derived from the old tier,
marker `{"migrated_from": "radar-ledger-v2"}`, rules digest `legacy-v2`), then the old copy is
dropped; nothing is lost if the copy fails before the drop. The real 8,593-row ledger was migrated
in this round and a test constructs a v2 table and asserts the migrated decisions.

**Cost.** Two tables and a ~15-line rebuild path; writes touch two tables. **Benefit:** history is
provable (test: two judgements, history length 2, current = newer) and feed reads do not pay for a
correlated MAX (benchmark in PERFORMANCE.md).

## ADR-003 Work identity is the official identifier, not the title

**Problem.** The feed deduplicated by normalised title (audit D10).

**Decision.** A materialised `observation.work_key` is computed from DOI (lowercased, normalised),
then PMID, then a normalised title fallback; the feed partitions by it. The observation remains the
unit of storage (two sources publishing one DOI stay two observations, which is the corroboration),
and one *work* is one feed row. A test covers: same DOI + different titles => one row; same title +
different DOIs => two rows.

**Cost.** One derived column and an index; the fallback still merges different works that share a
title and carry no identifier (disclosed as a limitation, not hidden). **Reversal:** drop the
column and restore the title partition.

## ADR-004 Discovery stores everything; qualification decides

**Problem.** PubMed/Crossref adapters filtered records before the ledger stored them (audit D11),
using a second relevance rule set.

**Decision.** Adapters store what the source returned. Relevance is a property of a decision that
can be re-made under a new rule version. The generic `accept_record` hook stays in the adapter
framework for a future source with a licensing/access constraint, but the two publication adapters
no longer use it.

**Cost.** Ingestion volume grows for search-based sources; the existing ledger was not
re-collected, so the evaluation sample cannot contain records the old gate dropped (stated in the
quality report as a selection limit). **Reversal:** re-add `accept_record` overrides.

## ADR-005 Time is stored and shown at the precision the source stated

**Problem.** A month-precision date was rendered as a midnight instant (audit D9); openFDA decision
dates could be mistaken for publication dates; the "latest" scope could include a source-stated
future date.

**Decision.** Keep event_at/published_at/source_updated_at/first_observed_at/last_checked_at as
distinct fields with a precision each (records.py already did this); freshness is computed from the
earliest instant a precision-limited date can denote; the UI formats according to precision and
shows a precision label; a primary-record publication date that the source does not publish is
rendered as "not published by source", never as the decision date; the "latest" scope requires
`date <= now`.

**Cost.** Coarse-precision records are judged conservatively and may miss a "latest" window when
their interval straddles the boundary; that is the honest direction for a freshness claim.

## ADR-006 One generated quality report, one frozen sample, one baseline

**Problem.** The previous acceptance document contradicted its own JSON (audit D7) and measured a
14-day window against a 30-day product (D8).

**Decision.** `scripts/evaluate_relevance.py` is the only producer: it reads a frozen labelled
sample and a read-only ledger, computes binary and 5-class metrics with Wilson intervals and
N/A-as-null, and writes both JSON and Markdown from the same object. `--check` fails if either
file is stale. A test asserts the evaluator window equals the API default. Samples are frozen
before rule work and carry a sha256 of their items; two samples exist: a development sample
(used while designing v2) and a held-out sample (drawn with a different seed after the rules were
frozen). The headline number is the held-out one; the development number is reported beside it so
the optimism gap is visible.

**Cost.** A rule change requires re-running the command and regenerating both files; committing a
hand-edited number is now a test failure rather than a documentation slip.

## ADR-007 Keep the modular monolith, do not split the lanes this round

**Problem.** Three lanes with three stores (audit D18) and API/dataset hotspots (D15).

**Options.** (a) Create services per lane: rejected, no operational capacity and the failure modes
(snapshot activation, single-writer lock) are solved locally. (b) Unify all three stores into one:
rejected for this round, it needs a snapshot rebuild, a browser E2E matrix and a deployment window.
(c) Declare the radar ledger the intelligence system of record, keep the snapshot as the FDA
evidence store, freeze the legacy lane, and document the seams.

**Decision (c).** The doc `docs/refoundation/004/REPAIR_PLAN.md` lists the concrete merge steps for
the next round (shared Observation/Evidence contract, one organization registry, one API surface),
each with its precondition.

**Cost.** The duplication is documented, not removed. A future round pays for it with interest;
pretending otherwise would be worse.

## ADR-008 Do not create a new framework for the repair

No new dependency was added. The assessment engine, the v3 schema, the derived projection, the
evaluator and the tests use the standard library plus what the project already depends on (pytest,
FastAPI for the existing API, Vite/React for the existing UI). The web bundle was rebuilt with the
existing toolchain; the only new artefact is `web/dist/index-Bxn-0Rgq.js` replacing the previous
hash.
