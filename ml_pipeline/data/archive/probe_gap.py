"""Explain the 44 cells where raw != labelled_fraction.

reduce(sum) is confirmed correct (1 band, value 1 at a labelled pixel). Yet
raw (sum of the nine class means) / labelled_fraction is as low as 0.9400 in
cell 73.8893_18.5431. Since both are cell means of the same per-pixel one-hot
sum, they must be equal. They are not, so something differs between the two
reductions.

Prints, for that cell:
  - each class mean
  - the labelled_fraction mean
  - their difference
  - the per-pixel histogram of the one-hot sum (must be 0 or 1)
  - totalPixels, to see whether the two bands are being reduced over the SAME
    pixel set (different denominators would explain a pure ratio gap)
"""
import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024
dw = bc.dynamic_world_tree(EPOCH)
names = list(bc.DW_CLASSES.values())
per_class = dw.select(names)
labelled = per_class.reduce(ee.Reducer.sum()).rename("labelled_fraction")

WORST = [
    (73.8848, 18.5386, "73.8893_18.5431 norm=0.9400"),
    (73.8938, 18.5386, "73.8983_18.5431 norm=0.9446"),
]
GOOD = (73.8398, 18.4306, "73.8443_18.4351 (control, norm=1.0000)")

for lon, lat, label in WORST + [GOOD]:
    pt = ee.Geometry.Point([lon, lat])
    cell = ee.Geometry.Rectangle([lon - 0.0045, lat - 0.0045,
                                  lon + 0.0045, lat + 0.0045],
                                 proj="EPSG:4326", geodesic=False)
    print(f"--- {label} ---")
    cm = per_class.reduceRegion(ee.Reducer.mean(), cell, 30, maxPixels=1e9).getInfo()
    lm = labelled.reduceRegion(ee.Reducer.mean(), cell, 30, maxPixels=1e9).getInfo()
    tp = ee.Image.constant(1).reduceRegion(
        ee.Reducer.sum(), cell, 30, maxPixels=1e9).getInfo().get("constant", 0)

    raw = sum(v for v in cm.values() if v is not None)
    lab = lm.get("labelled_fraction")
    print(f"  class means : " + ", ".join(
        f"{k}={v:.5f}" for k, v in sorted(cm.items()) if v))
    print(f"  raw sum     : {raw:.6f}")
    print(f"  labelled    : {lab:.6f}")
    print(f"  raw/label   : {raw / lab:.6f}   diff {raw - lab:+.6f}")
    print(f"  totalPixels : {tp}")

    # histogram of the one-hot sum: must be {0, 1}, never in between
    hist = ee.Image.constant(1).addBands(labelled).reduceRegion(
        ee.Reducer.frequencyHistogram(), cell, 30, maxPixels=1e9
    ).getInfo()
    print(f"  one-hot sum histogram: {hist.get('constant')}")
    print()

print("If the histogram shows values other than 0 and 1, the majority vote is")
print("not producing a one-hot label and the shortfall is real missing land")
print("cover rather than reduction noise.")
print("If totalPixels differs between bands, the two means have different")
print("denominators and the ratio gap is an artefact of masking, not structure.")