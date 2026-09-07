"""Regime-Filter: wie streng muss der ADX-Filter sein?

Methodisch wichtig: das hier ist eine Parametersuche, und genau die kann man sich
selbst schoenrechnen. Darum wird geteilt:

  In-Sample  (Optimierung):  2024-01-01 bis 2025-06-30
  Out-of-Sample (Pruefung):  2025-07-01 bis heute

Der beste In-Sample-Wert wird NICHT als Ergebnis verkauft. Nur was out-of-sample
haelt, zaehlt. Faellt der beste Wert out-of-sample zusammen, war es Overfitting -
und das ist ein Ergebnis, kein Misserfolg.
"""
import sys

sys.path.insert(0, ".")

from src.backtest.engine import metrics, run_backtest
from src.data.klines import fetch_klines
from src.strategies.trend import TrendStrategy
from src.utils.config import load_config

SPLIT = "2025-07-01"
GRID = [0, 15, 20, 25, 30, 35, 40]

cfg = load_config()
df = fetch_klines("BTCUSDT", "15m", "2024-01-01")
in_sample, out_sample = df.loc[:SPLIT], df.loc[SPLIT:]
print(f"In-Sample: {len(in_sample)} Kerzen | Out-of-Sample: {len(out_sample)} Kerzen\n")

def run(data, adx_min):
    b = run_backtest(data, TrendStrategy(adx_min=adx_min), cfg, "BTCUSDT", "trend")
    return metrics(b)

print(f"{'ADX-Filter':>10} | {'IN: Return':>11} {'MaxDD':>7} {'Trades':>7} {'Calmar':>7} "
      f"| {'OUT: Return':>12} {'MaxDD':>7} {'Trades':>7} {'avg R':>7}")
print("-" * 96)
rows = []
for adx_min in GRID:
    i, o = run(in_sample, adx_min), run(out_sample, adx_min)
    rows.append((adx_min, i, o))
    print(f"{adx_min:>10} | {i['return_pct']:>10.1f}% {i['max_drawdown_pct']:>6.1f}% "
          f"{i['trades']:>7} {i['calmar']:>7.2f} | {o['return_pct']:>11.1f}% "
          f"{o['max_drawdown_pct']:>6.1f}% {o['trades']:>7} {o['avg_r']:>7.3f}")

# Mindest-Trade-Zahl ist Pflicht: Calmar auf 3 Trades ist eine Zufallszahl.
# Ohne diese Bedingung waehlt die Suche zuverlaessig den unbrauchbarsten Wert.
MIN_TRADES = 50
candidates = [r for r in rows if r[1]["trades"] >= MIN_TRADES]
best = max(candidates, key=lambda r: r[1]["calmar"])
print(f"\nBester In-Sample-Wert nach Calmar: ADX >= {best[0]}")
print(f"  In-Sample:     {best[1]['return_pct']:+.1f}%  (Calmar {best[1]['calmar']})")
print(f"  Out-of-Sample: {best[2]['return_pct']:+.1f}%  (avg R {best[2]['avg_r']})")
print("  -> Haelt der Vorteil out-of-sample, oder war es Kurvenanpassung?")
