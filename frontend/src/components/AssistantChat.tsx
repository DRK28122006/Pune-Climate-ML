/**
 * Disha — the DishaDharti intake + narrator assistant.
 *
 * One fire-free conversation path: every user message goes to Gemini via
 * POST /api/v1/assistant. Gemini collects the building inputs, shows them
 * back as a structured card, and only scores on the officer's confirmation.
 * After the scorer runs, the same conversation narrates the measured output.
 * The assistant's knowledge is limited to the conversation, the draft, the
 * assessment and the 41 measured ward rows — it never invents numbers.
 */
import { useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';
import { usePlan } from '../state/PlanContext';
import { assistantReply, type ScoreResult } from '../services/climateApi';
import { MATERIALS, GOAL_LABELS } from '../config';
import type { AssessmentInputs, AssessmentGoal } from '../types';

interface AssistantChatProps {
  /** Extra grounding, e.g. Engine's own scored result. */
  assessment?: ScoreResult | null;
  /** Called when the officer confirms scoring. Defaults to the shared submit(). */
  onConfirm?: () => Promise<boolean> | void;
  /** Compact height for sidebars. */
  maxHeight?: number;
}

type ChatMsg = { role: 'user' | 'assistant'; text: string; source?: 'gemini' | 'fallback' | 'system' | 'error' };

const GREETING: ChatMsg = {
  role: 'assistant',
  text: "I'm Disha — I can help score a building permit. Talk to me like you would a colleague: what are you proposing, and where? Or ask me about the wards, the process, or a scored proposal.",
};

const DT_FIELDS: (keyof AssessmentInputs)[] = [
  'planName', 'wardNo', 'builtUpAreaSqm', 'plotAreaSqm', 'storeys',
  'builtUpPct', 'pavedPct', 'canopyPct', 'materials', 'projectType', 'goal',
];

function pickDraft(raw: Record<string, unknown>): Partial<AssessmentInputs> {
  const out: Record<string, unknown> = {};
  for (const key of DT_FIELDS) {
    if (raw[key] !== undefined) out[key] = raw[key];
  }
  return out as Partial<AssessmentInputs>;
}

export default function AssistantChat({ assessment, onConfirm, maxHeight = 300 }: AssistantChatProps) {
  const { inputs, setInputs, result, submit } = usePlan();
  const [messages, setMessages] = useState<ChatMsg[]>([GREETING]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<'collecting' | 'ready' | 'confirmed'>('collecting');
  const [scoring, setScoring] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const grounding = assessment ?? result ?? null;

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    const history: ChatMsg[] = [...messages, { role: 'user', text }];
    setMessages(history);
    setInput('');
    setBusy(true);
    setNotice(null);
    try {
      const res = await assistantReply({
        messages: history.slice(-30).map((m) => ({ role: m.role, text: m.text })),
        draft: inputs,
        phase,
        assessment: grounding,
      });
      setInputs(pickDraft(res.draft) as AssessmentInputs);
      setPhase(res.phase);
      const live = res.source === 'groq' || res.source === 'gemini';
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: res.reply, source: live ? 'gemini' : 'fallback' },
      ]);
      if (!live) {
        setNotice('Assistant offline — the reply did not come from the model. The form and scorer still work.');
      } else if (res.unknownMaterials && res.unknownMaterials.length > 0) {
        setNotice(
          `These materials aren't in the India table: ${res.unknownMaterials.join(', ')}. The scorer will flag them as unverified mass (carbon may be withheld if over 10% of the BOQ is unrecognised).`,
        );
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: 'Something went wrong on my side. Please try again.', source: 'error' },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const confirmScore = async () => {
    if (scoring) return;
    setScoring(true);
    setNotice(null);
    try {
      const ok = onConfirm ? await onConfirm() : await submit();
      if (ok !== false) {
        setPhase('confirmed');
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: 'Scored. Ask me about the result — approvability, the factors, the canopy ledger, or what to change.',
            source: 'system',
          },
        ]);
      }
    } finally {
      setScoring(false);
    }
  };

  const goalLabel = (g: AssessmentInputs['goal']) =>
    g && GOAL_LABELS[g as AssessmentGoal] ? GOAL_LABELS[g as AssessmentGoal] : g;

  return (
    <div>
      <div ref={scrollRef} style={{ maxHeight, overflowY: 'auto', padding: '8px', marginBottom: '8px' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ textAlign: m.role === 'user' ? 'right' : 'left', marginBottom: '8px' }}>
            <span
              style={{
                display: 'inline-block', padding: '6px 12px', borderRadius: '10px',
                background: m.role === 'user' ? '#2e7d4f' : '#fffcf6',
                color: m.role === 'user' ? '#fff' : '#1b2a26',
                border: m.role === 'assistant' ? '1px solid rgba(40,34,26,0.18)' : 'none',
                maxWidth: '85%', fontSize: '13px', lineHeight: 1.5, whiteSpace: 'pre-wrap',
                textAlign: 'left',
              }}
            >
              {m.text}
            </span>
          </div>
        ))}
        {busy && (
          <div style={{ color: '#4a5a55', fontSize: '12px', padding: '4px 8px' }}>Disha is thinking…</div>
        )}
      </div>

      {notice && (
        <p className="note" style={{ color: '#7d5400', margin: '0 8px 8px' }}>{notice}</p>
      )}

      {phase === 'ready' && (
        <div style={{ background: '#f4efe3', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '8px', padding: '10px 12px', margin: '0 8px 8px' }}>
          <p style={{ fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase', color: '#4a5a55', marginBottom: '6px' }}>
            Inputs loaded — review please
          </p>
          <dl className="mlist" style={{ margin: 0 }}>
            <div><dt>Ward</dt><dd>Ward {inputs.wardNo}</dd></div>
            <div><dt>Built-up</dt><dd>{inputs.builtUpAreaSqm?.toLocaleString('en-IN')} m² of {inputs.plotAreaSqm?.toLocaleString('en-IN')} m² plot</dd></div>
            <div><dt>Storeys</dt><dd>{inputs.storeys ?? 'not given'}</dd></div>
            <div><dt>Project</dt><dd>{inputs.projectType}{inputs.goal ? ` · ${goalLabel(inputs.goal)}` : ''}</dd></div>
            <div><dt>Materials</dt><dd>
              {inputs.materials.filter((m) => m.materialId && m.quantityKg > 0).map((m, i) => {
                const label = MATERIALS.find((x) => x.value === m.materialId)?.label ?? m.materialId;
                return <span key={i} style={{ display: 'block' }}>{label}: {m.quantityKg.toLocaleString('en-IN')} kg</span>;
              })}
            </dd></div>
            <div><dt>Land cover</dt><dd>built {inputs.builtUpPct ?? '—'}% · paved {inputs.pavedPct ?? '—'}% · canopy {inputs.canopyPct ?? '—'}%</dd></div>
          </dl>
          <div className="row-actions" style={{ marginTop: '8px' }}>
            <button type="button" className="btn btn--primary btn--md" disabled={scoring} onClick={() => void confirmScore()}>
              {scoring ? 'Scoring…' : 'Score the proposal'}
            </button>
            <button type="button" className="btn btn--ghost btn--md" onClick={() => document.getElementById('f-planName')?.focus({ preventScroll: true })}>
              Edit in the form
            </button>
          </div>
        </div>
      )}

      <div
        className="assistant-input"
        style={{ display: 'flex', gap: '8px', padding: '0 0 4px' }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT') {
            e.preventDefault();
            void send();
          }
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Talk to Disha — e.g. 'ward 12, 2000 sqm built-up on a 4000 sqm plot…'"
          aria-label="Message to Disha"
          style={{ flex: 1, padding: '8px 12px', border: '1px solid rgba(40,34,26,0.18)', borderRadius: '6px', fontSize: '13px', background: '#fffcf6', color: '#1b2a26' }}
        />
        <button type="button" className="btn btn--primary btn--md" disabled={busy} onClick={() => void send()} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Send size={16} /> {busy ? '…' : 'Send'}
        </button>
      </div>
    </div>
  );
}
