"""Bot A - Trendfolge: EMA-Cross mit ATR-Stop.

Idee: schnelle EMA kreuzt langsame EMA nach oben -> Long. Verdient in Trends,
verliert in Seitwaertsphasen durch staendige Fehlsignale. Genau dafuer gibt es
spaeter Bot B als Gegenspieler und den Allocator darueber.

Confidence: je weiter die EMAs auseinander sind (gemessen in ATR) und je staerker
der Trend laut ADX, desto sicherer. Ob diese Confidence etwas taugt, zeigt erst
die Kalibrierungs-Auswertung im Journal - das ist keine rhetorische Vorsicht,
sondern der eigentliche Test dieser Strategie.
"""
from __future__ import annotations

import pandas as pd

from src.core import Side, Signal
from src.strategies.base import Strategy
from src.utils.indicators import adx, atr, ema


class TrendStrategy(Strategy):
    name = "trend_ema"

    def __init__(
        self,
        fast: int = 21,
        slow: int = 55,
        atr_period: int = 14,
        stop_atr: float = 2.0,
        adx_min: float = 30.0,
    ) -> None:
        self.fast, self.slow = fast, slow
        self.atr_period, self.stop_atr = atr_period, stop_atr
        self.adx_min = adx_min

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.fast)
        out["ema_slow"] = ema(out["close"], self.slow)
        out["atr"] = atr(out, self.atr_period)
        out["adx"] = adx(out, self.atr_period)
        out["spread_atr"] = (out["ema_fast"] - out["ema_slow"]) / out["atr"]
        return out

    def signal(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None:
        if i < self.slow + self.atr_period:
            return None   # Indikatoren noch nicht eingeschwungen

        row, prev = df.iloc[i], df.iloc[i - 1]
        if pd.isna(row["atr"]) or row["atr"] <= 0:
            return None

        crossed_up = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
        crossed_dn = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]

        if not (crossed_up or crossed_dn):
            return None
        if row["adx"] < self.adx_min:
            # Zu schwacher Trend. Der Default 30 ist NICHT frei optimiert, sondern
            # kommt aus analysis/regime_filter.py: von ADX 0 bis 30 verbessert sich
            # avg_r monoton, und der Effekt haelt out-of-sample und auf ETHUSDT.
            # Preis dafuer: nur ~50 Trades pro Jahr. Statistisch duenn - siehe CLAUDE.md.
            return None

        side = Side.LONG if crossed_up else Side.SHORT
        price = row["close"]
        stop = price - self.stop_atr * row["atr"] if side is Side.LONG \
            else price + self.stop_atr * row["atr"]

        # Confidence aus Trendstaerke (ADX 20..50) und EMA-Abstand (0..1 ATR)
        adx_score = min(max((row["adx"] - self.adx_min) / 30.0, 0.0), 1.0)
        spread_score = min(abs(row["spread_atr"]), 1.0)
        confidence = round(min(max(0.2 + 0.5 * adx_score + 0.3 * spread_score, 0.0), 1.0), 3)

        return Signal(
            timestamp=df.index[i], symbol=symbol, side=side,
            confidence=confidence, stop=float(stop), strategy=self.name,
            features={
                "adx": round(float(row["adx"]), 2),
                "atr": round(float(row["atr"]), 2),
                "spread_atr": round(float(row["spread_atr"]), 3),
                "close": round(float(price), 2),
            },
        )
