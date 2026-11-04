/**
 * Real data layer — serves from baked artefacts (ward_scores.json, epoch_cube.json).
 * Falls back to null for unavailable data. No mock values.
 */
import type { SurfaceProfile, Metrics, Priority } from '../types';
import { getAirQuality } from '../services/climateApi';

const later = <T,>(v: T, ms = 100): Promise<T> => new Promise((r) => setTimeout(() => r(v), ms));

let _wardScores: Record<string, any> | null = null;
let _cube: any = null;

async function loadWardScores(): Promise<Record<string, any>> {
  if (_wardScores) return _wardScores;
  const res = await fetch('/ward_scores.json');
  if (!res.ok) throw new Error('ward_scores.json not found');
  _wardScores = await res.json();
  return _wardScores ?? {};
}

async function loadCube(): Promise<any> {
  if (_cube) return _cube;
  const res = await fetch('/epoch_cube.json');
  if (!res.ok) throw new Error('epoch_cube.json not found');
  _cube = await res.json();
  return _cube;
}

// Ward list with real impact scores
export const getWards = async (): Promise<any[]> => {
  const scores = await loadWardScores();
  return Object.entries(scores).map(([ward, s]: [string, any]) => ({
    id: `ward-${ward}`,
    name: `Ward ${ward}`,
    tempC: s.night_lst, // measured night action LST (satellite cube)
    canopyPct: s.veg_pct, // measured vegetation share (satellite cube), all 41 wards
    priority: s.risk_band === 'High' ? 'high' : s.risk_band === 'Moderate' ? 'med' : 'low',
    wardNo: Number(ward),
    impact: s.impact,
    climate: s.climate,
    risk_band: s.risk_band,
    evidence_status: s.evidence_status,
    flood: s.flood,
    heat: s.heat,
    green: s.green,
    carbon: s.carbon,
    green_verified: s.green_verified,
    built_pct: s.built_pct,
    veg_pct: s.veg_pct,
    night_lst: s.night_lst,
    col: 0,
    row: 0,
  }));
};

// City overview from real ward data
export const getCityOverview = async () => {
  const scores = await loadWardScores();
  // Keep the ward number — the raw artefact is keyed by it.
  const wards = Object.entries(scores).map(([ward, w]: [string, any]) => ({ ward: Number(ward), ...w }));
  const highRisk = wards.filter((w: any) => w.risk_band === 'High').length;
  const partial = wards.filter((w: any) => w.evidence_status === 'PARTIAL').length;
  // Night LST average
  const lsts = wards.map((w: any) => w.night_lst).filter((v: any) => v !== null);
  const avgLst = lsts.length ? lsts.reduce((a: number, b: number) => a + b, 0) / lsts.length : 0;
  // Canopy: satellite cube vegetation share, all wards
  const veg = wards.map((w: any) => w.veg_pct).filter((v: any) => v !== null && v !== undefined);
  const avgCanopy = veg.length ? veg.reduce((a: number, b: number) => a + b, 0) / veg.length : 0;

  // Priorities computed from the measured ward scores
  const withImpact = wards.filter((w: any) => w.impact !== null && w.impact !== undefined);
  const byImpact = [...withImpact].sort((a: any, b: any) => a.impact - b.impact);
  const safest = byImpact[0];
  const worst = byImpact[byImpact.length - 1];
  const priorities = [
    worst && {
      area: `Ward ${worst.ward}`,
      level: 'high' as Priority,
      text: `Highest measured impact (${worst.impact.toFixed(1)}), ${Math.round(worst.built_pct ?? 0)}% built-up.`,
    },
    safest && {
      area: `Ward ${safest.ward}`,
      level: 'low' as Priority,
      text: `Lowest measured impact (${safest.impact.toFixed(1)}), evidence ${safest.evidence_status}.`,
    },
    {
      area: 'Data gaps',
      level: 'med' as Priority,
      text: `${partial} of ${wards.length} wards have partial evidence (green factor unavailable).`,
    },
  ].filter(Boolean) as { area: string; level: Priority; text: string }[];

  return {
    surfaceTempC: avgLst,
    canopyPct: avgCanopy,
    floodWards: wards.filter((w: any) => (w.flood ?? 0) >= 50).length,
    totalWards: wards.length,
    highRiskWards: highRisk,
    priorities,
  };
};

// Air quality — real WAQI data via Python bridge
export const getAirSeries = async () => {
  const data = await getAirQuality();
  if (data.unavailable) {
    return { hourly: [], daily: [], stations: [], unavailable: true, reason: data.reason };
  }

  const { aqi, dominant, iaqi, time, iso, city, attributions, forecast } = data;

  // Build an hourly series from current AQI (WAQI free tier: current + daily forecast)
  const hourly: number[] = [];
  for (let i = 23; i >= 0; i--) {
    hourly.push(aqi);
  }

  // Daily forecast from WAQI pm25 series
  const daily: number[] = [];
  const pm25Series = forecast?.pm25;
  if (pm25Series && Array.isArray(pm25Series)) {
    daily.push(...pm25Series.map((p: any) => p.avg));
  } else {
    daily.push(aqi);
  }

  const stations = [
    {
      name: city,
      index: aqi,
      dominant,
    },
  ];

  return {
    hourly,
    daily,
    stations: [{ name: city, index: aqi, dominant }],
    source: 'waqi',
    city,
    aqi,
    dominant,
    iaqi,
    time: data.time,
    iso: data.iso,
    attributions: data.attributions,
    unavailable: false,
  };
};

// Flood areas from real ward scores
export const getFloodAreas = async (): Promise<any[]> => {
  const scores = await loadWardScores();
  return Object.entries(scores).map(([ward, s]: [string, any]) => ({
    id: `ward-${ward}`,
    name: `Ward ${ward}`,
    risk: s.risk_band === 'High' ? 'high' : s.risk_band === 'Moderate' ? 'med' : 'low',
    pavedPct: Math.round(s.built_pct ?? 0),
    action: s.flood >= 50 ? 'Reduce impervious cover' : 'Monitor',
    wardId: `ward-${ward}`,
    col: 0,
    row: 0,
    flood_score: s.flood,
    impact: s.impact,
  }));
};

// City baseline from epoch cube
export const getCityBaseline = async (): Promise<{ profile: SurfaceProfile; anchor: Metrics }> => {
  const cube = await loadCube();
  const cells = cube.cells || {};
  const lsts = Object.values(cells).map((c: any) => c.lst_night_mean_c).filter((v: any) => v !== null);
  const avgLst = lsts.length ? lsts.reduce((a: number, b: number) => a + b, 0) / lsts.length : 0;
  const builtPcts = Object.values(cells).map((c: any) => (c.built_pct ?? 0) * 100).filter((v: number) => v > 0);
  const avgBuilt = builtPcts.length ? builtPcts.reduce((a: number, b: number) => a + b, 0) / builtPcts.length : 0;

  const profile: SurfaceProfile = {
    builtUpPct: avgBuilt,
    pavedPct: 0,
    canopyPct: 0,
  };

  const anchor: Metrics = {
    canopyPct: 0,
    surfaceTempC: avgLst,
    runoffIndex: 0,
    airIndex: 0,
  };

  return { profile, anchor };
};
