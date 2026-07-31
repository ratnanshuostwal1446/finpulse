"""
app.py
------
Streamlit dashboard for FinPulse. This is a pure frontend - it holds no
data itself. Every piece of data on screen comes from calling the
FastAPI backend's REST endpoints over HTTP (via the `requests` library).

This separation (frontend calls backend via REST, doesn't touch the DB
directly) is exactly what the assignment is testing: that you understand
how components of a web app talk to each other.
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---- Config ----------------------------------------------------------
# Change this to your deployed Render backend URL once live.
# For local testing, this points at a locally-running FastAPI instance.
API_URL = st.secrets.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="FinPulse", page_icon="📈", layout="wide")


# ---- Helper functions to call the backend -----------------------------
@st.cache_data(ttl=60, show_spinner="Loading...")  # cache for 60s so we don't hammer the API on every rerun
def get_stocks():
    r = requests.get(f"{API_URL}/stocks", timeout=15)
    r.raise_for_status()
    return pd.DataFrame(r.json())


@st.cache_data(ttl=60, show_spinner="Loading...")
def get_stock_detail(ticker):
    r = requests.get(f"{API_URL}/stocks/{ticker}", timeout=15)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=60, show_spinner="Loading...")
def get_market_summary():
    r = requests.get(f"{API_URL}/market-summary", timeout=15)
    r.raise_for_status()
    return r.json()


def trigger_refresh():
    with st.spinner("Refreshing live data from yfinance... this can take ~30s for 20 tickers"):
        r = requests.post(f"{API_URL}/refresh", timeout=120)
        r.raise_for_status()
        return r.json()


# ---- Sidebar ------------------------------------------------------------
st.sidebar.title("📈 FinPulse")
st.sidebar.caption("Indian equity market monitoring dashboard")

st.sidebar.caption(
    "ℹ️ Data refreshes automatically once daily via a scheduled GitHub "
    "Action (fetches live prices and pushes updates to the backend) - "
    "see the 'Data last updated' timestamp above for freshness. See "
    "README for architecture details."
)
st.sidebar.markdown("---")


# ---- Main content ---------------------------------------------------------
st.title("FinPulse — Market Dashboard")

try:
    stocks_df = get_stocks()
except Exception:
    st.warning(
        "⏳ Couldn't reach the backend just now. If this app (or the "
        "backend on Render) has been idle for a while, it may be waking "
        "up from sleep - this can take 30-60 seconds on the free tier. "
        "Please wait a moment and refresh this page."
    )
    st.stop()

if stocks_df.empty:
    st.warning("No data yet. Click 'Refresh live data' in the sidebar to fetch it.")
    st.stop()

# Show data freshness - important given the deployed version uses
# pre-fetched/scheduled data rather than fetching on every request.

if "last_updated" in stocks_df.columns and not stocks_df["last_updated"].isna().all():
    most_recent_utc = pd.to_datetime(stocks_df["last_updated"], format="mixed").max()
    # Data is stored in UTC (datetime.utcnow() on the backend); convert to
    # IST (UTC+5:30) for display, since that's the relevant timezone for
    # Indian equity data.
    most_recent_ist = most_recent_utc.tz_localize("UTC").tz_convert("Asia/Kolkata")
    st.caption(f"📅 Data last updated: {most_recent_ist.strftime('%d %b %Y, %H:%M IST')}")

# --- Market summary cards ---
summary = get_market_summary()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Companies Tracked", summary.get("total_companies", "-"))
col2.metric("Total Market Cap", f"₹{summary.get('total_market_cap', 0) / 1e7:.0f} Cr"
            if summary.get("total_market_cap") else "-")
col3.metric("Average P/E Ratio", summary.get("average_pe_ratio", "-"))
col4.metric("Gainers / Losers",
            f"{summary.get('gainers_count', 0)} / {summary.get('losers_count', 0)}")

st.markdown("---")

# --- Full stock table ---
st.subheader("All Tracked Companies")
display_df = stocks_df[["ticker", "company_name", "sector", "price",
                          "pe_ratio", "eps", "market_cap", "volume"]].copy()
# Market cap comes from yfinance in raw rupees; convert to crores (1 Cr = 1e7)
# for readability, matching how Indian equity reports normally present it.

display_df["market_cap"] = (display_df["market_cap"] / 1e7).round(0)
display_df.columns = ["Ticker", "Company", "Sector", "Price (₹)",
                        "P/E", "EPS", "Market Cap (₹ in Cr)", "Volume"]
display_df.index = range(1, len(display_df) + 1)  # 1-20 instead of 0-19
st.dataframe(display_df, use_container_width=True)

st.markdown("---")

# --- Historical price chart for one company ---
st.subheader("Historical Price Chart")
selected_ticker = st.selectbox("Select a company", stocks_df["ticker"].tolist())
detail = get_stock_detail(selected_ticker)
history_df = pd.DataFrame(detail["history"])

if not history_df.empty:
    # Two rows sharing the x-axis: candlestick on top, volume bars below -
    # this is the standard "price + volume" layout used in trading platforms.
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.03,
    )
    fig.add_trace(go.Candlestick(
        x=history_df["date"],
        open=history_df["open"], high=history_df["high"],
        low=history_df["low"], close=history_df["close"],
        name=selected_ticker,
    ), row=1, col=1)

    # Color each volume bar green/red based on whether that day closed up or down
    volume_colors = ["#26A69A" if c >= o else "#EF5350"
                      for c, o in zip(history_df["close"], history_df["open"])]
    fig.add_trace(go.Bar(
        x=history_df["date"], y=history_df["volume"],
        marker_color=volume_colors, name="Volume",
    ), row=2, col=1)

    fig.update_layout(
        title=f"{detail['stock']['company_name']} — 6 Month Price & Volume History",
        xaxis2_title="Date", yaxis_title="Price (₹)", yaxis2_title="Volume",
        xaxis_rangeslider_visible=False,
        height=550, showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No historical data available for this ticker yet.")

st.markdown("---")

# --- Company comparison ---
st.subheader("Company Comparison")
compare_tickers = st.multiselect(
    "Select companies to compare (fundamentals)",
    stocks_df["ticker"].tolist(),
    default=stocks_df["ticker"].tolist()[:5],
)

if compare_tickers:
    compare_df = stocks_df[stocks_df["ticker"].isin(compare_tickers)].copy()
    metric_labels = {"pe_ratio": "P/E", "eps": "EPS", "market_cap": "Market Cap", "price": "Price"}
    metric_choice = st.radio(
        "Metric to compare", ["pe_ratio", "eps", "market_cap", "price"],
        format_func=lambda x: metric_labels[x],
        horizontal=True,
    )
    y_values = compare_df[metric_choice]
    y_label = metric_choice.replace('_', ' ').title()
    if metric_choice == "market_cap":
        y_values = y_values / 1e7  # show in crores, consistent with the table above
        y_label = "Market Cap (₹ in Cr)"

    fig2 = go.Figure(data=[go.Bar(
        x=compare_df["company_name"], y=y_values,
        marker_color="#4C78A8",  # calm steel blue instead of the default red
    )])
    fig2.update_layout(
        title=f"Comparison by {y_label}",
        yaxis_title=y_label,
        height=400,
    )
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# --- Sector-wise breakdown (bonus feature) ---
st.subheader("Sector-wise Market Cap Breakdown")
sector_df = stocks_df.groupby("sector")["market_cap"].sum().reset_index()
fig3 = go.Figure(data=[go.Pie(labels=sector_df["sector"], values=sector_df["market_cap"])])
fig3.update_layout(height=400)
st.plotly_chart(fig3, use_container_width=True)
