import crypto from "node:crypto";
import { explainScore, scoreAssessment } from "../domain/scoring.js";
import { getMlOutput } from "./mlService.js";

export function assessDataQuality(input, mlOutput) {
  const materialCount = Object.keys(input.materials || {}).length;
  // "request" payloads are slider-derived scenarios, not measured observations.
  const measuredMl = ["gee-segformer"].includes(mlOutput.source);
  let completeness = 20;
  if (input.coordinates) completeness += 15;
  completeness += measuredMl ? 30 : 10;
  if (input.builtUpAreaSqm) completeness += 15;
  if (materialCount) completeness += 20;
  const assumptions = [];
  if (!input.coordinates) assumptions.push("Default Pune coordinates are used by fixture mode.");
  if (!measuredMl) assumptions.push("Spatial indicators are development fixtures, not measured observations.");
  if (!materialCount) assumptions.push("No material quantities were supplied; carbon impact is a lower-bound estimate.");
  return {
    completeness,
    confidence: completeness >= 80 ? "high" : completeness >= 50 ? "medium" : "low",
    source: measuredMl ? "measured-or-supplied" : "estimated",
    assumptions,
  };
}

export function buildProject(input, mlOutput, existing = {}, ownerId = existing.ownerId) {
  const scoring = scoreAssessment({ mlOutput, materials: input.materials, builtUpAreaSqm: input.builtUpAreaSqm });
  return {
    ...existing,
    id: existing.id || crypto.randomUUID(),
    ownerId,
    input,
    mlOutput,
    scoring,
    explanation: explainScore(scoring),
    dataQuality: assessDataQuality(input, mlOutput),
    createdAt: existing.createdAt || new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

export async function createAssessment({ input, ownerId, config, store, notificationService }) {
  const mlOutput = await getMlOutput(input, config);
  const project = buildProject(input, mlOutput, {}, ownerId);
  await store.saveAssessment(project);
  if (notificationService && ownerId) {
    try {
      await notificationService.create({
        userId: ownerId,
        title: "Climate assessment completed",
        message: `${input.name} has been scored at ${project.scoring.climateScore}/100.`,
        channels: ["in_app"],
        metadata: { assessmentId: project.id },
      });
    } catch (error) {
      // Notifications are best-effort; they must not fail an assessment.
      console.warn("Assessment notification skipped:", error.message);
    }
  }
  return project;
}
