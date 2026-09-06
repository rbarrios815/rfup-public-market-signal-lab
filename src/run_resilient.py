"""Resilient production entrypoint for the RFUP public-data model.

Primary behavior:
1. Prefer the configured tradeable target feed (SPY by default).
2. If every tradeable target feed fails, fall back to the public FRED S&P 500
   index while explicitly changing the effective instrument identity.
3. Let the base model select the largest feature set with enough complete rows,
   so temporary optional-feed outages do not collapse the entire run.
"""
from __future__ import annotations

import os
import sys
from typing import Any

import numpy as np
import pandas as pd

import build_model as base

_original_fetch_price = base.fetch_price


def _fred_sp500_price(config: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    use_initial_release = bool(os.getenv("FRED_API_KEY", "").strip())
    close = base.fetch_fred_series(
        "SP500",
        "close",
        initial_release=use_initial_release,
    ).dropna(subset=["close"])
    if len(close) < 900:
        raise RuntimeError(f"FRED SP500 fallback returned only {len(close)} usable rows.")
    frame = close.copy()
    frame["open"] = frame["close"]
    frame["high"] = frame["close"]
    frame["low"] = frame["close"]
    frame["volume"] = np.nan
    metadata = {
        "source": (
            "ALFRED/FRED API SP500 initial-release fallback"
            if use_initial_release
            else "FRED SP500 current-history fallback"
        ),
        "status": "ok_proxy",
        "requested_symbol": config.target_symbol,
        "effective_symbol": "SP500",
        "effective_name": "S&P 500 Index (FRED SP500 proxy)",
        "is_tradeable": False,
        "proxy_for_requested_target": True,
        "point_in_time": use_initial_release,
    }
    return frame[["open", "high", "low", "close", "volume"]], metadata


def robust_fetch_price(config: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        return _original_fetch_price(config)
    except Exception as primary_error:
        try:
            frame, metadata = _fred_sp500_price(config)
            metadata["primary_price_error"] = str(primary_error)
            return frame, metadata
        except Exception as fallback_error:
            raise RuntimeError(
                "All public target-price sources failed. "
                f"Primary: {primary_error}; FRED fallback: {fallback_error}"
            ) from fallback_error


def run() -> int:
    base.fetch_price = robust_fetch_price
    return base.run()


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"RESILIENT_RUN_ERROR: {exc}", file=sys.stderr)
        raise
