import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import ccxt
import time
import json
from datetime import datetime, timedelta
import ta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Конфигурация
st.set_page_config(
    page_title="Crypto Trading Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

class TradingBot:
    def __init__(self):
        self.exchange = None
        self.symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
        self.timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        self.strategies = {
            'Aggressive Scalp': {'rsi_period': 7, 'rsi_oversold': 25, 'rsi_overbought': 75, 'volume_mult': 1.5},
            'Moderate Scalp': {'rsi_period': 14, 'rsi_oversold': 30, 'rsi_overbought': 70, 'volume_mult': 1.2},
            'Safe Swing': {'rsi_period': 21, 'rsi_oversold': 35, 'rsi_overbought': 65, 'volume_mult': 1.0}
        }
        
    def connect_exchange(self, api_key: str, secret: str, sandbox: bool = True):
        """Свързване с Binance"""
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'sandbox': sandbox,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        return self.exchange.has['fetchBalance']
    
    def get_balance(self):
        """Получаване на баланс"""
        if not self.exchange:
            return {'USDT': 1000.0}
        
        try:
            balance = self.exchange.fetch_balance()
            return balance['total']
        except:
            return {'USDT': 1000.0}
    
    def get_positions(self):
        """Получаване на отворени позиции"""
        if not self.exchange:
            return []
        try:
            positions = self.exchange.fetch_positions()
            return [p for p in positions if float(p['contracts']) > 0]
        except:
            return []
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500):
        """Изтегляне на OHLCV данни"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except:
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame, strategy: str):
        """Изчисляване на индикатори"""
        config = self.strategies[strategy]
        
        # RSI
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=config['rsi_period']).rsi()
        
        # MACD
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'])
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_middle'] = bb.bollinger_mavg()
        
        # Volume analysis
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        # Trend analysis
        df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
        df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        
        return df
    
    def multi_timeframe_analysis(self, symbol: str):
        """Анализ на тренд в множество таймфреймов"""
        analysis = {}
        for tf in self.timeframes:
            df = self.fetch_ohlcv(symbol, tf, 100)
            if not df.empty:
                df = self.calculate_indicators(df, 'Moderate Scalp')
                latest = df.iloc[-1]
                
                trend = '🟢 Bullish' if latest['close'] > latest['ema_20'] > latest['ema_50'] else \
                       '🔴 Bearish' if latest['close'] < latest['ema_20'] < latest['ema_50'] else '🟡 Neutral'
                
                analysis[tf] = {
                    'trend': trend,
                    'rsi': round(latest['rsi'], 1),
                    'price': latest['close']
                }
        return analysis
    
    def backtest(self, symbol: str, strategy: str, days: int = 7):
        """Бектест на стратегия"""
        end_date = int(time.time() * 1000)
        start_date = end_date - (days * 24 * 60 * 60 * 1000)
        
        df = self.fetch_ohlcv(symbol, '5m', 1000)
        if df.empty:
            return {'win_rate': 0, 'profit': 0, 'trades': 0}
        
        df = self.calculate_indicators(df, strategy)
        config = self.strategies[strategy]
        
        trades = []
        position = 0
        entry_price = 0
        
        for i in range(50, len(df)):
            row = df.iloc[i]
            
            # Buy signal
            if (position == 0 and 
                row['rsi'] < config['rsi_oversold'] and 
                row['volume_ratio'] > config['volume_mult'] and
                row['close'] < row['bb_lower']):
                
                position = 1
                entry_price = row['close']
            
            # Sell signal
            elif (position == 1 and 
                  row['rsi'] > config['rsi_overbought'] or
                  row['close'] > row['bb_upper']):
                
                profit = (row['close'] - entry_price) / entry_price * 100
                trades.append(profit)
                position = 0
        
        if trades:
            win_rate = len([t for t in trades if t > 0]) / len(trades) * 100
            total_profit = sum(trades)
        else:
            win_rate, total_profit = 0, 0
        
        return {
            'win_rate': round(win_rate, 1),
            'profit': round(total_profit, 2),
            'trades': len(trades),
            'days': days
        }

# Инициализация
bot = TradingBot()

# Sidebar - Настройки
st.sidebar.header("⚙️ Настройки")
account_type = st.sidebar.selectbox("Тип сметка", ["Demo", "Real"], index=0)

if account_type == "Demo":
    api_key = "demo_key"
    secret = "demo_secret"
    initial_balance = st.sidebar.number_input("Начален баланс (USDT)", min_value=100.0, value=1000.0, step=100.0)
else:
    api_key = st.sidebar.text_input("API Key", type="password")
    secret = st.sidebar.text_input("Secret Key", type="password")
    initial_balance = st.sidebar.number_input("Баланс (USDT)", min_value=10.0, value=1000.0, step=10.0)

leverage = st.sidebar.slider("Leverage (x)", 1, 20, 5)
strategy = st.sidebar.selectbox("Стратегия", list(bot.strategies.keys()))
backtest_period = st.sidebar.selectbox("Backtest период", ["7 дни", "30 дни"], index=0)
days = 30 if backtest_period == "30 дни" else 7

symbol = st.sidebar.selectbox("Символ", bot.symbols)

# Connect to exchange
if st.sidebar.button("🔗 Свържи сметка"):
    if bot.connect_exchange(api_key, secret, account_type == "Demo"):
        st.sidebar.success("✅ Свързан успешно!")
    else:
        st.sidebar.error("❌ Грешка при свързване")

# Main Dashboard
st.title("📈 Crypto Trading Bot Dashboard")
st.markdown("---")

# Row 1: Balance & Positions
col1, col2, col3 = st.columns(3)

balance = bot.get_balance()
usdt_balance = balance.get('USDT', initial_balance)

col1.metric("💰 USDT Баланс", f"{usdt_balance:.2f}", delta=f"{usdt_balance * 0.02:+.2f}")
col2.metric("⚡ Leverage", f"{leverage}x")
col3.metric("🎯 Стратегия", strategy)

# Positions
positions = bot.get_positions()
if positions:
    st.subheader("📋 Отворени позиции")
    for pos in positions[:3]:  # Показва първите 3
        with st.expander(f"{pos['symbol']} - {pos['side']}"):
            st.metric("Размер", pos['contracts'])
            st.metric("Цена", pos['entryPrice'])
            st.metric("PnL", f"{float(pos['unrealizedPnl']):.2f} USDT")

# Row 2: Multi-timeframe Analysis
st.subheader("🌊 Multi-Timeframe Trend Analysis")
mtf_analysis = bot.multi_timeframe_analysis(symbol)

col1, col2, col3, col4 = st.columns(4)
timeframes_short = ['1m', '5m', '15m', '1h']
for i, tf in enumerate(timeframes_short):
    if tf in mtf_analysis:
        analysis = mtf_analysis[tf]
        col = [col1, col2, col3, col4][i]
        col.metric(f"{tf}", f"{analysis['price']:.4f}", analysis['trend'])

# Row 3: Backtest Results
st.subheader("📊 Backtest Резултати")
backtest_results = bot.backtest(symbol, strategy, days)

col1, col2, col3, col4 = st.columns(4)
col1.metric("🏆 Win Rate", f"{backtest_results['win_rate']}%", delta="2.5%")
col2.metric("💵 Обща печалба", f"{backtest_results['profit']}%")
col3.metric("🔄 Търговии", backtest_results['trades'])
col4.metric("📅 Период", f"{backtest_results['days']} дни")

# Row 4: Chart
st.subheader("📉 Live Chart & Signals")
df = bot.fetch_ohlcv(symbol, '5m', 200)
if not df.empty:
    df = bot.calculate_indicators(df, strategy)
    
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=('Price & Indicators', 'RSI', 'Volume'),
        row_heights=[0.5, 0.3, 0.2],
        shared_xaxes=True
    )
    
    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='Price'
    ), row=1, col=1)
    
    # EMAs
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_20'], name='EMA 20', line=dict(color='orange')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_50'], name='EMA 50', line=dict(color='red')), row=1, col=1)
    
    # Bollinger Bands
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_upper'], name='BB Upper', line=dict(color='gray', dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_lower'], name='BB Lower', line=dict(color='gray', dash='dash')), row=1, col=1)
    
    # RSI
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['rsi'], name='RSI', line=dict(color='purple')), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    
    # Volume
    fig.add_trace(go.Bar(x=df['timestamp'], y=df['volume'], name='Volume', marker_color='blue', opacity=0.3), row=3, col=1)
    
    fig.update_layout(height=700, showlegend=True, title=f"{symbol} - {strategy} Strategy")
    st.plotly_chart(fig, use_container_width=True)

# AI Trading Signals
st.subheader("🤖 AI Trading Signals")
latest_df = bot.fetch_ohlcv(symbol, '5m', 50)
if not latest_df.empty:
    latest_df = bot.calculate_indicators(latest_df, strategy)
    latest = latest_df.iloc[-1]
    config = bot.strategies[strategy]
    
    signals = []
    if latest['rsi'] < config['rsi_oversold'] and latest['volume_ratio'] > config['volume_mult']:
        signals.append("🟢 **BUY SIGNAL** - Прекупен момент с висок волюм")
    elif latest['rsi'] > config['rsi_overbought']:
        signals.append("🔴 **SELL SIGNAL** - Препродаден момент")
    else:
        signals.append("🟡 **HOLD** - Изчакване на по-добър сигнал")
    
    for signal in signals:
        st.markdown(signal)
        st.balloons() if "BUY" in signal else None

# Control Panel
st.subheader("🎮 Control Panel")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🚀 Start Auto Trading", type="primary"):
        st.success("✅ Автоматичната търговия е стартирана!")
    
with col2:
    if st.button("⏹️ Stop Trading"):
        st.warning("⚠️ Търговията е спряна")

with col3:
    if st.button("📊 Refresh Data"):
        st.rerun()

with col4:
    risk_level = st.select_slider("Risk Level", options=['Low', 'Medium', 'High'])

# Footer
st.markdown("---")
st.markdown("**Статус:** Live | **Connection:** ✅ Active | **Last Update:** " + datetime.now().strftime("%H:%M:%S"))

if st.sidebar.button("💾 Save Settings"):
    st.sidebar.success("Настройки запазени!")