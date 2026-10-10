"""What does `multi_band_image.reduce(ee.Reducer.sum())` actually return?

`ee.Image.reduce()` applies a single-input reducer to EACH band independently
unless the reducer shares inputs -- so a 9-band image reduced by `Reducer.sum()`
may come back as 9 separate sums, not one total. That would explain
`labelled_fraction` being small and only ever a shortfall.

This prints the band list and per-band values at a known cell, and compares the
candidate constructions against ground truth (the cell mean of the one-hot sum).
"""
import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024
dw = bc.dynamic_world_tree(EPOCH)
names = list(bc.DW_CLASSES.values())
per_class = dw.select(names)

print("per_class bandNames:", per_class.bandNames().getInfo())

red = per_class.reduce(ee.Reducer.sum())
print("reduce(sum) bandNames:", red.bandNames().getInfo())
print("reduce(sum) band count:", len(red.bandNames().getInfo()))

renamed = red.rename("labelled_fraction")
print("rename('labelled_fraction') bandNames:", renamed.bandNames().getInfo())
print("rename band count:", len(renamed.bandNames().getInfo()))

# Cell 73.8443_18.4351: built .3406, trees .1236, crops .2025, shrub .3333 -> sum 1.0000
cell = ee.Geometry.Rectangle([73.8398, 18.4306, 73.8488, 18.4396],
                             proj="EPSG:4326", geodesic=False)

print()
print("per-band reduce(sum) values at that cell:")
print(" ", red.reduceRegion(ee.Reducer.sum(), cell, 30, maxPixels=1e9).getInfo())

print()
print("mean of each class band at that cell:")
print(" ", per_class.reduceRegion(ee.Reducer.mean(), cell, 30, maxPixels=1e9).getInfo())

print()
print("GROUND TRUTH via single-pixel sum of the reduced bands:")
gt = per_class.reduceRegion(ee.Reducer.sum(), ee.Geometry.Point([73.8443, 18.4351]),
                            30, maxPixels=1e9).getInfo()
print("  single pixel:", gt, "-> total", sum(gt.values()))

print()
print("single-pixel value of labelled_fraction via rename:")
v = renamed.select("labelled_fraction").reduceRegion(
    ee.Reducer.mean(), ee.Geometry.Point([73.8443, 18.4351]), 30, maxPixels=1e9).getInfo()
print(" ", v, "   (should be 1.0)")

print()
print("single-pixel value of labelled_fraction via reduce(sum).select(first):")
first = red.select(ee.Reducer.sum().name(0))
print("  band names:", first.bandNames().getInfo())
print("  value:", first.reduceRegion(ee.Reducer.mean(),
                                     ee.Geometry.Point([73.8443, 18.4351]),
                                     30, maxPixels=1e9).getInfo())

print()
print("CORRECT construction -- totalPixels-weighted share of labelled pixels:")
# One-hot label image: 1 where labelled, 0 elsewhere. Built by summing all nine,
# which requires an explicit total: use Reducer.sum() with combine, or simply
# sum the bands pairwise.
tot = per_class.select(names[0])
for n in names[1:]:
    tot = tot.addBands(per_class.select(n))
total_img = tot.reduce(ee.Reducer.sum())
print("  pairwise-add then reduce(sum) bandNames:", total_img.bandNames().getInfo())
print("  single pixel:", total_img.reduceRegion(
    ee.Reducer.mean(), ee.Geometry.Point([73.8443, 18.4351]), 30, maxPixels=1e9).getInfo())
print("  hill cell  :", total_img.reduceRegion(
    ee.Reducer.mean(), ee.Geometry.Point([73.7633, 18.4351]), 30, maxPixels=1e9).getInfo())