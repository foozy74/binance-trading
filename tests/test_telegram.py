from unittest.mock import MagicMock

import pytest
import requests

from app.config import settings
from app.services import telegram as telegram_module
from app.services.telegram import TelegramService

TOKEN = "123456:geheimer-bot-token"


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "42")
    return TelegramService()


def _response(status, body):
    response = MagicMock(status_code=status)
    response.json.return_value = body
    return response


def test_network_error_does_not_log_token(service, monkeypatch, capsys):
    error = requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage")
    monkeypatch.setattr(telegram_module.requests, "post", MagicMock(side_effect=error))

    assert service.send_message("hi") is False
    out = capsys.readouterr().out
    assert TOKEN not in out
    assert "ConnectionError" in out


def test_api_error_is_logged_with_description(service, monkeypatch, capsys):
    response = _response(400, {"ok": False, "description": "Bad Request: chat not found"})
    monkeypatch.setattr(telegram_module.requests, "post", MagicMock(return_value=response))

    assert service.send_message("hi") is False
    out = capsys.readouterr().out
    assert "400" in out and "chat not found" in out


def test_success_posts_chat_id_and_text(service, monkeypatch):
    post = MagicMock(return_value=_response(200, {"ok": True}))
    monkeypatch.setattr(telegram_module.requests, "post", post)

    assert service.send_message("hi") is True
    assert post.call_args.kwargs["json"]["chat_id"] == "42"
    assert post.call_args.kwargs["json"]["text"] == "hi"


def test_trade_notification_uses_symbol_assets(service, monkeypatch):
    sent = MagicMock(return_value=True)
    monkeypatch.setattr(service, "send_message", sent)

    service.send_trade_notification({"side": "sell", "symbol": "ETH/USDC:USDC", "amount": 0.5,
                                     "price": 3000, "usdt_value": 1500, "stop_loss": 3100})

    text = sent.call_args.args[0]
    assert "0.50000000 ETH" in text and "1500.00 USDC" in text and "Stop-Loss: 3100.00 USDC" in text
    assert "BTC" not in text and "USDT" not in text
