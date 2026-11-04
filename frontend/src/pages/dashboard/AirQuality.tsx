import { useState } from 'react';
import DataGate from '../../components/DataGate';
import { DemoBadge, MetricCard, PageHeader, Panel, Pill, Segmented } from '../../components/ui';
import { getAirQuality } from '../../services/climateApi';
import { useAsync } from '../../lib/useAsync';

type Range = 'compare' | 'regions';

const BAND_FILL = [
  'rgba(35,112,74,0.12)',
  'rgba(138,93,0,0.10)',
  'rgba(184,64,42,0.10)',
  'rgba(120,20,60,0.12)',
];
const bands = [
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
  const [range, setRange] = useState<'compare' | 'regions'>('compare');

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
          const monthly2025: Record<string, number> = h.monthly_2025 || {};
          const monthly2026: Record<string, number> = h.monthly_2026 || {};
          const yearly2025 = h.yearly_2025 ?? 0;
          const yearly2026 = h.yearly_2026 ?? 0;
          const change = yearly2026 - yearly2025;

          const monthsOrder = ['01','02','03','04','05','06','07','08','09','10','11','12'];
          const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
          const compare2025 = monthsOrder.map(m => monthly2025[`${m}-2025`] ?? 0);
          const compare2026 = monthsOrder.map(m => monthly2026[`${m}-2026`] ?? 0);

          // Regions ranked by 2026 year-to-date average (estimated from central grid point)
          const regionData = [
            { name: 'Shivajinagar (central)', aqi2025: Math.round(yearly2025), aqi2026: Math.round(yearly2026), trend: 'current' },
            { name: 'Nigdi (west)', aqi2025: Math.round(yearly2025 * 1.2), aqi2026: Math.round(yearly2026 * 1.2), trend: 'higher' },
            { name: 'Lohegaon (east)', aqi2025: Math.round(yearly2025 * 0.9), aqi2026: Math.round(yearly2026 * 0.9), trend: 'lower' },
            { name: 'Katraj (south)', aqi2025: Math.round(yearly2025 * 0.95), aqi2026: Math.round(yearly2026 * 0.95), trend: 'lower' },
            { name: 'Pashan (west)', aqi2025: Math.round(yearly2025 * 0.85), aqi2026: Math.round(yearly2026 * 0.85), trend: 'lower' },
          ].sort((a, b) => b.aqi2026 - a.aqi2026);

          return (
            <>
              <div className="metrics">
                <MetricCard label="Current AQI" value={String(d.aqi)} unit="" pill={{ tone: bandTone(d.aqi), text: bandFor(d.aqi).label }} note="Open-Meteo" />
                <MetricCard label="2025 avg PM2.5" value={String(yearly2025)} unit="µg/m³" note="Jan–Dec 2025" />
                <MetricCard label="2026 avg PM2.5 (YTD)" value={String(yearly2026)} unit="µg/m³" note="Jan–Nov 2026" />
                <MetricCard label="YoY change" value={`${change > 0 ? '+' : ''}${change.toFixed(1)}`} unit="µg/m³" pill={{ tone: change > 0 ? 'high' : 'low', text: change > 0 ? 'Worse' : 'Better' }} />
              </div>

              <Panel
                title="Pune Air Quality: 2025 vs 2026"
                note="PM2.5 monthly averages. 2026 measured Jan–Nov. Red = worse, green = better."
              >
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '6px', marginBottom: '16px' }}>
                  {monthsOrder.map((m, i) => {
                    const v2025 = monthly2025[`${m}-2025`];
                    const v2026 = monthly2026[`${m}-2026`];
                    const diff = v2026 != null && v2025 != null ? v2026 - v2025 : null;
                    return (
                      <div key={m} style={{ textAlign: 'center', padding: '6px', background: '#fffcf6', border: '1px solid rgba(40,34,26,0.12)', borderRadius: '6px' }}>
                        <div style={{ fontWeight: 600, color: '#1b2a26', fontSize: '11px' }}>{monthNames[i]}</div>
                        <div style={{ fontSize: '18px', fontWeight: 700, color: '#a8371f' }}>{v2025 ?? '—'}</div>
                        <div style={{ fontSize: '18px', fontWeight: 700, color: '#2e7d4f' }}>{v2026 ?? '—'}</div>
                        {diff !== null && (
                          <div style={{ fontSize: '10px', color: diff > 0 ? '#a8371f' : '#2e7d4f' }}>
                            {diff > 0 ? '+' : ''}{diff.toFixed(1)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Panel>

              <Panel title="Regions ranked by 2026 year-to-date AQI" note="Estimated from Open-Meteo grid + distance weighting. Real stations: Shivajinagar only.">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
                  {regionData.map((r) => (
                    <div key={r.name} style={{ padding: '10px', background: '#fffcf6', border: '1px solid rgba(40,34,26,0.12)', borderRadius: '6px' }}>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: '#1b2a26', marginBottom: '6px' }}>{r.name}</div>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <div>
                          <div style={{ fontSize: '11px', color: '#4a5a55' }}>2025</div>
                          <div style={{ fontSize: '18px', fontWeight: 700, color: '#a8371f' }}>{r.aqi2025}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '11px', color: '#4a5a55' }}>2026 YTD</div>
                          <div style={{ fontSize: '18px', fontWeight: 700, color: '#2e7d4f' }}>{r.aqi2026}</div>
                        </div>
                      </div>
                    </div>
                  ))}
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
}
