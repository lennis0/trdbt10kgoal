"""Bringt der Allocator ueberhaupt etwas?

Die Frage, die man sich stellen MUSS, bevor man ihn einbaut: schlaegt er die
dumme Variante? Vergleich gegen feste Gewichte - wenn die feste Aufteilung
gewinnt, ist der Allocator kein Fortschritt, sondern teure Komplexitaet.
"""
import sys

sys.path.insert(0, ".")

from src.allocator.allocator import AllocatorConfig
from src.backtest.engine import metrics
from src.backtest.portfolio import Leg, run_portfolio
from src.data.klines import fetch_klines
from src.strategies.reversion import ReversionStrategy
from src.strategies.trend import TrendStrategy
from src.utils.config import load_config

cfg = load_config()


def build_legs(sym):
    return [Leg(TrendStrategy(), fetch_klines(sym, "15m", "2024-01-01"), sym),
            Leg(ReversionStrategy(), fetch_klines(sym, "4h", "2024-01-01"), sym)]


VARIANTS = [
    ("fest 50/50 (Referenz)", AllocatorConfig(rebalance_days=10**6)),
    ("Allocator 90d Fenster", AllocatorConfig(lookback_days=90, rebalance_days=7)),
    ("Allocator 180d Fenster", AllocatorConfig(lookback_days=180, rebalance_days=14)),
    ("Allocator 365d Fenster", AllocatorConfig(lookback_days=365, rebalance_days=30)),
    ("Allocator 365d, min 20 Trades",
     AllocatorConfig(lookback_days=365, rebalance_days=30, min_trades=20)),
]

for sym in cfg.symbols:
    master = fetch_klines(sym, "15m", "2024-01-01")
    print(f"\n=== {sym} ===")
    print(f"{'Variante':<30} {'Return':>9} {'MaxDD':>8} {'Trades':>7} {'avg R':>8}")
    print("-" * 66)
    for label, acfg in VARIANTS:
        broker, _ = run_portfolio(build_legs(sym), master, cfg, 200.0, allocator_config=acfg)
        m = metrics(broker)
        print(f"{label:<30} {m['return_pct']:>8.1f}% {m['max_drawdown_pct']:>7.1f}% "
              f"{m['trades']:>7} {m['avg_r']:>8.3f}")
