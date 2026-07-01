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


def sample_raw(rows: int = 260):
    index = pd.bdate_range("2024-01-01", periods=rows)
    close = pd.Series(np.exp(np.linspace(np.log(400), np.log(500), rows)), index=index)
    frame = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.linspace(60_000_000, 80_000_000, rows),
            "vix": 18.0,
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
