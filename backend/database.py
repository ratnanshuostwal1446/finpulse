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
