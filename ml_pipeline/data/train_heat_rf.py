"""Heat downscaling model: land cover -> MODIS night LST.

Trains on ml_pipeline/data/kaggle_heat_train.csv (864 cells, summer night
means). Predicts TEMPERATURE only -- never a score. Outputs feed
compute_heat with error bars; gates fall back to 1km MODIS when MAE is bad.

Protocol (no exceptions):
- split by WARD cluster (whole wards held out), never random rows.
- must beat the no-ML baseline (rural 20.23 + ward offset) or it ships nothing.
- bars: held-out MAE < 1.0 C and r > 0.65.

Usage:
    .venv/bin/python ml_pipeline/data/train_heat_rf.py
Outputs: ml_pipeline/data/heat_rf_model.json, heat_holdout_pred.csv
"""
import csv
import json
import math
import os
import statistics

DATA = os.path.join(os.path.dirname(__file__), "kaggle_heat_train.csv")
FEATS = [
    "built_pct", "vegetation_pct", "tree_canopy_pct", "water_pct",
    "bare_pct", "bare_season_pct", "elevation_m",
]
TARGET = "lst_night_mean_c"
RURAL_REF = 20.23  # summer true-rural vegetated ring median, measured GEE

HOLDOUT_WARDS = {3, 7, 13, 21, 25, 29, 5, 17, 33, 9, 40}  # 11 whole wards


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    return sum(a * b for a, b in zip(dx, dy)) / den if den else float("nan")


def load():
    rows = []
    with open(DATA) as f:
        for r in csv.DictReader(f):
            try:
                x = [float(r[k]) for k in FEATS]
                y = float(r[TARGET])
                w = int(r["ward"]) if r["ward"] else None
            except (ValueError, TypeError):
                continue
            rows.append({"x": x, "y": y, "ward": w, "id": r["cell_id"]})
    return rows


def ridge_fit(X, y, lam=1.0):
    import numpy as np

    X1 = np.hstack([np.ones((len(X), 1)), np.asarray(X)])
    yv = np.asarray(y)
    A = X1.T @ X1 + lam * np.eye(X1.shape[1])
    A[0, 0] -= lam  # do not penalise the intercept
    return np.linalg.solve(A, X1.T @ yv)


def ridge_pred(beta, X):
    import numpy as np

    X1 = np.hstack([np.ones((len(X), 1)), np.asarray(X)])
    return (X1 @ np.asarray(beta)).tolist()


def main():
    rows = load()
    train = [r for r in rows if r["ward"] not in HOLDOUT_WARDS]
    test = [r for r in rows if r["ward"] in HOLDOUT_WARDS]
    print(f"train {len(train)} / held-out {len(test)} rows "
          f"({len(HOLDOUT_WARDS)} whole wards)")

    # Baseline: rural reference + ward-mean offset from TRAIN wards only.
    ward_mean = {}
    for r in train:
        if r["ward"] is not None:
            ward_mean.setdefault(r["ward"], []).append(r["y"] - RURAL_REF)
    ward_off = {w: statistics.mean(v) for w, v in ward_mean.items()}
    global_off = statistics.mean([r["y"] - RURAL_REF for r in train])
    base = [RURAL_REF + ward_off.get(r["ward"], global_off) for r in test]
    yt = [r["y"] for r in test]
    base_mae = statistics.mean(abs(a - b) for a, b in zip(base, yt))
    print(f"BASELINE (rural+ward offset): MAE={base_mae:.3f} C")

    # Ridge (numpy, no extra deps).
    beta = ridge_fit([r["x"] for r in train], [r["y"] for r in train])
    pred = ridge_pred(beta, [r["x"] for r in test])
    mae = statistics.mean(abs(a - b) for a, b in zip(pred, yt))
    r = pearson(pred, yt)
    print(f"RIDGE: MAE={mae:.3f} C  r={r:+.4f}")
    print("coefficients (intercept first):",
          [round(float(b), 4) for b in beta])

    out = {
        "model": "ridge",
        "features": FEATS,
        "rural_ref": RURAL_REF,
        "holdout_wards": sorted(HOLDOUT_WARDS),
        "baseline_mae": base_mae,
        "mae": mae,
        "r": r,
        "intercept": float(beta[0]),
        "coefficients": [float(b) for b in beta[1:]],
    }

    # Random Forest when sklearn is available; same split, same bars.
    try:
        from sklearn.ensemble import RandomForestRegressor

        rf = RandomForestRegressor(
            n_estimators=400, min_samples_leaf=5, random_state=2024, n_jobs=-1
        )
        rf.fit([r["x"] for r in train], [r["y"] for r in train])
        rp = rf.predict([r["x"] for r in test]).tolist()
        rmae = statistics.mean(abs(a - b) for a, b in zip(rp, yt))
        rr = pearson(rp, yt)
        print(f"RANDOM FOREST: MAE={rmae:.3f} C  r={rr:+.4f}")
        print("importances:",
              {k: round(float(v), 3) for k, v in zip(FEATS, rf.feature_importances_)})
        if rmae < mae:
            out.update({
                "model": "random_forest",
                "mae": rmae,
                "r": rr,
                "n_estimators": 400,
                "min_samples_leaf": 5,
            })
            import pickle

            with open(os.path.join(os.path.dirname(__file__),
                                   "heat_rf_model.pkl"), "wb") as f:
                pickle.dump(rf, f)
            print("saved heat_rf_model.pkl")
            pred = rp
    except ImportError:
        print("sklearn absent: RF skipped (ridge stands alone)")

    ok = out["mae"] < 1.0 and out["r"] > 0.65 and out["mae"] < base_mae
    print(f"VERDICT: {'SHIPPABLE' if ok else 'NOT SHIPPABLE'} "
          f"(bars: MAE<1.0, r>0.65, beats baseline {base_mae:.3f})")

    with open(os.path.join(os.path.dirname(__file__),
                           "heat_rf_model.json"), "w") as f:
        json.dump(out, f, indent=2)
    with open(os.path.join(os.path.dirname(__file__),
                           "heat_holdout_pred.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cell_id", "ward", "observed", "predicted"])
        for r, p in zip(test, pred):
            w.writerow([r["id"], r["ward"], round(r["y"], 3), round(p, 3)])
    print("wrote heat_rf_model.json + heat_holdout_pred.csv")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
