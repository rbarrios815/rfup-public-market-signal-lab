# RFUP Public Market Signal Lab

A public-data, walk-forward research dashboard for forecasting the next U.S. equity-market trading session. The requested target is **SPY**. When a tradeable SPY feed is unavailable, the system may fall back to the public **FRED S&P 500 Index** series, but the run changes its effective target identity and visibly labels that series as a non-tradeable proxy rather than presenting index levels as SPY prices.

> Research software only. It is not investment advice, a trading recommendation, or a promise of predictive accuracy.

## What this replaces

The original concept mixed useful hypotheses with unavailable, licensed, or leakage-prone inputs. This implementation deliberately replaces:

- Bloomberg BGN prices with configurable public/free price feeds and explicit source/instrument metadata.
- Comprehensive issuer-level ratings data with public aggregate credit-spread proxies and optional later adapters.
- Arbitrary hand-assigned weights with regularized regression trained only on prior observations.
- Random train/test splits with expanding-window walk-forward predictions.
- Generic weekday arithmetic with the **XNYS/NYSE exchange calendar**, including market holidays.
- Revised macro history presented as contemporaneous data with either ALFRED/FRED initial-release observations or an explicit revision-risk warning.
- Fibonacci levels as assumed predictors with testable rolling support/resistance distances.
- “Laws of physics” claims with clearly defined normalized return derivatives.

## Live architecture

1. `src/build_model.py` downloads public daily data, engineers features, selects the largest sufficiently complete feature set, performs an expanding-window backtest, calculates simple benchmarks and grouped feature ablations, and writes JSON/CSV files to `docs/data/`.
2. `src/run_resilient.py` preserves scheduled runs when the tradeable target feed fails. A FRED S&P 500 fallback is explicitly marked as a proxy and non-tradeable.
3. `.github/workflows/update-data.yml` runs tests, refreshes the model after U.S. market hours on weekdays, and commits refreshed outputs. Pull requests run the regression tests without writing model output.
4. `.github/workflows/pages.yml` deploys the static dashboard in `docs/` to GitHub Pages after refreshed output is committed.
5. When `GOOGLE_SERVICE_ACCOUNT_JSON` is configured, the run can also sync the Google Sheet tabs `Data`, `Predictions`, `Backtest`, `Signals`, and `Model Runs`.

## Data integrity and point-in-time handling

- **Requested target:** `SPY`.
- **Primary tradeable feeds:** Alpha Vantage when `ALPHA_VANTAGE_API_KEY` is configured, otherwise the configured Stooq series.
- **Resilient price fallback:** FRED `SP500`. If used, `latest.json` and the dashboard show `target=SP500`, `target_is_tradeable=false`, and `using_proxy_target=true`.
- **Next-session calendar:** XNYS/NYSE through `exchange_calendars`; holidays are skipped.
- **Macro data:** VIX, Treasury yields, yield-curve slope, investment-grade/high-yield spreads, WTI oil, and the broad U.S. dollar index.
- **ALFRED mode:** when `FRED_API_KEY` is configured, the model requests FRED API `output_type=4` initial-release observations. If that mode is unavailable, the system falls back to current FRED history and sets a revision-risk warning for active macro features.
- **Missing feeds:** unavailable features are excluded only when necessary to preserve the minimum complete training sample; the active feature list is published in model metadata.

## Validation diagnostics

Every production run now publishes:

- RidgeCV expanding-window walk-forward forecast metrics.
- Buy-and-hold comparison with transaction-cost-aware strategy results.
- Simple challenge baselines: zero-return, one-day momentum, one-day mean reversion, and buy-and-hold.
- Grouped feature ablation for returns/volatility, derivatives, trend/range/volume, and macro/credit/cross-asset inputs.
- Current standardized feature contributions.

The diagnostic tables are visible on the public dashboard and are also written to `docs/data/benchmarks.csv` and `docs/data/ablation.csv`.

## Linked Google Sheet

The project control workbook is:

`https://docs.google.com/spreadsheets/d/1D2jwkfc5rT-54elnimGGFnrEPcGaDaraJkSbO0gXZmg/edit`

To enable automated writes:

1. Create a Google Cloud service account with Sheets access.
2. Share the workbook with the service-account email as Editor.
3. Add its JSON credentials to the repository secret `GOOGLE_SERVICE_ACCOUNT_JSON`.
4. Add `GOOGLE_SHEET_ID=1D2jwkfc5rT-54elnimGGFnrEPcGaDaraJkSbO0gXZmg` as a repository variable.

## Optional repository secrets

- `ALPHA_VANTAGE_API_KEY` — prefer Alpha Vantage for the requested tradeable SPY target.
- `FRED_API_KEY` — enable ALFRED/FRED API initial-release macro observations.
- `GOOGLE_SERVICE_ACCOUNT_JSON` — enable automated Google Sheet writes.

SEC XBRL fundamentals, FINRA aggregate bond activity/sentiment, headline sentiment, issuer rating actions, and corporate-action breadth remain later adapters. They should not be enabled until data-source terms and timestamp integrity are reviewed, and they are never silently fabricated.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python src/run_resilient.py
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000`.

## Repository and deployment

Repository: `https://github.com/rbarrios815/rfup-public-market-signal-lab`

Dashboard: `https://rbarrios815.github.io/rfup-public-market-signal-lab/`

The `main` branch is the canonical source. GitHub Pages should use **GitHub Actions** as its deployment source.

## Backtest rules

- A feature row known at close on day `t` predicts the close-to-close return for the next observed market session.
- Every historical Ridge prediction is generated by a model trained only on rows before the prediction origin.
- Entry/exit thresholds are calculated from prior predictions only.
- Strategy results include configurable transaction costs.
- The next live forecast date comes from the XNYS exchange calendar.
- Current-history FRED data is never described as point-in-time; the dashboard displays revision risk unless initial-release observations are active for the macro features used by the model.
- Ablation results are diagnostics, not a license to select a feature set on the same backtest and then call that selected result unbiased out-of-sample performance.

## Tests

```bash
pytest -q
```

Regression coverage includes the 2026 Labor Day case: a September 4, 2026 origin advances to the September 8 NYSE session, not September 7.
