"""Full-extent diagnostic of the land-cover partition, WITH labelled_fraction.

build_cube's gate refuses to write when any cell is outside tolerance, which is
correct behaviour but blocks the analysis needed to pick that tolerance. This
calls reduce_extent() directly and reports the whole distribution so the
tolerance can be set from measurement instead of guesswork.

The question being answered: over the pixels Dynamic World actually labelled,
do the nine classes account for everything? Two populations are expected:
  - hill cells where almost nothing is labelled (Sinhagad), and
  - reduction noise / partial masking in ordinary city cells.
They need different treatment and must not share one epsilon.
"""
import json
import statistics
import sys

import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024
PART = list(bc.PARTITION_BANDS)

out = bc.reduce_extent(
    lst=bc.surface_temperature(EPOCH),
    veg=bc.vegetation_indices(),
    dw=bc.dynamic_world_tree(EPOCH),
    terr=bc.terrain(),
    bare_season=bc.dynamic_world_bare_season(EPOCH),
)
cells = out["cells"] if isinstance(out, dict) and "cells" in out else out
print(f"cells returned: {len(cells)}", file=sys.stderr)

rows = []
for cid, row in cells.items():
    if not row:
        continue
    total = sum(float(row.get(b, 0.0)) for b in PART)
    lab = row.get("labelled_fraction")
    rows.append((cid, total, None if lab is None else float(lab), row))

labelled = [r for r in rows if r[2] is not None]
print(f"cells with labelled_fraction present: {len(labelled)}/{len(rows)}")
if labelled:
    v = [r[2] for r in labelled]
    print(f"  labelled_fraction  min {min(v):.4f}  p5 {sorted(v)[len(v)//20]:.4f}  "
          f"median {statistics.median(v):.4f}  max {max(v):.4f}")

raw = sorted(r[1] for r in rows)
print()
print("RAW 9-class sum:")
for q, lbl in [(0, "min"), (10, "p1"), (43, "p5"), (432, "median"),
               (-43, "p95"), (-10, "p99"), (-1, "max")]:
    print(f"  {lbl:<7} {raw[q]:.6f}")

print()
print("POPULATIONS")
low = [r for r in rows if r[1] < 0.5]
mid = [r for r in rows if 0.5 <= r[1] < 0.98]
near = [r for r in rows if 0.98 <= r[1] <= 1.02]
over = [r for r in rows if r[1] > 1.02]
print(f"  raw < 0.50 (mostly unlabelled terrain) : {len(low)}")
print(f"  0.50 <= raw < 0.98                     : {len(mid)}")
print(f"  0.98 <= raw <= 1.02                    : {len(near)}")
print(f"  raw > 1.02                             : {len(over)}")

print()
print("NORMALISED (raw / labelled_fraction) -- the real partition test")
norms = []
bad = []
for cid, total, lab, row in labelled:
    if lab is None or lab <= 0:
        continue
    n = total / lab
    norms.append(n)
    bad.append((abs(n - 1.0), cid, n, total, lab))
ns = sorted(norms)
print(f"  n={len(ns)}  min {ns[0]:.6f}  p1 {ns[len(ns)//100]:.6f}  "
      f"p5 {ns[len(ns)//20]:.6f}  median {statistics.median(ns):.6f}  max {ns[-1]:.6f}")
for eps in (0.002, 0.005, 0.01, 0.02, 0.05, 0.10):
    print(f"    cells outside +/-{eps:<6}: "
          f"{sum(1 for d, *_ in bad if d > eps)}")

print()
print("WORST 12 by normalised deviation (for cause analysis)")
bad.sort(reverse=True)
for d, cid, n, total, lab in bad[:12]:
    row = dict((k, v) for k, v in next(r for r in rows if r[0] == cid)[3].items()
               if k in PART and v)
    print(f"  {cid}  norm={n:.4f}  raw={total:.4f}  labelled={lab:.4f}")
    print(f"     {row}")

# Persist for offline reuse so the tolerance decision is reproducible.
json.dump({cid: {"raw": t, "labelled": l, "bands": r}
           for cid, t, l, r in rows},
          open("/tmp/partition_full.json", "w"), indent=1)
print()
print("wrote /tmp/partition_full.json", file=sys.stderr)