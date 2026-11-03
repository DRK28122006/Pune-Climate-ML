"""Verify or refresh the 2024 heat corroboration.

Default mode is offline: it reads the tracked summary JSON, recomputes the
Spearman rho and the 10,000-shuffle permutation p, and compares them with the
stored values.  `--refresh` re-fetches Open-Meteo 2024 hourly 2 m temperature
for the 41 ward centroids, rebuilds the CSV + JSON, and recomputes.

Run:
    python ml_pipeline/data/heat_crosscheck.py
    python ml_pipeline/data/heat_crosscheck.py --refresh

The correlation is corroboration only.  Night LST remains the only heat input;
2 m air temperature is never substituted into the 0-100 heat factor.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CSV = REPO / "ml_pipeline" / "data" / "heat_crosscheck_2024.csv"
JSON = REPO / "ml_pipeline" / "data" / "heat_crosscheck_2024.json"
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
REF_DB = REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"
WARD_VALIDATION = REPO / "ml_pipeline" / "data" / "ward_validation.json"

NIGHT_HOURS = {22, 23, 0, 1, 2, 3, 4, 5}
N_PERM = 10000
SEED = 42
CSV_FIELDS = [
    "ward", "lat", "lon", "n_hours", "night_mean_c", "annual_mean_c",
    "source", "retrieved_at", "licence",
]


def _ranks(values: List[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def _spearman(xs: List[float], ys: List[float]) -> float:
    return _pearson(_ranks(xs), _ranks(ys))


def _perm_p(xs: List[float], ys: List[float], observed: float) -> float:
    rng = random.Random(SEED)
    count = 0
    rx = _ranks(xs)
    for _ in range(N_PERM):
        shuffled = list(ys)
        rng.shuffle(shuffled)
        if abs(_pearson(rx, _ranks(shuffled))) >= abs(observed):
            count += 1
    return (count + 1) / (N_PERM + 1)


def _asymptotic_p(rho: float, n: int) -> Tuple[float, str]:
    if n <= 2:
        return 1.0, "n<=2"
    dof = n - 2
    t_stat = abs(rho) * math.sqrt(dof / max(1e-12, 1.0 - rho * rho))
    try:
        from scipy.stats import t as t_dist

        return float(2.0 * t_dist.sf(t_stat, dof)), "scipy t"
    except Exception:
        # Normal approximation; labelled so it cannot be mistaken for the
        # scipy value stored in the JSON.
        p = 2.0 * (1.0 - statistics.NormalDist().cdf(abs(rho) * math.sqrt(n - 1)))
        return float(p), "normal approx"


def _pairs(rows: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    pairs = [
        (float(r["lst_night_mean_c"]), float(r["night_mean_c"]))
        for r in rows
        if r.get("lst_night_mean_c") is not None
        and r.get("night_mean_c") is not None
    ]
    return [a for a, _ in pairs], [b for _, b in pairs]


def _verify() -> int:
    if not JSON.exists():
        print(f"FAIL: summary JSON missing at {JSON}")
        return 1
    data = json.loads(JSON.read_text())
    rows = data.get("rows") or []
    xs, ys = _pairs(rows)
    n = len(xs)
    if n < 5:
        print(f"FAIL: only {n} paired rows")
        return 1

    rho = _spearman(xs, ys)
    perm = _perm_p(xs, ys, rho)
    p_asym, p_label = _asymptotic_p(rho, n)

    stored_rho = float(data.get("rho"))
    stored_perm = float(data.get("p_permutation_10000"))
    stored_p = float(data.get("p_asymptotic"))

    print("HEAT CROSS-CHECK — verify")
    print(f"  rows          : {len(rows)}  pairs {n}")
    print(f"  rho           : {rho:.6f}  stored {stored_rho:.6f}")
    print(f"  p permutation : {perm:.6f}  stored {stored_perm:.6f}")
    print(f"  p asymptotic  : {p_asym:.6f} ({p_label})  stored {stored_p:.6f}")

    ok = (
        len(rows) == 41
        and n == 41
        and abs(rho - stored_rho) < 1e-4
        and abs(perm - stored_perm) < 1e-4
    )

    if CSV.exists():
        csv_rows = list(csv.DictReader(CSV.open()))
        print(f"  csv rows      : {len(csv_rows)}")
        if len(csv_rows) != len(rows):
            ok = False
        by_ward = {int(r["ward"]): r for r in rows}
        for row in csv_rows:
            ward = int(row["ward"])
            ref = by_ward.get(ward)
            if ref is None or abs(float(row["night_mean_c"]) - float(ref["night_mean_c"])) > 0.001:
                ok = False
                break
    else:
        print(f"  csv           : missing at {CSV}")
        ok = False

    print("  verdict       : " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def _ward_rings() -> Dict[int, List[Any]]:
    import sqlite3

    if not REF_DB.exists():
        raise SystemExit(f"reference layer missing at {REF_DB}")
    conn = sqlite3.connect(f"file:{REF_DB}?mode=ro", uri=True)
    try:
        return {
            int(ward): json.loads(ring_json)
            for ward, ring_json in conn.execute(
                "SELECT ward_no, ring_json FROM wards"
            )
        }
    finally:
        conn.close()


def _centroid(ring: List[Any]) -> Tuple[float, float]:
    from shapely.geometry import Polygon

    poly = Polygon(ring)
    if not poly.is_valid or poly.is_empty:
        poly = poly.buffer(0)
    c = poly.centroid
    return float(c.x), float(c.y)


def _area_weighted_lst(ring: List[Any], cube: Dict[str, Any]) -> Optional[float]:
    from ml_pipeline.data import validate_wards as VW

    agg = VW._cells_for_ward(ring, cube)
    indicators = (agg or {}).get("indicators") or {}
    value = indicators.get("lst_night_mean_c")
    return float(value) if value is not None else None


def _fetch_openmeteo(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        "&start_date=2024-01-01&end_date=2024-12-31"
        "&hourly=temperature_2m&timezone=Asia%2FKolkata"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read())
        except Exception:
            time.sleep(5)
    return None


def _night_and_annual(obj: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], int]:
    hourly = obj.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    night: List[float] = []
    all_vals: List[float] = []
    for stamp, value in zip(times, temps):
        if value is None:
            continue
        all_vals.append(float(value))
        try:
            hour = int(stamp[11:13])
        except (ValueError, IndexError):
            continue
        if hour in NIGHT_HOURS:
            night.append(float(value))
    night_mean = sum(night) / len(night) if night else None
    annual_mean = sum(all_vals) / len(all_vals) if all_vals else None
    return night_mean, annual_mean, len(night)


def _refresh() -> int:
    rings = _ward_rings()
    cube = json.loads(CUBE.read_text())
    validation: Dict[int, float] = {}
    if WARD_VALIDATION.exists():
        for row in json.loads(WARD_VALIDATION.read_text()).get("rows", []):
            if row.get("lst_night_mean_c") is not None:
                validation[int(row["ward"])] = float(row["lst_night_mean_c"])

    retrieved_at = datetime.now(timezone.utc).date().isoformat()
    rows: List[Dict[str, Any]] = []
    for ward in sorted(rings):
        ring = rings[ward]
        lon, lat = _centroid(ring)
        lst = validation.get(ward)
        if lst is None:
            lst = _area_weighted_lst(ring, cube)

        obj = _fetch_openmeteo(lat, lon)
        if obj is None:
            print(f"ward {ward}: fetch failed")
            night_mean, annual_mean, n_hours, source = None, None, 0, "UNAVAILABLE"
        else:
            if isinstance(obj, list):
                obj = obj[0]
            night_mean, annual_mean, n_hours = _night_and_annual(obj)
            source = "open-meteo-archive"
        rows.append({
            "ward": ward,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "n_hours": n_hours,
            "night_mean_c": round(night_mean, 3) if night_mean is not None else None,
            "annual_mean_c": round(annual_mean, 3) if annual_mean is not None else None,
            "lst_night_mean_c": round(lst, 3) if lst is not None else None,
            "source": source,
            "retrieved_at": retrieved_at,
            "licence": "Open-Meteo (CC BY 4.0)",
        })
        print(
            f"ward {ward}: lat {lat:.4f} lon {lon:.4f} "
            f"n_hours {n_hours} night_mean {night_mean} lst_night {lst}"
        )
        time.sleep(0.5)

    with CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in CSV_FIELDS})

    xs, ys = _pairs(rows)
    n = len(xs)
    rho = _spearman(xs, ys)
    perm = _perm_p(xs, ys, rho)
    p_asym, p_label = _asymptotic_p(rho, n)

    summary = {
        "n": n,
        "rho": rho,
        "p_asymptotic": p_asym,
        "p_asymptotic_method": p_label,
        "p_permutation_10000": perm,
        "night_hours": sorted(NIGHT_HOURS),
        "source": "open-meteo-archive",
        "retrieved_at": retrieved_at,
        "licence": "Open-Meteo (CC BY 4.0)",
        "rows": rows,
    }
    JSON.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {CSV}")
    print(f"wrote {JSON}")
    print(f"n {n}  rho {rho:.6f}  p_perm {perm:.6f}  p_asym {p_asym:.6f} ({p_label})")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="heat_crosscheck")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch Open-Meteo 2024 and rewrite the CSV + JSON",
    )
    args = ap.parse_args(argv)
    return _refresh() if args.refresh else _verify()


if __name__ == "__main__":
    raise SystemExit(main())
