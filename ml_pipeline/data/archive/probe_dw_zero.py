"""Confirm Dynamic World's class-0-is-water bug and find the correct validity mask.

`dynamic_world_tree` does:

    def keep(image):
        return image.updateMask(image.select("label").neq(0))

Dynamic World's nine classes are {0 water, 1 trees, 2 grass, 3 flooded_vegetation,
4 crops, 5 shrub_and_scrub, 6 built, 7 bare, 8 snow_and_ice}. So code 0 is WATER,
not "no data". Masking `label != 0` therefore deletes every water pixel from the
image -- which is why water_pct is 0 in all 864 cells and why labelled_fraction
read 0.033 on a cell that JRC GSW independently says is 99% permanent water.

This prints the available Dynamic World bands to find the real validity mask
(`water_mask` is the documented one), and measures how many pixels the buggy
keep() was deleting.
"""
import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024

img = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(
    f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01").filterBounds(
    ee.Geometry.Rectangle(bc.BBOX, proj="EPSG:4326", geodesic=False)).first()

print("Dynamic World V1 bands:")
print(" ", img.bandNames().getInfo())
print()

CID = "73.7633_18.4351"
GRID = {f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}": c
        for c in bc.grid_cells()}
c = GRID[CID]
geom = ee.Geometry.Rectangle([c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
                            proj="EPSG:4326", geodesic=False)

print(f"cell {CID} -- JRC GSW says 99% permanent water here")
print()

# 1. What fraction of pixels does the buggy keep() delete?
coll_all = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
            .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
            .filterBounds(ee.Geometry.Rectangle(bc.BBOX, proj="EPSG:4326",
                                                geodesic=False)))
label_mean = coll_all.select("label").mean().rename("label_mean")
wm = coll_all.select("water_mask").mean().rename("water_mask_mean")

stats = ee.Image.cat([label_mean, wm]).reduceRegion(
    ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()
print(f"  mean label         over cell: {stats.get('label_mean'):.6f}")
print(f"  mean water_mask    over cell: {stats.get('water_mask_mean'):.6f}")
print()
print("  water_mask ~1 everywhere means the scene is valid, so the pixels the")
print("  buggy keep() dropped were VALID pixels that merely happened to be water.")
print()

# 2. Confirm the correct mask restores water.
print("label histogram WITHOUT the buggy keep (raw Dynamic World):")
hist = coll_all.select("label").mode().reduceRegion(
    ee.Reducer.frequencyHistogram(), geom, 30, maxPixels=1e9).getInfo()
print(" ", hist)
print()
print("  code 0 dominating = water. The buggy keep() masked exactly those.")
print()

# 3. Does water_mask exist and is it a real validity flag?
print("water_mask value distribution over the cell:")
wmh = coll_all.select("water_mask").mode().reduceRegion(
    ee.Reducer.frequencyHistogram(), geom, 30, maxPixels=1e9).getInfo()
print(" ", wmh)

# 4. Candidate fix: keep = mask by water_mask, then majority vote.
fixed = coll_all.map(lambda im: im.updateMask(im.select("water_mask")))
mode_fixed = fixed.select("label").mode()
onehot = [mode_fixed.eq(c0).rename(n) for c0, n in bc.DW_CLASSES.items()]
vals = ee.Image(onehot).reduceRegion(
    ee.Reducer.mean(), geom, 30, maxPixels=1e9).getInfo()
print()
print("with keep() = water_mask, class fractions at that cell:")
tot = 0.0
for k, v in sorted(vals.items(), key=lambda kv: -kv[1]):
    print(f"    {k:<22} {v:.6f}")
    tot += v or 0
print(f"    {'SUM':<22} {tot:.6f}")