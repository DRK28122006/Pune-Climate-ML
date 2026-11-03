import { useEffect } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { DemoBadge } from '../../components/ui';
import { usePlan } from '../../state/PlanContext';
import { atmosphere } from '../../scene/atmosphereStore';
import { PAGE_INTENSITY } from '../../config';

/**
 * Dashboard content wrapper. The sidebar now lives in AppShell.
 * Background greenness stays at zero until an optimization has succeeded,
 * then each page uses its own intensity.
 */
export default function DashboardLayout() {
  const { pathname } = useLocation();
  const { result } = usePlan();

  const slug = pathname.split('/')[2] ?? 'overview';
  const intensity = result ? PAGE_INTENSITY[slug] ?? 0.5 : 0;
  useEffect(() => {
    atmosphere.setTarget(intensity);
    atmosphere.setWide(false);
  }, [intensity]);

  return (
    <>
      <div className="topbar">
        <span className="topbar__city">Pune · prototype city</span>
        <span className="topbar__plan">
          {result ? (
            <>
              Plan: <b>{result.inputs.planName}</b> <DemoBadge label="Demo result" />
            </>
          ) : (
            <>
              No plan evaluated yet. <Link to="/assess">Evaluate a plan</Link>
            </>
          )}
        </span>
      </div>
      <main id="main" className="shell__content" key={slug}>
        <Outlet />
      </main>
    </>
  );
}
