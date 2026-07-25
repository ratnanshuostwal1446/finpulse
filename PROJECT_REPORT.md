\# FinPulse — Project Report



\*\*Live App:\*\* https://finpulse-7mxpoux9kjtzr5ctjp3kbi.streamlit.app/

\*\*Live API:\*\* https://finpulse-fn4r.onrender.com/docs



\## Project Architecture

FinPulse follows a three-tier architecture: a data layer, a backend

layer (FastAPI REST API), and a frontend layer (Streamlit dashboard)

that consumes the API over HTTP. The frontend never touches the

database directly — everything flows through documented REST

endpoints.



The data layer has two independent paths. Locally, `data\_fetcher.py`

calls yfinance directly and writes to SQLite. In production, a

separate script (`scripts/push\_live\_data.py`) runs on a GitHub Actions

schedule, fetches from yfinance using GitHub's IP range, and pushes

the result to the backend's `/ingest` endpoint — the backend itself

never calls yfinance once deployed. This split exists because of a

real, discovered production constraint (see Challenges below).



\## APIs Used

\- \*\*yfinance\*\* for live fundamentals and 6-month historical OHLCV data

&#x20; for 20 NSE-listed companies across six sectors (IT, Banking, Defense,

&#x20; Telecom, Metal, Consumer).

\- Our own \*\*FastAPI REST API\*\* exposes this via 7 endpoints: `/stocks`,

&#x20; `/stocks/{ticker}` (GET and DELETE), `/market-summary`, `/refresh`,

&#x20; and `/ingest`.



\## Database Design

SQLite, chosen for zero-setup file-based storage. Two tables: `stocks`

(latest snapshot, upserted) and `price\_history` (append-only, unique

on ticker+date). Both the local and production data paths write

through a single shared function (`database.upsert\_stock()`) so write

logic can't drift between the two paths.



\## Features Implemented

\- Live + historical data for 20 companies across 6 custom sector

&#x20; categories (overriding yfinance's default classification)

\- SQLite storage with upsert logic

\- 7 REST endpoints (more than double the required 3), including a

&#x20; token-authenticated `/ingest` endpoint and a `DELETE` endpoint for

&#x20; data cleanup

\- Interactive dashboard: full data table (1-indexed), candlestick

&#x20; chart with volume overlay, multi-company fundamental comparison

&#x20; with properly labeled metrics (P/E, EPS, Market Cap, Price), and a

&#x20; sector-wise market cap breakdown pie chart

\- Market-cap-weighted average P/E calculation (`Sum(P/E x market\_cap) /

&#x20; Sum(market\_cap)`), rather than a simple mean, so large companies

&#x20; proportionally influence the market-wide average P/E more than

&#x20; small-cap outliers with extreme multiples

\- Automated daily data refresh via GitHub Actions, with a manual

&#x20; "Run workflow" trigger available for on-demand refreshes

\- IST-localized timestamps (converted from UTC, which is what the

&#x20; backend stores) and a visible "data last updated" indicator

\- Graceful degradation: friendly, non-technical error messages for

&#x20; backend cold-starts and connection failures, instead of raw

&#x20; tracebacks



\## Challenges Faced



\*\*Python 3.14 dependency conflicts.\*\* Several pinned package versions

(pandas, pillow, streamlit's own pinned dependencies) predated Python

3.14 and had no prebuilt wheels, causing pip to attempt compiling from

source (and failing, since no C++ build tools were installed). Fixed

by unpinning versions and letting pip resolve to the latest

Python-3.14-compatible builds instead.



\*\*Yahoo Finance blocks cloud-hosting IPs.\*\* Live fetches that worked

perfectly locally consistently failed on Render with 429 errors. Root

cause: yfinance is an unofficial scraper of Yahoo Finance, and Yahoo

blocklists known cloud/datacenter IP ranges. An initial attempted fix

(having a GitHub Action call the backend's `/refresh` endpoint) failed

for a subtler reason: the actual yfinance call still happened on

Render's IP even when triggered remotely — calling an endpoint

remotely doesn't change where the underlying network request

originates. The correct fix required moving the fetch logic itself

into the GitHub Action (using GitHub's own IP), with the fetched data

then pushed to a new backend endpoint (`/ingest`) that performs no

yfinance calls of its own, only database writes. This is a good

illustration of a real architectural lesson: fixing "where a request

is triggered from" is different from fixing "where a request

originates from."



\*\*Windows phantom port binding.\*\* After stopping and restarting the

local server repeatedly, `uvicorn --reload` would intermittently leave

an orphaned process holding port 8000, causing new instances to bind

successfully in logs while the browser kept hitting the old, stale

process — silently invalidating test results until diagnosed via

`netstat -ano` and `taskkill`. Worked around during development by

running on an alternate port (8001) when the issue recurred.



\*\*Non-blocking startup requirement.\*\* The original design fetched all

20 tickers during FastAPI's startup lifecycle before opening the port.

Render expects a service to bind its port quickly after starting, so

this caused deploy timeouts. Fixed by making startup only initialize

the database schema, with data population handled separately via

`/ingest` (production) or `/refresh` (local).



\*\*Gitignore pattern didn't match nested paths.\*\* A `.gitignore` entry

for `.streamlit/secrets.toml` didn't match the file at its actual

nested path (`frontend/.streamlit/secrets.toml`), so a local

placeholder secrets file was accidentally committed and silently

overrode the real value set in Streamlit Cloud's dashboard, causing a

confusing "secret doesn't take effect" debugging session. Fixed with a

`\*\*/secrets.toml` glob pattern and removing the file from git tracking.



\*\*Corporate action broke a ticker.\*\* `TATAMOTORS.NS` returned a 404

because Tata Motors demerged in October 2025 into separate passenger

and commercial vehicle entities; the old symbol was reassigned.

Discovered via live testing and fixed by researching the current

correct ticker before the list was later replaced entirely with a

diversified, sector-organized selection.



\## Future Improvements

\- Replace yfinance with a licensed market data API to avoid the

&#x20; unofficial-scraper rate limiting and cloud-IP blocking entirely.

\- Add a watchlist/authentication layer for end users.

\- Add sector-relative valuation metrics (e.g. P/E vs sector average).

\- Migrate from SQLite to Postgres if concurrent write load ever became

&#x20; a concern — not needed at current scale.

\- Increase GitHub Actions refresh frequency beyond once daily if

&#x20; more real-time data becomes a priority.



\## AI Tool Usage Disclosure

Claude (Anthropic) was used throughout this project's development —

initial scaffolding, iterative debugging of real deployment issues,

and implementing UX/data-quality refinements. Every change was tested

locally and verified against live data before being pushed to

production, with the applicant reviewing and confirming each change

rather than accepting code without verification. The applicant can

walk through architecture, data flow, and every implementation

decision in the interview, including the reasoning behind each

debugging fix described above.

