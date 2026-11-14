# Known Limitations

Everything here is a real property of the v1 release, disclosed in the product where it matters.
None of it is a hidden defect: the product's stance is that a limitation shown is better than a
number smoothed over.

---

## 1. Coverage limitations (data)

| Limitation | Detail | Where it is disclosed |
|---|---|---|
| Not the full FDA applicant universe | The snapshot tracks **59 organizations**. A company outside the registry has no records, which is a coverage statement, not evidence of no activity. | Search empty state, Organizations page, Sources page |
| 73 records unattributed | Two applicant strings could not be attributed to a tracked organization; they are counted and listed, never folded in. | Sources / attribution audit; `/api/attribution` |
| Out-of-scope sources | De Novo (no openFDA endpoint), NMPA/China (WAF-blocked), EU MDR/CE, UDI, establishment registrations, clinical trials, financial filings, patents, hiring. | Sources page "Not covered in this release" |
| Snapshot, not a feed | Data is an immutable snapshot collected 2026-11-14/15. Records created after that date are absent until the collector is re-run. Freshness older than 30 days is flagged. | Snapshot chip, freshness badge, overview banner |
| No product/device identity | A device is a *record*, not an entity. The same device can appear as a 510(k), a PMA supplement and a recall; v1 does not deduplicate device lineage or versions. | ARCHITECTURE "not delivered"; NEXT_STEPS |
| No ownership aggregation | Organizations are tracked units. Parent/subsidiary relations are declared in notes but not used to aggregate totals, because the relations were not verified for this release. | Organization page "Ownership" |
| Recall semantics | Recalls are safety actions, not product launches; some recall records are product-level rows sharing one FDA event number. They are counted as records and labelled. | Compare warnings, event type notes |
| PMA supplements dominate volume | 37,658 of 91,457 records are PMA supplements. They are counted separately and never treated as new devices; a naive total of "records" would be misleading, so every aggregate states the event types it sums. | Event type labels, comparison warnings |

## 2. Attribution limitations (the main one)

* **1,410 of 1,590 accepted applicant spellings are machine-proposed and marked
  `pending_review`.** They cover **75,044 of 91,384 attributed records (82%)**. The rule used is
  narrow (observed inside the organization's own query scope + contains its distinctive token as a
  whole-word sequence + no exclusion token), and every proposal records its source, but no human has
  signed these mappings off.
* The UI labels every affected record as *provisional* and offers an attribution-review filter. The
  organization page and comparison warnings state the provisional share. Users who need only
  reviewed mappings can filter to `review=curated` (16,340 records).
* 9 look-alike strings are explicitly rejected with reasons; 2 ambiguous joint-venture strings are
  left unattributed rather than guessed.
* Corporate ownership history (e.g. Covidien and Tyco Healthcare for Medtronic, St. Jude for Abbott,
  CareFusion and Bard for BD, Howmedica and Wright Medical for Stryker) is encoded as curated
  applicant spellings with a basis, not as a temporal ownership graph. A record filed before an
  acquisition is attributed to the acquirer with a declared note; it is not re-attributed by date.
* Non-US parents (Dräger, Mindray, Philips, Siemens Healthineers) appear mostly through their US
  operating entities. The registry entry says so; the totals are therefore "FDA-recorded activity",
  not global corporate activity.

## 3. Time semantics limitations

* openFDA states **no publication timestamp** for 510(k) and PMA records. `published_at` is null for
  those sources by rule; the product never back-fills it from the decision date.
* `first_observed_at` is the snapshot collection time. It proves when MedRadar saw a record, not when
  the world could have seen it. Any "early signal" analysis on this data would therefore be
  retrospective - which is why the product makes no predictive claim.
* 16 records carried implausible dates (e.g. year 0010) and were quarantined: listed with
  `time_quality = unknown`, excluded from year series, original value preserved in the raw fields.
* Date-only precision: 510(k)/PMA dates are dates, not timestamps; ordering within a day is not
  meaningful.

## 4. Analytical limitations

* Record counts are **not** innovation, quality or market share. The product states this on every
  comparison and refuses to rank.
* Counts of different event types are not comparable with each other; every aggregate declares what
  it sums. PMA originals (574) and 510(k) clearances (23,400) measure different regulatory pathways.
* Comparison windows use complete calendar years for rates; partial years are shown but excluded from
  rates. A difference between two organizations can be driven by coverage start dates (e.g. recalls
  from the early 2000s, 510(k) back to the 1970s).
* Category mapping depends on the FDA classification dictionary; 1,257 records (1.4%) use product
  codes absent from the dictionary and are grouped as unclassified.
* No market, financial or clinical-outcome data is collected, so "competitive position" cannot be
  inferred beyond regulatory activity.

## 5. Product / engineering limitations

* **Bilingual coverage is partial.** All chrome, navigation, labels and page introductions are
  translated (EN/中文); long methodology prose and warning messages are English-only.
* **No accounts, saved views, alerts or collaboration.** The URL is the only saved state.
* **No PDF export.** CSV and Markdown are implemented; PDF was cut rather than shipped half-done.
* **Single-process in-memory dataset.** Loading 91k records takes ~3 s and holds them in memory.
  This is fine for one analyst and would need a store for multi-tenant or 10x data.
* **Attribution is loaded from a static JSON registry.** There is no review UI for accepting or
  rejecting proposed spellings; the review workflow is a script + review + commit.
* **Frontend build is committed.** `web/dist` is in git so the product runs without Node; that
  means a UI change requires a rebuild before committing, and the diff includes build output.
* **Playwright is not a product dependency.** The acceptance script needs an external Playwright
  installation; the product itself does not.
* **Hosting is not provided.** The release is verified locally; no deployment is claimed, and no
  paid infrastructure was created.

## 6. Research boundaries preserved

* The frozen SCIENCE studies and research artefacts were not modified. No claim from the research
  programme (predictive signal, early warning, cross-source lead time) is used in the product, and
  the product makes no such claim itself.
