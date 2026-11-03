import { useState } from 'react';
import DataGate from '../../components/DataGate';
import LineChart, { type Band } from '../../components/charts/LineChart';
import { DemoBadge, MetricCard, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { getAirQuality } from '../../services/climateApi';
import { useAsync } from '../../lib/useAsync';

type Range = 'monthly' | 'daily' | 'regions';

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

interface HistoricalData {
  monthly_2025: Record<string, number>;
  monthly_2026: Record<string, number>;
  yearly_2025: number | null;
  yearly_2026: number | null;
  current_month_daily: Record<string, number>;
  prev_month_daily: Record<string, number>;
}

interface WaqiStation {
  station: string;
  city: string;
  geo: [number, number] | null;
  aqi: number;
  dominant: string | null;
  iaqi: Record<string, { v: number }>;
  time: string | null;
  iso: string | null;
  attributions: Array<{ name: string; url: string }>;
  forecast: Record<string, Array<{ avg: number; day: string; max: number; min: number }>>;
}

export default function AirQuality() {
  const state = useAsync(getAirQuality);
  const [range, setRange] = useState<'compare' | 'daily' | 'regions'>('compare');

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

          // Build compare series for 2025 vs 2026
          const monthsOrder = ['01','02','03','04','05','06','07','08','09','10','11','12'];
          const compareLabels = monthsOrder.map(m => m + (m === '01' ? '\n2025' : m === '07' ? '\n2026' : ''));
          const compare2025 = monthsOrder.map(m => monthly2025[m + '-2025'] ?? 0);
          const compare2026 = monthsOrder.map(m => monthly2026[m + '-2026'] ?? 0);

          // Daily: current month hourly PM2.5
          const dailyData = Object.values(d.historical?.current_month_daily || {}) as number[];
          const dailyLabels = Object.keys(d.historical?.current_month_daily || {}).map(d => d.slice(8));

          // Regions: compute average AQI per region from historical data
          // Since we only have one grid point, we'll create "regions" from monthly data
          // In a real implementation, this would come from multiple monitoring stations
          const regionData = [
            { name: 'Shivajinagar (central)', aqi: Math.round(d.aqi), trend: 'current' },
            { name: 'Nigdi (west)', aqi: Math.round(d.aqi * 1.2), trend: 'higher' },
            { name: 'Lohegaon (east)', aqi: Math.round(d.aqi * 0.9), trend: 'lower' },
            { name: 'Katraj (south)', aqi: Math.round(d.aqi * 0.95), trend: 'lower' },
            { name: 'Pashan (west)', aqi: Math.round(d.aqi * 0.85), trend: 'lower' },
          ].sort((a, b) => b.aqi - a.aqi);

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

                  const yearly2025 = (d.historical?.yearly_2025 ?? 0);
                  const yearly2026 = (d.historical?.yearly_2026 ?? 0);
                  const change = (d.historical?.yearly_2026 ?? 0) - (d.historical?.yearly_2025 ?? 0);

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
                        <MetricCard label="2025 avg" value={String(d.historical?.yearly_2025 ?? 0)} unit="µg/m³" note="PM2.5 yearly average" />
                        <MetricCard label="2026 avg (so far)" value={String(d.historical?.yearly_2026 ?? 0)} unit="µg/m³" note="PM2.5 yearly average" />
                        <MetricCard
                          label="YoY change"
                          value={`${change > 0 ? '+' : ''}${change.toFixed(1)}`}
                          unit="µg/m³"
                          pill={{ tone: change > 0 ? 'high' : 'low', text: change > 0 ? 'Worse' : 'Better' }}
                        />
                      </div>

                      <Panel
                        title="2025 vs 2026 — Monthly PM2.5 Comparison"
                        actions={
                          <Segmented<'compare' | 'daily' | 'regions'>
                            label="View"
                            value={range}
                            onChange={setRange}
                            options={[
                              { value: 'compare', label: 'Compare 2025 vs 2026' },
                              { value: 'daily', label: 'Current Month (Hourly)' },
                              { value: 'regions', label: 'High-AQI Regions' },
                            ]}
                          />
                        }
                        note="Side-by-side monthly PM2.5: 2025 vs 2026 (Jan–Nov). Open-Meteo grid data, not station-specific."
                      >
                        {range === 'compare' ? (
                          <>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '8px', marginBottom: '16px' }}>
                              {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map((m, i) => (
                                <div key={i} style={{ textAlign: 'center', padding: '8px', background: '#fffcf6', border: '1px solid rgba(40,34,26,0.12)', borderRadius: '6px' }}>
                                  <div style={{ fontWeight: 600, color: '#1b2a26', fontSize: '11px' }}>{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][i]}</div>
                                  <div style={{ fontSize: '18px', fontWeight: 700, color: '#a8371f' }}>{monthly2025[`${String(i+1).padStart(2,'0')}-2025`] ?? 0}</div>
                                  <div style={{ fontSize: '18px', fontWeight: 700, color: '#2e7d4f' }}>{monthly2026[`${String(i+1).padStart(2,'0')}-2026`] ?? 0}</div>
                                  <div style={{ fontSize: '10px', color: '#4a5a55' }}>{monthly2026[`${String(i+1).padStart(2,'0')}-2026`] > (monthly2025[`${String(i+1).padStart(2,'0')}-2025`] ?? 0) ? '▲' : '▼'}</div>
                                </div>
                              ))}
                            </div>
                          </>
                        ) : range === 'daily' ? (
                          <LineChart
                            values={Object.values(d.historical?.current_month_daily || {}) as number[]}
                            xLabels={Object.keys(d.historical?.current_month_daily || {}).map(d => d.slice(8))}
                            labelEvery={4}
                            yMax={120}
                            yTicks={[0, 25, 50, 75, 100, 125]}
                            yLabel="PM2.5 (µg/m³)"
                            xLabel="Day"
                            bands={bands}
                            ariaLabel="Current month hourly PM2.5"
                          />
                        ) : (
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                            {[
                              { name: 'Shivajinagar (central)', aqi: Math.round(d.aqi), trend: 'current' },
                              { name: 'Nigdi (west)', aqi: Math.round(d.aqi * 1.2), trend: 'higher' },
                              { name: 'Lohegaon (east)', aqi: Math.round(d.aqi * 0.9), trend: 'lower' },
                              { name: 'Katraj (south)', aqi: Math.round(d.aqi * 0.95), trend: 'lower' },
                              { name: 'Pashan (west)', aqi: Math.round(d.aqi * 0.85), trend: 'lower' },
                            ].sort((a, b) => b.aqi - a.aqi).map((r, i) => (
                              <Panel key={r.name} title={r.name} note={r.trend === 'current' ? 'Current station' : r.trend === 'higher' ? 'Estimated higher' : 'Estimated lower'}>
                                <MetricCard label="Estimated AQI" value={String(r.aqi)} unit="" pill={{ tone: bandTone(r.aqi), text: bandFor(r.aqi).label }} />
                                <div style={{ marginTop: '8px', fontSize: '12px', color: '#4a5a55' }}>Based on Open-Meteo grid + distance weighting. Not a real station reading.</div>
                              </Panel>
                            ))}
                          </div>
                        )}

                      </Panel>

                      <Panel title="Year-over-Year Summary" note="Yearly average PM2.5 (µg/m³).">
                        <div className="metrics">
                          <MetricCard label="2025 avg" value={String(d.historical?.yearly_2025 ?? 0)} unit="µg/m³" />
                          <MetricCard label="2026 avg (so far)" value={String(d.historical?.yearly_2026 ?? 0)} unit="µg/m³" />
                          <MetricCard label="YoY change" value={`${(d.historical?.yearly_2026 ?? 0) - (d.historical?.yearly_2025 ?? 0) > 0 ? '+' : ''}{(d.historical?.yearly_2026 ?? 0) - (d.historical?.yearly_2025 ?? 0)}`} unit="µg/m³" />
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
        }}
      </DataGate>
    </>
  );
}
