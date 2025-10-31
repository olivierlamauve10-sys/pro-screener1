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
    rsi_threshold = 30 if "Survente" in rsi_mode else 70 if "X" in rsi_mode else 50

with col2:
    macd_cross = st.checkbox("Croisement MACD haussier", value=False)

with col3:
    volume_factor = st.slider("Volume > x moyenne (20j)", 0.5, 3.0, 1.0, 0.1)
    timeframe = st.selectbox("Unité de temps", ["1d", "5d"], index=0)  # 5d pour plus de data

# --- Debug : Afficher les instruments ---
st.write(f"**Instruments à scanner :** {len(instruments)} ({', '.join([s.replace('=X','').replace('-USD','') for s in instruments[:5]])}...)")

# --- Lancer le scan ---
if st.button("Lancer le Screener", type="primary"):
    results = []
    progress = st.progress(0)
    debug_info = []  # Pour debug si besoin
    
    for i, symbol in enumerate(instruments):
        try:
            df = yf.download(symbol, period="3mo", interval=timeframe, progress=False)
            if len(df) < 30:  # Assoupli à 30
                debug_info.append(f"{symbol}: Moins de 30 jours de data")
                continue
            
            # Indicateurs
            df['RSI'] = ta.rsi(df['Close'], length=14)
            macd = ta.macd(df['Close'])
            df = pd.concat([df, macd], axis=1)
            df['Vol_Avg'] = df['Volume'].rolling(20).mean()
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # === CONDITIONS (FIXÉES) ===
            # RSI
            rsi_ok = True
            if rsi_mode == "Survente (RSI < X)":
                rsi_ok = last['RSI'] < rsi_threshold if not pd.isna(last['RSI']) else False
            elif rsi_mode == "Surachat (RSI > X)":
                rsi_ok = last['RSI'] > rsi_threshold if not pd.isna(last['RSI']) else False
            elif rsi_mode == "Neutre (40 < RSI < 60)":
                rsi_ok = 40 < last['RSI'] < 60 if not pd.isna(last['RSI']) else False
            
            # MACD
            macd_ok = True
            if macd_cross:
                macd_prev_line = prev['MACD_12_26_9'] if 'MACD_12_26_9' in prev else 0
                macd_signal_prev = prev['MACDs_12_26_9'] if 'MACDs_12_26_9' in prev else 0
                macd_line = last['MACD_12_26_9'] if 'MACD_12_26_9' in last else 0
                macd_signal = last['MACDs_12_26_9'] if 'MACDs_12_26_9' in last else 0
                macd_ok = (macd_prev_line < macd_signal_prev) and (macd_line > macd_signal)
            
            # Volume (fix pour NaN)
            vol_ok = True
            if not pd.isna(last['Vol_Avg']) and last['Vol_Avg'] > 0:
                vol_ok = last['Volume'] > volume_factor * last['Vol_Avg']
            else:
                vol_ok = last['Volume'] > 1000  # Fallback pour Forex (volume faible)
            
            # Signal final
            if rsi_ok and macd_ok and vol_ok:
                results.append({
                    "Symbole": symbol.replace("=X", "").replace("-USD", ""),
                    "Prix": f"{last['Close']:.5f}",
                    "RSI": f"{last['RSI']:.1f}" if not pd.isna(last['RSI']) else "N/A",
                    "MACD": f"{last['MACD_12_26_9']:.4f}" if 'MACD_12_26_9' in last else "N/A",
                    "Vol x Moy": f"{last['Volume']/last['Vol_Avg']:.2f}" if not pd.isna(last['Vol_Avg']) else "N/A",
                    "Signal": "Achat potentiel"
                })
            else:
                debug_info.append(f"{symbol}: RSI_ok={rsi_ok}, MACD_ok={macd_ok}, Vol_ok={vol_ok}")
        except Exception as e:
            debug_info.append(f"{symbol}: Erreur {str(e)}")
        
        progress.progress((i + 1) / len(instruments))
    
    # --- Résultats ---
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"**{len(df_res)} opportunités trouvées !**")
        st.dataframe(df_res, use_container_width=True)
        
        # --- Graphique ---
        choice = st.selectbox("Voir le graphique de :", [""] + df_res["Symbole"].tolist())
        if choice:
            full_symbol = next((s for s in instruments if s.replace("=X", "").replace("-USD", "") == choice), choice)
            plot_chart(full_symbol, timeframe)
    else:
        st.warning("Aucun signal trouvé. Debug :")
        st.write("Premiers 5 instruments testés :")
        for info in debug_info[:5]:
            st.write(f"- {info}")
    
        st.info("**Astuce :** Choisis 'Aucun filtre RSI' + Volume 0.5 pour tester.")

# --- Fonction graphique (FIXÉE) ---
@st.cache_data
def plot_chart(symbol, timeframe):
    try:
        df = yf.download(symbol, period="3mo", interval=timeframe, progress=False)
        if df.empty:
            st.error("Données indisponibles.")
            return
        
        macd = ta.macd(df['Close'])
        df = pd.concat([df, macd], axis=1)
        df['RSI'] = ta.rsi(df['Close'], 14)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            subplot_titles=(f"{symbol} - {timeframe}", "MACD", "RSI"),
                            vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])
        
        # Candlesticks
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                     low=df['Low'], close=df['Close'], name="Prix"), row=1, col=1)
        
        # Volume (optionnel)
        if 'Volume' in df.columns and not df['Volume'].isna().all():
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume", 
                                 marker_color="rgba(100,100,255,0.3)", showlegend=False), row=1, col=1)
        
        # MACD
        if 'MACD_12_26_9' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD", line=dict(color="blue")), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal", line=dict(color="orange")), row=2, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="Histogram", marker_color="gray", showlegend=False), row=2, col=1)
        
        # RSI
        if 'RSI' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color="purple")), row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        
        fig.update_layout(height=800, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.error("Erreur lors du chargement du graphique.")
