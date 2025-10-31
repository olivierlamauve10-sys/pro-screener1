import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# === CONFIG ===
st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("ProScreener Pro – EMA200 ↑ + EMA50 ↓ (Pullback)")

# === MARCHÉS (CAC40 + NASDAQ 100) ===
markets = {
    "CAC 40": [
        "MC.PA", "OR.PA", "SAN.PA", "TTE.PA", "SU.PA", "BNP.PA", "AIR.PA", "RMS.PA",
        "KER.PA", "DG.PA", "CAP.PA", "SAF.PA", "EN.PA", "ACA.PA", "BN.PA", "HO.PA"
    ],
    "NASDAQ 100": [
        "AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META", "AMZN", "AVGO", "ASML", "PEP"
    ]
}

selected_markets = st.multiselect("Marchés", options=list(markets.keys()), default=["CAC 40", "NASDAQ 100"])
tickers = [t for m in selected_markets for t in markets[m]]

# === PARAMÈTRES (4 colonnes) ===
col1, col2, col3, col4 = st.columns(4)

with col1:
    rsi_filter = st.selectbox("RSI", ["Aucun", "< 30", "> 70", "30-70"])

with col2:
    macd_filter = st.checkbox("MACD Haussier", value=False)

with col3:
    ema200_up_filter = st.checkbox("EMA200 ↑ (trend)", value=True)

with col4:
    ema50_down_filter = st.checkbox("EMA50 ↓ (pullback)", value=True)

st.write(f"**{len(tickers)} actions à scanner**")

# === SCANNER ===
if st.button("LANCER LE SCANNER", type="primary"):
    results = []
    progress = st.progress(0)

    for i, symbol in enumerate(tickers):
        try:
            df = yf.Ticker(symbol).history(period="1y", interval="1d")
            if len(df) < 220:
                continue

            close = df['Close']

            # === INDICATEURS ===
            df['RSI'] = ta.rsi(close, length=14)
            macd = ta.macd(close)
            df = pd.concat([df, macd], axis=1)
            df['EMA200'] = ta.ema(close, length=200)
            df['EMA50'] = ta.ema(close, length=50)

            last = df.iloc[-1]
            prev = df.iloc[-2]

            # === CONDITIONS INDIVIDUELLES ===
            # RSI
            rsi_ok = True
            if rsi_filter == "< 30":
                rsi_ok = last['RSI'] < 30
            elif rsi_filter == "> 70":
                rsi_ok = last['RSI'] > 70
            elif rsi_filter == "30-70":
                rsi_ok = 30 <= last['RSI'] <= 70

            # MACD
            macd_ok = True
            if macd_filter:
                macd_ok = (prev['MACD_12_26_9'] < prev['MACDs_12_26_9']) and \
                          (last['MACD_12_26_9'] > last['MACDs_12_26_9'])

            # EMA200 ↑
            ema200_up_ok = last['EMA200'] > prev['EMA200']

            # EMA50 ↓
            ema50_down_ok = last['EMA50'] < prev['EMA50']

            # === SIGNAL FINAL (filtres indépendants) ===
            if (rsi_ok and
                (not macd_filter or macd_ok) and
                (not ema200_up_filter or ema200_up_ok) and
                (not ema50_down_filter or ema50_down_ok)):

                results.append({
                    "Symbole": symbol,
                    "Prix": f"{last['Close']:.2f}",
                    "RSI": f"{last['RSI']:.1f}",
                    "EMA200": f"{last['EMA200']:.2f}",
                    "EMA50": f"{last['EMA50']:.2f}",
                    "ΔEMA200": f"{last['EMA200'] - prev['EMA200']:+.2f}",
                    "ΔEMA50": f"{last['EMA50'] - prev['EMA50']:+.2f}",
                    "Signal": "ACHAT (pullback)"
                })

        except Exception as e:
            pass

        progress.progress((i + 1) / len(tickers))

    # === RÉSULTATS ===
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"**{len(df_res)} OPPORTUNITÉS EN TENDANCE**")
        df_res = df_res.sort_values("ΔEMA200", ascending=False)
        st.dataframe(df_res, use_container_width=True)

        # GRAPHIQUE
        if results:
            choice = st.selectbox("Graphique :", [""] + df_res["Symbole"].tolist())
            if choice and choice != "":
                plot_chart(choice)

        # EXPORT
        st.download_button("CSV", df_res.to_csv(index=False), f"pullback_{len(df_res)}.csv")

    else:
        st.warning("Aucun signal. Essaie :")
        st.write("- RSI : Aucun")
        st.write("- MACD : décoché")
        st.write("- EMA200 ↑ : coché")
        st.write("- EMA50 ↓ : décoché")

# === GRAPHIQUE ===
@st.cache_data
def plot_chart(symbol):
    df = yf.Ticker(symbol).history(period="1y")
    df['EMA200'] = ta.ema(df['Close'], 200)
    df['EMA50'] = ta.ema(df['Close'], 50)
    df['RSI'] = ta.rsi(df['Close'], 14)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True,
                        subplot_titles=(f"{symbol}", "MACD", "RSI", "Volume"),
                        row_heights=[0.5, 0.15, 0.15, 0.2])

    # Prix + EMA
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close']), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA200'], name="EMA200", line=dict(color="orange", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name="EMA50", line=dict(color="purple", width=2)), row=1, col=1)

    # MACD
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal"), row=2, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI"), row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3)

    # Volume
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume"), row=4, col=1)

    fig.update_layout(height=900, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
