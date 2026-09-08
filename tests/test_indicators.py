"""Regressionstests fuer die Indikatoren.

Der ADX-Test unten existiert wegen eines echten Ausfalls: der Live-Bot stuerzte
bei jedem Lauf ab, der Backtest lief sauber. Ursache war `pd.NA` in adx(), das
die Serie zu dtype=object macht - ewm() wirft darauf einen Fehler. Ausgeloest
wird das nur, wenn plus_di + minus_di irgendwo exakt 0 ist, also bei flachen
oder sehr kurzen Datenreihen. Genau der Fall, der im Backtest nie vorkam.
"""
import sys

import pandas as pd

sys.path.insert(0, ".")

from src.utils.indicators import adx, atr, bollinger, ema, regime, rsi


def _flat(n=60):
    """Voellig flache Kerzen - der Grenzfall, der den Bug ausgeloest hat."""
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": [100.0] * n, "high": [100.0] * n,
                         "low": [100.0] * n, "close": [100.0] * n,
                         "volume": [1.0] * n}, index=idx)


def _wiggly(n=200):
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    close = pd.Series([100 + (i % 7) - 3 + i * 0.05 for i in range(n)], index=idx)
    return pd.DataFrame({"open": close, "high": close + 1.0,
                         "low": close - 1.0, "close": close,
                         "volume": [1.0] * n}, index=idx)


def test_alle_indikatoren_liefern_floats():
    """Kein Indikator darf dtype=object zurueckgeben - darauf scheitert ewm()."""
    for name, df in [("flach", _flat()), ("bewegt", _wiggly())]:
        assert adx(df).dtype == "float64", f"adx auf {name}"
        assert rsi(df["close"]).dtype == "float64", f"rsi auf {name}"
        assert atr(df).dtype == "float64", f"atr auf {name}"
        assert ema(df["close"], 10).dtype == "float64", f"ema auf {name}"


def test_indikatoren_ueberleben_kurze_reihen():
    """Der Live-Runner hat nur wenige Tage Vorlauf, nicht Jahre."""
    for n in (20, 40, 60):
        df = _wiggly(n)
        assert len(adx(df)) == n
        assert not adx(df).isna().any()
        assert set(regime(df).unique()) <= {"trend", "range"}


def test_bollinger_ordnung():
    lower, mid, upper = bollinger(_wiggly()["close"])
    valid = mid.notna()
    assert (lower[valid] <= mid[valid]).all()
    assert (mid[valid] <= upper[valid]).all()


if __name__ == "__main__":
    for fn in [test_alle_indikatoren_liefern_floats,
               test_indikatoren_ueberleben_kurze_reihen,
               test_bollinger_ordnung]:
        fn()
        print(f"ok  {fn.__name__}")
    print("\nAlle Tests bestanden.")
