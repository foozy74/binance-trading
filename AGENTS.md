# AGENTS.md - Guidelines for AI Agents

## Build & Run Commands

```bash
# Install dependencies
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run FastAPI server (development)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run single test
pytest tests/test_indicators.py::test_obv_calculation -v

# Run all tests
pytest

# Docker
docker build -t binance-trading-bot .
docker run --env-file .env -p 8000:8000 binance-trading-bot
docker-compose up -d
```

## Testing

**Test Framework: pytest**

```bash
# All tests
pytest

# Single test file
pytest tests/test_indicators.py -v

# Single test
pytest tests/test_signals.py::TestOBVVWAPStrategy::test_buy_signal -v

# With coverage
pytest --cov=app --cov-report=html

# Dry-run mode (paper trading)
DRY_RUN=true uvicorn app.main:app
```

## Code Style Guidelines

### Imports
- Standard library imports first (`os`, `time`, `json`)
- Third-party libraries second (`pandas`, `numpy`, `ccxt`, `ta`)
- Local/special imports last (`influxdb_client`, `dotenv`)
- Use `import module` pattern; avoid `from x import *`

### Formatting
- 4 spaces for indentation (no tabs)
- Maximum line length: 120 characters
- Blank line between function definitions
- Spaces around operators: `x = 1 + 2`

### Naming Conventions
- **Files**: snake_case (`biance_bot_advanced.py`)
- **Functions**: snake_case (`fetch_market_data`, `get_signal`)
- **Variables**: snake_case (`trade_amount_usdt`, `api_key`)
- **Constants**: UPPER_SNAKE_CASE (`SYMBOL`, `TRADE_PERCENTAGE`)
- **Classes**: PascalCase (Strategy classes in `app/bot/strategies/`)

### Types
- Type hints for new functions: `def func(param: str) -> bool:`
- Pydantic for config: `class Settings(BaseSettings)`
- Expected types: `pd.DataFrame` for data, `str` for signals, `float` for prices

### Error Handling
- Wrap API calls in `try/except Exception as e` blocks
- Log errors with descriptive messages: `print(f"❌ Fehler: {e}")`
- Return early on validation failures (guard clause pattern)
- Never swallow exceptions silently
- HTTPExceptions for API errors: `raise HTTPException(status_code=400, detail="...")`

### Functions
- Single responsibility principle
- Maximum 30-40 lines per function
- German docstrings/comments (project convention)
- Pure functions where possible (e.g., indicator calculations)

### Security
- **NEVER** commit `.env` file or hardcoded credentials
- Load secrets from environment: `os.getenv("BINANCE_API_KEY")`
- API-Key authentication for protected endpoints
- JWT for future user authentication
- SQLite for local data (no external DB required)

### Architecture Patterns
- **Main entry point**: `app/main.py` (FastAPI application)
- **Data flow**: `fetch_market_data()` → `strategy.generate_signal()` → `trader._execute_trade()`
- **Indicators**: `app/bot/indicators.py` (OBV, VWAP, RSI, Bollinger, MACD, Stochastic, ADX, MFI, ATR)
- **Strategies**: `app/bot/strategies/` (Base class + 4 implementations)
- **Trade constants**: `app/config.py` via pydantic Settings

### Pandas/NumPy Usage
- Use vectorized operations over loops
- Column naming: snake_case (`'cumulative_vol'`, `'Bollinger_Upper'`)
- Access last row: `df.iloc[-1]`, previous: `df.iloc[-2]`
- All indicators in `app/bot/indicators.py`

### Logging
- Use emoji prefixes for log levels:
  - `📈` Info (signals, data)
  - `✅` Success (trades executed)
  - `❌` Error (exceptions)
  - `🔹` Debug (order details)
  - `📌` Configuration/notes
  - `⛔` Warning (blocked actions)
  - `🧪` Dry-run mode

### Git
- No pre-commit hooks configured
- Commit message format: imperative mood ("Add feature", "Fix bug")
- `.env` and secrets excluded via `.gitignore`

### Testing
- **Framework**: pytest
- **Fixtures**: `tests/conftest.py` (database, client)
- **Test files**: `test_indicators.py`, `test_signals.py`, `test_api.py`, `test_trading.py`
- **Coverage**: `pytest --cov=app --cov-report=html`

### Coolify Deployment
- Use `docker-compose.coolify.yml`
- Health check path: `/health`
- Port: `8000`
- Volume: `trading_data` for SQLite persistence

### Known Issues
- Legacy files (`biance_bot*.py`) should be migrated or removed
- InfluxDB client removed from requirements (SQLite replacement)
- No E2E tests yet (only unit and integration tests)
