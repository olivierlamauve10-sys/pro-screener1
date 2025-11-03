import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# === FONCTION GRAPHIQUE ===
def plot_chart(symbol):
    try:
        df = yf.Ticker(symbol).history(period="2y")
        if df.empty:
            st.error("Données indisponibles.")
            return

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
        if 'MACD_12_26_9' in df.columns:
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

    except Exception as e:
        st.error(f"Erreur graphique : {e}")

# === CONFIG ===
st.set_page_config(page_title="ProScreener Pro", layout="wide")
st.title("ProScreener Pro – EMA200 ↑ + EMA50 ↓ (Pullback)")

# === MARCHÉS ===
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

# === PARAMÈTRES ===
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

# === SESSION STATE ===
if 'last_results' not in st.session_state:
    st.session_state.last_results = None
if 'selected_symbol' not in st.session_state:
    st.session_state.selected_symbol = ""

# === LANCER SCAN ===
if st.button("LANCER LE SCANNER", type="primary"):
    with st.spinner("Analyse en cours..."):
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

                # === CONDITIONS ===
                rsi_ok = True
                if rsi_filter == "< 30":
                    rsi_ok = last['RSI'] < 30
                elif rsi_filter == "> 70":
                    rsi_ok = last['RSI'] > 70
                elif rsi_filter == "30-70":
                    rsi_ok = 30 <= last['RSI'] <= 70

                macd_ok = True
                if macd_filter:
                    macd_ok = (prev['MACD_12_26_9'] < prev['MACDs_12_26_9']) and \
                              (last['MACD_12_26_9'] > last['MACDs_12_26_9'])

                ema200_up_ok = last['EMA200'] > prev['EMA200']
                ema50_down_ok = last['EMA50'] < prev['EMA50']

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

        if results:
            df_res = pd.DataFrame(results)
            df_res = df_res.sort_values("ΔEMA200", ascending=False)
            st.session_state.last_results = df_res
            st.session_state.selected_symbol = ""

            st.success(f"**{len(df_res)} opportunités détectées**")
        else:
            st.warning("Aucun signal trouvé.")
            st.session_state.last_results = None
            st.session_state.selected_symbol = ""

# === AFFICHAGE DES RÉSULTATS ===
if st.session_state.last_results is not None:
    st.dataframe(st.session_state.last_results, use_container_width=True)

    st.subheader("Graphique")
    choice = st.selectbox(
        "Sélectionne un symbole :",
        [""] + st.session_state.last_results["Symbole"].tolist(),
        key="selected_symbol"
    )

    if choice:
        plot_chart(choice)

    st.download_button(
        "Exporter CSV",
        st.session_state.last_results.to_csv(index=False),
        f"pullback_{len(st.session_state.last_results)}.csv"
    )
