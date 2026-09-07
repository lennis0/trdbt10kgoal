"""Positionsgroesse und harte Risiko-Limits.

Kernregel des Projekts: der Hebel ist KEIN Regler. Man legt fest, wie viel Geld man
bei diesem Trade verlieren will, und die Positionsgroesse ergibt sich aus der
Stop-Distanz. Der Hebel ist nur das Ergebnis dieser Rechnung.

    Risiko  = Equity * base_risk_pct * confidence
    Groesse = Risiko / |Entry - Stop|

Dadurch ist der maximale Verlust pro Trade immer bekannt, egal wie volatil der
Markt gerade ist. Bei hoher Volatilitaet wird die Position automatisch kleiner.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.utils.config import RiskLimits


@dataclass
class SizingResult:
    size: float
    risk_amount: float
    leverage: float
    capped_by: str = ""   # "" | "max_risk" | "max_leverage"


class RiskManager:
    """Steht bewusst ausserhalb der Strategie-Logik. Eine Strategie kann keine
    Limits umgehen, weil sie die Groesse gar nicht selbst bestimmt."""

    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits
        self._day: date | None = None
        self._day_start_equity: float = 0.0
        self.halted = False
        self.halt_reason = ""

    # -- Sizing ------------------------------------------------------------

    def size_for(
        self, equity: float, entry: float, stop: float, confidence: float
    ) -> SizingResult:
        distance = abs(entry - stop)
        if distance <= 0:
            raise ValueError("Stop-Distanz ist 0 - Positionsgroesse waere unendlich")

        risk_pct = self.limits.base_risk_pct * confidence
        capped = ""

        if risk_pct > self.limits.max_risk_pct:
            risk_pct = self.limits.max_risk_pct
            capped = "max_risk"

        risk_amount = equity * risk_pct
        size = risk_amount / distance
        leverage = size * entry / equity

        if leverage > self.limits.max_leverage:
            # Nicht die Stop-Distanz aufweichen, sondern die Position verkleinern.
            # Das reduziert das Risiko unter das Ziel - richtig herum gedacht.
            size = self.limits.max_leverage * equity / entry
            risk_amount = size * distance
            leverage = self.limits.max_leverage
            capped = "max_leverage"

        return SizingResult(size, risk_amount, leverage, capped)

    # -- Kill-Switch -------------------------------------------------------

    def start_day(self, day: date, equity: float) -> None:
        if self._day != day:
            self._day = day
            self._day_start_equity = equity
            self.halted = False
            self.halt_reason = ""

    def check_kill_switch(self, equity: float) -> bool:
        """True = ab jetzt keine neuen Positionen mehr an diesem Tag.

        Bestehende Positionen laufen in ihre Stops. Der Schalter existiert gegen den
        Fall, dass eine Strategie in einem Marktumfeld kaputt geht und Verlust auf
        Verlust stapelt - das passiert schneller, als man zuschauen kann.
        """
        if self.halted or self._day_start_equity <= 0:
            return self.halted
        loss = (self._day_start_equity - equity) / self._day_start_equity
        if loss >= self.limits.daily_loss_kill_pct:
            self.halted = True
            self.halt_reason = f"Tagesverlust {loss:.1%} >= {self.limits.daily_loss_kill_pct:.0%}"
        return self.halted
