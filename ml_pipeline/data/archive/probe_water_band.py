"""Is `water` actually lost in the image, or only in the stored cube?

GSW (independent source) says the Sinhagad cell is 99% permanent water. Dynamic
World's mode says water. Yet the cube stores water_pct = 0.000000 for it, with
labelled_fraction = 0.033. Both cannot hold.

This isolates the band construction: build the nine one-hot bands exactly as
dynamic_world_tree does, then reduce them over the Sinhagad cell with the same
reducer and tileScale the build uses. It also checks what `unmask(0)` is doing
to the mask, because `unmask` restores the band VALUE but keeps the original
mask, and a masked band silently reduces to nothing.
"""
import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024
dw = bc.dynamic_world_tree(EPOCH)

GRID = {f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}": c
        for c in bc.grid_cells()}
CID = "73.7633_18.4351"
c = GRID[CID]
geom = ee.Geometry.Rectangle([c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
                            proj="EPSG:4326", geodesic=False)
print(f"cell {CID}: lon {c['lon0']}..{c['lon1']}  lat {c['lat0']}..{c['lat1']}")
print()

names = list(bc.DW_CLASSES.values())
print("STEP 1 -- what does the mode image itself say over this cell?")
coll = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
        .filterBounds(ee.Geometry.Rectangle(bc.BBOX, proj="EPSG:4326",
                                            geodesic=False)))
print(f"  images in collection: {coll.size().getInfo()}")
mode = coll.select("label").mode()
hist = mode.reduceRegion(ee.Reducer.frequencyHistogram(), geom, 30,
                         maxPixels=1e9).getInfo()
print(f"  label histogram over the cell: {hist}")

print()
print("STEP 2 -- per-class one-hot mean, built by hand (no unmask)")
onehot = []
for code, name in bc.DW_CLASSES.items():
    onehot.append(mode.eq(code).rename(name))
manual = ee.Image(onehot)
v = manual.reduceRegion(ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()
print("  manual one-hot (masked, no unmask):")
for k, val in sorted(v.items()):
    print(f"    {k:<22} {val}")

print()
print("STEP 3 -- same but with .unmask(0), as dynamic_world_tree does")
onehot2 = [mode.eq(code).unmask(0).rename(name)
           for code, name in bc.DW_CLASSES.items()]
manual2 = ee.Image(onehot2)
v2 = manual2.reduceRegion(ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()
print("  with unmask(0):")
for k, val in sorted(v2.items()):
    print(f"    {k:<22} {val}")

print()
print("STEP 4 -- masks")
m = manual.mask().reduceRegion(ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()
m2 = manual2.mask().reduceRegion(ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()
print(f"  manual  mask fraction: { {k: round(x, 4) for k, x in m.items()} }")
print(f"  unmask  mask fraction: { {k: round(x, 4) for k, x in m2.items()} }")
print()
print("STEP 5 -- the production function's own water band, in isolation")
wp = dw.select("water")
print(f"  water band mask fraction: "
      f"{wp.mask().reduceRegion(ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()}")
print(f"  water_pct (renamed band) : "
      f"{dw.select('water_pct').reduceRegion(ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()}")

print()
print("=" * 74)
print("STEP 6 -- is `water_pct` on the image actually a RENAME of water, or")
print("a DIFFERENT band? Two bands can share a name across constructions.")
print("=" * 74)
print("  image band names:", dw.bandNames().getInfo())
for b in ("water", "water_pct"):
    if b in dw.bandNames().getInfo():
        val = dw.select(b).reduceRegion(ee.Reducer.mean(), geom, 30,
                                        maxPixels=1e9).getInfo()
        print(f"    {b:<12} -> {val}")
    else:
        print(f"    {b:<12} -> ABSENT")