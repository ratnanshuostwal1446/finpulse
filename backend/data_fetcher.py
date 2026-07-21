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
from database import get_connection

# 20 NSE-listed companies we track. Mostly large, liquid names so data
# is reliable. HAL.NS (Hindustan Aeronautics) included as an aerospace/
# defense sector reference point.
TICKERS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "ITC.NS", "LT.NS", "HINDUNILVR.NS", "BAJFINANCE.NS",
    "KOTAKBANK.NS", "BHARTIARTL.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "TITAN.NS", "SUNPHARMA.NS", "WIPRO.NS", "ULTRACEMCO.NS",
    "TMPV.NS", "HAL.NS",
]


def fetch_and_store_stock(ticker: str, retries: int = 2) -> bool:
    """Fetch fundamentals + 6 months of daily history for one ticker
    and upsert into the database. Returns True on success, False if
    this ticker failed (so the caller can skip it and continue).

    Retries a couple of times with a growing pause if Yahoo Finance
    rate-limits us (HTTP 429), since that's usually transient."""
    for attempt in range(retries + 1):
        try:
            t = yf.Ticker(ticker)
            info = t.info  # dict of fundamentals from Yahoo Finance
            if not info or len(info) < 3:
                raise ValueError("Empty/near-empty response (likely rate-limited)")
            break
        except Exception as e:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                print(f"[data_fetcher] {ticker} attempt {attempt + 1} failed "
                      f"({e}); retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[data_fetcher] Failed to fetch {ticker} after "
                      f"{retries + 1} attempts: {e}")
                return False

    try:
        company_name = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "Unknown")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose")
        market_cap = info.get("marketCap")
        pe_ratio = info.get("trailingPE")
        eps = info.get("trailingEps")
        day_high = info.get("dayHigh")
        day_low = info.get("dayLow")
        volume = info.get("volume")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO stocks (ticker, company_name, sector, price, prev_close,
                                 market_cap, pe_ratio, eps, day_high, day_low,
                                 volume, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                company_name=excluded.company_name,
                sector=excluded.sector,
                price=excluded.price,
                prev_close=excluded.prev_close,
                market_cap=excluded.market_cap,
                pe_ratio=excluded.pe_ratio,
                eps=excluded.eps,
                day_high=excluded.day_high,
                day_low=excluded.day_low,
                volume=excluded.volume,
                last_updated=excluded.last_updated
        """, (ticker, company_name, sector, price, prev_close, market_cap,
              pe_ratio, eps, day_high, day_low, volume,
              datetime.utcnow().isoformat()))

        # Historical daily prices (last 6 months)
        hist = t.history(period="6mo", interval="1d")
        for date, row in hist.iterrows():
            cur.execute("""
                INSERT INTO price_history (ticker, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume
            """, (ticker, date.strftime("%Y-%m-%d"), row["Open"], row["High"],
                  row["Low"], row["Close"], int(row["Volume"])))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"[data_fetcher] Failed to fetch {ticker}: {e}")
        return False


def fetch_all(tickers=None, delay_seconds: float = 3.0):
    """Fetch every ticker in the list, pausing between each request so we
    don't fire 20 rapid requests at Yahoo Finance and trip its rate
    limiter (this is what was causing 429 errors). Returns
    (success_count, failed_list)."""
    tickers = tickers or TICKERS
    failed = []
    success = 0
    for i, ticker in enumerate(tickers):
        if fetch_and_store_stock(ticker):
            success += 1
        else:
            failed.append(ticker)
        if i < len(tickers) - 1:  # no need to sleep after the last one
            time.sleep(delay_seconds)
    return success, failed


if __name__ == "__main__":
    from database import init_db
    init_db()
    ok, failed = fetch_all()
    print(f"Fetched {ok}/{len(TICKERS)} tickers successfully.")
    if failed:
        print(f"Failed: {failed}")