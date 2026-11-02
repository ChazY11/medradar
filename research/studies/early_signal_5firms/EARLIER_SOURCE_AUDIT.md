# EARLIER SOURCE AUDIT — can anything precede a regulatory event here?

Window 2018-01-01 … 2025-12-31. Produced by `experiments/b084/earlier_source_audit.py`.

## Verdict

**NOT_EVALUABLE for lead-time pairing on the confirmatory tracks: the trial lane assigns therapy-area ids (t_*) and only two of them have an id-identical device counterpart, so a defensible crosswalk does not exist; 8-K carries no technology track and occurs ~5 times per firm in the window**

## Clinical trials (ctgov), resolvable by company_key

| firm | trials in window | with a track id | tracks used |
|---|---:|---:|---|
| medtronic | 113 | 51 | t_cardiometabolic:42, t_oncology:3, t_urology:2, t_womens_health:1 |
| ge_healthcare | 35 | 11 | t_oncology:6, t_neuroscience:3, t_womens_health:2 |
| philips | 59 | 10 | t_hepatology:3, t_womens_health:2, t_respiratory:2, t_neuroscience:1 |
| mindray | 0 | 0 | — |
| draeger | 0 | 0 | — |

## SEC 8-K

| firm | in window | tracks |
|---|---:|---|
| medtronic | 5 | None:5 |
| ge_healthcare | 4 | None:4 |
| philips | 0 | none assigned |
| mindray | 0 | none assigned |
| draeger | 0 | none assigned |

## Taxonomy

Store has 60 tracks: 38 device tracks and 22 therapy-area tracks (`t_*`).

Candidate crosswalks (identical id after the `t_` prefix — a candidate, not a mapping):

- `t_respiratory` → `respiratory` (Respiratory / Respiratory & Anesthesia)
- `t_ophthalmology` → `ophthalmology` (Ophthalmology / Ophthalmology)
- `t_urology` → `urology` (Urology / Urology)
- `t_womens_health` → `womens_health` (Women's Health / Women's Health)

## Consequences

- pairing trials to the study's device tracks requires a therapy-area -> device crosswalk that the store does not contain; inventing one after seeing outcomes would be a pre-registration violation
- 8-K is too sparse and trackless to support cell-level lead-time measurement
- the only defensible earlier-source pairing available today is at the *firm* level, not the firm-track level; that supports RQ3 weakly and RQ4 not at all

## Trials on the two confirmatory device tracks

| firm | imaging_us | respiratory |
|---|---:|---:|
| medtronic | 0 | 0 |
| ge_healthcare | 0 | 0 |
| philips | 0 | 0 |
| mindray | 0 | 0 |
| draeger | 0 | 0 |
