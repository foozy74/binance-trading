import requests
from typing import Optional
from app.config import settings
from app.services.exchange import symbol_assets


class TelegramService:
    """Service for sending Telegram notifications"""
    
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
    
    def send_message(self, text: str) -> bool:
        """Send message to Telegram chat"""
        if not self.enabled:
            return False

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
        except requests.RequestException as e:
            # requests nennt die URL samt Bot-Token in der Fehlermeldung – nie ungefiltert loggen
            print(f"❌ Telegram error: {type(e).__name__}: {str(e).replace(self.token, '***')}")
            return False

        if response.status_code != 200:
            try:
                description = response.json().get("description", "")
            except ValueError:
                description = ""
            print(f"❌ Telegram error: HTTP {response.status_code} {description}")
            return False
        return True
    
    def send_trade_notification(self, trade_data: dict) -> bool:
        """Send trade execution notification"""
        side = trade_data.get('side', 'unknown').upper()
        symbol = trade_data.get('symbol', 'unknown')
        amount = trade_data.get('amount', 0)
        price = trade_data.get('price', 0)
        usdt_value = trade_data.get('usdt_value', 0)
        stop_loss = trade_data.get('stop_loss')
        take_profit = trade_data.get('take_profit')
        is_dry_run = trade_data.get('is_dry_run', False)
        base, quote = symbol_assets(symbol) if "/" in symbol else ("", "")
        
        mode_text = "🧪 DRY RUN" if is_dry_run else "✅ LIVE"
        
        message = (
            f"{mode_text}\n\n"
            f"📢 Trade ausgeführt!\n"
            f"💰 Aktion: {side}\n"
            f"📈 Symbol: {symbol}\n"
            f"🔹 Menge: {amount:.8f} {base}\n"
            f"💵 Wert: {usdt_value:.2f} {quote}\n"
            f"💹 Preis: {price:.2f} {quote}\n"
        )
        
        if stop_loss:
            message += f"📌 Stop-Loss: {stop_loss:.2f} {quote}\n"
        if take_profit:
            message += f"📌 Take-Profit: {take_profit:.2f} {quote}\n"
        
        return self.send_message(message)
    
    def send_signal_notification(self, signal: str, symbol: str, confidence: Optional[float] = None) -> bool:
        """Send signal notification"""
        emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(signal, "⚪")
        confidence_text = f"({confidence:.0%} Confidence)" if confidence else ""
        
        message = (
            f"{emoji} Signal Update\n\n"
            f"📈 Symbol: {symbol}\n"
            f"📊 Signal: {signal} {confidence_text}\n"
        )
        
        return self.send_message(message)
