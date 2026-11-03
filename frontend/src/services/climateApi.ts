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

export { API_ROOT };
