"""Zustand des laufenden Bots - laden und speichern.

Der Runner ist bewusst ZUSTANDSLOS gebaut: er laedt den Zustand, verarbeitet die
neuen Kerzen, speichert den Zustand, und beendet sich. Das ist die Voraussetzung
dafuer, dass er als Cron-Job laufen kann (GitHub Actions, systemd-Timer) statt
als Dauerprozess - und es macht ihn absturzsicher: nach einem Neustart macht er
genau dort weiter, wo er aufgehoert hat.

Format ist JSON, nicht SQLite oder Pickle: lesbar, versionierbar, und man kann
im Zweifel mit einem Texteditor nachschauen, was der Bot gerade denkt.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.core import Side, Trade

STATE_PATH = Path(__file__).resolve().parents[2] / "state" / "paper_state.json"


def _trade_to_dict(t: Trade) -> dict:
    d = asdict(t)
    d["side"] = t.side.value
    d["entry_time"] = t.entry_time.isoformat()
    d["exit_time"] = t.exit_time.isoformat() if t.exit_time else None
    return d


def _trade_from_dict(d: dict) -> Trade:
    d = dict(d)
    d["side"] = Side(d["side"])
    d["entry_time"] = datetime.fromisoformat(d["entry_time"])
    d["exit_time"] = datetime.fromisoformat(d["exit_time"]) if d["exit_time"] else None
    return Trade(**d)


def load(path: Path = STATE_PATH) -> dict:
    """Liefert den gespeicherten Zustand oder einen leeren Startzustand."""
    if not path.exists():
        return {"equity": None, "open_trades": [], "closed_trades": [],
                "last_candle": {}, "equity_curve": [], "started_at": None}

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["open_trades"] = [_trade_from_dict(t) for t in raw.get("open_trades", [])]
    raw["closed_trades"] = [_trade_from_dict(t) for t in raw.get("closed_trades", [])]
    return raw


def save(state: dict, path: Path = STATE_PATH) -> None:
    """Schreibt atomar: erst in eine temporaere Datei, dann umbenennen.

    Ein Absturz mitten im Schreiben wuerde sonst eine halb geschriebene Datei
    hinterlassen - und damit den gesamten Zustand des Bots zerstoeren.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(state)
    out["open_trades"] = [_trade_to_dict(t) for t in state.get("open_trades", [])]
    out["closed_trades"] = [_trade_to_dict(t) for t in state.get("closed_trades", [])]

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
