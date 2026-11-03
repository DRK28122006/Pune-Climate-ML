import type { PlanInputs } from './types';

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

/** Wards named in the supplied prototype. Replace with the real ward list. */
export const FOCUS_AREAS = ['Hadapsar', 'Yerawada', 'Katraj', 'Kothrud', 'Baner', 'Aundh'];

export const DEFAULT_INPUTS: PlanInputs = {
  planName: 'Hadapsar greening plan',
  focusArea: 'Hadapsar',
  areaHa: 120,
  builtUpPct: 58,
  pavedPct: 24,
  canopyPct: 9,
  budgetCrore: 40,
  horizonYears: 30,
  goal: 'balanced',
};

export const GOAL_LABELS = {
  balanced: 'Balanced',
  cooling: 'Cooling first',
  flood: 'Flood resilience first',
  greening: 'Canopy first',
} as const;
