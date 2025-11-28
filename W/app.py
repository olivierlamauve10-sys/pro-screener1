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

# ──────────────────────────────────────────
#              CONFIG GÉNÉRALE
# ──────────────────────────────────────────
st.set_page_config(page_title="Screener Weekly RSI", layout="wide")
st.title("📈 Screener RSI — Weekly Reversal")

CACHE_DIR = "cache_data"
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 3600  # 1h


# ──────────────────────────────────────────
#              CHARGEMENT MARCHÉS
# ──────────────────────────────────────────
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
        return {"⚠️ Aucun marché dispo": []}


markets = load_markets()

selected_markets = st.multiselect(
    "Marchés à scanner",
    options=list(markets.keys()),
    default=["🇫🇷 SBF 120 (France)"]
)

tickers = [t for m in selected_markets for t in markets[m]]
st.write(f"📊 {len(tickers)} actions sélectionnées")


# ──────────────────────────────────────────
#         FETCH + CACHE DONNÉES WEEKLY
# ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_data(symbol: str) -> pd.DataFrame | None:
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.pkl")

    # cache disque
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime < CACHE_TTL:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    df = yf.Ticker(symbol).history(period="2y", interval="1wk")
    if df is not None and not df.empty:
        with open(cache_path, "wb") as f:
            pickle.dump(df, f)
        return df

    return None


# ──────────────────────────────────────────
#           INDICATEURS WEEKLY
# ──────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    df["EMA200"] = ta.ema(close, length=40)
    df["EMA50"] = ta.ema(close, length=10)
    df["EMA7"] = ta.ema(close, length=4)
    df["RSI7"] = ta.rsi(close, length=7)

    macd = ta.macd(close, fast=6, slow=15, signal=3)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)

    return df


# ──────────────────────────────────────────
#     CONDITION REBOND RSI WEEKLY
# ──────────────────────────────────────────
def check_rsi_reversal(df: pd.DataFrame) -> bool:
    R = df["RSI7"]
    if len(R) < 5:
        return False

    return (
        R.iloc[-3] < 30 and R.iloc[-2] < 30 and R.iloc[-1] > 30
    ) or (
        R.iloc[-4] < 30 and R.iloc[-3] < 30 and R.iloc[-2] > 30 and R.iloc[-1] > 30
    )


# ──────────────────────────────────────────
#        ANALYSE D’UN SYMBOLE
# ──────────────────────────────────────────
def analyze_symbol(symbol: str):
    try:
        df = get_data(symbol)
        if df is None or df.empty:
            return None

        df = compute_indicators(df)

        if check_rsi_reversal(df):
            info = yf.Ticker(symbol).info
            name = info.get("shortName", "Nom inconnu")
            price = float(df.iloc[-1]["Close"])
            return {
                "Symbole": symbol,
                "Nom": name,
                "Prix": f"{price:.2f}",
            }

        return None
    except Exception:
        return None


# ──────────────────────────────────────────
#             HEIKIN ASHI (FIX)
# ──────────────────────────────────────────
def compute_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    ha = df.copy()

    # close HA
    ha["HA_Close"] = (ha["Open"] + ha["High"] + ha["Low"] + ha["Close"]) / 4

    # open HA (1ère ligne avec iloc)
    ha["HA_Open"] = 0.0
    idx_ha_open = ha.columns.get_loc("HA_Open")
    ha.iloc[0, idx_ha_open] = (ha["Open"].iloc[0] + ha["Close"].iloc[0]) / 2

    # récursif
    for i in range(1, len(ha)):
        ha.iloc[i, idx_ha_open] = (ha["HA_Open"].iloc[i-1] + ha["HA_Close"].iloc[i-1]) / 2

    # high / low HA
    ha["HA_High"] = ha[["High", "HA_Open", "HA_Close"]].max(axis=1)
    ha["HA_Low"] = ha[["Low", "HA_Open", "HA_Close"]].min(axis=1)

    return ha


# ──────────────────────────────────────────
#     GRAPHIQUE WEEKLY + DAILY ZOOM
# ──────────────────────────────────────────
def plot_chart(symbol):
    try:
        # ===========================
        # DATA WEEKLY
        # ===========================
        df = get_data(symbol)
        if df is None or df.empty:
            st.error("Données introuvables.")
            return

        df = compute_indicators_cached(df)

        # ===========================
        # DATA DAILY zoom
        # ===========================
        df_daily = yf.Ticker(symbol).history(period="2mo", interval="1d")
        zoom_daily_available = df_daily is not None and not df_daily.empty

        if zoom_daily_available:
            df_daily["EMA7"] = ta.ema(df_daily["Close"], length=7)
            df_daily["EMA20"] = ta.ema(df_daily["Close"], length=20)

        # ===========================
        # STRUCTURE DES SUBPLOTS
        # ===========================
        fig = make_subplots(
            rows=3, cols=2,
            shared_xaxes=False,
            column_widths=[0.67, 0.33],
            row_heights=[0.60, 0.25, 0.15],
            horizontal_spacing=0.05,
            vertical_spacing=0.03,
            subplot_titles=[
                "Weekly Heikin Ashi", "Daily — zoom",
                "RSI7 weekly", "",
                "MACD Weekly", ""
            ]
        )

        # ===========================
        # WEEKLY — Ha + EMA
        # ===========================
        df_ha = compute_heikin_ashi(df)

        fig.add_trace(go.Candlestick(
            x=df_ha.index,
            open=df_ha["HA_Open"], high=df_ha["HA_High"],
            low=df_ha["HA_Low"], close=df_ha["HA_Close"],
            name="Heikin-Ashi",
            increasing_line_color="green",
            decreasing_line_color="red"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA50"],
            mode="lines", name="EMA50",
            line=dict(color="purple", width=1.5)
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA7"],
            mode="lines", name="EMA7",
            line=dict(color="cyan", width=1.5)
        ), row=1, col=1)

        # ===========================
        # DAILY — uniquement row1,col2
        # ===========================
        if zoom_daily_available:
            fig.add_trace(go.Candlestick(
                x=df_daily.index,
                open=df_daily["Open"], high=df_daily["High"],
                low=df_daily["Low"], close=df_daily["Close"],
                name="Daily",
                increasing_line_color="green",
                decreasing_line_color="red"
            ), row=1, col=2)

            fig.add_trace(go.Scatter(
                x=df_daily.index, y=df_daily["EMA7"],
                mode="lines", name="EMA7 daily",
                line=dict(color="cyan", width=1.3)
            ), row=1, col=2)

            fig.add_trace(go.Scatter(
                x=df_daily.index, y=df_daily["EMA20"],
                mode="lines", name="EMA20 daily",
                line=dict(color="orange", width=1.3)
            ), row=1, col=2)

            # zoom sur 50 derniers jours
            if len(df_daily) > 50:
                fig.update_xaxes(range=[df_daily.index[-50], df_daily.index[-1]], row=1, col=2)

        # ===========================
        # RSI weekly — uniquement col1
        # ===========================
        rsi = df["RSI7"]
        fig.add_trace(go.Scatter(
            x=df.index, y=rsi,
            mode="lines",
            line=dict(color="white", width=2),
            name="RSI7"
        ), row=2, col=1)

        fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)

        # ===========================
        # MACD weekly — uniquement col1
        # ===========================
        if all(c in df.columns for c in ["MACD_6_15_3","MACDs_6_15_3","MACDh_6_15_3"]):
            fig.add_trace(go.Bar(
                x=df.index, y=df["MACDh_6_15_3"],
                name="MACD Hist", opacity=0.5
            ), row=3, col=1)

            fig.add_trace(go.Scatter(
                x=df.index,
                y=df["MACD_6_15_3"],
                mode="lines", name="MACD"
            ), row=3, col=1)

            fig.add_trace(go.Scatter(
                x=df.index,
                y=df["MACDs_6_15_3"],
                mode="lines", name="Signal"
            ), row=3, col=1)


        # ===========================
        # LAYOUT FINAL
        # ===========================
        fig.update_layout(
            height=750,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=False,
            dragmode="drawline",
            newshape_line_color="red",
            modebar_add=['drawline', 'drawopenpath', 'drawrect', 'eraseshape']
        )

        # WEEKENDS OFF
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=1, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=1, col=2)

        # Y axis only for col1 except daily
        fig.update_yaxes(side="right", row=1, col=1)
        fig.update_yaxes(side="right", row=2, col=1)
        fig.update_yaxes(side="right", row=3, col=1)
        fig.update_yaxes(side="right", row=1, col=2)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")


# ──────────────────────────────────────────
#              BOUTON SCAN
# ──────────────────────────────────────────
if st.button("🚀 LANCER LE SCANNER", type="primary"):
    with st.spinner("Analyse en cours…"):
        results = []
        progress = st.progress(0)
        total = len(tickers) if tickers else 1
        workers = min(8, total) if total > 0 else 1

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
            st.warning("Aucun signal détecté.")
            st.session_state.last_results = None


# ──────────────────────────────────────────
#        AFFICHAGE DES RÉSULTATS
# ──────────────────────────────────────────
if "last_results" in st.session_state and st.session_state.last_results is not None:
    st.subheader("📌 Opportunités détectées")

    df_res = st.session_state.last_results

    for idx, row in df_res.iterrows():
        with st.container():
            st.write(f"🔹 **{row['Symbole']} — {row['Nom']}** — {row['Prix']}€")
            if st.button("📈 Voir", key=f"btn_{row['Symbole']}"):
                st.markdown(f"### 📊 {row['Symbole']} — {row['Nom']}")
                plot_chart(row["Symbole"])
                st.markdown("---")


# ──────────────────────────────────────────
#       AUDIT COMPLET DES TICKERS
# ──────────────────────────────────────────
def audit_symbol(symbol: str):
    df = yf.Ticker(symbol).history(period="2y", interval="1wk")
    if df is None or df.empty:
        return (symbol, "❗ Aucune donnée Yahoo Finance (empty)")
    if len(df) < 10:
        return (symbol, f"❗ Historique insuffisant ({len(df)} semaines)")

    df["RSI7"] = ta.rsi(df["Close"], length=7)
    last_rsi = df["RSI7"].iloc[-1]
    if pd.isna(last_rsi):
        return (symbol, "❗ RSI NaN (pas assez de points)")
    if last_rsi > 100 or last_rsi < 0:
        return (symbol, f"❗ RSI anormal ({last_rsi})")
    return (symbol, "✔ OK — données valides")


if st.button("🧪 AUDIT COMPLET DES TICKERS"):
    st.write("Analyse des causes des rejets…")
    for i, sym in enumerate(tickers):
        try:
            res = audit_symbol(sym)
            st.write(res)
            time.sleep(0.3)
            if i % 20 == 0 and i > 0:
                time.sleep(5)
        except Exception as e:
            st.write(sym, "❗ ERREUR inattendue :", e)
