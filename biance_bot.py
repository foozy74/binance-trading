import pandas as pd
import numpy as np
import ccxt
import time
import requests
import ta
from influxdb_client import InfluxDBClient, Point, WritePrecision

# 📌 Binance API-Schlüssel (ersetzen durch eigene)
api_key = ""
api_secret = ""

exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# 📌 Grafana Cloud InfluxDB v3 Konfiguration
INFLUXDB_URL = "https://us-east-1-1.aws.cloud2.influxdata.com"
INFLUXDB_TOKEN = "DEIN_INFLUXDB_TOKEN"  # Ersetze mit deinem Token "binancetrading"
ORG = "306492"
BUCKET = "stack-303219-influx-write"

client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=ORG)
write_api = client.write_api(write_options=WritePrecision.NS)

# 📌 Trading-Konstanten
SYMBOL = "BTC/USDT"
TRADE_PERCENTAGE = 0.10  # Anteil des Guthabens pro Trade

# 📊 Marktdaten abrufen & Indikatoren berechnen
def fetch_market_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe='1h', limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # ✅ Indikatoren berechnen
    df["RSI"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["EMA_20"] = df["close"].ewm(span=20).mean()
    
    return df

# 📈 Signal-Generierung
def get_signal(df):
    last = df.iloc[-1]
    if last["RSI"] < 30: return "BUY"
    if last["RSI"] > 70: return "SELL"
    return "HOLD"

# 🚀 Order-Funktion & Daten speichern
def place_order(symbol, side):
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        balance = exchange.fetch_balance()
        usdt_available = balance['total'].get('USDT', 0)
        trade_amount_usdt = usdt_available * TRADE_PERCENTAGE
        btc_amount = trade_amount_usdt / price

        # 📌 Order wird hier simuliert (kein echter Trade)
        print(f"🔹 Order: {side} {btc_amount:.6f} BTC zu {price:.2f} USDT")

        # 📊 Daten in Grafana Cloud speichern
        point = Point("trades") \
            .tag("symbol", symbol) \
            .tag("side", side) \
            .field("price", price) \
            .field("amount", btc_amount)
        
        write_api.write(bucket=BUCKET, record=point)
        print("✅ Trade-Daten in Grafana Cloud gespeichert!")

    except Exception as e:
        print(f"❌ Fehler beim Platzieren der Order: {e}")

# 🔄 Bot-Dauerschleife
while True:
    df = fetch_market_data()
    signal = get_signal(df)
    print(f"📈 Signal: {signal}")

    if signal in ["BUY", "SELL"]:
        place_order(SYMBOL, signal)

    time.sleep(60)
