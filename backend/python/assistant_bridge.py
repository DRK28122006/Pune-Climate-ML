"""Conversational intake + narrator bridge.

One endpoint for every user turn. Gemini talks freely; it may only read, never
invent, the supplied data (DRAFT inputs, ASSESSMENT if scored, the real
41-ward score table). It never computes beyond labelled unit conversions and
never softens or replaces the scorer's verdict.

Reads JSON from stdin:  { messages, draft, phase, assessment? }
Writes JSON to stdout:  { reply, draft, phase, source, unknownMaterials? }
"""

import json
import os
import sys
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Load .env
env_path = REPO / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from ml_pipeline.report.narrative import load_key

MAX_MESSAGES = 30
MAX_MESSAGE_CHARS = 2000
VALID_PROJECT_TYPES = {"residential", "commercial", "institutional", "industrial"}
VALID_GOALS = {"balanced", "cooling", "flood", "greening"}


def _load_materials():
    table = json.loads((REPO / "ml_pipeline" / "config" / "materials.json").read_text())
    ids = set(table.get("materials", {}).keys())
    aliases = table.get("aliases", {})
    # normalise alias keys once
    norm_aliases = {re.sub(r"[^a-z0-9]+", "_", k.lower()): v for k, v in aliases.items()}
    return ids, norm_aliases


def _normalise_material_id(name: Any, ids: set, norm_aliases: dict) -> str:
    if not isinstance(name, str) or not name.strip():
        return ""
    key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if key in ids:
        return key
    if key in norm_aliases:
        return norm_aliases[key]
    # substring heuristics: try alias containment, then id containment
    for alias, target in norm_aliases.items():
        if alias in key or key in alias:
            return target
    for mid in ids:
        if mid in key or key in mid:
            return mid
    return key  # keep raw — the scorer flags unknown materials honestly


def _sanitise_draft(draft: Any, prev: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the model-returned draft field by field. Never zero-fill."""
    prev = prev if isinstance(prev, dict) else {}
    out = dict(prev)
    if not isinstance(draft, dict):
        return out

    ids, norm_aliases = _load_materials()

    def pick_number(field, lo=None, hi=None, integer=False):
        v = draft.get(field)
        if v is None:
            return out.get(field)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return out.get(field)
        if not (v == v):  # NaN
            return out.get(field)
        if lo is not None and v < lo:
            return out.get(field)
        if hi is not None and v > hi:
            return out.get(field)
        return int(round(v)) if integer else v

    ward = draft.get("wardNo", draft.get("ward"))
    try:
        if ward is not None:
            ward = int(float(ward))
            if 1 <= ward <= 41:
                out["wardNo"] = ward
    except (TypeError, ValueError):
        pass

    for field in ("builtUpAreaSqm", "plotAreaSqm"):
        v = pick_number(field, lo=1)
        if v is not None:
            out[field] = v

    v = pick_number("storeys", lo=1, hi=200, integer=True)
    if v is not None:
        out["storeys"] = v

    for field in ("builtUpPct", "pavedPct", "canopyPct"):
        v = pick_number(field, lo=0, hi=100)
        if v is not None:
            out[field] = v

    name = draft.get("planName")
    if isinstance(name, str) and name.strip():
        out["planName"] = name.strip()[:70]
    elif prev.get("planName"):
        out["planName"] = prev["planName"]

    ptype = draft.get("projectType")
    if isinstance(ptype, str) and ptype.lower() in VALID_PROJECT_TYPES:
        out["projectType"] = ptype.lower()
    goal = draft.get("goal")
    if isinstance(goal, str) and goal.lower() in VALID_GOALS:
        out["goal"] = goal.lower()

    # Materials: accept model's full list if present; otherwise keep previous.
    mats = draft.get("materials")
    if isinstance(mats, list) and mats:
        cleaned = []
        for line in mats[:30]:
            if not isinstance(line, dict):
                continue
            mid = _normalise_material_id(line.get("materialId") or line.get("name") or line.get("material"), ids, norm_aliases)
            try:
                qty = float(line.get("quantityKg") or line.get("quantity_kg") or line.get("kg") or 0)
            except (TypeError, ValueError):
                continue
            if not mid or qty <= 0:
                continue
            cleaned.append({"materialId": mid, "quantityKg": int(round(qty))})
        if cleaned:
            out["materials"] = cleaned

    # Built-up cannot exceed plot.
    if out.get("builtUpAreaSqm") is not None and out.get("plotAreaSqm") is not None:
        if out["builtUpAreaSqm"] > out["plotAreaSqm"]:
            # Keep the previous valid pair rather than an impossible one.
            out["builtUpAreaSqm"] = prev.get("builtUpAreaSqm")
            out["plotAreaSqm"] = prev.get("plotAreaSqm")
            if out["builtUpAreaSqm"] is None or out["plotAreaSqm"] is None:
                out.pop("builtUpAreaSqm", None)
                out.pop("plotAreaSqm", None)

    return out


def _draft_problems(draft: Dict[str, Any]) -> List[str]:
    problems = []
    if not (isinstance(draft.get("wardNo"), int) and 1 <= draft["wardNo"] <= 41):
        problems.append("ward (1-41)")
    if not (isinstance(draft.get("builtUpAreaSqm"), (int, float)) and draft["builtUpAreaSqm"] > 0):
        problems.append("built-up area m2")
    if not (isinstance(draft.get("plotAreaSqm"), (int, float)) and draft["plotAreaSqm"] > 0):
        problems.append("plot area m2")
    mats = draft.get("materials") or []
    if not any(m.get("materialId") and m.get("quantityKg", 0) > 0 for m in mats):
        problems.append("at least one material quantity (kg)")
    return problems


def _compact_assessment(a: Any) -> Any:
    if not isinstance(a, dict):
        return None
    score = a.get("score") or {}
    canopy = a.get("canopy") or {}
    indicators = a.get("indicators") or {}
    carbon = (score.get("factors") or {}).get("carbon") or {}
    recs = a.get("recommendations") or []
    return {
        "ward": a.get("ward"),
        "score": {
            "impact_score": score.get("impact_score"),
            "climate_score": score.get("climate_score"),
            "risk_band": score.get("risk_band"),
            "evidence_status": score.get("evidence_status"),
            "decision_grade": score.get("decision_grade"),
            "recommendation": score.get("recommendation"),
            "sub_scores": score.get("sub_scores"),
            "factors": {k: {"score": f.get("score"), "status": f.get("status"), "reason": f.get("reason")}
                        for k, f in (score.get("factors") or {}).items() if isinstance(f, dict)},
        },
        "recommendations": [
            {"id": r.get("id"), "action": r.get("action"),
             "delta": {"impact_delta": (r.get("delta") or {}).get("impact_delta")}}
            for r in recs[:6]
        ],
        "canopy": {
            "total_trees": canopy.get("total_trees"),
            "canopy_cover_pct": canopy.get("canopy_cover_pct"),
            "canopy_cover_pct_proposed": canopy.get("canopy_cover_pct_proposed"),
            "action_counts": canopy.get("action_counts"),
            "compensatory_required": canopy.get("compensatory_required"),
            "census_coverage_complete": (canopy.get("census_coverage") or {}).get("coverage_complete"),
        },
        "carbon": {
            "total_kgco2e": carbon.get("total_kgco2e"),
            "intensity_kgco2e_m2": carbon.get("intensity_kgco2e_m2"),
            "dominant_material": carbon.get("dominant_material"),
            "unknown_mass_pct": carbon.get("unknown_mass_pct"),
            "band": carbon.get("band"),
        },
        "indicators": {
            "impervious_pct": indicators.get("impervious_pct"),
            "vegetation_pct": indicators.get("vegetation_pct"),
            "water_pct": indicators.get("water_pct"),
            "lst_night_mean_c": indicators.get("lst_night_mean_c"),
            "landcover_source": indicators.get("landcover_source"),
        },
        "satellite_cube_available": a.get("satellite_cube_available"),
    }


def _load_ward_table():
    try:
        return json.loads((REPO / "frontend" / "public" / "ward_scores.json").read_text())
    except Exception:
        return None


def build_prompt(messages, draft, phase, assessment, ward_table, material_ids):
    missing = _draft_problems(draft)
    draft_json = json.dumps(draft, indent=1, default=str)
    history = "\n".join(
        f"{'OFFICER' if m.get('role') == 'user' else 'DISHA'}: {str(m.get('text', ''))[:MAX_MESSAGE_CHARS]}"
        for m in messages[-MAX_MESSAGES:]
    )
    assessment_json = json.dumps(assessment, indent=1, default=str) if assessment else "not scored yet"
    ward_json = json.dumps(ward_table, indent=1) if ward_table else "not provided"

    return f"""You are Disha, the intake and explainer assistant for a municipal building-climate scoring pilot in Pune, India. You speak with a municipal officer deciding a building permit. Your knowledge is ONLY what is provided below. You never invent numbers.

IRON RULES. Violating any one fails the task:
1. Facts come only from (a) the conversation, (b) DRAFT, (c) ASSESSMENT, (d) WARD TABLE. If something is not there, say plainly that it is not in the measured data. Never guess.
2. You never compute. The ONLY arithmetic you may do is an explicitly labelled unit conversion the officer asked for or implied (tonnes -> kg: x1000; cm -> m). State the conversion in your reply the first time (e.g. "180 tonnes = 180,000 kg").
3. The scorer's verdict words (REVIEW, REJECT_OR_REDESIGN, APPROVE and similar) must be quoted exactly as given in ASSESSMENT. Never soften, paraphrase or replace them. You do not grant or refuse approvals; the scorer's verdict governs.
4. UNAVAILABLE factors stay UNAVAILABLE. Explain the stated reason; never substitute a value.
5. Never write a score, factor, canopy figure or carbon figure that is not in ASSESSMENT. If asked for one and it is missing, say it is not in the measured data.
6. Collecting: ask at most ONE missing item per turn. Acknowledge the answer briefly and confirm conversions.
7. Materials: use ONLY the MATERIAL IDS listed below as materialId. If the officer names something not listed, ask a clarifying question; do not invent an id. Quantities go in kg.
8. When every required field is valid, set phase="ready" and ask the officer to confirm (e.g. "That's everything I need — shall I score it?"). NEVER score yourself.
9. If the officer confirms (yes / score it / go ahead), set phase="confirmed". The app then runs the real scorer.
10. If ASSESSMENT is present, you may answer freely about it: approvability, factor breakdown, canopy ledger, verified recommendation deltas. Quote only its values.
11. Plain, warm, competent tone. Short replies (1-4 sentences unless asked for detail). No emojis.
12. Your reply value is plain natural language. NEVER put JSON inside the reply string. The JSON wrapper is handled by the system, not you.

REQUIRED FIELDS (DRAFT):
- wardNo: integer 1-41 (Pune Municipal Corporation ward)
- builtUpAreaSqm: number > 0 (built-up floor space)
- plotAreaSqm: number > 0 (plot including open space)
- materials: list of {{"materialId": id, "quantityKg": kg}} — at least one line
- storeys: optional integer
- builtUpPct / pavedPct / canopyPct: optional 0-100
- projectType: optional, one of residential|commercial|institutional|industrial
- planName: optional short string

CURRENT PHASE: {phase}
MISSING OR INVALID: {json.dumps(missing)}
CURRENT DRAFT:
{draft_json}

ASSESSMENT (computed, read-only):
{assessment_json}

WARD TABLE (measured scores per ward, read-only):
{ward_json}

MATERIAL IDS (use exactly these):
{", ".join(material_ids)}

CONVERSATION SO FAR:
{history}

TASK THIS TURN:
- Talk naturally and helpfully. Answer questions about the current draft, the proposal process, the measured ward data, or (if present) the assessment.
- If the officer states inputs, extract them into the reply JSON fields. Extract ONLY what they gave. Never fill gaps.
- If the officer asks to change something (materials, areas, ward), update DRAFT and set phase back to "collecting".
- If every required field became valid this turn, set phase="ready" and ask to confirm scoring.
- If the officer clearly confirms, set phase="confirmed".

Reply ONLY as JSON with exactly these keys:
{{"reply": "<what you say to the officer>",
  "draft": {{ ... the merged DRAFT, i.e. current draft with this turn's extracted values applied ... }},
  "phase": "collecting" | "ready" | "confirmed"}}"""


def main():
    request = json.load(sys.stdin)
    messages = request.get("messages") or []
    draft = request.get("draft") or {}
    phase = request.get("phase") or "collecting"
    prev_phase = phase if phase in ("collecting", "ready", "confirmed") else "collecting"

    material_ids = sorted(_load_materials()[0])
    compact_assessment = _compact_assessment(request.get("assessment"))
    ward_table = _load_ward_table() if compact_assessment is None else None

    prompt = build_prompt(
        messages if isinstance(messages, list) else [],
        draft if isinstance(draft, dict) else {},
        prev_phase,
        compact_assessment,
        ward_table,
        material_ids,
    )

    def fallback(reason: str) -> Dict[str, Any]:
        return {
            "reply": "The assistant is offline right now, so I can't answer. The form still works — or try again in a moment.",
            "draft": _sanitise_draft({}, draft),
            "phase": prev_phase if prev_phase != "confirmed" else "ready",
            "source": "fallback",
            "reason": reason,
        }

    key = load_key()
    if not key:
        print(json.dumps(fallback("no GEMINI_API_KEY")))
        return

    def call_gemini():
        last_error = None
        for attempt in range(3):
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096, "responseMimeType": "application/json"},
            }).encode()
            req = urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent",
                data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key},
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code in (429, 503) and attempt < 2:
                    time.sleep(5 * (attempt + 1))  # 5s, 10s — back off for rate limit
                    continue
                raise
            except Exception as e:
                last_error = e
                if attempt < 2:
                    time.sleep(3)
                    continue
                raise
        raise last_error  # unreachable, but keeps types happy

    try:
        data = call_gemini()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(json.dumps(fallback(str(e))))
        return

    raw = text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                parsed = {"reply": raw, "draft": draft, "phase": prev_phase}
        else:
            parsed = {"reply": raw, "draft": draft, "phase": prev_phase}

    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        reply = "I didn't catch that — could you say it again?"
    reply = reply.strip()

    # Unwrap a double-encoded reply: models sometimes emit JSON inside reply.
    for _ in range(2):
        stripped = reply.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                inner = json.loads(stripped)
            except json.JSONDecodeError:
                break
            if isinstance(inner, dict) and isinstance(inner.get("reply"), str):
                # Merge inner fields into the outer result, then re-read reply.
                parsed.setdefault("draft", inner.get("draft", draft))
                parsed["phase"] = inner.get("phase", prev_phase)
                reply = inner["reply"]
                continue
        break

    new_draft = _sanitise_draft(parsed.get("draft"), draft)
    missing = _draft_problems(new_draft)
    model_phase = parsed.get("phase")

    if model_phase == "confirmed":
        new_phase = "confirmed" if not missing else "collecting"
    elif model_phase == "ready":
        new_phase = "ready" if not missing else "collecting"
    else:
        new_phase = "ready" if not missing and prev_phase != "confirmed" else "collecting"

    unknown = [
        m["materialId"]
        for m in (new_draft.get("materials") or [])
        if m["materialId"] and m["materialId"] not in _load_materials()[0]
    ]

    print(json.dumps({
        "reply": reply,
        "draft": new_draft,
        "phase": new_phase,
        "missing": missing,
        "unknownMaterials": unknown,
        "source": "gemini",
    }, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"reply": "Something went wrong on my side. Please try again.",
                          "draft": {}, "phase": "collecting", "source": "error", "reason": str(error)}))
        sys.exit(1)
