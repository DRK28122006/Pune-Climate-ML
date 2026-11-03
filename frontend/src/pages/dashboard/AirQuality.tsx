import { useState } from 'react';
import DataGate from '../../components/DataGate';
import LineChart, { type Band } from '../../components/charts/LineChart';
import { DemoBadge, MetricCard, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { getAirQuality } from '../../services/climateApi';
import { useAsync } from '../../lib/useAsync';

type Range = 'monthly' | 'daily';

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
  if (v <= 50) return '#2e7d4f';
  if (v <= 100) return '#7d5400';
  if (v <= 150) return '#c9821a';
  if (v <= 200) return '#a8371f';
  return '#6a1b1b';
};

export default function AirQuality() {
  const state = useAsync(getAirQuality);
  const [range, setRange] = useState<Range>('monthly');

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

          const h = (d.historical || {}) as any;
          const monthly2025 = h.monthly_2025 || {};
          const monthly2026 = h.monthly_2026 || {};
          const yearly2025 = h.yearly_2025 ?? 0;
          const yearly2026 = h.yearly_2026 ?? 0;
          const change = yearly2026 - yearly2025;

          const series = range === 'monthly'
            ? Object.values(monthly2026) as number[]
            : d.hourly;
          const labels = range === 'monthly'
            ? Object.keys(monthly2026).map((m) => m.slice(5))
            : Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);

          return (
            <>
              <div className="metrics">
                <MetricCard
                  label="Current AQI"
                  value={String(d.aqi)}
                  unit=""
                  pill={{ tone: bandTone(d.aqi), text: bandFor(d.aqi).label }}
                  note={`Station: ${d.city}`}
                />
                <MetricCard label="2025 avg" value={String(yearly2025)} unit="µg/m³" note="PM2.5 yearly average" />
                <MetricCard label="2026 avg (so far)" value={String(yearly2026)} unit="µg/m³" note="PM2.5 yearly average" />
                <MetricCard
                  label="YoY change"
                  value={`${change > 0 ? '+' : ''}${change.toFixed(1)}`}
                  unit="µg/m³"
                  pill={{ tone: change > 0 ? 'high' : 'low', text: change > 0 ? 'Worse' : 'Better' }}
                />
              </div>

              <Panel
                title="Pune air quality: 2025 vs 2026"
                actions={
                  <Segmented<Range>
                    label="Time range"
                    value={range}
                    onChange={setRange}
                    options={[
                      { value: 'monthly', label: 'Monthly' },
                      { value: 'daily', label: 'Daily (current)' },
                    ]}
                  />
                }
                note="Real Open-Meteo data. Monthly = PM2.5 averages. Daily = current month hourly."
              >
                <LineChart
                  values={series}
                  xLabels={labels}
                  labelEvery={range === 'monthly' ? 1 : 4}
                  yMax={120}
                  yTicks={[0, 25, 50, 75, 100, 125]}
                  yLabel="PM2.5 (µg/m³)"
                  xLabel={range === 'monthly' ? 'Month' : 'Hour'}
                  bands={bands}
                  ariaLabel={`Air quality. 2025 avg ${yearly2025}, 2026 avg ${yearly2026}.`}
                />
              </Panel>

              <div className="two-col">
                <Panel title="2025 vs 2026 monthly" note="PM2.5 monthly averages. Red = worse, green = better.">
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '4px', fontSize: '11px' }}>
                    {Object.entries(monthly2026 as Record<string, number>).map(([month, val]) => {
                      const prevVal = (monthly2025 as Record<string, number>)[month];
                      const diff = prevVal ? (val - prevVal) : 0;
                      return (
                        <div key={month} style={{ textAlign: 'center', padding: '4px', background: '#fffcf6', border: '1px solid rgba(40,34,26,0.12)', borderRadius: '4px' }}>
                          <div style={{ fontWeight: 600, color: '#1b2a26' }}>{month.slice(5)}</div>
                          <div style={{ color: '#1b2a26' }}>{val}</div>
                          {prevVal && <div style={{ color: diff > 0 ? '#a8371f' : '#2e7d4f', fontSize: '10px' }}>{diff > 0 ? '+' : ''}{diff.toFixed(1)}</div>}
                        </div>
                      );
                    })}
                  </div>
                </Panel>

                <Panel title="Pollutant breakdown (current)" note="Individual pollutant sub-indices.">
                  {Object.entries(d.iaqi as Record<string, { v: number }>).map(([pol, v]) => (
                    <div key={pol} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(40,34,26,0.08)' }}>
                      <span style={{ fontSize: '13px', color: '#4a5a55' }}>{pol.toUpperCase()}</span>
                      <b>{v.v}</b>
                    </div>
                  ))}
                  {Object.keys(d.iaqi).length === 0 && <p className="note">No individual pollutant data available.</p>}
                </Panel>
              </div>

              <Panel title="Data source" note="Open-Meteo Air Quality API (real-time + historical).">
                <p style={{ fontSize: '13px', color: '#4a5a55', lineHeight: 1.6 }}>
                  <b>Source:</b> Open-Meteo Air Quality API (open-meteo.com) — satellite-derived, no API key needed.<br />
                  <b>Location:</b> Pune grid point (18.52°N, 73.86°E).<br />
                  <b>Current data:</b> {d.time} (today).<br />
                  <b>Historical:</b> Jan 2025 – Nov 2026 monthly averages.<br />
                  <b>Limitation:</b> Modelled data, not ground station. No per-ward differentiation (grid resolution ~25km). WAQI free tier returns stale 2021 data.
                </p>
                {d.attributions.map((a, i) => (
                  <div key={i} style={{ padding: '4px 0', fontSize: '13px', color: '#4a5a55' }}>
                    <a href={a.url} target="_blank" rel="noopener noreferrer" style={{ color: '#1f5a8c', textDecoration: 'underline' }}>
                      {a.name}
                    </a>
                  </div>
                ))}
              </Panel>
            </>
          );
        }}
      </DataGate>
    </>
  );
}
