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

# ---- Config ----------------------------------------------------------
# Change this to your deployed Render backend URL once live.
# For local testing, this points at a locally-running FastAPI instance.
API_URL = st.secrets.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="FinPulse", page_icon="📈", layout="wide")


# ---- Helper functions to call the backend -----------------------------
@st.cache_data(ttl=60)  # cache for 60s so we don't hammer the API on every rerun
def get_stocks():
    r = requests.get(f"{API_URL}/stocks", timeout=15)
    r.raise_for_status()
    return pd.DataFrame(r.json())


@st.cache_data(ttl=60)
def get_stock_detail(ticker):
    r = requests.get(f"{API_URL}/stocks/{ticker}", timeout=15)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=60)
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

if st.sidebar.button("🔄 Refresh live data"):
    result = trigger_refresh()
    st.sidebar.success(result["message"])
    st.cache_data.clear()

st.sidebar.markdown("---")
st.sidebar.caption(f"Backend: `{API_URL}`")


# ---- Main content ---------------------------------------------------------
st.title("FinPulse — Market Dashboard")

try:
    stocks_df = get_stocks()
except Exception as e:
    st.error(f"Could not reach the backend API at {API_URL}. "
              f"Make sure it's running. Error: {e}")
    st.stop()

if stocks_df.empty:
    st.warning("No data yet. Click 'Refresh live data' in the sidebar to fetch it.")
    st.stop()

# --- Market summary cards ---
summary = get_market_summary()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Companies Tracked", summary.get("total_companies", "-"))
col2.metric("Total Market Cap", f"₹{summary.get('total_market_cap', 0):,.0f} Cr"
            if summary.get("total_market_cap") else "-")
col3.metric("Average P/E Ratio", summary.get("average_pe_ratio", "-"))
col4.metric("Gainers / Losers",
            f"{summary.get('gainers_count', 0)} / {summary.get('losers_count', 0)}")

st.markdown("---")

# --- Full stock table ---
st.subheader("All Tracked Companies")
display_df = stocks_df[["ticker", "company_name", "sector", "price",
                          "pe_ratio", "eps", "market_cap", "volume"]].copy()
display_df.columns = ["Ticker", "Company", "Sector", "Price (₹)",
                        "P/E", "EPS", "Market Cap", "Volume"]
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.markdown("---")

# --- Historical price chart for one company ---
st.subheader("Historical Price Chart")
selected_ticker = st.selectbox("Select a company", stocks_df["ticker"].tolist())
detail = get_stock_detail(selected_ticker)
history_df = pd.DataFrame(detail["history"])

if not history_df.empty:
    fig = go.Figure(data=[go.Candlestick(
        x=history_df["date"],
        open=history_df["open"],
        high=history_df["high"],
        low=history_df["low"],
        close=history_df["close"],
        name=selected_ticker,
    )])
    fig.update_layout(
        title=f"{detail['stock']['company_name']} — 6 Month Price History",
        xaxis_title="Date", yaxis_title="Price (₹)",
        xaxis_rangeslider_visible=False,
        height=450,
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
    compare_df = stocks_df[stocks_df["ticker"].isin(compare_tickers)]
    metric_choice = st.radio(
        "Metric to compare", ["pe_ratio", "eps", "market_cap", "price"],
        horizontal=True,
    )
    fig2 = go.Figure(data=[go.Bar(
        x=compare_df["company_name"], y=compare_df[metric_choice],
    )])
    fig2.update_layout(
        title=f"Comparison by {metric_choice.replace('_', ' ').title()}",
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
