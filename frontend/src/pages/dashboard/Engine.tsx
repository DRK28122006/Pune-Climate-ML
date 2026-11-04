import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Cpu, MapPin, MessageCircle, Send, SlidersHorizontal } from 'lucide-react';
import DataGate from '../../components/DataGate';
import { DemoBadge, EmptyState, MetricCard, PageHeader, Panel, Pill } from '../../components/ui';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';
import { scoreProposal, narrateAssessment, type ScoreResult } from '../../services/climateApi';
import EngineMap from '../../components/EngineMap';
import type { Priority } from '../../types';

interface WardScore {
  impact: number | null;
  climate: number | null;
  risk_band: string;
  evidence_status: string;
  flood: number | null;
  heat: number | null;
  green: number | null;
  carbon: number | null;
  green_verified: boolean;
  built_pct: number | null;
  veg_pct: number | null;
  night_lst: number | null;
}

type WardScores = Record<string, WardScore>;

async function fetchWardScores(): Promise<WardScores> {
  const scoresRes = await fetch('/ward_scores.json');
  if (!scoresRes.ok) throw new Error('Failed to load ward scores');
  return scoresRes.json();
}

function riskTone(risk: string): Priority {
  if (risk === 'High') return 'high';
  if (risk === 'Moderate') return 'med';
  return 'low';
}

export default function Engine() {
  const state = useAsync(fetchWardScores);
  const { result } = usePlan();
  const [selectedWard, setSelectedWard] = useState<number | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<{ role: 'user' | 'assistant'; text: string }[]>([
    { role: 'assistant', text: 'Ask about a ward ("ward 33"), safest/worst wards, or missing data. Score a proposal first and I can explain its result — approvability, factor breakdown, canopy ledger — from the actual ML output.' },
  ]);

  // Scoring form state
  const [scoreWard, setScoreWard] = useState<number>(12);
  const [builtUp, setBuiltUp] = useState<number>(2000);
  const [plotArea, setPlotArea] = useState<number>(4000);
  const [scoring, setScoring] = useState(false);
  const [scoreResult, setScoreResult] = useState<ScoreResult | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);

  const scores = state.data ?? {};
  const selected = selectedWard ? scores[String(selectedWard)] : null;

  const sortedWards = useMemo(() => {
    return Object.entries(scores)
      .map(([ward, s]) => ({ ward: Number(ward), ...s }))
      .sort((a, b) => (a.impact ?? 999) - (b.impact ?? 999));
  }, [scores]);

  // Summary cards computed from the measured ward scores, never hardcoded.
  const summary = useMemo(() => {
    const wards = Object.entries(scores).map(([ward, s]) => ({ ward: Number(ward), ...s }));
    if (wards.length === 0) return null;
    const byImpact = [...wards].sort((a, b) => (a.impact ?? 999) - (b.impact ?? 999));
    const complete = wards.filter((w) => w.evidence_status === 'COMPLETE').length;
    return {
      safest: byImpact[0],
      worst: byImpact[byImpact.length - 1],
      complete,
      partial: wards.length - complete,
    };
  }, [scores]);

  const handleScore = async (e: React.FormEvent) => {
    e.preventDefault();
    setScoring(true);
    setScoreError(null);
    setScoreResult(null);
    try {
      const res = await scoreProposal({
        ward: scoreWard,
        builtUpAreaSqm: builtUp,
        plotAreaSqm: plotArea,
        materials: [
          { name: 'steel', quantityKg: 120000 },
          { name: 'cement', quantityKg: 400000 },
        ],
      });
      setScoreResult(res);
    } catch (err) {
      setScoreError(err instanceof Error ? err.message : 'Scoring failed');
    } finally {
      setScoring(false);
    }
  };

  const handleChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const userMsg = chatInput.trim();
    setChatMessages((prev) => [...prev, { role: 'user', text: userMsg }]);
    setChatInput('');

    // If we have a scored result, use the Gemini narrator; otherwise rule-based
    if (scoreResult) {
      try {
        const res = await narrateAssessment(scoreResult, userMsg);
        setChatMessages((prev) => [...prev, { role: 'assistant', text: res.text }]);
        return;
      } catch {
        // fall through to rule-based
      }
    }

    const lower = userMsg.toLowerCase();
    let response = '';
    const wardMatch = lower.match(/ward\s*(\d+)/);
    if (wardMatch) {
      const w = Number(wardMatch[1]);
      const s = scores[String(w)];
      if (s) {
        response = `Ward ${w}: Impact ${s.impact ?? 'N/A'}, Risk ${s.risk_band}, Evidence ${s.evidence_status}. ` +
          `Flood ${s.flood ?? 'N/A'}, Heat ${s.heat ?? 'N/A'}, Green ${s.green ?? 'UNAVAILABLE'}, Carbon ${s.carbon ?? 'N/A'}. ` +
          (s.green_verified ? 'All 4 factors available (decision-grade).' : 'Green unavailable — census block not loaded (diagnostic only).');
      } else {
        response = `Ward ${w} not found.`;
      }
    } else if (lower.includes('safest') || lower.includes('best')) {
      const safest = sortedWards.slice(0, 3);
      response = 'Safest wards: ' + safest.map((w) => `Ward ${w.ward} (impact ${w.impact})`).join(', ') + '. Ward 33 is the only Low-risk ward with complete data.';
    } else if (lower.includes('worst') || lower.includes('avoid')) {
      const worst = [...sortedWards].reverse().slice(0, 3);
      response = 'Worst wards: ' + worst.map((w) => `Ward ${w.ward} (impact ${w.impact})`).join(', ') + '. 94-99.9% built-up, near-zero vegetation.';
    } else if (lower.includes('missing') || lower.includes('unavailable')) {
      response = '26/41 wards: green UNAVAILABLE (census not loaded). Slope: unavailable everywhere. Fluvial flood: NOT_MODELLED. Storm drain distance: None (all wards). Heat corroboration: INCONCLUSIVE. Carbon bands (400/800/1200): UNSOURCED.';
    } else {
      response = 'Try: "ward 33", "safest wards", "worst wards", or "what data is missing?" Score a proposal first for AI-powered analysis.';
    }
    setChatMessages((prev) => [...prev, { role: 'assistant', text: response }]);
  };

  return (
    <>
      <PageHeader
        eyebrow="Engine · prototype"
        title="Engine"
        lede="Ward-level climate impact map, scoring, and assistant. Select a ward, run a proposal, or ask the assistant."
        badge={<DemoBadge label="Prototype" />}
      />

      <DataGate state={state}>
        {(data) => (
          <>
            <div className="two-col two-col--map">
              <Panel title="Ward impact map">
                <EngineMap scores={data} onSelect={setSelectedWard} selected={selectedWard} />
                <p className="legend" style={{ marginTop: '8px' }}>
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#2e7d4f', borderRadius: '2px', marginRight: '4px' }} />Low (&lt;30)
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#7d5400', borderRadius: '2px', marginLeft: '12px', marginRight: '4px' }} />Moderate (30-60)
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#a8371f', borderRadius: '2px', marginLeft: '12px', marginRight: '4px' }} />High (≥60)
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#c9b9a3', borderRadius: '2px', marginLeft: '12px', marginRight: '4px' }} />No data
                </p>
                <p className="note" style={{ marginTop: '4px' }}>Faded tiles = green unavailable. Click a ward for details.</p>
              </Panel>

              <Panel title={selected ? `Ward ${selectedWard} details` : 'Select a ward'}>
                {selected ? (
                  <div className="detail">
                    <Pill tone={riskTone(selected.risk_band)}>{selected.risk_band}</Pill>
                    <dl className="mlist">
                      <div><dt>Impact score</dt><dd>{selected.impact ?? '—'}</dd></div>
                      <div><dt>Climate score</dt><dd>{selected.climate ?? '—'}</dd></div>
                      <div><dt>Evidence</dt><dd>{selected.evidence_status} ({selected.green_verified ? '4/4' : '3/4'})</dd></div>
                      <div><dt>Flood</dt><dd>{selected.flood ?? '—'}</dd></div>
                      <div><dt>Heat</dt><dd>{selected.heat ?? '—'}</dd></div>
                      <div><dt>Green</dt><dd>{selected.green ?? 'UNAVAILABLE'}</dd></div>
                      <div><dt>Carbon</dt><dd>{selected.carbon ?? '—'}</dd></div>
                      <div><dt>Built-up</dt><dd>{selected.built_pct ?? '—'}%</dd></div>
                      <div><dt>Vegetation</dt><dd>{selected.veg_pct ?? '—'}%</dd></div>
                      <div><dt>Night LST</dt><dd>{selected.night_lst ?? '—'}°C</dd></div>
                    </dl>
                    {!selected.green_verified && (
                      <p className="note" style={{ color: '#7d5400', marginTop: '8px' }}>
                        Green unavailable (census block not loaded). Impact is a lower bound.
                      </p>
                    )}
                  </div>
                ) : (
                  <EmptyState title="Select a ward" text="Click a ward on the map to see its climate scores." />
                )}
              </Panel>
            </div>

            <div className="metrics" style={{ marginTop: '16px' }}>
              {summary && (
                <>
                  <MetricCard label="Safest ward" value={String(summary.safest.ward)} unit="" note={`Impact ${summary.safest.impact}, ${summary.safest.risk_band} risk, evidence ${summary.safest.evidence_status}`} />
                  <MetricCard label="Worst ward" value={String(summary.worst.ward)} unit="" note={`Impact ${summary.worst.impact}, ${summary.worst.risk_band} risk, evidence ${summary.worst.evidence_status}`} />
                  <MetricCard label="Complete data" value={String(summary.complete)} unit={`of ${Object.keys(scores).length}`} note="Wards with all 4 factors" />
                  <MetricCard label="Partial data" value={String(summary.partial)} unit={`of ${Object.keys(scores).length}`} note="Green unavailable" />
                </>
              )}
            </div>

            {/* Scoring form */}
            <div style={{ marginTop: '16px' }}>
              <Panel title="Score a proposal" note="Uses the real ML pipeline (epoch cube + tree census + SCS-CN flood + night LST heat + carbon).">
                <form onSubmit={handleScore} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', color: '#4a5a55', fontWeight: 600 }}>Ward</label>
                    <select value={scoreWard} onChange={(e) => setScoreWard(Number(e.target.value))} style={{ padding: '8px', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', background: '#fffcf6', color: '#1b2a26' }}>
                      {sortedWards.map((w) => <option key={w.ward} value={w.ward}>Ward {w.ward}</option>)}
                    </select>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', color: '#4a5a55', fontWeight: 600 }}>Built-up area (m²)</label>
                    <input type="number" value={builtUp} onChange={(e) => setBuiltUp(Number(e.target.value))} style={{ padding: '8px', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', background: '#fffcf6', color: '#1b2a26', width: '120px' }} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', color: '#4a5a55', fontWeight: 600 }}>Plot area (m²)</label>
                    <input type="number" value={plotArea} onChange={(e) => setPlotArea(Number(e.target.value))} style={{ padding: '8px', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', background: '#fffcf6', color: '#1b2a26', width: '120px' }} />
                  </div>
                  <button type="submit" className="btn btn--primary btn--md" disabled={scoring}>
                    {scoring ? 'Scoring...' : 'Score proposal'}
                  </button>
                </form>

                {scoreError && (
                  <p style={{ color: '#a8371f', marginTop: '8px', fontSize: '13px' }}>{scoreError}</p>
                )}

                {scoreResult && (
                  <div style={{ marginTop: '16px' }}>
                    <div className="metrics">
                      <MetricCard label="Impact score" value={String(scoreResult.score.impact_score ?? '—')} unit="/100" note={scoreResult.score.risk_band ?? ''} />
                      <MetricCard label="Climate score" value={String(scoreResult.score.climate_score ?? '—')} unit="/100" />
                      <MetricCard label="Evidence" value={scoreResult.score.evidence_status} note={scoreResult.score.decision_grade ? 'Decision-grade' : 'Diagnostic only'} />
                      <MetricCard label="Recommendations" value={String(scoreResult.recommendations.length)} unit="" />
                    </div>
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '12px' }}>
                      {Object.entries(scoreResult.score.factors).map(([k, v]) => (
                        <div key={k} style={{ padding: '8px 12px', background: '#fffcf6', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', minWidth: '100px' }}>
                          <div style={{ fontSize: '11px', color: '#4a5a55', textTransform: 'capitalize' }}>{k}</div>
                          <div style={{ fontSize: '18px', fontWeight: 700, color: '#1b2a26' }}>{v.score ?? 'N/A'}</div>
                          <div style={{ fontSize: '10px', color: v.status === 'UNAVAILABLE' ? '#a8371f' : '#1f6b44' }}>{v.status ?? ''}</div>
                        </div>
                      ))}
                    </div>
                    {scoreResult.recommendations.length > 0 && (
                      <div style={{ marginTop: '12px' }}>
                        <h4 style={{ fontSize: '13px', fontWeight: 600, color: '#1c5535', marginBottom: '8px' }}>Recommendations</h4>
                        {scoreResult.recommendations.map((rec, i) => (
                          <div key={i} style={{ padding: '8px 12px', marginBottom: '6px', background: '#fffcf6', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', fontSize: '13px' }}>
                            <b>{rec.title || `Recommendation ${i + 1}`}</b>
                            {rec.description && <p style={{ margin: '4px 0 0', color: '#4a5a55' }}>{rec.description}</p>}
                            {rec.impact !== undefined && <span style={{ fontSize: '11px', color: '#1f6b44' }}> Impact: {rec.impact}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                    {scoreResult.score.evidence_status !== 'COMPLETE' && (
                      <p className="note" style={{ color: '#7d5400', marginTop: '8px' }}>
                        {scoreResult.score.evidence_status}: {scoreResult.score.decision_grade ? '' : 'Diagnostic only — not decision-grade. '}
                        {Object.entries(scoreResult.score.factors).filter(([, v]) => v.status === 'UNAVAILABLE').map(([k]) => k).join(', ')} unavailable.
                      </p>
                    )}
                  </div>
                )}
              </Panel>
            </div>

            {/* AI Assistant */}
            <div style={{ marginTop: '16px' }}>
              <Panel title="Climate Assistant" note="Gemini answers from the scored assessment only — it quotes computed values, never invents numbers. Without a score, ward lookups come from the ward score table.">
                <div style={{ maxHeight: '240px', overflowY: 'auto', padding: '8px', marginBottom: '8px' }}>
                  {chatMessages.map((m, i) => (
                    <div key={i} style={{ textAlign: m.role === 'user' ? 'right' : 'left', marginBottom: '8px' }}>
                      <span style={{
                        display: 'inline-block', padding: '6px 12px', borderRadius: '10px',
                        background: m.role === 'user' ? '#2e7d4f' : '#fffcf6',
                        color: m.role === 'user' ? '#fff' : '#1b2a26',
                        border: m.role === 'assistant' ? '1px solid rgba(40,34,26,0.18)' : 'none',
                        maxWidth: '80%', fontSize: '13px', lineHeight: 1.5,
                      }}>
                        {m.text}
                      </span>
                    </div>
                  ))}
                </div>
                <form onSubmit={handleChat} style={{ display: 'flex', gap: '8px' }}>
                  <input type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)}
                    placeholder={scoreResult ? "Ask about this score, e.g. 'is this approvable?'" : "Ask about a ward, e.g. 'ward 33'"}
                    style={{ flex: 1, padding: '8px 12px', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', fontSize: '13px', background: '#fffcf6', color: '#1b2a26' }} />
                  <button type="submit" className="btn btn--primary btn--md" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Send size={16} /> Send
                  </button>
                </form>
              </Panel>
            </div>
          </>
        )}
      </DataGate>
    </>
  );
}
