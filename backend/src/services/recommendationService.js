import { scoreAssessment } from "../domain/scoring.js";

const round = (value) => Number(value.toFixed(1));

function frontendAssessment(project) {
  const { input, mlOutput, scoring } = project;
  return {
    id: project.id,
    projectName: input.name,
    location: input.location,
    projectType: input.type,
    climateScore: scoring.climateScore,
    impactScore: scoring.impactScore,
    status: scoring.riskLevel,
    heatRisk: scoring.breakdown.heat.score,
    floodRisk: scoring.breakdown.flood.score,
    carbonImpact: scoring.breakdown.carbon.score,
    greenCoverScore: scoring.breakdown.green.score,
    vegetation: mlOutput.landcover.vegetation_pct,
    impervious: mlOutput.landcover.impervious_pct,
    water: mlOutput.landcover.water_pct,
    lst: mlOutput.lst_celsius_mean,
    ndvi: mlOutput.ndvi_mean,
    ndbi: mlOutput.ndbi_mean,
    ndwi: mlOutput.ndwi_mean,
    elevation: mlOutput.elevation_m_mean,
    slope: mlOutput.slope_deg_mean,
    createdAt: project.createdAt,
  };
}

export function toApiAssessment(project) {
  return {
    ...frontendAssessment(project),
    organization: project.input.organization,
    description: project.input.description,
    coordinates: project.input.coordinates,
    builtUpAreaSqm: project.input.builtUpAreaSqm,
    materials: project.input.materials,
    ml: project.mlOutput,
    scoring: project.scoring,
    explanation: project.explanation,
    dataQuality: project.dataQuality,
  };
}

export function optimizeProject(project) {
  const baseline = frontendAssessment(project);
  const cover = project.mlOutput.landcover;
  const targetVegetation = Math.min(cover.vegetation_pct + 12, 45);
  const targetImpervious = Math.max(100 - cover.water_pct - targetVegetation, 0);
  const optimizedMl = {
    ...project.mlOutput,
    landcover: {
      ...cover,
      vegetation_pct: round(targetVegetation),
      impervious_pct: round(targetImpervious),
    },
    lst_celsius_mean: round(Math.max(project.mlOutput.lst_celsius_mean - 1.8, 28)),
    source: "illustrative-scenario",
  };
  const optimizedMaterials = Object.fromEntries(
    Object.entries(project.input.materials || {}).map(([name, amount]) => [name, round(amount * 0.85)]),
  );
  const scoring = scoreAssessment({
    mlOutput: optimizedMl,
    materials: optimizedMaterials,
    builtUpAreaSqm: project.input.builtUpAreaSqm,
  });
  const optimizedProject = {
    ...project,
    mlOutput: optimizedMl,
    scoring,
    input: { ...project.input, materials: optimizedMaterials },
  };
  const optimized = frontendAssessment(optimizedProject);
  const improvement = round(optimized.climateScore - baseline.climateScore);

  return {
    baseline,
    optimized,
    recommendations: [
      {
        id: "tree-canopy",
        icon: "tree",
        title: "Increase tree canopy",
        description: "Add connected tree cover around buildings and pedestrian corridors.",
        current: `${cover.vegetation_pct}%`,
        proposed: `${targetVegetation}%`,
        impact: improvement,
        target: "Heat + green cover",
      },
      {
        id: "permeable-surfaces",
        icon: "droplets",
        title: "Introduce permeable surfaces",
        description: "Replace selected hardscape to reduce runoff during the design storm.",
        current: `${cover.impervious_pct}%`,
        proposed: `${targetImpervious}%`,
        impact: round(project.scoring.breakdown.flood.score - scoring.breakdown.flood.score),
        target: "Flood risk",
      },
      {
        id: "cool-roofs",
        icon: "sun",
        title: "Adopt cool roofs",
        description: "Specify high-reflectance roofs and shaded paved areas.",
        current: `${project.mlOutput.lst_celsius_mean} C`,
        proposed: `${optimizedMl.lst_celsius_mean} C`,
        impact: round(project.scoring.breakdown.heat.score - scoring.breakdown.heat.score),
        target: "Heat risk",
      },
      {
        id: "lower-carbon-materials",
        icon: "leaf",
        title: "Reduce high-carbon materials",
        description: "Use verified lower-carbon mixes and optimize structural quantities.",
        current: "Baseline quantities",
        proposed: "15% reduction",
        impact: round(project.scoring.breakdown.carbon.score - scoring.breakdown.carbon.score),
        target: "Carbon impact",
      },
    ],
    scenario: { mlOutput: optimizedMl, materials: optimizedMaterials, scoring },
  };
}
