\# FinPulse — Stock Market Monitoring Platform



\*\*Live Deployment:\*\*

\- Frontend (Dashboard): https://finpulse-7mxpoux9kjtzr5ctjp3kbi.streamlit.app/

\- Backend (REST API + docs): https://finpulse-fn4r.onrender.com/docs



FinPulse tracks 20 NSE-listed Indian companies across six sectors (IT,

Banking, Defense, Telecom, Metal, Consumer) and displays live +

historical market data through an interactive dashboard, backed by a

REST API and a SQLite database.



Built for SoFI AlgoLabs Assignment 1.



\## Companies Tracked



| Sector | Companies |

|---|---|

| IT | TCS, HCL Technologies |

| Banking | ICICI Bank, Axis Bank, SBI, Bank of Baroda, Bajaj Finance |

| Defense | Bharat Electronics, HAL, Sigma Advanced Systems, Azad Engineering, Data Patterns, Paras Defence |

| Telecom | Bharti Airtel |

| Metal | Hindalco, Hindustan Zinc, Polycab India |

| Consumer | Trent, Aditya Birla Fashion \& Retail, Hindustan Unilever |



Sector labels are custom-assigned (see `SECTOR\_OVERRIDE` in the code)

rather than using yfinance's default classification, so the dashboard

groups companies the way an analyst actually would, not by generic

categories like "Basic Materials" or "Financial Services."



\## Architecture



FinPulse has two independent data-refresh paths, because of a real

production constraint discovered during development: \*\*Yahoo Finance

blocks requests from cloud-hosting IP ranges\*\* (Render, AWS, etc.), so

the backend cannot reliably fetch live data on its own once deployed.



```

LOCAL DEVELOPMENT PATH (works because your home IP isn't blocked)

&#x20;   yfinance --> data\_fetcher.py --> SQLite --> FastAPI --> Streamlit

&#x20;                (POST /refresh triggers this directly)



PRODUCTION PATH (the one that actually works once deployed)

&#x20;   yfinance --> scripts/push\_live\_data.py --> POST /ingest --> SQLite --> FastAPI --> Streamlit

&#x20;                (runs on GitHub Actions, NOT on Render -

&#x20;                 GitHub's IP isn't blocked by Yahoo Finance)

```



The backend itself never calls yfinance in the production path — it

only receives pre-fetched data over an authenticated HTTP endpoint.

This is why there are two separate scripts with near-identical fetch

logic (`backend/data\_fetcher.py` for local use, `scripts/push\_live\_data.py`

for the GitHub Actions job): they can't share a Python import, since

the Actions job runs standalone without the rest of the backend

package installed.



A GitHub Actions workflow (`.github/workflows/refresh.yml`) runs this

production path automatically once daily, and can also be triggered

manually from the repo's Actions tab for on-demand refreshes.



\## Tech Stack



| Layer      | Technology              |

|------------|--------------------------|

| Data       | yfinance (Yahoo Finance) |

| Database   | SQLite                   |

| Backend    | FastAPI + Uvicorn        |

| Frontend   | Streamlit + Plotly       |

| Automation | GitHub Actions           |

| Deployment | Render (backend), Streamlit Community Cloud (frontend) |



\## Project Structure



```

finpulse/

├── .github/workflows/

│   └── refresh.yml        # Scheduled + manual production data refresh

├── backend/

│   ├── main.py             # FastAPI app + REST endpoints

│   ├── database.py         # SQLite connection + schema + shared upsert logic

│   ├── data\_fetcher.py     # Local-only fetch path (yfinance -> SQLite directly)

│   ├── requirements.txt

│   └── finpulse.db         # Seeded with real data; also regenerable locally

├── scripts/

│   └── push\_live\_data.py   # Production fetch path (yfinance -> POST /ingest)

├── frontend/

│   ├── app.py               # Streamlit dashboard

│   ├── requirements.txt

│   └── .streamlit/

│       └── secrets.toml.example

├── PROJECT\_REPORT.md

├── .gitignore

└── README.md

```



\## Database Design



\*\*`stocks`\*\* — one row per ticker, upserted on every refresh (latest snapshot):

`ticker (PK), company\_name, sector, price, prev\_close, market\_cap, pe\_ratio, eps, day\_high, day\_low, volume, last\_updated`



\*\*`price\_history`\*\* — one row per (ticker, date), appended over time:

`id (PK), ticker, date, open, high, low, close, volume`, unique on `(ticker, date)` so re-fetching never creates duplicates.



Both the local fetch path and the production `/ingest` path write

through a single shared function (`database.upsert\_stock()`), so the

write logic can't drift between the two paths.



\## REST API Endpoints



| Method | Endpoint            | Description                                    |

|--------|----------------------|---------------------------------------------------|

| GET    | `/`                  | Health check                                       |

| GET    | `/stocks`            | List latest snapshot for all 20 companies          |

| GET    | `/stocks/{ticker}`   | Single company detail + full price history          |

| DELETE | `/stocks/{ticker}`   | Remove a ticker and its history (auth required)      |

| GET    | `/market-summary`    | Total market cap, market-cap-weighted avg P/E, gainers/losers |

| POST   | `/refresh`           | Local-only: fetch live data directly (fails on Render, see Architecture) |

| POST   | `/ingest`             | Production: accept pre-fetched data pushed from GitHub Actions (auth required) |



Interactive API docs are auto-generated by FastAPI at `/docs`.



\### A note on the average P/E calculation

`/market-summary`'s `average\_pe\_ratio` is a \*\*market-cap-weighted

average\*\*, not a simple mean: `Sum(P/E x market\_cap) / Sum(market\_cap)`

across all stocks with both values available. This gives larger

companies proportionally more influence on the number, which better

reflects "what the market as a whole is paying" than an unweighted

average that would let a single small-cap outlier with an extreme P/E

skew the result as much as a mega-cap.



\## Running Locally



You'll need Python 3.10+ and two terminal windows.



\*\*Terminal 1 — Backend:\*\*

```bash

cd backend

python -m venv venv

source venv/bin/activate      # Windows: venv\\Scripts\\activate

pip install -r requirements.txt

uvicorn main:app --reload

```

Backend runs at `http://localhost:8000`. Visit `http://localhost:8000/docs`

to test the API directly. The repo ships with a pre-seeded `finpulse.db`;

to force a fresh local fetch, delete it first and call `POST /refresh`.



\*\*Terminal 2 — Frontend:\*\*

```bash

cd frontend

python -m venv venv

source venv/bin/activate

pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml

streamlit run app.py

```

Dashboard opens at `http://localhost:8501`.



\## Deployment



\*\*Backend (Render):\*\*

1\. Push this repo to GitHub.

2\. Render: New -> Web Service -> connect the repo. Root directory: `backend`.

3\. Build command: `pip install -r requirements.txt`

4\. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

5\. Set environment variable `INGEST\_TOKEN` to a secret value (required for `/ingest` and `DELETE` to work).



\*\*Frontend (Streamlit Community Cloud):\*\*

1\. share.streamlit.io -> New app -> select repo -> main file path: `frontend/app.py`

2\. In App settings -> Secrets: `API\_URL = "https://your-render-url.onrender.com"`



\*\*Production data refresh (GitHub Actions):\*\*

1\. Repo -> Settings -> Secrets and variables -> Actions, add:

&#x20;  - `BACKEND\_URL` = your Render URL

&#x20;  - `INGEST\_TOKEN` = same value set on Render

2\. The workflow runs daily automatically (04:00 UTC), or trigger manually from the Actions tab -> "Scheduled data refresh" -> "Run workflow".


Note: both free-tier hosting platforms used here sleep after
inactivity. Render (backend) spins down after idle time, causing the
first request to take 30-60s to wake up - the dashboard shows a
friendly "waking up" message rather than a raw error in that case.
Streamlit Community Cloud (frontend) has separate, independent sleep
behavior of its own: if the app itself hasn't been visited in a
while, Streamlit shows its own standard "This app has gone to sleep
due to inactivity" screen with a one-click wake-up button, before the
dashboard loads at all. This is standard Streamlit Cloud platform
behavior, not specific to this app, and any visitor to any free-tier
Streamlit app would see the same screen.



\## External APIs / Libraries / AI Tools Used



\- \*\*yfinance\*\* — unofficial Yahoo Finance data library, used for all market data.

\- \*\*FastAPI\*\*, \*\*Streamlit\*\*, \*\*Plotly\*\*, \*\*pandas\*\*, \*\*requests\*\* — standard open-source libraries.

\- \*\*AI tool disclosure:\*\* I used Claude (Anthropic) to scaffold and iteratively debug this codebase, per the assignment's allowance for AI use in the AlgoLabs track. All architecture decisions, debugging, and understanding of implementation were done collaboratively with me driving the decisions and verifying every change locally before deployment.



\## Known Limitations / Future Improvements



See `PROJECT\_REPORT.md` for the full breakdown of features, challenges, and future improvement ideas.

