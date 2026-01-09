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
CACHE_TTL = 3600  # 1h

# ======================================
#        DEBUG BUFFER (thread-safe)
# ======================================
debug_exceptions = []
debug_lock = threading.Lock()
DEBUG_MAX = 5

def record_exception(symbol, e):
    with debug_lock:
        if len(debug_exceptions) < DEBUG_MAX:
            debug_exceptions.append(
                (symbol, type(e).__name__, str(e))
            )

# ======================================
#        CONFIGURATION GÉNÉRALE
# ======================================
st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("📈 Screener TAA")

# ======================================
#        HELPERS : DIAGNOSTICS YF
# ======================================
def classify_yf_exception(e: Exception) -> str:
    msg = str(e).lower()
    rate_signals = [
        "too many requests", "429", "rate limit", "ratelimit",
        "blocked", "forbidden", "captcha",
        "temporarily unavailable", "service unavailable"
    ]
    if any(s in msg for s in rate_signals):
        return "YF_RATE_LIMIT"
    return "YF_ERROR"

@st.cache_data(show_spinner=False, ttl=6*3600)
def get_company_name(symbol: str) -> str:
    try:
        info = yf.Ticker(symbol).info or {}
        name = info.get("shortName") or info.get("longName")
        if name:
            return name
    except Exception:
        pass

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
        with open("markets.json", "r", encoding="utf-8") as f:
            markets = json.load(f)
        if os.path.exists("sp500.json"):
            with open("sp500.json", "r", encoding="utf-8") as f:
                sp = json.load(f)
            if "S&P 500" in sp:
                markets["🇺🇸 S&P 500 (USA)"] = sp["S&P 500"]
        return markets
    except Exception as e:
        st.error(f"Erreur marchés : {e}")
        return {}

markets = load_markets()

if not markets:
    st.error("❌ Aucun marché chargé. Vérifie markets.json / sp500.json")
    st.stop()   # ⛔ STOP PROPRE : évite que Streamlit continue

market_keys = list(markets.keys())

selected_markets = st.multiselect(
    "Marchés à scanner",
    options=market_keys,
    default=market_keys[:2] if len(market_keys) >= 2 else market_keys
)

tickers = [t for m in selected_markets for t in markets.get(m, [])]
st.write(f"**{len(tickers)} tickers sélectionnés**")

# ======================================
#        DATA
# ======================================
@st.cache_data(show_spinner=False)
def get_data(symbol: str):
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.pkl")

    if os.path.exists(cache_path):
        try:
            if time.time() - os.path.getmtime(cache_path) < CACHE_TTL:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
        except Exception:
            pass

    time.sleep(0.05 + 0.15 * random.random())
    df = yf.Ticker(symbol).history(period="1y", interval="1d")

    if df is None or df.empty:
        return None

    if "Volume" in df.columns:
        df = df[df["Volume"] > 0]

    df = df.dropna(subset=["Close"])
    if len(df) < 250:
        return None

    try:
        with open(cache_path, "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass

    return df

@st.cache_data(show_spinner=False)
def compute_indicators_cached(df):
    df = df.copy()
    c = df["Close"]
    df["EMA200"]
