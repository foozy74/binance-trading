# Binance Trading Bot mit Grafana Cloud (InfluxDB v3)

Ein automatisierter **Binance Trading Bot**, der technische Indikatoren (RSI, EMA) verwendet, um Kauf- und Verkaufssignale zu generieren. Trades und Marktdaten werden in **InfluxDB v3 (Grafana Cloud)** gespeichert und können über **Grafana Dashboards** visualisiert werden.

## 🚀 Features
✅ **Automatisierter Handel** auf Binance (Spot-Trading)  
✅ **Technische Analyse**: RSI & EMA für Kauf-/Verkaufssignale  
✅ **Integration mit Grafana Cloud** (InfluxDB v3) zur Speicherung & Analyse  
✅ **Echtzeit-Datenvisualisierung** mit Grafana Dashboards  
✅ **Einfach konfigurierbar & erweiterbar**  

---

## 🛠 Installation & Einrichtung
### 1️⃣ Voraussetzungen
- **Python 3.8+**
- **Binance API-Key** (Registriere dich bei [Binance](https://www.binance.com))
- **Grafana Cloud Account** ([Anmelden](https://grafana.com/cloud))
- **InfluxDB v3 Token** (Erstelle ein Token in Grafana Cloud)

### 2️⃣ Python-Abhängigkeiten installieren
```bash
pip install python-dotenv influxdb-client pandas numpy ccxt ta requests
```

### 3️⃣ Umgebungsvariablen setzen
Erstelle eine **.env** Datei im Projektverzeichnis:
```env
BINANCE_API_KEY=dein_api_key
BINANCE_SECRET=dein_secret
INFLUXDB_URL=https://us-east-1-1.aws.cloud2.influxdata.com
INFLUXDB_TOKEN=dein_influxdb_token
ORG=306492
BUCKET=stack-303219-influx-write
```

### 4️⃣ Konfiguration im Code anpassen
Bearbeite den Code in `binance_bot.py`, um die Umgebungsvariablen zu laden:
```python
import os
from dotenv import load_dotenv

# 📌 Umgebungsvariablen laden
load_dotenv()

# 📌 Binance API
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_SECRET")

# 📌 InfluxDB v3 (Grafana Cloud)
INFLUXDB_URL = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
ORG = os.getenv("ORG")
BUCKET = os.getenv("BUCKET")
```

### 5️⃣ Bot starten
```bash
python binance_bot.py
```
Der Bot ruft nun Marktdaten ab, generiert Signale und speichert Trades in **Grafana Cloud (InfluxDB v3)**.

---

## 📊 Grafana Cloud Dashboard einrichten
### 1️⃣ InfluxDB in Grafana verbinden
1. **Gehe zu Grafana Cloud → Data Sources → InfluxDB v3**
2. **Verbinde mit deinem Token & Bucket**

### 2️⃣ Beispiel-Query für Trades
Füge in Grafana ein **Panel** mit folgendem Flux-Query hinzu:
```flux
from(bucket: "stack-303219-influx-write")
|> range(start: -1h)
|> filter(fn: (r) => r._measurement == "trades")
```

### 3️⃣ RSI & EMA als Time-Series Panel
```flux
from(bucket: "stack-303219-influx-write")
|> range(start: -1h)
|> filter(fn: (r) => r._measurement == "trades" and (r._field == "RSI" or r._field == "EMA_20"))
```

---

## ⚙️ Anpassungen & Erweiterungen
- **Trading-Strategie ändern:** Passe die `get_signal()`-Methode an.
- **Weitere Indikatoren hinzufügen:** Nutze `ta` (Technical Analysis Library) für zusätzliche Analysen.
- **Order-Funktion erweitern:** Implementiere Stop-Loss & Take-Profit Strategien.

---

## 📜 Lizenz
MIT License

---

## ✨ Kontakt & Feedback
Hast du Fragen oder möchtest etwas verbessern? Erstelle ein Issue oder Pull Request! 😊

