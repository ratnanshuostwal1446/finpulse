"""
push_live_data.py
-------------------
Fetches live market data via yfinance and pushes it to the FinPulse
backend's /ingest endpoint over HTTP.

WHY THIS SCRIPT EXISTS: Yahoo Finance blocks requests from cloud-hosting
IP ranges (Render, AWS, etc.), so the backend calling yfinance directly
on Render fails. This script is designed to run somewhere with an
unblocked IP - either GitHub Actions (see .github/workflows/refresh.yml)
or your own machine - fetch the data there, and push the finished
result to the backend, which just writes it to the database with zero
yfinance calls of its own.

Usage:
    python push_live_data.py

Required environment variables:
    BACKEND_URL   - e.g. https://finpulse-fn4r.onrender.com
    INGEST_TOKEN  - shared secret, must match the backend's INGEST_TOKEN
"""

import os
import sys
import time
import requests
import yfinance as yf
from datetime import datetime

# Kept in sync with backend/data_fetcher.py's TICKERS list. If you change
# one, change the other - see PROJECT_REPORT.md for why they're not
# imported from a single shared file (this script runs standalone in
# GitHub Actions, without the rest of the backend package installed).
TICKERS = [
    "TCS.NS", "HCLTECH.NS",
    "ICICIBANK.NS", "AXISBANK.NS", "SBIN.NS", "BANKBARODA.NS",
    "BEL.NS", "HAL.NS", "SIGMAADV.NS", "AZAD.NS", "DATAPATTNS.NS", "PARAS.NS",
    "BHARTIARTL.NS",
    "HINDALCO.NS", "HINDZINC.NS",
    "POLYCAB.NS", "BAJFINANCE.NS",
    "TRENT.NS", "ABFRL.NS", "HINDUNILVR.NS",
]

def fetch_one(ticker: str, retries: int = 2):
    """Fetch fundamentals + 6mo history for one ticker. Returns a record
    dict on success, or None on failure (after retries)."""
    for attempt in range(retries + 1):
        try:
            t = yf.Ticker(ticker)
            info = t.info
            if not info or len(info) < 3:
                raise ValueError("Empty/near-empty response (likely rate-limited)")
            hist = t.history(period="6mo", interval="1d")

            history = [
                {"date": date.strftime("%Y-%m-%d"), "open": row["Open"],
                 "high": row["High"], "low": row["Low"], "close": row["Close"],
                 "volume": int(row["Volume"])}
                for date, row in hist.iterrows()
            ]
            return {
                "ticker": ticker,
                "company_name": info.get("longName") or info.get("shortName") or ticker,
                "sector": info.get("sector", "Unknown"),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "prev_close": info.get("previousClose"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "eps": info.get("trailingEps"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "volume": info.get("volume"),
                "last_updated": datetime.utcnow().isoformat(),
                "history": history,
            }
        except Exception as e:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                print(f"  {ticker} attempt {attempt + 1} failed ({e}); retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Failed to fetch {ticker} after {retries + 1} attempts: {e}")
                return None


def main():
    backend_url = os.environ.get("BACKEND_URL")
    ingest_token = os.environ.get("INGEST_TOKEN")

    if not backend_url or not ingest_token:
        print("ERROR: BACKEND_URL and INGEST_TOKEN environment variables are required.")
        sys.exit(1)

    print(f"Fetching {len(TICKERS)} tickers from Yahoo Finance...")
    records = []
    for i, ticker in enumerate(TICKERS):
        record = fetch_one(ticker)
        if record:
            records.append(record)
            print(f"  [{i+1}/{len(TICKERS)}] {ticker}: OK")
        else:
            print(f"  [{i+1}/{len(TICKERS)}] {ticker}: FAILED")
        if i < len(TICKERS) - 1:
            time.sleep(1.5)

    if not records:
        print("ERROR: No tickers fetched successfully - nothing to push. "
              "This environment's IP may also be blocked by Yahoo Finance.")
        sys.exit(1)

    print(f"\nFetched {len(records)}/{len(TICKERS)} tickers. Pushing to {backend_url}/ingest ...")
    resp = requests.post(
        f"{backend_url}/ingest",
        json={"stocks": records},
        headers={"X-Ingest-Token": ingest_token},
        timeout=60,
    )
    resp.raise_for_status()
    print(f"Success: {resp.json()}")


if __name__ == "__main__":
    main()