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
    "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"],
    "Actions US": ["AAPL", "TSLA", "NVDA", "META"]
}

selected_markets = st.multiselect("Choisir les marchés", options=list(markets.keys()), default=["Forex", "Actions US"])
instruments = [item for m in selected_markets for item in markets[m]]

# --- Paramètres ---
col1, col2 = st.columns(2)

with col1:
    rsi_filter = st.selectbox("Filtre RSI", ["Aucun", "RSI < 30", "RSI > 70", "30 < RSI < 70"])
    macd_filter = st.checkbox("Croisement MACD haussier", value=False)

with col2:
    volume_filter = st.checkbox("Filtrer par volume élevé", value=False)
    timeframe = st.selectbox("Unité de temps", ["1d"], index=0)

# --- FORCER UN TEST ---
if st.button("Lancer le Screener", type="primary"):
    results = []
    debug = []

    for symbol in instruments:
        try:
            # Téléchargement
            df = yf.download(symbol, period="3mo", interval=timeframe, progress=False)
            if len(df) < 20:
                debug.append(f"{symbol}: Pas assez de données")
                continue

            # Indicateurs
            df['RSI'] = ta.rsi(df['Close'], length=14)
            macd = ta.macd(df['Close'])
            df = pd.concat([df, macd], axis=1)

            last = df.iloc[-1]
            prev = df.iloc[-2]

            # --- CONDITIONS ---
            rsi_ok = True
            if rsi_filter == "RSI < 30": rsi_ok = last['RSI'] < 30
            elif rsi_filter == "RSI > 70": rsi_ok = last['RSI'] > 70
            elif rsi_filter == "30 < RSI < 70": rsi_ok = 30 < last['RSI'] < 70

            macd_ok = True
            if macd_filter:
                macd_ok = (prev['MACD_12_26_9'] < prev['MACDs_12_26_9']) and (last['MACD_12_26_9'] > last['MACDs_12_26_9'])

            volume_ok = True
            if volume_filter:
                # SEULEMENT pour actions (pas Forex)
                if "=X" not in symbol and "-USD" not in symbol:
                    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
                    if pd.isna(avg_vol) or avg_vol == 0:
                        volume_ok = False
                    else:
                        volume_ok = last['Volume'] > avg_vol
                else:
                    volume_ok = True  # Forex ignoré

            if rsi_ok and macd_ok and volume_ok:
                results.append({
                    "Symbole": symbol.replace("=X", "").replace("-USD", ""),
                    "Prix": f"{last['Close']:.5f}",
                    "RSI": f"{last['RSI']:.1f}",
                    "MACD": f"{last['MACD_12_26_9']:.4f}",
                    "Signal": "OK"
                })
            else:
                debug.append(f"{symbol}: RSI={last['RSI']:.1f}, MACD_ok={macd_ok}, Vol_ok={volume_ok}")

        except Exception as e:
            debug.append(f"{symbol}: ERREUR {e}")

    # --- AFFICHAGE ---
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"{len(df_res)} RÉSULTATS TROUVÉS !")
        st.dataframe(df_res, use_container_width=True)

        choice = st.selectbox("Graphique :", [""] + df_res["Symbole"].tolist())
        if choice:
            sym = next(s for s in instruments if s.replace("=X", "").replace("-USD", "") == choice)
            plot_chart(sym, timeframe)
    else:
        st.warning("Aucun résultat.")
        st.write("**Debug (5 premiers) :**")
        for d in debug[:5]:
            st.write(f"- {d}")

# --- Graphique ---
@st.cache_data
def plot_chart(symbol, timeframe):
    df = yf.download(symbol, period="3mo", interval=timeframe, progress=False)
    if df.empty:
        st.error("Pas de données.")
        return

    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['RSI'] = ta.rsi(df['Close'], 14)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        subplot_titles=(symbol, "MACD", "RSI"),
                        row_heights=[0.6, 0.2, 0.2])

    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close']), row=1, col=1)

    if 'MACD_12_26_9' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal"), row=2, col=1)

    if 'RSI' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI"), row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3)

    fig.update_layout(height=700, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
