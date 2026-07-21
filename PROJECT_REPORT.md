# FinPulse — Project Report

**Live App:** https://finpulse-7mxpoux9kjtzr5ctjp3kbi.streamlit.app/
**Live API:** https://finpulse-fn4r.onrender.com/docs

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
  each fetch in a try/except with retries and backoff, so one bad
  ticker doesn't crash the whole refresh.
- **Cloud IPs get blocked harder than home connections**: yfinance is
  an unofficial scraper of Yahoo Finance, and Yahoo blocklists
  datacenter/cloud-hosting IP ranges (Render, AWS, etc.) more
  aggressively than residential IPs. Live fetches that worked fine
  locally returned consistent 429s from Render. Fixed by seeding the
  deployed database with data fetched once locally (committed to the
  repo), while keeping `POST /refresh` available for anyone running
  the app locally where live fetches work normally. A production
  system would use a licensed market data API with an API key instead
  of an unofficial scraper, which avoids this entirely - noted below
  as a future improvement.
- **Blocking startup caused deploy timeouts**: the original design
  fetched all 20 tickers during FastAPI's startup lifecycle before
  opening the port. Render expects a service to bind its port quickly
  after starting, so a slow, retry-heavy fetch caused deploy timeouts.
  Fixed by making startup only initialize the (fast, local) database
  schema, with data population handled separately via `/refresh` or,
  in this deployment, pre-seeded data.
- **Frontend/backend separation across two hosts**: since Render and
  Streamlit Cloud are different domains, CORS had to be explicitly
  enabled on the FastAPI backend for the dashboard to call it.
- **Secrets not applying on Streamlit Cloud**: a `.gitignore` pattern
  that worked for a top-level path didn't match the same file at a
  nested path (`frontend/.streamlit/secrets.toml`), so a local
  placeholder secrets file was accidentally committed to the repo and
  silently overrode the real value set in the Streamlit Cloud
  dashboard. Fixed by using a `**/secrets.toml` glob pattern and
  removing the committed file from git tracking.
- **Corporate action broke a ticker**: `TATAMOTORS.NS` returned a 404
  because Tata Motors demerged in October 2025 - the passenger vehicle
  business (including JLR) now trades as `TMPV.NS`, while the old
  symbol was reassigned to the spun-off commercial vehicle business.
  Fixed by updating the tracked ticker list.

## Future Improvements
- Move from polling `/refresh` manually to a scheduled background job
  (e.g. APScheduler or a cron-triggered endpoint) for automatic daily
  updates.
- Replace yfinance with a licensed market data API (e.g. one with a
  paid API key) to avoid Yahoo Finance's unofficial-scraper rate
  limiting and cloud-IP blocking entirely.
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