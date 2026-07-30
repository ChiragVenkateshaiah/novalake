#!/usr/bin/env python3
"""Generate the 8 Medium part posters for the NovaLake series.

One design system, eight distinct posters. Palette and typography are sampled
from docs/articles/novalake-architecture.png so the covers and the in-article
diagram read as the same body of work:

    cream ground   #FAF6EC     navy ink       #1B2A4A
    bronze tint    #EDD9B8     silver tint    #E4E8EE
    gold tint      #F5EFC7     serving tint   #D9EDEA
    genai tint     #E6DEEF     muted rule     #8B909B

Each part gets a saturated accent drawn from that same hue family, so the eight
covers are distinguishable in a feed while still obviously one series.

Writes  src/part-N-<slug>.svg  and  ../part-N-<slug>.png  (2400x1260, 1.905:1 —
the OG/LinkedIn standard, and well past Medium's 1192px minimum cover width).

Usage:  python3 make_posters.py          (needs rsvg-convert on PATH)
"""

import pathlib
import subprocess
from xml.sax.saxutils import escape

W, H = 1200, 630          # authored size; rendered at 2x
SCALE = 2

CREAM = "#FAF6EC"
INK = "#1B2A4A"
DECK_INK = "#46536B"
CHIP_OFF_STROKE = "#CFC9B9"
CHIP_OFF_INK = "#9A9486"
FOOTER_INK = "#8B909B"
SERIES_INK = "#A9A395"

SANS = "DejaVu Sans"
MONO = "JetBrains Mono"

FOOTER = "Databricks Free Edition · PySpark · dbt · Unity Catalog · DAB"

PARTS = [
    dict(
        n=1, slug="collaboration-model", accent="#47566E", chip="COLLAB",
        title=["The platform is the", "only source of truth"],
        deck=["A green checkmark that was quietly wrong — and the four-stage",
              "escalation that governed an AI agent's access for nine releases."],
    ),
    dict(
        n=2, slug="bronze", accent="#B07D3A", chip="BRONZE",
        title=["Bronze, and the", "confidently wrong fix"],
        deck=["51 inferred leaf fields, two of them lying — and an audit tool",
              "whose own null filter silently never fired."],
    ),
    dict(
        n=3, slug="silver-gold", accent="#A98A16", chip="SILVER·GOLD",
        title=["Silver and Gold"],
        deck=["Two pipelines describing the same business, deliberately never",
              "unified. Conformance verified per field, not assumed."],
    ),
    dict(
        n=4, slug="serving-cicd", accent="#2E8C80", chip="SERVE·CI",
        title=["Serving and CI/CD"],
        deck=["Guardrails against a model better at SQL than the guardrail —",
              "then a green checkmark that was quietly wrong."],
    ),
    dict(
        n=5, slug="genai", accent="#6B5AA0", chip="GENAI",
        title=["The agent that leaked", "its own system prompt"],
        deck=["The first injection probe anyone would try, run against a careful,",
              "rule-numbered system prompt. It worked."],
    ),
    dict(
        n=6, slug="dlt-vs-dbt", accent="#4F7C52", chip="DLT·SCALE",
        title=["DLT versus dbt, and", "getting to GB scale"],
        deck=["Three negative results and one that mattered — then rewriting",
              "both generators without losing their deliberate defects."],
    ),
    dict(
        n=7, slug="four-experiments", accent="#C2711F", chip="TUNING",
        title=["Four experiments that", "produced numbers"],
        deck=["122,592 duplicated rows, an 86% improvement caused by nothing,",
              "and a result cache that matched on meaning, not text."],
    ),
    dict(
        n=8, slug="what-i-take", accent="#1B2A4A", chip="RESULTS",
        title=["The one that", "didn't resolve"],
        deck=["Clustering quality 0.0, three remediation attempts that didn't",
              "unstick it, and why the failures are the deliverable."],
    ),
]


def poster_svg(p):
    a = p["accent"]
    title, deck = p["title"], p["deck"]
    o = []
    add = o.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*SCALE}" height="{H*SCALE}" '
        f'viewBox="0 0 {W} {H}">')
    add(f'<rect width="{W}" height="{H}" fill="{CREAM}"/>')

    # left accent bar — the strongest series/phase signal at thumbnail size
    add(f'<rect x="0" y="0" width="16" height="{H}" fill="{a}"/>')

    # ghosted part numeral, right — sits clear of even a two-line title
    add(f'<text x="1150" y="330" font-family="{SANS}" font-size="260" font-weight="bold" '
        f'fill="{a}" fill-opacity="0.12" text-anchor="end">{p["n"]:02d}</text>')
    add(f'<rect x="1098" y="66" width="28" height="28" fill="{a}"/>')

    # eyebrow — dx for the separator gaps, since SVG collapses literal whitespace
    add(f'<text x="78" y="92" font-family="{MONO}" font-size="21" font-weight="bold" '
        f'letter-spacing="4.5" fill="{INK}">NOVALAKE'
        f'<tspan dx="12" fill="{FOOTER_INK}">·</tspan>'
        f'<tspan dx="12" fill="{a}">PART {p["n"]} OF 8</tspan></text>')

    # title — one-line titles drop 30px so the block stays balanced against the
    # bottom-anchored chip strip instead of floating high
    y_title = 208 + (2 - len(title)) * 30
    y = y_title
    for line in title:
        add(f'<text x="78" y="{y}" font-family="{SANS}" font-size="54" font-weight="bold" '
            f'fill="{INK}">{escape(line)}</text>')
        y += 68
    y_rule = y_title + (len(title) - 1) * 68 + 40
    add(f'<rect x="78" y="{y_rule}" width="96" height="5" fill="{a}"/>')

    # deck
    y = y_rule + 58
    for line in deck:
        add(f'<text x="78" y="{y}" font-family="{SANS}" font-size="24" '
            f'fill="{DECK_INK}">{escape(line)}</text>')
        y += 38

    # 8-chip progress strip — filled chip position is legible even at 320px
    cx, cy, size, gap = 78, 452, 46, 14
    for i in range(1, 9):
        x = cx + (i - 1) * (size + gap)
        on = i == p["n"]
        if on:
            add(f'<rect x="{x}" y="{cy}" width="{size}" height="{size}" rx="9" fill="{a}"/>')
            add(f'<text x="{x + size/2}" y="{cy + 31}" font-family="{MONO}" font-size="19" '
                f'font-weight="bold" fill="{CREAM}" text-anchor="middle">{i}</text>')
            add(f'<text x="{x + size/2}" y="{cy + size + 30}" font-family="{MONO}" '
                f'font-size="16" font-weight="bold" letter-spacing="2.4" fill="{a}" '
                f'text-anchor="middle">{escape(p["chip"])}</text>')
        else:
            add(f'<rect x="{x}" y="{cy}" width="{size}" height="{size}" rx="9" fill="none" '
                f'stroke="{CHIP_OFF_STROKE}" stroke-width="1.6"/>')
            add(f'<text x="{x + size/2}" y="{cy + 31}" font-family="{MONO}" font-size="19" '
                f'fill="{CHIP_OFF_INK}" text-anchor="middle">{i}</text>')

    # footer
    add(f'<text x="78" y="592" font-family="{MONO}" font-size="19" '
        f'fill="{FOOTER_INK}">{escape(FOOTER)}</text>')
    add(f'<text x="1126" y="592" font-family="{MONO}" font-size="17" fill="{SERIES_INK}" '
        f'text-anchor="end">9 tagged releases · solo-built</text>')

    add('</svg>')
    return "\n".join(o)


def main():
    here = pathlib.Path(__file__).resolve().parent
    out = here.parent
    for p in PARTS:
        stem = f'part-{p["n"]}-{p["slug"]}'
        svg = here / f"{stem}.svg"
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
