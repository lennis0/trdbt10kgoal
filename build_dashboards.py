"""Erzeugt die Dashboards fuer beide Bots. Aufruf: python build_dashboards.py"""
import sys

sys.path.insert(0, ".")

from src.dashboard.build import build
from src.strategies.reversion import ReversionStrategy
from src.strategies.trend import TrendStrategy

JOBS = [
    ("BTCUSDT", "15m", TrendStrategy(), "trend",
     {"ema_fast": "EMA 21", "ema_slow": "EMA 55"}),
    ("ETHUSDT", "15m", TrendStrategy(), "trend",
     {"ema_fast": "EMA 21", "ema_slow": "EMA 55"}),
    ("BTCUSDT", "4h", ReversionStrategy(), "reversion",
     {"bb_lower": "BB unten", "bb_mid": "BB Mitte", "bb_upper": "BB oben"}),
    ("ETHUSDT", "4h", ReversionStrategy(), "reversion",
     {"bb_lower": "BB unten", "bb_mid": "BB Mitte", "bb_upper": "BB oben"}),
]

for symbol, tf, strat, portfolio, overlays in JOBS:
    path = build(symbol, tf, strat, portfolio, overlays)
    print(f"  {path.name}  ({path.stat().st_size // 1024} KB)")
