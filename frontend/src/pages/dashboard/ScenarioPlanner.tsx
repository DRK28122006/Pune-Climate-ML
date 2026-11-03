import { useMemo, useState } from 'react';
import DataGate from '../../components/DataGate';
import { RangeField } from '../../components/Field';
import { StreetScene } from '../../components/charts/Visuals';
import { Button, DemoBadge, PageHeader, Panel, Segmented } from '../../components/ui';
import { getCityBaseline } from '../../data/api';
import { LEVER_LIMITS, projectScenario } from '../../lib/optimizer';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';
import type { Levers, Metrics } from '../../types';

type Slot = 'A' | 'B' | 'C';
const SLOTS: Slot[] = ['A', 'B', 'C'];
const START: Record<Slot, Levers> = {
  A: { treesPct: 10, roofsPct: 20, pavingPct: 0 },
  B: { treesPct: 30, roofsPct: 10, pavingPct: 10 },
  C: { treesPct: 0, roofsPct: 50, pavingPct: 30 },
};

const ROWS: { key: keyof Metrics; label: string; unit: string; digits: number; upIsGood: boolean }[] = [
  { key: 'canopyPct', label: 'Tree canopy', unit: '%', digits: 1, upIsGood: true },
  { key: 'surfaceTempC', label: 'Surface temperature', unit: '°C', digits: 1, upIsGood: false },
  { key: 'runoffIndex', label: 'Runoff index', unit: '', digits: 1, upIsGood: false },
  { key: 'airIndex', label: 'Air index', unit: '', digits: 0, upIsGood: false },
];

export default function ScenarioPlanner() {
  const state = useAsync(getCityBaseline);
  const { result } = usePlan();
  const [slot, setSlot] = useState<Slot>('A');
  const [levers, setLevers] = useState<Record<Slot, Levers>>(START);

  const set = (k: keyof Levers) => (v: number) => setLevers((s) => ({ ...s, [slot]: { ...s[slot], [k]: v } }));
  const loadPlan = () => {
    if (!result) return;
    const l = result.levers;
    setLevers((s) => ({ ...s, [slot]: { treesPct: Math.round(l.treesPct), roofsPct: Math.round(l.roofsPct), pavingPct: Math.round(l.pavingPct) } }));
  };

  const projected = useMemo(() => {
    if (!state.data) return null;
    const { profile, anchor } = state.data;
    return Object.fromEntries(SLOTS.map((s) => [s, projectScenario(profile, levers[s], anchor)])) as Record<Slot, Metrics>;
  }, [state.data, levers]);

  return (
    <>
      <PageHeader
        eyebrow="Scenario planner"
        title="Scenario Planner"
        lede="Set a tree-planting, cool-roof and permeable-paving mix, then compare up to three scenarios against today's sample city figures."
        badge={<DemoBadge label="Simulated outputs" />}
      />
      <DataGate state={state}>
        {({ anchor }) => {
          const cur = projected![slot];
          const l = levers[slot];
          return (
            <>
              <div className="two-col two-col--sim">
                <Panel
                  title={`Scenario ${slot}`}
                  actions={<Segmented<Slot> label="Scenario slot" value={slot} onChange={setSlot} options={SLOTS.map((s) => ({ value: s, label: `Scenario ${s}` }))} />}
                >
                  <StreetScene
                    greenness={Math.min(1, Math.max(l.treesPct / LEVER_LIMITS.treesPct, l.roofsPct / LEVER_LIMITS.roofsPct))}
                    label="Street illustration. Trees and white roofs increase as the sliders move."
                  />
                  <RangeField id="trees" label="Open land planted with trees" value={l.treesPct} min={0} max={LEVER_LIMITS.treesPct} onChange={set('treesPct')} />
                  <RangeField id="roofs" label="Buildings with cool roofs" value={l.roofsPct} min={0} max={LEVER_LIMITS.roofsPct} onChange={set('roofsPct')} />
                  <RangeField id="paving" label="Paved area made permeable" value={l.pavingPct} min={0} max={LEVER_LIMITS.pavingPct} onChange={set('pavingPct')} />
                  <div className="row-actions">
                    <Button onClick={() => setLevers((s) => ({ ...s, [slot]: START[slot] }))}>Reset scenario {slot}</Button>
                    <Button onClick={loadPlan} disabled={!result} title={result ? undefined : 'Optimize a plan first'}>
                      Load my optimized plan
                    </Button>
                  </div>
                  {!result && <p className="note">“Load my optimized plan” unlocks after you evaluate a plan.</p>}
                </Panel>

                <Panel title={`Scenario ${slot} outcome`} note="Illustrative model applied to sample city figures. It is not a forecast.">
                  <div className="outs">
                    {ROWS.map((r) => {
                      const d = cur[r.key] - anchor[r.key];
                      const good = r.upIsGood ? d >= 0 : d <= 0;
                      return (
                        <div key={r.key} className="outs__cell">
                          <span className="k">{r.label} (now {anchor[r.key].toFixed(r.digits)}{r.unit})</span>
                          <div className="v">{cur[r.key].toFixed(r.digits)}{r.unit}</div>
                          <span className={`delta ${Math.abs(d) < 0.05 ? '' : good ? 'delta--good' : 'delta--bad'}`}>
                            {Math.abs(d) < 0.05 ? 'no change' : `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(r.digits)}${r.unit}`}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </Panel>
              </div>

              <Panel title="Compare scenarios" note="Best value in each row is marked. Values are simulated.">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>Measure</th><th className="n">Today (sample)</th>{SLOTS.map((s) => <th key={s} className="n">Scenario {s}</th>)}</tr>
                    </thead>
                    <tbody>
                      {ROWS.map((r) => {
                        const vals = SLOTS.map((s) => projected![s][r.key]);
                        const best = r.upIsGood ? Math.max(...vals) : Math.min(...vals);
                        return (
                          <tr key={r.key}>
                            <td>{r.label}</td>
                            <td className="n">{anchor[r.key].toFixed(r.digits)}{r.unit}</td>
                            {SLOTS.map((s, i) => (
                              <td key={s} className={`n${vals[i] === best ? ' best' : ''}`}>
                                {vals[i].toFixed(r.digits)}{r.unit}{vals[i] === best && <span className="sr-only"> (best)</span>}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </>
          );
        }}
      </DataGate>
    </>
  );
}
