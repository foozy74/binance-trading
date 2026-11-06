from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from app.config import settings
import time

# Trading Metrics
bot_trades_total = Counter(
    'bot_trades_total',
    'Total number of trades executed',
    ['side', 'dry_run']
)

bot_signals_total = Counter(
    'bot_signals_total',
    'Total number of signals generated',
    ['signal_type', 'strategy']
)

bot_uptime_seconds = Gauge(
    'bot_uptime_seconds',
    'Bot uptime in seconds'
)

# Track start time
START_TIME = time.time()


def update_uptime():
    """Update uptime metric"""
    bot_uptime_seconds.set(time.time() - START_TIME)


def get_metrics():
    """Generate Prometheus metrics"""
    update_uptime()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
