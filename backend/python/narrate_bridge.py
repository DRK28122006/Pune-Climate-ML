"""Adapter: assessment JSON + question -> Gemini prose (or rule-based fallback).

Reads JSON from stdin: { "assessment": {...}, "question": "...", "role": "..." }
Prints JSON to stdout: { "text": "...", "source": "gemini"|"fallback"|"error" }
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

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

from ml_pipeline.report.narrative import build_prompt, load_key


def main():
    request = json.load(sys.stdin)
    assessment = request.get("assessment", {})
    question = request.get("question", "")
    role = request.get("role", "urban_planner")

    key = load_key()
    if not key:
        # Rule-based fallback
        score = assessment.get("score", {}) or {}
        impact = score.get("impact_score")
        risk = score.get("risk_band")
        ev = score.get("evidence_status")
        factors = score.get("factors", {}) or {}
        lines = [f"Impact: {impact}/100, Risk: {risk}, Evidence: {ev}."]
        for k in ("flood", "heat", "green", "carbon"):
            f = factors.get(k) or {}
            s = f.get("score")
            if s is not None:
                lines.append(f"  {k}: {s}/100")
            else:
                lines.append(f"  {k}: UNAVAILABLE")
        lines.append("Gemini API key not configured — showing computed values only.")
        print(json.dumps({"text": "\n".join(lines), "source": "fallback"}))
        return

    # Input-review mode: the assessment carries form inputs but no score yet.
    # build_prompt would inject misleading boilerplate (EVIDENCE_STATUS COMPLETE
    # with no site values), so use a plain review prompt instead.
    if "score" not in assessment and isinstance(assessment.get("inputs"), dict):
        inputs_json = json.dumps(assessment["inputs"], indent=1, default=str)
        prompt = (
            "You are reviewing building-proposal inputs on a municipal climate "
            "scoring form before they are scored. Flag only real internal "
            "inconsistencies: footprint vs plot area, storeys vs footprint, "
            "material quantities wildly out of scale with the built-up area, "
            "land-cover shares not summing near 100. Reply with a short list; "
            "if nothing is wrong, say the inputs look consistent. Never invent "
            "numbers or scores.\n\nINPUTS:\n" + inputs_json
        )
        if question:
            prompt += "\n\nOFFICER NOTE: " + question
    else:
        # Build prompt
        base_prompt = build_prompt(assessment, role)
        if question:
            prompt = base_prompt + "\n\nUSER QUESTION: " + question + "\n\nAnswer concisely (3-5 sentences) using only the computed values above."
        else:
            prompt = base_prompt

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024}
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "x-goog-api-key": key,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        print(json.dumps({"text": text, "source": "gemini"}))
    except Exception as e:
        # Gemini unavailable — fall back to rule-based summary
        score = assessment.get("score", {}) or {}
        impact = score.get("impact_score")
        risk = score.get("risk_band")
        ev = score.get("evidence_status")
        factors = score.get("factors", {}) or {}
        lines = [f"Impact: {impact}/100, Risk: {risk}, Evidence: {ev}."]
        for k in ("flood", "heat", "green", "carbon"):
            f = factors.get(k) or {}
            sc = f.get("score")
            if sc is not None:
                lines.append(f"  {k}: {sc}/100")
            else:
                lines.append(f"  {k}: UNAVAILABLE")
        lines.append(f"Note: Gemini narrator temporarily unavailable ({e}). Showing computed values.")
        print(json.dumps({"text": "\n".join(lines), "source": "fallback"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"text": str(error), "source": "error"}))
        raise SystemExit(1)
