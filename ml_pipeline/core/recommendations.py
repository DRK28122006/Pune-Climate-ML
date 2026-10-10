"""Recommendation engine — L6.

Turns a score into actions an approver can actually take, and proves each one
by re-running the deterministic scorer on the modified site.

The critical property: every reported improvement is a RESCORE, not an
assertion. A recommendation that says "reduce impervious cover 18%" must show
the flood score before and after, computed by the same function that computed
the original score. If the delta is zero or negative, the recommendation is
dropped rather than reported.

This is the fix for the original JS optimiser, which hardcoded a +12%
vegetation improvement and labelled it "impact".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ml_pipeline.core.scoring import score_project


def _apply_materials(
    materials: Sequence[Dict[str, Any]], swaps: Dict[str, float]
) -> List[Dict[str, Any]]:
    """Return materials with a fraction of each quantity swapped.

    `swaps` maps material name -> fraction replaced (0..1).
    """
    out = []
    for m in materials:
        # FIX 2026-10-10: accept quantity_kg as well as quantityKg.
        # compute_carbon reads both, but this function read only quantityKg,
        # so BOQs using quantity_kg rescored as zero here while scoring
        # correctly elsewhere -- a silent rescore-vs-score split.
        qty = float(m.get("quantityKg", m.get("quantity_kg", 0.0)) or 0.0)
        name = str(m.get("name") or m.get("material") or "")
        frac = swaps.get(name, 0.0)
        if frac > 0 and qty > 0:
            replaced = qty * frac
            out.append({"name": name, "quantityKg": qty - replaced})
            out.append({"name": f"__SUBSTITUTE__{name}", "quantityKg": replaced,
                        "_substitute_for": name, "_fraction": frac})
        else:
            out.append({"name": name, "quantityKg": qty})
    return out


def _resolve_substitutions(materials: Sequence[Dict[str, Any]], table: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Swap __SUBSTITUTE__ markers for the best available alternative."""
    resolved = []
    for m in materials:
        if str(m.get("name", "")).startswith("__SUBSTITUTE__"):
            original = m.get("_substitute_for")
            entry = (table.get("materials", {}) or {}).get(original, {})
            alts = entry.get("substitutions", []) or []
            if not alts:
                resolved.append({"name": original, "quantityKg": m["quantityKg"]})
                continue
            # Pick the lowest-carbon available alternative that exists in the table.
            best, best_ef = None, None
            for alt in alts:
                a = (table.get("materials", {}) or {}).get(alt)
                if not a or a.get("ef") is None:
                    continue
                if best_ef is None or float(a["ef"]) < best_ef:
                    best, best_ef = alt, float(a["ef"])
            resolved.append({"name": best or original, "quantityKg": m["quantityKg"]})
        else:
            resolved.append({"name": m.get("name"), "quantityKg": m.get("quantityKg")})
    return resolved


def _rescore(
    site: Dict[str, Any],
    indicators: Dict[str, Any],
    region_config: Dict[str, Any],
    materials_table: Dict[str, Any],
    ledger: Dict[str, Any],
) -> Dict[str, Any]:
    return score_project(site, indicators, region_config, materials_table, ledger=ledger)


def _delta(res: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two score results, per factor plus composite."""
    before = base.get("impact_score")
    after = res.get("impact_score")
    factors = {}
    for k in ("flood", "heat", "green", "carbon"):
        b = (base.get("sub_scores") or {}).get(k)
        a = (res.get("sub_scores") or {}).get(k)
        factors[k] = {
            "before": b,
            "after": a,
            "delta": round(a - b, 1) if (a is not None and b is not None) else None,
        }
    return {
        "impact_before": before,
        "impact_after": after,
        "impact_delta": round(after - before, 1) if (after is not None and before is not None) else None,
        "climate_before": base.get("climate_score"),
        "climate_after": res.get("climate_score"),
        "factors": factors,
    }


class RecommendationEngine:
    """Rule-based actions. Every impact claim is verified by rescoring."""

    # -- individual actions ----------------------------------------------

    def _material_substitutions(
        self, site, indicators, region_config, materials_table, base, ledger,
        fraction: float = 0.35,
    ) -> List[Dict[str, Any]]:
        """Swap a fraction of each material for its lowest-carbon alternative."""
        materials = site.get("materials") or []
        swapped = _apply_materials(materials, {
            name: fraction for name in
            {str(m.get("name") or m.get("material") or "") for m in materials}
        })
        resolved = _resolve_substitutions(swapped, materials_table)

        new_site = dict(site)
        new_site["materials"] = resolved
        res = _rescore(new_site, indicators, region_config, materials_table, ledger)
        d = _delta(res, base)

        moved = [
            (str(m.get("name")), float(m.get("quantityKg") or 0.0))
            for m in resolved
        ]
        return [{
            "id": "material_substitution",
            "action": f"Substitute {fraction:.0%} of each material with its "
                      f"lower-carbon alternative",
            "delta": d,
            "verified": (d["impact_delta"] or 0) < 0,
            "affected": "carbon",
            # Structured parameters, so the combined rescore never has to parse
            # a number back out of a human-readable sentence.
            "params": {"fraction": fraction},
        }]

    def _impervious_reduction(
        self, site, indicators, region_config, materials_table, base, ledger,
        reduction_pct: float = 18.0,
    ) -> List[Dict[str, Any]]:
        """Convert impervious area to permeable. Raises vegetation, lowers impervious."""
        imperv = float(indicators.get("impervious_pct", 60.0))
        veg = float(indicators.get("vegetation_pct", 30.0))
        shift = min(reduction_pct, imperv)
        new_ind = dict(indicators)
        new_ind["impervious_pct"] = imperv - shift
        new_ind["vegetation_pct"] = veg + shift
        res = _rescore(site, new_ind, region_config, materials_table, ledger)
        d = _delta(res, base)
        return [{
            "id": "impervious_reduction",
            "action": f"Reduce impervious cover by {shift:.0f} percentage points "
                      f"(permeable paving, green roof, or open landscape)",
            "delta": d,
            "verified": (d["factors"]["flood"]["delta"] or 0) < 0,
            "affected": "flood",
            "params": {"shift_pct_points": shift},
        }]

    def _preserve_mature_trees(
        self, site, indicators, region_config, materials_table, base, ledger,
    ) -> List[Dict[str, Any]]:
        """Reduce the built-up footprint so mature trees stay on site.

        Rescaling built-up area is only a PROXY for a redesigned footprint, and
        it has a side effect: a smaller denominator raises carbon intensity even
        when absolute emissions are unchanged. So the action cannot be judged on
        the composite alone. It is verified when it genuinely improves the factor
        it targets (green), and its effect on the other factors is reported
        honestly alongside. A recommendation that improves its own factor while
        worsening the composite is still worth making — the tree canopy is
        retained, which saplings cannot substitute for — but the trade-off has
        to be visible rather than buried.
        """
        if not ledger or not ledger.get("always_preserve_count"):
            return []

        preserve = ledger["always_preserve_count"]
        canopy_saved = ledger.get("always_preserve_canopy_m2", 0.0)
        canopy_now_pct = float(ledger.get("canopy_cover_pct", 0.0) or 0.0)

        # Preserving canopy can only raise census canopy coverage, never lower
        # it. Adding the retained canopy is the correct direction; the earlier
        # version halved the ledger's canopy, which modelled the trees as being
        # REMOVED and made this action look like a green regression.
        retained_pct = min(
            100.0, canopy_now_pct + 100.0 * canopy_saved / max(1.0, float(site.get("plotAreaSqm", 1.0)))
        )

        new_site = dict(site)
        # Same materials, smaller footprint: carbon intensity per m2 rises even
        # though absolute emissions are unchanged.
        new_site["builtUpAreaSqm"] = float(site.get("builtUpAreaSqm", 1.0)) * 0.92

        new_ledger = dict(ledger)
        new_ledger["canopy_cover_pct"] = max(0.0, retained_pct)

        res = _rescore(new_site, indicators, region_config, materials_table, new_ledger)
        d = _delta(res, base)

        green_delta = (d["factors"]["green"]["delta"])
        composite_delta = d["impact_delta"]

        if green_delta is None or green_delta >= 0:
            # No measurable green benefit: do not recommend it.
            return [{
                "id": "preserve_mature_trees",
                "action": f"Redesign the footprint to retain the {preserve} "
                          f"heritage-class trees on site",
                "delta": d,
                "verified": False,
                "affected": "green",
                "params": {"footprint_scale": 0.92},
                "drop_reason": "rescoring showed no improvement to the green factor",
            }]

        return [{
            "id": "preserve_mature_trees",
            "action": f"Redesign the footprint to retain the {preserve} heritage-class "
                      f"trees on site, recovering {canopy_saved:.0f} m2 of canopy",
            "delta": d,
            # Verified on the factor it targets. The composite may still rise,
            # and that is reported rather than hidden.
            "verified": True,
            "affected": "green",
            "params": {"footprint_scale": 0.92},
            "composite_tradeoff": (
                f"green {d['factors']['green']['before']} -> "
                f"{d['factors']['green']['after']} (improves by "
                f"{-(green_delta):.1f}), but carbon intensity rises "
                f"{d['factors']['carbon']['before']} -> "
                f"{d['factors']['carbon']['after']} because the same materials are "
                f"spread over a smaller footprint. Composite impact moves "
                f"{composite_delta:+.1f}."
                if composite_delta is not None and composite_delta > 0
                else "Improves both the targeted factor and the composite."
            ),
            "note": "Canopy preserved rather than replaced. Saplings do not "
                    "substitute for retained mature canopy on any useful timescale.",
        }]

    # -- orchestration ----------------------------------------------------

    def build_recommendations(
        self,
        site: Dict[str, Any],
        indicators: Dict[str, Any],
        region_config: Dict[str, Any],
        materials_table: Dict[str, Any],
        ledger: Dict[str, Any],
    ) -> Dict[str, Any]:
        """All candidate actions, each with a verified impact delta."""
        base = _rescore(site, indicators, region_config, materials_table, ledger)

        candidates: List[Dict[str, Any]] = []
        candidates += self._impervious_reduction(
            site, indicators, region_config, materials_table, base, ledger
        )
        candidates += self._material_substitutions(
            site, indicators, region_config, materials_table, base, ledger
        )
        candidates += self._preserve_mature_trees(
            site, indicators, region_config, materials_table, base, ledger
        )

        # Also surface blocking advisories (e.g. riverbed sand) as mandatory
        # conditions regardless of any numeric score.
        carbon_blockers = [
            adv for adv in (base.get("factors", {}).get("carbon", {}).get("ecological_advisories") or [])
            if adv.get("severity") == "blocking"
        ]
        for adv in carbon_blockers:
            candidates.append({
                "id": "material_sourcing",
                "action": adv.get("text", ""),
                "delta": None,
                "verified": True,
                "affected": "carbon",
                "blocking": True,
                "alternatives": adv.get("alternatives", []),
            })

        verified = [c for c in candidates if c.get("verified")]
        unverified = [c for c in candidates if not c.get("verified")]

        def gain(c: Dict[str, Any]) -> float:
            """Rank by improvement on the targeted factor, not the composite.

            Using the composite here would bury the tree-preservation action,
            whose only modelled downside is an intensity artefact of the proxy
            denominator.
            """
            d = c.get("delta") or {}
            f = (d.get("factors") or {}).get(c.get("affected") or "")
            fd = f.get("delta") if isinstance(f, dict) else None
            if fd is not None:
                return -float(fd)
            dl = d.get("impact_delta")
            return -(dl or 0.0)

        verified.sort(key=gain, reverse=True)

        return {
            "baseline_impact": base.get("impact_score"),
            "baseline_climate": base.get("climate_score"),
            "baseline_risk": base.get("risk_band"),
            "recommendations": verified,
            "dropped_unverified": [
                {"id": c["id"], "reason": "rescoring showed no measurable improvement"}
                for c in unverified
            ],
            "verification_note": (
                "Each 'delta' is a genuine re-run of the deterministic scorer on the "
                "modified site. Recommendations that did not move the score are "
                "dropped, not reported."
            ),
            "combined_effect": self._combined(verified, base, site, indicators,
                                              region_config, materials_table, ledger),
        }

    def _combined(
        self, verified, base, site, indicators, region_config, materials_table, ledger
    ) -> Dict[str, Any]:
        """Rescore once with ALL verified changes applied together."""
        if not verified:
            return {"available": False, "reason": "no verified actions"}

        new_site = dict(site)
        new_ind = dict(indicators)

        # Aggregate: material substitution at the max fraction recommended.
        fracs = [
            float((c.get("params") or {}).get("fraction", 0.0))
            for c in verified if c["id"] == "material_substitution"
        ]
        frac = max(fracs) if fracs else 0.0
        if frac > 0:
            mats = site.get("materials") or []
            swapped = _apply_materials(
                mats, {str(m.get("name") or ""): frac for m in mats}
            )
            new_site["materials"] = _resolve_substitutions(swapped, materials_table)

        # Aggregate: impervious reduction, summed across any such actions.
        shifts = [
            float((c.get("params") or {}).get("shift_pct_points", 0.0))
            for c in verified if c["id"] == "impervious_reduction"
        ]
        total_shift = sum(shifts)
        if total_shift > 0:
            imperv = float(indicators.get("impervious_pct", 60.0))
            veg = float(indicators.get("vegetation_pct", 30.0))
            # Never drive impervious negative or vegetation above 100.
            total_shift = min(total_shift, imperv, max(0.0, 100.0 - veg))
            new_ind["impervious_pct"] = imperv - total_shift
            new_ind["vegetation_pct"] = veg + total_shift

        # Aggregate: footprint rescale for tree preservation.
        # FIX 2026-10-10: the old code rescaled the footprint but rescored
        # with the ORIGINAL ledger, dropping the retained-canopy gain the
        # individual action models -- the combined effect understated green.
        # Mirror _preserve_mature_trees: carry the retained canopy forward.
        new_ledger = ledger
        if any(c["id"] == "preserve_mature_trees" for c in verified):
            new_site["builtUpAreaSqm"] = float(site.get("builtUpAreaSqm", 1.0)) * 0.92
            preserved_canopy = float((ledger or {}).get("always_preserve_canopy_m2", 0.0) or 0.0)
            canopy_now = float((ledger or {}).get("canopy_cover_pct", 0.0) or 0.0)
            plot = float(site.get("plotAreaSqm", 1.0) or 1.0)
            new_ledger = dict(ledger or {})
            new_ledger["canopy_cover_pct"] = min(
                100.0, max(0.0, canopy_now + 100.0 * preserved_canopy / max(1.0, plot))
            )

        res = _rescore(new_site, new_ind, region_config, materials_table, new_ledger)
        d = _delta(res, base)
        return {"available": True, "delta": d}
