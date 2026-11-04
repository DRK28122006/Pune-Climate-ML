/**
 * DEMONSTRATION OPTIMIZATION ENGINE
 * ---------------------------------
 * Every coefficient in this file is an illustrative assumption. Nothing here is
 * a validated scientific model, and nothing is calibrated to Pune measurements.
 *
 * To connect a real backend, replace `runDemoOptimization` with a call to your
 * API that resolves to an `OptimizationResult`. Nothing else in the UI needs to
 * change, as long as the result shape in `types.ts` is kept.
 */
import type {
  AllocationLine,
  FieldErrors,
  Levers,
  Metrics,
  OptimizationResult,
  PlanGoal,
  PlanInputs,
  SurfaceProfile,
  TrajectoryPoint,
} from '../types';
import { clamp } from './math';

export const MODEL_VERSION = 'demo-0.1';

/* ------------------------------------------------------------------ */
/* Validation                                                          */
/* ------------------------------------------------------------------ */

const isNum = (v: number) => typeof v === 'number' && Number.isFinite(v);

/** Legacy demo-model error map, keyed by the old PlanInputs shape. */
export type PlanFieldErrors = Partial<Record<keyof PlanInputs, string>>;

export function validateInputs(i: PlanInputs): PlanFieldErrors {
  const e: PlanFieldErrors = {};
  if (!i.planName.trim()) e.planName = 'Give the plan a name.';
  else if (i.planName.trim().length > 60) e.planName = 'Keep the name under 60 characters.';
  if (!i.focusArea) e.focusArea = 'Choose a focus area.';

  const range = (key: keyof PlanInputs, v: number, min: number, max: number, label: string) => {
    if (!isNum(v)) e[key] = `Enter a number for ${label}.`;
    else if (v < min || v > max) e[key] = `${label} must be between ${min} and ${max}.`;
  };
  range('areaHa', i.areaHa, 5, 5000, 'Plan area');
  range('builtUpPct', i.builtUpPct, 0, 100, 'Built-up share');
  range('pavedPct', i.pavedPct, 0, 100, 'Paved share');
  range('canopyPct', i.canopyPct, 0, 100, 'Tree canopy');
  range('budgetCrore', i.budgetCrore, 1, 2000, 'Budget');
  range('horizonYears', i.horizonYears, 10, 50, 'Planning horizon');

  if (!e.builtUpPct && !e.canopyPct && i.builtUpPct + i.canopyPct > 100)
    e.canopyPct = 'Built-up share plus tree canopy cannot exceed 100%.';
  if (!e.pavedPct && !e.canopyPct && !e.builtUpPct && i.pavedPct + i.builtUpPct + i.canopyPct > 100)
    e.pavedPct = 'Built-up, paved and canopy shares together cannot exceed 100%.';
  return e;
}

/* ------------------------------------------------------------------ */
/* Surface model (shared by optimizer and Scenario Planner)            */
/* ------------------------------------------------------------------ */

export function baselineMetrics(p: SurfaceProfile): Metrics {
  return {
    canopyPct: p.canopyPct,
    surfaceTempC: 31 + 0.085 * p.builtUpPct + 0.05 * p.pavedPct - 0.14 * p.canopyPct,
    runoffIndex: clamp(25 + 0.55 * p.pavedPct + 0.15 * p.builtUpPct - 0.25 * p.canopyPct, 5, 100),
    airIndex: clamp(70 + p.builtUpPct + 0.5 * p.pavedPct - 0.9 * p.canopyPct, 20, 300),
  };
}

export function openLandPct(p: SurfaceProfile): number {
  return Math.max(0, 100 - p.builtUpPct - p.canopyPct);
}

/** Apply lever settings to a surface profile and return demo metrics. */
export function applyLevers(p: SurfaceProfile, l: Levers): Metrics {
  const canopyGain = (openLandPct(p) * l.treesPct) / 100;
  const roofShare = (p.builtUpPct * l.roofsPct) / 100;
  const converted = (p.pavedPct * l.pavingPct) / 100;
  const canopy = p.canopyPct + canopyGain;
  const base = baselineMetrics({ ...p, canopyPct: canopy, pavedPct: p.pavedPct - converted });
  return {
    canopyPct: canopy,
    surfaceTempC: base.surfaceTempC - 0.045 * roofShare - 0.02 * converted,
    runoffIndex: base.runoffIndex,
    airIndex: base.airIndex,
  };
}

/**
 * Project a scenario against an anchor (for example the city's sample figures).
 * The model's change is applied on top of the anchor so the starting point matches.
 */
export function projectScenario(p: SurfaceProfile, l: Levers, anchor?: Metrics): Metrics {
  const before = baselineMetrics(p);
  const after = applyLevers(p, l);
  if (!anchor) return after;
  return {
    canopyPct: anchor.canopyPct + (after.canopyPct - before.canopyPct),
    surfaceTempC: anchor.surfaceTempC + (after.surfaceTempC - before.surfaceTempC),
    runoffIndex: clamp(anchor.runoffIndex + (after.runoffIndex - before.runoffIndex), 0, 100),
    airIndex: clamp(anchor.airIndex + (after.airIndex - before.airIndex), 0, 300),
  };
}

export const LEVER_LIMITS: Record<keyof Levers, number> = { treesPct: 60, roofsPct: 70, pavingPct: 60 };

/* ------------------------------------------------------------------ */
/* Optimizer                                                           */
/* ------------------------------------------------------------------ */

const LEVER_COST_SCALE: Record<keyof Levers, number> = { treesPct: 5, roofsPct: 8, pavingPct: 6 };
const LEVER_LABELS: Record<keyof Levers, string> = {
  treesPct: 'Tree planting on open land',
  roofsPct: 'Cool roofs on buildings',
  pavingPct: 'Permeable paving',
};

const GOAL_WEIGHTS: Record<PlanGoal, { temp: number; runoff: number; canopy: number; air: number }> = {
  balanced: { temp: 1, runoff: 1, canopy: 1, air: 1 },
  cooling: { temp: 2.4, runoff: 0.6, canopy: 0.8, air: 0.6 },
  flood: { temp: 0.6, runoff: 2.4, canopy: 0.8, air: 0.6 },
  greening: { temp: 0.8, runoff: 0.8, canopy: 2.4, air: 1.2 },
};

export class OptimizationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OptimizationError';
  }
}

const leversFromSpend = (spend: Record<keyof Levers, number>, areaScale: number): Levers => {
  const pct = (k: keyof Levers) =>
    LEVER_LIMITS[k] * (1 - Math.exp(-spend[k] / (LEVER_COST_SCALE[k] * areaScale)));
  return { treesPct: pct('treesPct'), roofsPct: pct('roofsPct'), pavingPct: pct('pavingPct') };
};

/** Deterministic: the same inputs always give the same output. */
export function optimizePlan(inputs: PlanInputs): OptimizationResult {
  const profile: SurfaceProfile = {
    builtUpPct: inputs.builtUpPct,
    pavedPct: inputs.pavedPct,
    canopyPct: inputs.canopyPct,
  };
  const areaScale = inputs.areaHa / 100;
  if (inputs.budgetCrore / areaScale < 0.5) {
    throw new OptimizationError(
      'Demo rule: this budget is too small to fund any intervention for a plan this large. Increase the budget or reduce the area.',
    );
  }

  const w = GOAL_WEIGHTS[inputs.goal];
  const score = (a: Metrics, b: Metrics) =>
    w.temp * (a.surfaceTempC - b.surfaceTempC) / 1 +
    w.runoff * (a.runoffIndex - b.runoffIndex) / 10 +
    w.canopy * (b.canopyPct - a.canopyPct) / 3 +
    w.air * (a.airIndex - b.airIndex) / 30;

  const keys: (keyof Levers)[] = ['treesPct', 'roofsPct', 'pavingPct'];
  const spend: Record<keyof Levers, number> = { treesPct: 0, roofsPct: 0, pavingPct: 0 };
  const steps = 150;
  const step = inputs.budgetCrore / steps;
  for (let s = 0; s < steps; s++) {
    const current = applyLevers(profile, leversFromSpend(spend, areaScale));
    let best: keyof Levers = 'treesPct';
    let bestScore = -Infinity;
    for (const k of keys) {
      const trial = { ...spend, [k]: spend[k] + step };
      const sc = score(current, applyLevers(profile, leversFromSpend(trial, areaScale)));
      if (sc > bestScore + 1e-12) {
        bestScore = sc;
        best = k;
      }
    }
    spend[best] += step;
  }

  const levers = leversFromSpend(spend, areaScale);
  const before = baselineMetrics(profile);
  const after = applyLevers(profile, levers);

  const allocation: AllocationLine[] = keys
    .map((k) => ({
      lever: k,
      label: LEVER_LABELS[k],
      crore: spend[k],
      sharePct: (spend[k] / inputs.budgetCrore) * 100,
      detail:
        k === 'treesPct'
          ? `${levers.treesPct.toFixed(0)}% of open land planted`
          : k === 'roofsPct'
            ? `${levers.roofsPct.toFixed(0)}% of buildings with cool roofs`
            : `${levers.pavingPct.toFixed(0)}% of paved area made permeable`,
    }))
    .sort((a, b) => b.crore - a.crore);

  const H = inputs.horizonYears;
  const tau = H * 0.4;
  const treeFrac = (y: number) => (1 - Math.exp(-y / tau)) / (1 - Math.exp(-H / tau));
  const otherFrac = (y: number) => Math.min(1, y / (H * 0.25));
  const every = Math.max(1, Math.round(H / 10));
  const years: number[] = [];
  for (let y = 0; y < H; y += every) years.push(y);
  years.push(H);
  const trajectory: TrajectoryPoint[] = years.map((y) => {
    const m = applyLevers(profile, {
      treesPct: levers.treesPct * treeFrac(y),
      roofsPct: levers.roofsPct * otherFrac(y),
      pavingPct: levers.pavingPct * otherFrac(y),
    });
    return { year: y, canopyPct: m.canopyPct, surfaceTempC: m.surfaceTempC, baselineTempC: before.surfaceTempC };
  });

  const top = allocation[0];
  const implications = [
    `In this demo model, spending is led by "${top.label.toLowerCase()}" (${top.sharePct.toFixed(0)}% of the budget) under the "${inputs.goal}" goal.`,
    `Canopy moves from ${before.canopyPct.toFixed(1)}% to ${after.canopyPct.toFixed(1)}% by year ${H}. Tree growth is slow, so most of the cooling from trees arrives late in the horizon.`,
    `Modelled surface temperature changes by ${(after.surfaceTempC - before.surfaceTempC).toFixed(1)}°C and the demo runoff index by ${(after.runoffIndex - before.runoffIndex).toFixed(1)} points.`,
    'Change the goal or the budget and run the optimization again to see how the allocation shifts. Treat the numbers as a way to compare options, not as forecasts.',
  ];

  return {
    isDemo: true,
    modelVersion: MODEL_VERSION,
    inputs: { ...inputs },
    levers,
    before,
    after,
    allocation,
    trajectory,
    implications,
  };
}

/**
 * Async wrapper that stands in for a network call. Replace this function with a
 * real API request to plug in a backend.
 */
export function runDemoOptimization(
  inputs: PlanInputs,
  opts: { delayMs?: number; signal?: AbortSignal } = {},
): Promise<OptimizationResult> {
  const { delayMs = 2200, signal } = opts;
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      try {
        resolve(optimizePlan(inputs));
      } catch (err) {
        reject(err);
      }
    }, delayMs);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(new DOMException('Optimization cancelled', 'AbortError'));
    });
  });
}
