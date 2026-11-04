import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { scoreProposal, type ScoreResult } from '../services/climateApi';
import type { AssessmentInputs, FieldErrors, RunStatus } from '../types';

interface PlanContextValue {
  inputs: AssessmentInputs;
  setInput: <K extends keyof AssessmentInputs>(key: K, value: AssessmentInputs[K]) => void;
  resetInputs: () => void;
  errors: FieldErrors;
  status: RunStatus;
  errorMessage: string | null;
  result: ScoreResult | null;
  stale: boolean;
  submit: () => Promise<boolean>;
  dismissError: () => void;
}

const Ctx = createContext<PlanContextValue | null>(null);

const DEFAULT_INPUTS: AssessmentInputs = {
  planName: 'Hadapsar greening plan',
  wardNo: 2,
  builtUpAreaSqm: 2000,
  plotAreaSqm: 4000,
  builtUpPct: 58,
  pavedPct: 24,
  canopyPct: 9,
  storeys: null,
  materials: [
    { materialId: 'cement_opc', quantityKg: 180_000 },
    { materialId: 'steel_reinforcement', quantityKg: 95_000 },
    { materialId: 'brick_clay', quantityKg: 210_000 },
    { materialId: 'river_sand', quantityKg: 140_000 },
    { materialId: 'concrete_ready_mix', quantityKg: 600_000 },
  ],
  goal: 'balanced',
  projectType: 'residential',
};

const validate = (inputs: AssessmentInputs): FieldErrors => {
  const errors: FieldErrors = {};
  if (!inputs.planName.trim()) errors.planName = 'Give the plan a name.';
  if (!Number.isFinite(inputs.wardNo) || inputs.wardNo < 1 || inputs.wardNo > 41)
    errors.wardNo = 'Ward must be between 1 and 41.';
  if (!Number.isFinite(inputs.builtUpAreaSqm) || inputs.builtUpAreaSqm <= 0)
    errors.builtUpAreaSqm = 'Built-up area must be greater than 0.';
  if (!Number.isFinite(inputs.plotAreaSqm) || inputs.plotAreaSqm <= 0)
    errors.plotAreaSqm = 'Plot area must be greater than 0.';
  if (
    Number.isFinite(inputs.builtUpAreaSqm) &&
    Number.isFinite(inputs.plotAreaSqm) &&
    inputs.builtUpAreaSqm > inputs.plotAreaSqm
  )
    errors.builtUpAreaSqm = 'Built-up area cannot exceed plot area.';
  if (inputs.materials.some((m) => !m.materialId.trim() || !Number.isFinite(m.quantityKg) || m.quantityKg <= 0))
    errors.materials = 'Every material line needs a name and a positive quantity.';
  if (inputs.builtUpPct != null && (inputs.builtUpPct < 0 || inputs.builtUpPct > 100))
    errors.builtUpPct = 'Built-up must be between 0 and 100.';
  if (inputs.pavedPct != null && (inputs.pavedPct < 0 || inputs.pavedPct > 100))
    errors.pavedPct = 'Paved must be between 0 and 100.';
  if (inputs.canopyPct != null && (inputs.canopyPct < 0 || inputs.canopyPct > 100))
    errors.canopyPct = 'Canopy must be between 0 and 100.';
  return errors;
};

export function PlanProvider({ children }: { children: ReactNode }) {
  const [inputs, setInputsState] = useState<AssessmentInputs>(DEFAULT_INPUTS);
  const [attempted, setAttempted] = useState(false);
  const [status, setStatus] = useState<RunStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ScoreResult | null>(null);
  // The inputs that were sent for the current result.
  const [scoredInputs, setScoredInputs] = useState<AssessmentInputs | null>(null);
  const runId = useRef(0);

  const errors = useMemo(() => (attempted ? validate(inputs) : {}), [attempted, inputs]);

  const setInput = useCallback<PlanContextValue['setInput']>((key, value) => {
    setInputsState((prev) => ({ ...prev, [key]: value }));
  }, []);

  const resetInputs = useCallback(() => {
    setInputsState(DEFAULT_INPUTS);
    setAttempted(false);
    setErrorMessage(null);
    setResult(null);
    setScoredInputs(null);
  }, []);

  const submit = useCallback(async (): Promise<boolean> => {
    setAttempted(true);
    const found = validate(inputs);
    if (Object.keys(found).length > 0) {
      setErrorMessage(null);
      const first = Object.keys(found)[0];
      requestAnimationFrame(() => document.getElementById(`f-${first}`)?.focus({ preventScroll: true }));
      return false;
    }
    const id = ++runId.current;
    setStatus('loading');
    setErrorMessage(null);

    const cleanMaterials = inputs.materials
      .filter((m) => m.materialId.trim() && Number.isFinite(m.quantityKg) && m.quantityKg > 0)
      .map((m) => ({ materialId: m.materialId.trim(), quantityKg: Math.round(m.quantityKg) }));

    const payload = {
      ward: inputs.wardNo,
      builtUpAreaSqm: inputs.builtUpAreaSqm,
      plotAreaSqm: inputs.plotAreaSqm,
      materials: cleanMaterials.map((m) => ({ name: m.materialId, quantityKg: m.quantityKg })),
      storeys: inputs.storeys ?? undefined,
      projectType: inputs.projectType,
      impervious: inputs.builtUpPct ?? undefined,
      vegetation: inputs.canopyPct ?? undefined,
      water: 0,
      slope: undefined,
    };

    try {
      const res = await scoreProposal(payload);
      if (id !== runId.current) return false;
      setResult(res);
      setScoredInputs(inputs);
      setStatus('success');
      return true;
    } catch (err) {
      if (id !== runId.current) return false;
      setStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'The climate backend could not score the proposal. Please try again.');
      return false;
    }
  }, [inputs]);

  const dismissError = useCallback(() => {
    setErrorMessage(null);
    setStatus(result ? 'success' : 'idle');
  }, [result]);

  const stale = useMemo(
    () => (result && scoredInputs ? JSON.stringify(inputs) !== JSON.stringify(scoredInputs) : false),
    [inputs, result, scoredInputs],
  );

  const value = useMemo<PlanContextValue>(
    () => ({ inputs, setInput, resetInputs, errors, status, errorMessage, result, stale, submit, dismissError }),
    [inputs, setInput, resetInputs, errors, status, errorMessage, result, stale, submit, dismissError],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePlan(): PlanContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('usePlan must be used inside PlanProvider');
  return v;
}
