import { CloudRain, LayoutDashboard, SlidersHorizontal, Thermometer, Trees, Wind, type LucideIcon } from 'lucide-react';

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { path: 'overview', label: 'Overview', icon: LayoutDashboard },
  { path: 'heat', label: 'Heat', icon: Thermometer },
  { path: 'air-quality', label: 'Air Quality', icon: Wind },
  { path: 'green-cover', label: 'Green Cover', icon: Trees },
  { path: 'flood-risk', label: 'Flood Risk', icon: CloudRain },
  { path: 'scenario-planner', label: 'Scenario Planner', icon: SlidersHorizontal },
];
