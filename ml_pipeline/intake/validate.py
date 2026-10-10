"""Intake validation — L1.

Decides whether a submission can be scored at all, and says precisely what is
missing when it cannot.

Two rules this module enforces:

  1. GEOMETRY IS MANDATORY AND HUMAN-SUPPLIED. Files are evidence, never the
     geometry source. An uploaded PDF may propose a built-up area, but the
     polygon always comes from the user's map drawing or an explicit GeoJSON.

  2. NOTHING IS INVENTED. A missing input produces a named validation error,
     not a default. The scorer will happily compute a number from an assumed
     plot area, and that number would look identical to a measured one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ml_pipeline.core import geometry as G

Coord = Tuple[float, float]

MANDATORY = (
    "geometry",
    "builtUpAreaSqm",
    "plotAreaSqm",
    "materials",
)

RECOMMENDED = (
    "storeys",
    "projectType",
    "drainagePlan",
    "greenInfrastructure",
)

VALID_PROJECT_TYPES = {
    "residential", "commercial", "mixed", "industrial", "institutional", "public",
}

EPOCHS_SUPPORTED = (2024,)


@dataclass
class ValidationResult:
    valid: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    site: Dict[str, Any] = field(default_factory=dict)
    indicators: Dict[str, Any] = field(default_factory=dict)
    geometry: Optional[G.SiteGeometry] = None

    def add_error(self, code: str, message: str, field_name: str = "") -> None:
        self.errors.append({"code": code, "field": field_name, "message": message})

    def add_warning(self, code: str, message: str, field_name: str = "") -> None:
        self.warnings.append({"code": code, "field": field_name, "message": message})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "geometry": self.geometry.to_dict() if self.geometry else None,
            "site": self.site,
            "indicators_supplied": self.indicators,
        }


def _parse_ring(raw: Any) -> List[Coord]:
    """Accept a list of [lon,lat] pairs, or a GeoJSON Polygon/MultiPolygon."""
    ring: List[Coord] = []

    if isinstance(raw, dict):
        geom = raw.get("geometry") or raw
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if gtype == "Polygon" and coords:
            ring = [(float(c[0]), float(c[1])) for c in coords[0]]
        elif gtype == "MultiPolygon" and coords:
            ring = [(float(c[0]), float(c[1])) for c in coords[0][0]]
        else:
            raise ValueError(f"Unsupported GeoJSON geometry type: {gtype}")
        return ring

    if isinstance(raw, str):
        obj = json.loads(raw)
        return _parse_ring(obj)

    if isinstance(raw, (list, tuple)):
        if raw and isinstance(raw[0], (list, tuple)) and raw[0] and isinstance(raw[0][0], (list, tuple)):
            # Already a nested ring.
            return [(float(c[0]), float(c[1])) for c in raw[0]]
        return [(float(c[0]), float(c[1])) for c in raw]

    raise ValueError(f"Cannot interpret geometry of type {type(raw).__name__}")


def _close_ring(ring: Sequence[Coord]) -> List[Coord]:
    pts = list(ring)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def validate_submission(
    payload: Dict[str, Any],
    region_config: Dict[str, Any],
    require_pmc: bool = True,
) -> ValidationResult:
    """Validate one project submission. Returns errors, never raises."""
    res = ValidationResult(valid=False)

    # --- geometry ------------------------------------------------------
    raw_geom = payload.get("geometry")
    if raw_geom is None:
        res.add_error(
            "geometry_missing",
            "A site boundary is required. Draw it on the map or supply GeoJSON. "
            "An uploaded document can propose the footprint, but the polygon "
            "must be human-confirmed.",
            "geometry",
        )
    else:
        try:
            ring = _close_ring(_parse_ring(raw_geom))
        except Exception as exc:  # noqa: BLE001
            res.add_error("geometry_unparseable", f"Could not read the boundary: {exc}",
                          "geometry")
            ring = []

        if ring:
            if len(ring) < 4:
                res.add_error("geometry_too_few_vertices",
                              f"Boundary needs at least 4 vertices, got {len(ring)}.",
                              "geometry")
            else:
                geom = G.normalise_site(ring)
                res.geometry = geom

                if geom.area_m2 <= 0:
                    res.add_error("geometry_zero_area",
                                  "Boundary encloses no area.", "geometry")
                elif geom.area_m2 < 50.0:
                    res.add_warning(
                        "geometry_tiny",
                        f"Site is only {geom.area_m2:.0f} m2. At 10 m satellite "
                        f"resolution this is a handful of pixels.",
                        "geometry",
                    )
                elif geom.area_m2 > 500_000.0:
                    res.add_warning(
                        "geometry_very_large",
                        f"Site is {geom.area_m2/1e6:.2f} km2. Consider ward-level "
                        f"assessment rather than a single site polygon.",
                        "geometry",
                    )

                # Is it inside the PMC?
                ward = G.containing_ward(geom.centroid)
                if ward:
                    res.site["ward_no"] = ward["ward_no"]
                    res.site["ward_name"] = ward["ward_name"]
                    bounds = region_config.get("bounds", {}) or {}
                    if bounds:
                        inside = (
                            bounds.get("min_lon", -180) <= geom.centroid[0] <= bounds.get("max_lon", 180)
                            and bounds.get("min_lat", -90) <= geom.centroid[1] <= bounds.get("max_lat", 90)
                        )
                        if not inside:
                            res.add_warning(
                                "outside_region_bounds",
                                f"Site centroid lies outside the configured {region_config.get('region_id','region')} "
                                f"bounds but matched ward {ward['ward_no']}.",
                                "geometry",
                            )
                elif require_pmc:
                    res.add_error(
                        "outside_pmc",
                        "Site centroid does not fall inside any PMC ward. This "
                        "pipeline currently scores PMC sites only.",
                        "geometry",
                    )

                # Drainage context, kept strictly separated by sign.
                drain = G.drainage_context(geom.centroid, radius_m=600.0)
                if drain.get("available"):
                    res.indicators["dist_to_storm_drain_m"] = drain.get("dist_to_storm_drain_m")
                    res.site["drainage_context"] = {
                        "dist_to_storm_drain_m": drain.get("dist_to_storm_drain_m"),
                        "nearest_natural_water_m": drain.get("nearest_natural_water_m"),
                        "flood_plain_note": drain.get("flood_plain_note"),
                    }
                else:
                    res.indicators["dist_to_storm_drain_m"] = None

    # --- numeric form fields -------------------------------------------
    def num(key: str, minimum: float = 0.0) -> Optional[float]:
        v = payload.get(key)
        if v is None or v == "":
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            res.add_error(f"{key}_not_numeric", f"{key} must be a number, got {v!r}", key)
            return None
        if f < minimum:
            res.add_error(f"{key}_negative", f"{key} must be >= {minimum}, got {f}", key)
            return None
        return f

    built_up = num("builtUpAreaSqm", 1.0)
    plot = num("plotAreaSqm", 1.0)

    if built_up is None:
        res.add_error("builtUpAreaSqm_missing",
                      "Built-up area (the area actually covered by the building, in m2) "
                      "is required. Without it there is no carbon denominator.", "builtUpAreaSqm")
    else:
        res.site["builtUpAreaSqm"] = built_up

    if plot is None:
        res.add_error("plotAreaSqm_missing",
                      "Plot area (total site area in m2) is required. Without it the "
                      "impervious fraction cannot be computed, which drives the flood score.",
                      "plotAreaSqm")
    else:
        res.site["plotAreaSqm"] = plot

    if built_up and plot:
        if built_up > plot:
            res.add_error("built_up_exceeds_plot",
                          f"Built-up area {built_up:.0f} m2 exceeds plot area {plot:.0f} m2. "
                          f"Built-up is the covered footprint and cannot exceed the site.",
                          "builtUpAreaSqm")
        res.site["builtUpRatio"] = round(built_up / plot, 4)

    # --- materials ------------------------------------------------------
    materials = payload.get("materials") or []
    if not materials:
        res.add_error("materials_missing",
                      "A bill of quantities is required. Cement, steel, sand, aggregate, "
                      "brick, glass and aluminium all change the carbon score.", "materials")
    elif not isinstance(materials, list):
        res.add_error("materials_not_a_list",
                      "materials must be a list of {name, quantityKg} objects.", "materials")
    else:
        clean: List[Dict[str, Any]] = []
        for i, m in enumerate(materials):
            if not isinstance(m, dict):
                res.add_error("material_not_object",
                              f"materials[{i}] must be an object with name and quantityKg.",
                              "materials")
                continue
            name = m.get("name") or m.get("material")
            qty = m.get("quantityKg", m.get("quantity_kg"))
            if not name:
                res.add_error("material_name_missing", f"materials[{i}] has no name.", "materials")
                continue
            try:
                qty_f = float(qty or 0.0)
            except (TypeError, ValueError):
                res.add_error("material_quantity_invalid",
                              f"materials[{i}] ({name}) quantityKg is not a number.", "materials")
                continue
            if qty_f < 0:
                res.add_error("material_quantity_negative",
                              f"materials[{i}] ({name}) quantity is negative.", "materials")
                continue
            clean.append({"name": str(name), "quantityKg": qty_f})
        if clean:
            res.site["materials"] = clean
            if sum(m["quantityKg"] for m in clean) == 0:
                res.add_warning("materials_all_zero",
                                "Every material quantity is zero, so the carbon score "
                                "will be zero.", "materials")

    # --- optional, but they change the recommendation quality ----------
    storeys = payload.get("storeys")
    if storeys not in (None, ""):
        try:
            res.site["storeys"] = int(storeys)
        except (TypeError, ValueError):
            res.add_warning("storeys_invalid", "storeys should be an integer.", "storeys")

    ptype = payload.get("projectType")
    if ptype:
        if str(ptype).lower() not in VALID_PROJECT_TYPES:
            res.add_warning("projectType_unrecognised",
                            f"projectType '{ptype}' is not one of "
                            f"{sorted(VALID_PROJECT_TYPES)}.", "projectType")
        res.site["projectType"] = str(ptype).lower()

    if payload.get("drainagePlan"):
        res.site["drainagePlan"] = True
    if payload.get("greenInfrastructure"):
        res.site["greenInfrastructure"] = payload["greenInfrastructure"]

    epoch = payload.get("epoch", 2024)
    try:
        epoch_i = int(epoch)
    except (TypeError, ValueError):
        epoch_i = 2024
    if epoch_i not in EPOCHS_SUPPORTED:
        res.add_warning(
            "epoch_not_scoreable",
            f"Epoch {epoch_i} is not supported for scoring. Only "
            f"{list(EPOCHS_SUPPORTED)} is validated; other epochs are context "
            f"layers or labelled scenarios.",
            "epoch",
        )
    res.site["epoch"] = epoch_i

    # --- satellite-derived indicators ----------------------------------
    for key in ("impervious_pct", "vegetation_pct", "water_pct",
                "lst_mean_c", "mean_slope_deg"):
        v = payload.get(key)
        if v is None:
            continue
        try:
            res.indicators[key] = float(v)
        except (TypeError, ValueError):
            res.add_warning(f"{key}_ignored", f"{key} was not numeric and was ignored.", key)

    if res.indicators.get("lst_mean_c") is None:
        res.add_warning(
            "heat_unavailable",
            "No LST observation supplied, so the heat factor cannot be scored and "
            "the composite excludes it. Requires the satellite epoch cube.",
            "lst_mean_c",
        )

    res.valid = not res.errors
    return res
