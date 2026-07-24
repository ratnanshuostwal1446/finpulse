"""
main.py
-------
FastAPI app for FinPulse. Exposes REST endpoints that the Streamlit
frontend (or anyone else) can call to read stock data.

Endpoints:
    GET  /                  -> health check
    GET  /stocks             -> list all tracked stocks with latest snapshot
    GET  /stocks/{ticker}    -> single stock detail + historical prices
    GET  /market-summary     -> aggregate market stats
    POST /refresh             -> re-fetch live data from yfinance directly
                                  on Render (works locally; typically fails
                                  on Render itself - see /ingest below)
    POST /ingest               -> accept pre-fetched data pushed from
                                  elsewhere (used by the GitHub Actions
                                  scheduled job, which fetches via yfinance
                                  from its own IP and pushes the results
                                  here, since Render's own IP is blocked
                                  by Yahoo Finance)

Run locally with:
    uvicorn main:app --reload
"""

import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Optional

from database import init_db, get_connection, upsert_stock
import data_fetcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts up. Deliberately does NOT fetch
    # live data here - only sets up the (fast, local) database schema.
    #
    # Why: hosting platforms like Render expect the app to bind its port
    # within a short window after starting. yfinance calls (especially
    # 20 of them with retries) can take minutes, and cloud IPs get
    # rate-limited by Yahoo Finance more aggressively than home
    # connections - so blocking startup on that fetch caused deploys to
    # time out. Instead, the database starts empty and gets populated by
    # calling POST /refresh once after the app is live (the Streamlit
    # dashboard's "Refresh live data" button does exactly this).
    init_db()
    yield
    # (no shutdown cleanup needed for SQLite)


app = FastAPI(title="FinPulse API", version="1.0", lifespan=lifespan)

# Allow the Streamlit frontend (hosted on a different domain) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "message": "FinPulse API is running"}


@app.get("/stocks")
def get_all_stocks():
    """Returns the latest snapshot for every tracked company."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM stocks ORDER BY market_cap DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/stocks/{ticker}")
def get_stock_detail(ticker: str):
    """Returns fundamentals + full historical price series for one ticker."""
    conn = get_connection()
    stock = conn.execute(
        "SELECT * FROM stocks WHERE ticker = ?", (ticker,)
    ).fetchone()

    if stock is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    history = conn.execute(
        "SELECT date, open, high, low, close, volume FROM price_history "
        "WHERE ticker = ? ORDER BY date ASC", (ticker,)
    ).fetchall()
    conn.close()

    return {
        "stock": dict(stock),
        "history": [dict(row) for row in history],
    }


@app.get("/market-summary")
def get_market_summary():
    """Aggregate stats across all tracked stocks: total market cap,
    average P/E, and counts of gainers vs losers based on price vs
    previous close."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM stocks").fetchall()
    conn.close()

    if not rows:
        return {"message": "No data yet - call POST /refresh first"}

    total_market_cap = sum(r["market_cap"] or 0 for r in rows)
    pe_values = [r["pe_ratio"] for r in rows if r["pe_ratio"] is not None]
    avg_pe = sum(pe_values) / len(pe_values) if pe_values else None

    gainers, losers = [], []
    for r in rows:
        if r["price"] is None or r["prev_close"] is None:
            continue
        change_pct = (r["price"] - r["prev_close"]) / r["prev_close"] * 100
        entry = {"ticker": r["ticker"], "company_name": r["company_name"],
                  "change_pct": round(change_pct, 2)}
        if change_pct >= 0:
            gainers.append(entry)
        else:
            losers.append(entry)

    gainers.sort(key=lambda x: x["change_pct"], reverse=True)
    losers.sort(key=lambda x: x["change_pct"])

    return {
        "total_companies": len(rows),
        "total_market_cap": total_market_cap,
        "average_pe_ratio": round(avg_pe, 2) if avg_pe else None,
        "gainers_count": len(gainers),
        "losers_count": len(losers),
        "top_gainers": gainers[:5],
        "top_losers": losers[:5],
    }


@app.post("/refresh")
def refresh_data():
    """Manually trigger a fresh pull of live data from yfinance for all
    tracked tickers. Works reliably when the backend itself is running
    somewhere with an unblocked IP (e.g. locally); on Render this
    typically fails since Yahoo Finance blocks cloud-hosting IP ranges.
    For the production refresh path, see /ingest."""
    success, failed = data_fetcher.fetch_all()
    return {
        "message": f"Refreshed {success}/{len(data_fetcher.TICKERS)} tickers",
        "failed_tickers": failed,
    }


class HistoryPoint(BaseModel):
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None


class StockRecord(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    price: Optional[float] = None
    prev_close: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[int] = None
    last_updated: str
    history: List[HistoryPoint] = []


class IngestPayload(BaseModel):
    stocks: List[StockRecord]


@app.post("/ingest")
def ingest_data(payload: IngestPayload, x_ingest_token: str = Header(default="")):
    """Accepts pre-fetched stock data and writes it to the database,
    WITHOUT making any yfinance/network calls itself. This is the
    production-safe way to refresh data on Render: the actual fetching
    happens elsewhere (the GitHub Actions job, or your own machine, using
    scripts/push_live_data.py) where Yahoo Finance doesn't block the IP,
    and the result is pushed here over a simple authenticated HTTP call.

    Protected by a shared-secret header so random internet traffic can't
    write arbitrary data into the database. Set the INGEST_TOKEN
    environment variable on the backend, and pass the same value as the
    X-Ingest-Token header when calling this endpoint.
    """
    expected_token = os.environ.get("INGEST_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="INGEST_TOKEN is not configured on this server - set it "
                   "as an environment variable before using /ingest.",
        )
    if x_ingest_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Ingest-Token header")

    written = 0
    for stock in payload.stocks:
        record = stock.model_dump()
        upsert_stock(record)
        written += 1

    return {"message": f"Ingested {written} stock record(s)"}

@app.delete("/stocks/{ticker}")
def delete_stock(ticker: str, x_ingest_token: str = Header(default="")):
    """Remove a ticker and its history from the database. Protected by the
    same shared-secret token as /ingest, since this is also a
    write/destructive operation that shouldn't be publicly callable."""
    expected_token = os.environ.get("INGEST_TOKEN")
    if not expected_token or x_ingest_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Ingest-Token header")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM stocks WHERE ticker = ?", (ticker,))
    cur.execute("DELETE FROM price_history WHERE ticker = ?", (ticker,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"message": f"Deleted ticker '{ticker}'", "rows_affected": deleted}
