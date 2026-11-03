"""Preview the score impact of the derived slope band WITHOUT enabling it.

This script is deliberately read-only with respect to the repository.  It reads
the current cube, the derived band and the existing validation harnesses, then
calls `compute_flood` twice per row:

    once with mean_slope_deg=None   (current behaviour)
    once with the derived slope      (what enabling it would do)

It does not edit the scorer, the validators, the validation JSONs or the cube.
The only file it writes is `/tmp/opencode/slope_preview.json`.  It refuses to
run if the band's `source_cube_sha256` does not match the current cube, or if
any cube cell lacks a slope.

Scope is FLOOD ONLY.  Slope does not touch heat, green or carbon.  With fixed
weights (0.30 flood / 0.30 heat / 0.20 green / 0.20 carbon), a flood delta
`dF` implies, when all four factors are present:

    d(impact)  = +0.30 * dF
    d(climate) = -0.30 * dF

That identity is stated, not recomputed with a fake ledger.

The wider 41-ward run is a `centroid_sample`: a ward centroid is a point, not
an area-weighted ward slope, and must not be presented as one.

Run:
    .venv/bin/python ml_pipeline/data/slope_preview.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

BAND = REPO / "ml_pipeline" / "data" / "slope_band.json"
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
CONFIG_DIR = REPO / "ml_pipeline" / "config"
OUT = Path("/tmp/opencode/slope_preview.json")

FLOOD_WEIGHT = 0.30

# The house gate from the session prompt (0015-slope-derivation.md was not
# present when this session ran).  This is a policy threshold, not a measured
# constant.
GATE_P95_DEG = 1.0
GATE_MIN_WARDS_MOVED = 3
GATE_WARD_DELTA_POINTS = 1.0


# -------------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------------


def _quantile(values: List[float], q: float) -> Optional[float]:
    """Linear-interpolation quantile, matching derive_slope.py."""
    if not values:
        return None
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    q = min(1.0, max(0.0, float(q)))
    pos = (len(xs) - 1) * q
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return xs[low]
    frac = pos - low
    return xs[low] * (1.0 - frac) + xs[high] * frac


def _stats(values: List[float]) -> Dict[str, Optional[float]]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"min": None, "median": None, "p95": None, "max": None}
    return {
        "min": round(min(vals), 4),
        "median": round(_quantile(vals, 0.50), 4),
        "p95": round(_quantile(vals, 0.95), 4),
        "max": round(max(vals), 4),
    }


def _cell_key_for_point(
    cube: Dict[str, Any], lon: float, lat: float
) -> Optional[str]:
    """Return the cube key whose cell contains (lon, lat).

    Mirrors the bbox arithmetic in `geometry.cube_cell_for_point`, but returns
    the KEY rather than the cell dict so the preview can report which cell it
    sampled.  Falls back to the nearest key if the grid arithmetic misses.
    """
    from ml_pipeline.core import geometry as G

    cells = cube.get("cells") or {}
    if not cells:
        return None
    bbox = cube.get("bbox")
    cell_deg = cube.get("cell_deg")
    try:
        if bbox and len(bbox) == 4 and cell_deg and float(cell_deg) > 0:
            west, south, east, north = (float(v) for v in bbox)
            step = float(cell_deg)
            col = math.floor((float(lon) - west) / step)
            row = math.floor((float(lat) - south) / step)
            lon0 = west + col * step
            lat0 = south + row * step
            lon1 = min(lon0 + step, east)
            lat1 = min(lat0 + step, north)
            centre = ((lon0 + lon1) / 2.0, (lat0 + lat1) / 2.0)
            for key in G._cube_keys(*centre):
                if key in cells:
                    return key
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    best_key: Optional[str] = None
    best_d: Optional[float] = None
    for key in cells:
        try:
            k_lon, k_lat = (float(x) for x in key.split("_"))
        except (ValueError, AttributeError):
            continue
        d = G.haversine_m((float(lon), float(lat)), (k_lon, k_lat))
        if best_d is None or d < best_d:
            best_key, best_d = key, d
    return best_key


def _enrich_cube(cube: Dict[str, Any], band: Dict[str, Any]) -> Dict[str, Any]:
    """Return a cube copy whose cells carry `mean_slope_deg` from the band.

    Passing this copy to the existing validators' helpers is how the preview
    reads the band without editing any validator or the cube on disk.
    """
    band_cells = band.get("cells") or {}
    enriched = dict(cube)
    cells: Dict[str, Any] = {}
    for key, cell in (cube.get("cells") or {}).items():
        new_cell = dict(cell)
        entry = band_cells.get(key) or {}
        if entry.get("mean_slope_deg") is not None:
            new_cell["mean_slope_deg"] = entry["mean_slope_deg"]
        cells[key] = new_cell
    enriched["cells"] = cells
    return enriched


def _flood_kwargs(
    indicators: Dict[str, Any],
    region: Dict[str, Any],
    slope_deg: Optional[float],
) -> Dict[str, Any]:
    hyd = region.get("hydrology") or {}
    return {
        "impervious_pct": indicators.get("impervious_pct"),
        "vegetation_pct": indicators.get("vegetation_pct"),
        "water_pct": indicators.get("water_pct"),
        "design_storm_mm": hyd.get("design_storm_mm"),
        "cn_table": hyd.get("cn_table"),
        "bare_pct": indicators.get("bare_pct"),
        "mean_slope_deg": slope_deg,
        "dist_to_storm_drain_m": indicators.get("dist_to_storm_drain_m"),
        "slope_full_effect_deg": hyd.get("slope_full_effect_deg", 15.0),
        "slope_max_multiplier": hyd.get("slope_max_multiplier", 1.25),
        "drain_full_benefit_m": hyd.get("storm_drain_full_benefit_m", 500.0),
        "drain_min_multiplier": hyd.get("storm_drain_min_multiplier", 0.80),
        "bare_season_pct": indicators.get("bare_season_pct"),
        "landcover_source": indicators.get("landcover_source"),
    }


def _row(
    group: str,
    label: str,
    cell_id: Optional[str],
    slope_deg: Optional[float],
    slope_basis: str,
    indicators: Dict[str, Any],
    region: Dict[str, Any],
) -> Dict[str, Any]:
    from ml_pipeline.core.scoring import compute_flood

    before = compute_flood(**_flood_kwargs(indicators, region, None))
    after = compute_flood(**_flood_kwargs(indicators, region, slope_deg))
    b = before.get("score")
    a = after.get("score")
    delta = round(a - b, 1) if (a is not None and b is not None) else None
    return {
        "group": group,
        "row": label,
        "cell_id": cell_id,
        "derived_slope_deg": slope_deg,
        "slope_basis": slope_basis,
        "flood_before": b,
        "flood_after": a,
        "flood_delta": delta,
        "implied_impact_delta": (
            round(FLOOD_WEIGHT * delta, 2) if delta is not None else None
        ),
        "implied_climate_delta": (
            round(-FLOOD_WEIGHT * delta, 2) if delta is not None else None
        ),
        "slope_available_before": before.get("slope_available"),
        "slope_multiplier_after": after.get("slope_multiplier"),
        "flood_available_before": b is not None,
        "flood_available_after": a is not None,
    }


def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    slopes = [
        r["derived_slope_deg"]
        for r in rows
        if r["derived_slope_deg"] is not None
    ]
    deltas = [
        r["flood_delta"] for r in rows if r["flood_delta"] is not None
    ]
    stats = _stats(slopes)
    stats.update(
        {
            "rows": len(rows),
            "rows_with_slope": len(slopes),
            "rows_delta_ge_1": sum(
                1 for d in deltas if d >= GATE_WARD_DELTA_POINTS
            ),
            "rows_unchanged": sum(1 for d in deltas if d == 0.0),
            "rows_unavailable": sum(
                1 for r in rows if r["flood_delta"] is None
            ),
            "max_flood_delta": max(deltas) if deltas else None,
            "max_abs_implied_impact_delta": (
                round(max(abs(FLOOD_WEIGHT * d) for d in deltas), 2)
                if deltas
                else None
            ),
        }
    )
    return stats


def _print_table(title: str, rows: List[Dict[str, Any]], note: str = "") -> None:
    print()
    print(title)
    if note:
        print(f"  ({note})")
    print(
        f"{'row':<24} {'cell id':<18} {'slope':>7} {'before':>7} "
        f"{'after':>7} {'delta':>7} {'dImpact':>8} {'dClimate':>9}"
    )
    print("-" * 100)
    for r in rows:
        slope = (
            f"{r['derived_slope_deg']:.2f}"
            if r["derived_slope_deg"] is not None
            else "-"
        )
        before = (
            f"{r['flood_before']:.1f}"
            if r["flood_before"] is not None
            else "-"
        )
        after = (
            f"{r['flood_after']:.1f}" if r["flood_after"] is not None else "-"
        )
        delta = (
            f"{r['flood_delta']:+.1f}"
            if r["flood_delta"] is not None
            else "-"
        )
        impact = (
            f"{r['implied_impact_delta']:+.2f}"
            if r["implied_impact_delta"] is not None
            else "-"
        )
        climate = (
            f"{r['implied_climate_delta']:+.2f}"
            if r["implied_climate_delta"] is not None
            else "-"
        )
        print(
            f"{r['row']:<24} {str(r['cell_id']):<18} {slope:>7} {before:>7} "
            f"{after:>7} {delta:>7} {impact:>8} {climate:>9}"
        )


# -------------------------------------------------------------------------
# Preview builders
# -------------------------------------------------------------------------


def _validation_wards(
    cube: Dict[str, Any], enriched: Dict[str, Any], region: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The 6 validation wards, indicators built exactly as validate_wards.py.

    `validate_wards._cells_for_ward` is imported, not copied: it is the same
    area-weighted intersection code the validation artifact uses.  Its output
    carries `mean_slope_deg` because the enriched cube does.
    """
    from ml_pipeline.core import geometry as G
    from ml_pipeline.data import validate_wards as VW

    ward_rings = VW._load_ward_rings()
    rows: List[Dict[str, Any]] = []
    for w in [3, 7, 12, 13, 21, 25]:
        ring = ward_rings.get(w)
        if not ring:
            print(f"  ward {w}: no polygon; skipping")
            continue
        agg = VW._cells_for_ward(ring, enriched)
        indicators = dict(agg.get("indicators") or {})
        if not indicators:
            print(f"  ward {w}: no cube cells; skipping")
            continue
        # validate_wards takes drainage from the ward profile.  That profile
        # currently has no storm-drain field, so this is None -- identical to
        # the current validation behaviour.
        try:
            prof = G.ward_tree_profile(w)
        except Exception:  # noqa: BLE001
            prof = {}
        indicators["dist_to_storm_drain_m"] = prof.get("dist_to_storm_drain_m")
        indicators["landcover_source"] = "area_weighted_cube_cells"

        centroid = G.polygon_centroid([(float(a), float(b)) for a, b in ring])
        cell_id = _cell_key_for_point(cube, centroid[0], centroid[1])
        rows.append(
            _row(
                "ward_validation",
                f"ward {w}",
                cell_id,
                indicators.get("mean_slope_deg"),
                "area_weighted_cube_cells",
                indicators,
                region,
            )
        )
    return rows


def _validation_sites(
    cube: Dict[str, Any], enriched: Dict[str, Any], region: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The 8 validation sites, indicators built exactly as validate_sites.py."""
    from ml_pipeline import cli as CLI
    from ml_pipeline.core import geometry as G
    from ml_pipeline.data import validate_sites as VS

    rows: List[Dict[str, Any]] = []
    for spec in VS.SITES:
        lon, lat = spec["lon"], spec["lat"]
        d = VS._half_width_deg(VS.PLOT_SQM)
        ring = [
            (lon - d, lat - d),
            (lon + d, lat - d),
            (lon + d, lat + d),
            (lon - d, lat + d),
            (lon - d, lat - d),
        ]
        sat = CLI.indicators_from_cube(ring, enriched)
        if not sat:
            print(f"  {spec['name']}: no cube cell; skipping")
            continue
        try:
            drain = G.drainage_context((lon, lat))
        except Exception:  # noqa: BLE001
            drain = {}
        indicators = {
            "impervious_pct": VS._pct(sat.get("built_pct")),
            "vegetation_pct": VS._pct(sat.get("vegetation_pct")),
            "water_pct": VS._pct(sat.get("water_pct")),
            "bare_pct": (
                VS._pct(sat.get("bare_pct"))
                if sat.get("bare_pct") is not None
                else None
            ),
            "bare_season_pct": sat.get("bare_season_pct"),
            "mean_slope_deg": sat.get("mean_slope_deg", sat.get("slope_deg")),
            "dist_to_storm_drain_m": drain.get("dist_to_storm_drain_m"),
            "landcover_source": "single_cube_cell",
        }
        cell_id = _cell_key_for_point(cube, lon, lat)
        rows.append(
            _row(
                "site_validation",
                spec["name"],
                cell_id,
                indicators.get("mean_slope_deg"),
                "single_cube_cell",
                indicators,
                region,
            )
        )
    return rows


def _all_wards_centroid(
    cube: Dict[str, Any], enriched: Dict[str, Any], region: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """All 41 wards sampled at the ward CENTROID CELL (not area-weighted)."""
    from ml_pipeline.core import geometry as G
    from ml_pipeline.data import validate_wards as VW

    ward_rings = VW._load_ward_rings()
    rows: List[Dict[str, Any]] = []
    for w in sorted(ward_rings):
        ring = ward_rings[w]
        centroid = G.polygon_centroid([(float(a), float(b)) for a, b in ring])
        cell_id = _cell_key_for_point(enriched, centroid[0], centroid[1])
        cell = ((enriched.get("cells") or {}).get(cell_id) or {}) if cell_id else {}
        if not cell:
            print(f"  ward {w}: no centroid cell; skipping")
            continue
        indicators = {
            "impervious_pct": (
                float(cell["built_pct"]) * 100.0
                if cell.get("built_pct") is not None
                else None
            ),
            "vegetation_pct": (
                float(cell["vegetation_pct"]) * 100.0
                if cell.get("vegetation_pct") is not None
                else None
            ),
            "water_pct": (
                float(cell["water_pct"]) * 100.0
                if cell.get("water_pct") is not None
                else None
            ),
            "bare_pct": (
                float(cell["bare_pct"]) * 100.0
                if cell.get("bare_pct") is not None
                else None
            ),
            "bare_season_pct": cell.get("bare_season_pct"),
            "mean_slope_deg": cell.get("mean_slope_deg"),
            # The ward profile has no storm-drain field, so current validation
            # behaviour leaves this None.  Keep the comparison honest.
            "dist_to_storm_drain_m": None,
            "landcover_source": "single_cube_cell_centroid_sample",
        }
        rows.append(
            _row(
                "centroid_sample",
                f"ward {w} centroid",
                cell_id,
                indicators.get("mean_slope_deg"),
                "single_cube_cell_centroid_sample",
                indicators,
                region,
            )
        )
    return rows


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> int:
    if not BAND.exists():
        print(f"slope band missing at {BAND}")
        print("Nothing to preview. Run: python ml_pipeline/data/derive_slope.py")
        return 0
    if not CUBE.exists():
        print(f"epoch cube missing at {CUBE}")
        return 0

    cube_raw = CUBE.read_bytes()
    cube = json.loads(cube_raw)
    cube_sha = hashlib.sha256(cube_raw).hexdigest()

    band = json.loads(BAND.read_text())
    prov = band.get("provenance") or {}
    band_sha = prov.get("source_cube_sha256")
    if band_sha != cube_sha:
        print("STALE SLOPE BAND — refusing to preview.", file=sys.stderr)
        print(f"  band source : {band_sha}", file=sys.stderr)
        print(f"  current cube: {cube_sha}", file=sys.stderr)
        print("  re-run: python ml_pipeline/data/derive_slope.py", file=sys.stderr)
        return 2

    cube_cells = cube.get("cells") or {}
    band_cells = band.get("cells") or {}
    matched = sum(
        1
        for key in cube_cells
        if (band_cells.get(key) or {}).get("mean_slope_deg") is not None
    )
    if matched != len(cube_cells):
        print(
            f"INCOMPLETE SLOPE BAND — {matched}/{len(cube_cells)} cube cells "
            "have a slope; refusing to preview.",
            file=sys.stderr,
        )
        print("  re-run: python ml_pipeline/data/derive_slope.py", file=sys.stderr)
        return 2

    enriched = _enrich_cube(cube, band)
    region = json.loads((CONFIG_DIR / "regions" / "pune.json").read_text())

    p95 = prov.get("slope_p95_deg")

    print("SLOPE SCORE-IMPACT PREVIEW  (flood only; NOTHING ENABLED)")
    print("=" * 100)
    print(f"band      : {BAND}")
    print(f"cube hash : {cube_sha}")
    print(f"coverage  : {matched}/{len(cube_cells)} cube cells")
    print(
        "band dist : "
        f"min {prov.get('slope_min_deg')}  p05 {prov.get('slope_p05_deg')}  "
        f"median {prov.get('slope_median_deg')}  p95 {p95}  "
        f"max {prov.get('slope_max_deg')}"
    )
    print(
        "threshold : cells >1 deg "
        f"{prov.get('cells_above_1_deg')}, >5 deg "
        f"{prov.get('cells_above_5_deg')}, >15 deg "
        f"{prov.get('cells_above_15_deg')}"
    )
    print()
    print(
        "identity  : d(impact) = +0.30 * dF and d(climate) = -0.30 * dF "
        "when all four factors are present."
    )

    wards = _validation_wards(cube, enriched, region)
    sites = _validation_sites(cube, enriched, region)
    centroid_sample = _all_wards_centroid(cube, enriched, region)

    _print_table("6 VALIDATION WARDS — area-weighted cube cells", wards)
    _print_table("8 VALIDATION SITES — single cube cell (centroid)", sites)
    _print_table(
        "41 WARDS — CENTROID SAMPLE (NOT an area-weighted ward slope)",
        centroid_sample,
        "a ward centroid is a point sample; do not present it as ward slope",
    )

    ward_agg = _aggregate(wards)
    site_agg = _aggregate(sites)
    centroid_agg = _aggregate(centroid_sample)
    all_agg = _aggregate(wards + sites + centroid_sample)

    gate_p95_pass = p95 is not None and float(p95) >= GATE_P95_DEG
    gate_wards_pass = ward_agg["rows_delta_ge_1"] >= GATE_MIN_WARDS_MOVED
    gate_pass = bool(gate_p95_pass and gate_wards_pass)

    print()
    print("=" * 100)
    print("AGGREGATES")
    print("=" * 100)
    for name, agg in (
        ("6 validation wards", ward_agg),
        ("8 validation sites", site_agg),
        ("41-ward centroid sample", centroid_agg),
        ("all preview rows", all_agg),
    ):
        print(
            f"{name:<26} slope min {agg['min']} median {agg['median']} "
            f"p95 {agg['p95']} max {agg['max']} | "
            f"delta>=1: {agg['rows_delta_ge_1']}/{agg['rows']} | "
            f"unchanged: {agg['rows_unchanged']} | "
            f"max flood delta: {agg['max_flood_delta']}"
        )

    print()
    print("=" * 100)
    print("KILL GATE (house judgment, not a measured constant)")
    print("=" * 100)
    print(
        f"  p95 slope >= {GATE_P95_DEG:.1f} deg      : "
        f"{'PASS' if gate_p95_pass else 'FAIL'}  (p95 = {p95})"
    )
    print(
        f"  >= {GATE_MIN_WARDS_MOVED} of 6 wards move "
        f">= {GATE_WARD_DELTA_POINTS:.1f} : "
        f"{'PASS' if gate_wards_pass else 'FAIL'}  "
        f"({ward_agg['rows_delta_ge_1']} of {ward_agg['rows']} moved)"
    )
    print(f"  OVERALL                  : {'PASS' if gate_pass else 'FAIL'}")
    print(
        "  Recommendation           : "
        + ("ENABLE (review-gated)" if gate_pass else "DO NOT ENABLE")
    )

    payload = {
        "scope": "flood_only",
        "identity": {
            "impact_delta": "+0.30 * flood_delta",
            "climate_delta": "-0.30 * flood_delta",
            "note": (
                "Implied composite change when all four factors are present; "
                "the composite was not recomputed."
            ),
        },
        "band_provenance": prov,
        "gate": {
            "label": "house_judgment",
            "thresholds": {
                "p95_slope_deg": GATE_P95_DEG,
                "wards_moved_ge_points": GATE_WARD_DELTA_POINTS,
                "min_wards_moved": GATE_MIN_WARDS_MOVED,
            },
            "p95_slope_deg": p95,
            "p95_pass": gate_p95_pass,
            "wards_moved": ward_agg["rows_delta_ge_1"],
            "wards_total": ward_agg["rows"],
            "wards_pass": gate_wards_pass,
            "pass": gate_pass,
            "recommendation": (
                "ENABLE (review-gated)" if gate_pass else "DO NOT ENABLE"
            ),
        },
        "wards": wards,
        "sites": sites,
        "centroid_sample": {
            "label": "centroid_sample",
            "warning": (
                "A ward centroid is one cube cell, not an area-weighted ward "
                "slope. Do not present this as ward-level slope."
            ),
            "rows": centroid_sample,
        },
        "aggregates": {
            "wards": ward_agg,
            "sites": site_agg,
            "centroid_sample": centroid_agg,
            "all_rows": all_agg,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print()
    print(f"wrote {OUT}  (no tracked file was written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
