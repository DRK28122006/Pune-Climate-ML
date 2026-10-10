"""LLM narrator: deterministic JSON in, officer-plain prose out.

Architecture law: the model READS computed values and speaks them. It
never computes, adjusts, rounds-beyond-display, or invents a number. Any
code path that lets model text flow back into a score is a defect.

Provider-agnostic core (prompt builder + pass-through guards) with a
thin Gemini REST transport (stdlib only, no new dependencies). Groq or
others plug in as a second transport later -- the prompt builder stays.

Credentials: GEMINI_API_KEY in .env (git-ignored). Never in chat, never
in git, never in a prompt. Read via os.environ with a minimal .env
fallback (no python-dotenv dependency).

Usage:
    .venv/bin/python -m ml_pipeline.cli assess ... --json-out /tmp/a.json
    .venv/bin/python ml_pipeline/report/narrative.py /tmp/a.json [--role R]
"""
import json
import os
import sys
import urllib.request
from typing import Any, Callable, Dict, List, Optional

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent")
ALLOWED_ROLES = ("municipal_authority", "urban_planner",
                 "environmental_consultant", "public_viewer")


def load_key(name: str = "GEMINI_API_KEY") -> Optional[str]:
    """API key from env, else a minimal .env parse. None when absent."""
    val = os.environ.get(name)
    if val:
        return val.strip()
    here = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    for cand in (os.path.join(here, ".env"),
                 os.path.expanduser("~/.env")):
        try:
            with open(cand) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            continue
    return None


def _r1(x: Any) -> Any:
    """Round display floats to 1dp so prompts never carry float noise
    (fixed 2026-10-10: 83.13000000000001% printed verbatim in prose)."""
    try:
        return round(float(x), 1)
    except (TypeError, ValueError):
        return x


def _fmt_blockers(score: Dict[str, Any]) -> List[str]:
    # Blocking issues gate approval: the narrator must state them, never
    # bury them (fixed 2026-10-10: the timber blocker never reached prose).
    out = []
    for b in score.get("blocking_issues") or []:
        if isinstance(b, dict):
            out.append(f"- BLOCKING: {b.get('type')}: {b.get('detail')}")
        else:
            out.append(f"- BLOCKING: {b}")
    if out:
        return ["blocking issues (must be resolved before approval):", *out]
    return []


def _fmt_factors(score: Dict[str, Any]) -> List[str]:
    lines = []
    for key in ("flood", "heat", "green", "carbon"):
        fac = (score.get("factors") or {}).get(key) or {}
        s = fac.get("score")
        if s is None:
            lines.append(f"- {key}: UNAVAILABLE "
                         f"({fac.get('reason') or fac.get('status')})")
            continue
        lines.append(f"- {key}: {s}/100 (high=worse)")
    return lines


def _fmt_conditions(recs: Dict[str, Any]) -> List[str]:
    lines = []
    for c in (recs.get("recommendations") or [])[:6]:
        d = c.get("delta") or {}
        lines.append(f"- {c.get('action')} "
                     f"[verified={c.get('verified')}, "
                     f"impact_delta={d.get('impact_delta')}]")
    ce = recs.get("combined_effect") or {}
    if ce.get("available"):
        lines.append(f"- combined effect: "
                     f"{(ce.get('delta') or {}).get('impact_delta')}")
    return lines


def build_prompt(assessment: Dict[str, Any], role: str = "urban_planner") -> str:
    """Deterministic prompt. Every number below is copied, never derived."""
    if role not in ALLOWED_ROLES:
        role = "urban_planner"  # hostile/typo roles remap, never interpolate
    if not isinstance(assessment, dict):
        raise ValueError("assessment must be a dict")
    score = assessment.get("score", {}) or {}
    recs = assessment.get("recommendations", {}) or {}
    ledger = assessment.get("canopy", {}) or {}
    validation = assessment.get("validation", {}) or {}
    site = validation.get("site", {}) or {}
    ind = assessment.get("indicators", {}) or {}

    site_bits = [f"ward {site.get('ward_no')}",
                 f"built-up {_r1(site.get('builtUpAreaSqm'))} m2",
                 f"plot {_r1(site.get('plotAreaSqm'))} m2"]
    parts = [
        "You are a municipal climate-permit explainer. An officer will "
        "decide APPROVE / CONDITION / REJECT on a building proposal from "
        "your words. Precision outranks eloquence.",
        "",
        "IRON RULES. Violating any one fails the task:",
        "1. Repeat every number EXACTLY as given. Never recompute, round "
        "beyond display, interpolate, or invent a missing one.",
        "2. UNAVAILABLE factors stay unavailable. Explain the stated "
        "reason; never substitute a plausible value.",
        "3. Recommendation effects are quoted from the verified deltas "
        "only. Never promise an unmeasured improvement.",
        "4. Tree compensation is a RANGE (given below), never a point.",
        "5. No legal advice beyond the stated statutory basis.",
        "6. The verdict line quotes the computed recommendation EXACTLY as "
        "given below. REVIEW stays REVIEW; REJECT_OR_REDESIGN stays "
        "REJECT_OR_REDESIGN. Never translate it into approval language "
        "('approved with conditions', 'conditional approval'). A softened "
        "verdict is a failed task.",
        "",
        "ASSESSMENT (computed, read-only):",
        f"VERBATIM_VERDICT: {score.get('recommendation')}",
        f"site: {', '.join(str(b) for b in site_bits)}",
        f"impact: {score.get('impact_score')}/100 "
        f"(high=worse), climate: {score.get('climate_score')}/100, "
        f"band: {score.get('risk_band')}, "
        f"recommendation: {score.get('recommendation')}",
        "factors (0-100, high=worse):",
        *_fmt_factors(score),
        "verified conditions:",
        *_fmt_conditions(recs),
        f"canopy ledger: {ledger.get('total_trees')} trees on site; "
        f"canopy {ledger.get('tree_canopy_m2_before')} -> "
        f"{ledger.get('tree_canopy_m2_after')} m2; "
        f"compensatory {ledger.get('compensatory_required')} "
        f"({ledger.get('compensatory_basis')}); "
        f"must-preserve {ledger.get('always_preserve_count')}",
        f"satellite: flood/heat/green context from ~1km cell "
        f"(built {_r1(ind.get('impervious_pct'))}%, veg "
        f"{_r1(ind.get('vegetation_pct'))}%, night LST "
        f"{_r1(ind.get('lst_night_mean_c'))}C); carbon is per-BOQ, "
        f"not spatial.",
        *_fmt_blockers(score),
        "",
        f"Write for role '{role}'. Structure: 1) one-line verdict for the "
        "file. 2) Why, factor by factor, each with its number. "
        "3) Conditions in order with measured effects. 4) Trees: what "
        "stays, what falls, the compensation range. 5) What is unknown "
        "or provisional, stated plainly. Plain officer English. No format "
        "experiments: headings + short paragraphs.",
    ]
    return "\n".join(parts)


def _gemini_post(url: str, key: str, prompt: str,
                 timeout: int = 60) -> str:
    """Thin REST transport. Key travels in the header, never the URL
    (URLs land in proxy/server logs). Returns raw prose."""
    body = json.dumps(
        {"contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {"temperature": 0.2,
                              # Narration needs almost no reasoning: cap the
                              # hidden thought budget (fixed 2026-10-10: the
                              # default ~2000-thought drain left ~80 tokens
                              # for prose and cut Ward-36 mid-sentence) and
                              # raise the ceiling so prose always fits.
                              "maxOutputTokens": 4096,
                              "thinkingConfig": {"thinkingBudget": 512}}
         }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"unexpected Gemini response shape: {data!r:.300}") \
            from e


def narrate(assessment: Dict[str, Any], role: str = "urban_planner",
            model: str = GEMINI_MODEL, key: Optional[str] = None,
            post: Optional[Callable[[str, str, str], str]] = None,
            timeout: int = 60) -> str:
    """Full path: prompt builder + transport. `post` stub injects tests."""
    prompt = build_prompt(assessment, role)
    key = key or load_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY absent (env and .env). "
                           "Ask the human to provision it; never paste it "
                           "into chat.")
    sender = post or (lambda u, k, p: _gemini_post(u, k, p, timeout))
    return sender(GEMINI_URL.format(model=model), key, prompt)


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: narrative.py ASSESS_JSON [--role ROLE] [--model M]")
        return 2
    path = argv[0]
    role, model = "urban_planner", GEMINI_MODEL
    for i, a in enumerate(argv[1:]):
        if a == "--role" and i + 2 <= len(argv[1:]):
            role = argv[1:][i + 1]
        if a == "--model" and i + 2 <= len(argv[1:]):
            model = argv[1:][i + 1]
    with open(path) as f:
        assessment = json.load(f)
    print(narrate(assessment, role, model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
