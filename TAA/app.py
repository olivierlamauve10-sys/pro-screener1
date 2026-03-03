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
import random
import numpy as np
import threading

# ======================================
#        CONFIG & CACHE
# ======================================
CACHE_DIR = "cache_data"
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 3600  # 1h cache disque

# ======================================
#        DEBUG BUFFER (thread-safe)
# ======================================
DEBUG_MAX = 5
_debug_lock = threading.Lock()

def _get_debug_buf():
    # keep in session_state so it survives reruns cleanly
    if "debug_exceptions" not in st.session_state:
        st.session_state.debug_exceptions = []
    return st.session_state.debug_exceptions

def record_exception(symbol: str, e: Exception):
    buf = _get_debug_buf()
    with _debug_lock:
        if len(buf) < DEBUG_MAX:
            buf.append((symbol, type(e).__name__, str(e)))

# ======================================
#        CONFIGURATION GÉNÉRALE
# ======================================
st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("📈 Screener TAA")

# ======================================
#        HELPERS : DIAGNOSTICS YF
# ======================================
def classify_yf_exception(e: Exception) -> str:
    """
    Classe les erreurs Yahoo Finance.
    Retour possible: YF_RATE_LIMIT, YF_ERROR
    """
    msg = str(e).lower()

    rate_signals = [
        "too many requests", "429", "rate limit", "ratelimit",
        "blocked", "forbidden", "captcha", "unauthorized",
        "temporarily unavailable", "service unavailable"
    ]
    if any(s in msg for s in rate_signals):
        return "YF_RATE_LIMIT"
    if "yfratelimiterror" in msg:
        return "YF_RATE_LIMIT"
    return "YF_ERROR"


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def get_company_name(symbol: str) -> str:
    """
    Essaie d'obtenir un nom lisible.
    - Actions: shortName/longName
    - FX: fallback "FX: EUR/HUF" si symbol contient '=X'
    """
    try:
        info = yf.Ticker(symbol).info or {}
        name = info.get("shortName") or info.get("longName")
        if name and isinstance(name, str) and name.strip():
            return name.strip()
    except Exception:
        pass

    # fallback FX
    if symbol.endswith("=X"):
        base = symbol.replace("=X", "")
        if len(base) == 6:
            return f"FX: {base[:3]}/{base[3:]}"
        return f"FX: {base}"

    return "Nom inconnu"

# ======================================
#        CHARGEMENT DES MARCHÉS
# ======================================
@st.cache_data
def load_markets():
    try:
        json_path = os.path.join(os.getcwd(), "markets.json")
        with open(json_path, "r", encoding="utf-8") as f:
            markets = json.load(f)

        sp500_path = os.path.join(os.getcwd(), "sp500.json")
        if os.path.exists(sp500_path):
            with open(sp500_path, "r", encoding="utf-8") as f:
                sp500_data = json.load(f)
            if "S&P 500" in sp500_data:
                markets["🇺🇸 S&P 500 (USA)"] = sp500_data["S&P 500"]

        return markets
    except Exception as e:
        st.error(f"Erreur lecture marchés : {e}")
        return {}

st.subheader("🌍 Sélection des marchés")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔁 Rafraîchir les marchés"):
        load_markets.clear()
        st.rerun()

markets = load_markets()
if not markets:
    st.error("❌ Aucun marché chargé. Vérifie markets.json / sp500.json (chemin, JSON valide).")
    st.stop()

market_keys = list(markets.keys())
selected_markets = st.multiselect(
    "Marchés à scanner",
    options=market_keys,
    default=["🇫🇷 SBF 120 (France)","🇺🇸 S&P 500 (USA)","EU EUR (Europe)","DECO"] if "🇫🇷 SBF 120 (France)" in market_keys and "🇺🇸 S&P 500 (USA)" in market_keys else (market_keys[:2] if len(market_keys) >= 2 else market_keys)
)

tickers = [t for m in selected_markets for t in markets.get(m, [])]
st.write(f"**{len(tickers)} actions sélectionnées**")

# ======================================
#        DATA + INDICATEURS
# ======================================
@st.cache_data(show_spinner=False)
def get_data(symbol: str):
    """
    Historique daily ~1 an avec cache disque.
    Retourne None si pas assez de données exploitables.
    """
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.pkl")

    # 1) Lire cache disque si valide
    if os.path.exists(cache_path):
        try:
            mtime = os.path.getmtime(cache_path)
            if time.time() - mtime < CACHE_TTL:
                with open(cache_path, "rb") as f:
                    df = pickle.load(f)
                if df is not None and not df.empty:
                    return df
        except Exception:
            pass

    # 2) Sinon requête Yahoo (petit jitter)
    time.sleep(0.08 + 0.18 * random.random())

    df = yf.Ticker(symbol).history(period="1y", interval="1d")

    if df is None or df.empty:
        return None

    # ✅ Volume: ne filtre que si la colonne existe (FX/indices souvent sans volume)
    if "Volume" in df.columns:
        df = df[df["Volume"] > 0]

    df = df.dropna(subset=["Close"])

    # ✅ garde-fou: EMA200 + slices cup/handle
    if len(df) < 250:
        return None

    # 3) Écrire cache disque
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass

    return df


@st.cache_data(show_spinner=False)
def compute_indicators_cached(df: pd.DataFrame):
    df = df.copy()
    close = df["Close"]

    df["EMA200"] = ta.ema(close, length=200)
    df["EMA50"]  = ta.ema(close, length=50)
    df["EMA7"]   = ta.ema(close, length=7)

    df["RSI7"]   = ta.rsi(close, length=7)
    df["RSI32"]  = ta.rsi(close, length=32)

    macd = ta.macd(close, fast=10, slow=104, signal=10)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)

    return df


def check_conditions(df: pd.DataFrame) -> bool:
    # ✅ garde-fou
    if df is None or df.empty or len(df) < 250:
        return False

    close = df["Close"]  # ✅ défini dès le début

    # ============================
    # 1) Contexte haussier de fond
    # ============================
    ema200 = df["EMA200"]
    bullish_trend = (
        #ema200.iloc[-1] > ema200.iloc[-15]
        #and ema200.iloc[-15] > ema200.iloc[-30]
        #and ema200.iloc[-30] > ema200.iloc[-45]
        ema200.iloc[-1] / ema200.iloc[-45]>1.01
    )

    # ============================
    # 2) Identification large du creux (cup)
    # ============================
    left_search = close.iloc[-90:-55]
    cup_bottom_search = close.iloc[-65:-35]
    right_search = close.iloc[-40:-10]

    if left_search.empty or cup_bottom_search.empty or right_search.empty:
        return False

    left_top = float(left_search.max())
    cup_bottom = float(cup_bottom_search.min())
    right_top = float(right_search.max())
    last_close = float(close.iloc[-1])

    cup_depth = (left_top - cup_bottom) / left_top * 100.0
    cup_shape_ok = (cup_depth >= 10) and (cup_depth <= 45)

    # ============================
    # 3) Anse (handle)
    # ============================
    recent = close.tail(20)
    handle_depth = (recent.max() - recent.min()) / recent.max() * 100.0
    handle_ok = (handle_depth <= 20)

    # ============================
    # 4) RSI permissif
    # ============================
    rsi_ok = df["RSI7"].iloc[-1] > 40

    # ===========
    # 5) Breakout
    # ===========
    breakout = (last_close >= right_top * 0.99) and (last_close <= right_top * 1.15)

    # ============================
    # 6) Cohérence entre hauts gauche/droite (intervalle => AND)
    # ============================
    coherence = (left_top >= right_top * 0.93) and (left_top <= right_top * 1.03)

    # ============================
    # 7) EMA50 s’aplatit (régression linéaire)
    # ============================
    ema50 = df["EMA50"].iloc[-60:-10]
    if len(ema50) < 10:
        ema50_flat_ok = False
    else:
        x = np.arange(len(ema50))
        slope = np.polyfit(x, ema50.values, 1)[0]
        ema50_flat_ok = abs(slope) < 0.125

    return (
        bullish_trend
        and cup_shape_ok
        and handle_ok
        and rsi_ok
        and breakout
        and coherence
        and ema50_flat_ok
    )


def analyze_symbol(symbol: str):
    """
    Retourne (result, status) avec status ∈ {
        'MATCH', 'NO_SIGNAL', 'NO_DATA', 'YF_RATE_LIMIT', 'YF_ERROR'
    }
    """
    try:
        df = get_data(symbol)
        if df is None or df.empty:
            return None, "NO_DATA"

        df = compute_indicators_cached(df)

        if not check_conditions(df):
            return None, "NO_SIGNAL"

        company_name = get_company_name(symbol)

        last = df.iloc[-1]
        result = {
            "Symbole": symbol,
            "Nom": company_name,
            "Prix": f"{last['Close']:.2f}",
            "EMA200": f"{last['EMA200']:.2f}",
            "EMA50": f"{last['EMA50']:.2f}",
            "EMA7": f"{last['EMA7']:.2f}",
            "Signal": "TAA"
        }
        return result, "MATCH"

    except Exception as e:
        record_exception(symbol, e)
        return None, classify_yf_exception(e)


# ======================================
#        GRAPHIQUE
# ======================================
def plot_chart(symbol: str):
    try:
        df = get_data(symbol)
        if df is None or df.empty:
            st.error("Données introuvables.")
            return

        df = compute_indicators_cached(df)

        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.65, 0.20, 0.15],
            subplot_titles=[
                f"{symbol} – Prix & Moyennes Mobiles",
                "RSI 32",
                "MACD"
            ]
        )

        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            name="Prix",
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

        for i in range(1, len(df)):
            color = "blue" if df["EMA200"].iloc[i] >= df["EMA200"].iloc[i - 1] else "red"
            fig.add_trace(go.Scatter(
                x=df.index[i - 1:i + 1],
                y=df["EMA200"].iloc[i - 1:i + 1],
                mode="lines",
                line=dict(color=color, width=2),
                name="EMA200" if i == 1 else None,
                showlegend=(i == 1)
            ), row=1, col=1)

        rsi = df["RSI32"]
        for i in range(1, len(rsi)):
            color = "blue" if rsi.iloc[i] >= rsi.iloc[i - 1] else "red"
            fig.add_trace(go.Scatter(
                x=df.index[i - 1:i + 1],
                y=rsi.iloc[i - 1:i + 1],
                mode="lines",
                line=dict(color=color, width=2),
                name="RSI 32" if i == 1 else None,
                showlegend=(i == 1)
            ), row=2, col=1)

        fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)

        if all(c in df.columns for c in ["MACD_10_104_10", "MACDs_10_104_10", "MACDh_10_104_10"]):
            fig.add_trace(go.Bar(
                x=df.index, y=df["MACDh_10_104_10"],
                name="MACD Hist", opacity=0.5
            ), row=3, col=1)

            fig.add_trace(go.Scatter(
                x=df.index,
                y=df["MACD_10_104_10"],
                mode="lines", name="MACD"
            ), row=3, col=1)

            fig.add_trace(go.Scatter(
                x=df.index,
                y=df["MACDs_10_104_10"],
                mode="lines", name="Signal"
            ), row=3, col=1)

        fig.update_layout(
            height=750,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=True,
            dragmode="drawline",
            newshape_line_color="red",
            modebar_add=['drawline', 'drawopenpath', 'drawrect', 'eraseshape']
        )

        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        for i in range(1, 4):
            fig.update_yaxes(side="right", row=i, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")

# ======================================
#        BOUTON SCANNER
# ======================================
if st.button("🚀 LANCER LE SCANNER", type="primary"):
    # reset debug buffer
    st.session_state.debug_exceptions = []

    results = []
    progress = st.progress(0)

    max_workers = min(4, len(tickers)) if len(tickers) > 0 else 1

    status_counts = {
        "MATCH": 0,
        "NO_SIGNAL": 0,
        "NO_DATA": 0,
        "YF_RATE_LIMIT": 0,
        "YF_ERROR": 0,
    }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_symbol, symbol): symbol for symbol in tickers}

        done = 0
        total = len(tickers) if len(tickers) > 0 else 1

        for future in as_completed(futures):
            try:
                result, status = future.result()
            except Exception as e:
                # si une exception échappe à analyze_symbol, on la capture aussi
                record_exception(futures[future], e)
                result, status = None, classify_yf_exception(e)

            status_counts[status] = status_counts.get(status, 0) + 1

            if result is not None:
                results.append(result)

            done += 1
            progress.progress(done / total)

    nb_match = status_counts["MATCH"]
    nb_no_signal = status_counts["NO_SIGNAL"]
    nb_no_data = status_counts["NO_DATA"]
    nb_rate = status_counts["YF_RATE_LIMIT"]
    nb_err = status_counts["YF_ERROR"]

    st.info(
        f"""
**Diagnostic du scan :**
- {nb_match} tickers correspondent au filtre (MATCH)
- {nb_no_signal} tickers scannés sans signal (NO_SIGNAL)
- {nb_no_data} tickers sans données (NO_DATA)
- {nb_rate} tickers en erreur probable de rate limit / ban Yahoo (YF_RATE_LIMIT)
- {nb_err} tickers en autre erreur Yahoo / réseau (YF_ERROR)
"""
    )

    # afficher les 5 premières exceptions réelles
    dbg = _get_debug_buf()
    if dbg:
        st.subheader("🧪 Debug – 5 premières exceptions réelles")
        for sym, typ, msg in dbg:
            st.code(f"{sym} → {typ}: {msg}")

    if results:
        df_res = pd.DataFrame(results)
        st.success(f"🚀 {len(df_res)} opportunités détectées")
        st.session_state.last_results = df_res
    else:
        st.session_state.last_results = None

# ======================================
#        AFFICHAGE DES RÉSULTATS
# ======================================
if "last_results" in st.session_state and st.session_state.last_results is not None:
    st.subheader("📊 Résultats du scan")

    df_res = st.session_state.last_results.copy()

    st.markdown("""
    <style>
    .result-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 10px 20px;
        margin-bottom: 8px;
    }
    .symbol { font-weight: 700; color: #4da6ff; font-size: 17px; }
    .price { color: #d9d9d9; }
    .metric { color: #aaaaaa; font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

    for _, row in df_res.iterrows():
        with st.container():
            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            cols = st.columns([1.2, 1, 1, 1, 1])

            cols[0].markdown(
                f"<span class='symbol'>{row['Symbole']} — {row['Nom']}</span>",
                unsafe_allow_html=True
            )
            cols[1].markdown(f"<span class='price'>{row['Prix']}</span>", unsafe_allow_html=True)
            cols[2].markdown(f"<span class='metric'>EMA200: {row['EMA200']}</span>", unsafe_allow_html=True)
            cols[3].markdown(f"<span class='metric'>EMA50: {row['EMA50']}</span>", unsafe_allow_html=True)
            cols[4].markdown(f"<span class='metric'>EMA7: {row['EMA7']}</span>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown(f"### 📊 Graphique – {row['Symbole']} — {row['Nom']}")
            plot_chart(row["Symbole"])
            st.markdown("---")
