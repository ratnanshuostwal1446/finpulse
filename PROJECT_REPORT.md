# FinPulse — Project Report

## Project Architecture
FinPulse follows a three-tier architecture: a data layer (yfinance →
SQLite), a backend layer (FastAPI REST API), and a frontend layer
(Streamlit dashboard) that consumes the API over HTTP. This separation
means the frontend has no direct database access — everything flows
through documented REST endpoints, which was the point of the exercise
(understanding how app components communicate).

## APIs Used
- **yfinance** for both live fundamentals (`.info`) and 6-month daily
  historical OHLCV data (`.history()`) for 20 NSE-listed companies
  (`.NS` suffix tickers).
- Our own **FastAPI REST API** exposes this data via `/stocks`,
  `/stocks/{ticker}`, `/market-summary`, and `/refresh`.

## Database Design
SQLite, chosen for zero-setup file-based storage suitable for a
project of this scale. Two tables: `stocks` (latest snapshot, one row
per ticker, upserted on refresh) and `price_history` (append-only,
unique on ticker+date to prevent duplicate rows on repeated fetches).

## Features Implemented
- Live + historical data for 20 companies (price, market cap, P/E, EPS,
  day high/low, volume)
- SQLite storage with upsert logic to avoid duplicate history rows
- 4 REST endpoints (one more than the required 3)
- Interactive dashboard: full data table, candlestick historical price
  chart, multi-company fundamental comparison, sector-wise market cap
  breakdown (pie chart)
- Manual refresh trigger (since free-tier hosting doesn't support
  background cron jobs reliably)

## Challenges Faced
- **yfinance reliability**: Yahoo Finance occasionally rate-limits or
  returns incomplete `.info` data for some tickers. Handled by wrapping
  each fetch in a try/except so one bad ticker doesn't crash the whole
  refresh — failures are logged and reported back via the `/refresh`
  response.
- **Frontend/backend separation across two hosts**: since Render and
  Streamlit Cloud are different domains, CORS had to be explicitly
  enabled on the FastAPI backend for the dashboard to call it.
- **Free-tier cold starts**: Render's free tier sleeps after inactivity,
  causing the first request to be slow. Addressed by keeping fetch
  logic idempotent and giving the user a manual refresh button rather
  than depending on a background job that may not run.

## Future Improvements
- Move from polling `/refresh` manually to a scheduled background job
  (e.g. APScheduler or a cron-triggered endpoint) for automatic daily
  updates.
- Add a watchlist/authentication layer so users can track a custom
  subset of stocks.
- Add sector-relative valuation metrics (e.g. P/E vs sector average)
  for more actionable comparison.
- Migrate from SQLite to Postgres (e.g. Supabase) if concurrent write
  load ever became a concern — not needed at this scale but noted as
  the natural next step.

## AI Tool Usage Disclosure
Claude (Anthropic) was used to scaffold and write the FastAPI backend,
SQLite schema, and Streamlit dashboard code, consistent with the
AlgoLabs track's AI usage policy. All code was reviewed and understood
by the applicant, who can walk through architecture, data flow, and
implementation decisions in the interview.
