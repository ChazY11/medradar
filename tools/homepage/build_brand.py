#!/usr/bin/env python3
"""Generate the MedRadar brand assets (deterministic, stdlib only).

Outputs
-------
    docs/assets/brand/mark.svg          square radar mark, currentColor-friendly
    docs/assets/brand/favicon.svg       navy rounded tile for browsers
    docs/assets/brand/banner-dark.svg   1600 x 1000 README / social banner (SVG source)
    docs/assets/badges/*.svg            offline status badges (no shields.io)

The banner is rasterised to ``banner-dark.png`` by ``tools/homepage/render_banner.py``
because GitHub renders <img> PNG more predictably than a large SVG banner.

Run:  python tools/homepage/build_brand.py [--check]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "docs" / "assets" / "brand"
BADGES = ROOT / "docs" / "assets" / "badges"

INK = "#0B1220"
ICE = "#6FB6E8"
ACCENT = "#2B7FC4"
MUTED = "#7D92AA"
DARK_INK = "#E8F0F8"
DARK_INK_2 = "#B9CBDE"
NAVY = "#081120"

FONT = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


# --------------------------------------------------------------------------- mark
def mark_svg(size: int = 32) -> str:
    """Concentric radar: outer ring, two quarter arcs, sweep line, origin dot."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 32 32" role="img" aria-label="MedRadar mark">
<title>MedRadar mark</title>
<g fill="none" stroke="#2B7FC4" stroke-width="1.5" stroke-linecap="round">
<circle cx="16" cy="16" r="12.5" stroke-opacity=".55"/>
<path d="M16 3.5 A12.5 12.5 0 0 1 28.5 16" stroke-opacity=".95"/>
<circle cx="16" cy="16" r="7.4" stroke-opacity=".30"/>
<path d="M16 8.6 A7.4 7.4 0 0 0 8.6 16" stroke-opacity=".80"/>
</g>
<path d="M16 16 L26.6 5.9" stroke="#2B7FC4" stroke-width="1.4" stroke-linecap="round" stroke-opacity=".45"/>
<circle cx="16" cy="16" r="2.3" fill="#2B7FC4"/>
<circle cx="25.1" cy="6.9" r="2.1" fill="#6FB6E8"/>
</svg>
"""


def mark_dark_svg(size: int = 32) -> str:
    """Mark tuned for dark surfaces (navy footer, dark hero)."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 32 32" role="img" aria-label="MedRadar mark">
<title>MedRadar mark</title>
<g fill="none" stroke="#6FB6E8" stroke-width="1.5" stroke-linecap="round">
<circle cx="16" cy="16" r="12.5" stroke-opacity=".45"/>
<path d="M16 3.5 A12.5 12.5 0 0 1 28.5 16" stroke-opacity=".95"/>
<circle cx="16" cy="16" r="7.4" stroke-opacity=".28"/>
<path d="M16 8.6 A7.4 7.4 0 0 0 8.6 16" stroke-opacity=".80"/>
</g>
<path d="M16 16 L26.6 5.9" stroke="#6FB6E8" stroke-width="1.4" stroke-linecap="round" stroke-opacity=".45"/>
<circle cx="16" cy="16" r="2.3" fill="#6FB6E8"/>
<circle cx="25.1" cy="6.9" r="2.1" fill="#9BD0F2"/>
</svg>
"""


def favicon_svg() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" role="img" aria-label="MedRadar">
<title>MedRadar</title>
<rect width="32" height="32" rx="7.5" fill="#0B1730"/>
<g fill="none" stroke="#6FB6E8" stroke-width="1.6" stroke-linecap="round">
<circle cx="16" cy="16" r="10.2" stroke-opacity=".45"/>
<path d="M16 5.8 A10.2 10.2 0 0 1 26.2 16" stroke-opacity="1"/>
<circle cx="16" cy="16" r="5.6" stroke-opacity=".30"/>
</g>
<path d="M16 16 L24.4 7.9" stroke="#6FB6E8" stroke-width="1.5" stroke-linecap="round" stroke-opacity=".55"/>
<circle cx="16" cy="16" r="2.2" fill="#9BD0F2"/>
</svg>
"""


# --------------------------------------------------------------------------- banner
def banner_svg() -> str:
    nodes = [
        # (cx, cy, r, fill, opacity)
        (1188, 352, 4.2, ICE, 0.95),
        (1310, 300, 3.0, ACCENT, 0.85),
        (1402, 402, 4.6, ICE, 0.9),
        (1256, 452, 2.6, ICE, 0.7),
        (1350, 540, 3.6, ACCENT, 0.9),
        (1448, 318, 2.4, ICE, 0.6),
        (1128, 470, 3.4, ICE, 0.8),
        (1210, 590, 2.8, ACCENT, 0.75),
        (1440, 596, 3.2, ICE, 0.85),
        (1020, 388, 2.6, ACCENT, 0.7),
        (1372, 218, 2.4, ICE, 0.55),
        (1494, 486, 2.6, ICE, 0.6),
        (1156, 262, 2.2, ACCENT, 0.6),
        (1268, 640, 2.2, ICE, 0.5),
    ]
    edges = [
        (0, 1), (0, 3), (0, 6), (1, 2), (1, 11), (2, 4), (2, 11),
        (3, 4), (3, 8), (4, 12), (5, 2), (6, 7), (7, 8), (8, 11),
        (9, 6), (10, 1), (12, 0), (13, 7),
    ]
    parts: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000" '
        'role="img" aria-label="MedRadar: public evidence research on medical technology change">',
        "<title>MedRadar — public evidence research on medical technology change</title>",
        "<desc>Dark navy cover with a radar and evidence-graph motif, the MedRadar wordmark, "
        "the research positioning, and the 2026-10-31 data snapshot.</desc>",
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        f'<stop offset="0" stop-color="#0A1526"/><stop offset="1" stop-color="#060C16"/>',
        "</linearGradient>",
        '<radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">',
        '<stop offset="0" stop-color="#6FB6E8" stop-opacity=".16"/>',
        '<stop offset="0.55" stop-color="#6FB6E8" stop-opacity=".05"/>',
        '<stop offset="1" stop-color="#6FB6E8" stop-opacity="0"/>',
        "</radialGradient>",
        '<linearGradient id="sweep" x1="0" y1="1" x2="1" y2="0">',
        '<stop offset="0" stop-color="#6FB6E8" stop-opacity="0"/>',
        '<stop offset="1" stop-color="#9BD0F2" stop-opacity=".55"/>',
        "</linearGradient>",
        '<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">',
        '<path d="M40 0H0V40" fill="none" stroke="#6FB6E8" stroke-opacity=".045" stroke-width="1"/>',
        "</pattern>",
        "</defs>",
        '<rect width="1600" height="1000" fill="url(#bg)"/>',
        '<rect width="1600" height="1000" fill="url(#grid)"/>',
        '<rect width="1600" height="1000" fill="url(#glow)" transform="translate(300 60) scale(1.55)"/>',
    ]

    # left: brand block
    parts += [
        '<g transform="translate(112 152) scale(1.35)" fill="none" stroke="#6FB6E8" stroke-linecap="round">',
        '<circle cx="16" cy="16" r="12.5" stroke-width="1.5" stroke-opacity=".55"/>',
        '<path d="M16 3.5 A12.5 12.5 0 0 1 28.5 16" stroke-width="1.8" stroke-opacity=".95"/>',
        '<circle cx="16" cy="16" r="7.4" stroke-width="1.5" stroke-opacity=".30"/>',
        '<path d="M16 8.6 A7.4 7.4 0 0 0 8.6 16" stroke-width="1.6" stroke-opacity=".80"/>',
        '<path d="M16 16 L26.6 5.9" stroke-width="1.5" stroke-opacity=".45"/>',
        '<circle cx="16" cy="16" r="2.4" fill="#6FB6E8" stroke="none"/>',
        '<circle cx="25.1" cy="6.9" r="2.2" fill="#9BD0F2" stroke="none"/>',
        "</g>",
        f'<text x="112" y="266" font-family="{MONO}" font-size="14" letter-spacing="3.6" fill="{ICE}" fill-opacity=".85">OPEN RESEARCH PLATFORM</text>',
        f'<text x="110" y="372" font-family="{FONT}" font-size="82" font-weight="700" letter-spacing="-2.2" fill="{DARK_INK}">MedRadar</text>',
        f'<line x1="112" y1="412" x2="252" y2="412" stroke="{DARK_INK}" stroke-opacity=".28" stroke-width="1"/>',
        f'<text x="110" y="478" font-family="{FONT}" font-size="33" fill="{DARK_INK_2}">Public evidence research on</text>',
        f'<text x="110" y="526" font-family="{FONT}" font-size="33" font-weight="600" fill="{DARK_INK}">medical technology change.</text>',
        f'<text x="112" y="590" font-family="{MONO}" font-size="15" fill="{MUTED}">Regulatory \u00b7 Clinical trials \u00b7 Corporate filings</text>',
        # editorial line: the project's own thesis, straight from the README
        '<rect x="112" y="672" width="2" height="58" fill="#6FB6E8" fill-opacity=".45"/>',
        f'<text x="132" y="697" font-family="{FONT}" font-size="20" font-style="italic" fill="{DARK_INK_2}" fill-opacity=".92">The engineering and the negative results</text>',
        f'<text x="132" y="723" font-family="{FONT}" font-size="20" font-style="italic" fill="{DARK_INK_2}" fill-opacity=".92">are the deliverable.</text>',
    ]

    # right: radar + evidence graph
    cx, cy = 1298, 456
    parts.append('<g>')
    for radius, opacity in ((62, 0.16), (124, 0.13), (188, 0.10), (252, 0.075), (318, 0.055)):
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{ICE}" '
            f'stroke-opacity="{opacity}" stroke-width="1"/>'
        )
    # quarter-arc highlights
    for radius in (124, 252):
        parts.append(
            f'<path d="M {cx} {cy - radius} A {radius} {radius} 0 0 1 {cx + radius} {cy}" '
            f'fill="none" stroke="{ICE}" stroke-opacity=".20" stroke-width="1.2"/>'
        )
    # sweep wedge
    parts.append(
        f'<path d="M {cx} {cy} L {cx + 318 * 0.87:.1f} {cy - 318 * 0.49:.1f} '
        f'A 318 318 0 0 1 {cx + 318 * 0.95:.1f} {cy - 318 * 0.31:.1f} Z" '
        f'fill="{ICE}" fill-opacity=".035"/>'
    )
    parts.append(
        f'<line x1="{cx}" y1="{cy}" x2="{cx + 330 * 0.87:.1f}" y2="{cy - 330 * 0.49:.1f}" '
        f'stroke="url(#sweep)" stroke-width="1.4"/>'
    )
    # graph edges
    for a, b in edges:
        ax, ay, _, _, _ = nodes[a]
        bx, by, _, _, _ = nodes[b]
        parts.append(
            f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" stroke="{ICE}" stroke-opacity=".13" stroke-width="1"/>'
        )
    # nodes
    for nx, ny, r, fill, opacity in nodes:
        parts.append(f'<circle cx="{nx}" cy="{ny}" r="{r}" fill="{fill}" fill-opacity="{opacity}"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="5.4" fill="{ICE}"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="11" fill="none" stroke="{ICE}" stroke-opacity=".35"/>')
    parts.append("</g>")

    # right: timeline
    ty = 800
    x0, x1 = 1010, 1490
    ticks = [(1966, "1966"), (1980, "1980"), (1995, "1995"), (2010, "2010"), (2020, "2020"), (2026, "2026")]
    def tx(year: int) -> float:
        return x0 + (year - 1966) / (2026 - 1966) * (x1 - x0)

    parts.append(f'<line x1="{x0}" y1="{ty}" x2="{x1}" y2="{ty}" stroke="{ICE}" stroke-opacity=".22"/>')
    parts.append(
        f'<line x1="{tx(2015):.1f}" y1="{ty}" x2="{tx(2026):.1f}" y2="{ty}" stroke="{ICE}" '
        f'stroke-opacity=".7" stroke-width="2"/>'
    )
    for year, label in ticks:
        x = tx(year)
        parts.append(f'<line x1="{x:.1f}" y1="{ty - 5}" x2="{x:.1f}" y2="{ty + 5}" stroke="{ICE}" stroke-opacity=".45"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{ty + 26}" font-family="{MONO}" font-size="12" fill="{MUTED}" '
            f'text-anchor="middle">{label}</text>'
        )
    parts.append(
        f'<text x="{x1}" y="{ty - 24}" font-family="{MONO}" font-size="12" fill="{ICE}" '
        f'fill-opacity=".7" text-anchor="end">EVENT-TIME AXIS</text>'
    )

    # stat strip
    parts += [
        f'<line x1="112" y1="836" x2="1488" y2="836" stroke="{DARK_INK}" stroke-opacity=".10"/>',
        f'<text x="112" y="890" font-family="{MONO}" font-size="17" fill="{DARK_INK}">375,378 events</text>',
        f'<text x="290" y="890" font-family="{MONO}" font-size="17" fill="{MUTED}">'
        f'\u00b7 6 public sources \u00b7 1966\u20132026 \u00b7 snapshot 2026-10-31</text>',
        f'<text x="1488" y="890" font-family="{MONO}" font-size="13" fill="{MUTED}" text-anchor="end">'
        f'research infrastructure, not a predictive product</text>',
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- badges
def badge(label: str, value: str) -> str:
    size = 11.0
    label_w = max(46.0, 12 + _w(label, size) + 12)
    value_w = max(40.0, 12 + _w(value, size) + 12)
    total = label_w + value_w
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total:.0f}" height="22" viewBox="0 0 {total:.0f} 22" role="img" aria-label="{label}: {value}">
<title>{label}: {value}</title>
<rect width="{total:.0f}" height="22" rx="4" fill="#FFFFFF" stroke="#E1E7F0"/>
<rect x="0" y="0" width="3" height="22" rx="1.5" fill="#2B7FC4"/>
<text x="12" y="15" font-family="{FONT}" font-size="11" fill="#64748B">{label}</text>
<text x="{label_w:.0f}" y="15" font-family="{MONO}" font-size="11" font-weight="600" fill="#0B1220">{value}</text>
</svg>
"""


def _w(text: str, size: float) -> float:
    total = 0.0
    for ch in text:
        if ch in "iljtfr.,:;'()|! ":
            total += size * 0.30
        elif ch.isupper() or ch.isdigit():
            total += size * 0.62
        elif ch == "\u2013":
            total += size * 0.55
        else:
            total += size * 0.52
    return total


BADGE_SPECS = {
    "version": ("version", "0.5.0"),
    "tests": ("tests", "1,157 passing"),
    "data": ("data snapshot", "375,378 events"),
    "python": ("python", "3.10\u20133.12"),
    "license": ("licence", "MIT"),
}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    files: dict[Path, str] = {
        BRAND / "mark.svg": mark_svg(),
        BRAND / "mark-dark.svg": mark_dark_svg(),
        BRAND / "favicon.svg": favicon_svg(),
        BRAND / "banner-dark.svg": banner_svg(),
    }
    for name, (label, value) in BADGE_SPECS.items():
        files[BADGES / f"{name}.svg"] = badge(label, value)

    stale: list[str] = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)} ({len(content):,} chars)")
    if check and stale:
        print("stale brand assets:", *stale, sep="\n  ")
        return 1
    if check:
        print("brand assets are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
