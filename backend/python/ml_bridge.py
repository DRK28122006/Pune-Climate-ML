"""Adapter between the Node API and the ML pipeline.

Two modes, selected by the request payload:

  * Extraction mode (default, when ``coordinates`` is present and no ``ward``
    / ``mode`` is given): runs the GEE + SegFormer extractor. Requires
    ``GEE_PROJECT_ID`` and ``MODEL_PATH``.

  * Scoring mode (when ``mode == "score"`` or ``ward`` is present): runs the
    deterministic scorer on a ward + site proposal. Needs no network and no
    model weights -- only the baked artefacts (epoch cube, reference layers,
    tree index, materials/species config). Returns the full ``score_project``
    result plus recommendations and the canopy ledger.

Both modes read JSON from stdin and print JSON to stdout, so the Node side
can use the same spawn plumbing for both.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_extraction(request: Dict[str, Any]) -> Dict[str, Any]:
    repository_root = _repository_root()
    sys.path.insert(0, str(repository_root))

    from ml_pipeline.extractor import PuneExtractor

    coordinates = request.get("coordinates")
    if not coordinates:
        raise ValueError("coordinates are required when ML_MODE=python (extraction)")

    project_id = os.environ.get("GEE_PROJECT_ID")
    model_path = os.environ.get("MODEL_PATH")
    if not project_id or not model_path:
        raise ValueError("GEE_PROJECT_ID and MODEL_PATH are required for extraction mode")

    extractor = PuneExtractor(project_id, model_path)
    result = extractor.extract(
        coordinates["lat"],
        coordinates["lon"],
        request.get("bufferM", 500),
    )
    return {**result, "source": "gee-segformer"}


def _ward_ring(ward_no: int) -> Optional[List[Any]]:
    import sqlite3

    ref_db = _repository_root() / "ml_pipeline" / "data" / "reference_layers.sqlite"
    if not ref_db.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{ref_db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT ring_json FROM wards WHERE ward_no = ?", (ward_no,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def _ward_for_point(lat: float, lon: float) -> Optional[int]:
    """Find the ward containing a point via point-in-polygon against reference layers."""
    import sqlite3
    from shapely.geometry import Point, Polygon

    ref_db = _repository_root() / "ml_pipeline" / "data" / "reference_layers.sqlite"
    if not ref_db.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{ref_db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        for ward_no, ring_json in conn.execute("SELECT ward_no, ring_json FROM wards"):
            try:
                ring = json.loads(ring_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if len(ring) < 3:
                continue
            try:
                poly = Polygon(ring)
                if poly.is_valid and poly.contains(Point(lon, lat)):
                    return int(ward_no)
            except Exception:
                continue
    finally:
        conn.close()
    return None


def _indicators_from_cube(ring: List[Any], cube: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Satellite indicators for a ring from the baked cube (fractions -> pct)."""
    repository_root = _repository_root()
    sys.path.insert(0, str(repository_root))
    from ml_pipeline.core import geometry as G

    if not cube or not ring or len(ring) < 3:
        return {}
    centroid = G.polygon_centroid([(float(a), float(b)) for a, b in ring])
    cell = G.cube_cell_for_point(cube, centroid[0], centroid[1])
    if not cell:
        return {}

    def pct(x: Any) -> Optional[float]:
        if x is None:
            return None
        try:
            return float(x) * 100.0
        except (TypeError, ValueError):
            return None

    return {
        "impervious_pct": pct(cell.get("built_pct")),
        "vegetation_pct": pct(cell.get("vegetation_pct")),
        "water_pct": pct(cell.get("water_pct")),
        "bare_pct": pct(cell.get("bare_pct")),
        "bare_season_pct": pct(cell.get("bare_season_pct")),
        "lst_mean_c": cell.get("lst_mean_c"),
        "lst_reference_c": cell.get("lst_reference_c"),
        "lst_max_c": cell.get("lst_max_c"),
        "lst_night_mean_c": cell.get("lst_night_mean_c"),
        "lst_night_reference_c": cell.get("lst_night_reference_c"),
        "mean_slope_deg": cell.get("mean_slope_deg", cell.get("slope_deg")),
        "dist_to_storm_drain_m": None,
        "landcover_source": "epoch_cube",
    }


def _canopy_ledger(ring: List[Any], plot_area_m2: float) -> Optional[Dict[str, Any]]:
    """Build a canopy ledger if the tree index is available, else None."""
    repository_root = _repository_root()
    sys.path.insert(0, str(repository_root))
    from ml_pipeline.core.canopy import CanopyLedger, TreeRecord
    from ml_pipeline.core import geometry as G

    tree_db = repository_root / "ml_pipeline" / "data" / "tree_index.sqlite"
    if not tree_db.exists():
        return None
    try:
        trees_raw = G.trees_in_ring(ring, tree_db)
    except Exception:
        return None
    ledger_engine = CanopyLedger(
        json.loads((repository_root / "ml_pipeline" / "config" / "species.json").read_text())
    )
    records = [
        TreeRecord(
            tree_id=t["tree_id"],
            lon=t["lon"],
            lat=t["lat"],
            botanical_name=t.get("botanical_name") or "",
            girth_cm=t.get("girth_cm") or 0.0,
            height_m=t.get("height_m") or 0.0,
            canopy_dia_m=t.get("canopy_dia_m") or 0.0,
            condition=t.get("condition") or "",
            is_rare=bool(t.get("is_rare")),
        )
        for t in trees_raw
    ]
    ledger = ledger_engine.process_site(records, plot_area_m2=plot_area_m2)
    # Census coverage is a hard precondition for any tree-derived figure.
    try:
        coverage = G.census_coverage()
        ledger["census_coverage"] = coverage
        ledger["census_reliable_for_this_site"] = bool(coverage.get("coverage_complete", False)) or len(trees_raw) > 0
    except Exception:
        ledger["census_coverage"] = {"coverage_complete": False}
        ledger["census_reliable_for_this_site"] = len(trees_raw) > 0
    return ledger


def _run_scoring(request: Dict[str, Any]) -> Dict[str, Any]:
    repository_root = _repository_root()
    sys.path.insert(0, str(repository_root))

    import json as _json

    from ml_pipeline.core import scoring as S
    from ml_pipeline.core.recommendations import RecommendationEngine
    from ml_pipeline.intake.validate import validate_submission

    config_dir = repository_root / "ml_pipeline" / "config"
    region = _json.loads((config_dir / "regions" / "pune.json").read_text())
    materials_table = _json.loads((config_dir / "materials.json").read_text())

    ward_no = request.get("ward")
    ring = None
    coords = request.get("coordinates")
    if ward_no is not None:
        ring = _ward_ring(int(ward_no))
    elif coords:
        lat = coords.get("lat") if isinstance(coords, dict) else (coords[0] if isinstance(coords, (list, tuple)) else None)
        lon = coords.get("lon") if isinstance(coords, dict) else (coords[1] if isinstance(coords, (list, tuple)) else None)
        if lat is not None and lon is not None:
            ward_no = _ward_for_point(float(lat), float(lon))
            if ward_no is not None:
                ring = _ward_ring(ward_no)
    elif request.get("geometry"):
        ring = request["geometry"]
    if not ring:
        raise ValueError("ward, coordinates, or geometry is required for scoring")

    built_up = float(request.get("builtUpAreaSqm", 2000.0))
    plot = float(request.get("plotAreaSqm", 4000.0))

    payload = {
        "geometry": [[float(a), float(b)] for a, b in ring],
        "builtUpAreaSqm": built_up,
        "plotAreaSqm": plot,
        "materials": request.get("materials", []),
        "storeys": request.get("storeys"),
        "projectType": request.get("projectType"),
        "epoch": request.get("epoch", 2024),
    }
    v = validate_submission(payload, region)
    if not v.valid:
        raise ValueError("validation failed: " + "; ".join(e["message"] for e in v.errors))
    geom = v.geometry
    if geom is None:
        raise ValueError("geometry could not be measured")

    cube_path = repository_root / "ml_pipeline" / "data" / "epoch_cube.json"
    cube = None
    if cube_path.exists():
        try:
            cube = _json.loads(cube_path.read_text())
        except _json.JSONDecodeError:
            cube = None

    sat = _indicators_from_cube(ring, cube)

    # Land-cover assumptions (explicit user inputs when no cube).
    assumption_fields: List[str] = []
    if sat.get("built_pct") is None and request.get("impervious") is not None:
        assumption_fields.append("impervious_pct")
    if sat.get("vegetation_pct") is None and request.get("vegetation") is not None:
        assumption_fields.append("vegetation_pct")
    if sat.get("water_pct") is None and request.get("water") is not None:
        assumption_fields.append("water_pct")
    landcover_source = (
        "user_supplied_assumption" if assumption_fields
        else "epoch_cube" if sat else "unavailable"
    )

    def _pct_cube_or_fallback(cube_value, fallback):
        if cube_value is not None:
            try:
                return float(cube_value) * 100.0
            except (TypeError, ValueError):
                pass
        if fallback is None:
            return None
        return float(fallback)

    indicators = {
        "impervious_pct": _pct_cube_or_fallback(sat.get("built_pct", sat.get("impervious_pct")), request.get("impervious")),
        "vegetation_pct": _pct_cube_or_fallback(sat.get("vegetation_pct"), request.get("vegetation")),
        "water_pct": _pct_cube_or_fallback(sat.get("water_pct"), request.get("water")),
        "bare_pct": (float(sat["bare_pct"]) * 100.0) if sat.get("bare_pct") is not None else None,
        "bare_season_pct": (float(sat["bare_season_pct"]) * 100.0) if sat.get("bare_season_pct") is not None else None,
        "landcover_source": landcover_source,
        "landcover_assumptions": assumption_fields,
        "lst_mean_c": sat.get("lst_mean_c"),
        "lst_reference_c": sat.get("lst_reference_c"),
        "lst_max_c": sat.get("lst_max_c"),
        "lst_night_mean_c": sat.get("lst_night_mean_c"),
        "lst_night_reference_c": sat.get("lst_night_reference_c"),
        "mean_slope_deg": (request.get("slope") if request.get("slope") is not None
                           else sat.get("mean_slope_deg", sat.get("slope_deg"))),
        "dist_to_storm_drain_m": None,
    }

    ledger = _canopy_ledger(ring, geom.area_m2)

    result = S.score_project(v.site, indicators, region, materials_table, ledger=ledger)
    recs = RecommendationEngine().build_recommendations(
        v.site, indicators, region, materials_table, ledger
    )

    return {
        "source": "ml-pipeline-scorer",
        "mode": "score",
        "ward": ward_no,
        "validation": v.to_dict(),
        "score": result,
        "recommendations": (recs.get("recommendations", []) if isinstance(recs, dict) else (recs or [])),
        "canopy": ledger,
        "indicators": indicators,
        "satellite_cube_available": bool(cube),
        "epoch": request.get("epoch", 2024),
    }


def main() -> None:
    request = json.load(sys.stdin)
    mode = request.get("mode")
    if mode == "score" or request.get("ward") is not None or request.get("geometry"):
        result = _run_scoring(request)
    else:
        result = _run_extraction(request)
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
