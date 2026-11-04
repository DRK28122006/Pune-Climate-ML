import type { AssessmentGoal } from './types';

export const APP_NAME = 'DishaDharti';
export const TAGLINE = 'Plan the city in a better direction.';
export const CITY = 'Pune';

/** Canopy target taken from the supplied HTML prototype. Treat as a placeholder planning target. */
export const CANOPY_TARGET_PCT = 33;

export const DEMO_NOTICE =
  'Demonstration data. Values are simulated and are not measurements, official statistics or validated predictions.';

/**
 * How green the background scene gets on each dashboard page once a plan has been
 * successfully optimized. Before optimization every page stays in the polluted state.
 */
export const PAGE_INTENSITY: Record<string, number> = {
  overview: 0.55,
  heat: 0.45,
  'air-quality': 0.55,
  'green-cover': 0.85,
  'flood-risk': 0.5,
  'scenario-planner': 0.65,
};
/** The 41 Pune Municipal Corporation wards (names from pmc_wards_2025.kml). */
export const WARDS = Array.from({ length: 41 }, (_, i) => ({
  value: String(i + 1),
  label: `Ward ${i + 1}`,
}));

/** Cradle-to-gate India materials (IFC Table 16 GWP / CEEW for aluminium). */
export const MATERIALS: { value: string; label: string; ef: number }[] = [
  { value: 'cement_opc', label: 'Cement — OPC', ef: 0.91 },
  { value: 'cement_ppc', label: 'Cement — PPC', ef: 0.507 },
  { value: 'cement_psc', label: 'Cement — PSC', ef: 0.312 },
  { value: 'cement_ggbs', label: 'Cement — GGBS', ef: 0.05 },
  { value: 'concrete_ready_mix', label: 'Ready-mix concrete', ef: 0.11 },
  { value: 'concrete_low_clinker_30ggbs', label: '30% GGBS concrete', ef: 0.089 },
  { value: 'steel_reinforcement', label: 'Steel — rebar (BOF)', ef: 2.6 },
  { value: 'steel_rebar_eaf', label: 'Steel — rebar (EAF)', ef: 0.83 },
  { value: 'steel_rebar_recycled', label: 'Steel — recycled rebar', ef: 0.45 },
  { value: 'brick_clay', label: 'Brick — clay (fired)', ef: 0.39 },
  { value: 'fly_ash_brick', label: 'Brick — fly ash', ef: 0.09 },
  { value: 'aac_block', label: 'AAC block', ef: 0.11 },
  { value: 'hollow_concrete_block', label: 'Hollow concrete block', ef: 0.14 },
  { value: 'river_sand', label: 'River sand', ef: 0.009 },
  { value: 'manufactured_sand_msand', label: 'Manufactured sand (M-sand)', ef: 0.008 },
  { value: 'aggregate_rock', label: 'Aggregate — rock', ef: 0.009 },
  { value: 'aggregate_recycled', label: 'Aggregate — recycled', ef: 0.01 },
  { value: 'glass_float', label: 'Glass — float', ef: 1.2 },
  { value: 'glass_recycled_cullet', label: 'Glass — recycled', ef: 0.5 },
  { value: 'aluminium_primary', label: 'Aluminium — primary', ef: 20.88 },
  { value: 'aluminium_recycled', label: 'Aluminium — recycled', ef: 0.9 },
  { value: 'timber_wood', label: 'Timber — wood', ef: 0.5 },
  { value: 'gypsum_plaster', label: 'Gypsum plaster', ef: 0.15 },
  { value: 'tiles_vitrified', label: 'Tiles — vitrified', ef: 0.35 },
  { value: 'paint_emulsion', label: 'Paint — emulsion', ef: 0.3 },
  { value: 'insulation_mineral', label: 'Insulation — mineral wool', ef: 0.9 },
];

export const GOAL_LABELS: Record<AssessmentGoal, string> = {
  balanced: 'Balanced',
  cooling: 'Cooling first',
  flood: 'Flood resilience first',
  greening: 'Canopy first',
};
