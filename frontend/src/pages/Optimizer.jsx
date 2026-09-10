import { useState } from "react";
import { ArrowRight, Check, Sparkles, TreePine, Droplets, Sun, Leaf, RotateCcw } from "lucide-react";
import { assessment as demoAssessment, optimized as demoOptimized, recommendations as demoRecommendations } from "../data/mockData";
import { optimizeAssessment } from "../services/climateApi";
import ClimateGauge from "../components/ClimateGauge";
import SectionHeader from "../components/SectionHeader";

const iconMap = { tree: TreePine, droplets: Droplets, sun: Sun, leaf: Leaf };

export default function Optimizer() {
  const [applied, setApplied] = useState([]);
  const [showAfter, setShowAfter] = useState(false);
  const [scenario, setScenario] = useState({ baseline: demoAssessment, optimized: demoOptimized, recommendations: demoRecommendations });
  const [loading, setLoading] = useState(false);
  const { baseline: assessment, optimized, recommendations } = scenario;

  async function evaluate() {
    setLoading(true);
    try {
      setScenario(await optimizeAssessment());
      setShowAfter(true);
    } finally {
      setLoading(false);
    }
  }

  const currentScore = showAfter ? optimized.climateScore : assessment.climateScore;

  return (
    <div className="page">
      <div className="hero-row">
        <div><div className="eyebrow">DECISION SUPPORT · AI OPTIMIZATION</div><h1>Turn insight into <span>better design.</span></h1><p className="hero-copy">Explore intervention scenarios and verify how each change can improve the site's climate impact score.</p></div>
        <button className="secondary-btn" onClick={()=>{setApplied([]);setShowAfter(false)}}><RotateCcw size={16}/> Reset scenario</button>
      </div>

      <div className="optimizer-layout">
        <section className="panel optimizer-score">
          <SectionHeader eyebrow="LIVE SCENARIO SCORE" title={showAfter ? "Optimized scenario" : "Current baseline"} />
          <ClimateGauge score={currentScore} label={showAfter ? "OPTIMIZED" : assessment.status.toUpperCase()} />
          <div className="score-delta">{showAfter ? <><span className="positive">+13 points</span><small>improvement from baseline</small></> : <><span>68 / 100</span><small>baseline score</small></>}</div>
          <div className="optimizer-note"><Sparkles size={16}/><span>AI recommendations are designed to be evaluated against the deterministic climate scoring model.</span></div>
        </section>

        <section className="panel recommendations-panel">
          <SectionHeader eyebrow="AI-GENERATED INTERVENTIONS" title="Recommended actions" action={<span className="ai-tag"><Sparkles size={13}/> AI assisted</span>} />
          <div className="recommendations">
            {recommendations.map((r, i) => {
              const Icon = iconMap[r.icon];
              const isApplied = applied.includes(i);
              return <div className={`recommendation ${isApplied ? "applied" : ""}`} key={r.title}>
                <div className="recommendation-icon"><Icon size={19}/></div>
                <div className="recommendation-body"><div className="recommendation-head"><h3>{r.title}</h3><span>+{r.impact} pts</span></div><p>{r.description}</p><div className="rec-values"><span>{r.current}</span><ArrowRight size={13}/><strong>{r.proposed}</strong><small>{r.target}</small></div></div>
                <button className={isApplied ? "applied-btn" : "apply-btn"} onClick={()=>setApplied(isApplied ? applied.filter(x=>x!==i) : [...applied,i])}>{isApplied ? <><Check size={15}/> Applied</> : "Apply"}</button>
              </div>
            })}
          </div>
          <div className="optimizer-action"><button className="primary-btn" onClick={evaluate} disabled={loading}><Sparkles size={16}/> {loading ? "Evaluating..." : "Evaluate optimized scenario"} <ArrowRight size={16}/></button></div>
        </section>
      </div>

      <section className="panel comparison-panel">
        <SectionHeader eyebrow="BEFORE → AFTER" title="Optimization impact" action={showAfter && <div className="improvement-badge">+13 POINT IMPROVEMENT</div>} />
        <div className="comparison-grid">
          <CompareMetric label="Climate score" before={assessment.climateScore} after={optimized.climateScore} max={100}/>
          <CompareMetric label="Heat risk" before={assessment.heatRisk} after={optimized.heatRisk} max={100}/>
          <CompareMetric label="Flood risk" before={assessment.floodRisk} after={optimized.floodRisk} max={100}/>
          <CompareMetric label="Carbon impact" before={assessment.carbonImpact} after={optimized.carbonImpact} max={100}/>
          <CompareMetric label="Green cover" before={assessment.vegetation} after={optimized.greenCover} max={50} suffix="%"/>
        </div>
      </section>
    </div>
  );
}

function CompareMetric({label,before,after,max,suffix=""}) {
  return <div className="compare-item"><div className="compare-head"><span>{label}</span><strong>{before}{suffix} <ArrowRight size={13}/> <em>{after}{suffix}</em></strong></div><div className="bar-pair"><div className="bar"><i style={{width:`${Math.min(before/max*100,100)}%`}}></i></div><div className="bar after"><i style={{width:`${Math.min(after/max*100,100)}%`}}></i></div></div><div className="bar-labels"><span>Current</span><span>Optimized</span></div></div>;
}
