"""Paper-Broker: simuliert Fills, Gebuehren und Slippage.

Wird sowohl vom Backtest als auch vom Paper-Trading genutzt - identische Logik,
darum sind die Ergebnisse vergleichbar. Das ist der ganze Grund fuer diese Klasse.

Grundregel: immer konservativ fuellen. Ein zu pessimistischer Backtest kostet dich
eine Strategie, ein zu optimistischer kostet dich Geld.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from src.core import Side, Trade


class InsufficientEquity(Exception):
    pass


class PaperBroker:
    """Ein virtuelles Wallet. Pro Bot wird eine Instanz angelegt."""

    def __init__(
        self,
        name: str,
        start_equity: float = 10_000.0,
        taker_fee: float = 0.00055,
        slippage_bps: float = 2.0,
    ) -> None:
        self.name = name
        self.equity = start_equity
        self.start_equity = start_equity
        self.taker_fee = taker_fee
        self.slippage_bps = slippage_bps / 10_000.0

        self.open_trades: dict[str, Trade] = {}
        self.closed_trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, float]] = []

    # -- Fill-Simulation ---------------------------------------------------

    def _fill_price(self, price: float, side: Side, opening: bool) -> float:
        """Slippage geht immer gegen uns - beim Oeffnen und beim Schliessen."""
        adverse = 1 if (side is Side.LONG) == opening else -1
        return price * (1 + adverse * self.slippage_bps)

    def _fee(self, price: float, size: float) -> float:
        return abs(price * size) * self.taker_fee

    # -- Orders ------------------------------------------------------------

    def open_trade(
        self,
        timestamp: datetime,
        symbol: str,
        side: Side,
        price: float,
        size: float,
        stop: float,
        confidence: float,
        strategy: str,
        shadow: bool = False,
        features: dict[str, float] | None = None,
        regime: str = "",
    ) -> Trade:
        if side is Side.FLAT:
            raise ValueError("FLAT ist kein Trade")

        fill = self._fill_price(price, side, opening=True)
        fee = self._fee(fill, size)

        if not shadow and fee > self.equity:
            raise InsufficientEquity(f"{self.name}: Gebuehr {fee:.2f} > Equity {self.equity:.2f}")

        trade = Trade(
            trade_id=uuid.uuid4().hex[:12],
            strategy=strategy,
            symbol=symbol,
            side=side,
            entry_time=timestamp,
            entry_price=fill,
            size=size,
            stop=stop,
            initial_stop=stop,
            confidence=confidence,
            portfolio=self.name,
            shadow=shadow,
            features=features or {},
            regime=regime,
        )
        trade.fees = fee
        trade.slippage = abs(fill - price) * size
        self.open_trades[trade.trade_id] = trade
        return trade

    def close_trade(
        self, trade_id: str, timestamp: datetime, price: float, reason: str = "signal"
    ) -> Trade:
        trade = self.open_trades.pop(trade_id)
        fill = self._fill_price(price, trade.side, opening=False)

        trade.exit_time = timestamp
        trade.exit_price = fill
        trade.exit_reason = reason
        trade.fees += self._fee(fill, trade.size)
        trade.slippage += abs(fill - price) * trade.size

        if not trade.shadow:
            self.equity += trade.pnl
        self.closed_trades.append(trade)
        self.equity_curve.append((timestamp, self.equity))
        return trade

    # -- Bar-Verarbeitung --------------------------------------------------

    def trail_stops(self, high: float, low: float, atr: float, distance: float) -> None:
        """Zieht Stops nach, sobald der Kurs zugunsten der Position laeuft.

        Der Stop wird NUR in Gewinnrichtung verschoben, nie zurueck. Sonst wuerde
        man das Anfangsrisiko nachtraeglich vergroessern - der klassische Weg, aus
        einem kleinen Verlust einen grossen zu machen.
        """
        if atr <= 0 or distance <= 0:
            return
        for t in self.open_trades.values():
            if t.side is Side.LONG:
                t.stop = max(t.stop, high - distance * atr)
            else:
                t.stop = min(t.stop, low + distance * atr)

    def check_stops(self, timestamp: datetime, high: float, low: float) -> list[Trade]:
        """Prueft Stops gegen High/Low der Kerze.

        Konservative Annahme: wird der Stop innerhalb der Kerze beruehrt, gilt er als
        ausgeloest - zum Stop-Preis, nicht besser. Bei Gap-Opens waere der echte Fill
        schlechter; das unterschaetzt Verluste leicht und ist der bekannte Schwachpunkt
        einer Kerzen-basierten Simulation.
        """
        hit = []
        for tid, t in list(self.open_trades.items()):
            touched = low <= t.stop if t.side is Side.LONG else high >= t.stop
            if touched:
                hit.append(self.close_trade(tid, timestamp, t.stop, reason="stop"))
        return hit

    # -- Kennzahlen --------------------------------------------------------

    @property
    def total_return(self) -> float:
        return self.equity / self.start_equity - 1

    @property
    def max_drawdown(self) -> float:
        peak, mdd = self.start_equity, 0.0
        for _, eq in self.equity_curve:
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak)
        return mdd

    def summary(self) -> dict:
        real = [t for t in self.closed_trades if not t.shadow]
        wins = [t for t in real if t.pnl > 0]
        rs = [t.r_multiple for t in real]
        return {
            "portfolio": self.name,
            "equity": round(self.equity, 2),
            "return_pct": round(self.total_return * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "trades": len(real),
            "winrate_pct": round(len(wins) / len(real) * 100, 1) if real else 0.0,
            "avg_r": round(sum(rs) / len(rs), 3) if rs else 0.0,
            "total_fees": round(sum(t.fees for t in real), 2),
        }
