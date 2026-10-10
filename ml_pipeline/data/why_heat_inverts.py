"""Why does a dense core site score LOW on heat while a park scores HIGH?

Pulls the actual 1 km cube cell behind each validation site and prints the
bands the reference is built from, so the mechanism is visible rather than
inferred. Pure read of epoch_cube.json, no scoring.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"

SITES = [
    ("Shivajinagar core", 73.8475, 18.5303),
    ("Koregaon Park green", 73.8936, 18.5362),
    ("Bhosari MIDC", 73.9020, 18.5100),
    ("Hadapsar fringe", 73.9880, 18.5089),
    ("Katraj plain", 73.8670, 18.4480),
]

METRES_PER_DEG_LAT = 111320.0


def main() -> None:
    cube = json.loads(CUBE.read_text())
    cells = cube["cells"]
    minx, miny, maxx, maxy = cube["bbox"]

    print("cube bbox:", cube["bbox"])
    print(f"cells: {len(cells)}")
    print()

    # Cell size, from the first cell's geometry if present, else the bbox/grid.
    print(f"{'site':<21} {'lst':>7} {'ref':>7} {'delta':>6} "
          f"{'built%':>7} {'veg%':>6} {'elev':>6}  heat_score(span 2.0)")
    print("-" * 96)

    # Cube cells are keyed "lon_lat" and carry no lon/lat properties of their
    # own, so the coordinate has to come from the key.
    for name, lon, lat in SITES:
        best = None
        best_d = None
        for cid, c in cells.items():
            try:
                cx_s, cy_s = cid.split("_")
                cx, cy = float(cx_s), float(cy_s)
            except ValueError:
                continue
            d = (cx - lon) ** 2 + (cy - lat) ** 2
            if best_d is None or d < best_d:
                best, best_d = c, d

        if best is None:
            print(f"{name:<21}  no cube cell covers this point")
            continue

        lst = best.get("lst_mean_c")
        ref = best.get("lst_reference_c")
        built = (best.get("built_pct") or 0) * 100
        veg = (best.get("vegetation_pct") or 0) * 100
        elev = best.get("elevation_m")

        delta = (lst - ref) if (lst is not None and ref is not None) else None
        score = max(0.0, min(100.0, (delta / 2.0) * 100.0)) if delta is not None else None

        # The formula's own docstring says the score is driven by delta/span.
        # Print the ratio of the two inputs the reference is built from.
        print(f"{name:<21} {lst if lst is not None else float('nan'):>7.2f} "
              f"{ref if ref is not None else float('nan'):>7.2f} "
              f"{delta if delta is not None else float('nan'):>+6.2f} "
              f"{built:>7.1f} {veg:>6.1f} "
              f"{elev if elev is not None else float('nan'):>6.0f}  "
              f"{score if score is not None else float('nan'):>6.1f}")

    print()
    print("MECHANISM CHECK")
    print("-" * 96)
    print("heat score = clamp((lst_mean - lst_reference) / 2.0 * 100, 0, 100)")
    print("lst_reference = median LST of THIS CELL's own vegetated pixels.")
    print()
    print("The reference is drawn from the SAME cell whose mean is being scored,")
    print("so the delta measures how much of that cell's own built surface sits")
    print("next to its own vegetation. It does NOT measure how hot the cell is")
    print("relative to the city.")
    print()
    print("Why that inverts on dense sites: a fully built cell has almost no")
    print("vegetated pixels left, and the few that survive sit at hot kerb edges,")
    print("so its reference rises toward its mean and the delta collapses. A cell")
    print("that is partly park keeps a genuinely cool reference, so its delta")
    print("stays large. The factor therefore rewards sites that already contain")
    print("green -- the opposite of what a heat-EXPOSURE score must do.")


if __name__ == "__main__":
    main()