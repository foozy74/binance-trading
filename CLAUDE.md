# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Code style, naming, logging emoji conventions and the full command list live in `AGENTS.md` — follow it (German docstrings/comments, max 120 chars, functions ≤40 lines).

## Commands

```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000        # backend (starts the bot thread too)
pytest                                            # all tests
pytest tests/test_signals.py::TestOBVVWAPStrategy::test_buy_signal -v
pytest --cov=app --cov-report=html
python -m app.bot.backtest --symbol BTC/USDC:USDC --candles 5000   # backtest all strategies on Hyperliquid candles
python -m app.bot.walk_forward --symbol BTC/USDC:USDC --train 2000 --test 500   # out-of-sample param selection
python -m app.bot.walk_forward --symbol BTC/USDC:USDC --compare-stops   # fixed-% vs ATR stops, OOS
python -m app.bot.price_action --timeframe 1h   # price-action method (backtest only): backtest + walk-forward
python -m app.bot.volume_profile --symbol ETH/USDC:USDC --verbose   # volume profile (backtest only): walk-forward per setup
python -m app.bot.compare_signals --limit 500     # live signals from DB vs backtest replay (run in bot container)
cd frontend && npm run dev                        # React/Vite dashboard (npm run build → dist/)
```

Copy `.env.example` to `.env`. Keep `DRY_RUN=true` unless live trading is explicitly intended — `DRY_RUN=false` places real orders on the configured exchange.

## Architecture

- **One process, two roles**: `app/main.py` lifespan calls `init_db()` and starts `TradingBot.run()` in a daemon thread; FastAPI serves the API in parallel. Importing `app.main` (e.g. in tests) therefore spins up the bot loop.
- **Trading loop** (`app/bot/trader.py`): every 60 s fetch OHLCV → `strategy.generate_signal(df)` returns `(signal, confidence)` → persist signal → `_execute_trade()` via `BinanceService` (dry-run simulates orders) → persist trade, Prometheus counters, Telegram notify.
- **Exchange switch**: `EXCHANGE=binance|hyperliquid`. All ccxt clients come from `create_exchange()` in `app/services/exchange.py` — never instantiate `ccxt.binance` directly. Hyperliquid runs perps (`SYMBOL=BTC/USDC:USDC`): SELL opens/extends a short sized from the USDC margin, and market orders need a reference price. `BinanceService` keeps its name but serves both exchanges; balances are keyed by base/quote of `SYMBOL`.
- **Strategies** (`app/bot/strategies/`): subclass `BaseStrategy` (abstract `generate_signal`, `name`) and register in the `STRATEGIES` dict in `__init__.py`; selected by `ACTIVE_STRATEGY`. Indicators are pure functions in `app/bot/indicators.py`.
- **Backtest** (`app/bot/backtest.py`): mirrors the live loop — indicators on the rolling 100-candle window, signal at close of t, fill at open of t+1, same flip logic, taker fee, SL/TP checked against candle high/low (both hit → SL). `stop_loss` may be an `AtrStop(multiple, take_profit_r)`: distance = multiple × ATR of the signal candle, converted to a fraction at entry (no stop while ATR is still 0). Live on Hyperliquid, SL/TP are reduce-only trigger orders placed after each entry (old triggers cancelled first); in dry-run they are simulated each loop in `check_simulated_stops`. Stop math is shared in `app/bot/stops.py` (`configured_stop`, `stop_prices`): live default is `STOP_ATR_MULTIPLE=3` × ATR of the signal candle, no TP (`TAKE_PROFIT_R=0`); `STOP_ATR_MULTIPLE=0` falls back to fixed `TRAILING_STOP_PERCENT`/`TAKE_PROFIT_PERCENT` (a fixed stop, not trailing). Keep it in sync when trading logic changes.
- **Walk-forward** (`app/bot/walk_forward.py`): picks volume filter + SL/TP from `GRID` on each train window, scores only the following test window. `select_strategy` (stage 2) also re-picks the strategy per fold; `fixed_return` keeps fold 1's choice as the control for whether re-selection helps. The volume filter lives in `app/bot/signals.py` and is shared with the live loop (`VOLUME_FILTER`, 0 = off). Judge filters/params by its OOS numbers, not by single backtest runs (overfitting).
- **Price action** (`app/bot/price_action.py`, from `strategy/Strategiepapier_*.md`): backtest/walk-forward only, not in `STRATEGIES` and not live. Emits per-candle limit `Order`s (entry at zone edge, own stop/target per trade, CRV filter) instead of BUY/SELL; `simulate_orders` fills limits against high/low (stop wins on the fill candle). Swings = extremes over k candles each side, confirmed k candles later (no lookahead, tested).
- **Volume profile** (`app/bot/volume_profile.py`, from `strategy/Systematisches Regelwerk_*.md`): backtest/walk-forward only. Profile (POC/VAL/VAH, 70 %) per UTC day from the previous day, candle volume spread uniformly over high–low. Three setups emit `Signal`s (`POC_BOUNCE` first touch of the prior POC, `VA_REVERSAL`, `BREAKOUT` strong candle + pullback + BOS, target = nearest naked POC); `build_signals(..., setups=)` picks them, first setup wins per candle. `simulate_signals` enters at next open, sizes by risk (`RISK_PER_TRADE` / stop distance, capped by `MAX_LEVERAGE`), time-stops at the session's last close and reports R after fees per setup. Walk-forward reuses `walk_forward_orders(..., build, simulate)`.
- **Funding signal** (`app/bot/funding.py`, ported from AutoFund-AI `lib/fundingSignal.ts`): contrarian Hyperliquid funding value in [-1, 1] (neutral = 11 % APR base rate). Only used in the walk-forward (as filter param and as standalone `funding_*` strategies), not live. Timestamps: pandas 3 stores datetimes in µs — convert via `astype('datetime64[ms]')`, never assume ns.
- **Persistence**: SQLAlchemy + SQLite (`DATABASE_URL`, default `data/trading.db`); access only through the repositories in `app/db/repository.py` (`TradeRepository`, `SignalRepository`, `ConfigRepository` — runtime config key/value). Dashboard changes (`PUT /api/config`) are validated in `app/bot/runtime_config.py`, stored there and set on `settings` at once; `load_saved_config` re-applies them at startup, and the bot swaps strategy at the start of each loop.
- **API** (`app/api/`): routes under `/api/*`, `/health`, `/metrics` (Prometheus). All `/api/*` routes except `POST /api/auth/login` require `require_auth`: a JWT (`Authorization: Bearer`, 8 h, from the dashboard login against `ADMIN_USERNAME`/`ADMIN_PASSWORD`) or `X-API-Key` from `API_KEYS` (`name:secret,...`, for scripts). Login has an in-memory lockout (10 failures / 15 min per client IP). `JWT_SECRET` ≥ 32 chars, `ADMIN_PASSWORD` ≥ 12, API-key secrets ≥ 16 — enforced at startup.
- **Dashboard-Backtest** (`app/api/backtest_route.py`, `POST /api/backtest`): runs `generate_signals`/`simulate` on up to 5000 Hyperliquid 1h candles of `SYMBOL` (must exist on Hyperliquid); one run at a time (409 otherwise), nginx allows 180 s for it. Panel: `frontend/src/components/BacktestPanel.jsx`.
- **Settings**: pydantic `Settings` in `app/config.py`, read from env.
- **Tests**: `tests/conftest.py` uses a file-based `sqlite:///./test.db` and overrides `get_db` on the app.

## Deployment

Docker (`Dockerfile`, `docker-compose.yml`); Coolify uses `docker-compose.coolify.yml` with health check `/health`, port 8000, volume `trading_data` for SQLite. `frontend/` has its own Dockerfile + nginx.

Legacy `biance_bot*.py` scripts at the root are deleted/being migrated — don't revive them.
