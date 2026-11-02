"""Static layout checks for the paper figures: catches what the SVG validator cannot.

`verify_figures.py` proves a figure is *correct*: valid XML, finite coordinates, values re-derived from the source
artifact. It cannot see that a legend was painted over two column headings, or that a label runs off the canvas —
both defects that shipped in a draft and were caught only by rendering the SVG in a browser (fourth occurrence,
D-069). This checker covers the two mechanical classes without needing a browser:

  1. **Text outside the canvas.** Every <text> box is estimated from its anchor, font size and character count and
     must lie inside the viewBox.
  2. **Text painted over by a filled shape.** If a non-background <rect> or <circle> is drawn *after* a text element
     and its box intersects the text box, the text is (partly) hidden.

It is an approximation by design: text width is estimated, not measured. It reports what it finds and exits non-zero
so a figure with an off-canvas label or a covered heading cannot pass the round-end gate.

    python papers/check_layout.py
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

FIGURES = Path("papers/figures")
SVG_NS = "{http://www.w3.org/2000/svg}"
CHAR_WIDTH_RATIO = 0.50      # Helvetica/Arial average advance as a fraction of font size


def _number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def text_box(element: ElementTree.Element) -> tuple[float, float, float, float] | None:
    content = "".join(element.itertext()).strip()
    if not content:
        return None
    x = _number(element.get("x"))
    y = _number(element.get("y"))
    size = _number(element.get("font-size"), 10.0)
    width = len(content) * size * CHAR_WIDTH_RATIO
    anchor = (element.get("text-anchor") or "start").strip()
    left = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
    box = (left, y - size, left + width, y + size * 0.28)
    transform = (element.get("transform") or "").lower()
    if "rotate" in transform:
        # a rotated axis label runs vertically around its anchor: swap the box extents
        if anchor == "middle":
            return (x - size * 0.5, y - width / 2, x + size * 0.5, y + width / 2)
        return (x - size, y - width, x + size * 0.28, y)
    return box


def shape_box(element: ElementTree.Element) -> tuple[float, float, float, float] | None:
    tag = element.tag.replace(SVG_NS, "")
    if tag == "rect":
        fill = (element.get("fill") or "").strip().lower()
        if fill in ("#ffffff", "#fff", "white", "none", ""):
            return None
        x = _number(element.get("x"))
        y = _number(element.get("y"))
        width = _number(element.get("width"))
        height = _number(element.get("height"))
        return x, y, x + width, y + height
    if tag == "circle":
        fill = (element.get("fill") or "").strip().lower()
        if fill in ("#ffffff", "#fff", "white", "none", ""):
            return None
        cx = _number(element.get("cx"))
        cy = _number(element.get("cy"))
        radius = _number(element.get("r"), 3.0)
        return cx - radius, cy - radius, cx + radius, cy + radius
    return None


def intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float],
               tolerance: float = 1.0) -> bool:
    return not (a[2] - tolerance <= b[0] or b[2] - tolerance <= a[0]
                or a[3] - tolerance <= b[1] or b[3] - tolerance <= a[1])


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        tree = ElementTree.parse(path)
    except ElementTree.ParseError as error:
        return [f"{path.name}: not valid XML ({error})"]
    root = tree.getroot()
    view = (root.get("viewBox") or "").split()
    if len(view) != 4:
        return [f"{path.name}: missing viewBox"]
    min_x, min_y, width, height = (float(value) for value in view)
    max_x, max_y = min_x + width, min_y + height

    ordered = list(root.iter())
    for index, element in enumerate(ordered):
        if element.tag.replace(SVG_NS, "") != "text":
            continue
        box = text_box(element)
        if box is None:
            continue
        content = "".join(element.itertext()).strip()
        if box[0] < min_x - 0.5 or box[2] > max_x + 0.5 or box[1] < min_y - 0.5 or box[3] > max_y + 0.5:
            problems.append(f"{path.name}: text {content[:40]!r} extends outside the canvas "
                            f"({box[0]:.0f}..{box[2]:.0f} of {min_x:.0f}..{max_x:.0f}, "
                            f"{box[1]:.0f}..{box[3]:.0f} of {min_y:.0f}..{max_y:.0f})")
        for later in ordered[index + 1:]:
            shape = shape_box(later)
            if shape is None:
                continue
            if intersects(box, shape):
                problems.append(f"{path.name}: text {content[:40]!r} is painted over by a later shape")
                break
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(FIGURES))
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    paths = sorted(directory.glob("*.svg"))
    if not paths:
        print(f"no SVG files in {directory}")
        return 1
    failures = 0
    for path in paths:
        problems = check(path)
        failures += len(problems)
        status = "OK" if not problems else f"{len(problems)} problem(s)"
        print(f"{path.name}: {status}")
        for problem in problems:
            print(f"  - {problem}")
    print(f"\nlayout checks: {len(paths)} figures; problems: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
