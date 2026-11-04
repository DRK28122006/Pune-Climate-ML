import { Link } from 'react-router-dom';
import { ArrowRight, CloudRain, Thermometer, Trees, Wind, SlidersHorizontal } from 'lucide-react';
import DataGate from '../../components/DataGate';
import { EmptyState, MetricCard, PageHeader, Panel, Pill } from '../../components/ui';
import { getCityOverview } from '../../data/api';
import { getAirQuality } from '../../services/climateApi';
import { CANOPY_TARGET_PCT } from '../../config';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';

const LINKS = [
  { to: '/dashboard/heat', icon: Thermometer, title: 'Heat', text: 'Rank wards by surface temperature and tree cover.' },
  { to: '/dashboard/air-quality', icon: Wind, title: 'Air Quality', text: 'Live AQI and 2025–2026 PM2.5 comparison from Open-Meteo.' },
  { to: '/dashboard/green-cover', icon: Trees, title: 'Green Cover', text: 'Satellite-measured vegetation against the target, ward by ward.' },
  { to: '/dashboard/flood-risk', icon: CloudRain, title: 'Flood Risk', text: 'Ward exposure under a chosen rainfall, ranked by measured flood factor.' },
  { to: '/dashboard/scenario-planner', icon: SlidersHorizontal, title: 'Scenario Planner', text: 'Rescore the evaluated proposal with material swaps and ward relocation.' },
];

export default function Overview() {
  const state = useAsync(getCityOverview);
  const aq = useAsync(getAirQuality);
  const { result } = usePlan();
  const aqi = aq.status === 'ready' && !aq.data.unavailable ? aq.data.aqi : null;

  return (
    <>
      <PageHeader
        eyebrow="Pune · prototype city"
        title="Overview"
        lede="A single view of heat, air, green cover and flood exposure, with the places that need attention first."
        badge={<Pill tone="low">Satellite cube</Pill>}
      />

      <DataGate state={state}>
        {(o) => (
          <>
            <div className="metrics">
              <MetricCard label="Night surface temp" value={o.surfaceTempC.toFixed(1)} unit="°C" note="Night LST, city average (satellite cube)" />
              <MetricCard label="Air quality index" value={aqi != null ? String(aqi) : aq.status === 'loading' ? '…' : 'UNAVAILABLE'} unit={aqi != null ? 'AQI' : ''} note="Open-Meteo, Pune grid point" />
              <MetricCard label="Vegetation cover" value={o.canopyPct.toFixed(1)} unit="%" pill={{ tone: 'med', text: `${(CANOPY_TARGET_PCT - o.canopyPct).toFixed(1)} pts below target` }} note={`Satellite-measured city average. Target is ${CANOPY_TARGET_PCT}%`} />
              <MetricCard label="Flood-prone wards" value={String(o.floodWards)} unit={`of ${o.totalWards}`} pill={{ tone: 'high', text: `${o.highRiskWards} high risk` }} note="Flood factor ≥ 50 (satellite cube)" />
            </div>

            <div className="two-col">
              <Panel title="Priorities" note="Computed from the measured ward scores (satellite cube). Highest/lowest impact wards and data coverage.">
                <ul className="prio">
                  {o.priorities.map((p) => (
                    <li key={p.area}>
                      <Pill tone={p.level} />
                      <div><b>{p.area}</b><p>{p.text}</p></div>
                    </li>
                  ))}
                </ul>
              </Panel>

              <Panel title="Your evaluated plan">
                {result ? (
                  <div className="plansum">
                    <p><b>Plan scored by ML pipeline</b> · {result.ward ? `Ward ${result.ward}` : 'site'}</p>
                    <dl className="mlist">
                      <div><dt>Impact score</dt><dd>{result.score.impact_score ?? '—'}/100</dd></div>
                      <div><dt>Climate score</dt><dd>{result.score.climate_score ?? '—'}/100</dd></div>
                      <div><dt>Evidence</dt><dd>{result.score.evidence_status ?? '—'}</dd></div>
                    </dl>
                    <p className="note">Computed by the ML pipeline (satellite cube + census tree data). Ward figures on this page come from the same cube.</p>
                    <div className="row-actions">
                      <Link to="/assess" className="btn btn--secondary">Re-run evaluation</Link>
                      <Link to="/dashboard/engine" className="btn btn--secondary">Open Engine</Link>
                      <Link to="/dashboard/scenario-planner" className="btn btn--ghost">Scenario Planner</Link>
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    title="No plan evaluated yet"
                    text="Evaluate a plan to see how an optimized outcome compares with today."
                    action={<Link to="/assess" className="btn btn--primary">Evaluate a plan</Link>}
                  />
                )}
              </Panel>
            </div>
          </>
        )}
      </DataGate>

      <h2 className="h2">Explore</h2>
      <div className="linkgrid">
        {LINKS.map(({ to, icon: Icon, title, text }) => (
          <Link key={to} to={to} className="linkcard">
            <Icon size={22} aria-hidden="true" />
            <span><b>{title}</b><small>{text}</small></span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
        ))}
      </div>
      <p className="note">Source and last-updated time will appear here once live data is connected.</p>
    </>
  );
}
