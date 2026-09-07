"""Historische Klines laden und cachen.

Nutzt ausschliesslich oeffentliche Endpoints - kein API-Key, kein Account, kein KYC.
Quelle: Binance Public REST (api.binance.com/api/v3/klines).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# Reihenfolge ist wichtig. data-api.binance.vision ist Binances oeffentlicher
# Endpunkt NUR fuer Marktdaten - er hat keine Laendersperre und funktioniert
# damit auch auf GitHub-Actions-Maschinen, die in den USA stehen.
# api.binance.com antwortet von dort mit HTTP 451 ("restricted location").
# Genau daran ist der erste CI-Lauf gescheitert.
ENDPOINTS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
]
MAX_LIMIT = 1000  # Maximum Kerzen pro Request bei Binance

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]

# Timeframe -> Millisekunden
TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def _to_ms(value: str | datetime) -> int:
    """Datum ('2024-01-01') oder datetime -> Unix-Millisekunden (UTC)."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _cache_path(symbol: str, timeframe: str, start: str, end: str) -> Path:
    name = f"{symbol}_{timeframe}_{start}_{end[:10]}.parquet".replace(":", "-")
    return CACHE_DIR / name


def fetch_klines(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    start: str = "2023-01-01",
    end: str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Laedt Klines und liefert einen DataFrame mit UTC-Index.

    Spalten: open, high, low, close, volume, trades.
    Die letzte, noch nicht abgeschlossene Kerze wird verworfen - sonst handelt
    der Bot im Backtest auf unvollstaendigen Daten (klassischer Lookahead-Fehler).
    """
    if timeframe not in TF_MS:
        raise ValueError(f"Timeframe {timeframe!r} unbekannt. Bekannt: {list(TF_MS)}")

    # BUG-FIX: frueher stand hier strftime("%Y-%m-%d"). Das ergibt MITTERNACHT des
    # heutigen Tages als Endzeit - alle Kerzen von heute fehlten dadurch. Im
    # Backtest faellt das kaum auf, fuer den Live-Runner ist es toedlich: er
    # bekommt nie eine neue Kerze zu sehen.
    end = end or datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = _cache_path(symbol, timeframe, start, end)

    if use_cache and path.exists():
        return pd.read_parquet(path)

    start_ms, end_ms = _to_ms(start), _to_ms(end)
    step = TF_MS[timeframe]
    rows: list[list] = []
    cursor = start_ms

    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": MAX_LIMIT,
        }
        batch, last_error = None, None
        for url in ENDPOINTS:
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                batch = resp.json()
                break
            except requests.RequestException as exc:
                last_error = exc
        if batch is None:
            raise RuntimeError(f"Kein Binance-Endpunkt erreichbar: {last_error}")
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + step
        if len(batch) < MAX_LIMIT:
            break
        time.sleep(0.25)  # hoeflich bleiben, Rate-Limit nicht reizen

    if not rows:
        raise RuntimeError(f"Keine Daten fuer {symbol} {timeframe} ab {start}")

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("timestamp")

    numeric = ["open", "high", "low", "close", "volume"]
    df[numeric] = df[numeric].astype(float)
    df["trades"] = df["trades"].astype(int)
    df = df[numeric + ["trades"]]

    df = df[~df.index.duplicated(keep="first")].sort_index()

    # Letzte Kerze verwerfen, falls ihr Zeitfenster noch laeuft
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if not df.empty and _to_ms(df.index[-1].to_pydatetime()) + step > now_ms:
        df = df.iloc[:-1]

    # Nur cachen, wenn der Cache auch genutzt werden soll. Der Live-Runner holt
    # bewusst frische Daten (use_cache=False) und braucht dann weder die Datei
    # noch die pyarrow-Abhaengigkeit - das haelt den CI-Lauf schlank.
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
    return df


def check_gaps(df: pd.DataFrame, timeframe: str) -> pd.DatetimeIndex:
    """Gibt fehlende Kerzen-Zeitpunkte zurueck. Leer = Daten sind luekenlos."""
    expected = pd.date_range(df.index[0], df.index[-1], freq=pd.Timedelta(milliseconds=TF_MS[timeframe]))
    return expected.difference(df.index)


if __name__ == "__main__":
    data = fetch_klines("BTCUSDT", "1h", "2024-01-01")
    print(data.tail())
    print(f"\n{len(data)} Kerzen von {data.index[0]} bis {data.index[-1]}")
    print(f"Luecken: {len(check_gaps(data, '1h'))}")
