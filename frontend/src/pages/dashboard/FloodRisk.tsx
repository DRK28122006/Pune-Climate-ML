import { useMemo, useState } from 'react';
import DataGate from '../../components/DataGate';
import { ConceptMap, waterColor } from '../../components/charts/Visuals';
import { DemoBadge, EmptyState, MetricCard, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { RangeField } from '../../components/Field';
import { getFloodAreas } from '../../data/api';
import type { FloodArea } from '../../data/sample';
import { clamp } from '../../lib/math';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';
import type { Priority } from '../../types';

/** Demo rule: more paved surface floods at lower rainfall intensity. */
const threshold = (a: FloodArea) => 90 - a.pavedPct * 0.6;
const exposureShare = (a: FloodArea, rain: number) => clamp((rain - threshold(a)) / 50, 0, 1);

export default function FloodRisk() {
  const state = useAsync(getFloodAreas);
  const { result } = usePlan();
  const [rain, setRain] = useState(60);
  const [filter, setFilter] = useState<'all' | Priority>('all');
  const [selected, setSelected] = useState<string | null>('riverside');
  const [applyPlan, setApplyPlan] = useState(false);

  const reduction = result ? clamp((result.before.runoffIndex - result.after.runoffIndex) / result.before.runoffIndex, 0, 1) : 0;
  const exposed = (a: FloodArea) => {
    const base = a.households * exposureShare(a, rain);
    return applyPlan && result && a.wardId && result.inputs.focusArea.toLowerCase() === a.wardId ? base * (1 - reduction) : base;
  };

  const areas = state.data ?? [];
  const rows = useMemo(() => areas.filter((a) => filter === 'all' || a.risk === filter), [areas, filter]);
  const total = areas.reduce((s, a) => s + exposed(a), 0);

  return (
    <>
      <PageHeader
        eyebrow="Flood risk"
        title="Flood Risk"
        lede="Low-lying, heavily paved areas drain slowest. Choose a rainfall intensity to see how many households a simple demo rule would flag."
        badge={<DemoBadge />}
      />
      <DataGate state={state}>
        {(list) => {
          const sel = list.find((a) => a.id === selected) ?? null;
          return (
            <>
              <Panel title="Rainfall scenario (demo)">
                <RangeField id="rain" label="Rainfall intensity" unit=" mm/hour" min={20} max={120} value={rain} onChange={setRain} />
                <div className="toolbar toolbar--tight">
                  <label className="check">
                    <input type="checkbox" checked={applyPlan} disabled={!result} onChange={(e) => setApplyPlan(e.target.checked)} />
                    Apply my plan's runoff reduction to the {result ? result.inputs.focusArea : 'focus'} area
                  </label>
                  {!result && <span className="note">Unlocks after you optimize a plan.</span>}
                </div>
              </Panel>

              <div className="metrics">
                <MetricCard label="Households flagged" value={Math.round(total).toLocaleString('en-IN')} note={`At ${rain} mm/hour, demo rule`} />
                <MetricCard label="Areas affected" value={String(list.filter((a) => exposed(a) > 0).length)} unit={`of ${list.length}`} />
                {applyPlan && result && <MetricCard label="Plan runoff reduction" value={(reduction * 100).toFixed(0)} unit="%" note="Demo model, plan area only" delta={{ text: 'applied', good: true }} />}
              </div>

              <div className="two-col two-col--map">
                <Panel title="Risk map (conceptual)" actions={<Segmented<'all' | Priority> label="Filter by risk" value={filter} onChange={setFilter} options={[{ value: 'all', label: 'All' }, { value: 'high', label: 'High' }, { value: 'med', label: 'Medium' }, { value: 'low', label: 'Low' }]} />}>
                  <ConceptMap
                    cols={3}
                    rows={2}
                    ariaLabel="Flood area tiles. Select an area for details."
                    selectedId={selected}
                    onSelect={setSelected}
                    tiles={list.map((a) => {
                      const share = exposureShare(a, rain);
                      return {
                        id: a.id,
                        label: a.name,
                        display: `${Math.round(exposed(a)).toLocaleString('en-IN')} flagged`,
                        color: waterColor(share),
                        col: a.col,
                        row: a.row,
                        dimmed: !rows.some((r) => r.id === a.id),
                        darkText: share < 0.45,
                      };
                    })}
                  />
                  <p className="legend"><span className="legend__ramp" data-measure="water" />Lower to higher share of households flagged</p>
                </Panel>

                <Panel title={sel ? sel.name : 'Area details'}>
                  {sel ? (
                    <div className="detail">
                      <Pill tone={sel.risk} />
                      <dl className="mlist">
                        <div><dt>Households</dt><dd>{sel.households.toLocaleString('en-IN')}</dd></div>
                        <div><dt>Paved surface</dt><dd>{sel.pavedPct}%</dd></div>
                        <div><dt>Flags above</dt><dd>{threshold(sel).toFixed(0)} mm/hour</dd></div>
                        <div><dt>Suggested first action</dt><dd>{sel.action}</dd></div>
                      </dl>
                    </div>
                  ) : (
                    <EmptyState title="Select an area" text="Choose a tile to see its details." />
                  )}
                </Panel>
              </div>

              <Panel title="Areas ranked" note="Sample data. The flagging rule is a demonstration, not a hydrological model.">
                {rows.length === 0 ? (
                  <EmptyState title="No areas match this filter" text="Choose a different risk level." />
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr><th>Area</th><th>Risk</th><th className="n">Households</th><th className="n">Paved</th><th className="n">Flagged at {rain} mm/h</th><th>Suggested first action</th></tr>
                      </thead>
                      <tbody>
                        {rows.map((a) => (
                          <tr key={a.id} className={a.id === selected ? 'is-sel' : ''}>
                            <td><button type="button" className="linkbtn" onClick={() => setSelected(a.id)}>{a.name}</button></td>
                            <td><Pill tone={a.risk} /></td>
                            <td className="n">{a.households.toLocaleString('en-IN')}</td>
                            <td className="n">{a.pavedPct}%</td>
                            <td className="n">{Math.round(exposed(a)).toLocaleString('en-IN')}</td>
                            <td>{a.action}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>
            </>
          );
        }}
      </DataGate>
    </>
  );
}
