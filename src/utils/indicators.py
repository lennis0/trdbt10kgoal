"""Indikatoren. Bewusst als reine pandas-Funktionen ohne externe TA-Bibliothek -
weniger Abhaengigkeiten und man sieht, was gerechnet wird.

WICHTIG: Alle Funktionen geben Serien zurueck, die NUR vergangene Werte nutzen.
Kein `center=True`, kein Shift in die Zukunft. Sonst kennt der Backtest Kurse,
die es zum Handelszeitpunkt noch nicht gab, und das Ergebnis ist wertlos.
"""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range - Mass fuer die aktuelle Schwankungsbreite.
    Basis fuer Stop-Distanz und Positionsgroesse."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(50.0).astype(float)


def bollinger(series: pd.Series, period: int = 20, std: float = 2.0):
    mid = series.rolling(period).mean()
    dev = series.rolling(period).std()
    return mid - std * dev, mid, mid + std * dev


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Trendstaerke, 0-100. Ueber ~25 gilt als Trend, unter ~20 als Seitwaerts."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = ((up > down) & (up > 0)) * up.clip(lower=0)
    minus_dm = ((down > up) & (down > 0)) * down.clip(lower=0)
    tr = atr(df, period)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / tr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0.0)


def regime(df: pd.DataFrame, period: int = 14, threshold: float = 25.0) -> pd.Series:
    """Marktregime pro Kerze: 'trend' oder 'range'.

    Landet im Journal und beantwortet spaeter die Frage, in welchem Umfeld eine
    Strategie verliert - genau die Auswertung, auf der der Allocator aufbaut.
    """
    return pd.Series(
        ["trend" if v >= threshold else "range" for v in adx(df, period)],
        index=df.index, name="regime",
    )
