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
import random  # pour petite pause aléatoire

CACHE_DIR = "cache_data"
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_TTL = 3600  # = 1h cache


# ======================================
# PAGE D ACCEUIL
# ======================================
st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("📈 W esthétic ->")
st.title("50%: RETOURNEMENT avec retour ema200 en W+1 à W+7")
st.title("10%: petit retracement")
st.title("40%: continuation de tendance")
st.title("-> puis suivre en liste W de ZoneBourse")


# ======================================
# CHARGEMENT DES MARCHÉS
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

markets = load_markets()

selected_markets = st.multiselect(
    "Marchés à scanner",
    options=list(markets.keys()),
    default=["🇫🇷 SBF 120 (France)","🇺🇸 S&P 500 (USA)","EU EUR (Europe)","DECO"]
)

tickers = [t for m in selected_markets for t in markets[m]]
st.write(f"**{len(tickers)} actions sélectionnées**")

# ======================================
# FONCTIONS TECHNIQUES
# ======================================
@st.cache_data(show_spinner=False)
def get_data(symbol):
    """
    Récupère l'historique weekly sur 2 ans avec cache disque.
    On ne gère PAS les erreurs ici : elles sont attrapées dans analyze_symbol
    pour pouvoir distinguer ban / autres erreurs.
    """
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.pkl")

    # lire cache si valide
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime < CACHE_TTL:
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    # sinon récupérer depuis Yahoo Finance (avec petite pause aléatoire)
    # pour lisser les requêtes et réduire le risque de ban
    time.sleep(0.1 + 0.2 * random.random())

    df = yf.Ticker(symbol).history(period="2y", interval="1wk")

    if df is not None and not df.empty:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(df, f)
        except Exception:
            # si le cache disque rate, ce n'est pas grave pour le scan
            pass

    return df


def audit_symbol(symbol):
    """
    Audit basique d'un ticker individuel pour comprendre les rejets.
    (Bouton 'AUDIT COMPLET DES TICKERS')
    """
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

    df["ema200"] = ta.sma(close, length=40)
    df["EMA50"] = ta.ema(close, length=10)
    df["EMA7"] = ta.ema(close, length=4)

    df["RSI7"] = ta.rsi(close, length=7)
    df["RSI32"] = ta.rsi(close, length=32)

    macd = ta.macd(close, fast=6, slow=15, signal=3)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)

    return df


def check_conditions(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # =========================
    # RSI weekly (condition principale)
    # =========================
    RSI7 = df["RSI7"]

    rsi_ok = (
        RSI7.iloc[-5] < 30
        and RSI7.iloc[-4] < 30
        and RSI7.iloc[-3] > 30
        and RSI7.iloc[-2] > RSI7.iloc[-3]
        and RSI7.iloc[-1] > RSI7.iloc[-2]
    ) or (
        RSI7.iloc[-4] < 30
        and RSI7.iloc[-3] < 30
        and RSI7.iloc[-2] > 30
        and RSI7.iloc[-1] > RSI7.iloc[-2]
    ) or (
        RSI7.iloc[-3] < 30
        and RSI7.iloc[-2] < 30
        and RSI7.iloc[-1] > 30
    )
    
    if not rsi_ok:
        return False   # RSI est obligatoire

    # =========================
    # RSI2 Remontée trop brutale
    # =========================
    
    rsi2_ok = RSI7.iloc[-1] < 60
    
    # ===============================
    # Dans le sens de la tendance LT
    # Inutile car stratégie W parie sur un RETOURNEMENT de tendance 
    # ===============================
    
    # ema200 = df["ema200"]
    # tendanceLT_ok = ema200.iloc[-20] < ema200.iloc[-1] or ema200.iloc[-2] < ema200.iloc[-1]

    # =======================================
    # ema200 assez éloignée pour rentabilité
    # =======================================
    
    close = df["Close"]
    current_price = last["Close"]
    df["sma200"] = ta.sma(close, length=40)
    sma200 = df["sma200"]
    seuil_ok = current_price < sma200.iloc[-1]
    
    # =========================
    # MACD weekly (condition secondaire)
    # =========================
    
    # macdpr = df["MACD_6_15_3"]
    # signal = df["MACDs_6_15_3"]
    # macd_ok = signal.iloc[-1] > macdpr.iloc[-1]
    

    # =========================
    # CONDITIONS DE RESTITUTION
    # =========================
    return rsi_ok and rsi2_ok and seuil_ok
    # and macd_ok
    # and tendanceLT_ok
    # return rsi_ok and rsi2_ok and (tendanceLT_ok or macd_ok)


def classify_yf_exception(e: Exception) -> str:
    """Essaie de distinguer 'ban / rate limit' des autres erreurs."""
    msg = str(e).lower()
    if "too many requests" in msg or "429" in msg or "rate limit" in msg:
        return "YF_RATE_LIMIT"
    return "YF_ERROR"


def analyze_symbol(symbol):
    """
    Retourne (result, status) avec status ∈ {
        'MATCH', 'NO_SIGNAL', 'NO_DATA', 'YF_RATE_LIMIT', 'YF_ERROR'
    }
    """
    try:
        try:
            df = get_data(symbol)
        except Exception as e:
            status = classify_yf_exception(e)
            return None, status

        if df is None or df.empty:
            return None, "NO_DATA"

        df = compute_indicators_cached(df)

        if not check_conditions(df):
            return None, "NO_SIGNAL"

        # nom société (uniquement si match, pour limiter les requêtes)
        try:
            info = yf.Ticker(symbol).info
            company_name = info.get("shortName", "Nom inconnu")
        except Exception:
            company_name = "Nom inconnu"

        last = df.iloc[-1]
        result = {
            "Symbole": symbol,
            "Nom": company_name,
            "Prix": f"{last['Close']:.2f}",
            "ema200": f"{last['ema200']:.2f}",
            "EMA50": f"{last['EMA50']:.2f}",
            "EMA7": f"{last['EMA7']:.2f}",
            "Signal": "ACHAT (rebond technique)"
        }

        return result, "MATCH"

    except Exception as e:
        status = classify_yf_exception(e)
        return None, status


# ======================================
# GRAPHIQUE
# ======================================
def compute_heikin_ashi(df):
    ha = df.copy()
    ha.index = df.index  # 🔥 GARANTIT que l'index datetime reste

    ha["HA_Close"] = (ha["Open"] + ha["High"] + ha["Low"] + ha["Close"]) / 4

    ha["HA_Open"] = 0.0
    ha.iloc[0, ha.columns.get_loc("HA_Open")] = (ha["Open"].iloc[0] + ha["Close"].iloc[0]) / 2

    for i in range(1, len(ha)):
        ha.iloc[i, ha.columns.get_loc("HA_Open")] = (
            ha["HA_Open"].iloc[i - 1] + ha["HA_Close"].iloc[i - 1]
        ) / 2

    ha["HA_High"] = ha[["High", "HA_Open", "HA_Close"]].max(axis=1)
    ha["HA_Low"] = ha[["Low", "HA_Open", "HA_Close"]].min(axis=1)

    return ha


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
        # DATA DAILY DUREE
        # ===========================
        df_daily = yf.Ticker(symbol).history(period="4mo", interval="1d")

        if df_daily is None or df_daily.empty:
            st.warning("⚠️ Pas de données daily pour le zoom")
            zoom_daily_available = False
        else:
            zoom_daily_available = True
            df_daily["EMA7"] = ta.ema(df_daily["Close"], length=7)
            df_daily["EMA200"] = ta.ema(df_daily["Close"], length=200)

        # =================================
        # ❶ SUBPLOTS = 3 lignes × 2 colonnes
        # =================================
        fig = make_subplots(
            rows=3, cols=2,
            shared_xaxes=False,
            # column_widths=[0.67, 0.33],
            column_widths=[0.50, 0.50],
            row_heights=[0.50, 0.25, 0.25],
            horizontal_spacing=0.05,
            vertical_spacing=0.03,
            subplot_titles=[
                "Weekly Heikin Ashi",
                "Daily — zoom 30 derniers jours",
                "RSI7 weekly",
                "",
                "MACD Weekly",
                ""
            ]
        )

        # ===========================
        # WEEKLY — Heikin Ashi
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

        # ===========================
        # WEEKLY — EMA
        # ===========================

        for i in range(1, len(df)):
            color = "blue" if df["ema200"].iloc[i] >= df["ema200"].iloc[i - 1] else "red"
            fig.add_trace(go.Scatter(
                x=df.index[i - 1:i + 1],
                y=df["ema200"].iloc[i - 1:i + 1],
                mode="lines",
                line=dict(color=color, width=2),
                name="ema200" if i == 1 else None,
                showlegend=(i == 1)
            ), row=1, col=1)

        # ==========================================================
        # DAILY — bougies classiques + EMA7 + EMA20 (colonne droite)
        # ==========================================================
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


            if len(df_daily) > 100:
                fig.update_xaxes(range=[df_daily.index[-100], df_daily.index[-1]], row=1, col=2)

        # ===========================
        # RSI weekly
        # ===========================
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

        # ===========================
        # MACD weekly
        # ===========================
        if all(c in df.columns for c in ["MACD_6_15_3", "MACDs_6_15_3", "MACDh_6_15_3"]):
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
        # Layout général
        # ===========================
        fig.update_layout(
            height=750,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=False
        )

        fig.update_xaxes(rangeslider_visible=False)

        # Effacer week-end en weekly
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=1, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=1, col=2)

        # Y-axis à droite
        for r in range(1, 4):
            fig.update_yaxes(side="right", row=r, col=1)
            fig.update_yaxes(side="right", row=r, col=2)

        # OUTILS DE DESSIN
        fig.update_layout(
            dragmode="drawline",
            newshape_line_color="red",
            modebar_add=['drawline', 'drawopenpath', 'drawrect', 'eraseshape']
        )

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")


# ======================================
# BOUTON SCANNER
# ======================================
if st.button("🚀 LANCER LE SCANNER", type="primary"):
    with st.spinner("Analyse accélérée (multithread + cache)…"):

        results = []
        progress = st.progress(0)

        # ⚠️ Limiter le nombre de threads pour réduire les bursts de requêtes
        max_workers = min(4, len(tickers)) if len(tickers) > 0 else 1

        # stats de diagnostics
        status_counts = {
            "MATCH": 0,
            "NO_SIGNAL": 0,
            "NO_DATA": 0,
            "YF_RATE_LIMIT": 0,
            "YF_ERROR": 0,
            "UNKNOWN": 0,
        }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(analyze_symbol, symbol): symbol
                for symbol in tickers
            }

            done = 0
            total = len(tickers) if len(tickers) > 0 else 1

            for future in as_completed(futures):
                try:
                    result, status = future.result()
                except Exception as e:
                    # cas très rare si l'exception échappe à analyze_symbol
                    result, status = None, classify_yf_exception(e)

                status_counts[status] = status_counts.get(status, 0) + 1

                if result is not None:
                    results.append(result)

                done += 1
                progress.progress(done / total)

        # ====== Résumé diagnostique ======
        nb_match = status_counts["MATCH"]
        nb_no_signal = status_counts["NO_SIGNAL"]
        nb_no_data = status_counts["NO_DATA"]
        nb_rate = status_counts["YF_RATE_LIMIT"]
        nb_err = status_counts["YF_ERROR"]

        st.info(
            f"""
**Diagnostic du scan :**
- {nb_match} tickers correspondent au filtre (MATCH)
- {nb_no_signal} tickers scannés sans signal (NO_MATCH)
- {nb_no_data} tickers sans données (NO_DATA)
- {nb_rate} tickers en erreur probable de rate limit / ban Yahoo (YF_RATE_LIMIT)
- {nb_err} tickers en autre erreur Yahoo / réseau (YF_ERROR)
"""
        )

        if results:
            df_res = pd.DataFrame(results)
            st.success(f"🚀 {len(df_res)} opportunités détectées")
            st.session_state.last_results = df_res
        else:
            # Aucun résultat : essayer d'expliquer pourquoi
            if nb_match == 0 and nb_no_signal > 0 and nb_rate == 0 and nb_err == 0:
                st.warning(
                    "Aucun signal trouvé, mais **les données Yahoo semblent OK**.\n"
                    "→ Interprétation : probablement **aucune valeur ne remplit les conditions**."
                )
            elif nb_match == 0 and nb_rate > 0 and nb_no_signal == 0:
                st.error(
                    "⚠️ Aucun résultat et plusieurs erreurs de type 'rate limit'.\n"
                    "→ Interprétation : probable **ban / limitation temporaire** de Yahoo Finance "
                    "sur certaines requêtes. Réessaie plus tard ou réduis la fréquence."
                )
            else:
                st.warning(
                    "Aucun résultat, avec un mélange de tickers sans signal / sans données / en erreur.\n"
                    "→ Vois le récapitulatif ci-dessus pour affiner le diagnostic."
                )

            st.session_state.last_results = None


# ======================================
# AFFICHAGE DES RÉSULTATS
# ======================================
if "last_results" in st.session_state and st.session_state.last_results is not None:
    st.subheader("📊 Résultats du scan")

    df_res = st.session_state.last_results.copy()

    st.markdown("Affichage direct des graphiques pour chaque valeur détectée :")

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
            cols = st.columns([1.2, 1, 1, 1, 1])

            cols[0].markdown(
                f"<span class='symbol'>{row['Symbole']} — {row['Nom']}</span>",
                unsafe_allow_html=True
            )
            cols[1].markdown(f"<span class='price'>{row['Prix']}</span>", unsafe_allow_html=True)
            cols[2].markdown(f"<span class='metric'>ema200: {row['ema200']}</span>", unsafe_allow_html=True)
            cols[3].markdown(f"<span class='metric'>EMA50: {row['EMA50']}</span>", unsafe_allow_html=True)
            cols[4].markdown(f"<span class='metric'>EMA7: {row['EMA7']}</span>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            # --- Affichage DIRECT du graphique ---
            st.markdown(f"### 📊 Graphique – {row['Symbole']} — {row['Nom']}")
            plot_chart(row["Symbole"])
            st.markdown("---")


# ======================================
# SCANNER TECHNIQUE RAPIDE (AUDIT)
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


# ======================================
# BOUTON RAFRAICHIR LES MARCHES
# ======================================
col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔁 Rafraîchir les marchés"):
        load_markets.clear()
        st.rerun()
