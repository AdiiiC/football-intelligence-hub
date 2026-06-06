"""
Transfer price predictor — XGBoost-based model to estimate fee range.
Falls back to market value heuristics if model is not trained yet.
"""

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

MODEL_DIR = Path("models/artifacts")
MODEL_FILE = MODEL_DIR / "price_model.pkl"
SCALER_FILE = MODEL_DIR / "price_scaler.pkl"

FEATURE_COLS = [
    "market_value_m",
    "age",
    "contract_years_remaining",
    "performance_percentile",
    "league_difficulty",
    "recent_form_xg",
    "position_scarcity",
    "rumour_clubs_count",
]

LEAGUE_DIFFICULTY = {
    "Premier League": 1.0,
    "La Liga": 0.95,
    "Bundesliga": 0.88,
    "Serie A": 0.85,
    "Ligue 1": 0.80,
}

POSITION_SCARCITY = {
    "GK": 0.6,
    "CB": 0.7,
    "FB": 0.75,
    "DM": 0.8,
    "CM": 0.85,
    "AM": 0.9,
    "Winger": 0.95,
    "ST": 1.0,
}


def _extract_contract_years(contract_expiry: str, current_year: int = 2025) -> float:
    """Extract number of years remaining from contract expiry string."""
    if not contract_expiry:
        return 1.0
    import re
    m = re.search(r"(\d{4})", str(contract_expiry))
    if m:
        return max(0.0, float(int(m.group(1)) - current_year))
    return 1.0


def build_feature_vector(
    player: dict,
    league_name: str,
    performance_percentile: float = 50.0,
    recent_form_xg: float = 0.0,
    rumour_clubs: int = 0,
) -> np.ndarray:
    """
    Build feature vector for a player for price prediction.
    """
    age = int(player.get("age", 25)) if str(player.get("age", "25")).isdigit() else 25
    mv = float(player.get("market_value_m", 10.0))
    contract_yrs = _extract_contract_years(player.get("contract_expiry", ""))
    pos_group = player.get("position_group", "CM")

    features = np.array([
        mv,
        age,
        contract_yrs,
        performance_percentile,
        LEAGUE_DIFFICULTY.get(league_name, 0.85),
        recent_form_xg,
        POSITION_SCARCITY.get(pos_group, 0.8),
        float(rumour_clubs),
    ], dtype=float)

    return features


def _heuristic_prediction(player: dict, league_name: str, performance_percentile: float) -> dict:
    """
    Rule-based fallback when ML model is not available.
    Uses market value + adjustment factors.
    """
    mv = float(player.get("market_value_m", 10.0))
    age = int(player.get("age", 25)) if str(player.get("age", "25")).isdigit() else 25
    contract_yrs = _extract_contract_years(player.get("contract_expiry", ""))
    pos_group = player.get("position_group", "CM")

    # Age adjustment factor (peaks 24-27)
    if age <= 23:
        age_factor = 1.15
    elif age <= 27:
        age_factor = 1.10
    elif age <= 29:
        age_factor = 1.0
    elif age <= 31:
        age_factor = 0.85
    else:
        age_factor = 0.70

    # Contract leverage
    if contract_yrs >= 4:
        contract_factor = 1.15
    elif contract_yrs >= 2:
        contract_factor = 1.05
    elif contract_yrs >= 1:
        contract_factor = 0.90
    else:
        contract_factor = 0.70

    # Performance premium
    perf_factor = 0.85 + (performance_percentile / 100) * 0.40

    # Demand premium
    league_factor = LEAGUE_DIFFICULTY.get(league_name, 0.85)

    base_fee = mv * age_factor * contract_factor * perf_factor * league_factor

    lower = round(base_fee * 0.75, 1)
    median = round(base_fee, 1)
    upper = round(base_fee * 1.30, 1)

    reasoning = [
        f"Base market value: €{mv}m",
        f"Age factor ({age}y): ×{age_factor}",
        f"Contract leverage ({contract_yrs:.1f}yr remaining): ×{contract_factor}",
        f"Performance premium ({performance_percentile:.0f}th pct): ×{perf_factor:.2f}",
        f"Origin league strength: ×{league_factor}",
    ]

    return {
        "lower_m": lower,
        "median_m": median,
        "upper_m": upper,
        "confidence": "Heuristic estimate",
        "reasoning": reasoning,
        "method": "rules",
    }


def predict_transfer_fee(
    player: dict,
    league_name: str,
    performance_percentile: float = 50.0,
    recent_form_xg: float = 0.0,
    rumour_clubs: int = 0,
) -> dict:
    """
    Predict transfer fee for a player.
    Returns {lower_m, median_m, upper_m, confidence, reasoning}.
    """
    # Try ML model first
    if MODEL_FILE.exists() and SCALER_FILE.exists():
        try:
            import joblib
            model = joblib.load(MODEL_FILE)
            scaler = joblib.load(SCALER_FILE)
            features = build_feature_vector(player, league_name, performance_percentile, recent_form_xg, rumour_clubs)
            features_scaled = scaler.transform(features.reshape(1, -1))
            pred_log = model.predict(features_scaled)[0]
            pred = float(np.expm1(pred_log))  # inverse log1p transform

            return {
                "lower_m": round(pred * 0.75, 1),
                "median_m": round(pred, 1),
                "upper_m": round(pred * 1.30, 1),
                "confidence": "ML model (XGBoost)",
                "reasoning": [f"XGBoost prediction based on {len(FEATURE_COLS)} features"],
                "method": "ml",
            }
        except Exception:
            pass

    return _heuristic_prediction(player, league_name, performance_percentile)


def train_model_from_csv(csv_path: str) -> bool:
    """
    Train the XGBoost model from a historical transfers CSV.
    Expected columns: player, age, market_value_m, fee_m, contract_years,
                      performance_pct, league, position_group, rumour_clubs.
    Returns True on success.
    """
    try:
        import joblib
        from sklearn.preprocessing import StandardScaler
        from xgboost import XGBRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_error

        df = pd.read_csv(csv_path)
        required = ["fee_m", "market_value_m", "age"]
        for col in required:
            if col not in df.columns:
                return False

        # Fill missing features with defaults
        df["contract_years_remaining"] = df.get("contract_years", pd.Series([2.0] * len(df)))
        df["performance_percentile"] = df.get("performance_pct", pd.Series([50.0] * len(df)))
        df["league_difficulty"] = df.get("league", pd.Series(["Premier League"] * len(df))).map(
            lambda x: LEAGUE_DIFFICULTY.get(x, 0.85)
        )
        df["recent_form_xg"] = df.get("recent_form_xg", pd.Series([0.3] * len(df)))
        df["position_scarcity"] = df.get("position_group", pd.Series(["CM"] * len(df))).map(
            lambda x: POSITION_SCARCITY.get(x, 0.8)
        )
        df["rumour_clubs_count"] = df.get("rumour_clubs", pd.Series([1.0] * len(df)))

        X = df[FEATURE_COLS].fillna(0).values
        y = np.log1p(df["fee_m"].fillna(0).values)

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, random_state=42)
        model.fit(X_train_s, y_train, eval_set=[(X_test_s, y_test)], verbose=False)

        mae = mean_absolute_error(np.expm1(y_test), np.expm1(model.predict(X_test_s)))
        print(f"Model trained — MAE: €{mae:.1f}m")

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, MODEL_FILE)
        joblib.dump(scaler, SCALER_FILE)
        return True

    except Exception as e:
        print(f"Training failed: {e}")
        return False
