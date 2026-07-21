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
    POST /refresh             -> re-fetch live data from yfinance for all tickers

Run locally with:
    uvicorn main:app --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import init_db, get_connection
import data_fetcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts up.
    init_db()
    conn = get_connection()
    row_count = conn.execute("SELECT COUNT(*) as c FROM stocks").fetchone()["c"]
    conn.close()

    # If the DB is empty (first ever run), do an initial fetch so the
    # dashboard isn't blank. On redeploys the DB usually already has data.
    if row_count == 0:
        print("[startup] Empty database detected - fetching initial data...")
        data_fetcher.fetch_all()

    yield  # app runs here
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
    tracked tickers. Useful since free hosting tiers may not support
    background schedulers."""
    success, failed = data_fetcher.fetch_all()
    return {
        "message": f"Refreshed {success}/{len(data_fetcher.TICKERS)} tickers",
        "failed_tickers": failed,
    }
