from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Literal, Optional
import secrets


class Settings(BaseSettings):
    # Trading Mode
    DRY_RUN: bool = True
    
    # Exchange (binance = Spot, hyperliquid = Perps)
    EXCHANGE: Literal["binance", "hyperliquid"] = "binance"

    # Hyperliquid (API-Wallet-Adresse + Private Key)
    HYPERLIQUID_WALLET_ADDRESS: str = ""
    HYPERLIQUID_PRIVATE_KEY: str = ""

    # Binance
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    
    # Database
    DATABASE_URL: str = "sqlite:///./data/trading.db"
    
    # Auth
    JWT_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(32), min_length=32)
    API_KEYS: str = ""  # Format: name1:secret1,name2:secret2
    # Dashboard-Login; leeres Passwort = Login deaktiviert
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    
    # Bot Config
    ACTIVE_STRATEGY: str = "obv_vwap"
    TRADE_PERCENTAGE: float = 0.10
    TRAILING_STOP_PERCENT: float = 0.02
    TAKE_PROFIT_PERCENT: float = 0.05
    # Stop = STOP_ATR_MULTIPLE x ATR der Signal-Kerze (0 = feste TRAILING_STOP_PERCENT/TAKE_PROFIT_PERCENT)
    STOP_ATR_MULTIPLE: float = Field(default=3.0, ge=0)
    # Take-Profit bei ATR-Stops als Vielfaches des Stop-Abstands (0 = kein Take-Profit)
    TAKE_PROFIT_R: float = Field(default=0.0, ge=0)
    SYMBOL: str = "BTC/USDT"
    # Signal nur bei Volumen >= Faktor x Durchschnitt der letzten 20 Kerzen (0 = aus)
    VOLUME_FILTER: float = Field(default=0.0, ge=0)
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    @field_validator("ADMIN_PASSWORD")
    @classmethod
    def _admin_password_strong(cls, value: str) -> str:
        """Leer (deaktiviert) oder mindestens 12 Zeichen."""
        if value and len(value) < 12:
            raise ValueError("ADMIN_PASSWORD muss mindestens 12 Zeichen lang sein")
        return value

    @field_validator("API_KEYS")
    @classmethod
    def _api_keys_strong(cls, value: str) -> str:
        """Jeder API-Key-Secret mindestens 16 Zeichen – der Key-Pfad hat keine Login-Sperre."""
        for pair in filter(None, value.split(",")):
            if len(pair.split(":", 1)[-1].strip()) < 16:
                raise ValueError("Jeder Secret in API_KEYS muss mindestens 16 Zeichen lang sein")
        return value

    @property
    def parsed_api_keys(self) -> dict:
        """Parse API keys from comma-separated name:secret pairs"""
        if not self.API_KEYS:
            return {}
        keys = {}
        for pair in self.API_KEYS.split(","):
            if ":" in pair:
                name, secret = pair.split(":", 1)
                keys[name.strip()] = secret.strip()
        return keys
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
