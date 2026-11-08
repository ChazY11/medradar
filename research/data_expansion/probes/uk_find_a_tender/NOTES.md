# uk_find_a_tender — probe notes

**Status: VERIFIED_API** · 6 requests · 2026-11-09 · no key, no registration

## What was tested

| # | Request | Result |
|---|---|---|
| 1 | `GET /api/1.0/ocdsReleasePackages?limit=2` | 200, OCDS 1.1 package, 2 releases |
| 2 | `...&stages=award` | 200, `tag: ["award","contract"]`, `awards` present |
| 3 | `...&stages=tender` | 200, `tag: ["tender"]`, no awards |
| 4 | `...&updatedFrom=<7d ago>&updatedTo=<today>` | 200, date window works |
| 5 | `...&keywords=Medtronic` | **400** — no keyword parameter exists |
| 6 | `GET /Search/Results?keywords=Medtronic` (HTML) | 200, 173 KB |

## Why this is the best procurement source in the batch

One release object carries the whole chain with **separate fields and separate
dates**:

```
ocid: ocds-h6vhtk-07b710
tag:  ["award", "contract"]        <- stage marker, not prose
release.date: 2026-11-08T20:14:58Z <- when this release was published
awards[].suppliers[].name: Lumilinks Group Ltd
awards[].suppliers[].id:   GB-FTS-188248   <- an OCDS organisation identifier
contracts[].dateSigned:    2026-10-28T00:00:00Z   <- the contract signature date
contracts[].value:         {amount: 125460.0, currency: GBP}
tender.classification:     {scheme: CPV, id: 72000000}
```

So `source_public_at = release.date` and `event_at = contracts[0].dateSigned`
are genuinely different facts here — the whole point of the four-clock model.

## Honest gaps

* **`awards[].date` was `null`** in every record probed. The award date is not
  usable as `event_at`; `contracts[].dateSigned` is.
* `release.date` is the release's publication/update time. For a re-published
  release it is later than the first public appearance of the `ocid`; a
  first-visibility claim needs the earliest release of that `ocid`.
* No keyword parameter (HTTP 400). Firm-targeted retrieval is only possible via
  the HTML search page or a date-windowed scan, so a connector must walk dates,
  not search names.
* `tender.items` carries CPV + delivery region only — no model, no UDI.

## Docs opened

* <https://standard.open-contracting.org/latest/en/> (200) — the schema this feed implements
* `https://www.find-tender.service.gov.uk/Help/Api` → 404, so the API endpoint URLs above are the evidence

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* samples: `../../../samples/uk_find_a_tender/` (4 files, hash-verified)
