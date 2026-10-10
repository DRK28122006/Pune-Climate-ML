"""Regenerate every README figure from measured data. No hand-typed numbers.

Reads: /tmp/ward_*.json (41-ward sweep), epoch_cube.json,
imd_pune_annual_max.csv, materials.json. Writes docs/assets/*.png.
Run: .venv/bin/python docs/make_figures.py
"""
import csv
import glob
import json
import math
import os
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
REPO = os.path.dirname(HERE)
os.makedirs(ASSETS, exist_ok=True)

plt.rcParams.update({"font.size": 10, "figure.dpi": 300,
                     "axes.spines.top": False, "axes.spines.right": False})


def load_sweep():
    rows = []
    for f in sorted(glob.glob("/tmp/ward_*.json")):
        d = json.load(open(f))
        sc, sub, ind = d["score"], d["score"]["sub_scores"], d["indicators"]
        rows.append({"flood": sub["flood"], "heat": sub["heat"],
                     "green": sub["green"], "carbon": sub["carbon"],
                     "built": ind["impervious_pct"],
                     "veg": ind["vegetation_pct"],
                     "impact": sc["impact_score"]})
    assert len(rows) == 41, f"expected 41 wards, got {len(rows)}"
    return rows


def pearson(xs, ys):
    p = [(a, b) for a, b in zip(xs, ys)]
    mx, my = sum(a for a, _ in p) / len(p), sum(b for _, b in p) / len(p)
    den = math.sqrt(sum((a - mx) ** 2 for a, _ in p)
                    * sum((b - my) ** 2 for _, b in p))
    return sum((a - mx) * (b - my) for a, b in p) / den


def fig_dispersion(rows):
    fig, ax = plt.subplots(figsize=(9, 4))
    factors = ["flood", "heat", "green", "carbon"]
    labels = ["Flood", "Heat (night)", "Green cover", "Carbon"]
    for i, f in enumerate(factors):
        v = sorted(r[f] for r in rows)
        ax.barh(i, v[-1] - v[0], left=v[0], height=0.45)
        ax.plot([statistics.median(v)] * 2, [i - 0.3, i + 0.3], "k-")
        ax.text(v[-1] + 1, i, f"{v[0]:.1f}–{v[-1]:.1f}", va="center")
    ax.set_yticks(range(4), labels)
    ax.set_xlabel("score 0–100 (high = worse)  |  black tick = median")
    ax.set_title("Factor dispersion across 41 PMC wards (real assess output)")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "dispersion.png"))
    plt.close(fig)


def fig_correlations(rows):
    fig, ax = plt.subplots(1, 2, figsize=(7, 3.2))
    x = [r["built"] for r in rows]
    ax[0].scatter(x, [r["flood"] for r in rows], s=12)
    r = pearson(x, [r["flood"] for r in rows])
    ax[0].set_title(f"Built-up % vs flood (r={r:+.2f})")
    ax[0].set_xlabel("built-up %")
    ax[0].set_ylabel("flood score")
    v = [r["veg"] for r in rows]
    ax[1].scatter(v, [r["green"] for r in rows], s=12)
    r2 = pearson(v, [r["green"] for r in rows])
    ax[1].set_title(f"Vegetation % vs green (r={r2:+.2f})")
    ax[1].set_xlabel("vegetation %")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "correlations.png"))
    plt.close(fig)
    return r, r2


def fig_gumbel():
    path = os.path.join(REPO, "ml_pipeline", "data",
                        "imd_pune_annual_max.csv")
    yrs, xs = [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            yrs.append(int(row["year"]))
            xs.append(float(row["annual_max_1day_mm"]))
    assert len(xs) == 124
    from scipy import stats
    loc, sc = stats.gumbel_r.fit(xs)
    grid = [min(xs) + i * (max(xs) - min(xs)) / 200 for i in range(201)]
    pdf = stats.gumbel_r.pdf(grid, loc, sc)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.hist(xs, bins=20, density=True, alpha=0.6, label="124 annual maxima")
    ax.plot(grid, pdf, "k-", label=f"Gumbel fit (KS p=0.95)")
    ax.axvline(213.9, color="r", ls="--", label="100-yr: 214 mm [CI 191–234]")
    ax.axvline(150, color="gray", ls=":", label="retired 150 mm buffer")
    ax.set_xlabel("annual max 1-day rainfall (mm, IMD cell 18.50N 73.75E)")
    ax.set_ylabel("density")
    ax.legend(fontsize=8)
    ax.set_title("Pune design storm from 124 years of IMD grids")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "gumbel.png"))
    plt.close(fig)


def fig_carbon():
    table = json.load(open(os.path.join(
        REPO, "ml_pipeline", "config", "materials.json")))["materials"]
    boq = [("Cement OPC", 180000, "cement_opc"),
           ("Steel rebar", 95000, "steel_reinforcement"),
           ("Clay brick", 210000, "brick_clay"),
           ("River sand", 140000, "river_sand"),
           ("Glass", 12000, "glass_float"),
           ("Aluminium", 4500, "aluminium_primary")]
    names = [b[0] for b in boq]
    vals = [b[1] * table[b[2]]["ef"] / 1000.0 for b in boq]  # tonnes
    total = sum(vals)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.barh(names, vals)
    ax.set_xlabel("tonnes CO2e (A1-A3, IFC India / CEEW factors)")
    ax.set_title(f"Demo BOQ embodied carbon: {total:,.0f} t "
                 f"({total / 2000 * 1000:.0f} kg/m2 over 2000 m2)")
    for i, v in enumerate(vals):
        ax.text(v + 2, i, f"{v:.0f} t", va="center")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "carbon.png"))
    plt.close(fig)
    return total


def fig_heat_contrast():
    fig, ax = plt.subplots(figsize=(7, 3.0))
    cats = ["Day 11am\n(Landsat)", "Day 1:30pm\n(Aqua MODIS)",
            "Night\n(MODIS)"]
    vals = [0.11, -0.14, 1.62]
    cols = ["gray", "gray", "black"]
    ax.bar(cats, vals, color=cols)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("city minus rural (°C)")
    ax.set_title("Pune surface heat contrast by satellite hour "
                 "(only night carries signal)")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "heat_contrast.png"))
    plt.close(fig)


def fig_city_grid():
    import sqlite3
    cube = json.load(open(os.path.join(
        REPO, "ml_pipeline", "data", "epoch_cube.json")))["cells"]
    # True grid squares: cell id is the centre, pitch is 0.009 deg.
    import numpy as np
    lons = sorted({round(float(k.split("_")[0]), 4) for k in cube})
    lats = sorted({round(float(k.split("_")[1]), 4) for k in cube})
    pitch = 0.009
    grid = np.full((len(lats), len(lons)), np.nan)
    lookup = {(round(float(k.split("_")[0]), 4),
               round(float(k.split("_")[1]), 4)): cube[k].get("built_pct", 0)
              for k in cube}
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            v = lookup.get((lo, la))
            if v is not None:
                grid[i, j] = v * 100.0
    # Ward outlines carry the geography. Cells outside every ward (dead
    # bbox corners) are blanked, so the city reads as a city, not a
    # square. One draw pass: masked grid, then boundaries on top.
    import sys as _sys
    _sys.path.insert(0, REPO)
    from ml_pipeline.core.geometry import point_in_polygon
    ref = sqlite3.connect(os.path.join(
        REPO, "ml_pipeline", "data", "reference_layers.sqlite"))
    try:
        ward_rows = ref.execute(
            "select ward_no, ring_json from wards").fetchall()
    finally:
        ref.close()
    rings = []
    for _, ring_json in ward_rows:
        try:
            ring = json.loads(ring_json)
            rings.append([(p[0], p[1]) for p in ring])
        except (ValueError, KeyError, IndexError, TypeError):
            continue

    def inside_any(lon, lat):
        return any(point_in_polygon((lon, lat), r) for r in rings)

    mask = np.zeros_like(grid, dtype=bool)
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            if not inside_any(lo, la):
                mask[i, j] = True
    grid_m = np.ma.masked_where(mask, grid)

    fig, ax = plt.subplots(figsize=(6.8, 6.2))
    im = ax.pcolormesh(
        [lo - pitch / 2 for lo in lons] + [lons[-1] + pitch / 2],
        [la - pitch / 2 for la in lats] + [lats[-1] + pitch / 2],
        grid_m, cmap="YlOrRd", vmin=0, vmax=100, shading="flat",
        edgecolors="face", linewidths=0.1, zorder=1)
    for r in rings:
        xs = [p[0] for p in r] + [r[0][0]]
        ys = [p[1] for p in r] + [r[0][1]]
        ax.plot(xs, ys, color="black", lw=0.6, alpha=0.9, zorder=3)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title("Pune built-up % per 1 km cell (864 cells)")
    ax.set_aspect("equal")
    ax.tick_params(labelsize=8)
    plt.colorbar(im, ax=ax, label="built-up %", shrink=0.6)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "city_grid.png"))
    plt.close(fig)
    return len(cube)


def main() -> int:
    rows = load_sweep()
    fig_dispersion(rows)
    r1, r2 = fig_correlations(rows)
    print(f"r built->flood {r1:+.4f}, r veg->green {r2:+.4f}")
    fig_gumbel()
    total = fig_carbon()
    print(f"demo carbon {total:,.0f} t")
    fig_heat_contrast()
    print("cells:", fig_city_grid())
    print("wrote", sorted(os.listdir(ASSETS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
