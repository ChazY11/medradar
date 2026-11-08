# lever — probe notes

**Status: VERIFIED_API** (the endpoint works) · **negative result for all five firms** · 6 requests · 2026-11-09

## What was tested

`GET https://api.lever.co/v0/postings/<company>?mode=json`

| token | result |
|---|---|
| `leverdemo` (**control**) | **200**, 10 postings |
| `medtronic` | 404 |
| `gehealthcare` | 404 |
| `philips` | 404 |
| `draeger` | 404 |
| `mindray` | 404 |

Same logic as the Greenhouse probe: the control proves the endpoint works, so the
five 404s are "no such board", not a network failure.

## Payload facts (from the control board)

```
id:        uuid
text:      "Customer Success Manager"
createdAt: 1788199939703          <- epoch MILLISECONDS
categories: {commitment, department, location, team, allLocations}
```

* `createdAt/1000` → `2026-08-31T18:12:19Z`. A naive parser treats the raw value
  as seconds and gets a 1970 date — the connector must handle this explicitly.
* `categories.department` **was populated for some postings and `null` for
  others** (observed: `Sales`, `Finance`, `People (HR)`, `Business Development`,
  `Customer Success`, `Executive`, and `None`). So a role-mix split is possible
  only where the employer filled it in — the coverage rate has to be measured,
  never assumed.
* No `updatedAt` in the postings payload: an edit is indistinguishable from a new
  posting, so `createdAt` is the only defensible clock.

## Docs opened

* <https://github.com/lever/postings-api> (200)

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* samples: `../../../samples/lever/` (control postings, hash-verified)
* five-firm summary: `../../samples/procurement/FIVE_FIRM_PROBE.json`
