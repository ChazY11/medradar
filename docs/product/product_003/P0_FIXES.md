# P0_FIXES (PRODUCT-002 defects fixed before PRODUCT-003)

Two P0 defects were found in the PRODUCT-002 delivery and are fixed here, on a separate branch stacked
on PR #47 so they can be reviewed without the new module.

---

## P0-A: the reviewer could declare itself a human

### What was wrong

`POST /api/review/decisions` accepted `reviewer_kind` from the request body and defaulted it to
`"human"`. The store's only guard was `status == human_reviewed requires reviewer_kind == "human"`,
i.e. the *same value the client supplied*. Any caller - an AI agent, a script, a browser tab - could
therefore write `human_reviewed` by asserting it.

### What is enforced now

| Requirement | Implementation |
|---|---|
| A client cannot choose its authority class | The request body field `reviewer_kind` is rejected with `400 reviewer_kind_forbidden` on decide/revoke; the import endpoint ignores it and reports `ignored_reviewer_kind_fields` |
| Human is not the default | There is no default. The server derives the only authority it can attest, `agent`, and records `authority_method` (`local_service_token`, `cli_offline`, `offline_import`) |
| An agent cannot produce `human_reviewed` | The store refuses the status itself (`HumanAuthorityUnavailable`) and the API returns `403 human_review_authority_unavailable`; `human_authority()` raises unconditionally in this release |
| History stays complete | The ledger is still append-only, and the historical `reviewer_kind` column is never rewritten |
| Migration must not silently promote | Legacy rows are copied into a new `review_authority` table with `unverified_operator`; a legacy `human_reviewed` claim has its **effective** status downgraded at read time to `evidence_verified` (evidence present) or `unresolved`, with `status_recorded`, `status_downgraded` and a reason exposed in the API |
| Forged requests are tested | `tests/product/test_reviewer_authority.py` (11 tests) and browser check E2E-17 |

### The capability is reported, not hidden

`GET /api/review/capabilities` states:

```json
{
  "human_review_authority_available": false,
  "writable_statuses": ["rule_verified", "evidence_verified", "rejected", "unresolved"],
  "authority_kinds": ["agent"],
  "human_review_reason": "Human review authority requires server-side operator authentication ..."
}
```

The review workspace shows the same statement in place of the removed status option. `evidence_verified`
remains available and still requires at least one recorded evidence reference; it is the strongest
status this release can issue. Re-enabling `human_reviewed` requires a real server-side operator
authentication and authorisation mechanism - not a flag.

### Verification

```bash
python -m pytest tests/product/test_reviewer_authority.py -q     # 11 passed
python -m pytest tests/product -q                                 # 120 passed
```

Legacy migration is tested against a hand-built schema-1 database containing a forged
`human_reviewed` row: the row survives byte-identically, the effective status is downgraded, the audit
trail records `migrate:schema_v2`, and a second open is a no-op.

---

## P0-B: "original registrant" was not historical ownership

### What was wrong

`basis=original_registrant` excluded records whose applicant string matched a predecessor pattern. That
is a *name* rule, not a *time* rule. If an entity was acquired in 2023 and kept filing under its own
name in 2024, both the 2022 and the 2024 records were labelled "pre-acquisition". The basis also
silently dropped records, so a filtered count could read as low activity.

### The three concepts, now separated

| Concept | Field / API | Meaning |
|---|---|---|
| Original applicant | `applicant_name` (unchanged) | the verbatim FDA string; evidence, not interpretation |
| Registry-assigned group | `organization_key` | what the current registry attributes the applicant to |
| Historical owner at event time | `attribution.historical_owner` | who controlled the applicant **on the record's event date**, from a verified relation with an effective date |

`historical_owner` is computed per record:

* `verified_current_group` — a verified relation with `effective_from <= event_date` covers the applicant;
* `verified_predecessor` — the event predates every verified effective date, and the relation names
  the previous owner (e.g. "Covidien plc (NYSE: COV)", "General Electric Company");
* `unknown` with a reason: `no_relation`, `no_effective_date`, `no_event_date`.

### New counting basis

`basis=historical_owner_verified` (default remains `current_group`) keeps only
`verified_current_group` records. The comparison, the CSV provenance, the Markdown report and the
organization page report **what was excluded**:

* `basis_excluded_totals.excluded_predecessor_owner` (owner at event time was a predecessor),
* `basis_excluded_totals.excluded_unknown_owner` (owner unknown),
* warning `historical_owner_basis_excludes_records` explaining that an excluded record is not a zero.

The retired name is refused, not reinterpreted: `basis=original_registrant` returns
`400 retired_basis` with a hint pointing at `historical_owner_verified`.

### Measured on the committed snapshot

| Organization | Records | Owner = this group | Owner = predecessor | Owner UNKNOWN |
|---|---|---|---|---|
| Medtronic | 17,473 | 674 | 370 | 16,429 |
| GE HealthCare | 2,311 | 377 | 1,934 | 0 |
| Abbott | 8,737 | 0 | 0 | 8,737 |

Same spelling, different date, different answer (the exact failure mode of the old basis):

```
"Covidien Lp, Formerly Know AS Valleylab, A Divison"  2008-11-25  -> verified_predecessor (Covidien plc)
"Covidien, LLC"                                      2022-06-13  -> verified_current_group
```

In the 2021-2025 comparison window, GE HealthCare keeps 301 records under the historical basis and
reports 192 excluded because General Electric owned the business on those event dates; Medtronic keeps
196 and reports 3,230 excluded because their owner at event time is unknown (no verified relation).

### Consistency across surfaces

The same semantics are asserted in tests across the profile, the events API, the comparison, the CSV
and both Markdown exports (`tests/product/test_historical_ownership.py`), including the case where an
organization has *no* verifiable owner: Abbott returns 0 counted records **and** a non-zero excluded
unknown count, so the page can never imply "no activity".

---

## Not in scope for the P0 branch

The Device Intelligence module, its model, pages and tests. Those are PRODUCT-003 and live on the
branch stacked on top of this one.
