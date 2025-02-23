import pandas as pd
import numpy as np
import ccxt
import time
import requests
import ta
from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions
from dotenv import load_dotenv
import os

# .env-Datei laden
load_dotenv()

# API-Schlüssel und InfluxDB-Konfiguration aus .env-Datei laden
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = "6872658286"

INFLUXDB_URL = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET")

# Binance-API-Konfiguration
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# InfluxDB-Client initialisieren
client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=500, flush_interval=10_000, jitter_interval=2_000, retry_interval=5_000))

# Konstante Werte
SYMBOL = "BTC/USDT"
MIN_TRADE_AMOUNT_USDT = 10  # Binance erfordert mind. 10 USDT pro Trade
TRADE_PERCENTAGE = 0.10  # Anteil des Guthabens pro Trade
TRAILING_STOP_PERCENT = 0.02  # Trailing Stop-Loss in Prozent
TAKE_PROFIT_PERCENT = 0.05  # Take-Profit in Prozent

# Marktdaten abrufen & Indikatoren berechnen
def fetch_market_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe='1h', limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # OBV (On-Balance Volume)
    df['price_change'] = df['close'].diff()
    df['direction'] = np.where(df['price_change'] > 0, 1, np.where(df['price_change'] < 0, -1, 0))
    df['OBV'] = (df['direction'] * df['volume']).cumsum()

    # VWAP (Volume Weighted Average Price)
    df['cumulative_vol'] = df['volume'].cumsum()
    df['cumulative_vp'] = (df['close'] * df['volume']).cumsum()
    df['VWAP'] = df['cumulative_vp'] / df['cumulative_vol']

    # RSI (Relative Strength Index)
    df["RSI"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    # Bollinger Bands
    bollinger = ta.volatility.BollingerBands(df["close"], window=20)
    df["Bollinger_Upper"] = bollinger.bollinger_hband()
    df["Bollinger_Lower"] = bollinger.bollinger_lband()

    # EMA (Exponential Moving Average)
    df["EMA_20"] = df["close"].ewm(span=20).mean()

    return df

# Signal-Generierung mit zusätzlichen Filtern
def get_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # OBV & VWAP als Hauptstrategie
    if last['OBV'] > prev['OBV'] and last['close'] > last['VWAP']:
        signal = "BUY"
    elif last['OBV'] < prev['OBV'] and last['close'] < last['VWAP']:
        signal = "SELL"
    else:
        return "HOLD"

    # RSI-Filter
    if last["RSI"] > 70 and signal == "BUY":  # Überkauft
        return "HOLD"
    elif last["RSI"] < 30 and signal == "SELL":  # Überverkauft
        return "HOLD"

    # Bollinger Bands-Filter
    if last["close"] >= last["Bollinger_Upper"] and signal == "BUY":
        return "HOLD"
    elif last["close"] <= last["Bollinger_Lower"] and signal == "SELL":
        return "HOLD"

    return signal

# Order-Funktion mit Trailing Stop-Loss
def place_order(symbol, side):
    try:
        # Guthaben abrufen
        balance = exchange.fetch_balance()
        usdt_available = balance['total'].get('USDT', 0)
        btc_available = balance['total'].get('BTC', 0)

        # Dynamische Trade-Größe berechnen
        trade_amount_usdt = max(usdt_available * TRADE_PERCENTAGE, MIN_TRADE_AMOUNT_USDT)
        ticker = exchange.fetch_ticker(symbol)
        btc_amount = trade_amount_usdt / ticker['last']

        # Order nur platzieren, wenn genügend BTC/USDT vorhanden ist
        if side == "sell" and btc_amount > btc_available:
            print(f"⛔ Nicht genug BTC für Verkauf! BTC auf Binance: {btc_available}, benötigt: {btc_amount}")
            return

        # Market-Order platzieren
        order = exchange.create_market_order(symbol, side, btc_amount)

        # Trailing Stop-Loss & Take-Profit setzen
        stop_loss_price = ticker['last'] * (1 - TRAILING_STOP_PERCENT) if side == "buy" else ticker['last'] * (1 + TRAILING_STOP_PERCENT)
        take_profit_price = ticker['last'] * (1 + TAKE_PROFIT_PERCENT) if side == "buy" else ticker['last'] * (1 - TAKE_PROFIT_PERCENT)

        print(f"📌 Stop-Loss gesetzt auf: {stop_loss_price:.2f}, Take-Profit auf: {take_profit_price:.2f}")

        # Trade-Details in InfluxDB speichern
        point = Point("trades") \
            .tag("symbol", symbol) \
            .tag("side", side) \
            .field("amount", btc_amount) \
            .field("price", ticker['last']) \
            .field("usdt_value", trade_amount_usdt) \
            .field("stop_loss", stop_loss_price) \
            .field("take_profit", take_profit_price) \
            .time(time.time_ns())

        write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        print("✅ Trade-Daten in InfluxDB gespeichert!")

        # Telegram-Benachrichtigung senden
        message = (
            f"📢 Trade ausgeführt!\n"
            f"💰 Aktion: {side.upper()}\n"
            f"📈 Symbol: {symbol}\n"
            f"🔹 Menge: {btc_amount:.8f} BTC\n"
            f"💵 Wert: {trade_amount_usdt:.2f} USDT\n"
            f"📌 Stop-Loss: {stop_loss_price:.2f} USDT\n"
            f"📌 Take-Profit: {take_profit_price:.2f} USDT\n"
        )
        send_telegram_message(message)

    except Exception as e:
        print(f"❌ Fehler beim Platzieren der Order: {e}")

# Telegram-Benachrichtigung senden
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text})

# Bot-Dauerschleife
while True:
    df = fetch_market_data()
    signal = get_signal(df)
    print(f"📈 Aktuelles Signal: {signal}")

    if signal in ["BUY", "SELL"]:
        place_order(SYMBOL, signal)

    time.sleep(60)
