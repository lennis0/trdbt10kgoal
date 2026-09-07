"""Trade-Journal: persistieren und auswerten.

Das ist Stufe 1 von "aus Fehlern lernen" (siehe CLAUDE.md). Unspektakulaer, aber
es ist der Teil, der Strategien tatsaechlich besser macht.

Speicher: SQLite. Reicht fuer Millionen Trades, braucht keinen Server, und du kannst
mit normalem SQL Fragen stellen wie "verliere ich hauptsaechlich in Seitwaertsphasen".
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from src.core import Trade

DB_PATH = Path(__file__).resolve().parents[2] / "logs" / "journal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id    TEXT PRIMARY KEY,
    portfolio   TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    shadow      INTEGER NOT NULL,
    entry_time  TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_time   TEXT,
    exit_price  REAL,
    exit_reason TEXT,
    size        REAL NOT NULL,
    stop        REAL NOT NULL,
    confidence  REAL NOT NULL,
    regime      TEXT,
    fees        REAL NOT NULL,
    slippage    REAL NOT NULL,
    pnl         REAL,
    r_multiple  REAL,
    features    TEXT
);
CREATE INDEX IF NOT EXISTS idx_strategy  ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_portfolio ON trades(portfolio);
CREATE INDEX IF NOT EXISTS idx_entry     ON trades(entry_time);
"""


class Journal:
    def __init__(self, path: Path | str = DB_PATH, mode: str = "auto") -> None:
        self.path = Path(path)
        self.mode = mode  # "auto" | "WAL" | "MEMORY"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._set_journal_mode()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _set_journal_mode(self) -> None:
        """Waehlt den SQLite-Journal-Modus.

        WAL ist auf einer normalen lokalen Platte die richtige Wahl: schnell und
        absturzsicher. Auf Netzlaufwerken, Cloud-Sync-Ordnern und FUSE-Mounts hat
        SQLite aber kein verlaessliches File-Locking - dort scheitert WAL mit
        'disk I/O error' und MEMORY ist der einzige Modus, der funktioniert.

        MEMORY bedeutet: ein Absturz mitten in einer Transaktion kann die DB
        beschaedigen. Fuer ein Trade-Journal vertretbar, weil es aus den Logs
        rekonstruierbar ist.

        Ein fehlgeschlagener WAL-Versuch schreibt den Modus in den Datei-Header und
        legt -wal/-shm-Dateien an. Die muessen weg, sonst scheitert auch MEMORY.
        """
        if self.mode != "auto":
            self.conn = sqlite3.connect(self.path)
            self.conn.execute(f"PRAGMA journal_mode={self.mode}")
            self.journal_mode = self.mode
            return

        try:
            conn = sqlite3.connect(self.path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS _probe(x INTEGER)")
            conn.execute("DROP TABLE _probe")
            conn.commit()
            self.conn, self.journal_mode = conn, "WAL"
            return
        except sqlite3.OperationalError:
            try:
                conn.close()
            except Exception:
                pass
            for sidecar in (f"{self.path}-wal", f"{self.path}-shm"):
                Path(sidecar).unlink(missing_ok=True)

        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("CREATE TABLE IF NOT EXISTS _probe(x INTEGER)")
        conn.execute("DROP TABLE _probe")
        conn.commit()
        self.conn, self.journal_mode = conn, "MEMORY"

    def record(self, trade: Trade) -> None:
        """Schreibt oder aktualisiert einen Trade."""
        self.conn.execute(
            """INSERT OR REPLACE INTO trades VALUES
               (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trade.trade_id, trade.portfolio, trade.strategy, trade.symbol,
                trade.side.value, int(trade.shadow),
                trade.entry_time.isoformat(), trade.entry_price,
                trade.exit_time.isoformat() if trade.exit_time else None,
                trade.exit_price, trade.exit_reason,
                trade.size, trade.stop, trade.confidence, trade.regime,
                trade.fees, trade.slippage, trade.pnl, trade.r_multiple,
                json.dumps(trade.features),
            ),
        )
        self.conn.commit()

    def record_many(self, trades: list[Trade]) -> None:
        for t in trades:
            self.record(t)

    def to_frame(self, where: str = "exit_time IS NOT NULL") -> pd.DataFrame:
        df = pd.read_sql(f"SELECT * FROM trades WHERE {where}", self.conn,
                         parse_dates=["entry_time", "exit_time"])
        return df

    # -- Auswertungen ------------------------------------------------------

    def by_strategy(self) -> pd.DataFrame:
        df = self.to_frame("exit_time IS NOT NULL AND shadow = 0")
        if df.empty:
            return df
        return df.groupby("strategy").agg(
            trades=("trade_id", "count"),
            winrate=("pnl", lambda s: (s > 0).mean() * 100),
            avg_r=("r_multiple", "mean"),
            total_pnl=("pnl", "sum"),
            fees=("fees", "sum"),
        ).round(3)

    def by_regime(self) -> pd.DataFrame:
        """Beantwortet: in welchem Marktumfeld verliert diese Strategie?"""
        df = self.to_frame("exit_time IS NOT NULL AND shadow = 0")
        if df.empty:
            return df
        return df.groupby(["strategy", "regime"]).agg(
            trades=("trade_id", "count"),
            avg_r=("r_multiple", "mean"),
        ).round(3)

    def calibration(self, buckets: int = 5) -> pd.DataFrame:
        """Confidence-Kalibrierung - die wichtigste Auswertung im Projekt.

        Teilt Trades nach Confidence in Buckets und zeigt die tatsaechliche Trefferquote.
        Wenn der Bot bei confidence 0.9 sagt "geht hoch", sollte das oefter stimmen als
        bei 0.5. Steigt avg_r nicht mit der Confidence, ist das Sizing wertlos oder
        sogar schaedlich - dann setzt der Bot am meisten, wenn er sich irrt.
        """
        df = self.to_frame("exit_time IS NOT NULL")
        if df.empty:
            return df
        df["bucket"] = pd.cut(df["confidence"], bins=buckets)
        return df.groupby("bucket", observed=True).agg(
            trades=("trade_id", "count"),
            winrate=("pnl", lambda s: (s > 0).mean() * 100),
            avg_r=("r_multiple", "mean"),
        ).round(3)

    def close(self) -> None:
        self.conn.close()
