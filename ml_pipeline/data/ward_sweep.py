"""End-to-end ward sweep through the real CLI, after the cube fix.

Every number printed here is the pipeline's own output from
`python -m ml_pipeline.cli assess`. Nothing is recomputed. The sweep exists to
answer three questions with measurements rather than reasoning:

  1. Do flood and green scores now respond to the site's actual character, or
     are they still compressed?
  2. Is heat still inverted (the one factor the cube work did not target)?
  3. Do the factors still disperse across sites, or has the corrected cube
     collapsed them?

The same 3,000 m2 building / 8,000 m2 plot / identical BOQ is used for every
ward so only location varies.
"""
import json
import subprocess
import sys

WARDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
         16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
WARDS += [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41]

rows = []
print(f"running `assess` for {len(WARDS)} wards...", file=sys.stderr)
for w in WARDS:
    out = f"/tmp/ward_{w}.json"
    p = subprocess.run(
        [sys.executable, "-m", "ml_pipeline.cli", "assess",
         "--ward", str(w), "--built-up", "3000", "--plot", "8000",
         "--demo-materials", "--json-out", out],
        capture_output=True, text=True,
        env={"PYTHONPATH": "/home/mesh/Pune-Climate-ML", "PATH": "/usr/bin:/bin"},
    )
    if p.returncode != 0 or not __import__("os").path.exists(out):
        rows.append((w, None, (p.stderr or p.stdout).strip().splitlines()[-1:]))
        continue
    d = json.load(open(out))
    # FIX 2026-10-10: the old code read d["scores"]["sub_scores"][f]["score"]
    # ("scores" plural, factor dicts). The real assess schema is
    # d["score"]["sub_scores"][f] = plain float, drivers in d["indicators"],
    # CN/deltas in d["score"]["factors"]. The old mapping silently yielded
    # all-None rows (table of "-" with n=0 correlations) -- the same bug
    # class as ever: a plausible-looking empty result instead of an error.
    sc = d.get("score", {})
    sub = sc.get("sub_scores", {}) or {}
    ind = d.get("indicators", {}) or {}
    fac = sc.get("factors", {}) or {}
    v = {
        "impact": sc.get("impact_score"),
        "flood": sub.get("flood"),
        "heat": sub.get("heat"),
        "green": sub.get("green"),
        "carbon": sub.get("carbon"),
        "built": ind.get("impervious_pct"),
        "veg": ind.get("vegetation_pct"),
        "water": ind.get("water_pct"),
        "bare": ind.get("bare_pct"),
        "cn": (fac.get("flood") or {}).get("curve_number"),
        "lst": ind.get("lst_mean_c"),
    }
    # Guard against the 2026-10-10 failure mode: a schema drift that parses
    # zero numeric scores must FAIL loudly, never print a table of "-".
    if not any(isinstance(v[k], (int, float))
               for k in ("impact", "flood", "heat", "green", "carbon")):
        rows.append((w, None, ["schema drift: parsed no numeric scores"]))
        continue
    rows.append((w, v, None))

ok = [(w, v) for w, v, e in rows if v]
bad = [(w, e) for w, v, e in rows if not v]
print()
print(f"assess succeeded for {len(ok)}/{len(WARDS)} wards")
if bad:
    print("failed:")
    for w, e in bad:
        print(f"    ward {w}: {e}")
print()

print("=" * 108)
print(f"{'ward':>5} {'impact':>7} {'flood':>6} {'heat':>6} {'green':>6} {'carbon':>7} "
      f"| {'built%':>7} {'veg%':>6} {'water%':>7} {'bare%':>6} {'CN':>6} {'LST':>6}")
print("=" * 108)
for w, v in ok:
    def g(k):
        x = v.get(k)
        return f"{x:.1f}" if isinstance(x, (int, float)) else "  -  "
    print(f"{w:>5} {g('impact'):>7} {g('flood'):>6} {g('heat'):>6} {g('green'):>6} "
          f"{g('carbon'):>7} | {g('built'):>7} {g('veg'):>6} {g('water'):>7} "
          f"{g('bare'):>6} {g('cn'):>6} {g('lst'):>6}")


def col(vals):
    import statistics as st
    xs = [v for v in vals if isinstance(v, (int, float))]
    return (f"min {min(xs):6.1f}  median {st.median(xs):6.1f}  max {max(xs):6.1f}  "
            f"spread {max(xs) - min(xs):6.1f}") if xs else "no data"


print()
print("DISPERSION per factor (is anything still compressed?)")
for k in ("impact", "flood", "heat", "green", "carbon"):
    print(f"  {k:<8} {col([v.get(k) for _, v in ok])}")

print()
import statistics as st  # noqa: E402


def pearson(x, y):
    pairs = [(a, b) for a, b in zip(x, y)
             if isinstance(a, (int, float)) and isinstance(b, (int, float))
             and not isinstance(a, bool) and not isinstance(b, bool)]
    if len(pairs) < 3:
        return float("nan"), 0
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((a - mx) * (b - my) for a, b in pairs) / len(pairs)
    den = st.pstdev(xs) * st.pstdev(ys)
    # A constant factor (collapsed signal) has zero variance: report r=nan
    # with full n, never ZeroDivisionError (fixed 2026-10-10 -- the sweep
    # died exactly when it should have reported compression).
    if den == 0:
        return float("nan"), len(pairs)
    return cov / den, len(pairs)


print()
print("CORRELATIONS -- does each score respond to the right driver?")
built = [v.get("built") for _, v in ok]
lst = [v.get("lst") for _, v in ok]
veg = [v.get("veg") for _, v in ok]
water = [v.get("water") for _, v in ok]
for name, xs, ys, want in [
    ("built%   -> flood ", built, [v.get("flood") for _, v in ok], "positive"),
    ("built%   -> heat  ", built, [v.get("heat") for _, v in ok], "positive"),
    ("lst C    -> heat  ", lst, [v.get("heat") for _, v in ok], "positive"),
    ("veg%     -> flood ", veg, [v.get("flood") for _, v in ok], "negative"),
    ("veg%     -> green ", veg, [v.get("green") for _, v in ok], "negative"),
    ("water%   -> flood ", water, [v.get("flood") for _, v in ok], "ambiguous"),
    ("bare%    -> flood ", [v.get("bare") for _, v in ok],
     [v.get("flood") for _, v in ok], "positive"),
]:
    r, n = pearson(xs, ys)
    print(f"  {name} r = {r:+.4f}  (n={n})   expected {want}")