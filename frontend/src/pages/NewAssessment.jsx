import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { MapPin, Upload, ArrowRight, ArrowLeft, Check, Search, Building2, Satellite, FileText } from "lucide-react";
import { createAssessment } from "../services/climateApi";

const steps = [
  { title: "Project", icon: Building2 },
  { title: "Location", icon: MapPin },
  { title: "Environment", icon: Satellite },
  { title: "Documents", icon: FileText }
];

export default function NewAssessment() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({name:"", type:"Mixed-use development", organization:"", description:"", location:"Baner, Pune"});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function finish() {
    if (form.name.trim().length < 2) {
      setError("Please enter a project name before running the assessment.");
      setStep(0);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await createAssessment(form);
      navigate("/assessment/result");
    } catch (requestError) {
      setError(requestError.message || "The climate analysis could not be completed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page narrow-page">
      <div className="page-heading">
        <div><div className="eyebrow">PROJECT INTAKE</div><h1>New climate assessment</h1><p>Capture the project context and site boundary for environmental intelligence.</p></div>
      </div>

      <div className="stepper">
        {steps.map((s, i) => {
          const Icon = s.icon;
          return <div key={s.title} className={`step ${i === step ? "current" : ""} ${i < step ? "done" : ""}`}>
            <div className="step-icon">{i < step ? <Check size={15}/> : <Icon size={15}/>}</div>
            <span>{s.title}</span>
          </div>
        })}
      </div>

      <section className="panel form-panel">
        {step === 0 && <div className="form-content">
          <div className="form-title"><Building2 size={20}/><div><h2>Project information</h2><p>Start with the basic details of the proposed development.</p></div></div>
          <div className="form-grid">
            <label>Project name<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="e.g. Baner Urban Development"/></label>
            <label>Project type<select value={form.type} onChange={e=>setForm({...form,type:e.target.value})}><option>Mixed-use development</option><option>Residential development</option><option>Commercial development</option><option>Infrastructure</option><option>Public facility</option></select></label>
            <label className="full">Organization / developer<input value={form.organization} onChange={e=>setForm({...form,organization:e.target.value})} placeholder="Municipal department or organization"/></label>
            <label className="full">Project description<textarea value={form.description} onChange={e=>setForm({...form,description:e.target.value})} placeholder="Briefly describe the proposal, expected land use and major interventions."/></label>
          </div>
        </div>}

        {step === 1 && <div className="form-content">
          <div className="form-title"><MapPin size={20}/><div><h2>Site location & boundary</h2><p>Search for the project site and define its geographic extent.</p></div></div>
          <div className="search-field"><Search size={17}/><input value={form.location} onChange={e=>setForm({...form,location:e.target.value})} placeholder="Search Pune location..."/></div>
          <div className="map-placeholder large">
            <div className="map-grid"></div>
            <div className="map-controls"><button>+</button><button>−</button></div>
            <div className="map-pin"><MapPin size={20}/><span>{form.location || "Project site"}</span></div>
            <div className="boundary boundary-a"></div>
            <div className="map-legend"><span><i className="legend-green"></i> Project boundary</span><span><i className="legend-gray"></i> Urban area</span></div>
          </div>
          <div className="coordinate-row"><div><span>Latitude</span><strong>18.5590° N</strong></div><div><span>Longitude</span><strong>73.7868° E</strong></div><div><span>Estimated area</span><strong>4.2 ha</strong></div></div>
        </div>}

        {step === 2 && <div className="form-content">
          <div className="form-title"><Satellite size={20}/><div><h2>Environmental data</h2><p>The intelligence engine will retrieve satellite and terrain indicators for the selected site.</p></div></div>
          <div className="data-ready">
            <div className="ready-icon"><Check size={22}/></div>
            <div><strong>Site data source configured</strong><p>Satellite imagery · Land cover · Climate & weather · Terrain</p></div>
            <span className="online-tag">READY</span>
          </div>
          <div className="source-grid"><div><b>Sentinel / satellite imagery</b><span>Land cover, NDVI, NDBI, NDWI</span></div><div><b>Google Earth Engine</b><span>LST, elevation & slope</span></div><div><b>Climate & weather</b><span>Historical and current indicators</span></div></div>
        </div>}

        {step === 3 && <div className="form-content">
          <div className="form-title"><FileText size={20}/><div><h2>Supporting documents</h2><p>Upload project plans or environmental documents for the assessment record.</p></div></div>
          <div className="upload-zone"><div className="upload-icon"><Upload size={22}/></div><strong>Drop project documents here</strong><span>PDF, PNG, JPG or CSV · up to 20 MB</span><button className="secondary-btn">Choose files</button></div>
          <div className="data-ready"><div className="ready-icon"><Check size={22}/></div><div><strong>Structured site inputs are complete</strong><p>Ready to run the climate impact analysis.</p></div></div>
        </div>}

        {error && <p role="alert" style={{color:"#ff9b85", margin:"0 0 1rem"}}>{error}</p>}
        <div className="form-actions">
          {step > 0 ? <button className="secondary-btn" onClick={()=>setStep(step-1)}><ArrowLeft size={16}/> Back</button> : <span/>}
          {step < 3 ? <button className="primary-btn" onClick={()=>setStep(step+1)}>Continue <ArrowRight size={16}/></button> : <button className="primary-btn" onClick={finish} disabled={submitting}>{submitting ? "Analyzing..." : "Run climate analysis"} <ArrowRight size={16}/></button>}
        </div>
      </section>
    </div>
  );
}
