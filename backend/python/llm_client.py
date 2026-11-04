"""Shared LLM client with a provider chain: Groq first, Gemini as fallback.

Both bridges call the chain instead of Gemini directly. Groq's free tier
(30 req/min, ~1,000 req/day per model) is ample for permit intake; Gemini is
kept as the second provider so the assistant keeps working if Groq rate-limits.
If every provider fails the caller raises and the bridge emits its honest
offline fallback — never a disguised reply.

Environment (backend/.env):
  GROQ_API_KEY   — required for the primary provider
  GROQ_MODEL     — optional, defaults to qwen/qwen3.8-27b
  GEMINI_API_KEY — required for the fallback provider
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

# Groq sits behind Cloudflare; Python's default UA is blocked (error 1010).
# Send a browser-like UA instead.
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"


def _groq_key():
    return os.environ.get("GROQ_API_KEY")


def _gemini_key():
    val = os.environ.get("GEMINI_API_KEY")
    if val:
        return val.strip()
    try:
        from ml_pipeline.report.narrative import load_key
        return load_key()
    except Exception:
        return None


def call_groq(prompt, *, json_mode=True, temperature=0.2, max_tokens=4096, timeout=60):
    key = _groq_key()
    if not key:
        raise RuntimeError("GROQ_API_KEY not configured")
    model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    last_error = None
    for attempt in range(2):
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            _GROQ_URL,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": _UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            text = (data["choices"][0]["message"].get("content") or "").strip()
            if not text:
                # Reasoning models can spend the whole budget on thought.
                raise RuntimeError("empty completion (raise max_tokens)")
            return text, "groq"
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 and attempt == 0:
                # Groq sets retry-after; honour it briefly rather than fail over instantly.
                try:
                    wait = float((e.headers or {}).get("retry-after") or 0)
                except Exception:
                    wait = 0
                time.sleep(min(wait if wait > 0 else 5, 20))
                continue
            if e.code in (500, 502, 503) and attempt == 0:
                time.sleep(4)
                continue
            detail = ""
            try:
                detail = e.read().decode()[:200]
            except Exception:
                pass
            raise RuntimeError(f"groq HTTP {e.code}: {detail}") from e
        except Exception as e:
            last_error = e
            if attempt == 0:
                time.sleep(2)
                continue
            raise
    raise last_error  # unreachable


def call_gemini(prompt, *, json_mode=True, temperature=0.2, max_tokens=4096, timeout=45):
    key = _gemini_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    last_error = None
    for attempt in range(2):
        generation = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            generation["responseMimeType"] = "application/json"
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }).encode()
        req = urllib.request.Request(
            _GEMINI_URL,
            data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": key, "User-Agent": _UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            text = (data["candidates"][0]["content"]["parts"][0]["text"] or "").strip()
            if not text:
                raise RuntimeError("empty completion")
            return text, "gemini"
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in (429, 500, 502, 503) and attempt == 0:
                time.sleep(5)
                continue
            raise RuntimeError(f"gemini HTTP {e.code}") from e
        except Exception as e:
            last_error = e
            if attempt == 0:
                time.sleep(3)
                continue
            raise
    raise last_error  # unreachable


def call_llm(prompt, *, json_mode=True, temperature=0.2, max_tokens=4096):
    """Try Groq, then Gemini. Raises RuntimeError with both errors if all fail."""
    errors = []
    for provider in (call_groq, call_gemini):
        try:
            return provider(prompt, json_mode=json_mode, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            errors.append(f"{provider.__name__.replace('call_', '')}: {e}")
    raise RuntimeError("all providers failed — " + " | ".join(errors))


def extract_json(text):
    """Parse JSON from a completion; tolerate fences and nested braces."""
    raw = text.strip()
    # strip ``` fences if present
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.S)
    if fence:
        raw = fence.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None
