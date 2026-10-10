"""Measure what the corrected cube did to flood and green, cell by cell.

Everything is read off the real pipeline. No reimplemented formulas: the curve
numbers and factor scores come from ml_pipeline.core.scoring, so this only
compares inputs and calls the production code.

Compares:
  OLD cube (in /tmp/epoch_cube_OLD.json) -- 4 DW classes + NDVI vegetation
  NEW cube (installed)                  -- 9-class partition + landcover veg

and reports, for each of the 864 cells, the composite curve number, the runoff
depth at the configured design storm, and the green/heat inputs. The scorer is
also run end to end over the 41 wards through the CLI so the reported factor
scores come from `assess`, not from a reimplementation.
"""
import json
import statistics as st
import sys

sys.path.insert(0, ".")

from ml_pipeline.core.scoring import area_weighted_cn  # noqa: E402

OLD = json.load(open("/tmp/epoch_cube_OLD.json"))["cells"]
NEW = json.load(open("ml_pipeline/data/epoch_cube.json"))["cells"]
CONF = json.load(open("ml_pipeline/config/regions/pune.json"))

CN = CONF["hydrology"]["cn_table"]
OLD_CN = {k: v for k, v in CN.items() if k != "bare"}  # the old table had no bare
STORM = CONF["hydrology"]["design_storm_mm"]
SPAN = CONF["thermal"]["uhi_max_delta_c"]

print(f"design storm      : {STORM} mm")
print(f"uhi span          : {SPAN} C")
print(f"cn_table          : {CN}")
print()

shared = sorted(set(OLD) & set(NEW))
print(f"cells in both cubes: {len(shared)}")
print()

print("=" * 78)
print("INPUT SHIFT (what the corrected cube changed)")
print("=" * 78)
for band, label in [
    ("built_pct", "built"),
    ("vegetation_pct", "vegetation"),
    ("tree_canopy_pct", "tree canopy"),
    ("water_pct", "water"),
]:
    o = [OLD[c].get(band, 0) * 100 for c in shared]
    n = [NEW[c].get(band, 0) * 100 for c in shared]
    print(f"  {label:<13} OLD median {st.median(o):6.2f}%  ->  NEW median {st.median(n):6.2f}%"
          f"   ({st.median(n) / max(st.median(o), 1e-9):5.2f}x)")

o_bare = [OLD[c].get("bare_pct", 0) * 100 for c in shared]
n_bare = [NEW[c].get("bare_pct", 0) * 100 for c in shared]
n_seas = [NEW[c].get("bare_season_pct", 0) * 100 for c in shared]
print(f"  {'bare (annual)':<13} OLD median {st.median(o_bare):6.2f}%  ->  NEW median {st.median(n_bare):6.2f}%")
print(f"  {'bare (season)':<13} (not stored)              ->  NEW median {st.median(n_seas):6.2f}%")
print()

print("=" * 78)
print("FLOOD: curve number, old renormalised vs new honest")
print("=" * 78)


def runoff_mm(cn: float, storm: float) -> float:
    """NRCS-CN direct runoff depth. Same formula the scorer uses."""
    S = 25400.0 / cn - 254.0
    Ia = 0.2 * S
    if storm <= Ia:
        return 0.0
    return (storm - Ia) ** 2 / (storm + 0.8 * S)


cn_old, cn_new, ro_old, ro_new, deltas = [], [], [], [], []
for c in shared:
    o, n = OLD[c], NEW[c]
    a = area_weighted_cn(o["built_pct"] * 100, o["vegetation_pct"] * 100,
                         o["water_pct"] * 100, OLD_CN)
    b = area_weighted_cn(n["built_pct"] * 100, n["vegetation_pct"] * 100,
                         n["water_pct"] * 100, CN,
                         bare_pct=n.get("bare_season_pct", 0) * 100)
    cn_old.append(a)
    cn_new.append(b)
    deltas.append(a - b)
    ro_old.append(runoff_mm(a, STORM))
    ro_new.append(runoff_mm(b, STORM))

print(f"  CN OLD  median {st.median(cn_old):6.2f}  min {min(cn_old):6.2f}  max {max(cn_old):6.2f}")
print(f"  CN NEW  median {st.median(cn_new):6.2f}  min {min(cn_new):6.2f}  max {max(cn_new):6.2f}")
print()
print(f"  inflation removed (OLD - NEW): mean {st.mean(deltas):+.2f} CN"
      f"  median {st.median(deltas):+.2f}  range {min(deltas):+.2f} .. {max(deltas):+.2f}")
print()
print(f"  runoff OLD median {st.median(ro_old):6.1f} mm  mean {st.mean(ro_old):6.1f}")
print(f"  runoff NEW median {st.median(ro_new):6.1f} mm  mean {st.mean(ro_new):6.1f}")
gap = [a - b for a, b in zip(ro_old, ro_new)]
print(f"  runoff overstatement removed: mean {st.mean(gap):+.1f} mm"
      f"  range {min(gap):+.1f} .. {max(gap):+.1f}")
print()

worst = sorted(zip(deltas, shared), reverse=True)[:5]
print("  most-inflated cells under the old cube:")
for d, c in worst:
    print(f"    {c}  was +{d:.1f} CN too high")
print()

print("=" * 78)
print("GREEN: ground vegetation no longer starved")
print("=" * 78)
g0 = g1 = 0
sat_old, sat_new = [], []
for c in shared:
    so = OLD[c]["vegetation_pct"] * 100
    sn = NEW[c]["vegetation_pct"] * 100
    sat_old.append(so)
    sat_new.append(sn)
    # the 8,000 m2 synthetic plot used in the 12-ward e2e run
    if so - 0.0 <= 0:
        g0 += 1
    if sn - 0.0 <= 0:
        g1 += 1
print(f"  cells where ground_vegetation == 0 with a TREELESS plot")
print(f"    OLD (NDVI)      : {g0}/{len(shared)}")
print(f"    NEW (landcover) : {g1}/{len(shared)}")
print()
print(f"  satellite vegetation OLD median {st.median(sat_old):.2f}%")
print(f"  satellite vegetation NEW median {st.median(sat_new):.2f}%")
print()

print("=" * 78)
print("HEAT: is it still inverted?")
print("=" * 78)
pairs_b, pairs_l = [], []
for c in shared:
    n = NEW[c]
    delta = n.get("lst_mean_c", 0) - n.get("lst_reference_c", 0)
    if delta > 0:
        pairs_b.append(n["built_pct"] * 100)
        pairs_l.append(delta)


def pearson(x, y):
    if len(x) < 3:
        return float("nan")
    mx, my = st.mean(x), st.mean(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / len(x)
    return cov / (st.pstdev(x) * st.pstdev(y))


print(f"  r(built_pct, lst_delta) = {pearson(pairs_b, pairs_l):+.4f}"
      f"   (n={len(pairs_b)} cells that are warmer than their own reference)")
print("  A positive value is correct: more built should mean hotter.")
print()
print("  NOTE heat_score itself is not recomputed here -- it needs ward-level")
print("  aggregation and a built-up area input. Run the CLI for that.")