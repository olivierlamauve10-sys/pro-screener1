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

CACHE_DIR = "cache_data"
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_TTL = 3600  # = 1h cache


# ======================================
#        CONFIGURATION GÉNÉRALE
# ======================================
st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("📈 Screener W")


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
        return {"⚠️ Aucun marché disponible": []}


st.subheader("🌍 Sélection des marchés")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔁 Rafraîchir les marchés"):
        load_markets.clear()
        st.rerun()

markets = load_markets()

selected_markets = st.multiselect(
    "Marchés à scanner",
    options=list(markets.keys()),
    default=["🇫🇷 SBF 120 (France)"]
)

tickers = [t for m in selected_markets for t in markets[m]]
st.write(f"**{len(tickers)} actions sélectionnées**")


# ======================================
#     PARAMÈTRE : % RETRACEMENT
# ======================================
retracement_percent = st.slider(
    "Retracement minimal (%) par rapport au plus haut des 252 séances",
    min_value=5,
    max_value=30,
    value=10,
    step=1,
    help="Exemple : 10% → le cours du jour doit être au moins 10% sous le plus haut atteint sur 252 séances."
)


# ======================================
#        FONCTIONS TECHNIQUES
# ======================================
@st.cache_data(show_spinner=False)
def get_data(symbol):
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.pkl")

    # lire cache si valide
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime < CACHE_TTL:  
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except:
                pass

    # sinon récupérer depuis Yahoo Finance
    df = yf.Ticker(symbol).history(period="2y", interval="1wk")

    if df is not None and not df.empty:
        with open(cache_path, "wb") as f:
            pickle.dump(df, f)

    return df

def audit_symbol(symbol):
    df = yf.Ticker(symbol).history(period="2y", interval="1wk")
    
    if df is None or df.empty:
        return (symbol, "❗ Aucune donnée Yahoo Finance (empty)")

    if len(df) < 10:
        return (symbol, f"❗ Historique insuffisant (seulement {len(df)} semaines)")

    df["RSI7"] = ta.rsi(df["Close"], length=7)
    last_rsi = df["RSI7"].iloc[-1]

    if pd.isna(last_rsi):
        return (symbol, "❗ RSI NaN (pas assez de points exploitables)")

    if last_rsi > 100 or last_rsi < 0:
        return (symbol, f"❗ RSI anormal ({last_rsi}) — données suspectes")

    return (symbol, "✔ OK — données valides")

@st.cache_data(show_spinner=False)
def compute_indicators_cached(df):
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


def check_conditions(df, retracement_percent):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    ema200 = df["EMA200"]
    ema50 = df["EMA50"]

    ema200_up_ok = (
        ema200.iloc[-1] > ema200.iloc[-4]
        and ema200.iloc[-4] > ema200.iloc[-8]
        and ema200.iloc[-8] > ema200.iloc[-12]
    )

    ema50_down_ok = (
        ema50.iloc[-2] < ema50.iloc[-4]
        and ema50.iloc[-4] < ema50.iloc[-6]
      )

    ema7_up_ok = last["EMA7"] > prev["EMA7"]

    RSI7 = df["RSI7"]
    rsi_ok = (
        RSI7.iloc[-3] < 30
        and RSI7.iloc[-2] < 30
        and RSI7.iloc[-1] > 30
    )

    highest_52 = df["High"].tail(52).max()
    current_price = last["Close"]

    retracement_threshold = 1 - (retracement_percent / 100)
    retracement_ok = current_price <= highest_52 * retracement_threshold

    return (
        # ema200_up_ok
        # and ema50_down_ok
        # and ema7_up_ok
        rsi_ok
        # and retracement_ok
    )


def analyze_symbol(symbol, retracement_percent):
    try:
        df = get_data(symbol)
        if df is None:
            return None

        df = compute_indicators_cached(df)

        if check_conditions(df, retracement_percent):

            # nom société
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
                "Signal": "ACHAT (rebond technique)"
            }

        return None

    except Exception:
        return None


# ======================================
#        GRAPHIQUE
# ======================================

def compute_heikin_ashi(df):
    ha = df.copy()
    ha.index = df.index   # 🔥 GARANTIT que l'index datetime reste

    ha["HA_Close"] = (ha["Open"] + ha["High"] + ha["Low"] + ha["Close"]) / 4

    ha["HA_Open"] = 0.0
    ha.iloc[0, ha.columns.get_loc("HA_Open")] = (ha["Open"].iloc[0] + ha["Close"].iloc[0]) / 2

    for i in range(1, len(ha)):
        ha.iloc[i, ha.columns.get_loc("HA_Open")] = (ha["HA_Open"].iloc[i-1] + ha["HA_Close"].iloc[i-1]) / 2

    ha["HA_High"] = ha[["High", "HA_Open", "HA_Close"]].max(axis=1)
    ha["HA_Low"]  = ha[["Low", "HA_Open", "HA_Close"]].min(axis=1)

    return ha



def plot_chart(symbol):
    try:
        df = get_data(symbol)
        if df is None:
            st.error("Données introuvables.")
            return

        df = compute_indicators_cached(df)

        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.65, 0.20, 0.15],
            subplot_titles=[
                f"{symbol} – Prix & Moyennes Mobiles",
                "RSI7",
                "MACD Week"
            ]
        )

        # === Candlesticks
        df = compute_heikin_ashi(df)

        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["HA_Open"], high=df["HA_High"],
            low=df["HA_Low"], close=df["HA_Close"],
            name="Heikin-Ashi",
            increasing_line_color="green",
            decreasing_line_color="red"
        ), row=1, col=1)


        # === EMA50
        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA50"],
            mode="lines", name="EMA50",
            line=dict(color="purple", width=1.5)
        ), row=1, col=1)

        # === EMA7
        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA7"],
            mode="lines", name="EMA7",
            line=dict(color="cyan", width=1.5)
        ), row=1, col=1)

        # === EMA200 colorée
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

        # === RSI
        rsi = df["RSI7"]
        for i in range(1, len(rsi)):
            color = "blue" if rsi.iloc[i] >= rsi.iloc[i - 1] else "red"
            fig.add_trace(go.Scatter(
                x=df.index[i - 1:i + 1],
                y=rsi.iloc[i - 1:i + 1],
                mode="lines",
                line=dict(color=color, width=2),
                name="RSI7" if i == 1 else None,
                showlegend=(i == 1)
            ), row=2, col=1)

        fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)

        # === MACD
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


        # === Mise en forme générale
        fig.update_layout(
            height=750,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=True
        )

        # === Mise en forme générale pour les outils
        fig.update_layout(
            dragmode="drawline",
            newshape_line_color="red"
        )
        
        # supprimer week-ends
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

        # Y-axis à droite
        for i in range(1, 4):
            fig.update_yaxes(side="right", row=i, col=1)

        fig.update_layout(modebar_add=['drawline', 'drawopenpath', 'drawrect', 'eraseshape'])
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")


# ======================================
#        SCANNER TECHNIQUE RAPIDE
# ======================================
if st.button("🧪 AUDIT COMPLET DES TICKERS"):
    st.write("Analyse des causes des rejets…")

    for i, symbol in enumerate(tickers):
        try:
            res = audit_symbol(symbol)
            st.write(res)

            # Pause automatique pour éviter ban
            time.sleep(0.3)

            # Pause + longue toutes les 20 requêtes
            if i % 20 == 0 and i > 0:
                time.sleep(5)

        except Exception as e:
            st.write(symbol, "❗ ERREUR inattendue :", e)

if st.button("🚀 LANCER LE SCANNER", type="primary"):
    with st.spinner("Analyse accélérée (multithread + cache)…"):

        results = []
        progress = st.progress(0)

        max_workers = min(8, len(tickers)) if len(tickers) > 0 else 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(analyze_symbol, symbol, retracement_percent): symbol
                for symbol in tickers
            }

            done = 0
            total = len(tickers) if len(tickers) > 0 else 1

            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)
                done += 1
                progress.progress(done / total)

        if results:
            df_res = pd.DataFrame(results)
            st.success(f"🚀 {len(df_res)} opportunités détectées")
            st.session_state.last_results = df_res
        else:
            st.warning("Aucun signal trouvé.")
            st.session_state.last_results = None


# ======================================
#        AFFICHAGE DES RÉSULTATS
# ======================================
if "last_results" in st.session_state and st.session_state.last_results is not None:
    st.subheader("📊 Résultats du scan")

    df_res = st.session_state.last_results.copy()

    st.markdown("Clique sur **📈 Voir** pour afficher le graphique :")

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

    for idx, row in df_res.iterrows():
        with st.container():
            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            cols = st.columns([1.2, 1, 1, 1, 1, 0.8])

            cols[0].markdown(
                f"<span class='symbol'>{row['Symbole']} — {row['Nom']}</span>",
                unsafe_allow_html=True
            )
            cols[1].markdown(f"<span class='price'>{row['Prix']}</span>", unsafe_allow_html=True)
            cols[2].markdown(f"<span class='metric'>EMA200: {row['EMA200']}</span>", unsafe_allow_html=True)
            cols[3].markdown(f"<span class='metric'>EMA50: {row['EMA50']}</span>", unsafe_allow_html=True)
            cols[4].markdown(f"<span class='metric'>EMA7: {row['EMA7']}</span>", unsafe_allow_html=True)

            if cols[5].button("📈 Voir", key=f"btn_{row['Symbole']}"):
                st.markdown(f"### 📊 Graphique – {row['Symbole'] — {row['Nom']}")
                plot_chart(row["Symbole"])
                st.markdown("---")

            st.markdown("</div>", unsafe_allow_html=True)
