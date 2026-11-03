import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

const KEY = 'dishadharti.sidebar';

/**
 * Shared layout for every page after the landing page (assessment and dashboard).
 * It owns the single sidebar and its collapsed state, so both routes use the same
 * component and the state survives navigation between them.
 */
export default function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved !== null) return saved === '1';
    } catch {
      /* storage unavailable: fall through to the default */
    }
    // No saved choice: start collapsed on narrow screens so content keeps its room.
    return window.matchMedia('(max-width: 899px)').matches;
  });

  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem(KEY, c ? '0' : '1');
      } catch {
        /* storage unavailable: ignore */
      }
      return !c;
    });

  return (
    <div className={`shell${collapsed ? ' shell--collapsed' : ''}`}>
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div className="shell__main">
        <Outlet />
      </div>
    </div>
  );
}
