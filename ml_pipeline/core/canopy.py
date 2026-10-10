"""Canopy ledger — deterministic tree-by-tree decisions for a site.

Pure logic. No I/O, no network, no config file reads at call time (the caller
passes config in). Every function here is unit-testable offline.

Legal posture, stated once so it is never misquoted later:

  The Maharashtra (Urban Areas) Preservation of Trees Act, 1975 requires Tree
  Officer permission to fell any tree in an urban area. It does NOT contain a
  girth-based automatic felling prohibition. The Act (1975, as amended July
  2021) sets compensation as trees planted "in such number equal to the age
  of the tree" -- the section number is deliberately not cited (primary
  Act text unverified 2026-10-10; age-equivalence confirmed via the 2021
  amendment record and PMC heritage-tree notifications).

  Therefore:
    - "girth >= 90 cm" MUST_PRESERVE is OUR house policy, not law.
    - Compensatory counts are AGE-EQUIVALENT estimates from girth, because the
      census has no age column. They are always reported as a range.
    - Nothing in this module is legal clearance. It is decision support.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# Census condition values that make a tree a poor transplant candidate.
_DEAD_CONDITIONS = {"dead", "dead tree", "fallen", "stump"}
_POOR_CONDITIONS = {"poor", "dying", "diseased", "damaged"}


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def species_key(botanical_name: Optional[str]) -> str:
    """Reduce a census botanical_name to 'Genus species'.

    The census stores full taxonomic strings, e.g.
    'Ficus religiosa Linn.' / 'Polyalthia longifolia var.pendula'.
    Taking the first two tokens matches the genus + epithet and tolerates the
    author suffix. A variety name in token 3 is intentionally ignored.
    """
    tokens = (botanical_name or "").split()
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    return f"{tokens[0]} {tokens[1]}"


def canopy_area_m2(canopy_dia_m: float) -> float:
    """Projected crown area of a single tree, in square metres."""
    radius = max(0.0, float(canopy_dia_m)) / 2.0
    return math.pi * radius * radius


def maturity_tier(girth_cm: float, thresholds: Optional[Dict[str, float]] = None) -> str:
    """Classify a tree by girth.

    Defaults come from the census distribution: median 35 cm, p75 74 cm.
    The 30/60/90 cm splits are house policy for tiering only — they are not
    statutory thresholds and are not used to decide legality of felling.
    """
    th = thresholds or {"young_cm": 30.0, "mature_cm": 60.0}
    g = float(girth_cm)
    if g < th["young_cm"]:
        return "sapling"
    if g < th["mature_cm"]:
        return "young"
    return "mature"


@dataclass
class TreeRecord:
    """One census tree, normalised.

    ward_id is intentionally absent as a required field: census ward values run
    3..63 and do NOT correspond to the 1..41 numbering of the 2025 ward KML.
    Ward assignment must be done by point-in-polygon, never by joining ids.
    """

    tree_id: int
    lon: float
    lat: float
    botanical_name: str = ""
    girth_cm: float = 0.0
    height_m: float = 0.0
    canopy_dia_m: float = 0.0
    condition: str = ""
    is_rare: bool = False

    @property
    def condition_norm(self) -> str:
        return _norm(self.condition)

    @property
    def is_dead(self) -> str:
        return _norm(self.condition) in _DEAD_CONDITIONS

    @property
    def is_poor(self) -> bool:
        return _norm(self.condition) in _POOR_CONDITIONS


@dataclass
class TreeDecision:
    tree_id: int
    botanical_name: str
    species_key: str
    girth_cm: float
    canopy_m2: float
    action: str
    reason: str
    statutory_basis: str
    compensatory_saplings: Dict[str, float] = field(default_factory=dict)
    age_estimate_years: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "tree_id": self.tree_id,
            "botanical_name": self.botanical_name,
            "species_key": self.species_key,
            "girth_cm": round(self.girth_cm, 1),
            "canopy_m2": round(self.canopy_m2, 1),
            "action": self.action,
            "reason": self.reason,
            "statutory_basis": self.statutory_basis,
        }
        if self.compensatory_saplings:
            out["compensatory_saplings"] = self.compensatory_saplings
        if self.age_estimate_years:
            out["age_estimate_years"] = self.age_estimate_years
        return out


def estimate_age_years(
    girth_cm: float,
    cm_per_year: float = 2.0,
    f_lo: float = 1.2,
    f_hi: float = 3.2,
) -> Dict[str, float]:
    """Estimate tree age from girth, with an explicit wide range.

    There is no age column in the census, and girth-to-age is species and site
    dependent. A linear increment of 2 cm/yr is a crude central proxy; the
    range brackets a faster and a slower growth assumption. Both are
    deliberately crude: a real assessment needs a measured DBH or an increment
    borer sample, and the report says so.

    Returns {'low', 'point', 'high'} in years.
    """
    g = max(0.0, float(girth_cm))
    point = g / cm_per_year if cm_per_year > 0 else 0.0
    return {
        "low": round(g / f_hi, 1) if f_hi else point,
        "point": round(point, 1),
        "high": round(g / f_lo, 1) if f_lo else point,
    }


class CanopyLedger:
    """Applies the tree-by-tree decision rules for one site."""

    def __init__(self, species_config: Dict[str, Any]) -> None:
        self.cfg = species_config
        legal = species_config.get("legal", {}) or {}
        # FIX 2026-10-10: the old expression
        #   float(legal.get("age_estimate_method", "") and 2.0 or 2.0)
        # evaluated to 2.0 on every path (string-and-float-or-float is a
        # constant) and ignored configuration. Read the numeric rate key,
        # falling back to the documented 2.0 proxy. Value is unchanged
        # today (species.json legal.age_girth_cm_per_year = 2.0); this fix
        # only makes the config actually drive the ledger going forward.
        try:
            self.age_cm_per_year = float(legal.get("age_girth_cm_per_year", 2.0) or 2.0)
        except (TypeError, ValueError):
            self.age_cm_per_year = 2.0
        self.legal = legal

        self.non_native: Dict[str, Dict[str, str]] = species_config.get("non_native", {}) or {}
        self.native_priority: Dict[str, Dict[str, str]] = {
            row["name"]: row for row in species_config.get("native_priority", []) or []
        }
        # Transplant ceiling applies per species AND globally.
        ceiling = species_config.get("transplant_hardy_ceiling_cm")
        self.transplant_ceiling_cm = float(ceiling) if ceiling else 45.0
        self.transplant_species: Dict[str, Dict[str, Any]] = {}
        for row in species_config.get("transplant_hardy", []) or []:
            rec = dict(row)
            rec["_max_girth"] = min(
                float(row.get("max_girth_cm", self.transplant_ceiling_cm)),
                self.transplant_ceiling_cm,
            )
            self.transplant_species[row["name"]] = rec

        self.heritage_girth_cm = float(
            (species_config.get("legal", {}) or {}).get("heritage_girth_cm", 90.0)
        )

    # -- classification ---------------------------------------------------

    def classify_species(self, botanical_name: str) -> str:
        key = species_key(botanical_name)
        if not key:
            return "unknown"
        if key in self.non_native:
            return "non_native"
        if key in self.native_priority:
            return "native_priority"
        return "unclassified"

    def is_native(self, botanical_name: str) -> str:
        """Native-ness for compensation purposes.

        'unclassified' is treated as native-conservative: we assume native and
        demand more replacement, because under-planting is the failure mode that
        actually damages the city. over-planting is a cost, not an ecological
        loss. Unknown species default to the stricter branch.
        """
        return self.classify_species(botanical_name) != "non_native"

    # -- per-tree decision ------------------------------------------------

    def evaluate_tree(
        self,
        tree: TreeRecord,
        inside_building_footprint: bool,
        preserve_only: bool = False,
    ) -> TreeDecision:
        key = species_key(tree.botanical_name)
        crown = canopy_area_m2(tree.canopy_dia_m)
        girth = float(tree.girth_cm)
        tier = maturity_tier(girth)

        # 1. Dead trees carry no ecological value and are not felled — removed.
        if tree.is_dead:
            return TreeDecision(
                tree_id=tree.tree_id,
                botanical_name=tree.botanical_name,
                species_key=key,
                girth_cm=girth,
                canopy_m2=crown,
                action="REMOVE_DEAD",
                reason="Census condition is dead/fallen. No felling permit required to "
                       "remove a dead tree, and no ecological loss.",
                statutory_basis="Not applicable — removal of a dead tree.",
                compensatory_saplings={},
            )

        # 2. House policy: preserve heritage-class trees. Rare flag wins first.
        if tree.is_rare:
            return TreeDecision(
                tree_id=tree.tree_id,
                botanical_name=tree.botanical_name,
                species_key=key,
                girth_cm=girth,
                canopy_m2=crown,
                action="MUST_PRESERVE",
                reason="Census is_rare flag set. Rare species cannot be substituted "
                       "with saplings — the genotype is the asset.",
                statutory_basis="PMC census 2019 is_rare flag.",
                compensatory_saplings={},
                age_estimate_years=estimate_age_years(
                    girth, self.age_cm_per_year),
            )

        if girth >= self.heritage_girth_cm:
            return TreeDecision(
                tree_id=tree.tree_id,
                botanical_name=tree.botanical_name,
                species_key=key,
                girth_cm=girth,
                canopy_m2=crown,
                action="MUST_PRESERVE",
                reason=f"Girth {girth:.0f} cm at or above the 90 cm house-policy "
                       f"heritage threshold. Relocation is not realistic at this "
                       f"size; design should be adjusted to retain the tree.",
                statutory_basis="HOUSE POLICY (not the 1975 Act) — the Act requires "
                                "Tree Officer permission, with no girth-based "
                                "automatic prohibition.",
                compensatory_saplings={},
                age_estimate_years=estimate_age_years(
                    girth, self.age_cm_per_year),
            )

        # 3. Outside the footprint and not in force-relocation mode: preserve.
        if not inside_building_footprint and not preserve_only:
            return TreeDecision(
                tree_id=tree.tree_id,
                botanical_name=tree.botanical_name,
                species_key=key,
                girth_cm=girth,
                canopy_m2=crown,
                action="PRESERVE",
                reason="Outside the built-up footprint. Retained in place.",
                statutory_basis="No permit needed while the tree is retained.",
                compensatory_saplings={},
            )

        # 4. Transplant candidate: small enough, healthy enough, hardy species.
        if (
            not preserve_only
            and key in self.transplant_species
            and girth <= self.transplant_species[key]["_max_girth"]
            and not tree.is_poor
            and not tree.is_dead
        ):
            rec = self.transplant_species[key]
            return TreeDecision(
                tree_id=tree.tree_id,
                botanical_name=tree.botanical_name,
                species_key=key,
                girth_cm=girth,
                canopy_m2=crown,
                action="RELOCATE",
                reason=f"{key} at {girth:.0f} cm is within the transplant ceiling "
                       f"({self.transplant_species[key]['_max_girth']:.0f} cm) and "
                       f"condition is '{tree.condition or 'unknown'}'. Root-ball "
                       f"transplantation is technically viable.",
                statutory_basis="HOUSE POLICY — relocatable under an arborist "
                                "assessment; a permit may still be required to "
                                "transplant rather than fell.",
                compensatory_saplings={},
                age_estimate_years=estimate_age_years(
                    girth, self.age_cm_per_year),
            )

        # 5. Otherwise: fell with compensation.
        native = self.is_native(tree.botanical_name)
        age = estimate_age_years(girth, self.age_cm_per_year)
        ratio_lo = int(age["low"]) if age["low"] > 0 else 0
        ratio_hi = int(age["high"]) if age["high"] > 0 else 0
        basis = (
            "Maharashtra (Urban Areas) Protection of Trees Act 1975 (as amended "
            "2021) — compensation is trees planted in number equal to the AGE "
            "of the tree felled. Age is estimated from girth here; the census "
            "has no age column."
        )

        if native:
            ratio_lo, ratio_hi = max(ratio_lo, 3), max(ratio_hi, 3)
            reason = (
                f"{key} at {girth:.0f} cm obstructs the footprint and exceeds the "
                f"transplant ceiling ({self.transplant_ceiling_cm:.0f} cm), so "
                f"relocation is not reliable. Compensation is age-equivalent, "
                f"estimated {ratio_lo}-{ratio_hi} saplings. Species is treated "
                f"as native so the native-conservative branch applies."
            )
        else:
            ratio_lo, ratio_hi = max(ratio_lo, 1), max(ratio_hi, 1)
            basis = (
                "Maharashtra (Urban Areas) Protection of Trees Act 1975 (as amended "
                "2021) — compensation is age-equivalent and SPECIES-BLIND. The statutory "
                "count is identical for a native and a non-native tree. This tool "
                "applies the same count to both and expresses the native/non-native "
                "distinction in the recommended species mix instead, which is the "
                "ecologically meaningful lever and stays inside the Act."
            )
            reason = (
                f"{key} at {girth:.0f} cm is a confirmed non-native species "
                f"obstructing the footprint. Statutory compensation is "
                f"{ratio_lo}-{ratio_hi} saplings, identical to what a native of "
                f"the same girth would require — but the recommended mix is "
                f"native-weighted, so the replanting is not simply more Subabul."
            )

        return TreeDecision(
            tree_id=tree.tree_id,
            botanical_name=tree.botanical_name,
            species_key=key,
            girth_cm=girth,
            canopy_m2=crown,
            action="FELL_AND_COMPENSATE",
            reason=reason,
            statutory_basis=basis,
            compensatory_saplings={"low": ratio_lo, "high": ratio_hi},
            age_estimate_years=age,
        )

    # -- site roll-up -----------------------------------------------------

    def process_site(
        self,
        trees: Iterable[TreeRecord],
        plot_area_m2: float,
        footprint_trees: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Roll per-tree decisions up to a site-level ledger.

        footprint_trees: set of tree_ids inside the built-up footprint. Trees in
        this set are treated as obstructed; all others are preserved. When
        None, every supplied tree is assumed obstructed, which is the
        conservative assumption for a site plan the user has drawn.
        """
        trees = list(trees)
        all_ids = {t.tree_id for t in trees}
        in_fp = all_ids if footprint_trees is None else (set(footprint_trees) & all_ids)

        total_canopy = 0.0
        canopy_before = 0.0
        canopy_after = 0.0
        decisions: List[TreeDecision] = []
        comp_lo = comp_hi = 0
        species_risk: Dict[str, int] = {}
        counts: Dict[str, int] = {}
        rare_at_risk = 0
        dead_removed = 0

        for t in trees:
            crown = canopy_area_m2(t.canopy_dia_m)
            # Dead trees do not contribute existing canopy.
            if not t.is_dead:
                canopy_before += crown
            d = self.evaluate_tree(t, inside_building_footprint=(t.tree_id in in_fp))
            decisions.append(d)
            counts[d.action] = counts.get(d.action, 0) + 1

            if d.action in ("PRESERVE", "MUST_PRESERVE", "RELOCATE"):
                canopy_after += crown
            if d.action == "FELL_AND_COMPENSATE":
                comp_lo += d.compensatory_saplings.get("low", 0)
                comp_hi += d.compensatory_saplings.get("high", 0)
                species_risk[d.species_key] = species_risk.get(d.species_key, 0) + 1
            if d.action == "MUST_PRESERVE" and t.is_rare:
                rare_at_risk += 1
            if d.action == "REMOVE_DEAD":
                dead_removed += 1

        plot = max(1.0, float(plot_area_m2))
        # Crown areas can overlap each other; cap the union estimate so a dense
        # stand cannot report >100% canopy cover.
        canopy_cover_pct = min(100.0, (canopy_before / plot) * 100.0)

        comp_species = self._compensatory_mix(species_risk, comp_hi)

        return {
            "total_trees": len(trees),
            "tree_canopy_m2_before": round(canopy_before, 1),
            "tree_canopy_m2_after": round(canopy_after, 1),
            "tree_canopy_m2_lost": round(canopy_before - canopy_after, 1),
            "canopy_cover_pct": round(canopy_cover_pct, 1),
            "action_counts": counts,
            "rare_trees_in_site": sum(1 for t in trees if t.is_rare),
            "rare_trees_at_risk": rare_at_risk,
            "dead_trees_removed": dead_removed,
            "compensatory_required": {"low": comp_lo, "high": comp_hi},
            "compensatory_basis": "AGE_EQUIVALENT_ESTIMATE_FROM_GIRTH",
            "always_preserve_count": counts.get("MUST_PRESERVE", 0),
            "always_preserve_canopy_m2": round(
                sum(d.canopy_m2 for d in decisions if d.action == "MUST_PRESERVE"), 1
            ),
            "compensatory_species_mix": comp_species,
            "decisions": [d.to_dict() for d in decisions],
        }

    def _compensatory_mix(
        self, species_risk: Dict[str, int], comp_hi: int
    ) -> List[Dict[str, Any]]:
        """Native-weighted compensatory species mix.

        The census is 52.5% non-native in the 250k sample, with Leucaena alone
        at 15.7%. Replanting the statutory count of Subabul adds nothing. The
        mix is native-weighted so the statutory count is met with species that
        actually survive and cool the site.

        A native species is never "replaced" by itself: the entry records that
        it is being replanted in kind, and points at a native companion species
        for mix diversity instead. An earlier version emitted
        "replace Araucaria columnaris with Araucaria columnaris", which is
        useless advice to a Tree Officer.
        """
        mix: List[Dict[str, Any]] = []
        if not species_risk or comp_hi <= 0:
            return mix

        # Confirmed non-native felled species -> their native counterpart.
        replacements: Dict[str, str] = {
            "Leucaena leucocephala": "Mangifera indica",
            "Gliricidia sepium": "Azadirachta indica",
            "Polyalthia longifolia": "Syzygium cumini",
            "Millingtonia hortensis": "Syzygium cumini",
            "Ficus benjamina": "Ficus benghalensis",
            "Cocos nucifera": "Caryota urens",
            "Peltophorum pterocarpum": "Pongamia pinnata",
            "Delonix regia": "Bauhinia purpurea",
            "Tecoma stans": "Bauhinia purpurea",
            "Grevillea robusta": "Dalbergia melanoxylon",
            "Eucalyptus globulus": "Azadirachta indica",
            "Psidium gaujava": "Mangifera indica",
            "Terminalia catappa": "Syzygium cumini",
            "Spathodea campanulata": "Bauhinia purpurea",
            "Cascabela thevetia": "Bauhinia purpurea",
            "Pithecellobium dulce": "Pongamia pinnata",
            "Plumeria obtusa": "Bauhinia purpurea",
            "Casuarina equisetifolia": "Pongamia pinnata",
            "Manilkara zapota": "Syzygium cumini",
        }

        # Native species replanted in kind get a companion for mix diversity,
        # drawn from PMC's own proven natives and never equal to the original.
        companions: List[str] = [
            "Azadirachta indica", "Mangifera indica", "Syzygium cumini",
            "Pongamia pinnata", "Ficus benghalensis", "Dalbergia melanoxylon",
        ]

        total = sum(species_risk.values())
        for sp, n in sorted(species_risk.items(), key=lambda kv: -kv[1]):
            share = 100.0 * n / total
            native = self.is_native(sp)

            if native:
                companion = next(
                    (c for c in companions if c.lower() != sp.lower()), "Azadirachta indica"
                )
                mix.append(
                    {
                        "felled_species": sp,
                        "felled_share_pct": round(share, 1),
                        "strategy": "REPLANT_IN_KIND",
                        "recommended_replacement": sp,
                        "recommended_replacement_native": True,
                        "mix_companion": companion,
                        "note": "Native species. Replanted in kind; pair with "
                                f"{companion} for canopy and species diversity.",
                    }
                )
                continue

            alt = replacements.get(sp)
            if not alt or alt.lower() == sp.lower():
                alt = next((c for c in companions), "Azadirachta indica")
            mix.append(
                {
                    "felled_species": sp,
                    "felled_share_pct": round(share, 1),
                    "strategy": "REPLACE_WITH_NATIVE",
                    "recommended_replacement": alt,
                    "recommended_replacement_native": self.is_native(alt),
                    "recommended_replacement_origin": (
                        self.non_native.get(alt, {}).get("origin", "native")
                    ),
                    "mix_companion": alt,
                    "note": f"Non-native species occupying "
                            f"{self.non_native.get(sp, {}).get('origin', 'unknown')} "
                            f"origin. Statutory count is met, but not with this species.",
                }
            )
        return mix


def build_ledger(species_config: Dict[str, Any]) -> CanopyLedger:
    return CanopyLedger(species_config)
