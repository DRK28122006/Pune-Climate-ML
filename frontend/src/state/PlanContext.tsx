import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { DEFAULT_INPUTS } from '../config';
import { validateInputs } from '../lib/optimizer';
import { OptimizationError, runOptimization } from '../services/optimization';
import type { FieldErrors, OptimizationResult, PlanInputs, RunStatus } from '../types';

interface PlanContextValue {
  inputs: PlanInputs;
  setInput: <K extends keyof PlanInputs>(key: K, value: PlanInputs[K]) => void;
  resetInputs: () => void;
  errors: FieldErrors;
  status: RunStatus;
  errorMessage: string | null;
  result: OptimizationResult | null;
  /** True when inputs have been edited since the displayed result was produced. */
  stale: boolean;
  submit: () => Promise<boolean>;
  dismissError: () => void;
}

const Ctx = createContext<PlanContextValue | null>(null);

export function PlanProvider({ children }: { children: ReactNode }) {
  const [inputs, setInputs] = useState<PlanInputs>(DEFAULT_INPUTS);
  const [attempted, setAttempted] = useState(false);
  const [status, setStatus] = useState<RunStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const runId = useRef(0);

  const errors = useMemo(() => (attempted ? validateInputs(inputs) : {}), [attempted, inputs]);

  const setInput = useCallback<PlanContextValue['setInput']>((key, value) => {
    setInputs((prev) => ({ ...prev, [key]: value }));
  }, []);

  const resetInputs = useCallback(() => {
    setInputs(DEFAULT_INPUTS);
    setAttempted(false);
    setErrorMessage(null);
  }, []);

  const submit = useCallback(async () => {
    setAttempted(true);
    const found = validateInputs(inputs);
    if (Object.keys(found).length > 0) {
      setErrorMessage(null);
      const first = Object.keys(found)[0];
      requestAnimationFrame(() => document.getElementById(`f-${first}`)?.focus());
      return false;
    }
    const id = ++runId.current;
    setStatus('loading');
    setErrorMessage(null);
    try {
      const r = await runOptimization(inputs);
      if (id !== runId.current) return false;
      setResult(r);
      setStatus('success');
      return true;
    } catch (err) {
      if (id !== runId.current) return false;
      setStatus('error');
      setErrorMessage(
        err instanceof OptimizationError
          ? err.message
          : 'The optimization service could not finish. Please try again.',
      );
      return false;
    }
  }, [inputs]);

  const dismissError = useCallback(() => {
    setErrorMessage(null);
    setStatus(result ? 'success' : 'idle');
  }, [result]);

  const stale = useMemo(
    () => (result ? JSON.stringify(result.inputs) !== JSON.stringify(inputs) : false),
    [result, inputs],
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
