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
    recommendations: Array<{
      title?: string;
      impact?: number;
      target?: string;
      description?: string;
      id?: string;
      action?: string;
      delta?: {
        impact_before?: number;
        impact_after?: number;
        impact_delta?: number;
        climate_before?: number;
        climate_after?: number;
        factors?: Record<string, { before?: number; after?: number; delta?: number }>;
      };
    }>;
  };
  recommendations: Array<{
      title?: string;
      impact?: number;
      target?: string;
      description?: string;
      id?: string;
      action?: string;
      delta?: {
        impact_before?: number;
        impact_after?: number;
        impact_delta?: number;
        climate_before?: number;
        climate_after?: number;
        factors?: Record<string, { before?: number; after?: number; delta?: number }>;
      };
    }>;
  canopy: {
    canopy_cover_pct?: number;
    canopy_cover_pct_proposed?: number;
    census_reliable_for_this_site?: boolean;
    total_trees?: number;
    tree_canopy_m2_before?: number;
    tree_canopy_m2_after?: number;
    tree_canopy_m2_lost?: number;
    action_counts?: Record<string, number>;
    rare_trees_in_site?: number;
    rare_trees_at_risk?: number;
    dead_trees_removed?: number;
    compensatory_required?: { low?: number; high?: number };
    compensatory_basis?: string;
    always_preserve_count?: number;
    always_preserve_canopy_m2?: number;
    compensatory_species_mix?: Record<string, number> | string[];
    decisions?: unknown[];
    census_coverage?: string;
  } | null;
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

export type AssistantReply = {
  reply: string;
  draft: Record<string, unknown>;
  phase: 'collecting' | 'ready' | 'confirmed';
  missing?: string[];
  unknownMaterials?: string[];
  source: 'groq' | 'gemini' | 'fallback' | 'error';
  reason?: string;
};

export async function assistantReply(payload: {
  messages: { role: 'user' | 'assistant'; text: string }[];
  draft: unknown;
  phase: string;
  assessment: unknown | null;
}): Promise<AssistantReply> {
  return request('/assistant', {
    method: 'POST',
    body: JSON.stringify(payload),
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
  historical?: {
    monthly_2025: Record<string, number>;
    monthly_2026: Record<string, number>;
    yearly_2025: number | null;
    yearly_2026: number | null;
    current_month_daily: Record<string, number>;
    prev_month_daily: Record<string, number>;
  };
};

export type AirQualityData = {
  source: string;
  stations: WaqiStation[];
  unavailable?: boolean;
  reason?: string;
  cache?: { hit?: boolean; stale?: boolean; age_s?: number | null; reason?: string };
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
  historical?: {
    monthly_2025: Record<string, number>;
    monthly_2026: Record<string, number>;
    yearly_2025: number | null;
    yearly_2026: number | null;
    current_month_daily: Record<string, number>;
    prev_month_daily: Record<string, number>;
  };
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
  // Backend mirrors the primary reading at the top level — use it.
  const primary = stations.length > 0 ? stations[0] : null;

  return {
    source: data.source ?? 'open-meteo-air-quality',
    stations,
    cache: data.cache,
    hourly: data.hourly ?? [],
    daily: data.daily ?? [],
    aqi: data.aqi ?? primary?.aqi ?? 0,
    city: data.city ?? primary?.city ?? 'Pune',
    dominant: data.dominant ?? primary?.dominant ?? null,
    iaqi: data.iaqi ?? primary?.iaqi ?? {},
    time: data.time ?? primary?.time ?? null,
    iso: data.iso ?? primary?.iso ?? null,
    attributions: data.attributions ?? primary?.attributions ?? [],
    forecast: primary?.forecast ?? {},
    historical: data.historical,
    unavailable: false,
  };
}

export { API_ROOT };
