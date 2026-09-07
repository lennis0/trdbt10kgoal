"""Ein Bot, ein Wallet, mehrere Strategien, ein Allocator.

Aufbau:
- EIN PaperBroker = ein gemeinsames Wallet. Alle Strategien teilen sich das Kapital.
- Jede Strategie darf gleichzeitig eine eigene Position halten. Sie behindern sich
  nicht; Bot A kann long im Trend sein, waehrend Bot B eine Gegenbewegung handelt.
- Der Allocator setzt woechentlich die Gewichte. Das Gewicht geht direkt in die
  Positionsgroesse: Risiko = Equity * base_risk * Gewicht. Eine Strategie mit
  Gewicht 0.05 handelt also weiter, riskiert aber nur ein Zwanzigstel.

Multi-Timeframe: Bot A laeuft auf 15m, Bot B auf 4h. Die 15m-Kerzen sind die
Uhr des Systems - Stops werden auf 15m geprueft, auch fuer 4h-Positionen. Das ist
genauer als eine Pruefung auf 4h-Kerzen, weil ein Stop innerhalb einer 4h-Kerze
getroffen werden kann, ohne dass man es an ihren Extremwerten sehen wuerde.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.allocator.allocator import Allocator, AllocatorConfig
from src.core import Side
from src.journal.journal import Journal
from src.paper.broker import PaperBroker
from src.risk.sizing import RiskManager
from src.strategies.base import Strategy
from src.utils.config import Config
from src.utils.indicators import regime


@dataclass
class Leg:
    """Eine Strategie mit ihrem eigenen Timeframe und Datensatz."""
    strategy: Strategy
    df: pd.DataFrame          # Rohdaten in ihrem Timeframe
    symbol: str

    def __post_init__(self) -> None:
        self.data = self.strategy.prepare(self.df)
        self.data["regime"] = regime(self.df)
        # Zuordnung Zeitstempel -> Index, um beim Durchlauf der Master-Uhr zu
        # erkennen, wann eine Kerze dieser Strategie schliesst.
        self.index_at = {ts: i for i, ts in enumerate(self.data.index)}
        self.pending = None


def run_portfolio(
    legs: list[Leg],
    master: pd.DataFrame,
    config: Config,
    start_equity: float = 200.0,
    journal: Journal | None = None,
    allocator_config: AllocatorConfig | None = None,
) -> tuple[PaperBroker, Allocator]:
    broker = PaperBroker(
        "portfolio", start_equity,
        taker_fee=config.costs.taker_fee,
        slippage_bps=config.costs.slippage_bps,
    )
    risk = RiskManager(config.risk)
    allocator = Allocator([leg.strategy.name for leg in legs],
                          allocator_config or AllocatorConfig())

    for i in range(len(master)):
        row = master.iloc[i]
        ts = master.index[i]
        high, low, open_ = float(row["high"]), float(row["low"]), float(row["open"])

        risk.start_day(ts.date(), broker.equity)
        broker.check_stops(ts, high, low)
        allocator.maybe_rebalance(ts, broker.closed_trades)

        # 1. Aufgeschobene Signale ausfuehren - auf dem Open dieser Kerze
        for leg in legs:
            sig = leg.pending
            if sig is None:
                continue
            leg.pending = None
            name = leg.strategy.name

            # Nur die eigene Gegenposition schliessen, nicht die der anderen Strategie
            for tid, t in list(broker.open_trades.items()):
                if t.strategy == name and t.side is not sig.side:
                    broker.close_trade(tid, ts, open_, reason="signal")

            if any(t.strategy == name for t in broker.open_trades.values()):
                continue
            if risk.check_kill_switch(broker.equity):
                continue

            stop = open_ + (sig.stop - sig.features["close"])
            weight = allocator.weight(name)
            try:
                sizing = risk.size_for(broker.equity, open_, stop, weight)
            except ValueError:
                continue
            if sizing.size <= 0:
                continue
            broker.open_trade(
                ts, leg.symbol, sig.side, open_, sizing.size, stop,
                weight, name, features=sig.features,
                regime=str(leg.data.iloc[leg.index_at[sig.timestamp]]["regime"]),
            )

        # 2. Neue Signale einsammeln - nur bei Strategien, deren Kerze jetzt schliesst
        for leg in legs:
            idx = leg.index_at.get(ts)
            if idx is None:
                continue
            sig = leg.strategy.signal(leg.data, idx, leg.symbol)
            if sig is not None and sig.side is not Side.FLAT:
                leg.pending = sig

    last_ts, last_close = master.index[-1], float(master.iloc[-1]["close"])
    for tid in list(broker.open_trades):
        broker.close_trade(tid, last_ts, last_close, reason="end")

    if journal is not None:
        journal.record_many(broker.closed_trades)
    return broker, allocator
