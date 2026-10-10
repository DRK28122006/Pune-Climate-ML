"""Build docs/Dishadharti_ML_Report.pdf from measured repo data.

Black text, ruled sections, sourced tables, embedded figures.
Run: .venv/bin/python docs/make_report.py
"""
import csv
import glob
import json
import os
import statistics

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Image, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(HERE, "Dishadharti_ML_Report.pdf")
BLACK = colors.HexColor("#111111")
RULE = colors.HexColor("#111111")
HEAD_BG = colors.HexColor("#E8E8E8")

styles = getSampleStyleSheet()
sTitle = ParagraphStyle("Title2", parent=styles["Title"], textColor=BLACK,
                        fontSize=22, spaceAfter=2 * mm)
sSub = ParagraphStyle("Sub", parent=styles["Normal"], textColor=BLACK,
                      fontSize=11, spaceAfter=6 * mm)
sH1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=BLACK,
                     fontSize=14, spaceBefore=6 * mm, spaceAfter=3 * mm,
                     borderPadding=(0, 0, 2 * mm))
sH2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=BLACK,
                     fontSize=11, spaceBefore=4 * mm, spaceAfter=2 * mm)
sBody = ParagraphStyle("Body", parent=styles["Normal"], textColor=BLACK,
                       fontSize=9.5, leading=13.5, spaceAfter=2 * mm)
sCell = ParagraphStyle("Cell", parent=styles["Normal"], textColor=BLACK,
                       fontSize=8, leading=10.5)
sCap = ParagraphStyle("Cap", parent=styles["Normal"], textColor=BLACK,
                      fontSize=8, leading=10.5, spaceBefore=1 * mm,
                      spaceAfter=4 * mm, alignment=1)
sMono = ParagraphStyle("Mono", parent=styles["Code"], textColor=BLACK,
                       fontSize=8, leading=11, backColor=colors.HexColor(
                           "#F4F4F4"), borderPadding=6)


def rule():
    return HRFlowable(width="100%", thickness=0.8, color=RULE,
                      spaceBefore=2 * mm, spaceAfter=2 * mm)


def stable(headers, rows, widths=None):
    data = [[Paragraph(f"<b>{h}</b>", sCell) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), sCell) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("BOX", (0, 0), (-1, -1), 0.8, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def fig(path, width_mm=150):
    p = os.path.join(HERE, "assets", path)
    if not os.path.exists(p):
        return Paragraph(f"[figure missing: {path}]", sCap)
    # Preserve native aspect (fixed 2026-10-10: a fixed height box
    # squished the square city map). Width-constrained, height follows.
    from PIL import Image as PILImage
    iw, ih = PILImage.open(p).size
    w = width_mm * mm
    return Image(p, width=w, height=w * ih / iw)


def sweep_stats():
    rows = []
    for f in sorted(glob.glob("/tmp/ward_*.json")):
        d = json.load(open(f))
        sc, sub = d["score"], d["score"]["sub_scores"]
        rows.append({k: sub[k] for k in
                     ("flood", "heat", "green", "carbon")})
    out = {}
    for k in ("flood", "heat", "green", "carbon"):
        v = sorted(r[k] for r in rows)
        out[k] = (v[0], statistics.median(v), v[-1])
    return out, len(rows)


def main() -> int:
    S, n = sweep_stats()
    story = []
    A = story.append
    A(Paragraph("Dishadharti — ML Technical Report", sTitle))
    A(Paragraph("Everything the ML track built: inputs, data, methods per "
                "factor, measurements, decisions, sources with links, and "
                "how to run and reuse it. Written so every teammate — "
                "technical or not — knows exactly what is done. Every "
                "number below was read off a real run.", sSub))
    A(rule())

    A(Paragraph("1. Problem and use cases", sH1))
    A(Paragraph("A municipal officer receives a development proposal and "
                "must decide: approve, condition, or reject. Today that "
                "decision has no climate evidence. This system scores the "
                "proposal on flood, heat, green cover, and embodied carbon "
                "(0–100, high = worse), explains the scores in plain "
                "language, and attaches redesign conditions whose effects "
                "are measured by re-scoring — not asserted.", sBody))
    A(stable(["Use case", "Who", "What the system does"],
             [["Pre-approval screening", "Municipal officer",
               "Pin plot + two areas + bill of quantities; receive four "
               "scores, a verdict (approve / condition / reject), and "
               "ranked conditions."],
              ["Redesign guidance", "Builder / architect",
               "Each condition shows its measured score delta, so redesign "
               "targets the factor that moves most."],
              ["Tree compliance", "Tree Officer",
               "Plot-level tree ledger: what stays, what falls, "
               "age-equivalent compensation as a range."],
              ["Spoken explanation", "Officer / public",
               "Chatbot narrates the computed JSON. It reads numbers; it "
               "never computes or adjusts them."],
              ["Reuse in another city", "Any municipal team",
               "The engine holds no city knowledge: new config + cube + "
               "census + wards, same scorer."]],
             widths=[38 * mm, 32 * mm, 100 * mm]))

    A(Paragraph("2. Inputs: what the builder hands over", sH1))
    A(Paragraph("Four things, nothing else trusted. Storeys and project "
                "type are framing words only — they never change a number.",
                sBody))
    A(stable(["Input", "Example", "How it is used"],
             [["Site boundary", "Map pin / GeoJSON / KML polygon",
               "Decides the ward and exactly which census trees stand "
               "inside the footprint (point-in-polygon, never a ward-id "
               "join)."],
              ["Built-up area", "3,000 m2",
               "Drives flood (impervious fraction) and divides carbon "
               "intensity. Must not exceed plot area — rejected otherwise."],
              ["Plot area", "8,000 m2",
               "The site extent. Canopy percentage divides by this; "
               "zero or missing plot fails validation with reasons."],
              ["Bill of quantities", "cement 120,000 kg; steel 45,000 kg",
               "Each line times its emission factor. 102 name aliases "
               "resolve real-world spellings; over 10% unrecognised mass "
               "withholds the carbon score instead of guessing."]],
             widths=[32 * mm, 52 * mm, 86 * mm]))

    A(Paragraph("3. System architecture", sH1))
    A(Paragraph("Two phases. Phase 1 runs once, offline: satellites and "
                "census files are baked into two artefacts — epoch_cube.json "
                "(864 one-km Pune cells: land cover, day/night surface "
                "temperature, elevation) and tree_index.sqlite (4,009,623 "
                "deduplicated census trees, spatially indexed). Phase 2 runs "
                "per proposal in ~10 seconds with no internet: point-in-"
                "polygon on 864 rows plus a tree-ledger walk, then "
                "deterministic arithmetic. This is a lookup table, not "
                "retrieval: no embeddings, no vector store. A committee can "
                "audit an exact number and challenge it.", sBody))
    A(fig("city_grid.png"))
    A(Paragraph("Figure 1. Built-up share per cell with ward boundaries. "
                "Every flood score in the system comes out of this "
                "partition.", sCap))

    A(Paragraph("4. Data built", sH1))
    A(stable(["Artefact", "Content", "Count / status"],
             [["Epoch cube", "2024 land cover + temperatures + elevation",
               "864/864 cells complete"],
              ["Tree index", "Deduplicated 2019 census, spatial lookup",
               "4,009,623 trees"],
              ["Rainfall series", "124 annual 1-day maxima, IMD grids",
               "imd_pune_annual_max.csv"],
              ["Emission table", "38 materials, 102 aliases, India factors",
               "materials.json"],
              ["Species table", "Census species data, full-index audit",
               "species.json"]],
             widths=[35 * mm, 70 * mm, 65 * mm]))
    A(Paragraph("The partition was the hard part. An early build silently "
                "deleted every water pixel, read vegetation from the wrong "
                "sensor at half its value, and smeared classifier "
                "uncertainty into phantom snow. All three were found by "
                "measurement and gated: the cube now refuses to build unless "
                "its nine land classes sum to one per cell. Water went 0 to "
                "258 cells; vegetation median 6.3% to 30.2%.", sBody))

    A(Paragraph("5. Flood", sH1))
    A(Paragraph("Standard SCS curve-number hydrology (NRCS TR-55): "
                "area-weighted coefficients versus a vegetated baseline, "
                "excess runoff at the design storm. Drainage proximity can "
                "only lower the score; natural streams never count. Design "
                "storm 214 mm: Gumbel 100-year quantile over 124 IMD annual "
                "maxima (fit p = 0.95, interval 191–234). Across 41 wards: "
                f"{S['flood'][0]:.1f}–{S['flood'][2]:.1f}; built-up predicts "
                "it at r = +0.92, vegetation at r = −0.95.", sBody))
    A(fig("gumbel.png"))
    A(Paragraph("Figure 2. Gumbel fit to 124 IMD annual maxima. The retired "
                "150 mm buffer sat between the 10- and 25-year storms.", sCap))
    A(fig("correlations.png"))
    A(Paragraph("Figure 3. Flood rises with concrete, green cover falls "
                "with vegetation loss. Both point the right way.", sCap))

    A(Paragraph("6. Heat", sH1))
    A(Paragraph("Night surface temperature minus a rural vegetated ring, "
                "over a measured 5.0 C span. City mean +1.62 C above rural "
                "(Yale YCEO anchor sampled live at +1.139). Daytime was "
                "tested twice and retired: 11am contrast +0.11 C with "
                "seasonal sign flip; 1:30pm peak-hour contrast −0.14 C "
                "(dry rural soil out-heats shaded city — documented dryland "
                "effect). Reports label heat night-only and carry unscored "
                "afternoon context instead of a faked score. Spread 0.8–99.0, "
                "the widest of any factor.", sBody))
    A(fig("heat_contrast.png", width_mm=130))
    A(Paragraph("Figure 4. Only the night column carries signal.", sCap))

    A(Paragraph("7. Green cover and carbon", sH1))
    A(Paragraph("Green: census canopy (70%) + satellite ground vegetation "
                "(30%), stratified against double-counting; missing data "
                "returns unavailable, never perfect. Compensation is "
                "age-equivalent ranges under the 1975 Trees Act as amended "
                "2021. Spread 62–100, r = −0.81. Carbon: bill of quantities "
                "times India factors (cement 0.91, steel 2.6, brick 0.39; "
                "aluminium 20.88), per square metre against a 1200 scale. "
                "Above 10% unknown mass the score is withheld. Flat across "
                "wards by design.", sBody))
    A(fig("carbon.png"))
    A(Paragraph("Figure 5. Demo bill: 602 tonnes, steel first. Every bar "
                "multiplies out by hand.", sCap))
    A(fig("dispersion.png"))
    A(Paragraph("Figure 6. All four factors across 41 wards. Carbon is flat "
                "because materials do not vary by location.", sCap))

    A(Paragraph("8. What the system refuses", sH1))
    A(Paragraph("Missing data drops a factor out (weights redistribute) — "
                "never zero-filled. The narrator cannot alter numbers "
                "(prompt rules + tests; one live verdict-softening caught "
                "and locked). Unsourced numbers stay labelled (carbon bands, "
                "soil group). No neural scorer: one candidate heat model was "
                "trained, failed its own bars, and ships nothing.", sBody))

    A(Paragraph("9. Verification ledger", sH1))
    A(stable(["Claim", "Evidence"],
             [["Flood tracks built cover", "r = +0.92, n = 41 real runs"],
              ["Flood tracks vegetation", "r = −0.95"],
              ["Green tracks vegetation", "r = −0.81"],
              ["Night heat has contrast", "city +1.62; r = +0.55 / −0.54"],
              ["YCEO anchor", "+1.139 sampled live"],
              ["Storm 214 mm", "Gumbel KS p = 0.95, CI 191–234"],
              ["Cement / steel / brick", "IFC India Table 16"],
              ["IGBC / high-rise anchors", "700 / 454, primary sources"],
              ["Census total", "4,009,623 indexed of 4,009,624 unique"],
              ["Suites", "48/48, 8/8, e2e, narrative 22/22, engine 23/23"]],
             widths=[60 * mm, 110 * mm]))

    A(PageBreak())
    A(Paragraph("10. Sources", sH1))
    A(Paragraph("Datasets", sH2))
    A(stable(["Dataset", "Source", "Link"],
             [["PMC Tree Census 2019 (17 parts)",
               "OpenCity CKAN package f00d83b8",
               "data.opencity.in"],
              ["IMD 0.25-degree daily rainfall 1901-2024 (Pai et al. 2014)",
               "IMD Pune, Climate Monitoring group",
               "imdpune.gov.in/cmpg/Griddata"],
              ["Landsat 8/9 C2L2 surface temperature",
               "USGS via Google Earth Engine",
               "LANDSAT/LC08/C02/T1_L2 (GEE catalog)"],
              ["MODIS day/night LST, Terra + Aqua (10:30 / 1:30)",
               "NASA via Google Earth Engine",
               "MODIS/061/MOD11A1 + MYD11A1 (GEE catalog)"],
              ["Dynamic World land cover (9 classes)",
               "Google via Google Earth Engine",
               "GOOGLE/DYNAMICWORLD/V1 (GEE catalog)"],
              ["ECOSTRESS night LST (70 m)",
               "NASA/JPL via Google Earth Engine",
               "NASA/ECOSTRESS/L2T_LSTE/V2 (GEE catalog)"],
              ["Yale YCEO urban heat (yearly)",
               "Yale via Google Earth Engine",
               "YALE/YCEO/UHI/UHI_yearly_averaged/v4 (GEE catalog)"],
              ["GEDI canopy height (RH95)",
               "NASA via Google Earth Engine",
               "LARSE/GEDI/GEDI02_A_002_MONTHLY (GEE catalog)"],
              ["IFC India materials database (Table 16 GWP)",
               "IFC / EU Eco-cities 2017",
               "edgebuildings.com (IFC India DB methodology report)"],
              ["PMC ward boundaries (41 wards)",
               "pmc_wards_2025.kml, repo file",
               "repo: pmc_wards_2025.kml"]],
             widths=[48 * mm, 62 * mm, 60 * mm]))
    A(Paragraph("Papers and standards", sH2))
    A(stable(["Reference", "Used for", "Find it"],
             [["USDA SCS TR-55 (1986)", "Curve numbers, runoff equation",
               "USDA NRCS (TR-55)"],
              ["Vivekanandan (2022), JWRE journalspub",
               "Gumbel/EV1 choice for Pune",
               "civil.journalspub.info (JWRE Vol.8 No.1)"],
              ["Das et al. (2022), MAUSAM journal",
               "Gumbel IDF precedent, India", "MAUSAM journal"],
              ["Chow / Maidment / Mays (1988), Applied Hydrology",
               "Annual-maximum method", "McGraw-Hill textbook"],
              ["Stewart & Oke (2012), Bull. Am. Meteorol. Soc.",
               "Local Climate Zones language", "AMS journal"],
              ["Karadumpa et al. (2024), Indian cement plants",
               "Cement factors 0.89–0.94", "PubMed 38123770"],
              ["CEEW steel + aluminium reports",
               "Indian industry factors", "ceew.in publications"],
              ["Akshatha et al. (2025), high-rise study",
               "Mean 454 kgCO2e/m2", "ResearchGate 396344543"],
              ["IGBC Net Zero Carbon rating page",
               "700 kgCO2e/m2 anchor", "igbc.in net-zero-carbon-rating"],
              ["WRI India Pune tree-cover technical note (DOI "
               "10.46830/writn.21.00111)",
               "620 ha loss; census caveats", "wri-india.org"],
              ["Maharashtra Trees Act 1975 + 2021 amendment (PRS Bill "
               "No. 8 of 2021)",
               "Felling permission; age-equivalent compensation",
               "prsindia.org; pmc.gov.in tree-protection page"]],
             widths=[52 * mm, 58 * mm, 60 * mm]))

    A(Paragraph("11. Engine reuse and chatbot", sH1))
    A(Paragraph("Any-region engine. The scorer holds no city knowledge: "
                "engine/region.py builds the grid and a validated config "
                "scaffold, engine/census.py maps any CSV headers onto the "
                "canonical tree index, engine/score.py scores through the "
                "live core (imports only, nothing copied). Proven by 23 "
                "self-tests on a synthetic region with foreign headers. "
                "A new city supplies four things — config, satellite cube, "
                "census index, ward polygons — and the same code scores it.",
                sBody))
    A(Paragraph("Chatbot narrator. Reads the computed assessment JSON and "
                "writes officer-plain prose: verdict first (quoted "
                "verbatim), then each factor with its number, conditions "
                "with measured effects, the tree ledger, and unknowns "
                "stated plainly. Model: Gemini Flash via REST (standard "
                "library only); key lives in server-side .env, never in "
                "chat, git, or prompts. Verified live: every score, delta, "
                "canopy figure, and verdict exact across test wards; one "
                "verdict-softening caught on a live run and locked by test. "
                "Blocking issues (unknown materials) are mandatory in "
                "prose, never buried.", sBody))

    A(Paragraph("12. Run and reuse", sH1))
    A(Paragraph("Assess: python -m ml_pipeline.cli assess --ward 12 "
                "--built-up 3000 --plot 8000 --materials '[...]' "
                "--role municipal_authority --json-out /tmp/out.json. "
                "Narrate: python ml_pipeline/report/narrative.py /tmp/out.json "
                "(GEMINI_API_KEY in .env). Any other city: engine/ takes a "
                "config, a cube, a census index, and ward polygons — the "
                "scorer holds no city knowledge.", sBody))
    A(Paragraph("Known limits. Flood and heat score a 1 km square, not the "
                "plot. Daytime surface heat carries no signal here. Carbon "
                "bands are house bands with sourced anchors. A "
                "plausible-but-wrong input inside 0–100 is undetectable "
                "without a second source. No trained model exists here, "
                "deliberately.", sBody))

    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm,
                            rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="Dishadharti ML Report",
                            author="ML track")
    doc.build(story)
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
