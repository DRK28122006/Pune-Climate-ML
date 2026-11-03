/**
 * Typed client for the Pune Climate backend API.
 *
 * In development the Vite dev server proxies `/api` to the Express backend.
 * In production (Vercel) `/api` is served by the serverless function.
 */
export type BackendAssessment = {
  id: string;
  projectName: string;
  location: string;
  projectType: string;
  climateScore: number;
  impactScore: number;
  status: string;
  heatRisk: number;
  floodRisk: number;
  carbonImpact: number;
  greenCoverScore: number;
  vegetation: number;
  impervious: number;
  water: number;
  lst: number;
  ndvi: number;
  ndbi: number;
  ndwi: number;
  elevation: number;
  slope: number;
  createdAt: string;
};

export type BackendOptimization = {
  baseline: BackendAssessment;
  optimized: BackendAssessment;
  recommendations: Array<{
    id: string;
    icon: string;
    title: string;
    description: string;
    current: string;
    proposed: string;
    impact: number;
    target: string;
  }>;
  scenario?: unknown;
};

const API_ROOT = import.meta.env.VITE_API_URL || '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function createAssessment(payload: {
  name: string;
  type: string;
  organization?: string;
  description?: string;
  location: string;
  coordinates: { lat: number; lon: number };
  bufferM?: number;
  builtUpAreaSqm?: number;
  materials?: Record<string, number>;
  mlOutput?: unknown;
}): Promise<{ assessment: BackendAssessment & { id: string }; optimization: BackendOptimization }> {
  return request('/assessments?includeOptimization=true', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function optimizeAssessment(id: string): Promise<BackendOptimization> {
  return request(`/assessments/${id}/optimize`, { method: 'POST' });
}

export async function listAssessments(): Promise<{ items: BackendAssessment[]; count: number }> {
  return request('/assessments');
}

export async function getAssessment(id: string): Promise<BackendAssessment> {
  return request(`/assessments/${id}`);
}

export type ScoreResult = {
  source: string;
  mode: string;
  ward: number | null;
  score: {
    impact_score: number | null;
    climate_score: number | null;
    risk_band: string | null;
    evidence_status: string;
    decision_grade: boolean;
    factors: Record<string, { score: number | null; status?: string; reason?: string }>;
    recommendations: Array<{ title?: string; impact?: number; target?: string; description?: string }>;
  };
  recommendations: Array<{ title?: string; impact?: number; target?: string; description?: string }>;
  canopy: { canopy_cover_pct?: number; census_reliable_for_this_site?: boolean; total_trees?: number } | null;
  indicators: Record<string, unknown>;
  satellite_cube_available: boolean;
};

export async function scoreProposal(payload: {
  ward?: number;
  coordinates?: { lat: number; lon: number };
  builtUpAreaSqm: number;
  plotAreaSqm: number;
  materials?: Array<{ name: string; quantityKg: number }>;
  storeys?: number;
  projectType?: string;
  impervious?: number;
  vegetation?: number;
  water?: number;
  slope?: number;
}): Promise<ScoreResult> {
  return request('/score', {
    method: 'POST',
    body: JSON.stringify({ ...payload, epoch: 2024 }),
  });
}

export async function narrateAssessment(assessment: unknown, question: string): Promise<{ text: string; source: string }> {
  return request('/narrate', {
    method: 'POST',
    body: JSON.stringify({ assessment, question }),
  });
}

export type WaqiStation = {
  station: string;
  city: string;
  geo: [number, number] | null;
  aqi: number;
  dominant: string | null;
  iaqi: Record<string, { v: number }>;
  time: string | null;
  iso: string | null;
  attributions: Array<{ name: string; url: string }>;
  forecast: Record<string, Array<{ avg: number; day: string; max: number; min: number }>>;
};

export type AirQualityData = {
  source: string;
  stations: WaqiStation[];
  unavailable?: boolean;
  reason?: string;
  hourly: number[];
  daily: number[];
  aqi: number;
  city: string;
  dominant: string | null;
  iaqi: Record<string, { v: number }>;
  time: string | null;
  iso: string | null;
  attributions: Array<{ name: string; url: string }>;
  forecast: Record<string, Array<{ avg: number; day: string; max: number; min: number }>>;
};

export async function getAirQuality(): Promise<AirQualityData> {
  const data = await request('/air-quality', { method: 'GET' }) as any;
  if (data.unavailable) {
    return {
      source: 'waqi',
      stations: [],
      unavailable: true,
      reason: data.reason,
      hourly: [],
      daily: [],
      aqi: 0,
      city: '',
      dominant: '',
      iaqi: {},
      time: null,
      iso: null,
      attributions: [],
      forecast: {},
    };
  }

  const stations = (data.stations || []) as WaqiStation[];
  // Use first station with data as primary
  const primary = stations.length > 0 ? stations[0] : null;

  const aqi = primary?.aqi ?? 0;
  const city = primary?.city ?? 'Pune';
  const dominant = primary?.dominant ?? '';
  const iaqi = primary?.iaqi ?? {};
  const time = primary?.time ?? null;
  const iso = primary?.iso ?? null;
  const attributions = primary?.attributions ?? [];
  const forecast = primary?.forecast ?? {};

  // Build an hourly series from current AQI
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

  return {
    source: 'waqi',
    stations,
    hourly,
    daily,
    aqi,
    city,
    dominant,
    iaqi,
    time,
    iso,
    attributions,
    forecast,
    unavailable: false,
  };
}

export { API_ROOT };
