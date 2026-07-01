"""Resilient production entrypoint for the RFUP public-data model.

The base model intentionally contains the full feature catalog. This entrypoint
keeps scheduled runs alive when a free provider is unavailable by:
1. falling back from the configured SPY source to the public FRED S&P 500 close;
2. training on the always-available price/derivative feature core, while the
   source-status payload still reports every optional macro/credit feed.
"""
from __future__ import annotations

import sys
from typing import Any

import numpy as np
import pandas as pd

import build_model as base

CORE_FEATURES = [
    "return_1d",
    "return_5d",
    "return_20d",
    "realized_vol_20d",
    "velocity",
    "acceleration",
    "jerk",
    "opposite_velocity",
    "opposite_acceleration",
    "ma_distance_20",
    "ma_distance_50",
    "ma_distance_200",
    "distance_to_20d_high",
    "distance_to_20d_low",
    "distance_to_60d_high",
    "distance_to_60d_low",
]

_original_fetch_price = base.fetch_price


def _fred_sp500_price() -> pd.DataFrame:
    close = base.fetch_fred_series("SP500", "close").dropna(subset=["close"])
    if len(close) < 900:
        raise RuntimeError(f"FRED SP500 fallback returned only {len(close)} usable rows.")
    frame = close.copy()
    frame["open"] = frame["close"]
    frame["high"] = frame["close"]
    frame["low"] = frame["close"]
    frame["volume"] = np.nan
    return frame[["open", "high", "low", "close", "volume"]]


def robust_fetch_price(config: Any) -> tuple[pd.DataFrame, str]:
    try:
        return _original_fetch_price(config)
    except Exception as primary_error:
        try:
            return _fred_sp500_price(), "FRED SP500 close fallback"
        except Exception as fallback_error:
            raise RuntimeError(
                "All public target-price sources failed. "
                f"Primary: {primary_error}; FRED fallback: {fallback_error}"
            ) from fallback_error


def run() -> int:
    # Optional free feeds remain visible in source_status, but a temporary outage
    # cannot eliminate every training row by forcing an all-column dropna.
    base.FEATURE_COLUMNS = CORE_FEATURES
    base.fetch_price = robust_fetch_price
    return base.run()


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"RESILIENT_RUN_ERROR: {exc}", file=sys.stderr)
        raise
