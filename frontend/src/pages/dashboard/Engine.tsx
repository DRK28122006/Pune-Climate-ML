import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Cpu, MapPin, MessageCircle, Send, SlidersHorizontal } from 'lucide-react';
import DataGate from '../../components/DataGate';
import { DemoBadge, EmptyState, MetricCard, PageHeader, Panel, Pill } from '../../components/ui';
import { useAsync } from '../../lib/useAsync';
import { usePlan } from '../../state/PlanContext';
import EngineMap from '../../components/EngineMap';
import type { Priority } from '../../types';

/** Ward-level impact scores from the ML pipeline (standard proposal: 2000 m2 built on 4000 m2 plot). */
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
  const res = await fetch('/wards.geojson');
  // We don't need the geojson here, just the scores
  const scoresRes = await fetch('/ward_scores.json');
  if (!scoresRes.ok) throw new Error('Failed to load ward scores');
  return scoresRes.json();
}

function riskTone(risk: string): Priority {
  if (risk === 'High') return 'high';
  if (risk === 'Moderate') return 'med';
  return 'low';
}

function impactColor(impact: number | null): string {
  if (impact === null) return '#c9b9a3'; // haze
  if (impact < 30) return '#2e7d4f'; // leaf
  if (impact < 60) return '#7d5400'; // amber
  return '#a8371f'; // heat
}

export default function Engine() {
  const state = useAsync(fetchWardScores);
  const { result } = usePlan();
  const [selectedWard, setSelectedWard] = useState<number | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<{ role: 'user' | 'assistant'; text: string }[]>([
    { role: 'assistant', text: 'I can help you understand the climate impact scores for any ward. Ask me about a specific ward, or type "compare 33 and 23" to see two wards side by side.' },
  ]);

  const scores = state.data ?? {};
  const selected = selectedWard ? scores[String(selectedWard)] : null;

  const sortedWards = useMemo(() => {
    return Object.entries(scores)
      .map(([ward, s]) => ({ ward: Number(ward), ...s }))
      .sort((a, b) => (a.impact ?? 999) - (b.impact ?? 999));
  }, [scores]);

  const handleChat = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const userMsg = chatInput.trim();
    setChatMessages((prev) => [...prev, { role: 'user', text: userMsg }]);
    setChatInput('');

    // Simple rule-based responses (no LLM call yet — wired to narrative.py later)
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
        response = `Ward ${w} not found in the dataset.`;
      }
    } else if (lower.includes('safest') || lower.includes('best')) {
      const safest = sortedWards.slice(0, 3);
      response = 'Safest wards for construction: ' + safest.map((w) => `Ward ${w.ward} (impact ${w.impact})`).join(', ') + '. Ward 33 is the only one scoring Low risk with complete data.';
    } else if (lower.includes('worst') || lower.includes('avoid')) {
      const worst = [...sortedWards].reverse().slice(0, 3);
      response = 'Worst wards (avoid or heavily mitigate): ' + worst.map((w) => `Ward ${w.ward} (impact ${w.impact})`).join(', ') + '. These are 94-99.9% built-up with near-zero vegetation.';
    } else if (lower.includes('unavailable') || lower.includes('missing')) {
      response = '26 of 41 wards have green = UNAVAILABLE (census block not loaded). Slope is unavailable everywhere. Fluvial flood is NOT_MODELLED. Storm drain distance is None for all wards. Heat corroboration is INCONCLUSIVE. Carbon bands (400/800/1200) are UNSOURCED.';
    } else {
      response = 'I can answer questions about ward scores. Try: "ward 33", "safest wards", "worst wards", or "what data is missing?"';
    }
    setChatMessages((prev) => [...prev, { role: 'assistant', text: response }]);
  };

  return (
    <>
      <PageHeader
        eyebrow="Engine · prototype"
        title="Engine"
        lede="Ward-level climate impact map and scoring assistant. Select a ward to see its scores, or ask the assistant below."
        badge={<DemoBadge label="Prototype" />}
      />

      <DataGate state={state}>
        {(data) => (
          <>
            <div className="two-col two-col--map">
              <Panel title="Ward impact map (conceptual)">
                <EngineMap scores={data} onSelect={setSelectedWard} selected={selectedWard} />
                <p className="legend" style={{ marginTop: '8px' }}>
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#2e7d4f', borderRadius: '2px', marginRight: '4px' }} />Low (&lt;30)
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#7d5400', borderRadius: '2px', marginLeft: '12px', marginRight: '4px' }} />Moderate (30-60)
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#a8371f', borderRadius: '2px', marginLeft: '12px', marginRight: '4px' }} />High (≥60)
                  <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#c9b9a3', borderRadius: '2px', marginLeft: '12px', marginRight: '4px' }} />No data
                </p>
                <p className="note" style={{ marginTop: '4px' }}>Faded tiles = green unavailable (census block not loaded). Standard proposal: 2,000 m² built on 4,000 m² plot.</p>
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
                        Green is UNAVAILABLE for this ward (census block not loaded). Impact is a lower bound — with green data it would be higher.
                      </p>
                    )}
                  </div>
                ) : (
                  <EmptyState title="Select a ward" text="Click a tile on the map to see its climate scores and data availability." />
                )}
              </Panel>
            </div>

            <div className="metrics" style={{ marginTop: '16px' }}>
              <MetricCard label="Safest ward" value="33" unit="" note="Impact 26.5, Low risk, all 4 factors" />
              <MetricCard label="Worst ward" value="23" unit="" note="Impact 70.0, High risk, 99.9% built" />
              <MetricCard label="Complete data" value="15" unit="of 41" note="Wards with all 4 factors" />
              <MetricCard label="Partial data" value="26" unit="of 41" note="Green unavailable" />
            </div>

            {/* AI Assistant */}
            <div style={{ marginTop: '16px' }}>
            <Panel title="Climate Assistant" note="Rule-based for now. Will be wired to the Gemini narrator (narrative.py) via the backend API.">
              <div style={{ maxHeight: '240px', overflowY: 'auto', padding: '8px', marginBottom: '8px' }}>
                {chatMessages.map((m, i) => (
                  <div key={i} style={{
                    textAlign: m.role === 'user' ? 'right' : 'left',
                    marginBottom: '8px',
                  }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '6px 12px',
                      borderRadius: '10px',
                      background: m.role === 'user' ? '#2e7d4f' : '#fffcf6',
                      color: m.role === 'user' ? '#fff' : '#1b2a26',
                      border: m.role === 'assistant' ? '1px solid rgba(40,34,26,0.18)' : 'none',
                      maxWidth: '80%',
                      fontSize: '13px',
                      lineHeight: 1.5,
                    }}>
                      {m.text}
                    </span>
                  </div>
                ))}
              </div>
              <form onSubmit={handleChat} style={{ display: 'flex', gap: '8px' }}>
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Ask about a ward, e.g. 'ward 33' or 'safest wards'"
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    border: '1px solid rgba(40,34,26,0.18)',
                    borderRadius: '6px',
                    fontSize: '13px',
                    background: '#fffcf6',
                    color: '#1b2a26',
                  }}
                />
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
