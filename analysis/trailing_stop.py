"""Bringt ein Trailing-Stop etwas?

Erwartung vorab (damit man sich das Ergebnis nicht hinterher zurechtlegt):
Ein Trailing-Stop sichert Gewinne, schneidet aber genau die langen Bewegungen ab,
aus denen bei dieser Strategie der gesamte Gewinn stammt. Plausibel ist also:
hoehere Winrate, kleinerer Drawdown, niedrigerer Gesamtertrag.

Getestet wird auf BTC und ETH gemeinsam - eine Verbesserung, die nur auf einem
Asset auftritt, ist keine.
"""
import sys

sys.path.insert(0, ".")

from src.backtest.engine import metrics, run_backtest
from src.data.klines import fetch_klines
from src.strategies.trend import TrendStrategy
from src.utils.config import load_config

VARIANTS = [None, 6.0, 4.0, 3.0, 2.0]

cfg = load_config()
data = {s: fetch_klines(s, "15m", "2024-01-01") for s in cfg.symbols}

print(f"{'Trailing':>12} {'Symbol':>9} {'Return':>9} {'MaxDD':>8} {'Winrate':>8} {'avg R':>8} {'Calmar':>7}")
print("-" * 68)
for trail in VARIANTS:
    label = "aus" if trail is None else f"{trail:.0f} ATR"
    for sym, df in data.items():
        b = run_backtest(df, TrendStrategy(), cfg, sym, "trend", trail_atr=trail)
        m = metrics(b)
        print(f"{label:>12} {sym:>9} {m['return_pct']:>8.1f}% {m['max_drawdown_pct']:>7.1f}% "
              f"{m['winrate_pct']:>7.1f}% {m['avg_r']:>8.3f} {m['calmar']:>7.2f}")
    print()
