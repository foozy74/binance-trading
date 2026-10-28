import pytest
from pydantic import ValidationError

from app.bot.runtime_config import ConfigUpdate, apply_config, load_saved_config
from app.bot.strategies.macd_crossover import MACDCrossoverStrategy
from app.bot.trader import TradingBot
from app.config import settings
from app.db.repository import ConfigRepository


@pytest.fixture(autouse=True)
def restore_settings(monkeypatch):
    """Tests ändern die globalen Settings – monkeypatch stellt die Originalwerte wieder her."""
    for field in ("ACTIVE_STRATEGY", "TRADE_PERCENTAGE", "TRAILING_STOP_PERCENT", "TAKE_PROFIT_PERCENT"):
        monkeypatch.setattr(settings, field, getattr(settings, field))


def test_apply_config_sets_only_given_values():
    before = settings.TRADE_PERCENTAGE
    assert apply_config(ConfigUpdate(active_strategy="macd_crossover")) == {"active_strategy": "macd_crossover"}
    assert settings.ACTIVE_STRATEGY == "macd_crossover"
    assert settings.TRADE_PERCENTAGE == before


@pytest.mark.parametrize("values", [
    {"active_strategy": "gibt_es_nicht"},
    {"trade_percentage": 0},
    {"trade_percentage": 1.5},
    {"trailing_stop_percent": -0.01},
    {"take_profit_percent": 1},
    {"unbekannt": 1},
])
def test_invalid_config_rejected(values):
    with pytest.raises(ValidationError):
        ConfigUpdate(**values)


def test_load_saved_config_applies_and_skips_invalid(db_session):
    repo = ConfigRepository(db_session)
    repo.set("active_strategy", "rsi_divergence")
    repo.set("trade_percentage", "0.2")
    repo.set("take_profit_percent", "kaputt")
    before = settings.TAKE_PROFIT_PERCENT

    load_saved_config(db_session)

    assert settings.ACTIVE_STRATEGY == "rsi_divergence"
    assert settings.TRADE_PERCENTAGE == 0.2
    assert settings.TAKE_PROFIT_PERCENT == before


def test_bot_switches_strategy_on_change():
    bot = TradingBot()
    settings.ACTIVE_STRATEGY = "macd_crossover"
    bot._sync_strategy()
    assert isinstance(bot.strategy, MACDCrossoverStrategy)
