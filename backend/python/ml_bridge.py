"""Adapter between the Node API and the ML pipeline.

Three modes, selected by the request payload:

  * Extraction mode (default, when ``coordinates`` is present and no ``ward``
    / ``mode`` is given): runs the GEE + SegFormer extractor. Requires
    ``GEE_PROJECT_ID`` and ``MODEL_PATH``.

  * Scoring mode (when ``mode == "score"`` or ``ward`` is present): runs the
    deterministic scorer on a ward + site proposal. Needs no network and no
    model weights -- only the baked artefacts (epoch cube, reference layers,
    tree index, materials/species config). Returns the full ``score_project``
    result plus recommendations and the canopy ledger.

  * Air quality mode (when ``mode == "air_quality"``): fetches real
    Open-Meteo data for Pune via Python, cached on disk (Node HTTPS is
    unreliable in this env).

All modes read JSON from stdin and print JSON to stdout, so the Node side
can use the same spawn plumbing for both.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml_pipeline.paths import cache_dir, data_dir, demo_wards  # noqa: E402


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


_AQ_CACHE_PATH = cache_dir() / "air_quality_cache.json"
_AQ_CACHE_TTL_S = 3600  # 1 hour — Open-Meteo forecast updates hourly
_AQ_FAILURE_BACKOFF_S = 600  # after a failed fetch, serve the last reading for 10 min

# Some hosts are rate-limited by Open-Meteo (HTTP 429 from shared cloud IPs).
# The image therefore bakes the last measured reading into the demo pack, and a
# failed fetch serves it -- with the timestamp it was taken -- instead of
# blanking the tab. A stale measured reading is honest; an empty tab is not.


def _aq_read_cache() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(_AQ_CACHE_PATH.read_text())
    except Exception:
        return None


def _aq_serve_cache(cached: Dict[str, Any], reason: Optional[str] = None) -> Dict[str, Any]:
    """Return a stored reading, marked ``stale``, rather than going UNAVAILABLE."""
    out = dict(cached)
    fetched_at = out.pop("_fetched_at", None)
    out.pop("_failed_at", None)
    out["cache"] = {
        "hit": True,
        "stale": True,
        "age_s": int(time.time() - fetched_at) if fetched_at else None,
    }
    if reason:
        out["cache"]["reason"] = reason
    out["unavailable"] = False
    return out


def _run_air_quality(request: Dict[str, Any]) -> Dict[str, Any]:
    """Current + historical air quality for Pune, served through a 1-hour cache.

    Each call pulls ~2 years of hourly PM2.5 (several MB) and the backend spawns
    a fresh Python process per request, so without a disk cache every page load
    pays the full fetch. Fresh cache -> Open-Meteo -> last measured reading.
    """
    cached = _aq_read_cache()
    now = time.time()
    if cached:
        fetched_at = cached.get("_fetched_at") or 0
        failed_at = cached.get("_failed_at") or 0
        if now - fetched_at < _AQ_CACHE_TTL_S and not failed_at:
            fresh = dict(cached)
            fresh.pop("_fetched_at", None)
            fresh.pop("_failed_at", None)
            fresh["cache"] = {"hit": True, "age_s": int(now - fetched_at)}
            return fresh
        if failed_at and now - failed_at < _AQ_FAILURE_BACKOFF_S:
            return _aq_serve_cache(
                cached,
                "Open-Meteo is rate-limiting this host; showing the last measured "
                "reading.",
            )
    try:
        return _aq_fetch()
    except Exception as e:
        if cached:
            cached["_failed_at"] = now
            try:
                _AQ_CACHE_PATH.write_text(json.dumps(cached))
            except Exception:
                pass  # cache write failure is non-fatal
            return _aq_serve_cache(cached, str(e))
        return {"unavailable": True, "reason": str(e)}


def _aq_fetch() -> Dict[str, Any]:
    """Fetch current + 2 years of hourly PM2.5 from Open-Meteo."""
    # Fetch 2 years of hourly data for monthly comparison
    hist_url = ("https://air-quality-api.open-meteo.com/v1/air-quality"
                "?latitude=18.5204&longitude=73.8567"
                "&hourly=pm2_5,pm10"
                "&start_date=2025-01-01&end_date=2026-11-07&timezone=Asia/Kolkata")
    with urllib.request.urlopen(hist_url, timeout=30) as resp:
        hist_data = json.load(resp)

    hourly = hist_data.get("hourly", {})
    times = hourly.get("time", [])
    pm25 = hourly.get("pm2_5", [])
    pm10 = hourly.get("pm10", [])

    # Monthly averages
    months_pm25 = {}
    months_pm10 = {}
    for i, t in enumerate(times):
        day = t[:7]  # YYYY-MM
        if pm25[i] is not None:
            months_pm25.setdefault(day, []).append(pm25[i])
        if pm10[i] is not None:
            months_pm10.setdefault(day, []).append(pm10[i])

    monthly_2025 = {}
    monthly_2026 = {}
    for m in sorted(months_pm25):
        avg = round(sum(months_pm25[m]) / len(months_pm25[m]), 1)
        if m.startswith("2025"):
            monthly_2025[m] = avg
        else:
            monthly_2026[m] = avg

    # Current month (Nov 2026) daily averages
    current_month_daily = {}
    for i, t in enumerate(times):
        if t.startswith("2026-11") and pm25[i] is not None:
            day = t[:10]
            current_month_daily.setdefault(day, []).append(pm25[i])
    current_month = {d: round(sum(v)/len(v), 1) for d, v in sorted(current_month_daily.items())}

    # Previous month (Oct 2026) daily averages
    prev_month_daily = {}
    for i, t in enumerate(times):
        if t.startswith("2026-10") and pm25[i] is not None:
            day = t[:10]
            prev_month_daily.setdefault(day, []).append(pm25[i])
    prev_month = {d: round(sum(v)/len(v), 1) for d, v in sorted(prev_month_daily.items())}

    # Yearly averages
    y2025_vals = [v for m, vs in months_pm25.items() if m.startswith("2025") for v in vs]
    y2026_vals = [v for m, vs in months_pm25.items() if m.startswith("2026") for v in vs]
    yearly_2025 = round(sum(y2025_vals) / len(y2025_vals), 1) if y2025_vals else None
    yearly_2026 = round(sum(y2026_vals) / len(y2026_vals), 1) if y2026_vals else None

    # Current (last 24h) - fetch forecast
    forecast_url = ("https://air-quality-api.open-meteo.com/v1/air-quality"
                    "?latitude=18.5204&longitude=73.8567"
                    "&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"
                    "&timezone=Asia/Kolkata&forecast_days=3")
    with urllib.request.urlopen(forecast_url, timeout=15) as resp:
        fdata = json.load(resp)
    fh = fdata.get("hourly", {})
    ftimes = fh.get("time", [])
    fpm25 = fh.get("pm2_5", [])
    fpm10 = fh.get("pm10", [])
    fco = fh.get("carbon_monoxide", [])
    fno2 = fh.get("nitrogen_dioxide", [])
    fso2 = fh.get("sulphur_dioxide", [])
    fo3 = fh.get("ozone", [])

    # Current = last available non-None pm25
    idx = len(ftimes) - 1
    while idx >= 0 and (fpm25[idx] is None):
        idx -= 1
    if idx < 0:
        idx = len(ftimes) - 1

    current = {
        "pm25": fpm25[idx] if idx < len(fpm25) else None,
        "pm10": fpm10[idx] if idx < len(fpm10) else None,
        "co": fco[idx] if idx < len(fco) else None,
        "no2": fno2[idx] if idx < len(fno2) else None,
        "so2": fso2[idx] if idx < len(fso2) else None,
        "o3": fo3[idx] if idx < len(fo3) else None,
        "time": ftimes[idx] if idx < len(ftimes) else None,
    }

    # Hourly series (last 24h)
    hourly_series = fpm25[-24:] if len(fpm25) >= 24 else fpm25

    # Daily forecast
    daily_forecast = []
    days = {}
    for i, t in enumerate(ftimes):
        day = t[:10]
        if fpm25[i] is not None:
            days.setdefault(day, []).append(fpm25[i])
    for day in sorted(days.keys()):
        daily_forecast.append({"day": day, "avg": round(sum(days[day]) / len(days[day]), 1)})

    # AQI from PM2.5 (Indian standard)
    def pm25_aqi(v):
        if v is None: return None
        if v <= 30: return round(v * 50 / 30)
        if v <= 60: return round(50 + (v - 30) * 50 / 30)
        if v <= 90: return round(100 + (v - 60) * 100 / 30)
        if v <= 120: return round(200 + (v - 90) * 100 / 30)
        if v <= 250: return round(300 + (v - 120) * 100 / 130)
        return round(400 + (v - 250) * 100 / 130)

    aqi = pm25_aqi(current["pm25"]) or 0

    result = {
        "source": "open-meteo-air-quality",
        "city": "Pune",
        "geo": [18.5204, 73.8567],
        "aqi": aqi,
        "dominant": "pm25",
        "iaqi": {
            "pm25": {"v": current["pm25"]},
            "pm10": {"v": current["pm10"]},
            "co": {"v": current["co"]},
            "no2": {"v": current["no2"]},
            "so2": {"v": current["so2"]},
            "o3": {"v": current["o3"]},
        },
        "time": current["time"],
        "iso": current["time"],
        "attributions": [{"name": "Open-Meteo Air Quality API", "url": "https://open-meteo.com/en/docs/air-quality-api"}],
        "hourly": hourly_series,
        "daily": [d["avg"] for d in daily_forecast],
        "daily_forecast": daily_forecast,
        "stations": [{"station": "Pune (Open-Meteo)", "city": "Pune", "geo": [18.5204, 73.8567], "aqi": aqi, "dominant": "pm25", "iaqi": {"pm25": {"v": current["pm25"]}, "pm10": {"v": current["pm10"]}}, "time": current["time"], "iso": current["time"], "attributions": [], "forecast": {}}],
        "unavailable": False,
        "historical": {
            "monthly_2025": monthly_2025,
            "monthly_2026": monthly_2026,
            "yearly_2025": yearly_2025,
            "yearly_2026": yearly_2026,
            "current_month_daily": current_month,
            "prev_month_daily": prev_month,
        },
        "cache": {"hit": False, "age_s": 0},
    }
    try:
        to_cache = dict(result)
        to_cache["_fetched_at"] = time.time()
        _AQ_CACHE_PATH.write_text(json.dumps(to_cache))
    except Exception:
        pass  # cache write failure is non-fatal
    return result


def _ward_ring(ward_no: int) -> Optional[List[Any]]:
    import sqlite3

    ref_db = data_dir() / "reference_layers.sqlite"
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

    ref_db = data_dir() / "reference_layers.sqlite"
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


_CANOPY_CACHE_PATH = cache_dir() / "canopy_ledger_cache.json"

def _canopy_ledger(ring: List[Any], plot_area_m2: float, ward_no: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Build a canopy ledger if the tree index is available, else None.

    Per-ward aggregate cache (species counts, action counts, canopy m2): the
    census scan of ~100k trees is identical for every request in the same
    ward, and only the two cover-% values depend on the plot area. Cached
    aggregates are exact re-uses of a prior full computation, written once
    and reused after; decisions sample kept for the API trim.
    """
    repository_root = _repository_root()
    sys.path.insert(0, str(repository_root))
    from ml_pipeline.core.canopy import CanopyLedger, TreeRecord
    from ml_pipeline.core import geometry as G

    plot = max(1.0, float(plot_area_m2))
    if ward_no is not None:
        try:
            if _CANOPY_CACHE_PATH.exists():
                cache = json.loads(_CANOPY_CACHE_PATH.read_text())
                agg = cache.get(str(int(ward_no)))
                if agg:
                    ledger = {k: v for k, v in agg.items() if not k.startswith("_")}
                    before = agg.get("_canopy_before_m2") or 0.0
                    after = agg.get("_canopy_after_m2") or 0.0
                    ledger["canopy_cover_pct"] = round(min(100.0, before / plot * 100.0), 1)
                    ledger["canopy_cover_pct_proposed"] = round(min(100.0, after / plot * 100.0), 1)
                    return ledger
        except Exception:
            pass  # corrupt cache — recompute

    tree_db = data_dir() / "tree_index.sqlite"
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

    if ward_no is not None:
        try:
            agg = {k: v for k, v in ledger.items() if k != "decisions"}
            agg["_canopy_before_m2"] = ledger.get("tree_canopy_m2_before") or 0.0
            agg["_canopy_after_m2"] = ledger.get("tree_canopy_m2_after") or 0.0
            decisions = ledger.get("decisions") or []
            agg["_decisions_count"] = len(decisions)
            agg["_decisions_sample"] = decisions[:25]
            # Do not store the full decisions in the cache either — re-attach sample.
            agg["decisions_count"] = len(decisions)
            agg["decisions_sample"] = decisions[:25]
            agg["decisions_note"] = (
                f"per-tree decisions summarized for the API response; "
                f"{len(decisions)} total, first 25 kept as a deterministic sample (cached)"
            )
            cache: Dict[str, Any] = {}
            if _CANOPY_CACHE_PATH.exists():
                try:
                    cache = json.loads(_CANOPY_CACHE_PATH.read_text())
                except Exception:
                    cache = {}
            cache[str(int(ward_no))] = agg
            _CANOPY_CACHE_PATH.write_text(json.dumps(cache))
        except Exception:
            pass  # cache write failure is non-fatal
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
    pack = demo_wards()
    if ward_no is not None and pack and int(ward_no) not in pack:
        raise ValueError(
            f"Ward {int(ward_no)} is not in this deployment. This build ships the "
            f"demo pack for wards {', '.join(str(w) for w in pack)}; the other "
            f"wards need the full census index built locally."
        )
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

    cube_path = data_dir() / "epoch_cube.json"
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

    ledger = _canopy_ledger(ring, geom.area_m2, ward_no=ward_no if isinstance(ward_no, int) else (int(ward_no) if ward_no is not None else None))

    result = S.score_project(v.site, indicators, region, materials_table, ledger=ledger)
    recs = RecommendationEngine().build_recommendations(
        v.site, indicators, region, materials_table, ledger
    )

    # The per-tree decision list can hold tens of thousands of entries (the 2019
    # census covers the whole ward ring — ward 12 alone yields ~70k). Summarize it
    # for the API response; the full list remains available through the CLI and
    # report paths. Scoring and recommendations above already consumed it.
    if isinstance(ledger, dict) and isinstance(ledger.get("decisions"), list):
        decisions = ledger.pop("decisions")
        ledger["decisions_count"] = len(decisions)
        ledger["decisions_sample"] = decisions[:25]
        ledger["decisions_note"] = (
            "per-tree decisions summarized for the API response; "
            f"{len(decisions)} total, first 25 kept as a deterministic sample"
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
    if mode == "air_quality":
        result = _run_air_quality(request)
    elif mode == "score" or request.get("ward") is not None or request.get("geometry"):
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
