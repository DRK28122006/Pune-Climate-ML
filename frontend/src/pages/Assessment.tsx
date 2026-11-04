import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Send, Sparkles } from 'lucide-react';
import Logo from '../components/Logo';
import { NumberField, TextField, SelectField } from '../components/Field';
import { Button, Panel, SectionBand, EmptyState, ErrorState, Pill } from '../components/ui';
import { MATERIALS, WARDS } from '../config';
import { narrateAssessment, type ScoreResult } from '../services/climateApi';
import { usePlan } from '../state/PlanContext';
import type { AssessmentInputs, MaterialLine } from '../types';

export default function Assessment() {
  const { inputs, setInput, resetInputs, errors, status, errorMessage, result, stale, submit, dismissError } = usePlan();
  const loading = status === 'loading';
  const showResults = !!result && !loading;

  // Optional AI input review (Step 2). Skippable — scoring never depends on it.
  const [aiCheck, setAiCheck] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [aiCheckText, setAiCheckText] = useState<string | null>(null);
  const [aiDismissed, setAiDismissed] = useState(false);

  const runAiCheck = async () => {
    setAiCheck('loading');
    setAiDismissed(false);
    try {
      const summary = {
        ward: inputs.wardNo,
        builtUpAreaSqm: inputs.builtUpAreaSqm,
        plotAreaSqm: inputs.plotAreaSqm,
        storeys: inputs.storeys,
        builtUpPct: inputs.builtUpPct,
        pavedPct: inputs.pavedPct,
        canopyPct: inputs.canopyPct,
        materials: inputs.materials.filter((m) => m.materialId && m.quantityKg > 0),
        projectType: inputs.projectType,
      };
      const res = await narrateAssessment(
        { inputs: summary },
        'Review these building-proposal inputs for internal plausibility before scoring. ' +
          'This is an input review, not a scored assessment: ignore any EVIDENCE_STATUS, VERBATIM_VERDICT or ' +
          'factor lines in the template — they do not apply here. Do not state any score or verdict. ' +
          'Flag only real inconsistencies in the inputs (for example: footprint vs plot area, storeys vs footprint, ' +
          'material quantities wildly out of scale with the built-up area, land-cover shares not summing near 100). ' +
          'Reply with a short list; if nothing is wrong, say the inputs look consistent. Do not invent numbers.\n' +
          JSON.stringify(summary),
      );
      setAiCheckText(res.text);
      setAiCheck('done');
    } catch {
      setAiCheckText('The AI review is unavailable right now. You can skip it and score anyway — scoring does not depend on it.');
      setAiCheck('error');
    }
  };


  // Add/remove material lines.
  const addMaterial = () => {
    if (inputs.materials.length < 30)
      setInput('materials', [...inputs.materials, { materialId: '', quantityKg: 0 }]);
  };
  const setMaterialLine = (idx: number, patch: Partial<MaterialLine>) => {
    const next = inputs.materials.map((m, i) => (i === idx ? { ...m, ...patch } : m));
    setInput('materials', next);
  };
  const removeMaterial = (idx: number) => {
    setInput('materials', inputs.materials.filter((_, i) => i !== idx));
  };

  const scrollTo = (el: HTMLElement | null) => el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const resultsRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (showResults) {
      window.setTimeout(() => scrollTo(resultsRef.current), 150);
    }
  }, [showResults]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await submit();
    if (!ok && formRef.current) scrollTo(formRef.current);
  };

  return (
    <div className="assess">
      <header className="assess__bar">
        <Logo />
        <Link to="/dashboard/overview" className="assess__link">Dashboard</Link>
      </header>

      <main id="main">
        <section className="assess__form" aria-labelledby="assess-title">
          <div className="assess__wrap" ref={formRef}>
            <p className="eyebrow halo">Step 1 of 2 · Evaluate</p>
            <h1 id="assess-title" className="halo">Evaluate a building proposal</h1>
            <p className="lede lede--card">
              Enter the building's real inputs — footprint, plot, materials — and the ML pipeline
              computes flood, heat, green and carbon from satellite data and the 2019 tree census.
            </p>

            <form onSubmit={onSubmit} noValidate className="assess__panels" aria-describedby="run-status">
              <Panel title="1. The proposal">
                <div className="grid2">
                  <TextField id="planName" label="Plan name" value={inputs.planName} maxLength={70} error={errors.planName} onChange={(v) => setInput('planName', v)} />
                  <SelectField
                    id="wardNo"
                    label="Ward"
                    hint="Pune Municipal Corporation ward (1–41)"
                    value={String(inputs.wardNo)}
                    error={errors.wardNo}
                    options={WARDS.map((w) => ({ value: w.value, label: w.label }))}
                    onChange={(v) => setInput('wardNo', Number(v))}
                  />
                  <NumberField id="builtUpAreaSqm" label="Built-up area" unit="m²" min={1} step={1} hint="Floor space — the actual area the building occupies." value={inputs.builtUpAreaSqm} error={errors.builtUpAreaSqm} onChange={(v) => setInput('builtUpAreaSqm', v)} />
                  <NumberField id="plotAreaSqm" label="Plot area" unit="m²" min={1} step={1} hint="Total plot including open space and garden." value={inputs.plotAreaSqm} error={errors.plotAreaSqm} onChange={(v) => setInput('plotAreaSqm', v)} />
                  <NumberField id="storeys" label="Storeys" unit="" min={1} step={1} hint="Optional. Planning-design floor count." value={inputs.storeys ?? 0} error={errors.storeys} onChange={(v) => setInput('storeys', v > 0 ? v : null)} />
                </div>
              </Panel>

              <Panel title="2. Current land cover">
                <div className="grid3">
                  <NumberField id="builtUpPct" label="Built-up" unit="%" min={0} max={100} hint="Share of plot covered by buildings. Defaults from satellite." value={inputs.builtUpPct ?? 0} error={errors.builtUpPct} onChange={(v) => setInput('builtUpPct', v)} />
                  <NumberField id="pavedPct" label="Paved" unit="%" min={0} max={100} hint="Roads, yards and other sealed surface." value={inputs.pavedPct ?? 0} error={errors.pavedPct} onChange={(v) => setInput('pavedPct', v)} />
                  <NumberField id="canopyPct" label="Tree canopy" unit="%" min={0} max={100} hint="Share of plot shaded by tree crowns." value={inputs.canopyPct ?? 0} error={errors.canopyPct} onChange={(v) => setInput('canopyPct', v)} />
                </div>
                <p className="note">Values from the satellite cube (2024 flight) or enter your own — leave as 0 and the pipeline uses its cube measurement.</p>
              </Panel>

              <Panel title="3. Materials (BOQ)">
                <p className="note" style={{ marginBottom: '12px' }}>
                  List the materials and quantities for this building. Cement, steel and brick are the biggest drivers.
                  Carbon is UNAVAILABLE without a BOQ.
                </p>
                {inputs.materials.map((m, i) => (
                  <div key={i} className="grid3" style={{ marginBottom: '6px' }}>
                    <SelectField
                      id={`material-${i}`}
                      label="Material"
                      value={m.materialId}
                      options={[{ value: '', label: 'Pick a material…' }, ...MATERIALS.map((x) => ({ value: x.value, label: x.label }))]}
                      onChange={(v) => setMaterialLine(i, { materialId: v })}
                    />
                    <NumberField
                      id={`qty-${i}`}
                      label="Quantity"
                      unit="kg"
                      min={0}
                      step={1}
                      value={m.quantityKg}
                      onChange={(v) => setMaterialLine(i, { quantityKg: v })}
                    />
                    <Button type="button" variant="ghost" onClick={() => removeMaterial(i)} style={{ marginBottom: '6px' }}>
                      Remove
                    </Button>
                  </div>
                ))}
                <Button type="button" variant="ghost" onClick={addMaterial} style={{ fontSize: '13px', color: '#1f5a8c' }}>
                  + Add material line
                </Button>
                <p className="note" style={{ marginTop: '12px' }}>
                  {inputs.materials.filter((m) => m.materialId && m.quantityKg > 0).length} valid material lines.
                  Carbon will be <b>UNAVAILABLE</b> if this is 0 or quantities are 0.
                </p>
              </Panel>

              <Panel title="4. Optional AI input check">
                <p className="note" style={{ marginBottom: '12px' }}>
                  Gemini reviews the form for internal inconsistencies before scoring. This step is optional — skip it
                  and score directly. The ML score never depends on this review.
                </p>
                {aiCheck === 'idle' && !aiDismissed && (
                  <div className="row-actions">
                    <Button type="button" variant="secondary" onClick={() => void runAiCheck()}>
                      Check inputs with AI
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => setAiDismissed(true)}>
                      Skip
                    </Button>
                  </div>
                )}
                {aiCheck === 'loading' && <p className="status">Reviewing inputs…</p>}
                {(aiCheck === 'done' || aiCheck === 'error') && aiCheckText && (
                  <div className="ai-check-result">
                    <p className="note" style={{ whiteSpace: 'pre-wrap' }}>{aiCheckText}</p>
                    <div className="row-actions">
                      <Button type="button" variant="ghost" onClick={() => { setAiCheck('idle'); setAiCheckText(null); }}>
                        Run again
                      </Button>
                    </div>
                  </div>
                )}
                {aiDismissed && aiCheck === 'idle' && (
                  <p className="note">Input check skipped. <Button type="button" variant="ghost" onClick={() => setAiDismissed(false)}>Show it</Button></p>
                )}
              </Panel>

              <div className="assess__actions">
                <Button ref={null} type="submit" variant="primary" size="lg" busy={loading} id="score">
                  <Sparkles size={20} aria-hidden="true" />
                  {loading ? 'Scoring…' : 'Score proposal'}
                </Button>
                <Button type="button" variant="ghost" onClick={resetInputs} disabled={loading}>
                  Reset
                </Button>
              </div>

              <div id="run-status" aria-live="polite" className="assess__status">
                {Object.keys(errors).length > 0 && (
                  <p className="status status--warn">Fix the fields above, then score again.</p>
                )}
                {loading && <p className="status">Running the ML pipeline…</p>}
                {status === 'success' && !stale && <p className="status status--ok">Scored. Results are below.</p>}
                {status === 'success' && stale && <p className="status status--warn">Inputs changed — score again to refresh.</p>}
              </div>

              {status === 'error' && errorMessage && (
                <ErrorState message={errorMessage} onRetry={() => { dismissError(); void submit(); }} />
              )}
            </form>
          </div>

          {showResults && result && (
            <div ref={resultsRef} className="results" aria-labelledby="results-title">
              <Results result={result} inputs={inputs} onEdit={() => scrollTo(formRef.current)} />
            </div>
          )}
          {!showResults && !loading && (
            <div className="assess__locked">
              <EmptyState
                title="No scored proposal yet"
                text="Fill in the proposal and materials above to unlock the ML score."
              />
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Results sub-component
// ─────────────────────────────────────────────────────────────────

function Results({
  result,
  inputs,
  onEdit,
}: {
  result: ScoreResult;
  inputs: AssessmentInputs;
  onEdit: () => void;
}) {
  const score = result?.score || {};
  const factors = score.factors || {};
  const evidence = score.evidence_status || 'UNAVAILABLE';
  const recs = result.recommendations || [];
  const canopy = result.canopy || {};

  // Officer decision chat (Step 4): Gemini answers from the scored assessment only.
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<{ role: 'user' | 'assistant'; text: string }[]>([
    {
      role: 'assistant',
      text: 'This score is computed, not asserted. Ask me anything about it — "is this approvable?", "why is carbon what it is?", "what would moving the footprint do?". I quote only the values in this assessment.',
    },
  ]);
  const [chatBusy, setChatBusy] = useState(false);

  const askChat = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = chatInput.trim();
    if (!q || chatBusy) return;
    setChatMessages((prev) => [...prev, { role: 'user', text: q }]);
    setChatInput('');
    setChatBusy(true);
    try {
      const res = await narrateAssessment(result, q);
      setChatMessages((prev) => [...prev, { role: 'assistant', text: res.text }]);
    } catch {
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', text: 'The narrator is unavailable right now. The computed values above are still valid — try again shortly.' },
      ]);
    } finally {
      setChatBusy(false);
    }
  };

  const factorOrder = ['flood', 'heat', 'green', 'carbon'];
  const factorLabels: Record<string, string> = { flood: 'Flood', heat: 'Heat', green: 'Green cover', carbon: 'Carbon' };
  const factorTone = (f: string, v: number | null): 'high' | 'med' | 'low' => {
    if (v == null) return 'med';
    if (f === 'flood') return v >= 50 ? 'high' : v >= 30 ? 'med' : 'low';
    if (f === 'heat') return v >= 80 ? 'high' : v >= 50 ? 'med' : 'low';
    if (f === 'green') return v >= 80 ? 'high' : v >= 60 ? 'med' : 'low';
    return v >= 80 ? 'high' : v >= 50 ? 'med' : 'low';
  };

  return (
    <div className="assess__wrap results__wrap">
      <p className="eyebrow">Step 2 of 2 · ML Score</p>
      <div className="page-head__row">
        <h2 id="results-title">“{inputs.planName}”</h2>
        <Pill tone={evidence === 'COMPLETE' ? 'low' : 'med'}>
          {evidence}
        </Pill>
      </div>
      <p className="lede lede--card">
        Computed by the ML pipeline from the satellite cube, the 2019 tree census and measured IMD rainfall — not from sliders.
        Ward {inputs.wardNo}.
      </p>

      <div className="metrics">
        <div className="metric">
          <span className="metric__label">Impact score</span>
          <div className="metric__value">{score.impact_score ?? '—'}<small>/100 (higher = worse)</small></div>
        </div>
        <div className="metric">
          <span className="metric__label">Climate score</span>
          <div className="metric__value">{score.climate_score ?? '—'}<small>/100</small></div>
        </div>
        <div className="metric">
          <span className="metric__label">Risk band</span>
          <div className="metric__value">{score.risk_band || '—'}</div>
        </div>
        <div className="metric">
          <span className="metric__label">Evidence</span>
          <div className="metric__value">{evidence}<small>{score.decision_grade ? 'Decision-grade' : 'Diagnostic only'}</small></div>
        </div>
      </div>

      <Panel title="Four factors">
        <div className="grid4">
          {factorOrder.map((k) => {
            const f = (factors as any)[k];
            const v = f ? (f.score as number | null) : null;
            const tone = factorTone(k, v);
            const reason = f?.reason || f?.status || (v == null ? 'Unavailable' : 'OK');
            return (
              <div key={k} className="metric" style={{ textAlign: 'center' }}>
                <span className="metric__label">{factorLabels[k] || k}</span>
                <div className="metric__value">{v ?? '—'}</div>
                <Pill tone={tone}>{tone}</Pill>
                <p className="metric__note" style={{ fontSize: '11px', color: '#4a5a55' }}>{reason}</p>
              </div>
            );
          })}
        </div>
      </Panel>

      {recs.length > 0 && (
        <>
          <SectionBand>Recommendations (verified)</SectionBand>
          <Panel title={`${recs.length} recommendation${recs.length === 1 ? '' : 's'} for this building`} note="Each delta is verified by recomputing the factor on the proposed change.">
            <ul className="plain-list">
              {recs.map((r: any, i: number) => (
                <li key={i}>
                  <b>{r.action || r.title || `Recommendation ${i + 1}`}</b>
                  {r.delta?.impact_delta != null && (
                    <> <span className="delta delta--good">Impact {r.delta.impact_delta > 0 ? '+' : ''}{r.delta.impact_delta.toFixed(1)}</span></>
                  )}
                  {r.delta?.climate_after != null && (
                    <> <span className="note">climate score {r.delta.climate_before?.toFixed(1)} → {r.delta.climate_after?.toFixed(1)}</span></>
                  )}
                </li>
              ))}
            </ul>
          </Panel>
        </>
      )}

      {canopy && Object.keys(canopy).length > 0 && (
        <>
          <SectionBand>Tree canopy ledger</SectionBand>
          <Panel title="Ward tree census ledger" note="Trees come from the 2019 census for the ward. Without a drawn site geometry the scorer treats every census tree as obstructed — its conservative default.">
            <dl className="mlist">
              <div><dt>Census trees in ward</dt><dd>{canopy.total_trees?.toLocaleString('en-IN') ?? '—'}</dd></div>
              <div><dt>Canopy cover (existing)</dt><dd>{canopy.canopy_cover_pct?.toFixed?.(1) ?? '—'}%</dd></div>
              <div><dt>Canopy cover (proposed)</dt><dd>{canopy.canopy_cover_pct_proposed?.toFixed?.(1) ?? '—'}%</dd></div>
              <div><dt>Fell with compensation</dt><dd>{canopy.action_counts?.FELL_AND_COMPENSATE ?? '—'}</dd></div>
              <div><dt>Must preserve (no felling)</dt><dd>{canopy.action_counts?.MUST_PRESERVE ?? canopy.always_preserve_count ?? '—'}</dd></div>
              <div><dt>Relocate</dt><dd>{canopy.action_counts?.RELOCATE ?? '—'}</dd></div>
              {canopy.compensatory_required && <div><dt>Compensatory saplings required</dt><dd>{canopy.compensatory_required.low?.toLocaleString('en-IN')}–{canopy.compensatory_required.high?.toLocaleString('en-IN')}</dd></div>}
            </dl>
          </Panel>
        </>
      )}

      <SectionBand>Officer decision support</SectionBand>
      <Panel
        title="Ask about this score"
        note="Gemini answers from this assessment only — it quotes computed values and never invents numbers. The verdict wording is the scorer's, not the model's."
      >
        <div style={{ maxHeight: '260px', overflowY: 'auto', padding: '8px', marginBottom: '8px' }}>
          {chatMessages.map((m, i) => (
            <div key={i} style={{ textAlign: m.role === 'user' ? 'right' : 'left', marginBottom: '8px' }}>
              <span
                style={{
                  display: 'inline-block', padding: '6px 12px', borderRadius: '10px',
                  background: m.role === 'user' ? '#2e7d4f' : '#fffcf6',
                  color: m.role === 'user' ? '#fff' : '#1b2a26',
                  border: m.role === 'assistant' ? '1px solid rgba(40,34,26,0.18)' : 'none',
                  maxWidth: '80%', fontSize: '13px', lineHeight: 1.5, whiteSpace: 'pre-wrap',
                }}
              >
                {m.text}
              </span>
            </div>
          ))}
        </div>
        <form onSubmit={askChat} style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            placeholder="e.g. Is this approvable? Why is carbon 205 kg/m²?"
            style={{ flex: 1, padding: '8px 12px', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', fontSize: '13px', background: '#fffcf6', color: '#1b2a26' }}
          />
          <button type="submit" className="btn btn--primary btn--md" disabled={chatBusy} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Send size={16} /> {chatBusy ? 'Thinking…' : 'Send'}
          </button>
        </form>
      </Panel>

      <div className="next">
        <Link to="/dashboard/scenario-planner" className="btn btn--primary btn--lg">
          Rescore in the Scenario Planner <ArrowRight size={18} aria-hidden="true" />
        </Link>
        <Link to="/dashboard/overview" className="btn btn--secondary btn--lg">Open the dashboard</Link>
        <Button variant="ghost" onClick={onEdit}>Edit inputs</Button>
      </div>
    </div>
  );
}
