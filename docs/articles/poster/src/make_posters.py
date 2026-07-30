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

# The six data-plane stages, drawn on every poster. The highlight advances
# left-to-right across the series so the strip carries the story: a reader who
# sees part 6 knows at a glance which layer it touches and what came before.
STAGES = ["SOURCES", "BRONZE", "SILVER", "GOLD", "SERVING", "GENAI"]

# Per-part highlight state:
#   lit    — stages this part actually builds or measures (solid accent)
#   mid    — stages shown as context, outlined in accent rather than filled
#   rail   — light the CI/CD control plane above the data plane
#   dashed — mark a lit stage as a parallel/comparison implementation
#   cap    — one line saying what the highlighted slice does in this part

PARTS = [
    dict(
        n=1, slug="collaboration-model", accent="#47566E",
        title=["The platform is the", "only source of truth"],
        deck=["A green checkmark that was quietly wrong — and the four-stage",
              "escalation that governed an AI agent's access for nine releases."],
        lit=[], mid=STAGES, rail=True,
        cap="Every layer below, deployed through one written gate",
    ),
    dict(
        n=2, slug="bronze", accent="#B07D3A",
        title=["Bronze, and the", "confidently wrong fix"],
        deck=["51 inferred leaf fields, two of them lying — and an audit tool",
              "whose own null filter silently never fired."],
        lit=["SOURCES", "BRONZE"],
        cap="Raw JSON → Delta. Schema-on-read: drops nothing, restructures nothing",
    ),
    dict(
        n=3, slug="silver-gold", accent="#A98A16",
        title=["Silver and Gold"],
        deck=["Two pipelines describing the same business, deliberately never",
              "unified. Conformance verified per field, not assumed."],
        lit=["SILVER", "GOLD"],
        cap="Two parallel pipelines, unified only at Gold — 101 dbt models",
    ),
    dict(
        n=4, slug="serving-cicd", accent="#2E8C80",
        title=["Serving and CI/CD"],
        deck=["Guardrails against a model better at SQL than the guardrail —",
              "then a green checkmark that was quietly wrong."],
        lit=["SERVING"], rail=True,
        cap="Genie space + AI/BI dashboard on Gold, deployed by GitHub Actions",
    ),
    dict(
        n=5, slug="genai", accent="#6B5AA0",
        title=["The agent that leaked", "its own system prompt"],
        deck=["The first injection probe anyone would try, run against a careful,",
              "rule-numbered system prompt. It worked."],
        lit=["GENAI"], mid=["GOLD"],
        cap="Two Vector Search indexes and an agent over the same Gold tables",
    ),
    dict(
        n=6, slug="dlt-vs-dbt", accent="#4F7C52",
        title=["DLT versus dbt, and", "getting to GB scale"],
        deck=["Three negative results and one that mattered — then rewriting",
              "both generators without losing their deliberate defects."],
        lit=["SILVER"], dashed=True, mid=["SOURCES", "BRONZE"],
        cap="A Silver slice rebuilt in DLT alongside dbt, then everything at GB scale",
    ),
    dict(
        n=7, slug="four-experiments", accent="#C2711F",
        title=["Four experiments that", "produced numbers"],
        deck=["122,592 duplicated rows, an 86% improvement caused by nothing,",
              "and a result cache that matched on meaning, not text."],
        lit=["GOLD"], mid=["BRONZE"],
        cap="gold_gb.fct_transactions at 2,138,809 rows — the optimization target",
    ),
    dict(
        n=8, slug="what-i-take", accent="#1B2A4A",
        title=["The one that", "didn't resolve"],
        deck=["Clustering quality 0.0, three remediation attempts that didn't",
              "unstick it, and why the failures are the deliverable."],
        lit=["SILVER", "GOLD"],
        cap="Skew on gold_gb, the UDF on silver_gb — where the build stops, and why",
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
    y_title = 198 + (2 - len(title)) * 30
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

    # ---- architecture strip -------------------------------------------------
    # Same six-stage map on all eight posters; only the highlight moves. Read
    # across the series it animates the build, left to right.
    lit = set(p.get("lit", []))
    mid = set(p.get("mid", []))
    rail_on = p.get("rail", False)
    nw, ngap, ny, nh = 132, 20, 478, 46

    # CI/CD control plane, drawn above the data plane it deploys
    rail_ink = a if rail_on else SERIES_INK
    add(f'<text x="78" y="452" font-family="{MONO}" font-size="15" letter-spacing="2.2" '
        f'fill="{rail_ink}">CI/CD · GITHUB ACTIONS → BUNDLE DEPLOY</text>')
    add(f'<line x1="78" y1="462" x2="970" y2="462" stroke="{a if rail_on else "#DAD5C7"}" '
        f'stroke-width="1.4" stroke-dasharray="5 5"/>')

    for i, stage in enumerate(STAGES):
        x = 78 + i * (nw + ngap)
        if stage in lit:
            dash = ' stroke-dasharray="7 4" stroke="#FAF6EC" stroke-width="2"' \
                if p.get("dashed") else ''
            add(f'<rect x="{x}" y="{ny}" width="{nw}" height="{nh}" rx="8" fill="{a}"{dash}/>')
            ink, weight = CREAM, ' font-weight="bold"'
        elif stage in mid:
            add(f'<rect x="{x}" y="{ny}" width="{nw}" height="{nh}" rx="8" fill="none" '
                f'stroke="{a}" stroke-width="1.8"/>')
            ink, weight = a, ''
        else:
            add(f'<rect x="{x}" y="{ny}" width="{nw}" height="{nh}" rx="8" fill="none" '
                f'stroke="{CHIP_OFF_STROKE}" stroke-width="1.6"/>')
            ink, weight = CHIP_OFF_INK, ''
        add(f'<text x="{x + nw/2}" y="{ny + 30}" font-family="{MONO}" font-size="16"{weight} '
            f'letter-spacing="1.4" fill="{ink}" text-anchor="middle">{stage}</text>')
        if i < len(STAGES) - 1:
            cx = x + nw + ngap / 2 - 3
            add(f'<path d="M{cx},{ny + nh/2 - 5} L{cx + 6},{ny + nh/2} L{cx},{ny + nh/2 + 5}" '
                f'fill="none" stroke="{CHIP_OFF_STROKE}" stroke-width="2" '
                f'stroke-linecap="round" stroke-linejoin="round"/>')

    # what the highlighted slice does in this part
    add(f'<text x="78" y="554" font-family="{SANS}" font-size="20" '
        f'fill="{a}">{escape(p["cap"])}</text>')

    # footer
    add(f'<text x="78" y="594" font-family="{MONO}" font-size="19" '
        f'fill="{FOOTER_INK}">{escape(FOOTER)}</text>')
    add(f'<text x="1126" y="594" font-family="{MONO}" font-size="17" fill="{SERIES_INK}" '
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
