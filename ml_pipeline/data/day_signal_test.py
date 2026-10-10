"""Aqua-day signal test over PMC (read-only, no cube changes).

Aqua (MYD11A1) day overpass ~1:30pm local -- near the diurnal SUHI peak,
unlike Landsat's ~11am. Same product family and QC pattern as the live
night branch (LST_Day_1km x0.02, keep QC_Day bits 0-1 <= 1, drop fill 0).

Reports, for 2024 over the PMC bbox:
  A: day scenes intersecting, B: median clear-day count,
  C: city-mean day LST, rural-ring day LST, city-scale delta,
  D: r(built% -> day LST), r(veg% -> day LST) using Dynamic World 2024
     built/vegetation at 1 km.
Bar for building the day cube layer (same as night): correctly signed
city delta > +1 C and |r| > 0.5 with the physical drivers.

Usage:
    PYTHONPATH=. .venv/bin/python ml_pipeline/data/day_signal_test.py
"""
import ee

BBOX = [73.7318, 18.3856, 74.0183, 18.6216]
RURAL_PAD = 0.09  # ~10 km halo outside the bbox


def main() -> int:
    ee.Initialize()
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)
    halo = ee.Geometry.Rectangle(
        [BBOX[0] - RURAL_PAD, BBOX[1] - RURAL_PAD,
         BBOX[2] + RURAL_PAD, BBOX[3] + RURAL_PAD],
        proj="EPSG:4326", geodesic=False)

    def day_masked(col):
        def f(im):
            qa = im.select("QC_Day")
            m = qa.bitwiseAnd(3).lte(1)
            lst = (im.select("LST_Day_1km").multiply(0.02)
                     .subtract(273.15).updateMask(m))
            return lst.rename("day").set(
                "n", m.reduceRegion(ee.Reducer.sum(), region, 1000)
                .values().get(0))
        return col.map(f)

    col = (ee.ImageCollection("MODIS/061/MYD11A1")
           .filterBounds(region).filterDate("2024-01-01", "2025-01-01"))
    print("A: Aqua day scenes intersecting PMC bbox:", col.size().getInfo())

    masked = day_masked(col)
    comp = masked.median()
    n = masked.aggregate_array("n").getInfo()
    n = sorted(x or 0 for x in n)
    import statistics
    print(f"B: per-scene clear-pixel count med: {statistics.median(n):.0f} "
          f"(bbox pixels at 1km ~ {int((BBOX[2]-BBOX[0])*111*(BBOX[3]-BBOX[1])*111)})")

    city = comp.reduceRegion(ee.Reducer.mean(), region, 1000).getInfo()
    # Rural ring: vegetated Dynamic World pixels in the halo outside bbox.
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
          .filterBounds(halo).filterDate("2024-01-01", "2025-01-01")
          .select("label").mode())
    veg = dw.remap([0, 1, 2, 3, 4, 5, 6, 7, 8],
                   [0, 1, 1, 1, 1, 1, 0, 0, 0])
    ring = halo.difference(region, 100)
    rural = comp.updateMask(veg).reduceRegion(
        ee.Reducer.mean(), ring, 1000, maxPixels=1_000_000_000).getInfo()
    city_c = city.get("day")
    rur_c = rural.get("day")
    print(f"C: city day mean {city_c:.2f} C | rural vegetated ring {rur_c:.2f} C "
          f"| delta {city_c - rur_c:+.2f} C (YCEO daytime anchor: check sign)")

    # Driver correlations at 1 km cells over the bbox.
    built = dw.remap([0, 1, 2, 3, 4, 5, 6, 7, 8],
                     [0, 0, 0, 0, 0, 0, 1, 0, 0]).rename("built")
    samp = (comp.addBands(built).addBands(veg.rename("veg"))
            .sample(region=region, scale=1000, numPixels=600,
                    geometries=False))
    import math

    def pearson(pairs, ix, iy):
        xs = [p[ix] for p in pairs if p[ix] is not None and p[iy] is not None]
        ys = [p[iy] for p in pairs if p[ix] is not None and p[iy] is not None]
        n_ = len(xs)
        mx, my = sum(xs) / n_, sum(ys) / n_
        dx = [x - mx for x in xs]
        dy = [y - my for y in ys]
        den = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
        return sum(a * b for a, b in zip(dx, dy)) / den if den else float("nan"), n_

    pairs = [(f["properties"].get("day"), f["properties"].get("built"),
              f["properties"].get("veg")) for f in samp.getInfo()["features"]]
    rb, nb = pearson([(b, d) for d, b, v in pairs], 0, 1)
    rv, nv = pearson([(v, d) for d, b, v in pairs], 0, 1)
    print(f"D: r(built -> aqua-day) = {rb:+.4f} (n={nb})  expect positive")
    print(f"   r(veg   -> aqua-day) = {rv:+.4f} (n={nv})  expect negative")
    ok = (city_c - rur_c) > 1.0 and rb > 0.5 and rv < -0.5
    print("VERDICT:", "DAY SIGNAL - build the layer" if ok
          else "DAY WEAK - do not build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
