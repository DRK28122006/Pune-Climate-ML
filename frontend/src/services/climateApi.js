const API_ROOT = import.meta.env.VITE_API_URL || "/api/v1";
const STORAGE_KEY = "pune-climate-latest-assessment";
const OPTIMIZATION_KEY = "pune-climate-latest-optimization";

async function request(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${response.status})`);
  }
  return response.json();
}

function remember(assessment) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(assessment));
  return assessment;
}

export async function getAssessment() {
  const cached = sessionStorage.getItem(STORAGE_KEY);
  if (cached) return JSON.parse(cached);
  const result = await request("/assessments");
  return result.items?.length ? remember(result.items[0]) : null;
}

export async function createAssessment(payload) {
  const result = await request("/assessments?includeOptimization=true", {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      coordinates: { lat: 18.559, lon: 73.7868 },
      builtUpAreaSqm: 10000,
    }),
  });
  sessionStorage.setItem(OPTIMIZATION_KEY, JSON.stringify(result.optimization));
  return remember(result.assessment);
}

export async function optimizeAssessment() {
  const cached = sessionStorage.getItem(OPTIMIZATION_KEY);
  if (cached) return JSON.parse(cached);
  const assessment = await getAssessment();
  if (!assessment?.id) throw new Error("Create an assessment before optimizing it.");
  return request(`/assessments/${assessment.id}/optimize`, { method: "POST" });
}

export function getReportUrl(id) {
  return `${API_ROOT}/assessments/${id}/report`;
}
