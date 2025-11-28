# =======================================================
# ===================== IMPORTS =========================
# =======================================================
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

# =======================================================
# =================== CONFIG GLOBAL =====================
# =======================================================

CACHE_DIR = "cache_data"
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 3600  # 1h

st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("📈 Screener W")


# =======================================================
# ================= CHARGEMENT MARCHÉS ==================
# =======================================================

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
    except Exception as e:
        st.error(f"Erreur lecture marchés : {e}")
        return {"⚠️ Aucun marché disponible": []}


st.subheader("🌍 Sélection des marchés")

markets = load_markets()

selected_markets = st.multiselect(
    "Marchés à scanner",
    options=list(markets.keys()),
    default=["🇫🇷 SBF 120 (France)"]
)

tickers = [t for m in selected_markets for t in markets[m]]
st.write(f"**{len(tickers)} actions sélectionnées**")


# =======================================================
# ============ DATA: CACHE & DOWNLOADING ================
# =======================================================

@st.cache_data(show_spinner=False)
def get_data_weekly(symbol):
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.pkl")
    if os.path.exists(cache_path):
        if time.time() - os.path.getmtime(cache_path) < CACHE_TTL:
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


# =======================================================
# ================= INDICATEURS =========================
# =======================================================

@st.cache_data(show_spinner=False)
def compute_indicators(df):
    df = df.copy()
    close = df["Close"]

    df["EMA200"] = ta.ema(close, length=40)
    df["EMA50"] = ta.ema(close, length=10)
    df["EMA7"] = ta.ema(close, length=4)

    df["RSI7"] = ta.rsi(close, length=7)
    df["RSI32"] = ta.rsi(close, length=32)

    macd = ta.macd(close, fast=6, slow=15, signal=3)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)
    return df


def compute_heikin_ashi(df):
    ha = df.copy()
    ha.index = df.index
    ha["HA_Close"] = (ha["Open"] + ha["High"] + ha["Low"] + ha["Close"]) / 4
    ha["HA_Open"] = 0.0
    ha.iloc[0, ha.columns.get_loc("HA_Open")] = (ha["Open"].iloc[0] + ha["Close"].iloc[0]) / 2
    for i in range(1, len(ha)):
        ha.iloc[i, ha.columns.get_loc("HA_Open")] = (ha["HA_Open"].iloc[i-1] + ha["HA_Close"].iloc[i-1]) / 2
    ha["HA_High"] = ha[["High", "HA_Open", "HA_Close"]].max(axis=1)
    ha["HA_Low"] = ha[["Low", "HA_Open", "HA_Close"]].min(axis=1)
    return ha


# =======================================================
# ================= SIGNAL TRADING ======================
# =======================================================

def check_conditions(df):
    RSI7 = df["RSI7"]
    rsi_ok = (
        RSI7.iloc[-3] < 30 and
        RSI7.iloc[-2] < 30 and
        RSI7.iloc[-1] > 30
    ) or (
        RSI7.iloc[-4] < 30 and
        RSI7.iloc[-3] < 30 and
        RSI7.iloc[-2] > 30 and
        RSI7.iloc[-1] > 30
    )

    return rsi_ok


def analyze_symbol(symbol):
    try:
        df = get_data_weekly(symbol)
        if df is None:
            return None

        df = compute_indicators(df)

        if check_conditions(df):
            info = yf.Ticker(symbol).info
            company_name = info.get("shortName", "Nom inconnu")

            last = df.iloc[-1]
            return {
                "Symbole": symbol,
                "Nom": company_name,
                "Prix": f"{last['Close']:.2f}",
                "EMA200": f"{last['EMA200']:.2f}",
                "EMA50": f"{last['EMA50']:.2f}",
                "EMA7": f"{last['EMA7']:.2f}",
                "Signal": "ACHAT"
            }

        return None

    except Exception:
        return None


# =======================================================
# ================= GRAPHIC DISPLAY =====================
# =======================================================

def plot_chart(symbol):
    try:
        df = get_data_weekly(symbol)
        if df is None or df.empty:
            st.error("Données introuvables.")
            return
        df = compute_indicators(df)

        df_daily = yf.Ticker(symbol).history(period="2mo", interval="1d")
        zoom_available = df_daily is not None and not df_daily.empty
        if zoom_available:
            df_daily["EMA7"] = ta.ema(df_daily["Close"], length=7)
            df_daily["EMA20"] = ta.ema(df_daily["Close"], length=20)

        fig = make_subplots(
            rows=3, cols=2,
            column_widths=[0.67, 0.33],
            subplot_titles=[
                "Weekly Heikin Ashi", "Daily zoom",
                "RSI7 weekly", "",
                "MACD Weekly", ""
            ],
            horizontal_spacing=0.05,
            vertical_spacing=0.03
        )

        df_ha = compute_heikin_ashi(df)

        fig.add_trace(go.Candlestick(
            x=df_ha.index,
            open=df_ha["HA_Open"], high=df_ha["HA_High"],
            low=df_ha["HA_Low"], close=df_ha["HA_Close"],
            increasing_line_color="green",
            decreasing_line_color="red"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], mode="lines", line=dict(width=1.5), name="EMA50"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA7"], mode="lines", line=dict(width=1.5), name="EMA7"), row=1, col=1)

        if zoom_available:
            fig.add_trace(go.Candlestick(
                x=df_daily.index,
                open=df_daily["Open"], high=df_daily["High"],
                low=df_daily["Low"], close=df_daily["Close"],
                increasing_line_color="green",
                decreasing_line_color="red"
            ), row=1, col=2)

            fig.add_trace(go.Scatter(x=df_daily.index, y=df_daily["EMA7"], mode="lines", name="EMA7 daily"), row=1, col=2)
            fig.add_trace(go.Scatter(x=df_daily.index, y=df_daily["EMA20"], mode="lines", name="EMA20 daily"), row=1, col=2)

            fig.update_xaxes(range=[df_daily.index[-50], df_daily.index[-1]], row=1, col=2)

        rsi = df["RSI7"]
        fig.add_trace(go.Scatter(x=df.index, y=rsi, mode="lines", name="RSI7"), row=2, col=1)
        fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)

        if all(c in df.columns for c in ["MACD_6_15_3","MACDs_6_15_3","MACDh_6_15_3"]):
            fig.add_trace(go.Bar(x=df.index, y=df["MACDh_6_15_3"], opacity=0.5, name="MACDh"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["MACD_6_15_3"], mode="lines", name="MACD"), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["MACDs_6_15_3"], mode="lines", name="Signal"), row=3, col=1)

        fig.update_layout(height=750, template="plotly_dark", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")


# =======================================================
# ===================== SCAN ============================
# =======================================================

if st.button("🚀 LANCER LE SCANNER", type="primary"):
    with st.spinner("Scan en cours…"):

        results = []
        progress = st.progress(0)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(analyze_symbol, s): s for s in tickers}
            done = 0

            for future in as_completed(futures):
                res = future.result()
                if res is not None:
                    results.append(res)
                done += 1
                progress.progress(done / len(tickers))

        if results:
            st.session_state.last_results = pd.DataFrame(results)
            st.success(f"{len(results)} opportunités trouvées ✔️")
        else:
            st.warning("Aucun signal trouvé.")


# =======================================================
# ============== AFFICHAGE DES RÉSULTATS ================
# =======================================================

if "last_results" in st.session_state:
    df_res = st.session_state.last_results
    for idx, row in df_res.iterrows():
        if st.button(f"📈 {row['Symbole']} — {row['Nom']}", key=row['Symbole']):
            plot_chart(row["Symbole"])
            st.markdown("---")
