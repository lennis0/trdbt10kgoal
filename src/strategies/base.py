"""Gemeinsames Interface aller Strategien.

Jede Strategie bekommt den kompletten DataFrame und gibt pro Kerze ein Signal.
Sie berechnet ihre Indikatoren einmal vektorisiert (schnell) und liefert danach
pro Zeitpunkt ein Signal - der Backtest laeuft aber Kerze fuer Kerze durch,
damit kein Zukunftswissen einfliesst.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from src.core import Signal


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Indikatoren berechnen. Gibt den DataFrame mit Zusatzspalten zurueck."""

    @abstractmethod
    def signal(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None:
        """Signal fuer Kerze i. None = nichts tun.

        Es darf ausschliesslich auf df.iloc[:i+1] zugegriffen werden. Alles darueber
        hinaus ist Zukunftswissen und macht den Backtest wertlos.
        """
