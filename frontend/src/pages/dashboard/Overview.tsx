import { Link } from 'react-router-dom';
import { ArrowRight, CloudRain, Thermometer, Trees, Wind, SlidersHorizontal } from 'lucide-react';
import DataGate from '../../components/DataGate';
import { DemoBadge, EmptyState, MetricCard, PageHeader, Panel, Pill } from '../../components/ui';
import { getCityOverview } from '../../data/api';
import { CANOPY_TARGET_PCT } from '../../config';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';

const LINKS = [
  { to: '/dashboard/heat', icon: Thermometer, title: 'Heat', text: 'Rank wards by surface temperature and tree cover.' },
  { to: '/dashboard/air-quality', icon: Wind, title: 'Air Quality', text: 'Hourly and weekly air index with station readings.' },
  { to: '/dashboard/green-cover', icon: Trees, title: 'Green Cover', text: 'Canopy against the target, ward by ward.' },
  { to: '/dashboard/flood-risk', icon: CloudRain, title: 'Flood Risk', text: 'Exposed households under a chosen rainfall.' },
  { to: '/dashboard/scenario-planner', icon: SlidersHorizontal, title: 'Scenario Planner', text: 'Compare planting and cool-roof scenarios.' },
];

export default function Overview() {
  const state = useAsync(getCityOverview);
  const { result } = usePlan();

  return (
    <>
      <PageHeader
        eyebrow="Pune · prototype city"
        title="Overview"
        lede="A single view of heat, air, green cover and flood exposure, with the places that need attention first."
        badge={<DemoBadge />}
      />

      <DataGate state={state}>
        {(o) => (
          <>
            <div className="metrics">
              <MetricCard label="Surface temperature" value={o.surfaceTempC.toFixed(1)} unit="°C" pill={{ tone: 'high', text: 'Above 36°C threshold' }} note="City average, afternoon" />
              <MetricCard label="Air quality index" value={String(o.airIndex)} unit="AQI" pill={{ tone: 'med', text: 'Moderate' }} note="City average, CPCB-style scale" />
              <MetricCard label="Tree canopy" value={o.canopyPct.toFixed(1)} unit="%" pill={{ tone: 'med', text: `${(CANOPY_TARGET_PCT - o.canopyPct).toFixed(1)} points below target` }} note={`Target is ${CANOPY_TARGET_PCT}%`} />
              <MetricCard label="Flood-prone wards" value={String(o.floodWards)} unit={`of ${o.totalWards}`} pill={{ tone: 'high', text: `${o.highRiskWards} high risk` }} note="Flagged in the sample season" />
            </div>

            <div className="two-col">
              <Panel title="Priorities this season" note="Sample content from the prototype. Replace with ranked output from real data.">
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
                    <p><b>{result.inputs.planName}</b> · {result.inputs.focusArea}</p>
                    <dl className="mlist">
                      <div><dt>Canopy</dt><dd>{result.before.canopyPct.toFixed(1)}% → {result.after.canopyPct.toFixed(1)}%</dd></div>
                      <div><dt>Surface temperature</dt><dd>{result.before.surfaceTempC.toFixed(1)} → {result.after.surfaceTempC.toFixed(1)}°C</dd></div>
                      <div><dt>Runoff index</dt><dd>{result.before.runoffIndex.toFixed(1)} → {result.after.runoffIndex.toFixed(1)}</dd></div>
                    </dl>
                    <p className="note">Demonstration result for the plan area only. It does not change the city figures on this page.</p>
                    <div className="row-actions">
                      <Link to="/assess" className="btn btn--secondary">Review or re-run</Link>
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
