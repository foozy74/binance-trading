import time
import threading
from typing import Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.bot.stops import stop_prices
from app.bot.signals import fetch_market_data, volume_ratio
from app.bot.strategies import get_strategy
from app.services.binance import BinanceService
from app.services.telegram import TelegramService
from app.db.database import SessionLocal
from app.db.repository import TradeRepository, SignalRepository
from app.api.metrics import bot_trades_total, bot_signals_total, bot_profit_loss, bot_portfolio_value


class TradingBot:
    """Main trading bot with background loop"""
    
    def __init__(self):
        self.running = False
        self._strategy_key = settings.ACTIVE_STRATEGY
        self.strategy = get_strategy(self._strategy_key)
        self.binance = BinanceService(dry_run=settings.DRY_RUN)
        self.telegram = TelegramService()
        self.db: Optional[Session] = None
        self._thread: Optional[threading.Thread] = None
        self._last_candle_ts = None
    
    def start(self):
        """Start the trading bot"""
        self.running = True
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the trading bot"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def run(self):
        """Main trading loop"""
        print(f"📌 Trading Bot gestartet (Strategy: {self.strategy.name}, Dry Run: {settings.DRY_RUN})")
        
        while self.running:
            try:
                self._execute_loop()
            except Exception as e:
                print(f"❌ Error in trading loop: {e}")
            
            time.sleep(60)  # Wait 1 minute between iterations
    
    def _sync_strategy(self):
        """Strategie wechseln, wenn sie im Dashboard geändert wurde"""
        if self._strategy_key != settings.ACTIVE_STRATEGY:
            self.strategy = get_strategy(settings.ACTIVE_STRATEGY)
            self._strategy_key = settings.ACTIVE_STRATEGY
            print(f"🔄 Strategie gewechselt: {self.strategy.name}")

    def _execute_loop(self):
        """Execute one iteration of the trading loop"""
        self._sync_strategy()
        db = SessionLocal()
        try:
            # Fetch market data
            df = fetch_market_data()

            # Dry-Run: SL/TP minütlich gegen den aktuellen Preis prüfen (live erledigt das die Börse)
            stop_hit = self.binance.check_simulated_stops(settings.SYMBOL)
            if stop_hit:
                print(f"🧪 Simulierte Position geschlossen: {stop_hit}")

            # Pro abgeschlossener Kerze nur einmal auswerten, sonst wird dasselbe Signal jede Minute gehandelt
            candle_ts = df.iloc[-1]["timestamp"]
            if candle_ts == self._last_candle_ts:
                return
            self._last_candle_ts = candle_ts

            # Generate signal
            signal, confidence = self.strategy.generate_signal(df)
            if signal != "HOLD" and settings.VOLUME_FILTER and volume_ratio(df).iloc[-1] < settings.VOLUME_FILTER:
                print(f"⛔ {signal} verworfen: Volumen unter {settings.VOLUME_FILTER}x Durchschnitt")
                signal, confidence = "HOLD", None
            
            # Store signal in database
            last_row = df.iloc[-1]
            signal_repo = SignalRepository(db)
            signal_repo.create({
                "symbol": settings.SYMBOL,
                "signal": signal,
                "strategy": self.strategy.name,
                "confidence": confidence,
                "rsi": last_row.get("RSI"),
                "macd": last_row.get("MACD"),
                "obv": last_row.get("OBV"),
                "vwap": last_row.get("VWAP")
            })
            
            # Update metrics
            bot_signals_total.labels(signal_type=signal, strategy=self.strategy.name).inc()
            
            print(f"📈 Signal: {signal} (Confidence: {confidence})")
            
            # Execute trade if signal is BUY or SELL
            if signal in ["BUY", "SELL"]:
                self._execute_trade(signal, df, db)
            
        finally:
            db.close()
    
    def _execute_trade(self, signal: str, df, db: Session):
        """Execute a trade based on signal"""
        try:
            # Get balance and calculate position size
            balance = self.binance.fetch_balance()
            ticker = self.binance.fetch_ticker(settings.SYMBOL)
            size = self.binance.calculate_position_size(signal, balance, ticker)
            amount = size
            is_perp = settings.EXCHANGE == "hyperliquid"
            if is_perp:
                amount = self.binance.adjust_for_position(signal, size)
                if amount is None:
                    print(f"⛔ {signal} übersprungen: Position in gleicher Richtung bereits offen")
                    return
                self.binance.cancel_open_orders(settings.SYMBOL)

            # Create order
            order = self.binance.create_order(settings.SYMBOL, signal.lower(), amount)

            if order:
                # Calculate stop loss and take profit
                price = order.get('average') or order.get('price') or ticker['last']
                signal_bar = df.iloc[-1].to_dict()
                if is_perp:
                    stops = self.binance.place_protection(settings.SYMBOL, signal, size, price, signal_bar)
                else:
                    stops = stop_prices(signal, price, signal_bar)
                if 'stopLossPrice' not in stops:
                    print("⛔ Kein Stop-Loss gesetzt (ATR noch nicht berechenbar oder Stop abgeschaltet)")
                stop_loss, take_profit = stops.get('stopLossPrice'), stops.get('takeProfitPrice')
                
                # Store trade in database
                trade_repo = TradeRepository(db)
                trade = trade_repo.create({
                    "symbol": settings.SYMBOL,
                    "side": signal.lower(),
                    "amount": amount,
                    "price": price,
                    "usdt_value": amount * price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "is_dry_run": settings.DRY_RUN,
                    "status": "executed"
                })
                
                # Update metrics
                bot_trades_total.labels(side=signal.lower(), dry_run=str(settings.DRY_RUN)).inc()
                
                print(f"✅ Trade executed: {signal} {amount:.8f} BTC @ {price:.2f} USDT")
                
                # Send Telegram notification
                trade_data = {
                    "symbol": settings.SYMBOL,
                    "side": signal.lower(),
                    "amount": amount,
                    "price": price,
                    "usdt_value": amount * price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "is_dry_run": settings.DRY_RUN
                }
                self.telegram.send_trade_notification(trade_data)
                
        except Exception as e:
            print(f"❌ Failed to execute trade: {e}")
