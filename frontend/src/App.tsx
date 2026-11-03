import { useEffect } from 'react';
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Atmosphere from './components/Atmosphere';
import AppShell from './components/AppShell';
import { PlanProvider } from './state/PlanContext';
import Landing from './pages/Landing';
import Assessment from './pages/Assessment';
import DashboardLayout from './pages/dashboard/DashboardLayout';
import Overview from './pages/dashboard/Overview';
import Heat from './pages/dashboard/Heat';
import AirQuality from './pages/dashboard/AirQuality';
import GreenCover from './pages/dashboard/GreenCover';
import FloodRisk from './pages/dashboard/FloodRisk';
import ScenarioPlanner from './pages/dashboard/ScenarioPlanner';
import { PageHeader } from './components/ui';
import { useAtmosphere } from './scene/atmosphereStore';

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function NotFound() {
  useAtmosphere(0);
  return (
    <main className="plain">
      <PageHeader title="Page not found" lede="That address does not match a page in this prototype." />
      <p>
        <Link to="/">Back to the start</Link> or <Link to="/dashboard/overview">open the dashboard</Link>.
      </p>
    </main>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <PlanProvider>
        <a className="skip" href="#main">Skip to content</a>
        <Atmosphere />
        <ScrollToTop />
        <Routes>
          <Route path="/" element={<Landing />} />
          {/* One shared shell (and one sidebar) for the assessment and every dashboard page */}
          <Route element={<AppShell />}>
            <Route path="/assess" element={<Assessment />} />
            <Route path="/dashboard" element={<DashboardLayout />}>
              <Route index element={<Navigate to="overview" replace />} />
              <Route path="overview" element={<Overview />} />
              <Route path="heat" element={<Heat />} />
              <Route path="air-quality" element={<AirQuality />} />
              <Route path="green-cover" element={<GreenCover />} />
              <Route path="flood-risk" element={<FloodRisk />} />
              <Route path="scenario-planner" element={<ScenarioPlanner />} />
            </Route>
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </PlanProvider>
    </BrowserRouter>
  );
}
