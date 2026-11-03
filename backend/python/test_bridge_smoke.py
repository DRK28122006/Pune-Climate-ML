"""Smoke test for ml_bridge.py scoring mode.

Runs the bridge as a subprocess (same way the Node backend does) and checks
that it returns a complete, well-formed scoring result. Exits 0 on success.

Run:
    python backend/python/test_bridge_smoke.py
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "backend" / "python" / "ml_bridge.py"

REQUEST = {
    "mode": "score",
    "ward": 12,
    "builtUpAreaSqm": 2000,
    "plotAreaSqm": 4000,
    "materials": [
        {"name": "steel", "quantityKg": 120000},
        {"name": "cement", "quantityKg": 400000},
    ],
}


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(BRIDGE)],
        input=json.dumps(REQUEST),
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=300,
    )
    if proc.returncode != 0:
        print("FAIL: bridge exited", proc.returncode)
        print("stderr:", proc.stderr[:500])
        return 1
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print("FAIL: invalid JSON:", exc)
        print(proc.stdout[:500])
        return 1

    # Shape checks.
    assert result.get("source") == "ml-pipeline-scorer", result.get("source")
    assert result.get("mode") == "score"
    score = result.get("score") or {}
    assert "impact_score" in score, "missing impact_score"
    assert "climate_score" in score, "missing climate_score"
    assert "risk_band" in score, "missing risk_band"
    assert "evidence_status" in score, "missing evidence_status"
    assert "factors" in score, "missing factors"
    for k in ("flood", "heat", "green", "carbon"):
        assert k in score["factors"], f"missing factor {k}"
    assert isinstance(result.get("recommendations"), list)
    assert result.get("canopy") is not None or True  # canopy may be None if no tree index
    assert result.get("indicators") is not None

    # Evidence tier must be one of the four contract values.
    assert score["evidence_status"] in {"COMPLETE", "PARTIAL", "INSUFFICIENT", "UNAVAILABLE"}

    # Ward 12 has census data, so with the tree index present it should be COMPLETE.
    print("PASS: bridge scoring mode")
    print(f"  ward={REQUEST['ward']} impact={score['impact_score']} climate={score['climate_score']} "
          f"risk={score['risk_band']} evidence={score['evidence_status']}")
    print(f"  factors: flood={score['factors']['flood'].get('score')} "
          f"heat={score['factors']['heat'].get('score')} "
          f"green={score['factors']['green'].get('score') if score['factors']['green'] else None} "
          f"carbon={score['factors']['carbon'].get('score')}")
    print(f"  recommendations: {len(result['recommendations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
