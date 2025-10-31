import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="ProScreener", layout="wide")
st.title("ProScreener Python – TEST FINAL")

# === INSTRUMENTS STABLES (seulement actions US – données fiables) ===
tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META", "AMZN"]

# === PARAMÈTRES SIMPLES ===
rsi_filter = st.selectbox("Filtre RSI", ["Aucun", "RSI < 30", "RSI > 70"])
macd_filter = st.checkbox("Croisement MACD haussier", False)

if st.button("LANCER LE SCANNER", type="primary"):
    results = []
    debug = []

    for symbol in tickers:
        try:
            # Téléchargement forcé avec yfinance (mode safe)
            df = yf.Ticker(symbol).history(period="3mo", interval="1d")
            if len(df) < 30:
                debug.append(f"{symbol}: Pas assez de données")
                continue

            # Indicateurs
            close = df['Close']
            df['RSI'] = ta.rsi(close, length=14)
            macd = ta.macd(close)
            df = pd.concat([df, macd], axis=1)

            last = df.iloc[-1]
            prev = df.iloc[-2]

            # RSI
            rsi_ok = True
            if rsi_filter == "RSI < 30": rsi_ok = last['RSI'] < 30
            elif rsi_filter == "RSI > 70": rsi_ok = last['RSI'] > 70

            # MACD
            macd_ok = True
            if macd_filter:
                macd_ok = (prev['MACD_12_26_9'] < prev['MACDs_12_26_9']) and (last['MACD_12_26_9'] > last['MACDs_12_26_9'])

            if rsi_ok and macd_ok:
                results.append({
                    "Symbole": symbol,
                    "Prix": f"{last['Close']:.2f}",
                    "RSI": f"{last['RSI']:.1f}",
                    "MACD": f"{last['MACD_12_26_9']:.3f}",
                    "Signal": "OK"
                })
            else:
                debug.append(f"{symbol}: RSI={last['RSI']:.1f}, MACD_ok={macd_ok}")

        except Exception as e:
            debug.append(f"{symbol}: ERREUR {e}")

    # === AFFICHAGE ===
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"**{len(df_res)} RÉSULTATS !**")
        st.dataframe(df_res, use_container_width=True)

        choice = st.selectbox("Graphique :", [""] + df_res["Symbole"].tolist())
        if choice:
            plot_chart(choice)
    else:
        st.warning("Aucun résultat.")
        st.write("**Debug :**")
        for d in debug[:3]:
            st.write(f"- {d}")

# === GRAPHIQUE ===
@st.cache_data
def plot_chart(symbol):
    df = yf.Ticker(symbol).history(period="3mo", interval="1d")
    close = df['Close']
    df['RSI'] = ta.rsi(close, 14)
    macd = ta.macd(close)
    df = pd.concat([df, macd], axis=1)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        subplot_titles=(symbol, "MACD", "RSI"),
                        row_heights=[0.6, 0.2, 0.2])

    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close']), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI"), row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3)

    if 'MACD_12_26_9' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal"), row=2, col=1)

    fig.update_layout(height=700, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
