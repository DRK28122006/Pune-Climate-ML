"""Heat coverage check: ECOSTRESS night count + UHII/YCEO Pune lookup.

Read-only. Makes no changes to the cube. Evidence for the heat-factor
decision (AGENT_HANDOFF.md section 6): does a night-time product exist
over PMC, or do we fall back to a thermal-anomaly index?

Usage:
    PYTHONPATH=. .venv/bin/python ml_pipeline/data/heat_coverage_check.py
"""
import ee

BBOX = [73.7318, 18.3856, 74.0183, 18.6216]
CENTROID = [73.875, 18.5036]  # approx PMC centre
EPOCH = 2024


def main() -> int:
    ee.Initialize()
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)
    pt = ee.Geometry.Point(CENTROID)

    print("=== 1. ECOSTRESS L2T_LSTE V2 over PMC, 2024 ===")
    try:
        eco = (
            ee.ImageCollection("NASA/ECOSTRESS/L2T_LSTE/V2")
            .filterBounds(region)
            .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
        )
        n = eco.size().getInfo()
        print(f"total ECOSTRESS scenes intersecting PMC bbox in {EPOCH}: {n}")
        if n and n > 0:
            # Overpass hour histogram (UTC). IST = UTC + 5:30.
            # Night IST (18:00-06:00) ~= UTC 12:30-00:30.
            scenes = eco.toList(min(n, 200)).getInfo()
            from collections import Counter
            import datetime

            hours = Counter()
            for s in scenes:
                ts = s.get("properties", {}).get("system:time_start")
                if ts:
                    hours[datetime.datetime.utcfromtimestamp(ts / 1000).hour] += 1
            print(f"sampled {len(scenes)} scenes; UTC hour histogram:")
            for h in sorted(hours):
                print(f"  UTC {h:02d}:00  n={hours[h]}")
            print("night IST ~= UTC 12:30-00:30; day IST ~= UTC 00:30-12:30")
    except Exception as e:
        print(f"ECOSTRESS query failed: {type(e).__name__}: {e}")

    print("\n=== 2. UHII global dataset (Yang et al. 2024) at PMC centroid ===")
    for coll in ["MOD1", "MOD2", "MYD1", "MYD2", "SAT", "SMOD2", "SMYD1"]:
        cid = f"projects/sat-io/open-datasets/UHII/{coll}"
        try:
            ic = ee.ImageCollection(cid)
            size = ic.size().getInfo()
            first = ic.first()
            val = first.reduceRegion(
                reducer=ee.Reducer.first(), geometry=pt, scale=1000
            ).getInfo()
            keys = list(val.keys())[:6]
            sample = {k: val[k] for k in keys}
            print(f"{coll}: size={size}, sample@{CENTROID}: {sample}")
        except Exception as e:
            print(f"{coll}: FAILED {type(e).__name__}: {str(e)[:160]}")

    print("\n=== 3. Yale YCEO v4 yearly averaged at PMC centroid ===")
    try:
        yceo = ee.ImageCollection("YALE/YCEO/UHI/UHI_yearly_averaged/v4")
        print(f"YCEO size: {yceo.size().getInfo()}")
        first = yceo.first()
        val = first.reduceRegion(
            reducer=ee.Reducer.first(), geometry=pt, scale=1000
        ).getInfo()
        keys = list(val.keys())[:10]
        print(f"bands: {first.bandNames().getInfo()}")
        print(f"sample@{CENTROID}: " + str({k: val.get(k) for k in keys}))
    except Exception as e:
        print(f"YCEO query failed: {type(e).__name__}: {str(e)[:300]}")

    print("\nDone. Interpret: ECOSTRESS night n>=~10 clear scenes => option 1 viable;")
    print("else UHII/YCEO Pune present => option 2; else neither.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
