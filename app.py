import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# === CONFIGURATION ===
st.set_page_config(page_title="ProScreener Python", layout="wide")
st.title("ProScreener Python – MACD + RSI + Volume")

# --- Marchés ---
markets = {
    "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"],
    "Actions US": ["AAPL", "TSLA", "NVDA", "META", "GOOGL", "MSFT", "AMZN"],
    "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD"]
}

selected_markets = st.multiselect("Choisir les marchés", options=list(markets.keys()), default=["Forex", "Actions US"])
instruments = [item for m in selected_markets for item in markets[m]]

# --- Paramètres ---
col1, col2, col3 = st.columns(3)

with col1:
    rsi_mode = st.selectbox("Condition RSI", [
        "Survente (RSI < X)",
        "Surachat (RSI > X)",
        "Neutre (40 < RSI < 60)",
        "Aucun filtre RSI"
    ])
    if "X" in rsi_mode:
        rsi_threshold = st.slider("Seuil RSI", 0, 100, 30 if "Survente" in rsi_mode else 70)

with col2:
    macd_cross = st.checkbox("Croisement MACD haussier", value=False)

with col3:
    volume_factor = st.slider("Volume > x moyenne (20j)", 0.5, 5.0, 1.0, 0.1)
    timeframe = st.selectbox("Unité de temps", ["1d", "4h", "1h"], index=0)

# --- Lancer le scan ---
if st.button("Lancer le Screener", type="primary"):
    results = []
    progress = st.progress(0)
    
    for i, symbol in enumerate(instruments):
        try:
            df = yf.download(symbol, period="3mo", interval=timeframe, progress=False)
            if len(df) < 50: 
                continue
            
            # Indicateurs
            df['RSI'] = ta.rsi(df['Close'], length=14)
            macd = ta.macd(df['Close'])
            df = pd.concat([df, macd], axis=1)
            df['Vol_Avg'] = df['Volume'].rolling(20).mean()
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # === CONDITIONS ===
            # RSI
            rsi_ok = True
            if rsi_mode == "Survente (RSI < X)":
                rsi_ok = last['RSI'] < rsi_threshold
            elif rsi_mode == "Surachat (RSI > X)":
                rsi_ok = last['RSI'] > rsi_threshold
            elif rsi_mode == "Neutre (40 < RSI < 60)":
                rsi_ok = 40 < last['RSI'] < 60
            
            # MACD
            macd_up = macd_cross and (prev['MACD_12_26_9'] < prev['MACDs_12_26_9']) and (last['MACD_12_26_9'] > last['MACDs_12_26_9'])
            macd_ok = macd_up if macd_cross else True
            
            # Volume
            volume_ok = last['Volume'] > volume_factor * last['Vol_Avg'] if not pd.isna(last['Vol_Avg']) else False
            
            # Signal final
            if rsi_ok and macd_ok and volume_ok:
                results.append({
                    "Symbole": symbol.replace("=X", "").replace("-USD", ""),
                    "Prix": f"{last['Close']:.5f}",
                    "RSI": f"{last['RSI']:.1f}",
                    "MACD": f"{last['MACD_12_26_9']:.4f}",
                    "Vol x Moy": f"{last['Volume']/last['Vol_Avg']:.2f}" if not pd.isna(last['Vol_Avg']) else "N/A",
                    "Signal": "Achat potentiel"
                })
        except Exception as e:
            pass
        progress.progress((i + 1) / len(instruments))
    
    # --- Résultats ---
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"**{len(df_res)} opportunités trouvées !**")
        st.dataframe(df_res, use_container_width=True)
        
        # --- Graphique ---
        choice = st.selectbox("Voir le graphique de :", [""] + df_res["Symbole"].tolist())
        if choice:
            symbol = choice + "=X" if choice in [s.replace("=X","") for s in markets["Forex"]] else choice + "-USD" if choice in [s.replace("-USD","") for s in markets["Crypto"]] else choice
            plot_chart(symbol, timeframe)
    else:
        st.warning("Aucun signal avec ces critères. Essaye d'assouplir les filtres.")

# --- Fonction graphique ---
def plot_chart(symbol, timeframe):
    df = yf.download(symbol, period="3mo", interval=timeframe, progress=False)
    if df.empty:
        st.error("Données indisponibles pour ce symbole.")
        return
    
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['RSI'] = ta.rsi(df['Close'], 14)
    
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        subplot_titles=(f"{symbol} - {timeframe}", "MACD", "RSI"),
                        vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])
    
    # Candlesticks + Volume
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], name="Prix"), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume", marker_color="rgba(100,100,255,0.3)"), row=1, col=1)
    
    # MACD
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD", line=dict(color="blue")), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal", line=dict(color="orange")), row=2, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="Histogram", marker_color="gray"), row=2, col=1)
    
    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color="purple")), row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
    
    fig.update_layout(height=800, xaxis_rangeslider_visible=False, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
