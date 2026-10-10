"""Isolate the two independent fixes, and sanity-check the new bands.

`measure_cube_fix.py` fed the OLD cube's inputs through the NEW curve-number
code, so its "inflation removed" number measured the cube fix and the divisor
fix together. This separates them:

  A  old inputs  + OLD code (renormalise by represented sum, no bare class)
     = the shipped behaviour, the thing that produced mean +38.3 CN
  B  old inputs  + NEW code (divide by 100, residual as bare)
     = isolates the CN fix
  C  new inputs  + NEW code
     = isolates the cube fix on top

The production scorer is used for B and C. A is the historical formula,
written out here ONLY to quantify the defect being fixed -- it is not a
production path and no pipeline output depends on it.
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
OLD_CN = {k: v for k, v in CN.items() if k != "bare"}
STORM = CONF["hydrology"]["design_storm_mm"]


def cn_old_code(imperv, veg, water, table):
    """The shipped formula: renormalise by whatever the three bands covered.

    Kept verbatim from before the fix so the size of the defect is a measured
    number rather than a recollection. Never used by the pipeline.
    """
    imperv = max(0.0, min(100.0, imperv)) / 100.0
    veg = max(0.0, min(100.0, veg)) / 100.0
    water = max(0.0, min(100.0, water)) / 100.0
    total = imperv + veg + water
    if total <= 0:
        return float(table.get("vegetation", 60.0))
    cn = (
        veg * float(table.get("vegetation", 60.0))
        + imperv * float(table.get("impervious", 98.0))
        + water * float(table.get("water", 100.0))
    ) / total
    return max(1.0, min(100.0, cn))


def runoff_mm(cn, storm):
    S = 25400.0 / cn - 254.0
    Ia = 0.2 * S
    return 0.0 if storm <= Ia else (storm - Ia) ** 2 / (storm + 0.8 * S)


shared = sorted(set(OLD) & set(NEW))
print(f"cells compared: {len(shared)}")
print(f"design storm  : {STORM} mm")
print()

A, B, C = [], [], []
for c in shared:
    o, n = OLD[c], NEW[c]
    A.append(cn_old_code(o["built_pct"] * 100, o["vegetation_pct"] * 100,
                         o["water_pct"] * 100, OLD_CN))
    B.append(area_weighted_cn(o["built_pct"] * 100, o["vegetation_pct"] * 100,
                              o["water_pct"] * 100, CN,
                              bare_pct=o.get("bare_pct", 0) * 100))
    C.append(area_weighted_cn(n["built_pct"] * 100, n["vegetation_pct"] * 100,
                              n["water_pct"] * 100, CN,
                              bare_pct=n.get("bare_season_pct", 0) * 100))

print("=" * 76)
print("CURVE NUMBER: the two fixes separated")
print("=" * 76)
print(f"  A  old inputs + old renormalising code : median {st.median(A):6.2f}"
      f"   mean {st.mean(A):6.2f}   max {max(A):6.2f}")
print(f"  B  old inputs + new divisor, no bare  : median {st.median(B):6.2f}"
      f"   mean {st.mean(B):6.2f}   max {max(B):6.2f}")
print(f"  C  new inputs + new divisor + bare    : median {st.median(C):6.2f}"
      f"   mean {st.mean(C):6.2f}   max {max(C):6.2f}")
print()
dA = [a - c for a, c in zip(A, C)]
dB = [b - c for b, c in zip(B, C)]
print(f"  total correction A -> C : mean {st.mean(dA):+.2f} CN"
      f"  median {st.median(dA):+.2f}  range {min(dA):+.2f} .. {max(dA):+.2f}")
print(f"    of which CN-code fix (A->B): mean {st.mean([a - b for a, b in zip(A, B)]):+.2f} CN")
print(f"    of which cube fix   (B->C): mean {st.mean(dB):+.2f} CN"
      f"  range {min(dB):+.2f} .. {max(dB):+.2f}")
print()

rA = [runoff_mm(cn, STORM) for cn in A]
rC = [runoff_mm(cn, STORM) for cn in C]
g = [a - c for a, c in zip(rA, rC)]
print(f"  runoff A median {st.median(rA):6.1f} mm   ->   C median {st.median(rC):6.1f} mm")
print(f"  overstatement removed: mean {st.mean(g):+.1f} mm"
      f"  range {min(g):+.1f} .. {max(g):+.1f}")
print()

print("=" * 76)
print("SANITY: are the new bands physically plausible for Pune?")
print("=" * 76)


def q(vals, lo, hi):
    s = sorted(vals)
    return s[int(lo * (len(s) - 1))], st.median(s), s[int(hi * (len(s) - 1))]


for band, label, hi_expect in [
    ("built_pct", "built", 100),
    ("vegetation_pct", "vegetation", 100),
    ("tree_canopy_pct", "tree canopy", 40),
    ("water_pct", "water", 100),
    ("bare_pct", "bare (annual)", 100),
    ("bare_season_pct", "bare (season)", 100),
    ("snow_and_ice", "snow", 5),
    ("labelled_fraction", "labelled", 1),
]:
    v = [NEW[c].get(band, 0) * 100 for c in shared]
    p5, med, p95 = q(v, 0.05, 0.95)
    flag = ""
    if med > hi_expect:
        flag = "  <-- median exceeds the physical maximum"
    print(f"  {label:<14} p5 {p5:6.2f}%  median {med:6.2f}%  p95 {p95:6.2f}%"
          f"  max {max(v):6.2f}%{flag}")

print()
water_max = max(NEW[c].get("water_pct", 0) * 100 for c in shared)
snow_max = max(NEW[c].get("snow_and_ice", 0) * 100 for c in shared)
print(f"  water  max {water_max:.2f}%  (rivers and lakes exist -> must be > 0)")
print(f"  snow   max {snow_max:.2f}%  (Pune 535-1030 m -> must be ~0)")
print()
nz = sum(1 for c in shared if NEW[c].get("water_pct", 0) > 0.001)
print(f"  cells with any water: {nz}/{len(shared)}")
print("  If water is 0 in nearly every cell the majority vote is dropping the")
print("  thin linear rivers -- rivers are narrow, so at 30 m they may genuinely")
print("  be sub-pixel, but PMC's flood question is exactly about them.")