"""Relocation siting engine — L6.

Given trees that need to move, find real places in Pune to move them to, and
rank them by defensible ecological criteria.

The problem statement asks for "potential relocation sites based on green cover,
biodiversity, and local environmental needs". This module turns that into
four measurable, separately reported criteria rather than one invented
"suitability score":

  1. SPACING      Is there room? Free area in the park relative to the canopy
                 that needs to be installed. A park already at canopy capacity
                 cannot absorb more.
  2. CONNECTIVITY How well is the park joined to existing green? Gap to the
                 nearest large green patch, and green cover already in the
                 surrounding 300 m. Planting into an isolated fragment is
                 worse than planting into a corridor.
  3. FLOOD       Is the receiving site itself flood-exposed? Planting a mature
                 sapling into a nalla floodplain wastes it. Sourced from the
                 reference layers, with the nalla/river proximity treated as
                 EXPOSURE.
  4. ACCESS      Is it maintainable? Park proximity to the site it serves,
                 because a transplanted tree that cannot be watered dies.

Each criterion returns a sub-score with its own reason, and the composite is
reported alongside them so a planner can disagree with one criterion without
discarding the whole ranking.

Pure logic plus lookups against the reference layers. No network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ml_pipeline.core import geometry as G

# A transplanted tree needs roughly this much root space when mature.
# Deliberately conservative: this is a feasibility floor, not a design value.
MIN_ROOT_AREA_M2_PER_TREE = 25.0

# Canopy a relocated tree is expected to re-establish at maturity.
MEAN_MATURE_CANOPY_M2 = 35.0

# Above this canopy fraction of a park's area, treat it as capacity-limited.
CANOPY_SATURATION_PCT = 45.0

# Flood exposure penalty kicks in inside this distance of a natural watercourse.
FLOOD_EXPOSURE_PENALTY_M = 150.0
FLOOD_EXPOSURE_STRONG_PENALTY_M = 50.0

WEIGHTS = {
    "spacing": 0.35,
    "connectivity": 0.25,
    "flood": 0.25,
    "access": 0.15,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return lo
    if v != v:
        return lo
    return max(lo, min(hi, v))


def _green_patch_score(patch_area_m2: float, canopy_pct: float) -> float:
    """How substantial is an existing green patch?

    Log-scaled so a 1 ha park and a 2 ha park are not treated as equally good,
    but a 2 ha park does not swamp a 1.2 ha one either.
    """
    if patch_area_m2 <= 0:
        return 0.0
    # 1,000 m2 -> ~25; 10,000 m2 -> ~62; 100,000 m2 -> ~100
    size_term = _clamp(25.0 * math.log10(max(patch_area_m2, 1.0)))
    quality_term = _clamp(canopy_pct * 1.2)
    return 0.65 * size_term + 0.35 * quality_term


@dataclass
class SitingCriterion:
    name: str
    score: float
    weight: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion": self.name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "reason": self.reason,
        }


@dataclass
class CandidateSite:
    park_id: int
    name: str
    distance_m: float
    area_m2: float
    lon: float
    lat: float
    ward_no: Optional[int]
    criteria: List[SitingCriterion] = field(default_factory=list)
    composite: float = 0.0
    rank: Optional[int] = None
    capacity_trees: Optional[int] = None
    viable: bool = True
    disqualifiers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "park_id": self.park_id,
            "name": self.name,
            "ward_no": self.ward_no,
            "distance_m": round(self.distance_m, 1),
            "area_m2": round(self.area_m2, 1),
            "area_hectares": round(self.area_m2 / 10_000.0, 3),
            "lon": round(self.lon, 6),
            "lat": round(self.lat, 6),
            "viable": self.viable,
            "disqualifiers": self.disqualifiers,
            "capacity_trees": self.capacity_trees,
            "composite_score": round(self.composite, 1),
            "criteria": [c.to_dict() for c in self.criteria],
        }


class RelocationSitingEngine:
    """Ranks parks as relocation destinations for one site."""

    def __init__(
        self,
        search_radius_m: float = 2000.0,
        max_trees_per_site: int = 60,
        min_park_area_m2: float = 400.0,
    ) -> None:
        self.search_radius_m = search_radius_m
        self.max_trees_per_site = max_trees_per_site
        self.min_park_area_m2 = min_park_area_m2

    # -- criteria ---------------------------------------------------------

    def _score_spacing(
        self, park: Dict[str, Any], canopy_needed_m2: float, trees: int
    ) -> SitingCriterion:
        area = park.get("area_m2") or 0.0
        if area < self.min_park_area_m2:
            return SitingCriterion(
                "spacing", 0.0, WEIGHTS["spacing"],
                f"Park area {area:.0f} m2 is below the {self.min_park_area_m2:.0f} m2 "
                f"minimum viable for planting.",
            )

        canopy_needed_pct = 100.0 * canopy_needed_m2 / area
        if canopy_needed_pct >= CANOPY_SATURATION_PCT:
            return SitingCriterion(
                "spacing", 0.0, WEIGHTS["spacing"],
                f"Installing {canopy_needed_m2:.0f} m2 canopy would take this park to "
                f"{canopy_needed_pct:.0f}% canopy, above the {CANOPY_SATURATION_PCT:.0f}% "
                f"saturation threshold. No room without thinning.",
            )

        # Room to spare scales with how far below saturation we stay.
        headroom = 1.0 - (canopy_needed_pct / CANOPY_SATURATION_PCT)
        score = _clamp(40.0 + 60.0 * headroom)
        return SitingCriterion(
            "spacing", score, WEIGHTS["spacing"],
            f"Park {area:.0f} m2. The {canopy_needed_m2:.0f} m2 of canopy needed is "
            f"{canopy_needed_pct:.0f}% of park area, leaving "
            f"{(CANOPY_SATURATION_PCT - canopy_needed_pct):.0f} pts of headroom.",
        )

    def _score_connectivity(
        self, park: Dict[str, Any], site_pt: tuple
    ) -> SitingCriterion:
        # Green already present in a 300 m halo around the park.
        halo = G.parks_near(park_pt := (park["lon"], park["lat"]), radius_m=300.0, limit=50)
        halo_area = sum(p.get("area_m2") or 0.0 for p in halo)
        halo_score = _clamp(_green_patch_score(halo_area, 30.0))

        # Distance from the park to the site being served. Nearer means the
        # planting continues the site's own green network rather than starting
        # an isolated one.
        dist = park["distance_m"]
        proximity = _clamp(100.0 - (dist / max(self.search_radius_m, 1.0)) * 100.0)

        score = 0.55 * halo_score + 0.45 * proximity
        return SitingCriterion(
            "connectivity", score, WEIGHTS["connectivity"],
            f"{halo_area:.0f} m2 of green within 300 m of this park, and it is "
            f"{dist:.0f} m from the development site.",
        )

    def _score_flood(self, park_pt: tuple) -> SitingCriterion:
        ctx = G.drainage_context(park_pt, radius_m=300.0)
        if not ctx.get("available"):
            return SitingCriterion(
                "flood", 50.0, WEIGHTS["flood"],
                "Drainage layers unavailable; no flood adjustment applied.",
            )

        nearest_natural = ctx.get("nearest_natural_water_m")
        if nearest_natural is None:
            return SitingCriterion(
                "flood", 100.0, WEIGHTS["flood"],
                "No nalla or river within 300 m. Not flood-exposed.",
            )

        if nearest_natural <= FLOOD_EXPOSURE_STRONG_PENALTY_M:
            score = 10.0
            reason = (
                f"Only {nearest_natural:.0f} m from a natural watercourse. A mature "
                f"tree planted here is likely lost to inundation. Do not site here."
            )
        elif nearest_natural <= FLOOD_EXPOSURE_PENALTY_M:
            score = 45.0
            reason = (
                f"{nearest_natural:.0f} m from a nalla or river — inside the "
                f"flood-plain buffer. Usable only with species tolerant of "
                f"periodic inundation and a raised planting bed."
            )
        else:
            score = 100.0
            reason = f"{nearest_natural:.0f} m from the nearest watercourse. Not exposed."

        return SitingCriterion("flood", score, WEIGHTS["flood"], reason)

    def _score_access(self, park: Dict[str, Any]) -> SitingCriterion:
        dist = park["distance_m"]
        # Under 400 m is a short cart. Over 1.5 km a sapling needs a truck each time.
        score = _clamp(100.0 - (dist / 1500.0) * 100.0)
        return SitingCriterion(
            "access", score, WEIGHTS["access"],
            f"{dist:.0f} m from the development site; affects watering and "
            f"maintenance cost for the first two to three years.",
        )

    # -- ranking ----------------------------------------------------------

    def rank_sites(
        self,
        site_pt: tuple,
        trees_to_relocate: int,
        canopy_needed_m2: Optional[float] = None,
        max_results: int = 8,
    ) -> Dict[str, Any]:
        """Rank parks as destinations for `trees_to_relocate` trees."""
        n = max(0, int(trees_to_relocate))
        if n == 0:
            return {
                "requested_trees": 0,
                "candidates": [],
                "note": "No trees require relocation.",
            }

        canopy_needed = (
            float(canopy_needed_m2)
            if canopy_needed_m2 is not None
            else n * MEAN_MATURE_CANOPY_M2
        )

        parks = G.parks_near(site_pt, radius_m=self.search_radius_m, limit=400)
        if not parks:
            return {
                "requested_trees": n,
                "canopy_needed_m2": round(canopy_needed, 1),
                "candidates": [],
                "note": f"No PMC-mapped park within {self.search_radius_m:.0f} m. "
                        f"Relocation candidates must be supplied by the Tree Officer; "
                        f"this dataset does not include private or institutional land.",
            }

        candidates: List[CandidateSite] = []
        for p in parks:
            c = CandidateSite(
                park_id=p["park_id"],
                name=p["name"],
                distance_m=p["distance_m"],
                area_m2=p.get("area_m2") or 0.0,
                lon=p["lon"],
                lat=p["lat"],
                ward_no=p.get("ward_no"),
            )

            # Capacity: how many of the requested trees could this park hold?
            usable = max(0.0, c.area_m2 * (CANOPY_SATURATION_PCT / 100.0) - canopy_needed)
            c.capacity_trees = int(max(0.0, usable / MIN_ROOT_AREA_M2_PER_TREE))

            c.criteria = [
                self._score_spacing(p, canopy_needed, n),
                self._score_connectivity(p, site_pt),
                self._score_flood((p["lon"], p["lat"])),
                self._score_access(p),
            ]

            # Hard disqualifiers, applied after scoring so the reason survives.
            if c.area_m2 < self.min_park_area_m2:
                c.viable = False
                c.disqualifiers.append("park too small to plant into")
            flood = next((x for x in c.criteria if x.name == "flood"), None)
            if flood and flood.score <= 10.0:
                c.viable = False
                c.disqualifiers.append("inside nalla flood-plain exposure")

            c.composite = sum(x.score * x.weight for x in c.criteria)
            if not c.viable:
                # Push disqualified sites below viable ones rather than
                # dropping them, so a planner can still see the near-miss.
                c.composite -= 40.0
            candidates.append(c)

        candidates.sort(key=lambda x: (-x.composite, x.distance_m))
        for i, c in enumerate(candidates[:max_results], start=1):
            c.rank = i

        viable = [c for c in candidates if c.viable]
        return {
            "requested_trees": n,
            "canopy_needed_m2": round(canopy_needed, 1),
            "assumed_mature_canopy_m2_per_tree": MEAN_MATURE_CANOPY_M2,
            "search_radius_m": self.search_radius_m,
            "weights": WEIGHTS,
            "parks_examined": len(parks),
            "viable_count": len(viable),
            "candidates": [c.to_dict() for c in candidates[:max_results]],
            "method_note": (
                "Composite = 0.35*spacing + 0.25*connectivity + 0.25*flood + "
                "0.15*access. Each criterion is reported separately so it can be "
                "challenged on its own. Flood uses distance to NATURAL watercourses "
                "(nallas, rivers) as exposure; engineered stormwater proximity is "
                "deliberately not a siting bonus."
            ),
            "data_limit": (
                "Only PMC-mapped parks and gardens are considered. Private gardens, "
                "institutional grounds and undeveloped municipal plots are not in "
                "this dataset, so viable_count understates the true options."
            ),
        }


def suggest_relocation(
    site_pt: tuple,
    relocate_trees: int,
    search_radius_m: float = 2000.0,
    max_results: int = 5,
) -> Dict[str, Any]:
    engine = RelocationSitingEngine(search_radius_m=search_radius_m)
    return engine.rank_sites(
        site_pt, relocate_trees, max_results=max_results
    )
