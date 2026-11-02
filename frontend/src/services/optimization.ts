import type { PlanInputs, OptimizationResult, Metrics, Levers, AllocationLine, TrajectoryPoint } from '../types';
import { createAssessment } from './climateApi';

export class OptimizationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OptimizationError';
  }
}

function landCoverFromInputs(inputs: PlanInputs) {
  const impervious = inputs.builtUpPct + inputs.pavedPct;
  const vegetation = Math.max(0, 100 - impervious);
  return {
    vegetation_pct: Number(vegetation.toFixed(2)),
    impervious_pct: Number(impervious.toFixed(2)),
    water_pct: 0,
  };
}

function lstFromInputs(inputs: PlanInputs) {
  return 31 + 0.085 * inputs.builtUpPct + 0.05 * inputs.pavedPct - 0.14 * inputs.canopyPct;
}

function toMetrics(a: { vegetation: number; lst: number; floodRisk: number; carbonImpact: number }): Metrics {
  return {
    canopyPct: Number(a.vegetation.toFixed(1)),
    surfaceTempC: Number(a.lst.toFixed(1)),
    runoffIndex: Number(a.floodRisk.toFixed(1)),
    airIndex: Number(a.carbonImpact.toFixed(0)),
  };
}

function trajectoryBetween(before: Metrics, after: Metrics, years: number): TrajectoryPoint[] {
  const points: TrajectoryPoint[] = [];
  const steps = Math.max(2, Math.min(11, Math.round(years / 3) + 1));
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const y = Math.round((years * i) / steps);
    points.push({
      year: y,
      canopyPct: before.canopyPct + (after.canopyPct - before.canopyPct) * t,
      surfaceTempC: before.surfaceTempC + (after.surfaceTempC - before.surfaceTempC) * t,
      baselineTempC: before.surfaceTempC,
    });
  }
  // de-duplicate years
  const seen = new Set<number>();
  return points.filter((p) => (seen.has(p.year) ? false : (seen.add(p.year), true)));
}

export async function runOptimization(inputs: PlanInputs): Promise<OptimizationResult> {
  const builtUpAreaSqm = Math.max(100, Math.round(inputs.areaHa * 10000 * (inputs.builtUpPct / 100) || 10000));
  const payload = {
    name: inputs.planName,
    type: 'Urban climate plan',
    organization: '',
    description: `Focus area: ${inputs.focusArea}. Goal: ${inputs.goal}.`,
    location: inputs.focusArea || 'Pune',
    coordinates: { lat: 18.5204, lon: 73.8567 },
    bufferM: 500,
    builtUpAreaSqm,
    materials: {},
    mlOutput: {
      landcover: landCoverFromInputs(inputs),
      ndvi_mean: 0.3,
      ndbi_mean: 0.5,
      ndwi_mean: 0.1,
      lst_celsius_mean: lstFromInputs(inputs),
      slope_deg_mean: 3,
      elevation_m_mean: 560,
    },
  };

  let response;
  try {
    response = await createAssessment(payload);
  } catch (err) {
    throw new OptimizationError(err instanceof Error ? err.message : 'Backend request failed.');
  }

  const opt = response.optimization;
  if (!opt) throw new OptimizationError('Backend did not return an optimization result.');

  const before = toMetrics(opt.baseline);
  const after = toMetrics(opt.optimized);

  const levers: Levers = { treesPct: 0, roofsPct: 0, pavingPct: 0 };
  const allocation: AllocationLine[] = (opt.recommendations || []).map((r, idx) => ({
    lever: (idx === 0 ? 'treesPct' : idx === 1 ? 'roofsPct' : 'pavingPct') as keyof Levers,
    label: r.title,
    crore: 0,
    sharePct: 0,
    detail: r.description,
  }));

  const trajectory = trajectoryBetween(before, after, inputs.horizonYears);

  const implications = (opt.recommendations || []).map((r) => `${r.title}: ${r.current} → ${r.proposed} (impact ${r.impact}).`);
  if (implications.length === 0) implications.push('Backend optimization completed.');

  return {
    isDemo: true,
    modelVersion: 'prototype-demo-1.0',
    inputs: { ...inputs },
    levers,
    before,
    after,
    allocation,
    trajectory,
    implications,
  };
}
