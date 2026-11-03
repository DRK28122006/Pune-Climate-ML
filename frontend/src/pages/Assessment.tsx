import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDown, ArrowRight, RotateCcw, Sparkles } from 'lucide-react';
import Logo from '../components/Logo';
import { NumberField, SelectField, TextField } from '../components/Field';
import { Button, DemoBadge, EmptyState, ErrorState, Panel, SectionBand, Segmented } from '../components/ui';
import LineChart from '../components/charts/LineChart';
import { BarRow, StreetScene } from '../components/charts/Visuals';
import { FOCUS_AREAS, GOAL_LABELS } from '../config';
import { clamp } from '../lib/math';
import { useReducedMotion } from '../lib/useAsync';
import { atmosphere } from '../scene/atmosphereStore';
import { usePlan } from '../state/PlanContext';
import type { Metrics, OptimizationResult, PlanGoal } from '../types';

const STEPS = ['Checking the inputs', 'Evaluating the baseline', 'Allocating the budget across interventions', 'Projecting the outcome'];

export default function Assessment() {
  const { inputs, setInput, resetInputs, errors, status, errorMessage, result, stale, submit, dismissError } = usePlan();
  const reduce = useReducedMotion();
  const formRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);
  const [step, setStep] = useState(0);

  const loading = status === 'loading';
  const showResults = !!result && !loading;
  const errorCount = Object.keys(errors).length;

  // Cycle the loading messages.
  useEffect(() => {
    if (!loading) return;
    setStep(0);
    const t = window.setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 550);
    return () => window.clearInterval(t);
  }, [loading]);

  // Background: always polluted until results exist. After that, scrolling through
  // the results section moves the scene toward green.
  useEffect(() => {
    atmosphere.setWide(false);
    if (!showResults) {
      atmosphere.setTarget(0);
      return;
    }
    const onScroll = () => {
      const el = resultsRef.current;
      if (!el) return;
      const start = el.offsetTop - window.innerHeight * 0.6;
      const end = Math.max(start + 1, document.documentElement.scrollHeight - window.innerHeight);
      atmosphere.setTarget(clamp((window.scrollY - start) / (end - start), 0, 1));
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      atmosphere.setTarget(0);
    };
  }, [showResults]);

  const scrollTo = (el: HTMLElement | null) => el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await submit();
    if (ok) window.setTimeout(() => scrollTo(resultsRef.current), 120);
  };

  const onCue = () => {
    if (showResults) scrollTo(resultsRef.current);
    else {
      scrollTo(formRef.current);
      submitRef.current?.focus({ preventScroll: true });
    }
  };

  return (
    <div className="assess">
      <header className="assess__bar">
        <Logo />
        <Link to="/dashboard/overview" className="assess__link">Dashboard</Link>
      </header>

      <main id="main">
        {/* ---------------- Inputs ---------------- */}
        <section className="assess__form" aria-labelledby="assess-title">
          <div className="assess__wrap" ref={formRef}>
            <p className="eyebrow halo">Step 1 of 2 · Evaluate</p>
            <h1 id="assess-title" className="halo">Evaluate an urban plan</h1>
            <p className="lede lede--card">
              Describe the area and the budget. The optimizer sends the plan to the climate backend, which evaluates the
              baseline and an optimized scenario. Results are illustrative and are not validated predictions.
            </p>

            <form onSubmit={onSubmit} noValidate className="assess__panels" aria-describedby="run-status">
              <Panel title="1. The plan">
                <div className="grid2">
                  <TextField id="planName" label="Plan name" value={inputs.planName} maxLength={70} error={errors.planName} onChange={(v) => setInput('planName', v)} />
                  <SelectField
                    id="focusArea"
                    label="Focus area"
                    hint="Ward names are placeholders taken from the prototype."
                    value={inputs.focusArea}
                    error={errors.focusArea}
                    options={FOCUS_AREAS.map((a) => ({ value: a, label: a }))}
                    onChange={(v) => setInput('focusArea', v)}
                  />
                  <NumberField id="areaHa" label="Plan area" unit="ha" min={5} max={5000} hint="5 to 5,000 hectares." value={inputs.areaHa} error={errors.areaHa} onChange={(v) => setInput('areaHa', v)} />
                </div>
              </Panel>

              <Panel title="2. Current land cover">
                <div className="grid3">
                  <NumberField id="builtUpPct" label="Built-up" unit="%" min={0} max={100} hint="Share of area covered by buildings." value={inputs.builtUpPct} error={errors.builtUpPct} onChange={(v) => setInput('builtUpPct', v)} />
                  <NumberField id="pavedPct" label="Paved" unit="%" min={0} max={100} hint="Roads, yards and other sealed surface." value={inputs.pavedPct} error={errors.pavedPct} onChange={(v) => setInput('pavedPct', v)} />
                  <NumberField id="canopyPct" label="Tree canopy" unit="%" min={0} max={100} hint="Share shaded by tree crowns." value={inputs.canopyPct} error={errors.canopyPct} onChange={(v) => setInput('canopyPct', v)} />
                </div>
                <p className="note">Built-up, paved and canopy shares together cannot exceed 100%. What remains is treated as open land.</p>
              </Panel>

              <Panel title="3. Budget and goal">
                <div className="grid3">
                  <NumberField id="budgetCrore" label="Budget" unit="₹ crore" min={1} max={2000} hint="Demo units, not a cost estimate." value={inputs.budgetCrore} error={errors.budgetCrore} onChange={(v) => setInput('budgetCrore', v)} />
                  <NumberField id="horizonYears" label="Planning horizon" unit="years" min={10} max={50} hint="10 to 50 years." value={inputs.horizonYears} error={errors.horizonYears} onChange={(v) => setInput('horizonYears', v)} />
                  <SelectField
                    id="goal"
                    label="Priority"
                    hint="Which outcome the optimizer favours."
                    value={inputs.goal}
                    options={(Object.keys(GOAL_LABELS) as PlanGoal[]).map((g) => ({ value: g, label: GOAL_LABELS[g] }))}
                    onChange={(v) => setInput('goal', v as PlanGoal)}
                  />
                </div>
              </Panel>

              <div className="assess__actions">
                <Button ref={submitRef} type="submit" variant="primary" size="lg" busy={loading} id="optimize">
                  <Sparkles size={20} aria-hidden="true" />
                  {loading ? 'Optimizing…' : 'Optimize Plan'}
                </Button>
                <Button type="button" variant="ghost" onClick={resetInputs} disabled={loading}>
                  <RotateCcw size={16} aria-hidden="true" />
                  Reset example values
                </Button>
              </div>

              <div id="run-status" aria-live="polite" className="assess__status">
                {errorCount > 0 && <p className="status status--warn">Fix {errorCount} {errorCount === 1 ? 'field' : 'fields'} above, then optimize again.</p>}
                {loading && <p className="status">{STEPS[step]}…</p>}
                {status === 'success' && !loading && !stale && <p className="status status--ok">Optimization complete. Results are below.</p>}
              </div>

              {status === 'error' && errorMessage && (
                <ErrorState message={errorMessage} onRetry={() => { dismissError(); void submit(); }} />
              )}
            </form>

            <button type="button" className="cue" onClick={onCue}>
              <span>{showResults ? 'See the optimized outcome' : 'Results appear below once optimization completes'}</span>
              <ArrowDown size={22} aria-hidden="true" className="cue__arrow" />
            </button>
          </div>

          {loading && (
            <div className="busy" role="status" aria-label="Optimization in progress">
              <div className="busy__card">
                <div className="busy__bar"><i /></div>
                <strong>Running the climate optimizer</strong>
                <ol>
                  {STEPS.map((s, i) => (
                    <li key={s} className={i < step ? 'done' : i === step ? 'now' : ''}>{s}</li>
                  ))}
                </ol>
              </div>
            </div>
          )}
        </section>

        {/* ---------------- Results ---------------- */}
        {showResults && result && (
          <div ref={resultsRef} className="results" aria-labelledby="results-title">
            <Results result={result} stale={stale} onEdit={() => scrollTo(formRef.current)} />
          </div>
        )}
        {!showResults && !loading && (
          <div className="assess__locked">
            <EmptyState
              title="No optimized outcome yet"
              text="Scrolling does not run anything. Enter your inputs and choose Optimize Plan to unlock the results."
            />
          </div>
        )}
      </main>
    </div>
  );
}

/* ====================================================================== */

const METRIC_ROWS: { key: keyof Metrics; label: string; unit: string; digits: number; upIsGood: boolean }[] = [
  { key: 'canopyPct', label: 'Tree canopy', unit: '%', digits: 1, upIsGood: true },
  { key: 'surfaceTempC', label: 'Surface temperature (demo)', unit: '°C', digits: 1, upIsGood: false },
  { key: 'runoffIndex', label: 'Runoff index (demo)', unit: '', digits: 1, upIsGood: false },
  { key: 'airIndex', label: 'Air index (demo, 0–300)', unit: '', digits: 0, upIsGood: false },
];

function Results({ result, stale, onEdit }: { result: OptimizationResult; stale: boolean; onEdit: () => void }) {
  const [view, setView] = useState<'canopy' | 'temp'>('canopy');
  const { before, after, allocation, trajectory, inputs } = result;
  const years = trajectory.map((t) => `Y${t.year}`);

  return (
    <div className="assess__wrap results__wrap">
      <p className="eyebrow">Step 2 of 2 · Outcome</p>
      <div className="page-head__row">
        <h2 id="results-title">Optimized outcome for “{inputs.planName}”</h2>
        <DemoBadge label="Backend result" />
      </div>
      <p className="lede lede--card">
        Generated by the climate backend (model {result.modelVersion}). These numbers compare options; they are
        illustrative and are not measurements, forecasts or validated predictions.
      </p>

      {stale && (
        <div className="status status--warn banner" role="status">
          You changed the inputs after this run. Optimize again to refresh the results.
          <Button variant="ghost" onClick={onEdit}>Go to inputs</Button>
        </div>
      )}

      <div className="split">
        <article className="split__side">
          <h3>Original plan</h3>
          <StreetScene greenness={0} label="Illustration of the original plan: dusty air, bare streets, dark roofs" />
          <dl className="mlist">
            {METRIC_ROWS.map((m) => (
              <div key={m.key}><dt>{m.label}</dt><dd>{before[m.key].toFixed(m.digits)}{m.unit}</dd></div>
            ))}
          </dl>
        </article>

        <div className="split__mid" aria-hidden="false">
          <span className="split__line" />
          <p>Building Earth in a better direction</p>
          <span className="split__line" />
        </div>

        <article className="split__side split__side--after">
          <h3>Optimized outcome</h3>
          <StreetScene greenness={1} label="Illustration of the optimized outcome: clear air, street trees, white roofs" />
          <dl className="mlist">
            {METRIC_ROWS.map((m) => {
              const d = after[m.key] - before[m.key];
              const good = m.upIsGood ? d >= 0 : d <= 0;
              return (
                <div key={m.key}>
                  <dt>{m.label}</dt>
                  <dd>
                    {after[m.key].toFixed(m.digits)}{m.unit}
                    <span className={`delta ${good ? 'delta--good' : 'delta--bad'}`}>
                      {d > 0 ? '+' : '−'}{Math.abs(d).toFixed(m.digits)}{m.unit}
                    </span>
                  </dd>
                </div>
              );
            })}
          </dl>
        </article>
      </div>
      <p className="note">Illustrations are schematic and do not depict the real site.</p>

      <SectionBand>How the budget is used</SectionBand>
      <Panel title={`Allocation of ₹${inputs.budgetCrore} crore (demo units)`}>
        <div className="bars">
          {allocation.map((a) => (
            <BarRow key={a.lever} label={a.label} value={a.sharePct} max={100} display={`${a.sharePct.toFixed(0)}%`} right={`₹${a.crore.toFixed(1)} cr`} />
          ))}
        </div>
        <ul className="plain-list">
          {allocation.map((a) => <li key={a.lever}>{a.detail}</li>)}
        </ul>
      </Panel>

      <SectionBand>The path over {inputs.horizonYears} years</SectionBand>
      <Panel
        title="Projected trajectory"
        actions={
          <Segmented<'canopy' | 'temp'>
            label="Trajectory measure"
            value={view}
            onChange={setView}
            options={[{ value: 'canopy', label: 'Canopy' }, { value: 'temp', label: 'Surface temperature' }]}
          />
        }
        note="Demo projection. Trees mature slowly, so canopy benefits arrive late; roofs and paving act sooner."
      >
        {view === 'canopy' ? (
          <LineChart
            values={trajectory.map((t) => t.canopyPct)}
            xLabels={years}
            yMin={0}
            yMax={Math.max(40, Math.ceil(after.canopyPct / 10) * 10 + 10)}
            yTicks={[0, 10, 20, 30, 40].filter((t) => t <= Math.max(40, Math.ceil(after.canopyPct / 10) * 10 + 10))}
            unit="%"
            decimals={1}
            yLabel="Tree canopy (%)"
            xLabel="Years from now"
            ariaLabel={`Projected tree canopy rising from ${before.canopyPct.toFixed(1)}% to ${after.canopyPct.toFixed(1)}% over ${inputs.horizonYears} years (demo)`}
          />
        ) : (
          (() => {
            const lo = Math.floor(Math.min(...trajectory.map((t) => t.surfaceTempC)) - 1);
            const hi = Math.ceil(before.surfaceTempC + 1);
            const ticks: number[] = [];
            for (let t = lo; t <= hi; t++) ticks.push(t);
            return (
              <LineChart
                values={trajectory.map((t) => t.surfaceTempC)}
                compare={{ values: trajectory.map((t) => t.baselineTempC), label: 'original' }}
                xLabels={years}
                yMin={lo}
                yMax={hi}
                yTicks={ticks}
                unit="°C"
                decimals={1}
                yLabel="Surface temperature (°C, demo)"
                xLabel="Years from now"
                ariaLabel={`Modelled surface temperature falling from ${before.surfaceTempC.toFixed(1)}°C to ${after.surfaceTempC.toFixed(1)}°C over ${inputs.horizonYears} years (demo)`}
              />
            );
          })()
        )}
      </Panel>

      <SectionBand>What it means</SectionBand>
      <Panel title="Implications in the demo model">
        <ul className="plain-list plain-list--roomy">
          {result.implications.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </Panel>

      <div className="next">
        <Link to="/dashboard/scenario-planner" className="btn btn--primary btn--lg">
          Explore in the Scenario Planner <ArrowRight size={18} aria-hidden="true" />
        </Link>
        <Link to="/dashboard/overview" className="btn btn--secondary btn--lg">Open the dashboard</Link>
        <Button variant="ghost" onClick={onEdit}>Edit inputs</Button>
      </div>
      <p className="final">Greener. Cooler. Planned.</p>
    </div>
  );
}
