"""Bot B - Mean-Reversion: Rueckkehr zum Mittelwert.

Der bewusste Gegenspieler zu Bot A. Bot A handelt nur bei ADX >= 30 (Trend) und
laesst Seitwaertsphasen komplett liegen - genau dort soll Bot B verdienen.

Idee: Kurs faellt unter das untere Bollinger-Band und der RSI ist ueberverkauft
-> Gegenbewegung zur Mitte erwarten, Long. Umgekehrt fuer Short.

Anderer Charakter als Bot A, und das ist Absicht:
- viele kleine Gewinne, wenige grosse Verluste (Bot A ist genau umgekehrt)
- Take-Profit am Mittelband, weil die These mit Erreichen der Mitte erfuellt ist
- Trailing-Stop ist hier sinnvoll, bei Bot A war er schaedlich

Das Risiko dieser Strategie ist bekannt: in einem starken Trend kauft sie
wiederholt in einen fallenden Markt hinein. Darum der ADX-Filter nach OBEN -
sie handelt nur, wenn KEIN Trend laeuft.

WICHTIG - Bot B laeuft auf 4h, NICHT auf 15m.
Auf 15m erzeugt er ~2200 Trades in 2.5 Jahren mit einem Edge von 0.093R brutto.
Die Gebuehren kosten dort 0.23-0.52R pro Trade, also das Zwei- bis Fuenffache des
Edges -> Totalverlust. Auf 4h bleiben ~100 Trades mit 0.374R (BTC) bzw. 0.113R
(ETH) netto. Details und die Rechnung dahinter stehen in CLAUDE.md.
"""
from __future__ import annotations

import pandas as pd

from src.core import Side, Signal
from src.strategies.base import Strategy
from src.utils.indicators import adx, atr, bollinger, rsi


class ReversionStrategy(Strategy):
    name = "reversion_bb"

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_low: float = 30.0,
        rsi_high: float = 70.0,
        atr_period: int = 14,
        stop_atr: float = 3.0,
        adx_max: float = 25.0,
    ) -> None:
        self.bb_period, self.bb_std = bb_period, bb_std
        self.rsi_period, self.rsi_low, self.rsi_high = rsi_period, rsi_low, rsi_high
        self.atr_period, self.stop_atr = atr_period, stop_atr
        self.adx_max = adx_max

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        lower, mid, upper = bollinger(out["close"], self.bb_period, self.bb_std)
        out["bb_lower"], out["bb_mid"], out["bb_upper"] = lower, mid, upper
        out["rsi"] = rsi(out["close"], self.rsi_period)
        out["atr"] = atr(out, self.atr_period)
        out["adx"] = adx(out, self.atr_period)
        return out

    def signal(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None:
        if i < self.bb_period + self.atr_period:
            return None

        row, prev = df.iloc[i], df.iloc[i - 1]
        if pd.isna(row["bb_lower"]) or pd.isna(row["atr"]) or row["atr"] <= 0:
            return None

        # Nur in Seitwaertsphasen - im Trend verliert Mean-Reversion systematisch
        if row["adx"] > self.adx_max:
            return None

        # Rueckkehr INS Band hinein, nicht schon beim Durchbrechen. Sonst faengt
        # man das fallende Messer - der Kurs kann beliebig weit unter dem Band laufen.
        back_from_low = prev["close"] < prev["bb_lower"] and row["close"] >= row["bb_lower"]
        back_from_high = prev["close"] > prev["bb_upper"] and row["close"] <= row["bb_upper"]

        if back_from_low and row["rsi"] < self.rsi_high:
            side = Side.LONG
        elif back_from_high and row["rsi"] > self.rsi_low:
            side = Side.SHORT
        else:
            return None

        price = float(row["close"])
        stop = price - self.stop_atr * row["atr"] if side is Side.LONG \
            else price + self.stop_atr * row["atr"]

        return Signal(
            timestamp=df.index[i], symbol=symbol, side=side,
            confidence=1.0,   # gleiche Begruendung wie bei Bot A - siehe trend.py
            stop=float(stop), strategy=self.name,
            features={
                "rsi": round(float(row["rsi"]), 1),
                "adx": round(float(row["adx"]), 2),
                "atr": round(float(row["atr"]), 2),
                "close": round(price, 2),
                "bb_mid": round(float(row["bb_mid"]), 2),
                "band_width_atr": round(float((row["bb_upper"] - row["bb_lower"]) / row["atr"]), 2),
            },
        )
