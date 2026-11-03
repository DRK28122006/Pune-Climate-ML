import { useEffect, useMemo, useState } from 'react';
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

interface Ward {
  id: string;
  name: string;
  tempC: number;
  canopyPct: number;
  priority: Priority;
  wardNo: number;
  col: number;
  row: number;
  impact: number;
  climate: number;
  risk_band: string;
  evidence_status: string;
  flood: number;
  heat: number;
  green: number;
  carbon: number;
  green_verified: boolean;
  built_pct: number;
  veg_pct: number;
  night_lst: number;
}

function safeTemp(temp: number | undefined): number {
  return typeof temp === 'number' && isFinite(temp) ? temp : 0;
}

function safeCanopy(canopy: number | undefined): number {
  return typeof canopy === 'number' && isFinite(canopy) ? canopy : 0;
}

function safePriority(p: Priority | undefined): Priority {
  return p === 'high' || p === 'med' || p === 'low' ? p : 'low';
}

function safeNum(n: number | undefined, fallback = 0): number {
  return typeof n === 'number' && isFinite(n) ? n : fallback;
}

export default function Heat() {
  const state = useAsync(getWards);
  const [measure, setMeasure] = useState<'temp' | 'canopy'>('temp');
  const [filter, setFilter] = useState<'all' | Priority>('all');
  const [sort, setSort] = useState<'hottest' | 'canopy'>('hottest');
  const [selected, setSelected] = useState<string | null>(null);

  const wards = useMemo(() => (state.data ?? []) as Ward[], [state.data]);

  const rows = useMemo(() => {
    const w = state.data ?? [];
    const f = filter === 'all' ? w : w.filter((x) => safePriority(x.priority) === filter);
    return [...f].sort((a, b) => (sort === 'hottest'
      ? safeTemp(b.tempC) - safeTemp(a.tempC)
      : safeCanopy(a.canopyPct) - safeCanopy(b.canopyPct)));
  }, [state.data, filter, sort]);

  // Clear selection when filtered out
  useEffect(() => {
    if (selected && !rows.some((r) => r.id === selected)) {
      setSelected(rows[0]?.id ?? null);
    }
  }, [filter, rows, selected]);

  const maxT = useMemo(() => {
    const temps = wards.map((w) => safeTemp(w.tempC)).filter((t) => t > 0);
    return temps.length > 0 ? Math.max(...temps) : 42;
  }, [wards]);

  const selectedWard = useMemo(() => wards.find((w) => w.id === selected) ?? null, [wards, selected]);

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
          const safeWards = wards as Ward[];
          const sel = selectedWard;
          const maxT = Math.max(...safeWards.map((w) => safeTemp(w.tempC)).filter((t) => t > 0), 42);

          return (
            <>
              <div className="toolbar">
                <Segmented<'temp' | 'canopy'>
                  label="Map measure"
                  value={measure}
                  onChange={setMeasure}
                  options={[{ value: 'temp', label: 'Surface temperature' }, { value: 'canopy', label: 'Tree cover' }]}
                />
                <Segmented<'all' | Priority>
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
                    tiles={safeWards.map((w) => ({
                      id: w.id,
                      label: w.name,
                      display: measure === 'temp' ? `${safeTemp(w.tempC).toFixed(1)}°C` : `${safeCanopy(w.canopyPct)}%`,
                      color: measure === 'temp'
                        ? heatColor(safeTemp(w.tempC), 36, 42)
                        : greenColor(safeCanopy(w.canopyPct), 5, 30),
                      col: safeNum(w.col),
                      row: safeNum(w.row),
                      dimmed: !rows.some((r) => r.id === w.id),
                      darkText: measure === 'temp' ? safeTemp(w.tempC) < 39 : safeCanopy(w.canopyPct) < 18,
                    }))}
                  />
                  <p className="legend"><span className="legend__ramp" data-measure={measure} />{measure === 'temp' ? 'Cooler (36°C) to hotter (42°C)' : 'Less cover (5%) to more cover (30%)'}</p>
                </Panel>

                <Panel title={sel ? sel.name : 'Ward details'}>
                  {sel ? (
                    <div className="detail">
                      <Pill tone={safePriority(sel.priority)} />
                      <dl className="mlist">
                        <div><dt>Surface temperature</dt><dd>{safeTemp(sel.tempC).toFixed(1)}°C</dd></div>
                        <div><dt>Against city average ({CITY_AVG_TEMP}°C)</dt><dd>{safeTemp(sel.tempC) - CITY_AVG_TEMP >= 0 ? '+' : '−'}{Math.abs(safeTemp(sel.tempC) - CITY_AVG_TEMP).toFixed(1)}°C</dd></div>
                        <div><dt>Tree cover</dt><dd>{safeCanopy(sel.canopyPct)}%</dd></div>
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
                  <Segmented<'hottest' | 'canopy'>
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
                            <td>
                              <BarRow
                                label={w.name}
                                value={safeTemp(w.tempC) - 30}
                                max={Math.max(maxT - 30, 1)}
                                display={`${safeTemp(w.tempC).toFixed(1)}°`}
                                color={heatColor(safeTemp(w.tempC), 36, 42)}
                              />
                            </td>
                            <td className="n">{safeTemp(w.tempC) - CITY_AVG_TEMP >= 0 ? '+' : '−'}{Math.abs(safeTemp(w.tempC) - CITY_AVG_TEMP).toFixed(1)}°</td>
                            <td className="n">{safeCanopy(w.canopyPct)}%</td>
                            <td><Pill tone={safePriority(w.priority)} /></td>
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