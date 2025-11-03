import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# === FONCTION GRAPHIQUE ===
def plot_chart(symbol):
    try:
        # === Données ===
        df = yf.Ticker(symbol).history(period="1y")
        if df.empty:
            st.error("Données indisponibles.")
            return

        # === Indicateurs ===
        df['EMA200'] = ta.ema(df['Close'], 200)
        df['EMA50'] = ta.ema(df['Close'], 50)
        df['RSI'] = ta.rsi(df['Close'], 14)
        macd = ta.macd(df['Close'])
        df = pd.concat([df, macd], axis=1)

        # === Options d'affichage ===
        st.subheader("🧩 Options d’affichage du graphique")
        show_macd = st.checkbox("Afficher le MACD", value=True)
        show_rsi = st.checkbox("Afficher le RSI", value=True)
        show_volume = st.checkbox("Afficher le Volume", value=True)

        # === Détermination dynamique du nombre de lignes ===
        rows = 1
        if show_macd:
            rows += 1
        if show_rsi:
            rows += 1
        if show_volume:
            rows += 1

        heights = [0.5]
        if show_macd:
            heights.append(0.2)
        if show_rsi:
            heights.append(0.15)
        if show_volume:
            heights.append(0.15)

        # === Création du graphique ===
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=heights,
            subplot_titles=[f"{symbol} – Prix & Moyennes Mobiles"]
        )

        current_row = 1

        # === 1. PRIX + EMA ===
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'],
            name='Prix',
            increasing_line_color='green',
            decreasing_line_color='red'
        ), row=current_row, col=1)

        # EMA50 (violet)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['EMA50'],
            mode='lines', name='EMA50',
            line=dict(color='purple', width=1.5)
        ), row=current_row, col=1)

        # === EMA200 colorée selon la pente ===
        segments = []
        for i in range(1, len(df)):
            color = 'blue' if df['EMA200'].iloc[i] >= df['EMA200'].iloc[i - 1] else 'red'
            segments.append(go.Scatter(
                x=df.index[i-1:i+1],
                y=df['EMA200'].iloc[i-1:i+1],
                mode='lines',
                line=dict(color=color, width=1.8),
                name='EMA200',
                showlegend=False
            ))
        for seg in segments:
            fig.add_trace(seg, row=current_row, col=1)

        # === 2. MACD ===
        if show_macd:
            current_row += 1
            if all(col in df.columns for col in ['MACD_12_26_9', 'MACDs_12_26_9', 'MACDh_12_26_9']):
                fig.add_trace(go.Bar(
                    x=df.index, y=df['MACDh_12_26_9'],
                    name='Histogramme MACD', marker_color='gray', opacity=0.5
                ), row=current_row, col=1)
                fig.add_trace(go.Scatter(
                    x=df.index, y=df['MACD_12_26_9'],
                    mode='lines', name='MACD', line=dict(color='blue', width=1.2)
                ), row=current_row, col=1)
                fig.add_trace(go.Scatter(
                    x=df.index, y=df['MACDs_12_26_9'],
                    mode='lines', name='Signal', line=dict(color='red', width=1)
                ), row=current_row, col=1)

        # === 3. RSI ===
        if show_rsi:
            current_row += 1
            fig.add_trace(go.Scatter(
                x=df.index, y=df['RSI'],
                mode='lines', name='RSI',
                line=dict(color='cyan', width=1.2)
            ), row=current_row, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)

        # === 4. Volume ===
        if show_volume:
            current_row += 1
            fig.add_trace(go.Bar(
                x=df.index, y=df['Volume'],
                name='Volume', marker_color='lightblue'
            ), row=current_row, col=1)

        # === Layout global ===
        fig.update_layout(
            height=900,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=True,
            margin=dict(l=30, r=30, t=40, b=30)
        )

        # === Afficher toute la période ===
        fig.update_xaxes(range=[df.index.min(), df.index.max()])

        # === Masquer les week-ends ===
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

        # === Déplacer les axes Y à droite ===
        for i in range(1, current_row + 1):
            fig.update_yaxes(side="right", row=i, col=1)

        # === Affichage final ===
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
