"""Derive design-storm candidates from IMD 0.25-degree gridded rainfall.

Reads RF25_indYYYY_rfp25.nc (1901-2024, RAINFALL[TIME,LATITUDE,LONGITUDE],
-999 = missing) from /tmp/opencode/imd, extracts the annual-maximum
1-day series at the Pune cell nearest 18.53N 73.86E (18.50N 73.75E),
fits Gumbel (EV1 -- the distribution Vivekanandan 2022 selects for Pune)
and GEV for comparison, and reports return-period quantiles with
bootstrap 95% intervals. Writes the measured annual-maximum series to
ml_pipeline/data/imd_pune_annual_max.csv (in-repo evidence); prints
numbers for a human to adopt -- adopts nothing itself.

References: Chow/Maidment/Mays (1988) Ch.12 (annual-maximum series,
return period); Hosking (1990) L-moments; Das et al. (2022) MAUSAM
(Gumbel IDF for Indian cities incl. 100-yr 24-h); Pai et al. (2014)
for the gridded product itself.

Usage:
    .venv/bin/python ml_pipeline/data/derive_design_storm.py [/tmp/opencode/imd]
"""
import csv
import glob
import math
import os
import statistics
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/imd"
LON0, DLON, NLON = 66.5, 0.25, 135
LAT0, DLAT, NLAT = 6.5, 0.25, 129
PLON, PLAT = 73.86, 18.53  # Pune station


def load_annual_max(src):
    from scipy.io import netcdf_file
    import warnings
    warnings.filterwarnings("ignore")
    li = int(round((PLON - LON0) / DLON))
    lai = int(round((PLAT - LAT0) / DLAT))
    series = {}
    files = sorted(glob.glob(os.path.join(src, "RF25_ind*_rfp25.nc")))
    print(f"files: {len(files)}, pune cell: "
          f"{LON0 + li * DLON:.2f}E {LAT0 + lai * DLAT:.2f}N", flush=True)
    for f in files:
        try:
            year = int(f.split("_ind")[1][:4])
        except (IndexError, ValueError):
            print(f"odd filename skipped: {os.path.basename(f)}")
            continue
        try:
            with netcdf_file(f, "r", mmap=False) as nc:
                d = nc.variables["RAINFALL"][:, lai, li].copy()
        except Exception as e:  # noqa: BLE001 -- per-file isolation
            print(f"{year}: unreadable ({type(e).__name__}), skipped")
            continue
        d = [float(x) for x in d]
        valid = [x for x in d if x >= 0.0]
        if len(valid) < 300:
            print(f"{year}: only {len(valid)} valid days, skipped")
            continue
        series[year] = max(valid)
    return series


def gumbel_quantiles(xs):
    from scipy import stats
    loc, scale = stats.gumbel_r.fit(xs)
    ks = stats.kstest(xs, lambda q: stats.gumbel_r.cdf(q, loc, scale))
    out = {"loc": loc, "scale": scale, "ks_D": ks.statistic,
           "ks_p": ks.pvalue}
    for T in (10, 25, 50, 100):
        p = 1.0 - 1.0 / T
        out[T] = float(stats.gumbel_r.ppf(p, loc, scale))
    return out


def gev_quantiles(xs):
    from scipy import stats
    c, loc, scale = stats.genextreme.fit(xs)
    ks = stats.kstest(xs, lambda q: stats.genextreme.cdf(q, c, loc, scale))
    out = {"shape": c, "loc": loc, "scale": scale, "ks_D": ks.statistic,
           "ks_p": ks.pvalue}
    for T in (10, 25, 50, 100):
        out[T] = float(stats.genextreme.ppf(1.0 - 1.0 / T, c, loc, scale))
    return out


def main() -> int:
    series = load_annual_max(SRC)
    yrs = sorted(series)
    xs = [series[y] for y in yrs]
    print(f"annual maxima: n={len(xs)} ({yrs[0]}-{yrs[-1]}), "
          f"min={min(xs):.1f} med={statistics.median(xs):.1f} "
          f"max={max(xs):.1f} "
          f"(max year {yrs[xs.index(max(xs))]})")
    # Persist the measured series in-repo (tiny CSV): evidence must survive
    # /tmp wipes. Recompute with: derive_design_storm.py /tmp/opencode/imd
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "imd_pune_annual_max.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "annual_max_1day_mm", "grid_cell",
                    "product", "method"])
        for y in yrs:
            w.writerow([y, round(series[y], 2), "18.50N_73.75E",
                        "IMD_RF25_0.25deg_1901-2024", "cell annual maximum"])
    print(f"annual-maximum series saved: {csv_path} ({len(yrs)} years)")
    print(f"observed >120mm years: "
          f"{sum(1 for x in xs if x > 120)}; >150mm: "
          f"{sum(1 for x in xs if x > 150)}")

    g = gumbel_quantiles(xs)
    print(f"GUMBEL loc={g['loc']:.2f} scale={g['scale']:.2f} "
          f"KS D={g['ks_D']:.4f} p={g['ks_p']:.4f}")
    v = gev_quantiles(xs)
    print(f"GEV shape={v['shape']:+.4f} loc={v['loc']:.2f} scale={v['scale']:.2f} "
          f"KS D={v['ks_D']:.4f} p={v['ks_p']:.4f}")
    for T in (10, 25, 50, 100):
        print(f"T={T:>3}y: gumbel {g[T]:7.1f} mm | gev {v[T]:7.1f} mm")

    # Parametric bootstrap 95% interval on the Gumbel 100-yr value.
    # Seeded via NumPy (fixed 2026-10-10: random.seed() never seeded the
    # np-backed rvs draws, so intervals were non-reproducible).
    import numpy as np
    from scipy import stats
    rng = np.random.default_rng(2026)
    boots = []
    for _ in range(2000):
        samp = list(stats.gumbel_r.rvs(g["loc"], g["scale"],
                                       size=len(xs), random_state=rng))
        l2, s2 = stats.gumbel_r.fit(samp)
        boots.append(float(stats.gumbel_r.ppf(0.99, l2, s2)))
    boots.sort()
    print(f"gumbel 100-yr 95% interval: "
          f"{boots[50]:.1f} .. {boots[1950]:.1f} mm (2000 bootstraps)")
    print("NOTE: adopt nothing from this printout alone -- the human picks "
          "the return period and the distribution (EV1 per Vivekanandan "
          "for Pune) before any config change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
