"""GEDI RH95 vs census canopy, per ward (read-only, no cube changes).

Independent satellite cross-check of census canopy magnitudes (WRI-India
2024 rejected the census as ground truth over geolocation errors). Uses
GEE L2A monthly rasters (LARSE/GEDI/GEDI02_A_002_MONTHLY, bands rh95 /
quality_flag / degrade_flag, all verified 2026-10-10), quality mask
quality==1 & degrade==0, median RH95 composite Nov 2019-Feb 2023
(archive only; skips the Mar 2023-Apr 2024 hibernation gap), reduced to
mean + footprint count per ward polygon parsed from pmc_wards_2025.kml.

Compares DISTRIBUTIONS, never point-to-point: GEDI is sparse (~25 m
shots, few % of land) and measures height, not cover. Wards where dense
census canopy meets near-zero GEDI height (or vice versa) are flagged
for human review -- they are suspects, not verdicts.

Usage:
    PYTHONPATH=. .venv/bin/python ml_pipeline/data/gedi_ward_check.py
Writes /tmp/gedi_ward.csv
"""
import csv
import os
import xml.etree.ElementTree as ET

import ee

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KML = os.path.join(REPO, "pmc_wards_2025.kml")
OUT = "/tmp/gedi_ward.csv"
NS = "{http://www.opengis.net/kml/2.2}"


def parse_wards(path):
    tree = ET.parse(path)
    wards = []
    for pm in tree.getroot().iter(NS + "Placemark"):
        qwr = None
        for sd in pm.iter(NS + "SimpleData"):
            if sd.get("name") == "qwr" and (sd.text or "").strip():
                try:
                    qwr = int(float(sd.text.strip()))
                except ValueError:
                    pass
        rings = []
        for coords in pm.iter(NS + "coordinates"):
            pts = []
            for tup in (coords.text or "").strip().split():
                parts = tup.split(",")
                if len(parts) >= 2:
                    pts.append([float(parts[0]), float(parts[1])])
            if len(pts) >= 4:
                rings.append(pts)
        if qwr and rings:
            geom = ee.Geometry.Polygon(rings[0]) if len(rings) == 1 \
                else ee.Geometry.MultiPolygon([[r] for r in rings])
            wards.append(ee.Feature(geom, {"ward": qwr}))
    return ee.FeatureCollection(wards)


def main() -> int:
    ee.Initialize()
    wards = parse_wards(KML)
    print("wards parsed:", wards.size().getInfo())

    gedi = (
        ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY")
        .filterBounds(ee.Geometry.Rectangle(
            [73.7318, 18.3856, 74.0183, 18.6216],
            proj="EPSG:4326", geodesic=False))
        .filterDate("2019-11-01", "2023-03-01")
        .map(lambda im: im.updateMask(im.select("quality_flag").eq(1))
             .updateMask(im.select("degrade_flag").eq(0))
             .select("rh95"))
    )
    n = gedi.size().getInfo()
    print("GEDI monthly images in window:", n)
    comp = gedi.median().rename("rh95_med")

    # Per-ward SEQUENTIAL reduceRegions (2026-10-10): a single 41-feature
    # reduceRegions over the 40-image median returned all-null means while
    # the identical computation on 1-2 wards returns real values (w12: 48
    # shots @14.75 m, w4: 217 @8.18 m) -- per-request compute budget, not a
    # data gap. Sequential calls are slower (~10 min) but each is the exact
    # call already proven to work. Any ward that still yields null is
    # re-tried once, then recorded as NO_DATA (a logged fact, not a zero).
    ward_list = sorted(wards.getInfo()["features"],
                       key=lambda x: x["properties"]["ward"])
    import time
    results = []
    for feat in ward_list:
        wno = feat["properties"]["ward"]
        geom = ee.Geometry(feat["geometry"])
        val, cnt = None, 0
        for attempt in (1, 2):
            try:
                r = comp.reduceRegion(
                    ee.Reducer.mean().combine(ee.Reducer.count(), "", True),
                    geom, 25).getInfo()
                # Key names vary by call shape: the renamed band yields
                # rh95_med_mean/rh95_med_count; single-band reductions can
                # come back as mean/count or rh95_mean/rh95_count. Read all.
                val = r.get("rh95_med_mean",
                            r.get("rh95_mean", r.get("mean")))
                cnt = r.get("rh95_med_count",
                            r.get("rh95_count", r.get("count", 0))) or 0
                if val is not None:
                    break
            except Exception as e:  # noqa: BLE001 -- per-ward isolation
                print(f"ward {wno} attempt {attempt} failed: "
                      f"{type(e).__name__}")
            time.sleep(5)
        results.append((wno, val, cnt))
        print(f"ward {wno}: mean={val} n={cnt}", flush=True)
        time.sleep(5)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ward", "gedi_rh95_mean_m", "gedi_footprints"])
        for wno, val, cnt in results:
            w.writerow([wno, round(val, 2) if val is not None else "NO_DATA",
                        cnt])
    scored = sum(1 for _, v, _ in results if v is not None)
    print(f"wards with GEDI cover: {scored}/{len(results)} -> {OUT}")
    print("NEXT: join against ward_tree_profile canopy per ward; flag "
          "divergences as suspects, not verdicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
