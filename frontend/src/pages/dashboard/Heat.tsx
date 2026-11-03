import { useMemo, useState } from 'react';
import DataGate from '../../components/DataGate';
import { ConceptMap, BarRow, heatColor, greenColor } from '../../components/charts/Visuals';
import { DemoBadge, EmptyState, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { getWards } from '../../data/api';
import { CITY_AVG_TEMP } from '../../data/sample';
import { useAsync } from '../../lib/useAsync';
import type { Priority } from '../../types';

type Measure = 'temp' | 'canopy';
type Filter = 'all' | Priority;
type Sort = 'hottest' | 'canopy';

export default function Heat() {
  const state = useAsync(getWards);
  const [measure, setMeasure] = useState<Measure>('temp');
  const [filter, setFilter] = useState<Filter>('all');
  const [sort, setSort] = useState<Sort>('hottest');
  const [selected, setSelected] = useState<string | null>('hadapsar');

  const rows = useMemo(() => {
    const w = state.data ?? [];
    const f = filter === 'all' ? w : w.filter((x) => x.priority === filter);
    return [...f].sort((a, b) => (sort === 'hottest' ? b.tempC - a.tempC : a.canopyPct - b.canopyPct));
  }, [state.data, filter, sort]);

  return (
    <>
      <PageHeader
        eyebrow="Urban heat"
        title="Heat"
        lede="Wards ranked by afternoon surface temperature, with the gap to the city average and the tree cover that could bring it down."
        badge={<DemoBadge />}
      />
      <DataGate state={state}>
        {(wards) => {
          const sel = wards.find((w) => w.id === selected) ?? null;
          const maxT = Math.max(...wards.map((w) => w.tempC));
          return (
            <>
              <div className="toolbar">
                <Segmented<Measure>
                  label="Map measure"
                  value={measure}
                  onChange={setMeasure}
                  options={[{ value: 'temp', label: 'Surface temperature' }, { value: 'canopy', label: 'Tree cover' }]}
                />
                <Segmented<Filter>
                  label="Filter by priority"
                  value={filter}
                  onChange={setFilter}
                  options={[{ value: 'all', label: 'All' }, { value: 'high', label: 'High' }, { value: 'med', label: 'Medium' }, { value: 'low', label: 'Low' }]}
                />
              </div>

              <div className="two-col two-col--map">
                <Panel title={measure === 'temp' ? 'Heat by ward (°C)' : 'Tree cover by ward (%)'}>
                  <ConceptMap
                    ariaLabel="Ward tiles. Select a ward to see details."
                    selectedId={selected}
                    onSelect={setSelected}
                    tiles={wards.map((w) => ({
                      id: w.id,
                      label: w.name,
                      display: measure === 'temp' ? `${w.tempC.toFixed(1)}°C` : `${w.canopyPct}%`,
                      color: measure === 'temp' ? heatColor(w.tempC, 36, 42) : greenColor(w.canopyPct, 5, 30),
                      col: w.col,
                      row: w.row,
                      dimmed: !rows.some((r) => r.id === w.id),
                      darkText: measure === 'temp' ? w.tempC < 39 : w.canopyPct < 18,
                    }))}
                  />
                  <p className="legend"><span className="legend__ramp" data-measure={measure} />{measure === 'temp' ? 'Cooler (36°C) to hotter (42°C)' : 'Less cover (5%) to more cover (30%)'}</p>
                </Panel>

                <Panel title={sel ? sel.name : 'Ward details'}>
                  {sel ? (
                    <div className="detail">
                      <Pill tone={sel.priority} />
                      <dl className="mlist">
                        <div><dt>Surface temperature</dt><dd>{sel.tempC.toFixed(1)}°C</dd></div>
                        <div><dt>Against city average ({CITY_AVG_TEMP}°C)</dt><dd>{sel.tempC - CITY_AVG_TEMP >= 0 ? '+' : '−'}{Math.abs(sel.tempC - CITY_AVG_TEMP).toFixed(1)}°C</dd></div>
                        <div><dt>Tree cover</dt><dd>{sel.canopyPct}%</dd></div>
                      </dl>
                      <p className="note">Hotter wards with low tree cover are usually the strongest candidates for planting and cool roofs.</p>
                    </div>
                  ) : (
                    <EmptyState title="Select a ward" text="Choose a tile on the map to see its figures." />
                  )}
                </Panel>
              </div>

              <Panel
                title="Wards ranked"
                actions={
                  <Segmented<Sort>
                    label="Sort wards"
                    value={sort}
                    onChange={setSort}
                    options={[{ value: 'hottest', label: 'Hottest first' }, { value: 'canopy', label: 'Least cover first' }]}
                  />
                }
                note={`Sample data. City average ${CITY_AVG_TEMP}°C.`}
              >
                {rows.length === 0 ? (
                  <EmptyState title="No wards match this filter" text="Choose a different priority level." />
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr><th>Ward</th><th>Surface temperature</th><th className="n">vs city average</th><th className="n">Tree cover</th><th>Priority</th></tr>
                      </thead>
                      <tbody>
                        {rows.map((w) => (
                          <tr key={w.id} className={w.id === selected ? 'is-sel' : ''}>
                            <td><button type="button" className="linkbtn" onClick={() => setSelected(w.id)}>{w.name}</button></td>
                            <td><BarRow label={w.name} value={w.tempC - 30} max={maxT - 30} display={`${w.tempC.toFixed(1)}°`} color={heatColor(w.tempC, 36, 42)} /></td>
                            <td className="n">{w.tempC - CITY_AVG_TEMP >= 0 ? '+' : '−'}{Math.abs(w.tempC - CITY_AVG_TEMP).toFixed(1)}°</td>
                            <td className="n">{w.canopyPct}%</td>
                            <td><Pill tone={w.priority} /></td>
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
