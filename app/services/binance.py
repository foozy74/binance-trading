from typing import Optional, Dict
from app.config import settings
from app.bot.stops import stop_prices
from app.services.exchange import create_exchange, symbol_assets


class BinanceService:
    """Service for exchange interactions (Binance Spot oder Hyperliquid Perps, je nach EXCHANGE)"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.exchange = create_exchange()
        # shortcut: simulierte Position nur im Speicher, geht bei Neustart verloren – bei Bedarf aus Trades-DB ableiten
        self._sim_net_position = 0.0
        self._sim_stops: Optional[Dict[str, float]] = None

    def fetch_balance(self) -> Dict:
        """Fetch account balance for base and quote asset of SYMBOL"""
        balance = self.exchange.fetch_balance()
        return {asset: balance['total'].get(asset, 0) for asset in symbol_assets(settings.SYMBOL)}

    def fetch_ticker(self, symbol: str) -> Dict:
        """Fetch current ticker"""
        return self.exchange.fetch_ticker(symbol)

    def create_order(self, symbol: str, side: str, amount: float) -> Optional[Dict]:
        """Create market order (or simulate in dry run mode)"""
        if self.dry_run:
            ticker = self.fetch_ticker(symbol)
            self._sim_net_position += amount if side.lower() == 'buy' else -amount
            return {
                'id': f'dry_run_{side}_{symbol}',
                'symbol': symbol,
                'side': side,
                'type': 'market',
                'amount': amount,
                'price': ticker['last'],
                'status': 'simulated',
                'dry_run': True
            }

        if settings.EXCHANGE == "hyperliquid":
            # Hyperliquid braucht für Market-Orders einen Referenzpreis (Slippage-Grenze)
            price = self.fetch_ticker(symbol)['last']
            return self.exchange.create_order(symbol, 'market', side, amount, price)
        return self.exchange.create_market_order(symbol, side, amount)

    def fetch_net_position(self, symbol: str) -> float:
        """Netto-Position in Contracts: positiv = Long, negativ = Short"""
        if self.dry_run:
            return self._sim_net_position
        positions = self.exchange.fetch_positions([symbol])
        return sum(
            (p.get('contracts') or 0) * (1 if p.get('side') == 'long' else -1)
            for p in positions
        )

    def adjust_for_position(self, side: str, amount: float) -> Optional[float]:
        """Perps: gleiche Richtung -> None (nicht nachlegen), Gegenrichtung -> Position schließen und drehen"""
        net = self.fetch_net_position(settings.SYMBOL)
        is_buy = side.lower() == 'buy'
        if (is_buy and net > 0) or (not is_buy and net < 0):
            return None
        return amount + abs(net)

    def place_protection(self, symbol: str, side: str, size: float, entry_price: float,
                         signal_bar: Dict) -> Dict[str, float]:
        """Setzt reduce-only SL/TP-Trigger für eine frisch eröffnete Position (Hyperliquid)"""
        stops = stop_prices(side, entry_price, signal_bar)
        if self.dry_run:
            self._sim_stops = stops
            return stops
        close_side = 'sell' if side.lower() == 'buy' else 'buy'
        for key, trigger in stops.items():
            self.exchange.create_order(symbol, 'market', close_side, size, trigger,
                                       params={key: trigger, 'reduceOnly': True})
        return stops

    def cancel_open_orders(self, symbol: str) -> None:
        """Entfernt verbliebene SL/TP-Trigger, damit sie keine neue Position treffen"""
        if self.dry_run:
            self._sim_stops = None
            return
        ids = [order['id'] for order in self.exchange.fetch_open_orders(symbol)]
        if ids:
            self.exchange.cancel_orders(ids, symbol)

    def check_simulated_stops(self, symbol: str) -> Optional[str]:
        """Dry-Run: schließt die simulierte Position, wenn der Preis SL/TP erreicht"""
        net = self._sim_net_position
        if not self.dry_run or not self._sim_stops or not net:
            return None
        price = self.fetch_ticker(symbol)['last']
        direction = 1 if net > 0 else -1
        sl, tp = self._sim_stops.get('stopLossPrice'), self._sim_stops.get('takeProfitPrice')
        hit_sl = sl is not None and direction * (price - sl) <= 0
        hit_tp = tp is not None and direction * (price - tp) >= 0
        if not (hit_sl or hit_tp):
            return None
        self.create_order(symbol, 'sell' if direction > 0 else 'buy', abs(net))
        self._sim_stops = None
        return 'stop_loss' if hit_sl else 'take_profit'

    def calculate_position_size(self, side: str, balance: Dict, ticker: Dict) -> float:
        """Calculate position size based on trade percentage"""
        base, quote = symbol_assets(settings.SYMBOL)
        # Perps: Long und Short werden beide aus der Margin (Quote) bemessen
        if side.lower() == 'buy' or settings.EXCHANGE == "hyperliquid":
            quote_available = balance.get(quote, 0)
            trade_amount_quote = max(quote_available * settings.TRADE_PERCENTAGE, 10)
            return trade_amount_quote / ticker['last']
        return balance.get(base, 0) * settings.TRADE_PERCENTAGE
