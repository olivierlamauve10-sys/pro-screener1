import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
        # Ajout des Valeur Euro depuis fichier externe
        json_path = os.path.join(os.path.dirname(__file__), "markets.json")        
        with open(json_path, "r", encoding="utf-8") as f:
            markets = json.load(f)
        # Ajout du S&P 500 depuis fichier externe
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
    default=["🇩🇪 DAX 40 (Allemagne)", "🇮🇹 FTSE MIB (Italie)", "🇪🇸 IBEX 35 (Espagne)","🇧🇪 BEL 20 (Belgique)", "🇳🇱 AEX 25 (Pays-Bas)", "🇬🇧 FTSE 100 (Royaume-Uni)", "🇸🇪 OMX 30 (Suède)"],
    key="market_selector"
)

# Liste totale des tickers à scanner
tickers = [t for m in selected_markets for t in markets[m]]
st.write(f"**{len(tickers)} actions sélectionnées pour le scan**")

# ======================================
#        FONCTION D'AFFICHAGE GRAPHIQUE
# ======================================
def plot_chart(symbol):
    """Affiche le graphique complet : Prix, EMA, RSI 32, MACD Week, Volume."""
    try:
        df = yf.Ticker(symbol).history(period="1y")
        if df.empty:
            st.error("Données indisponibles.")
            return

        # === INDICATEURS TECHNIQUES ===
        # === INDICATEURS TECHNIQUES ===
        df['EMA200'] = ta.ema(df['Close'], 200)
        df['EMA50'] = ta.ema(df['Close'], 50)
        df['EMA7'] = ta.ema(df['Close'], 7)
        df['RSI'] = ta.rsi(df['Close'], 32)
        macd = ta.macd(df['Close'], fast=10, slow=104, signal=10)
        df = pd.concat([df, macd], axis=1)

        # === STRUCTURE DU GRAPHIQUE ===
        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=[0.65, 0.15, 0.15, 0.05],
            subplot_titles=[f"{symbol} – Prix & Moyennes Mobiles", "RSI 32", "MACD Week", "Volume"]
        )

        # === 1. PRIX + EMA ===
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'],
            name='Prix',
            increasing_line_color='green',
            decreasing_line_color='red'
        ), row=1, col=1)

        # EMA50 (violette)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['EMA50'],
            mode='lines', name='EMA50',
            line=dict(color='purple', width=1.5)
        ), row=1, col=1)

        # EMA7 (turquoise)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['EMA7'],
            mode='lines', name='EMA7',
            line=dict(color='cyan', width=1.5)
        ), row=1, col=1)

        # EMA200 colorée selon pente (bleu si haussière, rouge si baissière)
        for i in range(1, len(df)):
            color = 'blue' if df['EMA200'].iloc[i] >= df['EMA200'].iloc[i - 1] else 'red'
            fig.add_trace(go.Scatter(
                x=df.index[i-1:i+1],
                y=df['EMA200'].iloc[i-1:i+1],
                mode='lines',
                line=dict(color=color, width=2),
                name='EMA200',
                showlegend=False
            ), row=1, col=1)

        # === 2. MACD ===
        if all(col in df.columns for col in ['MACD_10_104_10', 'MACDs_10_104_10', 'MACDh_10_104_10']):
            fig.add_trace(go.Bar(
                x=df.index, y=df['MACDh_10_104_10'],
                name='Histogramme MACD ZL Week', marker_color='gray', opacity=0.5
            ), row=3, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df['MACD_10_104_10'],
                mode='lines', name='MACD', line=dict(color='blue', width=1.2)
            ), row=3, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df['MACDs_10_104_10'],
                mode='lines', name='Signal', line=dict(color='red', width=1)
            ), row=3, col=1)

        # === 3. RSI (30j) – coloré selon la pente ===
        rsi = df['RSI']

        # Boucle pour tracer les segments colorés
        for i in range(1, len(rsi)):
            # Si le RSI monte → bleu, sinon → rouge
            color = 'blue' if rsi.iloc[i] >= rsi.iloc[i - 1] else 'red'
            fig.add_trace(go.Scatter(
                x=df.index[i-1:i+1],
                y=rsi.iloc[i-1:i+1],
                mode='lines',
                line=dict(color=color, width=2),
                name='RSI' if i == 1 else None,  # une seule légende
                showlegend=(i == 1)
            ), row=2, col=1)

        # Lignes de surachat/survente
        fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)

        # === 4. VOLUME ===
        fig.add_trace(go.Bar(
            x=df.index, y=df['Volume'],
            name='Volume', marker_color='lightblue'
        ), row=4, col=1)

        # === MISE EN FORME ===
        fig.update_layout(
            height=900,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=True,
            margin=dict(l=30, r=30, t=40, b=30)
        )

        # Supprimer les week-ends et mettre l’axe Y à droite
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        for i in range(1, 5):
            fig.update_yaxes(side="right", row=i, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur graphique : {e}")

# ======================================
#        SCANNER TECHNIQUE
# ======================================
#        SCANNER TECHNIQUE
# ======================================
if st.button("🚀 LANCER LE SCANNER", type="primary"):
    with st.spinner("Analyse des marchés en cours..."):
        results = []
        progress = st.progress(0)

        for i, symbol in enumerate(tickers):
            try:
                df = yf.Ticker(symbol).history(period="1y", interval="1d")
                if len(df) < 220:
                    continue

                close = df['Close']

                # === Calcul des indicateurs ===
                # === Calcul des indicateurs ===
                df['EMA200'] = ta.ema(close, length=200)
                df['EMA50'] = ta.ema(close, length=50)
                df['EMA7'] = ta.ema(close, length=7)
                ema200 = df['EMA200']
                ema50 = df['EMA50']

                last = df.iloc[-1]
                prev = df.iloc[-2]

                # === Conditions de détection ===
                # === Conditions de détection ===
                ema200_up_ok = ema200.iloc[-1] > ema200.iloc[-11] and ema200.iloc[-11] > ema200.iloc[-33] and ema200.iloc[-33] > ema200.iloc[-60]    # tendance haussière
                ema50_down_ok = ema50.iloc[-2] < ema50.iloc[-7]      # retracement
                ema7_up_ok = last['EMA7'] > prev['EMA7']          # rebond technique

                # === Validation du signal global ===
                # === Validation du signal global ===
                if ema200_up_ok and ema50_down_ok and ema7_up_ok:
                    results.append({
                        "Symbole": symbol,
                        "Prix": f"{last['Close']:.2f}",
                        "EMA200": f"{last['EMA200']:.2f}",
                        "EMA50": f"{last['EMA50']:.2f}",
                        "EMA7": f"{last['EMA7']:.2f}",
                        "Signal": "ACHAT (rebond technique)"
                    })

            except Exception:
                pass

            progress.progress((i + 1) / len(tickers))

        # === Résultats ===
        if results:
            df_res = pd.DataFrame(results)
            st.success(f"✅ {len(df_res)} opportunités détectées")
            st.session_state.last_results = df_res
        else:
            st.warning("Aucun signal trouvé.")
            st.session_state.last_results = None

# ======================================
#        AFFICHAGE DES RÉSULTATS (version stylée + interactive)
# ======================================
if "last_results" in st.session_state and st.session_state.last_results is not None:
    st.subheader("📊 Résultats du scan")

    df_res = st.session_state.last_results.copy()

    st.markdown("Clique sur le bouton **📈 Voir le graphique** pour afficher la valeur correspondante :")

    # --- Style CSS pour un rendu plus propre ---
    st.markdown("""
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
    """, unsafe_allow_html=True)

    # --- Affichage sous forme de "cartes" avec bouton ---
    for idx, row in df_res.iterrows():
        with st.container():
            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            cols = st.columns([1.2, 1, 1, 1, 1, 0.8])

            cols[0].markdown(f"<span class='symbol'>{row['Symbole']}</span>", unsafe_allow_html=True)
            cols[1].markdown(f"<span class='price'>{row['Prix']}</span>", unsafe_allow_html=True)
            cols[2].markdown(f"<span class='metric'>EMA200: {row['EMA200']}</span>", unsafe_allow_html=True)
            cols[3].markdown(f"<span class='metric'>EMA50: {row['EMA50']}</span>", unsafe_allow_html=True)
            cols[4].markdown(f"<span class='metric'>EMA7: {row['EMA7']}</span>", unsafe_allow_html=True)

            if cols[5].button("📈 Voir", key=f"btn_{row['Symbole']}"):
                st.markdown(f"### 📊 Graphique pour {row['Symbole']}")
                plot_chart(row['Symbole'])
                st.markdown("---")

            st.markdown("</div>", unsafe_allow_html=True)
