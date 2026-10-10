"""Region-agnostic site scoring. Imports the live core, copies nothing.

Inputs are explicit paths + caller-resolved ward identity (your polygons,
your ids). Validates the region config first; refuses to score otherwise.
"""
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.region import validate_config  # noqa: E402
from ml_pipeline.core import scoring as S  # noqa: E402
from ml_pipeline.core.canopy import CanopyLedger, TreeRecord  # noqa: E402
from ml_pipeline.core.geometry import (  # noqa: E402
    polygon_area_m2, polygon_centroid, trees_in_ring,
)
from ml_pipeline.core.recommendations import (  # noqa: E402
    RecommendationEngine,
)


def indicators_from_cube_dict(ring: List[Any],
                              cube: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Satellite indicators for a ring from a cube dict (fractions->pct)."""
    if not cube:
        return {}
    if not ring or len(ring) < 3:
        raise ValueError("site_ring needs at least 3 points")
    centroid = polygon_centroid([(float(a), float(b)) for a, b in ring])
    cells = cube.get("cells") or {}
    key = f"{round(centroid[0], 3)}_{round(centroid[1], 3)}"
    cell = cells.get(key)
    if not cell:
        best, best_d = None, None
        from ml_pipeline.core.geometry import haversine_m
        for k, v in cells.items():
            try:
                lon_s, lat_s = k.split("_")
                d = haversine_m(centroid, (float(lon_s), float(lat_s)))
            except ValueError:
                continue
            if best_d is None or d < best_d:
                best, best_d = v, d
        cell = best if (best_d is not None and best_d < 2000.0) else None
    if not cell:
        return {}

    def pct(x: Any) -> float:
        try:
            return float(x) * 100.0
        except (TypeError, ValueError):
            return 0.0

    return {
        "impervious_pct": pct(cell.get("built_pct", 0.0)),
        "vegetation_pct": pct(cell.get("vegetation_pct", 0.0)),
        "water_pct": pct(cell.get("water_pct", 0.0)),
        "bare_pct": pct(cell.get("bare_season_pct",
                                 cell.get("bare_pct", 0.0))),
        "lst_mean_c": cell.get("lst_mean_c"),
        "lst_reference_c": cell.get("lst_reference_c"),
        "lst_max_c": cell.get("lst_max_c"),
        "lst_night_mean_c": cell.get("lst_night_mean_c"),
        "mean_slope_deg": cell.get("mean_slope_deg", 3.0),
        "dist_to_storm_drain_m": None,
    }


def score_site(*, region_config: Dict[str, Any],
               cube: Optional[Dict[str, Any]],
               tree_db_path: str,
               species_config: Dict[str, Any],
               materials_table: Dict[str, Any],
               site_ring: List[Any],
               ward_no: int,
               built_up_m2: float,
               plot_m2: float,
               materials: List[Dict[str, Any]],
               with_recommendations: bool = True) -> Dict[str, Any]:
    """Score one proposal. Returns score + recommendations + ledger."""
    validate_config(region_config)
    if built_up_m2 <= 0 or plot_m2 <= 0:
        raise ValueError("built_up_m2 and plot_m2 must be positive")
    if built_up_m2 > plot_m2:
        raise ValueError("built_up_m2 exceeds plot_m2")

    indicators = indicators_from_cube_dict(site_ring, cube)
    raw_trees = trees_in_ring(site_ring, Path(tree_db_path))
    # Record construction mirrors ml_pipeline/cli.py exactly.
    recs = [
        TreeRecord(
            tree_id=t["tree_id"], lon=t["lon"], lat=t["lat"],
            botanical_name=t["botanical_name"] or "",
            girth_cm=t["girth_cm"] or 0.0, height_m=t["height_m"] or 0.0,
            canopy_dia_m=t["canopy_dia_m"] or 0.0,
            condition=t["condition"] or "", is_rare=bool(t["is_rare"]),
        )
        for t in raw_trees
    ]
    ledger = CanopyLedger(species_config).process_site(
        recs, plot_area_m2=float(plot_m2))
    site = {"builtUpAreaSqm": float(built_up_m2),
            "plotAreaSqm": float(plot_m2), "materials": materials,
            "ward_no": ward_no,
            "site_area_m2": polygon_area_m2(
                [(float(a), float(b)) for a, b in site_ring])}
    result = S.score_project(site, dict(indicators), region_config,
                             materials_table, ledger)
    out: Dict[str, Any] = {"score": result, "ledger": ledger,
                           "indicators": indicators, "ward_no": ward_no}
    if with_recommendations:
        out["recommendations"] = RecommendationEngine(
            ).build_recommendations(site, dict(indicators), region_config,
                                    materials_table, ledger)
    return out
