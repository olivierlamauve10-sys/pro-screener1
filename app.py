import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# === FONCTION GRAPHIQUE ===
def plot_chart(symbol):
    try:
        df = yf.Ticker(symbol).history(period="1y")
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

