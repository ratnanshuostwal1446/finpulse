"""
data_fetcher.py
----------------
Pulls live + historical market data from yfinance for a fixed list of
20 NSE-listed companies, and stores it into SQLite via database.py.

Why yfinance: it's free, requires no API key, and wraps Yahoo Finance
data for both current fundamentals (.info) and historical OHLCV
(.history()). NSE tickers need a ".NS" suffix on Yahoo Finance.
"""

import time
import yfinance as yf
from datetime import datetime
from database import get_connection, upsert_stock

TICKERS = [
    "TCS.NS", "HCLTECH.NS",  # IT
    "ICICIBANK.NS", "AXISBANK.NS", "SBIN.NS", "BANKBARODA.NS",  # Banking
    "BEL.NS", "HAL.NS", "SIGMAADV.NS", "AZAD.NS", "DATAPATTNS.NS", "PARAS.NS",  # Defense
    "BHARTIARTL.NS",  # Telecom
    "HINDALCO.NS", "HINDZINC.NS",  # Metal
    "POLYCAB.NS", "BAJFINANCE.NS",  # Industrials/Financials
    "TRENT.NS", "ABFRL.NS", "HINDUNILVR.NS",  # Consumer
]
SECTOR_OVERRIDE = {
    "TCS.NS": "IT", "HCLTECH.NS": "IT",
    "ICICIBANK.NS": "Banking", "AXISBANK.NS": "Banking", "SBIN.NS": "Banking",
    "BANKBARODA.NS": "Banking", "BAJFINANCE.NS": "Banking",
    "BEL.NS": "Defense", "HAL.NS": "Defense", "SIGMAADV.NS": "Defense",
    "AZAD.NS": "Defense", "DATAPATTNS.NS": "Defense", "PARAS.NS": "Defense",
    "BHARTIARTL.NS": "Telecom",
    "HINDALCO.NS": "Metal", "HINDZINC.NS": "Metal", "POLYCAB.NS": "Metal",
    "TRENT.NS": "Consumer", "ABFRL.NS": "Consumer", "HINDUNILVR.NS": "Consumer",
}

def fetch_ticker_data(ticker: str, info: dict, hist) -> dict:
    history = [
        {"date": date.strftime("%Y-%m-%d"), "open": row["Open"], "high": row["High"],
         "low": row["Low"], "close": row["Close"], "volume": int(row["Volume"])}
        for date, row in hist.iterrows()
    ]
    return {
        "ticker": ticker,
        "company_name": info.get("longName") or info.get("shortName") or ticker,
	"sector": SECTOR_OVERRIDE.get(ticker, info.get("sector", "Unknown")),
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


def fetch_and_store_stock(ticker: str, retries: int = 2) -> bool:
    for attempt in range(retries + 1):
        try:
            t = yf.Ticker(ticker)
            info = t.info
            if not info or len(info) < 3:
                raise ValueError("Empty/near-empty response (likely rate-limited)")
            break
        except Exception as e:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                print(f"[data_fetcher] {ticker} attempt {attempt + 1} failed ({e}); retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[data_fetcher] Failed to fetch {ticker} after {retries + 1} attempts: {e}")
                return False

    try:
        hist = t.history(period="6mo", interval="1d")
        record = fetch_ticker_data(ticker, info, hist)
        upsert_stock(record)
        return True
    except Exception as e:
        print(f"[data_fetcher] Failed to fetch {ticker}: {e}")
        return False


def fetch_all(tickers=None, delay_seconds: float = 3.0):
    tickers = tickers or TICKERS
    failed = []
    success = 0
    for i, ticker in enumerate(tickers):
        if fetch_and_store_stock(ticker):
            success += 1
        else:
            failed.append(ticker)
        if i < len(tickers) - 1:
            time.sleep(delay_seconds)
    return success, failed


if __name__ == "__main__":
    from database import init_db
    init_db()
    ok, failed = fetch_all()
    print(f"Fetched {ok}/{len(TICKERS)} tickers successfully.")
    if failed:
        print(f"Failed: {failed}")
