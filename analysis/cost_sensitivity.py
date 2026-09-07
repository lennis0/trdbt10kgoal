"""Kosten-Sensitivitaet: wie viel der Verlust kommt von der Strategie, wie viel
von der Ausfuehrung?

Derselbe Backtest, nur mit verschiedenen Gebuehrensaetzen. Die 0%-Zeile zeigt die
rohe Handelsidee. Was zwischen 0% und dem realen Satz verloren geht, ist reine
Ausfuehrungsfrage - und die loest man mit Order-Typ und Handelsfrequenz,
nicht mit anderen EMA-Laengen.
"""
import sys
from dataclasses import replace

sys.path.insert(0, ".")

from src.backtest.engine import metrics, run_backtest
from src.data.klines import fetch_klines
from src.strategies.trend import TrendStrategy
from src.utils.config import Costs, load_config

SCENARIOS = [
    ("ohne Gebuehren (rohe Idee)", 0.0,     0.0),
    ("Futures Maker  0.020%",      0.0002,  1.0),
    ("Futures Taker  0.055%",      0.00055, 2.0),
    ("Spot Standard  0.100%",      0.0010,  2.0),
]

cfg = load_config()
df = fetch_klines("BTCUSDT", "15m", "2024-01-01")

print(f"{'Szenario':<28} {'Return':>9} {'MaxDD':>8} {'avg R':>8} {'Gebuehren':>11} {'Endkapital':>11}")
print("-" * 80)
for label, fee, slip in SCENARIOS:
    c = replace(cfg, costs=Costs(taker_fee=fee, slippage_bps=slip))
    b = run_backtest(df, TrendStrategy(), c, "BTCUSDT", "trend")
    m = metrics(b)
    print(f"{label:<28} {m['return_pct']:>8.1f}% {m['max_drawdown_pct']:>7.1f}% "
          f"{m['avg_r']:>8.3f} {m['total_fees']:>10.2f} {m['equity']:>10.2f}")
