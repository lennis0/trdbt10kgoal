"""Paper-Trading-Runner: verarbeitet neue Live-Kerzen und handelt simuliert.

Aufruf:
    python -m src.paper.runner            # ein Durchlauf, dann Ende (fuer Cron)
    python -m src.paper.runner --loop     # laeuft durch, prueft jede Minute
    python -m src.paper.runner --status   # nur Stand anzeigen, nichts handeln

Bewusst REST statt WebSocket. Ein WebSocket braucht einen Dauerprozess; REST
funktioniert auch als Cron-Job, der alle 15 Minuten kurz aufwacht. Fuer 15m- und
4h-Kerzen ist das voellig ausreichend - eine Kerze, die vor drei Minuten
geschlossen hat, ist dieselbe Kerze wie vor einer Sekunde.

Verarbeitet werden nur ABGESCHLOSSENE Kerzen. Auf einer laufenden Kerze zu
handeln waere derselbe Fehler wie Lookahead im Backtest, nur umgekehrt: der
Schlusskurs steht noch gar nicht fest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

from src.core import Side
from src.data.klines import fetch_klines
from src.paper import state as state_mod
from src.paper.broker import PaperBroker
from src.risk.sizing import RiskManager
from src.strategies.reversion import ReversionStrategy
from src.strategies.trend import TrendStrategy
from src.utils.config import load_config

# Welche Strategie auf welchem Timeframe laeuft. Ergebnis der Messungen -
# Begruendung in CLAUDE.md.
SETUP = [
    ("trend_ema", TrendStrategy, "15m"),
    ("reversion_bb", ReversionStrategy, "4h"),
]
SYMBOL = "BTCUSDT"
WARMUP_BARS = 400   # genug Vorlauf, damit die Indikatoren eingeschwungen sind


def _restore_broker(state: dict, config, start_equity: float) -> PaperBroker:
    broker = PaperBroker(
        "paper", state.get("equity") or start_equity,
        taker_fee=config.costs.taker_fee,
        slippage_bps=config.costs.slippage_bps,
    )
    broker.start_equity = start_equity
    broker.open_trades = {t.trade_id: t for t in state.get("open_trades", [])}
    broker.closed_trades = list(state.get("closed_trades", []))
    broker.equity_curve = [
        (datetime.fromisoformat(ts), eq) for ts, eq in state.get("equity_curve", [])
    ]
    return broker


def tick(verbose: bool = True) -> dict:
    """Ein Durchlauf: neue Kerzen holen, verarbeiten, Zustand speichern."""
    config = load_config()
    start_equity = config.portfolios.get("trend", {}).get("start_equity", 200)
    state = state_mod.load()
    broker = _restore_broker(state, config, start_equity)
    risk = RiskManager(config.risk)

    if state.get("started_at") is None:
        state["started_at"] = datetime.now(timezone.utc).isoformat()

    actions: list[str] = []

    for name, cls, timeframe in SETUP:
        strategy = cls()
        df = fetch_klines(SYMBOL, timeframe, _start_for(timeframe), use_cache=False)
        data = strategy.prepare(df)

        last_seen = state["last_candle"].get(timeframe)
        last_seen_ts = pd.Timestamp(last_seen) if last_seen else None

        # Beim allerersten Lauf nichts nachholen - sonst handelt der Bot beim Start
        # die halbe Historie in einer Sekunde durch.
        if last_seen_ts is None:
            state["last_candle"][timeframe] = data.index[-1].isoformat()
            actions.append(f"{name}: Start, setze Marke auf {data.index[-1]}")
            continue

        new_bars = data[data.index > last_seen_ts]
        state.setdefault("bars_seen", {})
        state["bars_seen"][timeframe] = state["bars_seen"].get(timeframe, 0) + len(new_bars)
        if new_bars.empty:
            continue

        for ts in new_bars.index:
            i = data.index.get_loc(ts)
            row = data.iloc[i]

            risk.start_day(ts.date(), broker.equity)

            # 1. Stops der eigenen Positionen pruefen
            for trade in broker.check_stops(ts, float(row["high"]), float(row["low"])):
                actions.append(f"STOP {trade.strategy} {trade.side.value} "
                               f"{trade.r_multiple:+.2f}R")

            # 2. Signal dieser Kerze - Ausfuehrung zum Schlusskurs, weil der
            #    naechste Open bei einem Cron-Lauf erst in 15 Minuten kommt.
            #    Leicht optimistischer als der Backtest; im Journal vergleichbar,
            #    weil Gebuehren und Slippage identisch gerechnet werden.
            sig = strategy.signal(data, i, SYMBOL)
            if sig is None or sig.side is Side.FLAT:
                continue

            price = float(row["close"])
            for tid, t in list(broker.open_trades.items()):
                if t.strategy == name and t.side is not sig.side:
                    closed = broker.close_trade(tid, ts, price, reason="signal")
                    actions.append(f"EXIT {name} {closed.r_multiple:+.2f}R")

            if any(t.strategy == name for t in broker.open_trades.values()):
                continue
            if risk.check_kill_switch(broker.equity):
                actions.append(f"KILL-SWITCH aktiv: {risk.halt_reason}")
                continue

            try:
                sizing = risk.size_for(broker.equity, price, sig.stop, 0.5)
            except ValueError:
                continue
            trade = broker.open_trade(
                ts, SYMBOL, sig.side, price, sizing.size, sig.stop,
                0.5, name, features=sig.features, regime=str(row.get("regime", "")),
            )
            actions.append(f"ENTRY {name} {sig.side.value} @ {trade.entry_price:.2f} "
                           f"Stop {sig.stop:.2f} Groesse {sizing.size:.6f}")

        state["last_candle"][timeframe] = new_bars.index[-1].isoformat()
        actions.append(f"{name}: {len(new_bars)} neue Kerze(n) verarbeitet")

    state["equity"] = broker.equity
    state["open_trades"] = list(broker.open_trades.values())
    state["closed_trades"] = broker.closed_trades
    state["equity_curve"] = [(ts.isoformat(), eq) for ts, eq in broker.equity_curve]
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    state_mod.save(state)

    if verbose:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"[{stamp}] Equity {broker.equity:.2f} | "
              f"offen {len(broker.open_trades)} | Trades gesamt {len(broker.closed_trades)}")
        for a in actions:
            print(f"   {a}")
        if not actions:
            print("   keine neuen Kerzen")
    return state


def _start_for(timeframe: str) -> str:
    """Genug Historie fuer den Indikator-Vorlauf, aber nicht mehr."""
    minutes = {"15m": 15, "1h": 60, "4h": 240}[timeframe]
    days = max(int(WARMUP_BARS * minutes / 1440) + 2, 5)
    return (pd.Timestamp.utcnow() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


# Erwartete Handelsfrequenz aus dem Backtest (BTCUSDT, 2024-01 bis 2026-09).
# Dient nur der Einordnung im Status - keine Vorhersage.
TRADES_PER_YEAR = 85


def status() -> None:
    """Zeigt den Stand - und vor allem, ob der Bot ueberhaupt noch lebt.

    Der wichtigste Teil ist die Lebenszeichen-Pruefung. Ein Bot ohne Signale und
    ein Bot mit kaputter Datenverbindung sehen von aussen identisch aus: beide
    machen nichts. Deshalb wird hier geprueft, ob noch Kerzen ankommen - und
    nicht nur, ob Trades entstehen.
    """
    s = state_mod.load()
    if s.get("equity") is None:
        print("Noch kein Zustand - der Bot lief noch nie.")
        return

    now = datetime.now(timezone.utc)
    closed = s["closed_trades"]
    wins = [t for t in closed if (t.pnl or 0) > 0]

    started = s.get("started_at")
    days = (now - datetime.fromisoformat(started)).total_seconds() / 86400 if started else 0
    expected = TRADES_PER_YEAR * days / 365

    print(f"Paper-Trading seit {started[:10] if started else '?'}  ({days:.1f} Tage)")
    print(f"  Equity        {s['equity']:.2f} CHF  ({s['equity'] / 200 - 1:+.1%})")
    print(f"  Offen         {len(s['open_trades'])}")
    print(f"  Abgeschlossen {len(closed)}"
          + (f" | Winrate {len(wins) / len(closed) * 100:.0f}%" if closed else "")
          + f"   (erwartet nach {days:.1f} Tagen: ~{expected:.1f})")

    for t in s["open_trades"]:
        print(f"    {t.strategy} {t.side.value} @ {t.entry_price:.2f} Stop {t.stop:.2f}")

    # -- Lebenszeichen --------------------------------------------------
    print("\n  Lebenszeichen:")
    updated = s.get("updated_at")
    if updated:
        age_min = (now - datetime.fromisoformat(updated)).total_seconds() / 60
        mark = "ok" if age_min < 60 else "ACHTUNG - laeuft der Bot noch?"
        print(f"    Letzter Lauf      vor {age_min:.0f} min   {mark}")

    for timeframe, iso in s.get("last_candle", {}).items():
        age_min = (now - datetime.fromisoformat(iso)).total_seconds() / 60
        limit = {"15m": 45, "1h": 150, "4h": 600}.get(timeframe, 600)
        mark = "ok" if age_min < limit else "ACHTUNG - keine frischen Daten"
        seen = s.get("bars_seen", {}).get(timeframe, 0)
        print(f"    {timeframe:<4} letzte Kerze  vor {age_min:>4.0f} min   "
              f"{seen} verarbeitet   {mark}")

    if not closed and days < 21:
        print("\n  Noch keine Trades - bei ~85 Trades/Jahr ist das bis etwa "
              "3 Wochen unauffaellig.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Paper-Trading-Runner")
    parser.add_argument("--loop", action="store_true", help="dauerhaft laufen")
    parser.add_argument("--status", action="store_true", help="nur Stand anzeigen")
    parser.add_argument("--interval", type=int, default=60, help="Sekunden je Pruefung im Loop")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.loop:
        import time
        print("Loop gestartet - mit Strg+C beenden")
        while True:
            try:
                tick()
            except Exception as exc:              # Netzfehler darf den Bot nicht killen
                print(f"Fehler (wird ignoriert, naechster Versuch): {exc}")
            time.sleep(args.interval)
    else:
        tick()
