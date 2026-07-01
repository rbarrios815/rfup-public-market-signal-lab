# Deployment checklist

- [x] Create the new GitHub repository `rfup-public-market-signal-lab`.
- [ ] Push this package to the repository's `main` branch.
- [ ] In Settings → Pages, select GitHub Actions.
- [ ] Run **Refresh public market model** manually once.
- [ ] Confirm **Deploy dashboard to GitHub Pages** succeeds.
- [ ] Add `GOOGLE_SHEET_ID` repository variable with value `1D2jwkfc5rT-54elnimGGFnrEPcGaDaraJkSbO0gXZmg`.
- [ ] Optional: add `ALPHA_VANTAGE_API_KEY` secret.
- [ ] Optional: add `GOOGLE_SERVICE_ACCOUNT_JSON` secret and share the Sheet with that service account.
- [ ] Replace the packaged demo banner only by running the real model; do not relabel demo data as live.
- [ ] Review data-source terms before enabling FINRA, rating-agency, news, or transaction-level feeds.
