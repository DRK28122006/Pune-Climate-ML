import { NavLink } from 'react-router-dom';
import { ClipboardCheck, House, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { NAV_ITEMS } from '../nav';
import { LogoMark } from './Logo';
import { APP_NAME } from '../config';

interface Props {
  collapsed: boolean;
  onToggle: () => void;
}

function Item({ to, label, collapsed, children }: { to: string; label: string; collapsed: boolean; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => `side__link${isActive ? ' is-active' : ''}`}
      aria-label={collapsed ? label : undefined}
      data-tip={collapsed ? label : undefined}
    >
      {children}
      <span className="side__text">{label}</span>
    </NavLink>
  );
}

export default function Sidebar({ collapsed, onToggle }: Props) {
  return (
    <aside className={`side${collapsed ? ' is-collapsed' : ''}`} id="sidebar">
      <div className="side__brand">
        <LogoMark size={38} tile />
        <span className="side__text side__name">{APP_NAME}</span>
      </div>

      <nav aria-label="Dashboard pages" className="side__nav">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <Item key={path} to={`/dashboard/${path}`} label={label} collapsed={collapsed}>
            <Icon size={20} aria-hidden="true" />
          </Item>
        ))}
      </nav>

      <div className="side__foot">
        <Item to="/assess" label="Evaluate a plan" collapsed={collapsed}>
          <ClipboardCheck size={20} aria-hidden="true" />
        </Item>
        <Item to="/" label="Home" collapsed={collapsed}>
          <House size={20} aria-hidden="true" />
        </Item>
        <button
          type="button"
          className="side__link side__toggle"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-controls="sidebar"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          data-tip={collapsed ? 'Expand sidebar' : undefined}
        >
          {collapsed ? <PanelLeftOpen size={20} aria-hidden="true" /> : <PanelLeftClose size={20} aria-hidden="true" />}
          <span className="side__text">Collapse</span>
        </button>
      </div>
    </aside>
  );
}
