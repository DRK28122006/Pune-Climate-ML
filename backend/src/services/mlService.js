import { spawn } from "node:child_process";
import path from "node:path";

function seededMetric(text, min, max) {
  let hash = 2166136261;
  for (const char of text) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return min + ((hash >>> 0) % 1000) / 1000 * (max - min);
}

function fixtureOutput(input) {
  const seed = `${input.location}|${input.coordinates?.lat}|${input.coordinates?.lon}`;
  const water = seededMetric(`${seed}:water`, 2, 7);
  const vegetation = seededMetric(`${seed}:vegetation`, 20, 38);
  const impervious = 100 - vegetation - water;
  return {
    project_location: {
      lat: input.coordinates?.lat ?? 18.559,
      lon: input.coordinates?.lon ?? 73.7868,
      buffer_m: input.bufferM || 500,
    },
    landcover: {
      vegetation_pct: Number(vegetation.toFixed(2)),
      impervious_pct: Number(impervious.toFixed(2)),
      water_pct: Number(water.toFixed(2)),
    },
    ndvi_mean: Number(seededMetric(`${seed}:ndvi`, 0.2, 0.48).toFixed(3)),
    ndbi_mean: Number(seededMetric(`${seed}:ndbi`, 0.35, 0.67).toFixed(3)),
    ndwi_mean: Number(seededMetric(`${seed}:ndwi`, 0.03, 0.14).toFixed(3)),
    lst_celsius_mean: Number(seededMetric(`${seed}:lst`, 32, 37).toFixed(2)),
    slope_deg_mean: Number(seededMetric(`${seed}:slope`, 1.5, 6).toFixed(2)),
    elevation_m_mean: Number(seededMetric(`${seed}:elevation`, 540, 610).toFixed(1)),
    source: "development-fixture",
  };
}

function validateMlOutput(output) {
  const cover = output?.landcover;
  const values = [cover?.vegetation_pct, cover?.impervious_pct, cover?.water_pct];
  if (values.some((value) => !Number.isFinite(value) || value < 0 || value > 100)) {
    throw new Error("ML output contains invalid land-cover percentages");
  }
  const total = values.reduce((sum, value) => sum + value, 0);
  if (Math.abs(total - 100) > 1) throw new Error("ML land-cover percentages must total 100 (+/- 1)");
  if (!Number.isFinite(output.lst_celsius_mean)) throw new Error("ML output is missing LST");
  return output;
}

function runPython(input, config) {
  const bridge = path.join(config.backendRoot, "python", "ml_bridge.py");
  return new Promise((resolve, reject) => {
    const child = spawn(config.pythonCommand, [bridge], {
      cwd: config.repositoryRoot,
      env: process.env,
      shell: false,
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => child.kill(), 10 * 60 * 1000);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0) return reject(new Error(stderr.trim() || `ML process exited with code ${code}`));
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error("ML process returned invalid JSON")); }
    });
    child.stdin.end(JSON.stringify(input));
  });
}

export async function getMlOutput(input, config) {
  if (input.mlOutput) return validateMlOutput({ ...input.mlOutput, source: "request" });
  const output = config.mlMode === "python"
    ? await runPython(input, config)
    : fixtureOutput(input);
  return validateMlOutput(output);
}

const REJECTED_INPUT = /validation failed|could not be measured|is required|not in this deployment|cannot exceed|does not fall inside|must be/i;

export async function getScore(input, config) {
  // Scoring uses only baked artefacts (epoch cube, reference layers, tree
  // index) — no GEE, no model weights.
  //
  // There is deliberately no fixture fallback here. A fabricated score is
  // indistinguishable from a measured one once it reaches the UI, and this
  // project does not ship numbers it did not measure. Bridge failures surface
  // as 400 when the submission was rejected and 502 when the pipeline itself
  // is unavailable, so the reason reaches the officer.
  const scoreInput = {
    mode: "score",
    ward: input.ward,
    coordinates: input.coordinates,
    geometry: input.geometry,
    builtUpAreaSqm: input.builtUpAreaSqm,
    plotAreaSqm: input.plotAreaSqm,
    materials: input.materials,
    storeys: input.storeys,
    projectType: input.projectType,
    epoch: input.epoch || 2024,
    impervious: input.impervious,
    vegetation: input.vegetation,
    water: input.water,
    slope: input.slope,
  };
  try {
    return await runPython(scoreInput, config);
  } catch (error) {
    if (!error.status) {
      error.status = REJECTED_INPUT.test(error.message || "") ? 400 : 502;
    }
    throw error;
  }
}


export async function getAirQuality(config) {
  // Use Python bridge (Node fetch/HTTPS is broken in this env)
  const child = spawn(config.pythonCommand, [path.join(config.backendRoot, "python", "ml_bridge.py")], {
    cwd: config.repositoryRoot,
    env: process.env,
    shell: false,
    windowsHide: true,
  });
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => child.kill(), 30 * 1000);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0) return reject(new Error(stderr.trim() || `ML process exited with code ${code}`));
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error("ML process returned invalid JSON")); }
    });
    child.stdin.end(JSON.stringify({ mode: "air_quality" }));
  });
}

export async function narrateAssessment(assessment, question, config) {
  const child = spawn(config.pythonCommand, [path.join(config.backendRoot, "python", "narrate_bridge.py")], {
    cwd: config.repositoryRoot,
    env: process.env,
    shell: false,
    windowsHide: true,
  });
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => child.kill(), 60 * 1000);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0) return reject(new Error(stderr.trim() || `narrate exited with code ${code}`));
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error("narrate returned invalid JSON")); }
    });
    child.stdin.end(JSON.stringify({ assessment, question, role: "municipal_authority" }));
  });
}

export async function assistantChat({ messages, draft, phase, assessment }, config) {
  const child = spawn(config.pythonCommand, [path.join(config.backendRoot, "python", "assistant_bridge.py")], {
    cwd: config.repositoryRoot,
    env: process.env,
    shell: false,
    windowsHide: true,
  });
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => child.kill(), 90 * 1000);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0) return reject(new Error(stderr.trim() || `assistant exited with code ${code}`));
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error("assistant returned invalid JSON")); }
    });
    child.stdin.end(JSON.stringify({ messages: messages || [], draft: draft || {}, phase: phase || "collecting", assessment: assessment || null }));
  });
}
