# PRODUCT-002 — Independent governance review of the derived-binary gate

**Date:** 2026-11-15
**Scope:** `tools/governance/check_licence.py`, `docs/governance/DATA_LICENSES.yaml`, `tests/governance/test_licence_derived_binary.py`, `docs/governance/{DECISION_LOG,RULE_CHANGES}.yaml`
**Method:** offline only (git tree, committed files, local Python 3.12.10). No network or
external legal source was consulted. Items that cannot be established from repository
evidence are marked **UNKNOWN** rather than asserted.

---

## 1. GOV-0004 / RC-0004: what the exception was and why it was too broad

GOV-0004 (RC-0004) added `policy.derived_binary_allowlist`. It let a restricted binary
format be committed when the inventory entry was `GREEN`, the named source declared
`may_redistribute: true`, and the inventory `sha256` matched the file bytes. The gate
printed the policy reason and hash prefix.

The old `_declared_derived_binary` judge checked only four things: allowlist enabled,
entry `GREEN`, source redistributable, and SHA-256 present/matching. It did **not** check:

* which source id was named (any `GREEN` source qualified), which repository path was
  used, and which restricted content kind the bytes were (ELF, ZIP, SQLite, Parquet and
  HDF5 were all eligible);
* the file size and the extension/content-kind consistency.

`generate_inventory` also wrote a `sha256` for every restricted, `GREEN`, non-synthetic
file, so an operator could regenerate a hash-bound entry for an ineligible blob without
editing the inventory by hand. In effect, GOV-0004 was a general “any GREEN hash-declared
binary anywhere” route, not an openFDA-snapshot exception. That was too broad for a
repository whose policy says restricted binaries are otherwise forbidden.

## 2. GOV-0005: what is now enforced

`Policy` now parses `allowed_source_ids`, `allowed_paths`, `allowed_content_kinds` and
`max_bytes`; a missing or empty list becomes `[]` and a missing/invalid byte cap becomes
`None`, so the scope permits nothing. `_declared_derived_binary(entry, data, policy, path)`
checks, in order, every condition below and returns a reason naming the failed condition.

| # | Condition | Implementation | Counter-example test | Result |
|---|---|---|---|---|
| a | Allowlist enabled | `derived_binary_allowed` + first scope check | `test_allowlist_disabled_fails` | PASS |
| a′ | Enabled allowlist must declare every scope key at policy parse time | `_check_policy_sections` | `test_enabled_allowlist_without_scope_key_is_a_policy_failure` | PASS |
| b | Detected kind in `allowed_content_kinds`; extension consistent (`.gz` for gzip); ELF/ZIP/SQLite/Parquet/HDF5 always rejected | `_derived_binary_scope_error`, `DERIVED_BINARY_EXTENSIONS`, `DERIVED_BINARY_FORBIDDEN_KINDS` | `test_elf_zip_sqlite_parquet_hdf5_content_fails_even_with_sha256`; `test_gzip_with_inconsistent_extension_fails` | PASS |
| c | Inventory `source_id` in `allowed_source_ids` | `derived_binary_source_ids` | `test_gzip_attributed_to_other_green_source_fails` | PASS |
| d | Repository path matches one of `allowed_paths` (literal `fnmatch` globs; empty allows nothing) | `derived_binary_paths` + `fnmatch.fnmatchcase` | `test_gzip_outside_allowed_path_fails`; `test_missing_or_empty_scope_keys_fail_closed` | PASS |
| e | File byte length `<= max_bytes` | `derived_binary_max_bytes` | `test_oversized_gzip_fails` | PASS |
| f | Entry `GREEN`, source `may_redistribute: true`, declared SHA-256 present and equal to the committed bytes | `_declared_derived_binary` | `test_sha256_mismatch_fails`; `test_amber_and_red_sources_keep_failing` | PASS |
| — | No inventory entry at all | `check_tree` → `inventory.coverage` + `content.restricted_kind` | `test_new_gzip_under_allowed_path_without_inventory_entry_fails` | PASS |
| — | The three committed snapshot gz files still pass | `_declared_derived_binary` on the real entries | `test_committed_snapshot_gz_files_pass_and_digests_are_bound` | PASS |

The policy values are: `allowed_source_ids: [openfda_device]`,
`allowed_paths: ["medradar/product/snapshot/*.gz"]`, `allowed_content_kinds: [gzip]`,
`max_bytes: 33554432` (32 MiB). `enabled`, `require_sha256`, `require_may_redistribute`
and `reason` are retained. `_check_policy_sections` also fails a policy whose enabled
allowlist lacks a non-empty list or a positive byte cap. `generate_inventory` now adds
`sha256` only to GREEN, non-synthetic entries that pass `_derived_binary_scope_error`, so
regenerating the inventory cannot bind an out-of-scope blob. This is a narrowing: the set of
files the exception can cover is now a subset of the old set, not a licence expansion.

## 3. Snapshot review: source statement and compressed fields

### 3.1 openFDA redistribution / source statement

`DATA_LICENSES.yaml` declares `openfda_device` as `GREEN`, `may_redistribute: true`, with
the attribution “U.S. Food and Drug Administration openFDA (510(k), PMA and device-recall
endpoints). U.S. Government work; not endorsed by the FDA.”

Offline findings:

* **Endpoint coverage is incomplete.** `scripts/product_collect.py` queries four endpoints:
  `/device/510k.json`, `/device/pma.json`, `/device/recall.json` and
  `/device/classification.json`. The attribution sentence names the first three but not the
  classification endpoint, although `classifications.jsonl.gz` is committed. The statement
  should explicitly include device-classification records.
* **“U.S. Government work; not endorsed by the FDA”** is consistent with the repository’s
  own statements (`medradar/product/dataset.py` reports “public domain (openFDA)” and
  product documents describe the records as public openFDA data). The actual openFDA terms
  of service were **not** fetched in this offline review, so the legal accuracy of the
  public-domain and non-endorsement wording is **UNKNOWN**.
* **“No additional third-party content”** in the policy comment is a provenance claim. The
  field inspection in §3.2 is consistent with it, but a byte-level legal provenance audit
  was not possible offline; treat that claim as **UNKNOWN** pending human licence review.

### 3.2 Fields in the compressed snapshot

Derived by opening each committed `.jsonl.gz` with `gzip.open(..., "rt")`, parsing every
line with `json.loads`, and taking the union of top-level keys (and, for `events`, the
union of `raw` keys per source): read-only, offline, and no values are copied here.

| File | Records | Top-level fields |
|---|---:|---|
| `events.jsonl.gz` | 91,457 | `applicant_name`, `device_name`, `event_date`, `event_id`, `event_type`, `official_id`, `official_url`, `product_code`, `published_at`, `published_at_status`, `raw`, `source_id`, `summary`, `time_quality` |
| `classifications.jsonl.gz` | 7,098 | `device_class`, `device_name`, `implant_flag`, `life_sustaining`, `product_code`, `regulation_number`, `specialty` |
| `applicants.jsonl.gz` | 1,563 | `applicant_name`, `by_org_scope`, `by_source`, `records` |

`events.raw` contains only project-selected openFDA fields; per source the observed keys are:

* **510(k):** `advisory_committee`, `advisory_committee_description`, `applicant`,
  `clearance_type`, `country_code`, `date_received`, `decision_code`, `decision_date`,
  `decision_description`, `device_name`, `expedited_review_flag`, `k_number`,
  `product_code`, `statement_or_summary`.
* **PMA:** `advisory_committee`, `advisory_committee_description`, `ao_statement`,
  `applicant`, `date_received`, `decision_code`, `decision_date`, `docket_number`,
  `expedited_review_flag`, `generic_name`, `pma_number`, `product_code`,
  `supplement_number`, `supplement_reason`, `supplement_type`, `trade_name`.
* **Recall:** `action`, `cfres_id`, `city`, `code_info`, `distribution_pattern`,
  `event_date_as_published`, `event_date_created`, `event_date_initiated`,
  `event_date_posted`, `event_date_terminated`, `k_numbers`, `product_code`,
  `product_description`, `product_quantity`, `product_res_number`, `reason_for_recall`,
  `recall_status`, `recalling_firm`, `res_event_number`, `root_cause_description`, `state`.

`event_date_as_published` is a derived key added during compaction (16 recall records with
an implausible date); free-text fields are truncated but not invented. `event_id`,
`source_id`, `event_type`, `official_id`, `official_url`, `published_at_status` and
`time_quality` are derived identifiers/status labels. `summary` is derived from source
fields (generic/trade name or recall reason). `official_id` is the source identifier and
`official_url` is constructed from it. `applicant_name`, `product_code`, `device_name`,
`event_date` and `published_at` are projected from the source record.

`classifications` fields are from `/device/classification.json`; `specialty` maps
`medical_specialty_description` (or `review_panel`) and `life_sustaining` maps
`life_sustain_support_flag`. `applicants` contains the source applicant string plus
derived counts (`records`, `by_source`, `by_org_scope`).

**Conclusion:** the compressed snapshot contains openFDA record fields (some renamed or
truncated) plus derived identifiers, URLs, status/quality labels and aggregate counts; no
non-openFDA third-party field names were observed — a field/provenance inspection, not a legal conclusion.

### 3.3 Hash semantics finding

`snapshot.json` and the inventory do not hash the same bytes:

| File | `.gz` bytes | SHA-256 of `.gz` bytes (inventory) | `snapshot.json` `sha256` | SHA-256 of expanded JSONL |
|---|---:|---|---|---|
| `applicants.jsonl.gz` | 22,428 | `2a84343d843d1a15…` | `309a7cf4199fbb2f…` | `309a7cf4199fbb2f…` |
| `classifications.jsonl.gz` | 159,193 | `69b06d08ffb3ded7…` | `bbee2d1109abbbe5…` | `bbee2d1109abbbe5…` |
| `events.jsonl.gz` | 12,842,998 | `044736477d6e8b01…` | `f2676ef7494467ae…` | `f2676ef7494467ae…` |

`scripts/product_collect.py::gzip_write` computes the manifest digest over the uncompressed
JSONL payload before gzip. The inventory digest is computed over the committed `.gz` bytes,
which is what `_declared_derived_binary` compares. Both bindings are internally consistent,
but they are **not the same value**, so the brief’s expectation that the inventory SHA-256
equals the manifest SHA-256 does not hold in this tree. `docs/product/DATA_CONTRACT.md`
(“`snapshot.json` records the SHA-256 of every data file”) is therefore imprecise: it
records the expanded-payload digest, not the artifact digest. The positive test asserts both
bindings explicitly so neither can drift silently.

## 4. Counter-example matrix

All tests are in `tests/governance/test_licence_derived_binary.py`. Offline runs on
2026-11-15 with Python 3.12.10 on the final working tree:

```
python -m pytest tests/governance -q                            -> 71 passed, 28 subtests passed in 43.26s
python tools/governance/check_licence.py --base origin/main      -> PASS check_licence (20 checks, 0 failures, 1 warnings)
python tools/governance/check_rule_audit.py --base origin/main   -> PASS check_rule_audit (36 checks, 0 failures, 0 warnings)
python tools/governance/check_frozen.py --base origin/main       -> PASS check_frozen (37 checks, 0 failures, 0 warnings)
python tools/governance/check_licence.py --write-inventory       -> 207 data files; DATA_INVENTORY.yaml unchanged
```

| Test | Scenario | Gate result |
|---|---|---|
| `test_sha256_mismatch_fails` | bytes replaced after the inventory hash was declared | FAIL (`sha256 mismatch`) |
| `test_new_gzip_under_allowed_path_without_inventory_entry_fails` | new `.gz` in the allowed directory, no inventory entry | FAIL (`inventory.coverage`, `content.restricted_kind`) |
| `test_gzip_attributed_to_other_green_source_fails` | gzip attributed to `medradar_derived_artifacts` | FAIL (`allowed_source_ids`) |
| `test_elf_zip_sqlite_parquet_hdf5_content_fails_even_with_sha256` | each forbidden format with a declared hash, including a policy that lists it | FAIL (`content kind ... never allowed`) |
| `test_gzip_outside_allowed_path_fails` | valid gzip at `docs/data.gz` | FAIL (`allowed_paths`) |
| `test_gzip_with_inconsistent_extension_fails` | valid gzip at a path that matches the glob but has a non-`.gz` suffix | FAIL (`extension`) |
| `test_oversized_gzip_fails` | gzip above `max_bytes` | FAIL (`max_bytes`) |
| `test_allowlist_disabled_fails` | `enabled: false` | FAIL (`disabled`) |
| `test_missing_or_empty_scope_keys_fail_closed` | each scope key missing or empty | FAIL (`... declares no <key>` / `exceeds max_bytes`) |
| `test_enabled_allowlist_without_scope_key_is_a_policy_failure` | enabled policy missing `allowed_paths` | FAIL (`policy.derived_binary_allowlist.allowed_paths`) |
| `test_amber_and_red_sources_keep_failing` | AMBER/RED entry status, and GREEN entry on a non-redistributable source | FAIL (`not GREEN` / `not declared redistributable`) |
| `test_amber_and_red_inventory_entries_still_fail_check_tree` | AMBER/RED entries through the full tree scan | FAIL (`content.restricted_kind` / `content.red_source`) |
| `test_committed_snapshot_gz_files_pass_and_digests_are_bound` | the three committed snapshot gz files | PASS (artifact hash and payload hash both verified) |

## 5. Residual risks

* **Human licence judgement is still required.** The gate checks consistency between the
  policy, the inventory, the committed bytes and the source declaration. It cannot decide
  whether openFDA terms, attribution wording or a particular redistribution are lawful.
* **The gate is a consistency control, not a legal guarantee.** A wrong human
  classification of a source as `GREEN` and redistributable is not detected.
* **SHA-256 binds bytes, not provenance.** A matching hash proves the reviewed bytes were
  committed; it does not prove where those bytes came from or that they may be
  redistributed.
* **The gzip payload is not inspected.** The gate classifies the container as gzip; it does
  not decompress and review the records. A gzip from the allowed source could still carry
  unreviewed content. The snapshot payload must be reviewed by a human.
* **`fnmatch` semantics.** Python’s `fnmatch` `*` crosses `/`, so
  `medradar/product/snapshot/*.gz` also matches nested paths under the snapshot directory.
  The scope is still anchored under that directory, but it is not a strict single-level
  match.
* **Source-statement gap.** The `openfda_device` attribution omits the classification
  endpoint used for `classifications.jsonl.gz`; that wording should be corrected in a
  reviewed policy change.
* **Manifest/documentation mismatch.** `snapshot.json` carries payload digests while the
  inventory carries artifact digests; `docs/product/DATA_CONTRACT.md` should say so
  explicitly. External openFDA terms and the “public domain” claim remain **UNKNOWN** in
  this offline review.
