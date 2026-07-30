#!/usr/bin/env python3
"""Generate the LinkedIn crops of the 8 NovaLake series posters.

Same design system and the same per-part highlight as make_posters.py, but at
2400x1256 (1.91:1) — the ratio LinkedIn's link-preview card assumes, so an
unfurled link is not centre-cropped.

The height has to come from somewhere, so the diagram is trimmed to the data
plane: the Unity Catalog container with its six stages and the DLT comparison
branch, kept at full legibility, plus the CI/CD control plane compressed from a
three-box band to a single labelled strip. The DAB orchestration bar is dropped
— it is the one band whose content is already carried by the footer line.

All part metadata (titles, decks, captions, accents, highlight state) is
imported from make_posters.py, so the two sets cannot drift.

Writes  src/linkedin/part-N-<slug>.svg  and  ../../linkedin-poster/part-N-<slug>.png

Usage:  python3 make_linkedin_posters.py      (needs rsvg-convert on PATH)
"""

import pathlib
import subprocess
from xml.sax.saxutils import escape

from make_posters import (
    PARTS, STAGES, box, arrow,
    CREAM, INK, DECK_INK, OFF_STROKE, OFF_INK, FOOTER_INK, SERIES_INK,
    PANEL_STROKE, SANS, MONO, FOOTER,
)

W, H = 1200, 628          # authored size; rendered at 2x -> 2400x1256 (1.91:1)
SCALE = 2


def poster_svg(p):
    a = p["accent"]
    title, deck = p["title"], p["deck"]
    lit, mid = set(p.get("lit", [])), set(p.get("mid", []))
    o = []
    add = o.append

    def state_of(key):
        return "lit" if key in lit else ("mid" if key in mid else "off")

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*SCALE}" height="{H*SCALE}" '
        f'viewBox="0 0 {W} {H}">')
    add(f'<rect width="{W}" height="{H}" fill="{CREAM}"/>')
    add(f'<rect x="0" y="0" width="16" height="{H}" fill="{a}"/>')

    add(f'<text x="1152" y="252" font-family="{SANS}" font-size="200" font-weight="bold" '
        f'fill="{a}" fill-opacity="0.12" text-anchor="end">{p["n"]:02d}</text>')
    add(f'<rect x="1124" y="44" width="26" height="26" fill="{a}"/>')

    add(f'<text x="78" y="68" font-family="{MONO}" font-size="19" font-weight="bold" '
        f'letter-spacing="4" fill="{INK}">NOVALAKE'
        f'<tspan dx="11" fill="{FOOTER_INK}">·</tspan>'
        f'<tspan dx="11" fill="{a}">PART {p["n"]} OF 8</tspan></text>')

    y_title = 130 + (2 - len(title)) * 28
    y = y_title
    for line in title:
        add(f'<text x="78" y="{y}" font-family="{SANS}" font-size="45" font-weight="bold" '
            f'fill="{INK}">{escape(line)}</text>')
        y += 56
    y_rule = y_title + (len(title) - 1) * 56 + 28
    add(f'<rect x="78" y="{y_rule}" width="84" height="5" fill="{a}"/>')
    y = y_rule + 40
    for line in deck:
        add(f'<text x="78" y="{y}" font-family="{SANS}" font-size="20" '
            f'fill="{DECK_INK}">{escape(line)}</text>')
        y += 28

    add(f'<text x="78" y="{y + 10}" font-family="{SANS}" font-size="18" font-weight="bold" '
        f'fill="{a}">{escape(p["cap"])}</text>')

    # ---- architecture, data plane only -------------------------------------
    X0, X1 = 78, 1152
    rail_on = p.get("rail")

    # CI/CD control plane, compressed to one labelled strip
    ry = 336
    add(f'<rect x="{X0}" y="{ry}" width="{X1-X0}" height="28" rx="7" fill="none" '
        f'stroke="{a if rail_on else OFF_STROKE}" stroke-width="1.3" stroke-dasharray="7 5"/>')
    add(f'<text x="{X0+14}" y="{ry+18}" font-family="{MONO}" font-size="10" '
        f'letter-spacing="1.6" fill="{a if rail_on else OFF_INK}">CI/CD CONTROL PLANE'
        f'<tspan dx="8" letter-spacing="0" fill="{a if rail_on else SERIES_INK}">'
        f'· GitHub Actions → scoped service principal → bundle deploy '
        f'· not part of the data flow below</tspan></text>')

    # Unity Catalog container
    uy, uh = 376, 180
    add(f'<rect x="{X0}" y="{uy}" width="{X1-X0}" height="{uh}" rx="10" fill="none" '
        f'stroke="{PANEL_STROKE}" stroke-width="1.3"/>')
    add(f'<text x="{X0+14}" y="{uy+17}" font-family="{SANS}" font-size="10" '
        f'font-style="italic" fill="{SERIES_INK}">'
        f'Unity Catalog · catalog: novalake — governs every table below</text>')

    nw, ngap, ny, nh = 156, 20, uy + 42, 68
    xs = []
    for i, (key, t, subs) in enumerate(STAGES):
        x = X0 + 16 + i * (nw + ngap)
        xs.append(x)
        st = state_of(key)
        add(f'<text x="{x}" y="{ny-8}" font-family="{MONO}" font-size="9.5" '
            f'font-weight="bold" letter-spacing="1.3" '
            f'fill="{a if st != "off" else OFF_INK}">{key}</text>')
        box(add, x, ny, nw, nh, st, a, t, subs, ts=11,
            dashed=bool(p.get("dashed")) and st == "lit")
        if i:
            arrow(add, xs[i-1] + nw + 4, x - 4, ny + nh / 2)

    # DLT comparison branch
    dy = ny + nh + 14
    dx0, dxw = xs[2] - 22, nw * 2 + ngap + 44
    add(f'<path d="M{xs[1]+nw/2},{ny+nh} L{xs[1]+nw/2},{dy+15} L{dx0-6},{dy+15}" fill="none" '
        f'stroke="{a if p.get("dlt") else OFF_STROKE}" stroke-width="1.3" stroke-dasharray="5 4"/>')
    box(add, dx0, dy, dxw, 30, "lit" if p.get("dlt") else "off", a,
        "Lakeflow Declarative Pipelines",
        ["re-implements the Silver transaction slice — comparison only"],
        ts=10.5, ss=8, dashed=True)

    add(f'<text x="78" y="596" font-family="{MONO}" font-size="17" '
        f'fill="{FOOTER_INK}">{escape(FOOTER)}</text>')
    add(f'<text x="1152" y="596" font-family="{MONO}" font-size="15" fill="{SERIES_INK}" '
        f'text-anchor="end">9 tagged releases · solo-built</text>')

    add('</svg>')
    return "\n".join(o)


def main():
    here = pathlib.Path(__file__).resolve().parent
    svg_dir = here / "linkedin"
    svg_dir.mkdir(exist_ok=True)
    out = here.parent.parent / "linkedin-poster"
    out.mkdir(exist_ok=True)
    for p in PARTS:
        stem = f'part-{p["n"]}-{p["slug"]}'
        svg = svg_dir / f"{stem}.svg"
        png = out / f"{stem}.png"
        svg.write_text(poster_svg(p), encoding="utf-8")
        subprocess.run(
            ["rsvg-convert", "-w", str(W * SCALE), "-h", str(H * SCALE),
             "-o", str(png), str(svg)],
            check=True,
        )
        print(f"{png.name}  ({png.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
