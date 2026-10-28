"""Per Dashboard änderbare Bot-Settings: Validierung und Übernahme in die laufenden Settings.

Bot und API lesen `settings` bei jeder Verwendung, daher wirken Änderungen ohne Neustart.
In der DB (ConfigRepository) liegen sie nur, damit sie einen Neustart überleben.
"""
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.bot.strategies import STRATEGIES
from app.config import settings
from app.db.repository import ConfigRepository

# API-Schlüssel -> Feld in Settings
FIELDS = {
    "active_strategy": "ACTIVE_STRATEGY",
    "trade_percentage": "TRADE_PERCENTAGE",
    "trailing_stop_percent": "TRAILING_STOP_PERCENT",
    "take_profit_percent": "TAKE_PROFIT_PERCENT",
}


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_strategy: Optional[str] = None
    trade_percentage: Optional[float] = Field(default=None, gt=0, le=1)
    trailing_stop_percent: Optional[float] = Field(default=None, gt=0, lt=1)
    take_profit_percent: Optional[float] = Field(default=None, ge=0, lt=1)

    @field_validator("active_strategy")
    @classmethod
    def _known_strategy(cls, value: Optional[str]) -> Optional[str]:
        """Nur registrierte Strategien, sonst scheitert der Bot-Loop beim Umschalten."""
        if value is not None and value not in STRATEGIES:
            raise ValueError(f"Unbekannte Strategie, erlaubt: {list(STRATEGIES)}")
        return value


def apply_config(update: ConfigUpdate) -> Dict[str, object]:
    """Setzt die übergebenen Werte auf die laufenden Settings und liefert sie zurück."""
    values = update.model_dump(exclude_none=True)
    for key, value in values.items():
        setattr(settings, FIELDS[key], value)
    return values


def load_saved_config(db: Session) -> None:
    """Gespeicherte Overrides beim Start übernehmen; ungültige Altwerte werden übersprungen."""
    for key, raw in ConfigRepository(db).get_all().items():
        if key not in FIELDS:
            continue
        try:
            apply_config(ConfigUpdate(**{key: raw}))
        except ValidationError:
            print(f"⚠️ Gespeicherter Config-Wert ignoriert: {key}={raw!r}")
