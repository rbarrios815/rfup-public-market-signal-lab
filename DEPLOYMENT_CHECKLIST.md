# Deployment checklist

- [x] Create the new GitHub repository `rfup-public-market-signal-lab`.
- [x] Push the application, model, tests, preview data, and workflows to `main`.
- [x] Link the repository and Google Sheet in project documentation.
- [ ] In **Settings → Pages**, set **Source** to **GitHub Actions**.
- [ ] Re-run **Deploy dashboard to GitHub Pages** after Pages is enabled.
- [ ] Run **Refresh public market model** manually once and confirm tests/data retrieval succeed.
- [ ] Add `GOOGLE_SHEET_ID` repository variable with value `1D2jwkfc5rT-54elnimGGFnrEPcGaDaraJkSbO0gXZmg`.
- [ ] Optional: add `ALPHA_VANTAGE_API_KEY` secret.
- [ ] Optional: add `GOOGLE_SERVICE_ACCOUNT_JSON` secret and share the Sheet with that service account.
- [ ] Replace the packaged demo banner only through a successful real-model run; do not relabel demo data as live.
- [ ] Review data-source terms before enabling FINRA, rating-agency, news, or transaction-level feeds.

## Current deployment state

- Repository source: complete on `main`.
- Current source/workflow head: `5d9cb3d8ac02ff8f6c8644c523b79a1b5e5fd6b1`.
- Pages workflow: correctly installed, but its first run stopped at `actions/configure-pages` because Pages has not yet been enabled in repository settings.
- Expected site URL after successful deployment: `https://rbarrios815.github.io/rfup-public-market-signal-lab/`.
