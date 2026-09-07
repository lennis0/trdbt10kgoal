# TradingBot

Ziel: eigener Trading-Bot — erst Backtesting, dann Paper-Trading zum "Trainieren", danach evtl. Live mit kleinem Kapital.

## Struktur
- `src/data/` — Marktdaten laden (Broker-/Exchange-API, CSV, Cache)
- `src/strategies/` — Strategien, alle mit gleichem Interface (`on_bar()` -> Signal)
- `src/backtest/` — Backtest-Engine + Metriken (PnL, Sharpe, Max Drawdown, Winrate)
- `src/paper/` — Paper-Trading-Runner (Live-Daten, simulierte Orders)
- `src/live/` — echter Order-Router (erst wenn Paper stabil ist)
- `config/` — YAML/ENV Konfiguration, Keys NICHT committen
- `data/raw|processed` — historische Kursdaten
- `logs/` — Trade- und Runtime-Logs
- `tests/` — Unit-Tests für Strategie-Logik

## Roadmap
1. Datenquelle wählen + historische Daten ziehen
2. Backtest-Engine (Fees + Slippage einrechnen)
3. Erste Strategie (z.B. EMA-Cross) implementieren + backtesten
4. Paper-Trading gegen Live-Feed, Logging aller Trades
5. Auswertung / Parameter-Tuning (Achtung: Overfitting)
6. Erst danach: Live mit minimalem Einsatz + Risk-Limits

## Regeln
- Risikolimit pro Trade fix definieren (z.B. 1% Equity)
- Kill-Switch bei X% Tagesverlust
- Kein Live-Deployment ohne mind. 4 Wochen sauberes Paper-Trading
