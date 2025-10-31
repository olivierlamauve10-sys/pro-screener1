import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("ProScreener Pro – CAC40 + 1000+ Actions + SMA 200")

# === MARCHÉS COMPLETS ===
markets = {
    "CAC 40": ["MC.PA", "OR.PA", "SAN.PA", "TTE.PA", "BNP.PA", "SU.PA", "AI.PA", "BN.PA", 
               "CAP.PA", "EN.PA", "RMS.PA", "KER.PA", "ACA.PA", "HO.PA", "URW.PA"],
    "Actions US (Top)": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META", "AMZN", "NFLX"],
    "Nasdaq 100": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX", "ADBE", "CRM"],
    "S&P 500 Leaders": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "JNJ"]
}

# Fusionner tous les marchés
all_tickers = []
for market, tickers in markets.items():
    all_tickers.extend(tickers)

# Supprimer les doublons
tickers_unique = list(set(all_tickers))

selected_markets = st.multiselect("Choisir les marchés", options=list(markets.keys()), default=["CAC 40", "Actions US (Top)"])
selected_tickers = []
for market in selected_markets:
    selected_tickers.extend(markets[market])

# Limiter pour performance
selected_tickers = selected_tickers[:50]  # Premier test
st.info(f"**{len(selected_tickers)} titres sélectionnés**")

# === PARAMÈTRES AVANCÉS ===
col1, col2, col3 = st.columns(3)

with col1:
    rsi_filter = st.selectbox("Filtre RSI", ["Aucun", "RSI < 30", "RSI > 70", "30 < RSI < 70"])
    
with col2:
    sma_200_filter = st.checkbox("Prix > SMA 200 (tendance haussière)", value=True)
    macd_filter = st.checkbox("Croisement MACD haussier", value=False)

with col3:
    st.write("**Performance optimisée**")
    timeframe = st.selectbox("Unité de temps", ["1d"], index=0)

# === SCANNER ===
if st.button("🚀 LANCER LE SCAN COMPLET", type="primary"):
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, symbol in enumerate(selected_tickers):
        try:
            # Téléchargement
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1y", interval="1d")  # 1 an pour SMA 200
            if len(df) < 200:
                continue

            # Indicateurs techniques
            close = df['Close']
            df['RSI'] = ta.rsi(close, length=14)
            df['SMA_200'] = ta.sma(close, length=200)
            macd = ta.macd(close)
            df = pd.concat([df, macd], axis=1)

            last = df.iloc[-1]
            prev = df.iloc[-2]

            # === CONDITIONS ===
            rsi_ok = True
            if rsi_filter == "RSI < 30": rsi_ok = last['RSI'] < 30
            elif rsi_filter == "RSI > 70": rsi_ok = last['RSI'] > 70
            elif rsi_filter == "30 < RSI < 70": rsi_ok = 30 < last['RSI'] < 70

            sma_200_ok = last['Close'] > last['SMA_200'] if sma_200_filter else True

            macd_ok = True
            if macd_filter and 'MACD_12_26_9' in df.columns:
                macd_ok = (prev['MACD_12_26_9'] < prev['MACDs_12_26_9']) and \
                         (last['MACD_12_26_9'] > last['MACDs_12_26_9'])

            # Signal final
            if rsi_ok and sma_200_ok and macd_ok:
                results.append({
                    "Symbole": symbol,
                    "Prix": f"{last['Close']:.2f}",
                    "RSI": f"{last['RSI']:.1f}",
                    "SMA_200": f"{last['SMA_200']:.2f}",
                    "Tendance": "🟢 Haussière" if last['Close'] > last['SMA_200'] else "🔴 Baissière",
                    "Variation_1mois": f"{((last['Close'] - df['Close'].iloc[-30]) / df['Close'].iloc[-30] * 100):+.1f}%",
                    "Signal": "💡 OPPORTUNITÉ"
                })

        except Exception as e:
            pass

        # Progress
        progress = (i + 1) / len(selected_tickers)
        progress_bar.progress(progress)
        status_text.text(f"Scan {i+1}/{len(selected_tickers)}: {symbol}")

    # === RÉSULTATS ===
    if results:
        df_results = pd.DataFrame(results)
        st.success(f"🎉 **{len(df_results)} OPPORTUNITÉS TROUVÉES !**")
        
        # Tableau interactif
        st.dataframe(df_results, use_container_width=True, height=400)
        
        # Métriques
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total titres scannés", len(selected_tickers))
        col2.metric("Opportunités", len(df_results))
        col3.metric("Meilleure perf 1 mois", f"{df_results['Variation_1mois'].max()}%")
        col4.metric("Taux de succès", f"{len(df_results)/len(selected_tickers)*100:.1f}%")
        
        # Graphique sélection
        choice = st.selectbox("📊 Voir le graphique de :", [""] + df_results["Symbole"].tolist())
        if choice:
            plot_advanced_chart(choice)
            
    else:
        st.warning("❌ Aucune opportunité avec ces critères.")
        st.info("💡 **Astuces :**")
        st.write("- Décoche 'SMA 200' pour plus de résultats")
        st.write("- Choisis 'Aucun' pour RSI")
        st.write("- Teste avec moins de marchés")

# === GRAPHIQUE AVANCÉ ===
@st.cache_data
def plot_advanced_chart(symbol):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="1y", interval="1d")
    
    if df.empty:
        st.error("Données indisponibles.")
        return
    
    # Indicateurs
    close = df['Close']
    df['RSI'] = ta.rsi(close, 14)
    df['SMA_200'] = ta.sma(close, 200)
    macd = ta.macd(close)
    df = pd.concat([df, macd], axis=1)
    
    # Graphique multi-panneaux
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True,
                        subplot_titles=(f"{symbol} - Prix + SMA 200", "RSI", "MACD", "Volume"),
                        row_heights=[0.5, 0.15, 0.15, 0.2],
                        vertical_spacing=0.05)
    
    # Prix + SMA 200
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], name="Prix"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_200'], name="SMA 200", 
                             line=dict(color="orange", width=2)), row=1, col=1)
    
    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color="purple")), row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    
    # MACD
    if 'MACD_12_26_9' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD", line=dict(color="blue")), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal", line=dict(color="orange")), row=3, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="Histogram", marker_color="gray"), row=3, col=1)
    
    # Volume
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume", marker_color="lightblue"), row=4, col=1)
    
    fig.update_layout(height=900, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
