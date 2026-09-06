# Deployment checklist

- [x] Create the GitHub repository `rfup-public-market-signal-lab`.
- [x] Push the application, model, tests, data output, and workflows to `main`.
- [x] Link the repository and Google Sheet in project documentation and the dashboard.
- [x] Set **Settings → Pages → Source** to **GitHub Actions**.
- [x] Deploy the dashboard successfully to GitHub Pages.
- [x] Run the public market model and replace the labeled demo output with live public data.
- [x] Add a resilient FRED S&P 500 fallback for outages in the free SPY feed.
- [x] Label the fallback as a non-tradeable S&P 500 proxy instead of displaying index levels as SPY.
- [x] Use the XNYS/NYSE exchange calendar for next-session dates.
- [x] Add simple model challenge baselines and grouped feature-ablation diagnostics.
- [x] Add PR regression CI, including the September 2026 Labor Day case.
- [x] Redeploy Pages automatically after every successful model-refresh workflow.
- [ ] Optional: add `FRED_API_KEY` secret to use ALFRED/FRED API initial-release macro observations and remove the active revision-risk warning.
- [ ] Optional: add `ALPHA_VANTAGE_API_KEY` secret to prefer Alpha Vantage for the requested tradeable SPY feed.
- [ ] Optional: add `GOOGLE_SERVICE_ACCOUNT_JSON` secret and share the Sheet with that service account.
- [ ] Optional: add `GOOGLE_SHEET_ID` repository variable with value `1D2jwkfc5rT-54elnimGGFnrEPcGaDaraJkSbO0gXZmg` for automated spreadsheet writes.
- [ ] Review data-source terms before enabling FINRA, rating-agency, news, SEC, or transaction-level feeds.

## Current deployment state

- Repository source: integrity-hardening merged to `main`.
- Live data refresh commit: `c9eb010aff8753ffbf42425314c185e425b26e3c`.
- Live model run: `20260906T223301Z`.
- Data through: `2026-09-04`.
- Requested target: `SPY`.
- Current effective target: `SP500` — **S&P 500 Index (FRED SP500 proxy)**.
- Current effective target is tradeable: **No**.
- Current public target source: `FRED SP500 current-history fallback`.
- Next forecast session from XNYS calendar: `2026-09-08`.
- Active feature count: `24`.
- Current revision-risk flag: **On** because `FRED_API_KEY` is not active for the macro features in the current run.
- Baseline and ablation outputs: published in `docs/data/benchmarks.csv` and `docs/data/ablation.csv` and displayed on the dashboard.
- Latest model-refresh workflow: passed tests, model build, and output commit.
- Latest GitHub Pages deployment: successful.
- Dashboard URL: `https://rbarrios815.github.io/rfup-public-market-signal-lab/`.
- Research software only; not investment advice.
