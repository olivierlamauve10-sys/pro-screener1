import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import pickle
import time


# ─────────────────────────────────────────────────────────────
#                      CONFIG + UI
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Screener Weekly RSI", layout="wide")
st.title("📈 Screener RSI — Weekly Reversal")

CACHE_DIR = "cache_data"
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 3600  # 1h cache local


# ─────────────────────────────────────────────────────────────
#                  MARKET JSON
# ─────────────────────────────────────────────────────────────
@st.cache_data
def load_markets():
    try:
        with open("markets.json", "r", encoding="utf-8") as f:
            markets = json.load(f)

        if os.path.exists("sp500.json"):
            with open("sp500.json", "r", encoding="utf-8") as f:
                sp500_data = json.load(f)
            if "S&P 500" in sp500_data:
                markets["🇺🇸 S&P 500 (USA)"] = sp500_data["S&P 500"]
        return markets
    except:
        return {"⚠️ Aucun marché dispo": []}


markets = load_markets()
selected_markets = st.multiselect(
    "Marchés à scanner",
    options=list(markets.keys()),
    default=["🇫🇷 SBF 120 (France)"]
)
tickers = [t for m in selected_markets for t in markets[m]]
st.write(f"📊 {len(tickers)} actions sélectionnées")


# ─────────────────────────────────────────────────────────────
#               FETCH + CACHE WEEKLY DATA
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_data(symbol):
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.pkl")

    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime < CACHE_TTL:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except:
                pass

    df = yf.Ticker(symbol).history(period="2y", interval="1wk")

    if df is not None and not df.empty:
        with open(cache_path, "wb") as f:
            pickle.dump(df, f)
    return df


# ─────────────────────────────────────────────────────────────
#                  INDICATEURS WEEKLY
# ─────────────────────────────────────────────────────────────
def compute_indicators(df):
    df = df.copy()
    df["EMA200"] = ta.ema(df["Close"], length=40)
    df["EMA50"] = ta.ema(df["Close"], length=10)
    df["EMA7"] = ta.ema(df["Close"], length=4)
    df["RSI7"] = ta.rsi(df["Close"], length=7)

    macd = ta.macd(df["Close"], fast=6, slow=15, signal=3)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)
    return df


# ─────────────────────────────────────────────────────────────
#         CONDITION REBOND RSI WEEKLY (définitif)
# ─────────────────────────────────────────────────────────────
def check_rsi_reversal(df):
    R = df["RSI7"]
    return (
        R.iloc[-3] < 30 and R.iloc[-2] < 30 and R.iloc[-1] > 30
    ) or (
        R.iloc[-4] < 30 and R.iloc[-3] < 30 and R.iloc[-2] > 30 and R.iloc[-1] > 30
    )


# ─────────────────────────────────────────────────────────────
#            ANALYSE SYMBOL — return minimal info
# ─────────────────────────────────────────────────────────────
def analyze_symbol(symbol):
    try:
        df = get_data(symbol)
        if df is None or df.empty:
            return None

        df = compute_indicators(df)

        if check_rsi_reversal(df):
            info = yf.Ticker(symbol).info
            name = info.get("shortName", "??")
            price = float(df.iloc[-1]["Close"])
            return {"Symbole": symbol, "Nom": name, "Prix": f"{price:.2f}"}

        return None
    except:
        return None


# ─────────────────────────────────────────────────────────────
#        HEIKIN ASHI
# ─────────────────────────────────────────────────────────────
def compute_heikin_ashi(df):
    ha = df.copy()
    ha["HA_Close"] = (ha["Open"] + ha["High"] + ha["Low"] + ha["Close"]) / 4
    ha.loc[0, "HA_Open"] = (ha.loc[0, "Open"] + ha.loc[0, "Close"]) / 2

    for i in range(1, len(ha)):
        ha.loc[i, "HA_Open"] = (ha.loc[i-1, "HA_Open"] + ha.loc[i-1, "HA_Close"]) / 2

    ha["HA_High"] = ha[["High", "HA_Open", "HA_Close"]].max(axis=1)
    ha["HA_Low"]  = ha[["Low", "HA_Open", "HA_Close"]].min(axis=1)

    return ha


# ─────────────────────────────────────────────────────────────
#       PLOT WEEKLY HEIKIN + DAILY ZOOM
# ─────────────────────────────────────────────────────────────
def plot_chart(symbol):
    try:
        # weekly
        df = get_data(symbol)
        df = compute_indicators(df)
        ha = compute_heikin_ashi(df)

        # daily zoom
        daily = yf.Ticker(symbol).history(period="2mo", interval="1d")
        if daily is not None and not daily.empty:
            daily["EMA7"] = ta.ema(daily["Close"], length=7)
            daily["EMA20"] = ta.ema(daily["Close"], length=20)
            zoom_ok = True
        else:
            zoom_ok = False

        fig = make_subplots(
            rows=3, cols=2,
            shared_xaxes=False,
            column_widths=[0.67, 0.33],
            horizontal_spacing=0.05,
            vertical_spacing=0.03,
            subplot_titles=["Weekly Heikin Ashi", "Daily zoom", "RSI weekly", "", "MACD", ""]
        )

        # weekly — HA
        fig.add_trace(go.Candlestick(
            x=ha.index,
            open=ha["HA_Open"], high=ha["HA_High"],
            low=ha["HA_Low"], close=ha["HA_Close"],
            increasing_line_color="green", decreasing_line_color="red"
        ), row=1, col=1)

        # weekly — EMA
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], mode="lines", line=dict(color="purple")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA7"], mode="lines", line=dict(color="cyan")), row=1, col=1)

        for i in range(1, len(df)):
            col = "blue" if df["EMA200"].iloc[i] >= df["EMA200"].iloc[i-1] else "red"
            fig.add_trace(go.Scatter(
                x=df.index[i-1:i+1], y=df["EMA200"].iloc[i-1:i+1],
                line=dict(color=col, width=2)
            ), row=1, col=1)

        # DAILY
        if zoom_ok:
            fig.add_trace(go.Candlestick(
                x=daily.index,
                open=daily["Open"], high=daily["High"], low=daily["Low"], close=daily["Close"]
            ), row=1, col=2)

            fig.add_trace(go.Scatter(x=daily.index, y=daily["EMA7"], line=dict(color="cyan")), row=1, col=2)
            fig.add_trace(go.Scatter(x=daily.index, y=daily["EMA20"], line=dict(color="orange")), row=1, col=2)

            if len(daily) > 50:
                fig.update_xaxes(range=[daily.index[-50], daily.index[-1]], row=1, col=2)

        # RSI
        rsi = df["RSI7"]
        fig.add_trace(go.Scatter(x=df.index, y=rsi, mode="lines"), row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)
        fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)

        # MACD
        if "MACD_6_15_3" in df:
            fig.add_trace(go.Bar(x=df.index, y=df["MACDh_6_15_3"], opacity=0.4), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["MACD_6_15_3"]), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["MACDs_6_15_3"]), row=3, col=1)

        fig.update_layout(
            height=780,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            dragmode="drawline",
            modebar_add=['drawline', 'drawopenpath', 'drawrect', 'eraseshape']
        )

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")


# ─────────────────────────────────────────────────────────────
#                  SCAN BUTTON
# ─────────────────────────────────────────────────────────────
if st.button("🚀 LANCER LE SCANNER", type="primary"):
    with st.spinner("Scanning…"):

        results = []
        progress = st.progress(0)
        total = len(tickers)
        workers = min(8, total)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(analyze_symbol, t): t for t in tickers}
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                if res:
                    results.append(res)
                progress.progress((i + 1) / total)

        if results:
            df_res = pd.DataFrame(results)
            st.success(f"🎯 {len(df_res)} opportunités détectées")
            st.session_state.last_results = df_res
        else:
            st.warning("Aucun signal détecté")
            st.session_state.last_results = None


# ─────────────────────────────────────────────────────────────
#              AFFICHAGE DES RÉSULTATS
# ─────────────────────────────────────────────────────────────
if "last_results" in st.session_state and st.session_state.last_results is not None:
    st.subheader("📌 Opportunités détectées")

    df_res = st.session_state.last_results

    for idx, row in df_res.iterrows():
        with st.container():
            st.write(f"🔹 **{row['Symbole']} — {row['Nom']}** — {row['Prix']}€")

            if st.button("📈 Voir", key=f"btn_{row['Symbole']}"):
                plot_chart(row["Symbole"])
                st.markdown("---")
