"""Backtest-Engine.

Laeuft Kerze fuer Kerze und nutzt exakt dieselben Bausteine wie das spaetere
Paper-Trading: PaperBroker, RiskManager, Journal. Genau das macht die Ergebnisse
vergleichbar - ein Unterschied zwischen Backtest und Paper kommt dann von den
Marktdaten, nicht von zwei verschiedenen Implementierungen.

Zwei Regeln gegen Selbstbetrug:
1. Das Signal einer Kerze wird erst auf der NAECHSTEN Kerze ausgefuehrt (open).
   Sonst handelt man auf einem Schlusskurs, den man zum Zeitpunkt der Entscheidung
   noch nicht kennen konnte.
2. Stops werden vor neuen Signalen geprueft. Innerhalb einer Kerze weiss man nicht,
   was zuerst kam - die pessimistische Annahme ist, dass der Stop zuerst kam.
"""
from __future__ import annotations

import pandas as pd

from src.core import Side
from src.journal.journal import Journal
from src.paper.broker import PaperBroker
from src.risk.sizing import RiskManager
from src.strategies.base import Strategy
from src.utils.config import Config
from src.utils.indicators import regime


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    config: Config,
    symbol: str,
    portfolio: str = "trend",
    journal: Journal | None = None,
    shadow: bool = False,
) -> PaperBroker:
    data = strategy.prepare(df)
    data["regime"] = regime(df)

    start_equity = config.portfolios.get(portfolio, {}).get("start_equity", 10_000)
    broker = PaperBroker(
        portfolio, start_equity,
        taker_fee=config.costs.taker_fee,
        slippage_bps=config.costs.slippage_bps,
    )
    risk = RiskManager(config.risk)

    pending = None   # Signal der Vorkerze, wird auf dem naechsten Open ausgefuehrt

    for i in range(len(data)):
        row = data.iloc[i]
        ts = data.index[i]

        risk.start_day(ts.date(), broker.equity)

        # 1. Stops zuerst - pessimistische Annahme
        broker.check_stops(ts, float(row["high"]), float(row["low"]))

        # 2. Aufgeschobenes Signal auf dem Open ausfuehren
        if pending is not None:
            sig = pending
            pending = None
            price = float(row["open"])

            # Gegenposition schliessen, bevor eine neue eroeffnet wird
            for tid, t in list(broker.open_trades.items()):
                if t.side is not sig.side:
                    broker.close_trade(tid, ts, price, reason="signal")

            if not broker.open_trades and not risk.check_kill_switch(broker.equity):
                # Stop relativ zum tatsaechlichen Einstiegskurs verschieben
                offset = sig.stop - sig.features["close"]
                stop = price + offset
                try:
                    sizing = risk.size_for(broker.equity, price, stop, sig.confidence)
                    broker.open_trade(
                        ts, symbol, sig.side, price, sizing.size, stop,
                        sig.confidence, strategy.name, shadow=shadow,
                        features=sig.features, regime=str(row["regime"]),
                    )
                except Exception:
                    pass   # Sizing unmoeglich (Stop-Distanz 0) -> Signal verfaellt

        # 3. Neues Signal einsammeln, Ausfuehrung naechste Kerze
        sig = strategy.signal(data, i, symbol)
        if sig is not None and sig.side is not Side.FLAT:
            pending = sig

    # Offene Position am Ende zum letzten Kurs schliessen, sonst fehlt sie in der Statistik
    for tid in list(broker.open_trades):
        broker.close_trade(tid, data.index[-1], float(data.iloc[-1]["close"]), reason="end")

    if journal is not None:
        journal.record_many(broker.closed_trades)
    return broker


def metrics(broker: PaperBroker, periods_per_year: float = 365 * 24 * 4) -> dict:
    """Kennzahlen. Calmar ist laut CLAUDE.md die Hauptmetrik, Sharpe steht daneben."""
    summary = broker.summary()
    curve = pd.Series({ts: eq for ts, eq in broker.equity_curve})

    sharpe = 0.0
    if len(curve) > 2:
        returns = curve.pct_change().dropna()
        if returns.std() > 0:
            trades_per_year = periods_per_year / max(len(curve), 1)
            sharpe = returns.mean() / returns.std() * (len(curve) ** 0.5) * 0 + \
                     returns.mean() / returns.std() * (min(trades_per_year, len(curve)) ** 0.5)

    mdd = summary["max_drawdown_pct"] / 100
    summary["sharpe"] = round(float(sharpe), 2)
    summary["calmar"] = round(summary["return_pct"] / 100 / mdd, 2) if mdd > 0 else 0.0
    return summary
