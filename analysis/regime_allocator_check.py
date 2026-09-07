"""Schlaegt die regimebasierte Gewichtung die feste 50/50-Aufteilung?

Gleiche Messlatte wie beim performance-basierten Allocator. Wenn sie die feste
Aufteilung nicht schlaegt, ist sie ebenfalls nur Komplexitaet.
"""
import sys

sys.path.insert(0, ".")

from src.allocator.allocator import AllocatorConfig, RegimeAllocator, RegimeAllocatorConfig
from src.backtest.engine import metrics
from src.backtest.portfolio import Leg, run_portfolio
from src.data.klines import fetch_klines
from src.strategies.reversion import ReversionStrategy
from src.strategies.trend import TrendStrategy
from src.utils.config import load_config
from src.utils.indicators import adx

cfg = load_config()
FIXED = AllocatorConfig(rebalance_days=10**6)

for sym in cfg.symbols:
    master = fetch_klines(sym, "15m", "2024-01-01")
    adx_series = adx(master, 14)

    def legs():
        return [Leg(TrendStrategy(), master, sym),
                Leg(ReversionStrategy(), fetch_klines(sym, "4h", "2024-01-01"), sym)]

    print(f"\n=== {sym} ===")
    print(f"{'Variante':<34} {'Return':>9} {'MaxDD':>8} {'avg R':>8} {'Calmar':>7}")
    print("-" * 70)

    b, _ = run_portfolio(legs(), master, cfg, 200.0, allocator_config=FIXED)
    m = metrics(b)
    print(f"{'fest 50/50 (Referenz)':<34} {m['return_pct']:>8.1f}% "
          f"{m['max_drawdown_pct']:>7.1f}% {m['avg_r']:>8.3f} {m['calmar']:>7.2f}")

    for low, high in [(20, 35), (15, 30), (25, 40)]:
        ra = RegimeAllocator("trend_ema", "reversion_bb",
                             RegimeAllocatorConfig(adx_low=low, adx_high=high))
        b, _ = run_portfolio(legs(), master, cfg, 200.0,
                             regime_allocator=ra, regime_series=adx_series)
        m = metrics(b)
        print(f"{f'Regime ADX {low}-{high}':<34} {m['return_pct']:>8.1f}% "
              f"{m['max_drawdown_pct']:>7.1f}% {m['avg_r']:>8.3f} {m['calmar']:>7.2f}")
