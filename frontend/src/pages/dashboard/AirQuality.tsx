import { useState } from 'react';
import DataGate from '../../components/DataGate';
import LineChart, { type Band } from '../../components/charts/LineChart';
import { DemoBadge, MetricCard, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { getAirQuality, type AirQualityData } from '../../services/climateApi';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';

type Range = 'hourly' | 'daily';

const BAND_FILL = [
  'rgba(35,112,74,0.12)',   // good
  'rgba(138,93,0,0.10)',    // moderate
  'rgba(184,64,42,0.10)',   // unhealthy
  'rgba(120,20,60,0.12)',   // very unhealthy
];
const bands: Band[] = [
  { from: 0, to: 50, label: 'Good', fill: BAND_FILL[0] },
  { from: 51, to: 100, label: 'Moderate', fill: BAND_FILL[1] },
  { from: 101, to: 150, label: 'Unhealthy for Sensitive', fill: BAND_FILL[2] },
  { from: 151, to: 300, label: 'Unhealthy', fill: BAND_FILL[3] },
];

const bandFor = (v: number) => bands.find((b) => v >= b.from && v <= b.to) ?? bands[bands.length - 1];

const bandTone = (v: number): 'high' | 'med' | 'low' => {
  if (v <= 50) return 'low';
  if (v <= 100) return 'med';
  return 'high';
};

const aqiColor = (v: number): string => {
  if (v <= 50) return '#2e7d4f';   // leaf
  if (v <= 100) return '#7d5400';  // amber
  if (v <= 150) return '#c9821a';  // orange
  if (v <= 200) return '#a8371f';  // heat
  return '#6a1b1b';                // very unhealthy
};

export default function AirQuality() {
  const state = useAsync(getAirQuality);
  const [range, setRange] = useState<Range>('hourly');
  const { result } = usePlan();

  return (
    <>
      <PageHeader
        eyebrow="Air quality"
        title="Air Quality"
        badge={<DemoBadge label="Open-Meteo real data" />}
      />
      <DataGate state={state}>
        {(d) => {
          if (d.unavailable) {
            return (
              <div className="state state--empty" style={{ padding: '32px', textAlign: 'center' }}>
                <p style={{ fontSize: '16px', fontWeight: 600, color: '#1b2a26', marginBottom: '8px' }}>Air quality data is not available</p>
                <p style={{ color: '#4a5a55', maxWidth: '600px', margin: '0 auto' }}>{d.reason}</p>
              </div>
            );
          }

          const series = range === 'hourly' ? d.hourly : d.daily;
          const labels = range === 'hourly'
            ? Array.from({ length: 24 }, (_, i) => `${String((i + 1) % 24).padStart(2, '0')}:00`)
            : d.iso ? ['Today', 'Tomorrow', '+2d', '+3d', '+4d', '+5d', '+6d'] : [];
          const peak = Math.max(...series);
          const avg = series.reduce((a: number, b: number) => a + b, 0) / series.length;

          return (
            <>
              <div className="metrics">
                <MetricCard
                  label="Current AQI"
                  value={String(d.aqi)}
                  unit=""
                  pill={{ tone: bandTone(d.aqi), text: bandFor(d.aqi).label }}
                  note={d.city ? `Station: ${d.city}` : ''}
                />
                <MetricCard label="24h average" value={avg.toFixed(0)} unit="AQI" />
                <MetricCard label="Dominant pollutant" value={d.dominant?.toUpperCase() ?? '—'} unit="" />
                <MetricCard label="Data time" value={d.time ?? '—'} unit="" note={d.iso ?? ''} />
              </div>

              <Panel
                title="City air index"
                actions={
                  <Segmented<Range>
                    label="Time range"
                    value={range}
                    onChange={setRange}
                    options={[
                      { value: 'hourly', label: 'Last 24 hours' },
                      { value: 'daily', label: 'Daily forecast' },
                    ]}
                  />
                }
                note="Real Open-Meteo air quality data. Current reading + 3-day forecast. No API key needed."
              >
                <LineChart
                  values={series}
                  xLabels={labels}
                  labelEvery={range === 'hourly' ? 4 : 1}
                  yMax={300}
                  yTicks={[0, 50, 100, 150, 200, 250, 300]}
                  yLabel="Air quality index"
                  xLabel={range === 'hourly' ? 'Hour' : 'Day'}
                  bands={bands}
                  ariaLabel={`Air index. Peak ${peak} at AQI ${d.aqi}.`}
                />
              </Panel>

              <div className="two-col">
                <Panel title="Pune monitoring stations" note="WAQI stations across Pune. All readings from 2021 (WAQI free tier).">
                  <ul className="stations">
                    {d.stations.map((s: { station: string; aqi: number; dominant: string | null; geo: [number, number] | null }) => (
                      <li key={s.station} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid rgba(40,34,26,0.08)' }}>
                        <div>
                          <span style={{ fontWeight: 600, fontSize: '13px' }}>{s.station}</span>
                          {s.geo && <span style={{ fontSize: '11px', color: '#4a5a55', marginLeft: '8px' }}>({s.geo[0].toFixed(2)}, {s.geo[1].toFixed(2)})</span>}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <b style={{ color: aqiColor(s.aqi), fontSize: '16px' }}>{s.aqi}</b>
                          <Pill tone={bandTone(s.aqi)}>{bandFor(s.aqi).label}</Pill>
                        </div>
                      </li>
                    ))}
                  </ul>
                  {d.stations.length === 0 && <p className="note">No station data available.</p>}
                </Panel>

                <Panel title="Pollutant breakdown (IAQI)" note="Individual pollutant sub-indices for Shivajinagar station.">
                  {Object.entries(d.iaqi).map(([pol, v]) => (
                    <div key={pol} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(40,34,26,0.08)' }}>
                      <span style={{ fontSize: '13px', color: '#4a5a55' }}>{pol.toUpperCase()}</span>
                      <b>{v.v}</b>
                    </div>
                  ))}
                  {Object.keys(d.iaqi).length === 0 && <p className="note">No individual pollutant data available.</p>}
                </Panel>

                {result && (
                  <Panel title="Effect of your plan (demo)" note="Simulated for the plan area only.">
                    {result ? (
                      <div>
                        <p>
                          For <b>{result.inputs.planName}</b>, the demo model evaluates the plan area against current AQI {d.aqi}.
                        </p>
                        <p className="note">Simulated scenario — unrelated to live station readings.</p>
                      </div>
                    ) : (
                      <p className="note">Evaluate a plan to see its modelled effect.</p>
                    )}
                  </Panel>
                )}
              </div>

              <Panel title="Data source" note="Open-Meteo Air Quality API.">
                {d.attributions.map((a, i) => (
                  <div key={i} style={{ padding: '4px 0', fontSize: '13px', color: '#4a5a55' }}>
                    <a href={a.url} target="_blank" rel="noopener noreferrer" style={{ color: '#1f5a8c', textDecoration: 'underline' }}>
                      {a.name}
                    </a>
                  </div>
                ))}
                {d.attributions.length === 0 && <p className="note">No source attributions available.</p>}
              </Panel>

              {d.historical && (
                <Panel title="Historical comparison" note="PM2.5 monthly averages. 2025 vs 2026.">
                  <div style={{ display: 'flex', gap: '24px', marginBottom: '16px' }}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '24px', fontWeight: 700, color: '#1b2a26' }}>{d.historical!.yearly_2025}</div>
                      <div style={{ fontSize: '11px', color: '#4a5a55' }}>2025 avg (µg/m³)</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '24px', fontWeight: 700, color: '#1b2a26' }}>{d.historical!.yearly_2026}</div>
                      <div style={{ fontSize: '11px', color: '#4a5a55' }}>2026 avg (µg/m³)</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '24px', fontWeight: 700, color: (d.historical!.yearly_2026 ?? 0) > (d.historical!.yearly_2025 ?? 0) ? '#a8371f' : '#2e7d4f' }}>
                        {(d.historical!.yearly_2026 ?? 0) > (d.historical!.yearly_2025 ?? 0) ? '+' : ''}{((d.historical!.yearly_2026 ?? 0) - (d.historical!.yearly_2025 ?? 0)).toFixed(1)}
                      </div>
                      <div style={{ fontSize: '11px', color: '#4a5a55' }}>YoY change</div>
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '4px', fontSize: '11px' }}>
                    {Object.entries(d.historical!.monthly_2026).map(([month, val]) => {
                      const prevVal = d.historical!.monthly_2025[month];
                      const change = prevVal ? (val - prevVal).toFixed(1) : '—';
                      return (
                        <div key={month} style={{ textAlign: 'center', padding: '4px', background: '#fffcf6', border: '1px solid rgba(40,34,26,0.12)', borderRadius: '4px' }}>
                          <div style={{ fontWeight: 600, color: '#1b2a26' }}>{month.slice(5)}</div>
                          <div style={{ color: '#1b2a26' }}>{val}</div>
                          {prevVal && <div style={{ color: val > prevVal ? '#a8371f' : '#2e7d4f', fontSize: '10px' }}>{val > prevVal ? '+' : ''}{change}</div>}
                        </div>
                      );
                    })}
                  </div>
                  <p className="note" style={{ marginTop: '8px' }}>
                    Monthly PM2.5 averages (µg/m³). Red = worse than 2025, green = better. Data from Open-Meteo Air Quality API.
                  </p>
                </Panel>
              )}
            </>
          );
        }}
      </DataGate>
    </>
  );
}
