"""
database.py
-----------
Handles all SQLite database setup and connections for FinPulse.

We use SQLite because it's file-based (no separate DB server to run/host),
which is perfect for a small project like this. Everything lives in one
file: finpulse.db

Two tables:
  1. stocks         -> latest snapshot of each company (overwritten on refresh)
  2. price_history   -> daily OHLC history per ticker (appended over time)
"""

import sqlite3
import os

# Store the DB file next to this script so it works regardless of
# what directory the app is launched from (important for deployment).
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finpulse.db")


def get_connection():
    """Open a new connection to the SQLite database.

    check_same_thread=False is needed because FastAPI can handle requests
    on different threads, and by default sqlite3 objects can only be used
    on the thread that created them.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["price"]
    return conn


def init_db():
    """Create tables if they don't already exist. Safe to call every startup."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            price REAL,
            prev_close REAL,
            market_cap REAL,
            pe_ratio REAL,
            eps REAL,
            day_high REAL,
            day_low REAL,
            volume INTEGER,
            last_updated TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            UNIQUE(ticker, date)
        )
    """)

    conn.commit()
    conn.close()


def upsert_stock(record: dict):
    """Write one stock's snapshot + history into the database. This is the
    single source of truth for DB writes, used both by data_fetcher.py
    (when fetching locally, where yfinance calls work fine) and by the
    /ingest endpoint in main.py (which receives pre-fetched data pushed by
    the GitHub Actions job, since yfinance calls made directly FROM Render
    get blocked by Yahoo Finance's cloud-IP rate limiting - see
    PROJECT_REPORT.md for the full explanation).

    Expected shape of `record`:
    {
        "ticker": str, "company_name": str, "sector": str, "price": float,
        "prev_close": float, "market_cap": float, "pe_ratio": float,
        "eps": float, "day_high": float, "day_low": float, "volume": int,
        "last_updated": str (ISO timestamp),
        "history": [
            {"date": "YYYY-MM-DD", "open": float, "high": float,
             "low": float, "close": float, "volume": int}, ...
        ]
    }
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO stocks (ticker, company_name, sector, price, prev_close,
                             market_cap, pe_ratio, eps, day_high, day_low,
                             volume, last_updated)
        VALUES (:ticker, :company_name, :sector, :price, :prev_close,
                :market_cap, :pe_ratio, :eps, :day_high, :day_low,
                :volume, :last_updated)
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
    """, record)

    for row in record.get("history", []):
        cur.execute("""
            INSERT INTO price_history (ticker, date, open, high, low, close, volume)
            VALUES (:ticker, :date, :open, :high, :low, :close, :volume)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume
        """, {**row, "ticker": record["ticker"]})

    conn.commit()
    conn.close()