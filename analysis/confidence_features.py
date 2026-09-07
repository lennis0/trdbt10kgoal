"""Welche Merkmale sagen den Erfolg eines Trades voraus?

Vorgehen, damit es keine Kurvenanpassung wird:
1. Merkmale werden in der Strategie definiert, BEVOR man die Ergebnisse ansieht.
2. Getestet wird auf In-Sample. Was dort nicht trennt, fliegt raus.
3. Was trennt, muss es out-of-sample nochmal tun. Sonst war es Zufall.
4. BTC und ETH werden gepoolt - 126 Trades allein sind zu wenig fuer eine Aussage.

Waehrend dieser Messung laeuft die Strategie mit confidence 1.0 fuer alle Trades,
damit die Positionsgroesse das Ergebnis nicht verzerrt.
"""
import sys

import pandas as pd

sys.path.insert(0, ".")

from src.backtest.engine import run_backtest
from src.data.klines import fetch_klines
from src.strategies.trend import TrendStrategy
from src.utils.config import load_config

SPLIT = "2025-07-01"
FEATURES = ["adx", "adx_slope", "dist_long_atr", "atr_rel", "trend_align"]


class FlatConfidence(TrendStrategy):
    """Gleiche Signale, aber confidence konstant 1.0."""
    def signal(self, df, i, symbol):
        sig = super().signal(df, i, symbol)
        if sig is None:
            return None
        return type(sig)(**{**sig.__dict__, "confidence": 1.0})


def collect() -> pd.DataFrame:
    cfg, rows = load_config(), []
    for sym in cfg.symbols:
        df = fetch_klines(sym, "15m", "2024-01-01")
        broker = run_backtest(df, FlatConfidence(), cfg, sym, "trend")
        for t in broker.closed_trades:
            rows.append({"symbol": sym, "entry": t.entry_time, "r": t.r_multiple, **t.features})
    return pd.DataFrame(rows)


def report(df: pd.DataFrame, feature: str, q: int = 3) -> pd.DataFrame:
    """Trades nach Merkmal in Quantile teilen und avg_R vergleichen."""
    d = df.dropna(subset=[feature]).copy()
    if d[feature].nunique() <= 2:
        d["bucket"] = d[feature]
    else:
        d["bucket"] = pd.qcut(d[feature], q, duplicates="drop")
    return d.groupby("bucket", observed=True).agg(
        trades=("r", "count"), avg_r=("r", "mean"), winrate=("r", lambda s: (s > 0).mean() * 100)
    ).round(3)


if __name__ == "__main__":
    trades = collect()
    ins = trades[trades["entry"] < SPLIT]
    out = trades[trades["entry"] >= SPLIT]
    print(f"Trades gesamt {len(trades)} | In-Sample {len(ins)} | Out-of-Sample {len(out)}")
    print(f"Basis avg_R: gesamt {trades['r'].mean():.3f} | in {ins['r'].mean():.3f} | out {out['r'].mean():.3f}\n")

    for f in FEATURES:
        print(f"### {f}")
        print("IN-SAMPLE"); print(report(ins, f))
        print("OUT-OF-SAMPLE"); print(report(out, f)); print()
