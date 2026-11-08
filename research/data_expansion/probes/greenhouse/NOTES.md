# greenhouse — probe notes

**Status: VERIFIED_API** (the endpoint works) · **negative result for all five firms** · 6 requests · 2026-11-09

## What was tested

`GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=false`

| token | result |
|---|---|
| `stripe` (**control**) | **200**, 766 live jobs |
| `medtronic` | 404 |
| `gehealthcare` | 404 |
| `philips` | 404 |
| `draeger` | 404 |
| `mindray` | 404 |

## How to read the 404s

The control row is what makes the negative result usable: the same endpoint, in
the same run, returned 766 real jobs for a token that exists. So the five 404s
mean **"no such board under this token"**, not "API broken" and not "no hiring
data exists anywhere".

The correct claim is:

> None of Medtronic / GE HealthCare / Philips / Dräger / Mindray publishes a
> public Greenhouse job board under its likely token.

Token guessing was capped at 6 requests and must not be extended into
enumeration — that would be an access strategy the protocol forbids.

## What the payload does give (from the control board)

```
id, internal_job_id, requisition_id        <- stable posting identity
first_published: 2026-09-03T13:30:34-04:00 <- the publication clock
updated_at:      2026-10-29T10:42:09-04:00 <- last edit, NOT publication
location.name, title, absolute_url
metadata: null on every probed posting     <- no department/function field
```

Two consequences for the hiring contract:

1. `first_published` is the correct `source_public_at`; `first_observed_at` is the
   fetch clock and must stay separate.
2. **R&D vs Sales vs Production cannot be split from Greenhouse structured
   fields** — there is no department field, only the title string. Any such split
   is a text heuristic and must be labelled as one.

## Docs opened

* <https://developers.greenhouse.io/job-board.html> (200)

## Artifacts

* `requests.jsonl`, `PROBE_RESULT.json`
* samples: `../../../samples/greenhouse/` (control board, hash-verified)
* five-firm summary: `../../samples/procurement/FIVE_FIRM_PROBE.json`
