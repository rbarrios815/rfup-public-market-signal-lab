from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
OUTPUT_DIR = ROOT / "docs" / "data"
USER_AGENT = "RFUP-Public-Market-Signal-Lab/1.1 research-contact rbarrio1@alumni.nd.edu"

FRED_SERIES = {
    "vix": "VIXCLS",
    "ust_2y": "DGS2",
    "ust_10y": "DGS10",
    "ust_30y": "DGS30",
    "curve_10y_2y": "T10Y2Y",
    "ig_oas": "BAMLC0A0CM",
    "hy_oas": "BAMLH0A0HYM2",
    "wti": "DCOILWTICO",
    "dollar": "DTWEXBGS",
}

FEATURE_COLUMNS = [
    "return_1d", "return_5d", "return_20d", "realized_vol_20d",
    "velocity", "acceleration", "jerk", "opposite_velocity",
    "opposite_acceleration", "ma_distance_20", "ma_distance_50",
    "ma_distance_200", "distance_to_20d_high", "distance_to_20d_low",
    "distance_to_60d_high", "distance_to_60d_low", "volume_z_20",
    "vix", "vix_change_1d", "ust_2y", "ust_10y", "ust_30y",
    "curve_10y_2y", "ig_oas", "ig_oas_change_5d", "hy_oas",
    "hy_oas_change_5d", "wti_change_5d", "dollar_change_5d",
]

FEATURE_GROUPS = {
    "returns_and_volatility": [
        "return_1d", "return_5d", "return_20d", "realized_vol_20d",
    ],
    "derivatives": [
        "velocity", "acceleration", "jerk",
        "opposite_velocity", "opposite_acceleration",
    ],
    "trend_range_and_volume": [
        "ma_distance_20", "ma_distance_50", "ma_distance_200",
        "distance_to_20d_high", "distance_to_20d_low",
        "distance_to_60d_high", "distance_to_60d_low", "volume_z_20",
    ],
    "macro_credit_cross_asset": [
        "vix", "vix_change_1d", "ust_2y", "ust_10y", "ust_30y",
        "curve_10y_2y", "ig_oas", "ig_oas_change_5d", "hy_oas",
        "hy_oas_change_5d", "wti_change_5d", "dollar_change_5d",
    ],
}

FEATURE_SOURCE = {
    "vix": "vix", "vix_change_1d": "vix",
    "ust_2y": "ust_2y", "ust_10y": "ust_10y", "ust_30y": "ust_30y",
    "curve_10y_2y": "curve_10y_2y",
    "ig_oas": "ig_oas", "ig_oas_change_5d": "ig_oas",
    "hy_oas": "hy_oas", "hy_oas_change_5d": "hy_oas",
    "wti_change_5d": "wti", "dollar_change_5d": "dollar",
}


@dataclass(frozen=True)
class Config:
    target_symbol: str
    minimum_training_days: int
    retrain_frequency_days: int
    transaction_cost_bps: float
    entry_quantile: float
    exit_quantile: float
    google_sheet_id: str
    google_sheet_url: str
    price_provider: str
    stooq_symbol: str
    exchange_calendar: str

    @classmethod
    def load(cls) -> "Config":
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return cls(
            target_symbol=str(raw.get("target_symbol", "SPY")),
            minimum_training_days=int(raw.get("minimum_training_days", 756)),
            retrain_frequency_days=int(raw.get("retrain_frequency_days", 21)),
            transaction_cost_bps=float(raw.get("transaction_cost_bps", 2.0)),
            entry_quantile=float(raw.get("entry_quantile", 0.65)),
            exit_quantile=float(raw.get("exit_quantile", 0.35)),
            google_sheet_id=str(raw.get("google_sheet_id", "")),
            google_sheet_url=str(raw.get("google_sheet_url", "")),
            price_provider=str(raw.get("price_provider", "auto")),
            stooq_symbol=str(raw.get("stooq_symbol", "spy.us")),
            exchange_calendar=str(raw.get("exchange_calendar", "XNYS")),
        )


def request_csv(url: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv,*/*"},
        timeout=45,
    )
    response.raise_for_status()
    text = response.text
    if "Thank you for using Alpha Vantage" in text or "Information" in text[:120]:
        raise RuntimeError("Provider returned a rate-limit or information response.")
    return pd.read_csv(StringIO(text))


def request_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if "error_code" in payload or "error_message" in payload:
        raise RuntimeError(payload.get("error_message") or str(payload))
    return payload


def _normalize_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise RuntimeError(f"Price feed missing columns: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in required - {"date"}:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).drop_duplicates("date").sort_values("date")
    return frame.set_index("date")


def fetch_price(config: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if api_key and config.price_provider.lower() in {"auto", "alpha_vantage"}:
        frame = request_csv(
            "https://www.alphavantage.co/query",
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": config.target_symbol,
                "outputsize": "full",
                "datatype": "csv",
                "apikey": api_key,
            },
        )
        source = "Alpha Vantage TIME_SERIES_DAILY"
    else:
        frame = request_csv(f"https://stooq.com/q/d/l/?s={config.stooq_symbol}&i=d")
        source = "Stooq daily CSV fallback"

    return _normalize_price_frame(frame), {
        "source": source,
        "status": "ok",
        "requested_symbol": config.target_symbol,
        "effective_symbol": config.target_symbol,
        "effective_name": f"{config.target_symbol} ETF",
        "is_tradeable": True,
        "proxy_for_requested_target": False,
    }


def fetch_fred_series(series_id: str, output_name: str, *, initial_release: bool = False) -> pd.DataFrame:
    if initial_release:
        api_key = os.getenv("FRED_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("FRED_API_KEY is required for ALFRED initial-release observations.")
        payload = request_json(
            "https://api.stlouisfed.org/fred/series/observations",
            {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "output_type": 4,
                "observation_start": "2005-01-01",
                "sort_order": "asc",
            },
        )
        rows = payload.get("observations", [])
        frame = pd.DataFrame(
            [{"date": row.get("date"), output_name: row.get("value")} for row in rows]
        )
    else:
        frame = request_csv("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": series_id})
        date_column = next(
            (c for c in frame.columns if c.upper() in {"DATE", "OBSERVATION_DATE"}),
            frame.columns[0],
        )
        value_column = next((c for c in frame.columns if c != date_column), None)
        if value_column is None:
            raise RuntimeError(f"FRED {series_id} returned no value column.")
        frame = frame.rename(columns={date_column: "date", value_column: output_name})

    if frame.empty:
        raise RuntimeError(f"FRED {series_id} returned no observations.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame[output_name] = pd.to_numeric(frame[output_name], errors="coerce")
    return frame.dropna(subset=["date"]).drop_duplicates("date").set_index("date")[[output_name]]


def fetch_all_data(config: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    price, price_status = fetch_price(config)
    joined = price.copy()
    status: dict[str, Any] = {"price": price_status}
    use_initial_release = bool(os.getenv("FRED_API_KEY", "").strip())

    for output_name, series_id in FRED_SERIES.items():
        try:
            if use_initial_release:
                series = fetch_fred_series(series_id, output_name, initial_release=True)
                series_status = {
                    "series_id": series_id,
                    "status": "ok",
                    "source": "ALFRED/FRED API initial-release observations",
                    "point_in_time": True,
                }
            else:
                series = fetch_fred_series(series_id, output_name)
                series_status = {
                    "series_id": series_id,
                    "status": "ok",
                    "source": "FRED current-history CSV",
                    "point_in_time": False,
                }
            joined = joined.join(series, how="left")
            status[output_name] = series_status
        except Exception as initial_error:
            if use_initial_release:
                try:
                    series = fetch_fred_series(series_id, output_name)
                    joined = joined.join(series, how="left")
                    status[output_name] = {
                        "series_id": series_id,
                        "status": "ok_with_revision_risk",
                        "source": "FRED current-history CSV fallback",
                        "point_in_time": False,
                        "message": f"ALFRED initial-release fetch failed: {initial_error}",
                    }
                    continue
                except Exception as fallback_error:
                    initial_error = RuntimeError(
                        f"ALFRED failed: {initial_error}; FRED fallback failed: {fallback_error}"
                    )
            joined[output_name] = np.nan
            status[output_name] = {
                "series_id": series_id,
                "status": "error",
                "point_in_time": False,
                "message": str(initial_error),
            }

    joined[list(FRED_SERIES)] = joined[list(FRED_SERIES)].ffill(limit=10)
    return joined.loc[joined.index >= pd.Timestamp("2005-01-01")], status


def engineer_features(raw: pd.DataFrame) -> pd.DataFrame:
    data = raw.copy()
    log_close = np.log(data["close"])
    data["return_1d"] = log_close.diff()
    data["return_5d"] = log_close.diff(5)
    data["return_20d"] = log_close.diff(20)
    data["realized_vol_20d"] = data["return_1d"].rolling(20).std() * math.sqrt(252)

    scale = data["return_1d"].rolling(60).std().replace(0, np.nan)
    data["velocity"] = data["return_1d"] / scale
    data["acceleration"] = data["velocity"].diff()
    data["jerk"] = data["acceleration"].diff()
    data["opposite_velocity"] = -data["velocity"]
    data["opposite_acceleration"] = -data["acceleration"]

    for window in (20, 50, 200):
        data[f"ma_distance_{window}"] = data["close"] / data["close"].rolling(window).mean() - 1
    for window in (20, 60):
        data[f"distance_to_{window}d_high"] = data["close"] / data["high"].rolling(window).max() - 1
        data[f"distance_to_{window}d_low"] = data["close"] / data["low"].rolling(window).min() - 1

    volume_std = data["volume"].rolling(20).std().replace(0, np.nan)
    data["volume_z_20"] = (data["volume"] - data["volume"].rolling(20).mean()) / volume_std
    data["vix_change_1d"] = data["vix"].diff()
    data["ig_oas_change_5d"] = data["ig_oas"].diff(5)
    data["hy_oas_change_5d"] = data["hy_oas"].diff(5)
    data["wti_change_5d"] = np.log(data["wti"]).diff(5)
    data["dollar_change_5d"] = np.log(data["dollar"]).diff(5)
    data["target_next_return"] = log_close.shift(-1) - log_close
    return data.replace([np.inf, -np.inf], np.nan)


def make_model() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("ridge", RidgeCV(alphas=np.logspace(-4, 4, 33))),
    ])


def raw_next_index(index: pd.DatetimeIndex, current: pd.Timestamp) -> pd.Timestamp | None:
    location = index.searchsorted(current, side="right")
    return None if location >= len(index) else index[location]


def next_exchange_session(origin_date: pd.Timestamp, calendar_name: str = "XNYS") -> pd.Timestamp:
    calendar = xcals.get_calendar(calendar_name)
    origin = pd.Timestamp(origin_date).normalize()
    sessions = calendar.sessions_in_range(origin + pd.Timedelta(days=1), origin + pd.Timedelta(days=14))
    if len(sessions) == 0:
        raise RuntimeError(f"No {calendar_name} session found within 14 days after {origin.date()}.")
    session = pd.Timestamp(sessions[0])
    if session.tzinfo is not None:
        session = session.tz_localize(None)
    return session.normalize()


def select_active_features(
    featured: pd.DataFrame,
    candidates: list[str],
    minimum_complete_rows: int,
) -> list[str]:
    available = [
        feature for feature in candidates
        if feature in featured.columns
        and int(featured[feature].notna().sum()) >= minimum_complete_rows
    ]
    required_columns = ["target_next_return", "close"]
    while available:
        complete_rows = int(featured.dropna(subset=available + required_columns).shape[0])
        if complete_rows >= minimum_complete_rows:
            return available
        missing_counts = {
            feature: int(featured[feature].isna().sum())
            for feature in available
        }
        available.remove(max(missing_counts, key=missing_counts.get))
    raise RuntimeError("No feature set has enough complete observations for walk-forward training.")


def walk_forward(
    features: pd.DataFrame,
    config: Config,
    feature_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, Pipeline]:
    feature_columns = feature_columns or FEATURE_COLUMNS
    usable = features.dropna(subset=feature_columns + ["target_next_return", "close"]).copy()
    required = max(config.minimum_training_days + 50, 900)
    if len(usable) < required:
        raise RuntimeError(f"Only {len(usable)} complete rows are available; at least {required} are required.")

    min_train = min(config.minimum_training_days, max(504, len(usable) // 2))
    model: Pipeline | None = None
    rows: list[dict[str, Any]] = []
    predicted_history: list[float] = []
    position = 0.0

    for i in range(min_train, len(usable)):
        if model is None or (i - min_train) % config.retrain_frequency_days == 0:
            model = make_model()
            model.fit(usable.iloc[:i][feature_columns], usable.iloc[:i]["target_next_return"])

        origin = usable.iloc[i]
        origin_date = usable.index[i]
        target_date = raw_next_index(features.index, origin_date)
        if target_date is None or target_date not in features.index:
            continue
        prediction = float(model.predict(origin[feature_columns].to_frame().T)[0])
        if len(predicted_history) >= 60:
            entry = float(pd.Series(predicted_history).quantile(config.entry_quantile))
            exit_ = float(pd.Series(predicted_history).quantile(config.exit_quantile))
        else:
            entry = exit_ = 0.0
        new_position = 1.0 if prediction > entry else 0.0 if prediction < exit_ else position
        signal = "ENTER" if position == 0 and new_position == 1 else "EXIT" if position == 1 and new_position == 0 else "HOLD"
        actual_return = float(origin["target_next_return"])
        rows.append({
            "date": target_date,
            "origin_date": origin_date,
            "actual_close": float(features.loc[target_date, "close"]),
            "predicted_close": float(origin["close"] * math.exp(prediction)),
            "actual_return": actual_return,
            "predicted_return": prediction,
            "origin_return_1d": float(origin["return_1d"]),
            "entry_threshold": entry,
            "exit_threshold": exit_,
            "signal": signal,
            "position": new_position,
            "velocity": float(origin["velocity"]),
            "acceleration": float(origin["acceleration"]),
            "jerk": float(origin["jerk"]),
            "opposite_velocity": float(origin["opposite_velocity"]),
        })
        predicted_history.append(prediction)
        position = new_position

    if model is None or not rows:
        raise RuntimeError("Walk-forward model produced no predictions.")
    result = pd.DataFrame(rows).set_index("date").sort_index()
    turnover = result["position"].diff().abs().fillna(result["position"].abs())
    costs = turnover * config.transaction_cost_bps / 10_000
    result["strategy_return"] = result["position"] * result["actual_return"] - costs
    result["benchmark_equity"] = np.exp(result["actual_return"].cumsum())
    result["strategy_equity"] = np.exp(result["strategy_return"].cumsum())
    result["residual"] = result["actual_return"] - result["predicted_return"]

    final_model = make_model()
    final_model.fit(usable[feature_columns], usable["target_next_return"])
    return result, final_model


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return float("nan")
    return float((equity.iloc[-1] / equity.iloc[0]) ** (252 / len(equity)) - 1)


def calculate_metrics(result: pd.DataFrame) -> dict[str, float]:
    error = result["actual_return"] - result["predicted_return"]
    active = result[result["signal"].isin(["ENTER", "EXIT"])]
    hit_rate = float("nan") if active.empty else float(np.mean(np.where(
        active["signal"].eq("ENTER"), active["actual_return"] > 0, active["actual_return"] <= 0
    )))
    return {
        "mae_return": float(np.mean(np.abs(error))),
        "rmse_return": float(np.sqrt(np.mean(error ** 2))),
        "directional_accuracy": float(np.mean(np.sign(result["actual_return"]) == np.sign(result["predicted_return"]))),
        "signal_hit_rate": hit_rate,
        "strategy_cagr": cagr(result["strategy_equity"]),
        "benchmark_cagr": cagr(result["benchmark_equity"]),
        "strategy_max_drawdown": max_drawdown(result["strategy_equity"]),
        "benchmark_max_drawdown": max_drawdown(result["benchmark_equity"]),
    }


def _prediction_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    error = actual - predicted
    return {
        "mae_return": float(np.mean(np.abs(error))),
        "rmse_return": float(np.sqrt(np.mean(error ** 2))),
        "directional_accuracy": float(np.mean(np.sign(actual) == np.sign(predicted))),
    }


def _position_metrics(actual: pd.Series, position: pd.Series, transaction_cost_bps: float) -> dict[str, float]:
    position = position.astype(float)
    turnover = position.diff().abs().fillna(position.abs())
    strategy_return = position * actual - turnover * transaction_cost_bps / 10_000
    equity = np.exp(strategy_return.cumsum())
    return {
        "strategy_cagr": cagr(equity),
        "strategy_max_drawdown": max_drawdown(equity),
    }


def calculate_benchmarks(result: pd.DataFrame, config: Config) -> list[dict[str, Any]]:
    actual = result["actual_return"]
    prior = result["origin_return_1d"]
    benchmark_specs = [
        ("zero_return", pd.Series(0.0, index=result.index), pd.Series(0.0, index=result.index)),
        ("one_day_momentum", prior, (prior > 0).astype(float)),
        ("one_day_mean_reversion", -prior, (prior < 0).astype(float)),
        ("buy_and_hold", prior * 0.0, pd.Series(1.0, index=result.index)),
    ]
    rows: list[dict[str, Any]] = []
    for name, predicted, position in benchmark_specs:
        rows.append({
            "name": name,
            **_prediction_metrics(actual, predicted),
            **_position_metrics(actual, position, config.transaction_cost_bps),
        })
    return rows


def forecast_next(
    features: pd.DataFrame,
    result: pd.DataFrame,
    model: Pipeline,
    config: Config,
    feature_columns: list[str] | None = None,
) -> dict[str, Any]:
    feature_columns = feature_columns or FEATURE_COLUMNS
    usable = features.dropna(subset=feature_columns + ["close"])
    current = usable.iloc[-1]
    origin_date = usable.index[-1]
    prediction = float(model.predict(current[feature_columns].to_frame().T)[0])
    entry = float(result["predicted_return"].quantile(config.entry_quantile))
    exit_ = float(result["predicted_return"].quantile(config.exit_quantile))
    prior_position = float(result["position"].iloc[-1])
    next_position = 1.0 if prediction > entry else 0.0 if prediction < exit_ else prior_position
    signal = "ENTER" if prior_position == 0 and next_position == 1 else "EXIT" if prior_position == 1 and next_position == 0 else "HOLD"
    residual_std = float(result["residual"].std(ddof=1))
    if not np.isfinite(residual_std) or residual_std <= 0:
        residual_std = 0.01
    confidence = float(np.clip(abs(prediction) / (abs(prediction) + residual_std), 0.01, 0.99))
    return {
        "origin_date": origin_date.strftime("%Y-%m-%d"),
        "next_date": next_exchange_session(origin_date, config.exchange_calendar).strftime("%Y-%m-%d"),
        "predicted_return": prediction,
        "predicted_close": float(current["close"] * math.exp(prediction)),
        "lower_return": prediction - 1.64 * residual_std,
        "upper_return": prediction + 1.64 * residual_std,
        "signal": signal,
        "confidence": confidence,
        "entry_threshold": entry,
        "exit_threshold": exit_,
    }


def feature_attribution(
    model: Pipeline,
    latest: pd.Series,
    feature_columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    feature_columns = feature_columns or FEATURE_COLUMNS
    scaler: StandardScaler = model.named_steps["scale"]
    ridge: RidgeCV = model.named_steps["ridge"]
    standardized = scaler.transform(latest[feature_columns].to_frame().T)[0]
    rows = [
        {"feature": feature, "coefficient": float(coef), "contribution": float(coef * value)}
        for feature, coef, value in zip(feature_columns, ridge.coef_, standardized, strict=True)
    ]
    return sorted(rows, key=lambda row: abs(row["contribution"]), reverse=True)[:12]


def calculate_ablation(
    featured: pd.DataFrame,
    full_result: pd.DataFrame,
    full_metrics: dict[str, float],
    config: Config,
    active_features: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    full_index = full_result.index
    for group_name, group_features in FEATURE_GROUPS.items():
        removed = [feature for feature in group_features if feature in active_features]
        remaining = [feature for feature in active_features if feature not in removed]
        if not removed or len(remaining) < 2:
            continue
        try:
            alt_result, _ = walk_forward(featured, config, remaining)
            common = full_index.intersection(alt_result.index)
            if len(common) < 250:
                continue
            aligned = alt_result.loc[common].copy()
            aligned["strategy_equity"] = np.exp(aligned["strategy_return"].cumsum())
            aligned["benchmark_equity"] = np.exp(aligned["actual_return"].cumsum())
            alt_metrics = calculate_metrics(aligned)
            rows.append({
                "removed_group": group_name,
                "removed_feature_count": len(removed),
                "directional_accuracy": alt_metrics["directional_accuracy"],
                "directional_accuracy_delta": alt_metrics["directional_accuracy"] - full_metrics["directional_accuracy"],
                "strategy_cagr": alt_metrics["strategy_cagr"],
                "strategy_cagr_delta": alt_metrics["strategy_cagr"] - full_metrics["strategy_cagr"],
                "rmse_return": alt_metrics["rmse_return"],
                "rmse_delta": alt_metrics["rmse_return"] - full_metrics["rmse_return"],
            })
        except Exception as exc:
            rows.append({
                "removed_group": group_name,
                "removed_feature_count": len(removed),
                "status": "error",
                "message": str(exc),
            })
    return rows


def serialize_series(result: pd.DataFrame, days: int = 756) -> list[dict[str, Any]]:
    return [
        {
            "date": date.strftime("%Y-%m-%d"),
            "actual_close": round(float(row.actual_close), 4),
            "predicted_close": round(float(row.predicted_close), 4),
            "actual_return": float(row.actual_return),
            "predicted_return": float(row.predicted_return),
            "signal": str(row.signal),
            "velocity": float(row.velocity),
            "acceleration": float(row.acceleration),
            "jerk": float(row.jerk),
            "opposite_velocity": float(row.opposite_velocity),
            "strategy_equity": float(row.strategy_equity),
            "benchmark_equity": float(row.benchmark_equity),
        }
        for date, row in result.tail(days).iterrows()
    ]


def revision_status(active_features: list[str], source_status: dict[str, Any]) -> tuple[bool, str]:
    relevant_sources = sorted({
        FEATURE_SOURCE[feature]
        for feature in active_features
        if feature in FEATURE_SOURCE
    })
    if not relevant_sources:
        return False, "No revision-sensitive FRED macro features are active in this run."
    non_point_in_time = [
        source for source in relevant_sources
        if not source_status.get(source, {}).get("point_in_time", False)
    ]
    if non_point_in_time:
        return True, (
            "Revision-risk warning: active macro features use current FRED history for "
            + ", ".join(non_point_in_time)
            + ". Configure FRED_API_KEY to use ALFRED/FRED API initial-release observations."
        )
    return False, "Active FRED macro features use ALFRED/FRED API initial-release observations."


def write_outputs(
    featured: pd.DataFrame,
    result: pd.DataFrame,
    metrics: dict[str, float],
    benchmarks: list[dict[str, Any]],
    ablation: list[dict[str, Any]],
    run_id: str,
    active_features: list[str],
    revision_bias_flag: bool,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["close", "return_1d", "velocity", "acceleration", "jerk", "opposite_velocity",
               "vix", "ust_2y", "ust_10y", "curve_10y_2y", "ig_oas", "hy_oas", "wti", "dollar"]
    featured.tail(1500)[columns].to_csv(OUTPUT_DIR / "data.csv", index_label="date")
    result.to_csv(OUTPUT_DIR / "predictions.csv", index_label="date")
    result[result["signal"].isin(["ENTER", "EXIT"])].to_csv(OUTPUT_DIR / "signals.csv", index_label="date")
    pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items()]).to_csv(
        OUTPUT_DIR / "backtest.csv", index=False
    )
    pd.DataFrame(benchmarks).to_csv(OUTPUT_DIR / "benchmarks.csv", index=False)
    pd.DataFrame(ablation).to_csv(OUTPUT_DIR / "ablation.csv", index=False)
    pd.DataFrame([{
        "run_id": run_id,
        "run_time_utc": datetime.now(timezone.utc).isoformat(),
        "data_through": featured.index.max().strftime("%Y-%m-%d"),
        "model": "RidgeCV expanding-window",
        "feature_count": len(active_features),
        "features": "|".join(active_features),
        "point_in_time_macro": not revision_bias_flag,
        "status": "success",
    }]).to_csv(OUTPUT_DIR / "model_runs.csv", index=False)


def sync_google_sheet(config: Config) -> str:
    credentials_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip() or config.google_sheet_id
    if not credentials_raw or not sheet_id:
        return "skipped: credentials not configured"
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        info = json.loads(credentials_raw) if credentials_raw.startswith("{") else json.loads(Path(credentials_raw).read_text())
        credentials = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"],
        )
        workbook = gspread.authorize(credentials).open_by_key(sheet_id)
        for tab, filename in {
            "Data": "data.csv", "Predictions": "predictions.csv", "Backtest": "backtest.csv",
            "Signals": "signals.csv", "Model Runs": "model_runs.csv",
        }.items():
            frame = pd.read_csv(OUTPUT_DIR / filename).replace({np.nan: ""})
            worksheet = workbook.worksheet(tab)
            worksheet.clear()
            worksheet.update([frame.columns.tolist()] + frame.astype(object).values.tolist(), value_input_option="USER_ENTERED")
        return "success"
    except Exception as exc:
        return f"error: {exc}"


def run() -> int:
    config = Config.load()
    raw, source_status = fetch_all_data(config)
    featured = engineer_features(raw)
    minimum_complete_rows = max(config.minimum_training_days + 50, 900)
    active_features = select_active_features(featured, FEATURE_COLUMNS, minimum_complete_rows)
    result, model = walk_forward(featured, config, active_features)
    metrics = calculate_metrics(result)
    benchmarks = calculate_benchmarks(result, config)
    ablation = calculate_ablation(featured, result, metrics, config, active_features)
    forecast = forecast_next(featured, result, model, config, active_features)
    latest_features = featured.dropna(subset=active_features).iloc[-1]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    revision_bias_flag, revision_bias_note = revision_status(active_features, source_status)
    price_status = source_status.get("price", {})
    payload = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "data_through": raw.index.max().strftime("%Y-%m-%d"),
            "status": "live",
            "requested_target": config.target_symbol,
            "target": price_status.get("effective_symbol", config.target_symbol),
            "target_name": price_status.get("effective_name", config.target_symbol),
            "target_is_tradeable": bool(price_status.get("is_tradeable", True)),
            "using_proxy_target": bool(price_status.get("proxy_for_requested_target", False)),
            "model": "RidgeCV expanding-window walk-forward",
            "run_id": run_id,
            "sheet_url": config.google_sheet_url,
            "revision_bias_flag": revision_bias_flag,
            "revision_bias_note": revision_bias_note,
            "price_source": price_status.get("source", "unknown"),
            "active_feature_count": len(active_features),
            "active_features": active_features,
            "source_status": source_status,
        },
        "forecast": forecast,
        "metrics": metrics,
        "benchmarks": benchmarks,
        "ablation": ablation,
        "series": serialize_series(result),
        "feature_importance": feature_attribution(model, latest_features, active_features),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "latest.json").write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    write_outputs(
        featured, result, metrics, benchmarks, ablation, run_id,
        active_features, revision_bias_flag,
    )
    sheet_status = sync_google_sheet(config)
    print(json.dumps({
        "run_id": run_id,
        "sheet_sync": sheet_status,
        "data_through": payload["metadata"]["data_through"],
        "effective_target": payload["metadata"]["target"],
        "next_session": forecast["next_date"],
        "active_feature_count": len(active_features),
    }))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
