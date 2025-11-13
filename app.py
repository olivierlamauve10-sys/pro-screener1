import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os

# ======================================
#        CONFIGURATION GÉNÉRALE
# ======================================
st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("📈 ProScreener Pro – EMA200 ↑ + EMA50 ↓ + EMA7 ↑ (Rebond technique)")

# ======================================
#        CHARGEMENT DES MARCHÉS
# ======================================
@st.cache_data
def load_markets():
    """Charge les tickers depuis des fichiers locaux JSON."""
    try:
        json_path = os.path.join(os.path.dirname(__file__), "markets.json")
        with open(json_path, "r", encoding="utf-8") as f:
            markets = json.load(f)

        # Ajout du S&P 500
        sp500_path = os.path.join(os.path.dirname(__file__), "sp500.json")
        if os.path.exists(sp500_path):
            with open(sp500_path, "r", encoding="utf-8") as f:
                sp500_data = json.load(f)
            if "S&P 500" in sp500_data:
                markets["🇺🇸 S&P 500 (USA)"] = sp500_data["S&P 500"]

        return markets

    except Exception as e:
        st.error(f"Erreur de lecture des fichiers de marchés : {e}")
        return {"⚠️ Aucun marché disponible": []}


st.subheader("🌍 Sélection des marchés")

# --- Bouton de rafraîchissement ---
col_refresh, col_empty = st.columns([1, 5])
with col_refresh:
    if st.button("🔁 Rafraîchir les marchés", help="Recharge markets.json et sp500.json"):
        load_markets.clear()
        st.rerun()

# Chargement effectif
markets = load_markets()

# Sélection de marchés
selected_markets = st.multiselect(
    "Marchés à scanner",
    options=list(markets.keys()),
    default=[
        "🇩🇪 DAX 40 (Allemagne)",
        "🇮🇹 FTSE MIB (Italie)",
        "🇪🇸 IBEX 35 (Espagne)",
        "🇧🇪 BEL 20 (Belgique)",
        "🇳🇱 AEX 25 (Pays-Bas)",
        "🇬🇧 FTSE 100 (Royaume-Uni)",
        "🇸🇪 OMX 30 (Suède)"
    ],
    key="market_selector"
)

# Liste totale des tickers à scanner
tickers = [t for m in selected_markets for t in markets[m]]
st.write(f"**{len(tickers)} actions sélectionnées pour le scan**")


# ======================================
#        FONCTIONS TECHNIQUES
# ======================================

@st.cache_data(show_spinner=False)
def get_data(symbol: str) -> pd.DataFrame | None:
    """Télécharge l'historique 1 an en daily, filtre les jours sans volume."""
    df = yf.Ticker(symbol).history(period="1y", interval="1d")

    if df is None or df.empty or len(df) < 220:
        return None

    # Suppression des week-ends / jours sans volume
    df = df[df["Volume"] > 0]

    return df


@st.cache_data(show_spinner=False)
def compute_indicators_cached(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule et ajoute les indicateurs techniques à un DataFrame:
    - EMA200, EMA50, EMA7
    - RSI7 (pour le screener)
    - RSI32 (pour l'affichage graphique)
    - MACD (10, 104, 10)
    """
    df = df.copy()
    close = df["Close"]

    df["EMA200"] = ta.ema(close, length=200)
    df["EMA50"] = ta.ema(close, length=50)
    df["EMA7"] = ta.ema(close, length=7)

    # RSI court pour le screener
    df["RSI7"] = ta.rsi(close, length=7)
    # RSI plus long pour le graphique (comme tu l’avais)
    df["RSI32"] = ta.rsi(close, length=32)

    macd = ta.macd(close, fast=10, slow=104, signal=10)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)

    return df


def check_conditions(df: pd.DataFrame) -> bool:
    """
    Retourne True si toutes les conditions techniques sont remplies :
    - EMA200 haussière
    - EMA50 en retracement baissier
    - EMA7 en rebond
    - RSI7 < 95
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

    ema200 = df["EMA200"]
    ema50 = df["EMA50"]

    # 1. EMA200 haussière
    ema200_up_ok = (
        ema200.iloc[-1] > ema200.iloc[-11]
        and ema200.iloc[-11] > ema200.iloc[-33]
        and ema200.iloc[-33] > ema200.iloc[-45]
    )

    # 2. EMA50 baissière (retracement)
    ema50_down_ok = (
        ema50.iloc[-2] < ema50.iloc[-4]
        and ema50.iloc[-4] < ema50.iloc[-6]
        and ema50.iloc[-6] < ema50.iloc[-8]
    )

    # 3. EMA7 rebond
    ema7_up_ok = last["EMA7"] > prev["EMA7"]

    # 4. RSI7 < 95
    rsi_ok = last["RSI7"] < 95

    return ema200_up_ok and ema50_down_ok and ema7_up_ok and rsi_ok


def analyze_symbol(symbol: str) -> dict | None:
    """
    Analyse un ticker :
    - téléchargement + indicateurs (avec cache)
    - vérification des conditions
    - retourne un dict de résultat ou None
    """
    try:
        df = get_data(symbol)
        if df is None:
            return None

        df = compute_indicators_cached(df)

        if check_conditions(df):
            last = df.iloc[-1]
            return {
                "Symbole": symbol,
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
#        FONCTION D'AFFICHAGE GRAPHIQUE
# ======================================
def plot_chart(symbol: str):
    """Affiche le graphique complet : Prix, EMA, RSI 32, MACD, Volume."""
    try:
        df = get_data(symbol)
        if df is None or df.empty:
            st.error("Données indisponibles pour ce symbole.")
            return

        df = compute_indicators_cached(df)

        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=[0.65, 0.15, 0.15, 0.05],
            subplot_titles=[
                f"{symbol} – Prix & Moyennes Mobiles",
                "RSI 32",
                "MACD Week",
                "Volume"
            ]
        )

        # ======== 1. PRIX + EMA ========
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="Prix",
                increasing_line_color="green",
                decreasing_line_color="red",
            ),
            row=1,
            col=1,
        )

        # EMA50
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["EMA50"],
                mode="lines",
                name="EMA50",
                line=dict(color="purple", width=1.5),
            ),
            row=1,
            col=1,
        )

        # EMA7
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["EMA7"],
                mode="lines",
                name="EMA7",
                line=dict(color="cyan", width=1.5),
            ),
            row=1,
            col=1,
        )

        # EMA200 colorée selon pente
        for i in range(1, len(df)):
            color = "blue" if df["EMA200"].iloc[i] >= df["EMA200"].iloc[i - 1] else "red"
            fig.add_trace(
                go.Scatter(
                    x=df.index[i - 1 : i + 1],
                    y=df["EMA200"].iloc[i - 1 : i + 1],
                    mode="lines",
                    line=dict(color=color, width=2),
                    name="EMA200" if i == 1 else None,
                    showlegend=(i == 1),
                ),
                row=1,
                col=1,
            )

        # ======== 2. RSI 32 ========
        rsi = df["RSI32"]

        for i in range(1, len(rsi)):
            color = "blue" if rsi.iloc[i] >= rsi.iloc[i - 1] else "red"
            fig.add_trace(
                go.Scatter(
                    x=df.index[i - 1 : i + 1],
                    y=rsi.iloc[i - 1 : i + 1],
                    mode="lines",
                    line=dict(color=color, width=2),
                    name="RSI 32" if i == 1 else None,
                    showlegend=(i == 1),
                ),
                row=2,
                col=1,
            )

        fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)

        # ======== 3. MACD ========
        if all(
            col in df.columns
            for col in ["MACD_10_104_10", "MACDs_10_104_10", "MACDh_10_104_10"]
        ):
            fig.add_trace(
                go.Bar(
                    x=df.index,
                    y=df["MACDh_10_104_10"],
                    name="Histogramme MACD",
                    opacity=0.5,
                ),
                row=3,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["MACD_10_104_10"],
                    mode="lines",
                    name="MACD",
                ),
                row=3,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["MACDs_10_104_10"],
                    mode="lines",
                    name="Signal",
                ),
                row=3,
                col=1,
            )

        # ======== 4. VOLUME ========
        fig.add_trace(
            go.Bar(x=df.index, y=df["Volume"], name="Volume"),
            row=4,
            col=1,
        )

        # ======== MISE EN FORME ========
        fig.update_layout(
            height=900,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=True,
            margin=dict(l=30, r=30, t=40, b=30),
        )

        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

        for i in range(1, 5):
            fig.update_yaxes(side="right", row=i, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")


# ======================================
#        SCANNER TECHNIQUE (MULTITHREAD)
# ======================================
if st.button("🚀 LANCER LE SCANNER", type="primary"):

    with st.spinner("Analyse accélérée des marchés (multithread + cache)…"):

        results = []
        progress = st.progress(0)

        if len(tickers) > 0:
            max_workers = min(8, len(tickers))
        else:
            max_workers = 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyze_symbol, symbol): symbol for symbol in tickers}

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

    st.markdown(
        "Clique sur le bouton **📈 Voir** pour afficher le graphique correspondant :"
    )

    # --- Style CSS pour un rendu plus propre ---
    st.markdown(
        """
        <style>
        .result-card {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 10px 20px;
            margin-bottom: 8px;
            box-shadow: 0 0 6px rgba(0,0,0,0.3);
        }
        .result-card:hover {
            background-color: #262626;
            transition: background-color 0.2s ease-in-out;
        }
        .symbol {
            font-weight: 700;
            color: #4da6ff;
            font-size: 17px;
        }
        .price {
            font-weight: 500;
            color: #d9d9d9;
        }
        .metric {
            color: #aaaaaa;
            font-size: 14px;
        }
        div[data-testid="stButton"] button {
            background-color: #4da6ff;
            color: white;
            border-radius: 6px;
            border: none;
            padding: 0.3em 0.8em;
            font-weight: 600;
            transition: background-color 0.2s;
        }
        div[data-testid="stButton"] button:hover {
            background-color: #1E90FF;
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # --- Affichage sous forme de "cartes" avec bouton ---
    for idx, row in df_res.iterrows():
        with st.container():
            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            cols = st.columns([1.2, 1, 1, 1, 1, 0.8])

            cols[0].markdown(
                f"<span class='symbol'>{row['Symbole']}</span>",
                unsafe_allow_html=True,
            )
            cols[1].markdown(
                f"<span class='price'>{row['Prix']}</span>",
                unsafe_allow_html=True,
            )
            cols[2].markdown(
                f"<span class='metric'>EMA200: {row['EMA200']}</span>",
                unsafe_allow_html=True,
            )
            cols[3].markdown(
                f"<span class='metric'>EMA50: {row['EMA50']}</span>",
                unsafe_allow_html=True,
            )
            cols[4].markdown(
                f"<span class='metric'>EMA7: {row['EMA7']}</span>",
                unsafe_allow_html=True,
            )

            if cols[5].button("📈 Voir", key=f"btn_{row['Symbole']}"):
                st.markdown(f"### 📊 Graphique pour {row['Symbole']}")
                plot_chart(row["Symbole"])
                st.markdown("---")

            st.markdown("</div>", unsafe_allow_html=True)
