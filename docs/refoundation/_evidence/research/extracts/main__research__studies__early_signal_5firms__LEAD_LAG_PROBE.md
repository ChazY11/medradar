# LEAD/LAG PROBE — can trials be paired to later regulatory events?

Window 2018-01-01 … 2025-12-31. Protocol frozen first in `PHASE1_PROTOCOL.md`.

## Verdict (frozen G1 criteria: ≥10 eligible pairs, ≥2 firms)

**G1 = NO-GO: best scope S2 yields 3 eligible pairs across 2 firms, below the frozen floor of 10 pairs / 2 firms**

## S1 primary — trials on device tracks

| firm | track | trials | regulatory events | eligible pairs (lag 0 / 30 / 60 / 90 d) |
|---|---|---:|---:|---|
| medtronic | imaging_us | 0 | 0 | 0 / 0 / 0 / 0 |
| medtronic | respiratory | 0 | 5 | 0 / 0 / 0 / 0 |
| ge_healthcare | imaging_us | 0 | 75 | 0 / 0 / 0 / 0 |
| ge_healthcare | respiratory | 0 | 2 | 0 / 0 / 0 / 0 |
| philips | imaging_us | 0 | 35 | 0 / 0 / 0 / 0 |
| philips | respiratory | 0 | 1 | 0 / 0 / 0 / 0 |
| mindray | imaging_us | 0 | 47 | 0 / 0 / 0 / 0 |
| mindray | respiratory | 0 | 6 | 0 / 0 / 0 / 0 |
| draeger | imaging_us | 0 | 0 | 0 / 0 / 0 / 0 |
| draeger | respiratory | 0 | 5 | 0 / 0 / 0 / 0 |

## S2 sensitivity — assumed crosswalk `t_respiratory` → `respiratory`

> Assumed mapping (id-identical after the `t_` prefix). Never pooled with S1.

| firm | scope | trials | regulatory events | eligible pairs (0/30/60/90 d) |
|---|---|---:|---:|---|
| medtronic | t_respiratory->respiratory | 1 | 5 | 1 / 1 / 1 / 1 |
| ge_healthcare | t_respiratory->respiratory | 0 | 2 | 0 / 0 / 0 / 0 |
| philips | t_respiratory->respiratory | 2 | 1 | 2 / 2 / 2 / 2 |
| mindray | t_respiratory->respiratory | 0 | 6 | 0 / 0 / 0 / 0 |
| draeger | t_respiratory->respiratory | 0 | 5 | 0 / 0 / 0 / 0 |

## S3 descriptive — firm level (any trial → next regulatory event)

| firm | trials | regulatory events | eligible pairs (0/30/60/90 d) |
|---|---:|---:|---|
| medtronic | 113 | 4947 | 0 / 0 / 0 / 0 |
| ge_healthcare | 35 | 229 | 0 / 0 / 0 / 0 |
| philips | 59 | 271 | 0 / 0 / 0 / 0 |
| mindray | 0 | 69 | 0 / 0 / 0 / 0 |
| draeger | 0 | 7 | 0 / 0 / 0 / 0 |

## SEC 8-K (no track attribution; descriptive only)

| firm | records | regulatory events | eligible pairs (0/30/60/90 d) |
|---|---:|---:|---|
| medtronic | 5 | 4947 | 0 / 0 / 0 / 0 |
| ge_healthcare | 4 | 229 | 0 / 0 / 0 / 0 |
| philips | 0 | 271 | 0 / 0 / 0 / 0 |
| mindray | 0 | 69 | 0 / 0 / 0 / 0 |
| draeger | 0 | 7 | 0 / 0 / 0 / 0 |

## Notes

- a pair requires the later event to be strictly after the earlier record's availability
- only the first later event per earlier record counts; skipped multiplicity is reported
- pairs with lead < 2 quarters are counted separately as below-threshold, not silently dropped
- S2 uses an assumed crosswalk and must never be pooled with S1
- no detection model is involved: this probe measures whether pairing is possible at all
