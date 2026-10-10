"""Engine self-test: any-region scoring on synthetic fixtures.

Builds a complete fake region (2x2 grid, scaffold config, 3-tree census)
in a temp dir and scores a site through engine/score.py. Run:
    .venv/bin/python engine/tests/test_engine.py
"""
import csv
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine import census as EC  # noqa: E402
from engine import region as ER  # noqa: E402
from engine import score as ES  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, extra=""):
    results.append((PASS if cond else FAIL, name, extra))
    print(f"  {PASS if cond else FAIL}  {name} {extra}")


def main() -> int:
    print("engine self-test (synthetic region, no satellites)")
    with tempfile.TemporaryDirectory() as tmp:
        spec = ER.RegionSpec(region_id="demo", display_name="Demo City",
                             bbox=[0.0, 0.0, 0.018, 0.018], cell_deg=0.009,
                             utm_epsg="EPSG:32643")
        grid = ER.make_grid(spec.bbox, spec.cell_deg)
        check("grid is 2x2", len(grid) == 4, f"({len(grid)} cells)")
        check("grid ids are 3dp centres",
              all(c["id"] == f"{round(c['centre'][0], 3)}_"
                  f"{round(c['centre'][1], 3)}" for c in grid))

        cfg_path = os.path.join(tmp, "regions", "demo.json")
        ER.write_config_scaffold(spec, cfg_path)
        cfg = json.load(open(cfg_path))
        check("scaffold validates", ER.validate_config(cfg) is True)
        check("scaffold marks storm provisional",
              cfg["hydrology"]["design_storm_status"]
              == "PROVISIONAL_UNVERIFIED")
        bad = dict(cfg)
        bad["weights"] = {"flood": 1.0, "heat": 1.0,
                          "green": 1.0, "carbon": 1.0}
        try:
            ER.validate_config(bad)
            check("bad weights rejected", False)
        except ValueError:
            check("bad weights rejected", True)

        # Synthetic cube: one dense cell, one green cell.
        dense = {"built_pct": 0.9, "vegetation_pct": 0.05,
                 "water_pct": 0.0, "bare_pct": 0.05,
                 "tree_canopy_pct": 0.02, "lst_mean_c": 40.0,
                 "lst_reference_c": 38.0, "lst_max_c": 42.0,
                 "lst_night_mean_c": 22.0, "elevation_m": 500.0}
        green = {"built_pct": 0.1, "vegetation_pct": 0.7,
                 "water_pct": 0.05, "bare_pct": 0.05,
                 "tree_canopy_pct": 0.4, "lst_mean_c": 33.0,
                 "lst_reference_c": 32.5, "lst_max_c": 34.0,
                 "lst_night_mean_c": 19.0, "elevation_m": 510.0}
        cube = {"cells": {grid[0]["id"]: dense, grid[1]["id"]: green,
                          grid[2]["id"]: green, grid[3]["id"]: green}}
        ring = [[grid[0]["bounds"][0], grid[0]["bounds"][1]],
                [grid[0]["bounds"][2], grid[0]["bounds"][1]],
                [grid[0]["bounds"][2], grid[0]["bounds"][3]],
                [grid[0]["bounds"][0], grid[0]["bounds"][3]]]
        ind = ES.indicators_from_cube_dict(ring, cube)
        check("indicators read dense cell",
              ind["impervious_pct"] == 90.0
              and ind["vegetation_pct"] == 5.0, str(ind))
        check("empty cube yields no indicators",
              ES.indicators_from_cube_dict(ring, None) == {})

        # Tiny census with foreign headers -> normalise -> index.
        raw = os.path.join(tmp, "census_raw.csv")
        with open(raw, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["especie", "perimetro_cm", "diametro_copa_m",
                        "lon", "lat"])
            cx, cy = grid[0]["centre"]
            w.writerow(["Azadirachta indica", "120", "8", cx, cy])
            w.writerow(["Mangifera indica", "40", "5", cx + 0.001, cy])
            w.writerow(["Ficus religiosa", "30", "6", 5.0, 5.0])  # far away
        canon = os.path.join(tmp, "canon.csv")
        EC.normalize_csv(raw, canon, {"botanical_name": "especie",
                                      "girth_cm": "perimetro_cm",
                                      "canopy_dia_m": "diametro_copa_m",
                                      "easting": "lon", "northing": "lat"})
        db = os.path.join(tmp, "trees.sqlite")
        stats = EC.build_index([canon], db, source_label="Demo 2024",
                               census_year=2024)
        import sqlite3
        nrows = sqlite3.connect(db).execute(
            "select count(*) from trees").fetchone()[0]
        check("3 trees indexed", nrows == 3, f"(rows={nrows})")
        meta = dict(sqlite3.connect(db).execute(
            "select key, value from meta").fetchall())
        check("caller meta stamped",
              meta.get("census_source") == "Demo 2024"
              and meta.get("census_year") == "2024", str(meta))

        species = {"legal": {"heritage_girth_cm": 90.0,
                             "age_girth_cm_per_year": 2.0},
                   "non_native": {}, "native_priority": [],
                   "transplant_hardy": [],
                   "transplant_hardy_ceiling_cm": 45}
        table = json.load(open(
            "ml_pipeline/config/materials.json"))
        mats = [{"name": "cement_opc", "quantityKg": 10000.0}]
        out = ES.score_site(
            region_config=cfg, cube=cube, tree_db_path=db,
            species_config=species, materials_table=table, site_ring=ring,
            ward_no=1, built_up_m2=500.0, plot_m2=2000.0, materials=mats)
        sc = out["score"]
        check("score completes", sc.get("complete") is True,
              str(sc.get("missing_factors")))
        check("flood responds to density",
              sc["factors"]["flood"]["score"] > 50,
              str(sc["factors"]["flood"]["score"]))
        check("ledger saw site trees",
              out["ledger"].get("canopy_cover_pct", 0) > 0,
              str(out["ledger"].get("canopy_cover_pct")))
        check("recommendations built",
              "recommendations" in out)
        out2 = ES.score_site(
            region_config=cfg, cube=cube, tree_db_path=db,
            species_config=species, materials_table=table, site_ring=ring,
            ward_no=1, built_up_m2=500.0, plot_m2=2000.0, materials=mats,
            with_recommendations=False)
        check("deterministic",
              out2["score"]["impact_score"] == sc["impact_score"])
        try:
            ES.score_site(
                region_config=cfg, cube=cube, tree_db_path=db,
                species_config=species, materials_table=table,
                site_ring=ring, ward_no=1, built_up_m2=5000.0,
                plot_m2=2000.0, materials=mats)
            check("built>plot rejected", False)
        except ValueError:
            check("built>plot rejected", True)
        for bad_bbox in (None, [0, 0], [1, 1, 0, 0]):
            try:
                ER.make_grid(bad_bbox, 0.009)
                check(f"bbox {bad_bbox} rejected", False)
            except ValueError:
                check(f"bbox {bad_bbox} rejected", True)
        for bad_cell in (0, -0.01, 0.0005):
            try:
                ER.make_grid([0, 0, 1, 1], bad_cell)
                check(f"cell_deg {bad_cell} rejected", False)
            except ValueError:
                check(f"cell_deg {bad_cell} rejected", True)
        nan_cfg = json.loads(json.dumps(cfg))
        nan_cfg["weights"] = {"flood": float("nan"), "heat": 0.3,
                              "green": 0.2, "carbon": 0.2}
        try:
            ER.validate_config(nan_cfg)
            check("NaN weights rejected", False)
        except ValueError:
            check("NaN weights rejected", True)
        try:
            ES.indicators_from_cube_dict([], cube)
            check("empty ring rejected", False)
        except ValueError:
            check("empty ring rejected", True)

    bad_n = sum(1 for r, _, _ in results if r == FAIL)
    print(f"{len(results) - bad_n}/{len(results)} passed")
    return 1 if bad_n else 0


if __name__ == "__main__":
    raise SystemExit(main())
