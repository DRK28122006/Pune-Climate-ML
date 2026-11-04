/**
 * SAMPLE DATA ONLY.
 * These numbers come from the supplied layout prototype ("Growing Pune") and are
 * placeholders. They are not measurements or official Pune statistics.
 * Replace the functions in `api.ts` with real data sources; keep these types.
 */
import type { Metrics, Priority, SurfaceProfile } from '../types';

export interface Ward {
  id: string;
  name: string;
  tempC: number;
  canopyPct: number;
  priority: Priority;
  /** Position on the conceptual tile map. Not geographic. */
  col: number;
  row: number;
}

export interface Station {
  name: string;
  index: number;
}

export interface FloodArea {
  id: string;
  name: string;
  risk: Priority;
  households: number;
  pavedPct: number;
  action: string;
  wardId?: string;
  col: number;
  row: number;
}

export interface CityOverview {
  surfaceTempC: number;
  airIndex: number;
  canopyPct: number;
  floodWards: number;
  totalWards: number;
  highRiskWards: number;
  priorities: { level: Priority; area: string; text: string }[];
}

export const CITY_AVG_TEMP = 38.4;

export const cityOverview: CityOverview = {
  surfaceTempC: 38.4,
  airIndex: 142,
  canopyPct: 18.6,
  floodWards: 7,
  totalWards: 41,
  highRiskWards: 2,
  priorities: [
    { level: 'high', area: 'Hadapsar', text: 'Highest surface temperature (41.2°C) and lowest tree cover (9%). Largest gap to the canopy target.' },
    { level: 'high', area: 'Riverside, Deccan', text: 'Highest flood exposure, with about 4,200 households and 81% paved surface.' },
    { level: 'med', area: 'Katraj lake belt', text: 'Medium flood risk and 15% canopy. Lake-edge planting would help both.' },
  ],
};

/** City-level surface mix used by the Scenario Planner. The mix is an assumption. */
export const cityProfile: SurfaceProfile = { builtUpPct: 58, pavedPct: 46, canopyPct: 18.6 };

export const cityAnchor: Metrics = { canopyPct: 18.6, surfaceTempC: 38.4, runoffIndex: 60, airIndex: 142 };

export const wards: Ward[] = [
  { id: 'hadapsar', name: 'Hadapsar', tempC: 41.2, canopyPct: 9, priority: 'high', col: 2, row: 1 },
  { id: 'yerawada', name: 'Yerawada', tempC: 40.6, canopyPct: 11, priority: 'high', col: 2, row: 0 },
  { id: 'katraj', name: 'Katraj', tempC: 39.8, canopyPct: 15, priority: 'med', col: 1, row: 1 },
  { id: 'kothrud', name: 'Kothrud', tempC: 38.1, canopyPct: 21, priority: 'low', col: 0, row: 1 },
  { id: 'baner', name: 'Baner', tempC: 37.4, canopyPct: 26, priority: 'low', col: 0, row: 0 },
  { id: 'aundh', name: 'Aundh', tempC: 36.9, canopyPct: 19, priority: 'low', col: 1, row: 0 },
];

export const aqiHourly: number[] = [96, 92, 88, 85, 84, 90, 104, 128, 152, 166, 158, 146, 138, 132, 130, 136, 148, 162, 176, 182, 171, 152, 128, 110];
export const aqiDaily: number[] = [128, 134, 121, 149, 142, 118, 142];

export const stations: Station[] = [
  { name: 'Shivajinagar', index: 138 },
  { name: 'Katraj', index: 121 },
  { name: 'Hadapsar', index: 212 },
  { name: 'Pashan', index: 74 },
];

/** CPCB-style category bands used for labelling. */
export const AQI_BANDS = [
  { from: 0, to: 50, label: 'Good', tone: 'low' as Priority },
  { from: 50, to: 100, label: 'Satisfactory', tone: 'low' as Priority },
  { from: 100, to: 200, label: 'Moderate', tone: 'med' as Priority },
  { from: 200, to: 300, label: 'Poor', tone: 'high' as Priority },
];

export const floodAreas: FloodArea[] = [
  { id: 'riverside', name: 'Riverside, Deccan', risk: 'high', households: 4200, pavedPct: 81, action: 'Restore riverbank buffer', col: 0, row: 0 },
  { id: 'hadapsar-lowlands', name: 'Hadapsar lowlands', risk: 'high', households: 3650, pavedPct: 74, action: 'Permeable paving and bioswales', wardId: 'hadapsar', col: 2, row: 1 },
  { id: 'katraj-lake', name: 'Katraj lake belt', risk: 'med', households: 2100, pavedPct: 58, action: 'Lake-edge tree belt', wardId: 'katraj', col: 1, row: 1 },
  { id: 'kothrud-slopes', name: 'Kothrud slopes', risk: 'med', households: 1480, pavedPct: 63, action: 'Check stormwater drains', wardId: 'kothrud', col: 0, row: 1 },
  { id: 'baner-hills', name: 'Baner hills', risk: 'low', households: 620, pavedPct: 41, action: 'Protect existing tree cover', wardId: 'baner', col: 1, row: 0 },
];
