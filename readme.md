# Binance Trading Bot v2.0

Python-basierter Trading-Bot für die Binance-Kryptowährungsbörse mit REST-API, mehreren Trading-Strategien, Coolify-Deployment-Support und modernem Web-UI.

## 🚀 Features

- **🎨 Modernes Web-UI**: React + Vite mit Glassmorphism Design
- **📊 Echtzeit-Dashboard**: Bot-Status, Signale, Trades, Konfiguration
- **🔌 REST-API** mit FastAPI (Health-Checks, Metrics, Trade-History)
- **📈 Mehrere Trading-Strategien**: OBV+VWAP, RSI-Divergenz, MACD-Crossover, Multi-Signal
- **🧪 Dry-Run Modus** für Paper-Trading ohne Risiko
- **📉 Prometheus-Metrics** für Monitoring
- **📱 Telegram-Benachrichtigungen** parallel zur API
- **💾 SQLite-Datenbank** für Trade-History
- **🐳 Docker-ready** mit Coolify-Konfiguration
- **🔐 JWT + API-Key Authentication**

## 📁 Projektstruktur

```
binance-trading/
├── app/                       # Backend (FastAPI)
│   ├── main.py                # FastAPI Application
│   ├── config.py              # Configuration (pydantic)
│   ├── api/
│   │   ├── routes.py          # REST-Endpoints
│   │   ├── auth.py            # JWT + API-Key Auth
│   │   └── metrics.py         # Prometheus Metrics
│   ├── bot/
│   │   ├── trader.py          # Trading-Loop
│   │   ├── signals.py         # Signal-Generierung
│   │   ├── indicators.py      # Technische Indikatoren
│   │   └── strategies/        # Trading-Strategien
│   ├── db/
│   │   ├── models.py          # SQLAlchemy Models
│   │   ├── database.py        # Database Connection
│   │   └── repository.py      # CRUD Operations
│   └── services/
│       ├── binance.py         # Binance API Wrapper
│       └── telegram.py        # Telegram Notifications
├── frontend/                  # Frontend (React + Vite)
│   ├── src/
│   │   ├── components/        # React Components
│   │   ├── services/          # API Services
│   │   └── styles/            # CSS Styles
│   ├── Dockerfile             # NGINX Docker Image
│   └── nginx.conf             # NGINX Configuration
├── tests/
│   ├── test_indicators.py
│   ├── test_signals.py
│   ├── test_api.py
│   └── test_trading.py
├── docker-compose.yml
├── docker-compose.coolify.yml
└── requirements.txt
```

## 🛠️ Installation

### Local Development (Backend)

```bash
# Virtuelle Umgebung erstellen
python -m venv venv && source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Umgebungsvariablen konfigurieren
cp .env.example .env
# .env mit eigenen Werten bearbeiten

# Bot starten (API + Trading)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Local Development (Frontend)

```bash
cd frontend

# Dependencies installieren
npm install

# Dev-Server starten (mit Proxy zum Backend)
npm run dev
```

### Docker

```bash
# Images bauen
docker-compose build

# Alle Services starten (Backend + Frontend)
docker-compose up -d

# Frontend: http://localhost:80
# Backend API: http://localhost:8000
```

### Docker Compose

```bash
# Standard (mit Frontend)
docker-compose up -d

# Coolify
docker-compose -f docker-compose.coolify.yml up -d
```

### Local Development (Frontend)

```bash
cd frontend

# Dependencies installieren
npm install

# Dev-Server starten (mit Proxy zum Backend)
npm run dev
```

### Docker

```bash
# Images bauen
docker-compose build

# Alle Services starten (Backend + Frontend)
docker-compose up -d

# Frontend: http://localhost:80
# Backend API: http://localhost:8000
```

### Docker Compose

```bash
# Standard (mit Frontend)
docker-compose up -d

# Coolify
docker-compose -f docker-compose.coolify.yml up -d
```

## 🌐 Web-UI

Das Dashboard ist nach dem Start unter `http://localhost:80` verfügbar.

**Features:**
- 📊 Echtzeit-Bot-Status (alle 10 Sekunden aktualisiert)
- 📈 Letzte Signale mit Strategie und Confidence
- 💼 Trade-History Tabelle
- ⚙️ Konfigurations-Panel (Strategie wechseln, etc.)
- 🔐 API-Key Authentication

**API-Key eingeben** um auf geschützte Endpoints zuzugreifen.

## 🌐 Web-UI

Das Dashboard ist nach dem Start unter `http://localhost:80` verfügbar.

**Features:**
- 📊 Echtzeit-Bot-Status (alle 10 Sekunden aktualisiert)
- 📈 Letzte Signale mit Strategie und Confidence
- 💼 Trade-History Tabelle
- ⚙️ Konfigurations-Panel (Strategie wechseln, etc.)
- 🔐 API-Key Authentication

**API-Key eingeben** um auf geschützte Endpoints zuzugreifen.

## 📡 API-Endpoints

### Public Endpoints

| Endpoint | Beschreibung |
|----------|--------------|
| `GET /` | API-Info |
| `GET /health` | Health-Check für Coolify |
| `GET /metrics` | Prometheus-Metrics |

### Protected Endpoints (API-Key required)

| Endpoint | Beschreibung |
|----------|--------------|
| `GET /api/status` | Bot-Status |
| `GET /api/signals` | Historische Signale |
| `GET /api/trades` | Historische Trades |
| `GET /api/portfolio` | Portfolio-Übersicht |
| `GET /api/config` | Aktuelle Konfiguration |
| `PUT /api/config` | Konfiguration aktualisieren |

### API-Key verwenden

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8000/api/status
```

## 📊 Trading-Strategien

### 1. OBV + VWAP (Default)
- On-Balance Volume + Volume Weighted Average Price
- RSI-Filter (>70 blockiert BUY, <30 blockiert SELL)
- Bollinger-Band-Filter

### 2. RSI-Divergenz
- Erkennt bullische/bärische Divergenzen
- RSI-Reversal von Extremwerten

### 3. MACD-Crossover
- MACD-Linie kreuzt Signallinie
- Nulllinien-Crossover

### 4. Multi-Signal Consensus
- Kombiniert alle Strategien
- Erfordert 2 von 3 Übereinstimmungen

### Strategie wechseln

**Per Environment Variable:**
```bash
ACTIVE_STRATEGY=macd_crossover
```

**Per API (dynamisch):**
```bash
curl -X PUT http://localhost:8000/api/config \
  -H "X-API-Key: your-secret" \
  -H "Content-Type: application/json" \
  -d '{"active_strategy": "multi_signal"}'
```

## 🔧 Konfiguration

### Environment Variablen

| Variable | Beschreibung | Default |
|----------|--------------|---------|
| `DRY_RUN` | Paper-Trading Modus | `true` |
| `BINANCE_API_KEY` | Binance API Key | - |
| `BINANCE_API_SECRET` | Binance API Secret | - |
| `JWT_SECRET` | JWT Signing-Key (min. 32 Zeichen) | auto-generated |
| `API_KEYS` | API-Keys für Skripte (name:secret, Secret min. 16 Zeichen) | - |
| `ADMIN_USERNAME` | Dashboard-Login Benutzer | `admin` |
| `ADMIN_PASSWORD` | Dashboard-Login Passwort (min. 12 Zeichen, leer = Login aus) | - |
| `ACTIVE_STRATEGY` | Trading-Strategie | `obv_vwap` |
| `TRADE_PERCENTAGE` | Trade-Größe (% des Portfolios) | `0.10` |
| `TRAILING_STOP_PERCENT` | Trailing Stop-Loss | `0.02` |
| `TAKE_PROFIT_PERCENT` | Take-Profit | `0.05` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | - |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | - |

## 🧪 Tests ausführen

```bash
# Alle Tests
pytest

# Mit Coverage
pytest --cov=app --cov-report=html

# Einzelne Testdatei
pytest tests/test_indicators.py -v

# Einzelner Test
pytest tests/test_signals.py::TestOBVVWAPStrategy::test_buy_signal -v
```

## 📈 Coolify-Deployment

1. **Repository zu Coolify hinzufügen**
2. **Build Settings:**
   - Build Command: `docker build -t binance-trading-bot .`
   - Start Command: (leer lassen, wird im Dockerfile definiert)
3. **Environment Variables setzen** (aus `.env.example`)
4. **Health Check Path:** `/health`
5. **Port:** `8000`

Oder `docker-compose.coolify.yml` verwenden.

## 🔐 Authentication

### API-Key generieren

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### API-Keys konfigurieren

```env
API_KEYS=admin:generated-secret-1,service:generated-secret-2
```

### Dashboard-Login

Alle `/api/*`-Routen verlangen einen Login (JWT, 8 h gültig) oder einen API-Key.
`ADMIN_USERNAME`/`ADMIN_PASSWORD` setzen, dann im Dashboard anmelden – oder per API:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" -d '{"username":"admin","password":"..."}'
# → {"access_token": "...", "token_type": "bearer"}
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/status
```

Nach 10 Fehlversuchen ist der Login 15 Minuten gesperrt.

## ⚠️ Haftungsausschluss

Dieser Bot ist für **Bildungszwecke** gedacht. Trading birgt finanzielle Risiken. 
- **Immer zuerst DRY_RUN=true testen!**
- Nie mehr investieren als man verlieren kann
- Eigene Due Diligence durchführen

## 📝 Lizenz

MIT License - siehe [LICENSE](LICENSE)
