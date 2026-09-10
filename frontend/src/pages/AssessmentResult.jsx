import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Sparkles, Download, Info, CheckCircle2, AlertTriangle } from "lucide-react";
import { assessment as demoAssessment } from "../data/mockData";
import { getAssessment, getReportUrl } from "../services/climateApi";
import ClimateGauge from "../components/ClimateGauge";
import RiskCard from "../components/RiskCard";
import SectionHeader from "../components/SectionHeader";

export default function AssessmentResult() {
  const [assessment, setAssessment] = useState(demoAssessment);
  useEffect(() => { getAssessment().then((value) => value && setAssessment(value)).catch(() => {}); }, []);

  return (
    <div className="page">
      <div className="result-top">
        <div><Link to="/dashboard" className="back-link"><ArrowLeft size={15}/> Dashboard</Link><div className="eyebrow">ASSESSMENT · 05 SEP 2026</div><h1>{assessment.projectName}</h1><p>📍 {assessment.location} · {assessment.projectType}</p></div>
        <div className="result-actions">{assessment.id && <a className="secondary-btn" href={getReportUrl(assessment.id)} target="_blank" rel="noreferrer"><Download size={16}/> Export</a>}<Link to="/optimizer" className="primary-btn"><Sparkles size={16}/> Optimize this site</Link></div>
      </div>

      <div className="result-hero">
        <div className="panel hero-score">
          <SectionHeader eyebrow="COMPOSITE ASSESSMENT" title="Climate impact score" />
          <div className="hero-gauge"><ClimateGauge score={assessment.climateScore} label={assessment.status.toUpperCase()}/><div className="score-summary"><div className="risk-badge medium">MODERATE–HIGH</div><h3>Action recommended</h3><p>The site has meaningful opportunities to reduce heat accumulation, runoff pressure and carbon impact before project approval.</p><Link to="/optimizer" className="text-btn">See AI recommendations <ArrowRight size={15}/></Link></div></div>
        </div>
        <div className="panel why-panel">
          <SectionHeader eyebrow="EXPLAINABLE AI" title="Why this score?" />
          <div className="reason"><AlertTriangle size={17}/><div><strong>High impervious surface</strong><span>61.3% of the site is currently impervious.</span></div></div>
          <div className="reason"><AlertTriangle size={17}/><div><strong>Elevated surface temperature</strong><span>LST recorded at {assessment.lst}°C.</span></div></div>
          <div className="reason"><AlertTriangle size={17}/><div><strong>Low vegetation coverage</strong><span>Vegetation coverage is {assessment.vegetation}%.</span></div></div>
          <div className="reason positive"><CheckCircle2 size={17}/><div><strong>Water presence detected</strong><span>NDWI indicates a measurable water component.</span></div></div>
        </div>
      </div>

      <section className="panel">
        <SectionHeader eyebrow="MULTI-DIMENSIONAL ANALYSIS" title="Climate risk breakdown" />
        <div className="risk-grid">
          <RiskCard type="heat" label="Urban heat" score={assessment.heatRisk} status="HIGH" />
          <RiskCard type="flood" label="Flood & drainage" score={assessment.floodRisk} status="MODERATE" />
          <RiskCard type="carbon" label="Carbon impact" score={assessment.carbonImpact} status="HIGH" />
          <RiskCard type="green" label="Green cover" score={assessment.greenCoverScore} status="MODERATE" />
        </div>
      </section>

      <section className="panel">
        <SectionHeader eyebrow="ENVIRONMENTAL BASELINE" title="Site intelligence" action={<span className="info-label"><Info size={14}/> Satellite-derived indicators</span>} />
        <div className="environment-grid">
          <Metric label="Vegetation cover" value={`${assessment.vegetation}%`} hint="Land cover"/>
          <Metric label="Impervious surface" value={`${assessment.impervious}%`} hint="Built / hard surface"/>
          <Metric label="Water cover" value={`${assessment.water}%`} hint="Land cover"/>
          <Metric label="Land surface temp." value={`${assessment.lst}°C`} hint="LST"/>
          <Metric label="NDVI" value={assessment.ndvi} hint="Vegetation index"/>
          <Metric label="NDBI" value={assessment.ndbi} hint="Built-up index"/>
          <Metric label="NDWI" value={assessment.ndwi} hint="Water index"/>
          <Metric label="Elevation" value={`${assessment.elevation} m`} hint="Terrain"/>
        </div>
      </section>
    </div>
  );
}

function Metric({label,value,hint}) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>;
}
