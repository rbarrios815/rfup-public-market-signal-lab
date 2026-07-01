# Deployment checklist

- [x] Create the new GitHub repository `rfup-public-market-signal-lab`.
- [x] Push the application, model, tests, data output, and workflows to `main`.
- [x] Link the repository and Google Sheet in project documentation and the dashboard.
- [x] Set **Settings → Pages → Source** to **GitHub Actions**.
- [x] Deploy the dashboard successfully to GitHub Pages.
- [x] Run the public market model and replace the labeled demo output with live public data.
- [x] Add a resilient FRED S&P 500 fallback for outages in the free SPY feed.
- [x] Redeploy Pages automatically after every successful model-refresh workflow.
- [ ] Optional: add `GOOGLE_SHEET_ID` repository variable with value `1D2jwkfc5rT-54elnimGGFnrEPcGaDaraJkSbO0gXZmg` for automated spreadsheet writes.
- [ ] Optional: add `ALPHA_VANTAGE_API_KEY` secret to prefer Alpha Vantage over the fallback.
- [ ] Optional: add `GOOGLE_SERVICE_ACCOUNT_JSON` secret and share the Sheet with that service account.
- [ ] Review data-source terms before enabling FINRA, rating-agency, news, or transaction-level feeds.

## Current deployment state

- Repository source: complete on `main`.
- Live model-data commit: `65506debec0557b86a7144af5d3ff03df9498b95`.
- Live model run: `20260701T182139Z`.
- Data through: `2026-06-30`.
- Current public target source: `FRED SP500 close fallback`.
- Dashboard URL: `https://rbarrios815.github.io/rfup-public-market-signal-lab/`.
- Research software only; not investment advice.
