export type Priority = 'high' | 'med' | 'low';

/** Inputs for evaluating an urban plan. All values are user-entered. */
export interface PlanInputs {
  planName: string;
  focusArea: string;
  areaHa: number;
  builtUpPct: number;
  pavedPct: number;
  canopyPct: number;
  budgetCrore: number;
  horizonYears: number;
  goal: PlanGoal;
}

export type PlanGoal = 'balanced' | 'cooling' | 'flood' | 'greening';

export type FieldErrors = Partial<Record<keyof AssessmentInputs, string>>;

/** Lever settings, each expressed as a percentage of what that lever can act on. */
export interface Levers {
  /** % of open (unbuilt, uncanopied) land planted with trees */
  treesPct: number;
  /** % of built-up area given a cool roof */
  roofsPct: number;
  /** % of paved area converted to permeable surface */
  pavingPct: number;
}

export interface SurfaceProfile {
  builtUpPct: number;
  pavedPct: number;
  canopyPct: number;
}

/** Demo-model outputs. Not measurements and not validated predictions. */
export interface Metrics {
  canopyPct: number;
  surfaceTempC: number;
  /** Demo runoff index, 0 to 100 */
  runoffIndex: number;
  /** Demo air index on a 0 to 300 scale. Not an official AQI. */
  airIndex: number;
}

export interface AllocationLine {
  lever: keyof Levers;
  label: string;
  crore: number;
  sharePct: number;
  detail: string;
}

export interface TrajectoryPoint {
  year: number;
  canopyPct: number;
  surfaceTempC: number;
  baselineTempC: number;
}

export interface OptimizationResult {
  isDemo: boolean;
  modelVersion: string;
  inputs: PlanInputs;
  levers: Levers;
  before: Metrics;
  after: Metrics;
  allocation: AllocationLine[];
  trajectory: TrajectoryPoint[];
  implications: string[];
}

export type RunStatus = 'idle' | 'loading' | 'success' | 'error';

/** BOQ line — one construction material line-item. */
export interface MaterialLine {
  /** Key from pune materials table (materials.json) e.g. cement_opc */
  materialId: string;
  quantityKg: number;
}

/** Form inputs for a real ML assessment. */
export interface AssessmentInputs {
  planName: string;
  /** Ward number 1–41 */
  wardNo: number;
  builtUpAreaSqm: number;
  plotAreaSqm: number;
  /** Satellite-measured share of the plot that is built (satellite or user input). */
  builtUpPct: number | null;
  pavedPct: number | null;
  canopyPct: number | null;
  storeys: number | null;
  materials: MaterialLine[];
  goal: AssessmentGoal;
  projectType: string;
}

export type AssessmentGoal = 'balanced' | 'cooling' | 'flood' | 'greening';

export type MaterialErrors = Record<string, string>;

export interface Step {
  id: string;
  label: string;
  done: boolean;
  now: boolean;
}
