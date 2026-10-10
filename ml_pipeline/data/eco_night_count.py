"""ECOSTRESS night usability recount over PMC (read-only, no cube changes).

Follows the verified recipe (2026-10-10): GEE bands LST/QC/cloud/water are
exact per the live catalog; cloud screening = cloud==0 AND QC bits 1&0 in
{00,01} (bitwiseAnd(3)<=1); night from system:time_start -> IST hour
(UTC+5:30), night = IST >= 18.5 or < 5.5. Reports:
  A: intersecting scenes, B: nominal night scenes, C: QC-clear night scenes
at >=50% and >=80% clear-pixel fractions over the PMC bbox.

Usage:
    PYTHONPATH=. .venv/bin/python ml_pipeline/data/eco_night_count.py [lo hi]
    lo/hi = IST hour window, defaults 18.5 5.5 (night). For the AFTERNOON
    peak-heat test use: eco_night_count.py 12.5 15.5
"""
import ee
import sys

BBOX = [73.7318, 18.3856, 74.0183, 18.6216]


def main() -> int:
    LO = float(sys.argv[1]) if len(sys.argv) > 1 else 18.5
    HI = float(sys.argv[2]) if len(sys.argv) > 2 else 5.5
    ee.Initialize()
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)
    col = (
        ee.ImageCollection("NASA/ECOSTRESS/L2T_LSTE/V2")
        .filterBounds(region)
        .filterDate("2024-01-01", "2025-01-01")
    )
    n_a = col.size().getInfo()
    print(f"A: intersecting scenes in 2024: {n_a}")

    def with_lhour(img):
        utc_h = ee.Number(ee.Date(img.get("system:time_start")).get("hour"))
        m = ee.Number(ee.Date(img.get("system:time_start")).get("minutes"))
        lhour = utc_h.add(m.divide(60.0)).add(5.5).mod(24)
        return img.set("lhour_ist", lhour)

    night = (
        col.map(with_lhour)
        .filter(ee.Filter.Or(
            ee.Filter.gte("lhour_ist", LO),
            ee.Filter.lt("lhour_ist", HI),
        ))
    ) if LO > HI else (
        col.map(with_lhour)
        .filter(ee.Filter.And(
            ee.Filter.gte("lhour_ist", LO),
            ee.Filter.lt("lhour_ist", HI),
        ))
    )
    label = "night" if (LO, HI) == (18.5, 5.5) else f"IST {LO}-{HI}"
    n_b = night.size().getInfo()
    print(f"B: nominal {label} scenes: {n_b}")

    def clear_frac(img):
        qa = img.select("QC")
        ok = (
            qa.bitwiseAnd(3).lte(1)
            .And(img.select("cloud").eq(0))
            .And(img.select("water").eq(0))
        )
        frac = ok.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=70,
            maxPixels=1_000_000_000,
        ).values().get(0)
        return img.set("clear_frac", frac)

    scored = night.map(clear_frac)
    fracs = scored.aggregate_array("clear_frac").getInfo()
    fracs_f = [float(x) if x is not None else 0.0 for x in fracs]
    import statistics
    print(f"scenes scored: {len(fracs_f)}")
    if fracs_f:
        print(f"clear_frac min/med/max: {min(fracs_f):.3f}/"
              f"{statistics.median(fracs_f):.3f}/{max(fracs_f):.3f}")
        n50 = sum(1 for x in fracs_f if x >= 0.5)
        n80 = sum(1 for x in fracs_f if x >= 0.8)
        print(f"C: QC-clear night scenes >=50%: {n50} | >=80%: {n80}")
        print("VERDICT:",
              "OPTION 1 VIABLE (>=10 clear nights)"
              if n50 >= 10 else
              "OPTION 1 NOT PROVEN -- fall back to thermal-anomaly index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
