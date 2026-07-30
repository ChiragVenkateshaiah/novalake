#!/usr/bin/env python3
"""Generate the 8 Medium part posters for the NovaLake series.

One design system, eight distinct posters. Palette and typography are sampled
from docs/articles/novalake-architecture.png so the covers and the in-article
diagram read as the same body of work:

    cream ground   #FAF6EC     navy ink       #1B2A4A
    bronze tint    #EDD9B8     silver tint    #E4E8EE
    gold tint      #F5EFC7     serving tint   #D9EDEA
    genai tint     #E6DEEF     muted rule     #8B909B

Each poster carries a compressed rendering of the full NovaLake architecture
diagram — the same three bands as the reference: a dashed CI/CD control plane,
a Unity Catalog container holding the six data-plane stages plus the DLT
comparison branch, and the DAB orchestration bar spanning the bottom. Only the
*highlight* changes between parts, so read across the series the diagram
animates the build rather than repeating one static image eight times.

Writes  src/part-N-<slug>.svg  and  ../part-N-<slug>.png  (2400x1520).

Usage:  python3 make_posters.py          (needs rsvg-convert on PATH)
"""

import pathlib
import subprocess
from xml.sax.saxutils import escape

W, H = 1200, 760          # authored size; rendered at 2x
SCALE = 2

CREAM = "#FAF6EC"
INK = "#1B2A4A"
DECK_INK = "#46536B"
OFF_STROKE = "#CFC9B9"
OFF_INK = "#9A9486"
OFF_SUB = "#B3ADA0"
FOOTER_INK = "#8B909B"
SERIES_INK = "#A9A395"
ARROW = "#7A8290"
PANEL_STROKE = "#C9C3B4"

SANS = "DejaVu Sans"
MONO = "JetBrains Mono"

FOOTER = "Databricks Free Edition · PySpark · dbt · Unity Catalog · DAB"

# ---------------------------------------------------------------------------
# The architecture, as drawn on every poster. Names and sub-labels mirror
# novalake-architecture.png so the poster and the in-article figure agree.
# ---------------------------------------------------------------------------

STAGES = [
    ("SOURCES", "Event Generators", ["NDJSON + paginated export", "raw JSON → UC Volume"]),
    ("BRONZE", "PySpark Ingestion", ["src/ingest.py · raw Delta", "schema-on-read · drops nothing"]),
    ("SILVER", "dbt Transformations", ["~80 models · dedupe", "DLQ split · array explode"]),
    ("GOLD", "dbt Dimensional Model", ["~22 models · conformed dims", "facts + metric rollups"]),
    ("SERVING", "Genie + Dashboard", ["natural-language SQL", "3 pages · 11 datasets"]),
    ("GENAI", "Vector Search + Agent", ["2 Delta Sync indexes", "Model Serving · LangGraph"]),
]

CICD = [
    ("GitHub Actions", "validate on PR · deploy on merge"),
    ("Scoped Service Principal", "OAuth M2M · least-privilege grants"),
    ("bundle deploy", "target: dev · no --auto-approve"),
]

# Per-part highlight state:
#   lit    — stages this part builds or measures      (solid accent, cream text)
#   mid    — stages shown as context                  (accent tint, navy text)
#   rail   — light the CI/CD control plane
#   dab    — light the orchestration bar
#   dlt    — light the Lakeflow comparison branch
#   dashed — draw the lit stage as a parallel implementation
#   cap    — one line naming what the highlighted slice does in this part

PARTS = [
    dict(
        n=1, slug="collaboration-model", accent="#47566E",
        title=["The platform is the", "only source of truth"],
        deck=["A green checkmark that was quietly wrong — and the four-stage",
              "escalation that governed an AI agent's access for nine releases."],
        lit=[], mid=[s[0] for s in STAGES], rail=True, dab=True,
        cap="Every layer below, deployed through one written gate",
    ),
    dict(
        n=2, slug="bronze", accent="#B07D3A",
        title=["Bronze, and the", "confidently wrong fix"],
        deck=["51 inferred leaf fields, two of them lying — and an audit tool",
              "whose own null filter silently never fired."],
        lit=["SOURCES", "BRONZE"], dab=True,
        cap="Raw JSON → Delta. Schema-on-read: drops nothing, restructures nothing",
    ),
    dict(
        n=3, slug="silver-gold", accent="#A98A16",
        title=["Silver and Gold"],
        deck=["Two pipelines describing the same business, deliberately never",
              "unified. Conformance verified per field, not assumed."],
        lit=["SILVER", "GOLD"], mid=["BRONZE"],
        cap="Two parallel pipelines, unified only at Gold — 101 dbt models",
    ),
    dict(
        n=4, slug="serving-cicd", accent="#2E8C80",
        title=["Serving and CI/CD"],
        deck=["Guardrails against a model better at SQL than the guardrail —",
              "then a green checkmark that was quietly wrong."],
        lit=["SERVING"], mid=["GOLD"], rail=True, dab=True,
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
        lit=["SILVER"], mid=["SOURCES", "BRONZE"], dlt=True, dashed=True,
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


def box(add, x, y, w, h, state, accent, title, subs, ts=12, ss=8.5, dashed=False):
    """One node of the diagram, in one of three highlight states."""
    dash = ' stroke-dasharray="6 4"' if dashed else ''
    if state == "lit":
        add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{accent}"'
            f'{" stroke=\'#FAF6EC\' stroke-width=\'2\'" + dash if dashed else ""}/>')
        t_ink, s_ink, s_op = CREAM, CREAM, "0.82"
    elif state == "mid":
        add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{accent}" '
            f'fill-opacity="0.16" stroke="{accent}" stroke-opacity="0.55" '
            f'stroke-width="1.4"{dash}/>')
        t_ink, s_ink, s_op = INK, INK, "0.72"
    else:
        add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{CREAM}" '
            f'stroke="{OFF_STROKE}" stroke-width="1.3"{dash}/>')
        t_ink, s_ink, s_op = OFF_INK, OFF_SUB, "1"

    cx = x + w / 2
    ty = y + (h - (ts + len(subs) * (ss + 3.5))) / 2 + ts
    add(f'<text x="{cx}" y="{ty}" font-family="{SANS}" font-size="{ts}" font-weight="bold" '
        f'fill="{t_ink}" text-anchor="middle">{escape(title)}</text>')
    for i, s in enumerate(subs):
        add(f'<text x="{cx}" y="{ty + 13 + i * (ss + 3.5)}" font-family="{SANS}" '
            f'font-size="{ss}" fill="{s_ink}" fill-opacity="{s_op}" '
            f'text-anchor="middle">{escape(s)}</text>')


def arrow(add, x1, x2, y):
    add(f'<line x1="{x1}" y1="{y}" x2="{x2 - 4}" y2="{y}" stroke="{ARROW}" stroke-width="1.5"/>')
    add(f'<path d="M{x2 - 5},{y - 3.4} L{x2},{y} L{x2 - 5},{y + 3.4} Z" fill="{ARROW}"/>')


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

    # ghosted part numeral + accent chip, top right
    add(f'<text x="1152" y="268" font-family="{SANS}" font-size="220" font-weight="bold" '
        f'fill="{a}" fill-opacity="0.12" text-anchor="end">{p["n"]:02d}</text>')
    add(f'<rect x="1124" y="46" width="28" height="28" fill="{a}"/>')

    # eyebrow
    add(f'<text x="78" y="72" font-family="{MONO}" font-size="20" font-weight="bold" '
        f'letter-spacing="4.2" fill="{INK}">NOVALAKE'
        f'<tspan dx="12" fill="{FOOTER_INK}">·</tspan>'
        f'<tspan dx="12" fill="{a}">PART {p["n"]} OF 8</tspan></text>')

    # title / rule / deck — one-line titles drop so the diagram stays put
    y_title = 138 + (2 - len(title)) * 30
    y = y_title
    for line in title:
        add(f'<text x="78" y="{y}" font-family="{SANS}" font-size="48" font-weight="bold" '
            f'fill="{INK}">{escape(line)}</text>')
        y += 60
    y_rule = y_title + (len(title) - 1) * 60 + 30
    add(f'<rect x="78" y="{y_rule}" width="88" height="5" fill="{a}"/>')
    y = y_rule + 44
    for line in deck:
        add(f'<text x="78" y="{y}" font-family="{SANS}" font-size="21" '
            f'fill="{DECK_INK}">{escape(line)}</text>')
        y += 30

    # caption — what the highlighted slice does in this part
    add(f'<text x="78" y="{y + 12}" font-family="{SANS}" font-size="19" font-weight="bold" '
        f'fill="{a}">{escape(p["cap"])}</text>')

    # ---- architecture ------------------------------------------------------
    X0, X1 = 78, 1152
    rail_on, dab_on, dlt_on = p.get("rail"), p.get("dab"), p.get("dlt")

    # band 1 — CI/CD control plane (dashed, sits outside the data flow)
    ry, rh = 352, 66
    r_stroke = a if rail_on else OFF_STROKE
    add(f'<rect x="{X0}" y="{ry}" width="{X1-X0}" height="{rh}" rx="9" fill="none" '
        f'stroke="{r_stroke}" stroke-width="1.4" stroke-dasharray="7 5"/>')
    add(f'<text x="{X0+14}" y="{ry+17}" font-family="{MONO}" font-size="10" '
        f'letter-spacing="1.8" fill="{a if rail_on else OFF_INK}">CI/CD CONTROL PLANE'
        f'<tspan dx="8" fill="{SERIES_INK}" letter-spacing="0">· not part of the data flow below</tspan></text>')
    bw, bgap = 320, 42
    for i, (t, s) in enumerate(CICD):
        bx = X0 + 16 + i * (bw + bgap)
        box(add, bx, ry + 24, bw, 32, "lit" if rail_on else "off", a, t, [s], ts=11, ss=8)
        if i < 2:
            arrow(add, bx + bw + 8, bx + bw + bgap - 8, ry + 40)

    # band 2 — Unity Catalog container holding the data plane
    uy, uh = 430, 178
    add(f'<rect x="{X0}" y="{uy}" width="{X1-X0}" height="{uh}" rx="10" fill="none" '
        f'stroke="{PANEL_STROKE}" stroke-width="1.3"/>')
    add(f'<text x="{X0+14}" y="{uy+18}" font-family="{SANS}" font-size="10" '
        f'font-style="italic" fill="{SERIES_INK}">'
        f'Unity Catalog · catalog: novalake — governs every table below</text>')

    nw, ngap, ny, nh = 156, 20, uy + 44, 70
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

    # the DLT comparison branch, hanging off Bronze under the Silver column
    dy = ny + nh + 16
    dstate = "lit" if dlt_on else "off"
    dx0, dxw = xs[2] - 22, nw * 2 + ngap + 44
    add(f'<path d="M{xs[1]+nw/2},{ny+nh} L{xs[1]+nw/2},{dy+16} L{dx0-6},{dy+16}" fill="none" '
        f'stroke="{a if dlt_on else OFF_STROKE}" stroke-width="1.3" stroke-dasharray="5 4"/>')
    box(add, dx0, dy, dxw, 34, dstate, a, "Lakeflow Declarative Pipelines",
        ["re-implements the Silver transaction slice — comparison only"], ts=11, ss=8,
        dashed=True)

    # band 3 — DAB orchestration
    oy = 638
    box(add, X0, oy, X1 - X0, 40, "lit" if dab_on else "off", a,
        "ORCHESTRATION — Databricks Asset Bundle (DAB)",
        ["one job graph: bronze ingest ▸ dbt (Silver / Gold) — plus dashboard, "
         "vector search & DLT pipeline as bundle resources"], ts=12, ss=8.5)

    # footer
    add(f'<text x="78" y="716" font-family="{MONO}" font-size="18" '
        f'fill="{FOOTER_INK}">{escape(FOOTER)}</text>')
    add(f'<text x="1152" y="716" font-family="{MONO}" font-size="16" fill="{SERIES_INK}" '
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
