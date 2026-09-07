"""Zentrale Datentypen. Alles andere haengt hieran - Aenderungen gut ueberlegen."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"   # kein Signal / Position schliessen


@dataclass(frozen=True)
class Signal:
    """Das, was jede Strategie zurueckgibt. Einheitlich fuer alle Strategien.

    confidence: 0.0-1.0, wie sicher sich die Strategie ist. Steuert spaeter die
    Positionsgroesse. MUSS kalibriert sein - siehe CLAUDE.md. Eine Strategie, die
    immer 1.0 liefert, ist erlaubt, macht das Sizing aber wirkungslos.

    stop: Preis des Stop-Loss. Der Abstand Entry->Stop bestimmt die Positionsgroesse,
    darum ist er Pflicht und nicht optional.

    features: Indikatorwerte zum Signalzeitpunkt. Landen im Journal und sind spaeter
    die Trainingsdaten, falls ML dazukommt.
    """
    timestamp: datetime
    symbol: str
    side: Side
    confidence: float
    stop: float | None = None
    strategy: str = ""
    features: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence muss 0..1 sein, ist {self.confidence}")
        if self.side is not Side.FLAT and self.stop is None:
            raise ValueError("Signal ohne Stop ist nicht erlaubt - Sizing braucht die Stop-Distanz")


@dataclass
class Trade:
    """Ein abgeschlossener oder offener Trade. Basis fuer das gesamte Journal."""
    trade_id: str
    strategy: str
    symbol: str
    side: Side
    entry_time: datetime
    entry_price: float
    size: float
    stop: float
    confidence: float
    initial_stop: float | None = None  # Stop beim Einstieg, fuer R unveraenderlich
    portfolio: str = "default"        # welcher der Bots (A/B/...)
    shadow: bool = False              # hypothetischer Trade einer nicht allokierten Strategie
    features: dict[str, float] = field(default_factory=dict)
    regime: str = ""                  # Marktregime beim Entry, fuer die Auswertung

    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: str = ""             # signal | stop | kill_switch
    fees: float = 0.0
    slippage: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    @property
    def pnl(self) -> float | None:
        """Realisierter PnL nach Gebuehren. None solange offen."""
        if self.exit_price is None:
            return None
        direction = 1 if self.side is Side.LONG else -1
        gross = (self.exit_price - self.entry_price) * self.size * direction
        return gross - self.fees - self.slippage

    @property
    def r_multiple(self) -> float | None:
        """PnL in Vielfachen des ANFANGSrisikos.

        Bezugsgroesse ist bewusst `initial_stop`, nicht `stop`: bei einem Trailing-Stop
        wandert `stop` waehrend des Trades mit. Rechnet man R gegen den mitgewanderten
        Stop, veraendert sich nachtraeglich der Nenner und die Zahl wird unsinnig -
        ein Gewinntrade kann dann ein negatives R bekommen.
        """
        if self.pnl is None:
            return None
        reference = self.initial_stop if self.initial_stop is not None else self.stop
        risk = abs(self.entry_price - reference) * self.size
        return self.pnl / risk if risk > 0 else 0.0
