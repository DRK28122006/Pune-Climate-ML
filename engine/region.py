"""Region scaffolding: grid + config template + validation.

No satellites here: make_grid defines the cell layout any cube build must
fill; write_config_scaffold writes a regions/<id>.json with UNSOURCED
placeholders wherever a cited number is required. validate_config is the
gate -- score.py refuses configs that fail it.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RegionSpec:
    region_id: str
    display_name: str
    bbox: List[float]  # [lon0, lat0, lon1, lat1], WGS84
    cell_deg: float = 0.009  # ~1 km at tropical latitudes
    utm_epsg: str = "EPSG:32643"
    flood_weight: float = 0.30
    heat_weight: float = 0.30
    green_weight: float = 0.20
    carbon_weight: float = 0.20
    design_storm_mm: float = 150.0
    design_storm_status: str = "PROVISIONAL_UNVERIFIED"
    scoring_years: List[int] = field(default_factory=lambda: [2024])


def make_grid(bbox: List[float], cell_deg: float) -> List[Dict[str, Any]]:
    """Rectangular lon/lat cells with 3dp centre ids (exact-hit format)."""
    import math
    if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4
            or not all(isinstance(x, (int, float))
                       and math.isfinite(x) for x in bbox)):
        raise ValueError("bbox must be [lon0, lat0, lon1, lat1] of numbers")
    if (not isinstance(cell_deg, (int, float))
            or not math.isfinite(cell_deg) or cell_deg <= 0):
        raise ValueError("cell_deg must be a positive number")
    if not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        raise ValueError("bbox corners inverted")
    if cell_deg < 0.001:
        raise ValueError("cell_deg below 0.001 collides 3dp centre ids")
    cells = []
    lat = bbox[1]
    while lat < bbox[3]:
        lon = bbox[0]
        while lon < bbox[2]:
            lon2 = min(lon + cell_deg, bbox[2])
            lat2 = min(lat + cell_deg, bbox[3])
            cx, cy = (lon + lon2) / 2.0, (lat + lat2) / 2.0
            cells.append({
                "id": f"{round(cx, 3)}_{round(cy, 3)}",
                "centre": [cx, cy],
                "bounds": [lon, lat, lon2, lat2],
            })
            lon = lon2
        lat = lat2
    return cells


def write_config_scaffold(spec: RegionSpec, out_path: str) -> str:
    """Write regions/<id>.json. Every cited number starts UNSOURCED."""
    wsum = (spec.flood_weight + spec.heat_weight + spec.green_weight
            + spec.carbon_weight)
    if abs(wsum - 1.0) >= 1e-6:
        raise ValueError(f"weights sum to {wsum}, must sum to 1.0")
    cfg = {
        "region_id": spec.region_id,
        "display_name": spec.display_name,
        "authority": "UNSOURCED -- name the competent municipal authority",
        "crs": {"working_crs": spec.utm_epsg,
                "working_crs_name": f"UTM ({spec.utm_epsg})"},
        "bounds": spec.bbox,
        "hydrology": {
            "design_storm_mm": spec.design_storm_mm,
            "design_storm_status": spec.design_storm_status,
            "design_storm_note": "UNSOURCED -- replace with a fitted value "
            "from the national met service gridded series at a stated "
            "return period before issuing any real report.",
            "return_period_years": 100,
            "cn_table": {"vegetation": 60.0, "impervious": 98.0,
                         "water": 100.0, "bare": 86.0},
            "cn_table_source": "UNSOURCED -- cite TR-55 per value and state "
            "the assumed hydrologic soil group with its basis.",
            "cn_soil_group_assumption": "UNSOURCED -- extract from the "
            "national soil survey before issuing.",
            "slope_full_effect_deg": 15.0,
            "slope_max_multiplier": 1.25,
            "storm_drain_full_benefit_m": 500.0,
            "storm_drain_min_multiplier": 0.8,
        },
        "thermal": {
            "reference_method": "rural-ring-vegetated-median",
            "reference_c": None,
            "reference_c_status": "PENDING_SATELLITE",
            "uhi_max_delta_c": 2.0,
            "uhi_max_delta_status": "PENDING_DERIVATION",
            "night_reference_c": None,
            "night_reference_status": "PENDING_SATELLITE",
            "night_uhi_max_delta_c": 5.0,
            "night_uhi_max_delta_status": "PENDING_DERIVATION",
            "day_reference_status": "RETIRED_NO_SIGNAL -- daytime surface "
            "contrast carries no usable signal; see Pune evidence.",
        },
        "trees": {
            "census_year": None,
            "census_source": "UNSOURCED -- name the enumeration + year",
            "ward_id_join": "POLYGON_ONLY",
        },
        "carbon": {
            "intensity_unit": "kgCO2e per m2 of built-up area",
            "bands": [{"label": "Low", "max": 400.0},
                      {"label": "Moderate", "max": 800.0},
                      {"label": "High", "max": 1200.0},
                      {"label": "Very High", "max": None}],
            "bands_status": "UNSOURCED_BANDS",
        },
        "weights": {"flood": spec.flood_weight, "heat": spec.heat_weight,
                    "green": spec.green_weight,
                    "carbon": spec.carbon_weight},
        "green": {"canopy_weight": 0.7, "ground_vegetation_weight": 0.3,
                  "sat_census_tolerance_pct": 15.0,
                  "stratification_note": "House split, not a literature "
                  "coefficient -- keep it labelled."},
        "epochs": {"scoring_supported": list(spec.scoring_years)},
    }
    validate_config(cfg)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(cfg, f, indent=2)
    return out_path


def validate_config(cfg: Dict[str, Any]) -> bool:
    """Gate: raise on any structural defect. Score refuses failures."""
    import math
    if not isinstance(cfg, dict):
        raise ValueError("region config must be a dict")
    for key in ("region_id", "bounds", "hydrology", "thermal", "weights",
                "green", "carbon", "epochs"):
        if key not in cfg:
            raise ValueError(f"region config missing required key: {key}")
    hyd = cfg["hydrology"]
    if not isinstance(hyd, dict):
        raise ValueError("hydrology must be a dict")
    for key in ("cn_table", "design_storm_mm", "design_storm_status"):
        if key not in hyd:
            raise ValueError(f"hydrology missing required key: {key}")
    storm = hyd["design_storm_mm"]
    if (not isinstance(storm, (int, float)) or isinstance(storm, bool)
            or not math.isfinite(storm) or storm <= 0):
        raise ValueError("design_storm_mm must be a positive number")
    w = cfg["weights"]
    if not isinstance(w, dict):
        raise ValueError("weights must be a dict")
    try:
        vals = [float(v) for v in w.values()]
    except (TypeError, ValueError):
        raise ValueError("weights must be numeric")
    if (not all(math.isfinite(v) for v in vals)
            or abs(sum(vals) - 1.0) >= 1e-6):
        raise ValueError("weights must be finite and sum to 1.0")
    if not cfg["epochs"].get("scoring_supported"):
        raise ValueError("epochs.scoring_supported must list scored years")
    if "bands" not in cfg["carbon"]:
        raise ValueError("carbon.bands missing")
    return True
