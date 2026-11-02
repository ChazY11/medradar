# Cycle 39 — the render-only defect class becomes a static check (2026-11-03)

**Status:** completed. Closes B-072. Decision: D-070.
Artifacts: `papers/check_layout.py`, `tests/test_check_layout.py` (7 tests), `tools/round_end.py` (10 steps).

## The defect class this closes

Four times a figure passed `verify_figures.py` and still shipped with a legibility defect visible only when rendered:
clipped labels (fig3), an annotation off-frame (fig2), and last cycle a legend covering two column headings, decision
ids printed over event labels, and a legend running off the canvas (fig5). The verifier checks **correctness** — valid
XML, finite coordinates, values re-derived from source — and correctness is not legibility.

## What the checker does

`papers/check_layout.py` performs two mechanical checks without a browser:

1. **Text outside the canvas** — each `<text>` box estimated from anchor, font size and character count must lie
   inside the viewBox. Rotated axis labels are measured **vertically**, because measuring them horizontally produces
   false alarms on every figure with a y-axis title.
2. **Text painted over by a later shape** — a non-background `<rect>`/`<circle>` drawn after a text element that
   intersects its box hides at least part of that text. This is exactly the fig5 defect class.

## Proven against injected defects, not just clean figures

A temporary SVG with a heading past the right edge and a filled rectangle painted over two headings produced both
expected reports:

```
CAUGHT: text 'column heading one' is painted over by a later shape
CAUGHT: text 'a heading that runs well past the right ' extends outside the canvas (120..340 of 0..200)
```

Seven unit tests cover: clean figure, missing viewBox, off-canvas text, painted-over text, a **background** shape over
text (must not fire), a rotated label that fits, a rotated label that does not, plus one asserting the committed
figures are clean so the check cannot silently rot.

## Calibration, stated because it is an approximation

The character-width ratio is 0.50, set after 0.56 produced three false alarms (two rotated axis labels measured
horizontally, one caption ~8 % too wide). The estimate errs toward over-width, so a clean pass is meaningful while a
failure deserves a glance at the figure.

## Gate

`tools/round_end.py` now runs **10 steps**, adding `layout checks: 5 figures; problems: 0`.

## Not claimed

That the checker replaces a rendered review. It catches two mechanical classes and nothing else: contrast,
text-on-text overlap, and other SVG features remain the render's job. The lesson is that the mechanical part is now
automatic — not that the manual part is unnecessary.

## Next

1. Reclassify backlog items whose data is structurally unavailable as **blocked**, with the evidence recorded.
2. Mature the prospective forecast set when the lane advances (earliest 2026-Q4).
3. Schedule a rendered review before any submission (contrast and text-on-text overlap).
