import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "build_model.py"
spec = importlib.util.spec_from_file_location("build_model", MODULE_PATH)
build_model = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = build_model
spec.loader.exec_module(build_model)


def sample_raw(rows: int = 1200):
    index = pd.bdate_range("2020-01-01", periods=rows)
    close = pd.Series(np.exp(np.linspace(np.log(400), np.log(500), rows)), index=index)
    frame = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.linspace(60_000_000, 80_000_000, rows),
            "vix": 18.0 + np.sin(np.linspace(0, 10, rows)),
            "ust_2y": 4.0,
            "ust_10y": 4.3,
            "ust_30y": 4.5,
            "curve_10y_2y": 0.3,
            "ig_oas": 1.0,
            "hy_oas": 3.5,
            "wti": 75.0,
            "dollar": 120.0,
        },
        index=index,
    )
    return frame


def test_opposite_derivatives_are_exact_negatives():
    features = build_model.engineer_features(sample_raw())
    valid = features.dropna(subset=["velocity", "opposite_velocity", "acceleration", "opposite_acceleration"])
    assert np.allclose(valid["opposite_velocity"], -valid["velocity"])
    assert np.allclose(valid["opposite_acceleration"], -valid["acceleration"])


def test_target_is_next_session_return_not_same_day():
    raw = sample_raw()
    features = build_model.engineer_features(raw)
    expected = np.log(raw["close"].shift(-1)) - np.log(raw["close"])
    valid = features["target_next_return"].dropna().index
    assert np.allclose(features.loc[valid, "target_next_return"], expected.loc[valid])


def test_raw_next_index_returns_strictly_later_date():
    index = pd.bdate_range("2026-01-01", periods=5)
    assert build_model.raw_next_index(index, index[2]) == index[3]


def test_nyse_calendar_skips_labor_day_2026():
    assert build_model.next_exchange_session(pd.Timestamp("2026-09-04")) == pd.Timestamp("2026-09-08")


def test_feature_selection_drops_unavailable_volume_feature():
    features = build_model.engineer_features(sample_raw())
    features["volume_z_20"] = np.nan
    selected = build_model.select_active_features(
        features,
        ["return_1d", "return_5d", "volume_z_20"],
        minimum_complete_rows=900,
    )
    assert "return_1d" in selected
    assert "return_5d" in selected
    assert "volume_z_20" not in selected


def test_benchmark_suite_contains_simple_baselines():
    index = pd.bdate_range("2024-01-01", periods=300)
    result = pd.DataFrame({
        "actual_return": np.sin(np.arange(300) / 13) / 100,
        "origin_return_1d": np.sin((np.arange(300) - 1) / 13) / 100,
    }, index=index)
    config = build_model.Config(
        target_symbol="SPY",
        minimum_training_days=50,
        retrain_frequency_days=21,
        transaction_cost_bps=2.0,
        entry_quantile=0.65,
        exit_quantile=0.35,
        google_sheet_id="",
        google_sheet_url="",
        price_provider="auto",
        stooq_symbol="spy.us",
        exchange_calendar="XNYS",
    )
    rows = build_model.calculate_benchmarks(result, config)
    names = {row["name"] for row in rows}
    assert names == {"zero_return", "one_day_momentum", "one_day_mean_reversion", "buy_and_hold"}
