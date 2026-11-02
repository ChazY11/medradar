# Cycle 18 — paper figures as dependency-free SVG, verified and visually checked (2026-11-03)

**Status:** completed. Creates and closes B-053. Decision: D-039.
Artifacts: `papers/figures.py`, `papers/figures/*.svg` (4), `papers/figures/figures_data.json`,
`papers/verify_figures.py`.

## Why hand-written SVG

The repository is stdlib-only (`dependencies = []`) and matplotlib is not installed. Rather than add a
plotting dependency for four plates, the generator emits SVG directly: deterministic, text-diffable, and
its plotted values can be re-derived and compared.

## The four plates

| figure | source artifact | points | what it shows |
|---|---|---:|---|
| `fig1_frontier.svg` | `experiments/detect_v1/benchmark.json` | 16 | sensitivity vs achieved false-alarm rate, four detectors, clustered CIs — a frontier, not a ranking |
| `fig2_calibration.svg` | `experiments/b027/momentum_calibration.json` | 50 | rate ratio vs exact p-value; grey markers pass the 1.25 rule but not the test |
| `fig3_rolling_origin.svg` | `experiments/b050/rolling_origin.json` | 12 | rolling-origin lift with clustered CIs; every interval crosses 1 |
| `fig4_verdict_stability.svg` | `experiments/b027/verdict_stability.json` | 53 | verdict per company across four as-of dates; 2 marked reversed |

## Verification

`papers/verify_figures.py` checks three things per plate: the values in `figures_data.json` match a
re-derivation from the source artifact (exact match, not approximate), the SVG parses as XML with real
drawn content, and the paper links the file. Also rejects numeric artefacts (NaN/inf/None as standalone
tokens — as substrings they occur in ordinary words such as "information", which the first version
wrongly flagged).

**Result: 4 figures, 131 plotted points, 0 failures.**

## What structural checks could not catch

SVG validity is not readability. Each plate was rendered to PNG with headless Edge and inspected, which
found three defects no check would have reported:

1. **Figure 3** — predictor labels were drawn outside the canvas and clipped; fixed with a per-figure
   left margin and flag counts inside the label.
2. **Figure 2** — the rightmost annotation (Olympus, 4.17×) ran off the frame; fixed with
   edge-aware label anchoring.
3. **Figure 4** — the matrix had no company labels at all; fixed with sparse row labels and explicit
   "reversed" markers.

All three were fixed, the plates regenerated, and the renders re-inspected.

## Effect on the paper

D-038 listed "no figures" as the only blocking readability gap. It is closed. The paper's Section 4.8 now
references each plate, and the reproduction block includes the generator and verifier.

## What is not claimed

The figures add no evidence; they re-present committed numbers. Their value is that a reader can see the
frontier's shape and the calibration gap without reading seventeen result files.

## Next

1. **B-026** spike vs sustained level-shift classifier — the last P1 modelling task that needs no new data.
2. **B-039** deployment-resolution fix.
3. Add a per-finding reproduction index to the paper's retraction table.
