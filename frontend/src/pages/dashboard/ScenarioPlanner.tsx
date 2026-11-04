import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, EmptyState, PageHeader, Panel, Pill } from '../../components/ui';
import { SelectField } from '../../components/Field';
import { WARDS } from '../../config';
import { scoreProposal, type ScoreResult } from '../../services/climateApi';
import { usePlan } from '../../state/PlanContext';
import type { MaterialLine } from '../../types';

/**
 * Real what-if rescore. The satellite cube takes precedence over user land-cover
 * values, so the canopy lever only changes the score where the cube has no
 * vegetation measurement — the response's landcover_source reports which happened.
 * Cool roofs and permeable paving are not modelled by the scorer and are shown
 * as NOT_MODELLED rather than given invented deltas.
 */

type SwapCategory = 'cement' | 'steel' | 'brick';

const SWAP_OPTIONS: Record<SwapCategory, { value: string; label: string }[]> = {
  cement: [
    { value: 'cement_opc', label: 'Cement — OPC (0.91 kgCO₂e/kg)' },
    { value: 'cement_ppc', label: 'Cement — PPC (0.507)' },
    { value: 'cement_psc', label: 'Cement — PSC (0.312)' },
    { value: 'cement_ggbs', label: 'Cement — GGBS (0.05)' },
    { value: 'calcined_clay_cement_lc3', label: 'LC3 — calcined clay cement (0.14)' },
  ],
  steel: [
    { value: 'steel_reinforcement', label: 'Steel rebar — BOF (2.6)' },
    { value: 'steel_rebar_eaf', label: 'Steel rebar — EAF (0.83)' },
    { value: 'steel_rebar_recycled', label: 'Steel rebar — recycled (0.45)' },
  ],
  brick: [
    { value: 'brick_clay', label: 'Brick — clay fired (0.39)' },
    { value: 'fly_ash_brick', label: 'Brick — fly ash (0.09)' },
    { value: 'aac_block', label: 'AAC block (0.11)' },
    { value: 'hollow_concrete_block', label: 'Hollow concrete block (0.14)' },
  ],
};

const CATEGORY_MATCH: Record<SwapCategory, (id: string) => boolean> = {
  cement: (id) => id.startsWith('cement_') || id.startsWith('concrete_') || id === 'calcined_clay_cement_lc3',
  steel: (id) => id.startsWith('steel_'),
  brick: (id) => ['brick_clay', 'fly_ash_brick', 'aac_block', 'hollow_concrete_block'].includes(id),
};

const FACTORS: { key: string; label: string; upIsGood: boolean }[] = [
  { key: 'flood', label: 'Flood', upIsGood: false },
  { key: 'heat', label: 'Heat', upIsGood: false },
  { key: 'green', label: 'Green cover', upIsGood: false },
  { key: 'carbon', label: 'Carbon', upIsGood: false },
];

export default function ScenarioPlanner() {
  const { result, inputs } = usePlan();
  const [swaps, setSwaps] = useState<Partial<Record<SwapCategory, string>>>({});
  const [scenarioWard, setScenarioWard] = useState<number | ''>('');
  const [canopyLever, setCanopyLever] = useState(0);
  const [rescoring, setRescoring] = useState(false);
  const [scenario, setScenario] = useState<ScoreResult | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

  const baseWard = result?.ward ?? inputs.wardNo;

  const appliedSwaps = useMemo(() => {
    const out: { line: MaterialLine; to: string }[] = [];
    (Object.keys(swaps) as SwapCategory[]).forEach((cat) => {
      const to = swaps[cat];
      if (!to) return;
      const line = inputs.materials.find((m) => CATEGORY_MATCH[cat](m.materialId));
      if (line && line.materialId !== to) out.push({ line, to });
    });
    return out;
  }, [swaps, inputs.materials]);

  // Canopy lever: plant the given share of open (unbuilt, unpaved, uncanopied) land.
  const openPct = Math.max(0, 100 - (inputs.builtUpPct ?? 0) - (inputs.pavedPct ?? 0) - (inputs.canopyPct ?? 0));
  const scenarioCanopyPct = Math.min(100, (inputs.canopyPct ?? 0) + (canopyLever / 100) * openPct);
  const canopyChanged = Math.abs(scenarioCanopyPct - (inputs.canopyPct ?? 0)) > 0.05;

  const rescore = async () => {
    if (!result) return;
    setRescoring(true);
    setScenarioError(null);
    try {
      const materialById = new Map(inputs.materials.map((m) => [m.materialId, m.quantityKg]));
      const materials = inputs.materials.map((m) => {
        const target = appliedSwaps.find((s) => s.line === m);
        return { name: target ? target.to : m.materialId, quantityKg: m.quantityKg };
      });
      // Ensure swapped-in materials appear even if the BOQ lacked the category.
      appliedSwaps.forEach((s) => {
        if (!materials.some((m) => m.name === s.to)) {
          materials.push({ name: s.to, quantityKg: materialById.get(s.line.materialId) ?? 0 });
        }
      });
      const res = await scoreProposal({
        ward: scenarioWard || baseWard,
        builtUpAreaSqm: inputs.builtUpAreaSqm,
        plotAreaSqm: inputs.plotAreaSqm,
        materials: materials.filter((m) => m.quantityKg > 0),
        storeys: inputs.storeys ?? undefined,
        projectType: inputs.projectType,
        vegetation: canopyChanged ? scenarioCanopyPct : undefined,
        water: 0,
      });
      setScenario(res);
    } catch (err) {
      setScenario(null);
      setScenarioError(err instanceof Error ? err.message : 'Rescore failed. Please try again.');
    } finally {
      setRescoring(false);
    }
  };

  const landcoverSource = (scenario?.indicators as { landcover_source?: string } | undefined)?.landcover_source;
  const landcoverAssumptions = (scenario?.indicators as { landcover_assumptions?: string[] } | undefined)?.landcover_assumptions ?? [];
  const leverApplied = landcoverAssumptions.includes('vegetation_pct');

  const carbonOf = (r: ScoreResult | null) =>
    (r?.score.factors?.carbon as { total_kgco2e?: number } | undefined)?.total_kgco2e ?? null;
  const intensityOf = (r: ScoreResult | null) =>
    (r?.score.factors?.carbon as { intensity_kgco2e_m2?: number } | undefined)?.intensity_kgco2e_m2 ?? null;

  const fmt = (v: number | null | undefined, digits = 1) => (v == null ? 'UNAVAILABLE' : v.toFixed(digits));
  const deltaText = (before: number | null, after: number | null, digits = 1) => {
    if (before == null || after == null) return 'UNAVAILABLE';
    const d = after - before;
    if (Math.abs(d) < 0.05) return 'no change';
    return `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(digits)}`;
  };

  return (
    <>
      <PageHeader
        eyebrow="Scenario planner"
        title="Scenario Planner"
        lede="Modify the scored proposal — swap materials, relocate the ward, add canopy — and the ML pipeline rescores it. Every delta is recomputed by the scorer, not estimated."
      />

      {!result ? (
        <Panel title="No scored proposal">
          <EmptyState
            title="Score a proposal first"
            text="The Scenario Planner rescores your evaluated proposal with modified inputs. Evaluate a plan to begin."
          />
          <div className="row-actions" style={{ marginTop: '12px' }}>
            <Link to="/assess" className="btn btn--primary">Evaluate a plan</Link>
          </div>
        </Panel>
      ) : (
        <>
          <div className="two-col">
            <Panel title="Modify the proposal" note={`Baseline: ward ${result.ward ?? baseWard}, scored ${fmt(result.score.impact_score)} impact, evidence ${result.score.evidence_status}.`}>
              <SelectField
                id="swap-cement"
                label="Binder swap"
                hint="Replaces the cement/concrete binder line in the BOQ."
                value={swaps.cement ?? ''}
                options={[{ value: '', label: 'Keep as proposed' }, ...SWAP_OPTIONS.cement]}
                onChange={(v) => setSwaps((s) => ({ ...s, cement: v || undefined }))}
              />
              <SelectField
                id="swap-steel"
                label="Steel swap"
                hint="Replaces the reinforcement steel line in the BOQ."
                value={swaps.steel ?? ''}
                options={[{ value: '', label: 'Keep as proposed' }, ...SWAP_OPTIONS.steel]}
                onChange={(v) => setSwaps((s) => ({ ...s, steel: v || undefined }))}
              />
              <SelectField
                id="swap-brick"
                label="Walling swap"
                hint="Replaces the brick/block line in the BOQ."
                value={swaps.brick ?? ''}
                options={[{ value: '', label: 'Keep as proposed' }, ...SWAP_OPTIONS.brick]}
                onChange={(v) => setSwaps((s) => ({ ...s, brick: v || undefined }))}
              />
              <SelectField
                id="scenario-ward"
                label="Relocate to ward"
                hint="Rescore the same proposal in another ward."
                value={scenarioWard ? String(scenarioWard) : ''}
                options={[{ value: '', label: `Keep ward ${baseWard}` }, ...WARDS.map((w) => ({ value: w.value, label: w.label }))]}
                onChange={(v) => setScenarioWard(v ? Number(v) : '')}
              />
              <div className="field">
                <label htmlFor="f-canopy-lever">Canopy added: {canopyLever}% of open land</label>
                <input
                  id="f-canopy-lever"
                  type="range"
                  min={0}
                  max={100}
                  value={canopyLever}
                  onChange={(e) => setCanopyLever(Number(e.target.value))}
                />
                <p className="field__hint">
                  Open land on this plot: {openPct.toFixed(1)}%. The satellite cube takes precedence where it has a
                  vegetation measurement — the rescore reports whether this lever was actually used.
                </p>
              </div>

              <div className="toolbar toolbar--tight" style={{ marginTop: '8px' }}>
                <span className="note">Cool roofs: <Pill tone="med">NOT_MODELLED</Pill></span>
                <span className="note">Permeable paving: <Pill tone="med">NOT_MODELLED</Pill></span>
              </div>

              <div className="row-actions" style={{ marginTop: '12px' }}>
                <Button variant="primary" busy={rescoring} onClick={() => void rescore()}>
                  {rescoring ? 'Rescoring…' : 'Rescore scenario'}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSwaps({});
                    setScenarioWard('');
                    setCanopyLever(0);
                    setScenario(null);
                    setScenarioError(null);
                  }}
                  disabled={rescoring}
                >
                  Reset
                </Button>
              </div>
              {scenarioError && <p className="field__error" role="alert">{scenarioError}</p>}
            </Panel>

            <Panel
              title="Rescored outcome"
              note={
                scenario
                  ? `Land cover source: ${landcoverSource ?? 'unknown'}. ${
                      leverApplied
                        ? 'Canopy lever was applied (no cube measurement for this ward).'
                        : 'Cube measurement took precedence — the canopy lever did not change this score.'
                    }`
                  : 'Run a rescore to see recomputed values.'
              }
            >
              {!scenario ? (
                <EmptyState title="No rescore yet" text="Set the swaps above and rescore. Deltas shown here come from the ML scorer itself." />
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Measure</th>
                        <th className="n">As proposed</th>
                        <th className="n">Scenario</th>
                        <th className="n">Delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Impact score <small>/100, higher = worse</small></td>
                        <td className="n">{fmt(result.score.impact_score)}</td>
                        <td className="n">{fmt(scenario.score.impact_score)}</td>
                        <td className="n">{deltaText(result.score.impact_score, scenario.score.impact_score)}</td>
                      </tr>
                      <tr>
                        <td>Climate score <small>/100</small></td>
                        <td className="n">{fmt(result.score.climate_score)}</td>
                        <td className="n">{fmt(scenario.score.climate_score)}</td>
                        <td className="n">{deltaText(result.score.climate_score, scenario.score.climate_score)}</td>
                      </tr>
                      {FACTORS.map((f) => {
                        const b = result.score.factors?.[f.key]?.score ?? null;
                        const a = scenario.score.factors?.[f.key]?.score ?? null;
                        return (
                          <tr key={f.key}>
                            <td>{f.label} factor</td>
                            <td className="n">{fmt(b)}</td>
                            <td className="n">{fmt(a)}</td>
                            <td className="n">{deltaText(b, a)}</td>
                          </tr>
                        );
                      })}
                      <tr>
                        <td>Carbon (A1–A3)</td>
                        <td className="n">{carbonOf(result) != null ? `${(carbonOf(result)! / 1000).toFixed(1)} tCO₂e` : 'UNAVAILABLE'}</td>
                        <td className="n">{carbonOf(scenario) != null ? `${(carbonOf(scenario)! / 1000).toFixed(1)} tCO₂e` : 'UNAVAILABLE'}</td>
                        <td className="n">
                          {carbonOf(result) != null && carbonOf(scenario) != null
                            ? deltaText(carbonOf(result), carbonOf(scenario), 0).replace(/(\d)(?=(\d{3})+$)/g, '$1,') + ' kg'
                            : 'UNAVAILABLE'}
                        </td>
                      </tr>
                      <tr>
                        <td>Carbon intensity</td>
                        <td className="n">{intensityOf(result) != null ? `${fmt(intensityOf(result))} kg/m²` : 'UNAVAILABLE'}</td>
                        <td className="n">{intensityOf(scenario) != null ? `${fmt(intensityOf(scenario))} kg/m²` : 'UNAVAILABLE'}</td>
                        <td className="n">{deltaText(intensityOf(result), intensityOf(scenario))}</td>
                      </tr>
                      <tr>
                        <td>Evidence</td>
                        <td className="n">{result.score.evidence_status}</td>
                        <td className="n">{scenario.score.evidence_status}</td>
                        <td className="n">—</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>

          {scenario && scenario.recommendations.length > 0 && (
            <Panel title="Scorer recommendations for the scenario" note="Deltas are verified by the scorer recomputing the factor on the proposed change.">
              <ul className="plain-list">
                {scenario.recommendations.map((r, i) => (
                  <li key={i}>
                    <b>{r.action || r.title}</b>
                    {r.delta?.impact_delta != null && (
                      <> <span className="delta delta--good">Impact {r.delta.impact_delta > 0 ? '+' : ''}{r.delta.impact_delta.toFixed(1)}</span></>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="Why some levers show no change">
            <p className="note">
              The scorer measures land cover from the satellite cube for {result.ward ? `ward ${result.ward}` : 'this ward'} and
              only falls back to user-supplied values where the cube has no measurement. Where the cube wins, the canopy lever
              cannot move the score — the rescore says so explicitly instead of showing a fabricated delta. Material swaps and
              ward relocation always rescore for real, because they change the actual inputs the scorer consumes.
            </p>
          </Panel>
        </>
      )}
    </>
  );
}
