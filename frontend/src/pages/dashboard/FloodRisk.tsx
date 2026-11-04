import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import DataGate from '../../components/DataGate';
import { ConceptMap, waterColor } from '../../components/charts/Visuals';
import { EmptyState, MetricCard, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { RangeField } from '../../components/Field';
import { getFloodAreas } from '../../data/api';
/** Ward flood row built by realApi from ward_scores.json (satellite cube + ML factors). */
interface FloodArea {
  id: string;
  name: string;
  risk: Priority;
  pavedPct: number;
  action: string;
  flood_score?: number | null;
  impact?: number | null;
  col: number;
  row: number;
}
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
  // The ML scorer reports a flood factor for the scored ward; it does not produce a
  // before/after runoff reduction, so the demo rule below stays independent of it.
  const floodFactor = result?.score.factors?.flood?.score ?? null;

  const areas = state.data ?? [];
  const rows = useMemo(() => areas.filter((a) => filter === 'all' || a.risk === filter), [areas, filter]);
  const exposedCount = areas.filter((a) => exposureShare(a, rain) > 0).length;

  return (
    <>
      <PageHeader
        eyebrow="Flood risk"
        title="Flood Risk"
        lede="Each ward's built-up share is measured (satellite cube) and its flood factor comes from the ML scorer. The rainfall threshold below is an illustrative heuristic, not a hydrological model."
        badge={<Pill tone="med">Demo heuristic</Pill>}
      />
      <DataGate state={state}>
        {(list) => {
          const sel = list.find((a) => a.id === selected) ?? null;
          const ff = list.map((a) => a.flood_score).filter((v): v is number => v != null);
          const meanFlood = ff.length ? ff.reduce((x, y) => x + y, 0) / ff.length : null;
          return (
            <>
              <Panel title="Rainfall scenario (demo)">
                <RangeField id="rain" label="Rainfall intensity" unit=" mm/hour" min={20} max={120} value={rain} onChange={setRain} />
                <div className="toolbar toolbar--tight">
                  {result ? (
                    <span className="note">
                      ML flood factor for ward {result.ward ?? '—'}: <b>{floodFactor != null ? `${floodFactor}/100` : 'UNAVAILABLE'}</b>
                      {' '}· evidence {result.score.evidence_status ?? '—'} (scored in <Link to="/assess">Evaluate a plan</Link>)
                    </span>
                  ) : (
                    <span className="note">No plan scored yet — <Link to="/assess">evaluate a plan</Link> to see its ML flood factor here.</span>
                  )}
                </div>
              </Panel>

              <div className="metrics">
                <MetricCard label="Wards exposed" value={String(exposedCount)} unit={`of ${list.length}`} note={`At ${rain} mm/hour, illustrative heuristic`} />
                <MetricCard label="Mean flood factor" value={meanFlood != null ? meanFlood.toFixed(1) : 'UNAVAILABLE'} unit={meanFlood != null ? '/100' : ''} note="Satellite cube, all wards" />
                {result && floodFactor != null && (
                  <MetricCard label={`ML flood factor · ward ${result.ward ?? '—'}`} value={String(floodFactor)} unit="/100" note={floodFactor >= 50 ? 'Higher score = higher flood factor contribution' : 'Lower contribution to impact'} />
                )}
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
                        display: `${Math.round(exposureShare(a, rain) * 100)}% exposed`,
                        color: waterColor(share),
                        col: a.col,
                        row: a.row,
                        dimmed: !rows.some((r) => r.id === a.id),
                        darkText: share < 0.45,
                      };
                    })}
                  />
                  <p className="legend"><span className="legend__ramp" data-measure="water" />Built-up share exceeds the heuristic threshold — illustrative, not a hydrological model</p>
                </Panel>

                <Panel title={sel ? sel.name : 'Area details'}>
                  {sel ? (
                    <div className="detail">
                      <Pill tone={sel.risk} />
                      <dl className="mlist">
                        <div><dt>Built-up share</dt><dd>{sel.pavedPct}%</dd></div>
                        <div><dt>Flood factor</dt><dd>{sel.flood_score != null ? `${sel.flood_score}/100` : 'UNAVAILABLE'}</dd></div>
                        <div><dt>Flags above</dt><dd>{threshold(sel).toFixed(0)} mm/hour</dd></div>
                        <div><dt>Suggested first action</dt><dd>{sel.action}</dd></div>
                      </dl>
                    </div>
                  ) : (
                    <EmptyState title="Select an area" text="Choose a tile to see its details." />
                  )}
                </Panel>
              </div>

              <Panel title="Wards ranked" note="Built-up share and flood factor are measured (satellite cube / ML scorer). The flagging threshold is an illustrative heuristic, not a hydrological model.">
                {rows.length === 0 ? (
                  <EmptyState title="No areas match this filter" text="Choose a different risk level." />
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr><th>Ward</th><th>Risk</th><th className="n">Flood factor</th><th className="n">Built-up</th><th className="n">Exposure at {rain} mm/h</th><th>Suggested first action</th></tr>
                      </thead>
                      <tbody>
                        {rows.map((a) => (
                          <tr key={a.id} className={a.id === selected ? 'is-sel' : ''}>
                            <td><button type="button" className="linkbtn" onClick={() => setSelected(a.id)}>{a.name}</button></td>
                            <td><Pill tone={a.risk} /></td>
                            <td className="n">{a.flood_score != null ? a.flood_score : '—'}</td>
                            <td className="n">{a.pavedPct}%</td>
                            <td className="n">{Math.round(exposureShare(a, rain) * 100)}%</td>
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
