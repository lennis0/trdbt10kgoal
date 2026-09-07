# CLAUDE.md — Kontext für das nächste Modell

Diese Datei beschreibt Ziel, Stand und Entscheidungen des Projekts. Bitte vor der ersten
Änderung komplett lesen und am Ende jeder Session den Abschnitt "Stand" aktualisieren.

## Wer / Was
- User: Le, 1. Lehrjahr Informatiker EFZ (TIE International, Schweiz). Spricht Deutsch.
- Bevorzugt direkte, kurze Antworten und schnelle Iteration statt langer Erklärungen.
- Projektziel: eigener Trading-Bot. Erst Backtest, dann Paper-Trading, evtl. später Live
  mit kleinem Kapital. Lerneffekt und saubere Architektur sind wichtiger als schneller Gewinn.

## Grundprinzipien (nicht ohne Rücksprache ändern)
1. Kein Live-Trading, bevor mind. 4 Wochen sauberes Paper-Trading dokumentiert sind.
2. Risiko-Limits liegen ausserhalb der Strategie-Logik und sind hart:
   max. 2% Equity-Risiko pro Trade, max. ~3x effektiver Hebel, Kill-Switch bei X% Tagesverlust.
3. Hebel ist NIE ein direkter Regler. Positionsgrösse ergibt sich aus:
   `Risiko = Equity * Basisrisiko% * Confidence` und `Size = Risiko / Stop-Distanz (ATR)`.
   Der Hebel ist nur das Ergebnis dieser Rechnung.
4. Backtests immer mit Gebühren + Slippage. Strategieauswahl immer gegen Out-of-Sample-Daten
   prüfen — sonst wählt man die glücklichste, nicht die beste Strategie.
5. Bei Zielkonflikt "sicher vs. profitabel": Hauptmetrik ist **Calmar Ratio**,
   Sharpe wird zusätzlich ausgewiesen.

## Architektur-Entscheid: 3 logische Bots, EIN Prozess
Nicht drei getrennte Programme/Wallets, sondern eine Engine mit drei virtuellen Portfolios.
Gleiche Datenbasis, gleiche Uhr, direkt vergleichbar, eine Codebasis.

- **Bot A — Trendfolge**: EMA-Cross / Donchian-Breakout + ATR-Stop. Verdient in Trends.
- **Bot B — Mean-Reversion**: RSI / Bollinger-Rückkehr zum Mittel. Verdient in Seitwärtsphasen.
- **Bot C — Allocator (Meta)**: handelt nicht selbst. Misst rollierende Performance von A und B
  und verteilt Kapital. Mindestgewicht 5% pro Strategie (keine stirbt endgültig).
  Abgeschaltete Strategien laufen im **Shadow-Mode** weiter und loggen hypothetische Trades,
  damit man sieht, wann sie wieder funktionieren.

Getrennte echte Wallets/Sub-Accounts erst dann, wenn eine Strategie live geht.

## "Lernen aus Fehlern" — Stufenplan
Stufe 1 (jetzt): Trade-Journal mit Entry, Exit, Signal, Indikatorwerten, Marktregime, PnL.
Auswertung nach Regime, Richtung, Confidence-Bucket.
Stufe 2 (später): Walk-Forward-Parameteroptimierung. Overfitting-Gefahr ernst nehmen.
Stufe 3 (viel später): ML/RL. Andockpunkt ist das `confidence`-Feld im Signal-Interface.
Nicht vorziehen — ohne Stufe 1 kann man ein Modell gar nicht bewerten.

Wichtig: Confidence muss **kalibriert** sein. Im Backtest Signale in Confidence-Buckets
einteilen und die tatsächliche Trefferquote pro Bucket prüfen. Unkalibrierte Confidence
ist schlechter als gar keine.

## Tech-Stack (recherchiert, Stand September 2026 — alles gratis)
- **Sprache**: Python. Abstraktion über `ccxt` (~100 Exchanges, Wechsel per Config).
- **Markt**: BTC/ETH Spot, Timeframe **15m** (vom User bestaetigt).
  15m heisst viele Trades -> Gebuehren und Slippage sind der dominante Kostenfaktor.
  Eine Strategie, die brutto knapp gewinnt, verliert hier netto. Immer netto bewerten. Begründung: 24/7 (schnelle Iteration),
  gratis APIs, echte Testumgebungen, viel Historie. Gold/CFD ist als Strategie okay,
  als Lernumgebung umständlicher (Handelszeiten, Broker-Account, Rollover) —
  lässt sich später über `src/data/` anhängen.
- **Verworfen: Memecoin-Sniping (Solana/Robinhood).** Der Edge liegt dort bei Latenz und
  Infrastruktur (eigener RPC-Node, Jito-Bundles), nicht bei Strategie. Dazu Rugpulls,
  Honeypots, Sandwich-Angriffe. Lässt sich nicht sinnvoll paper-traden, weil genau der
  entscheidende Teil — bekommt man den Fill? — nicht simulierbar ist.
- **HARTE VORGABE: kein KYC.** Es wird ausschliesslich mit oeffentlichen Endpoints
  gearbeitet (kein API-Key, kein Account). Kein Umgehen von KYC bei regulierten Boersen.
- **Paper-Trading: eigener Paper-Broker** (`src/paper/`), nicht Bybit Demo. Gruende:
  drei getrennte Wallets fuer die drei Bots (Bybit Demo gibt pro Account nur eine),
  identische Fill-Logik wie im Backtest -> Ergebnisse vergleichbar, Zeitraffer moeglich,
  kein 7-Tage-Limit. Preis dafuer: Fills werden selbst simuliert, also bei Slippage
  konservativ rechnen, nie optimistisch.
- Der User HAT einen Boersen-Account. Rolle: spaeterer Reality-Check - dieselbe Strategie
  parallel auf Bybit Demo laufen lassen und pruefen, ob die simulierten Fills passen.
  Nicht das Fundament.
- **Historische Daten**: Binance Public Data Dumps (`data.binance.vision`), gratis CSV-Klines
  ohne API-Key. Für Backtests die erste Wahl.
- **Charting**: `lightweight-charts` von TradingView (Apache-2.0, gratis, sehr klein).
  ACHTUNG Lizenz: Attribution auf TradingView nötig — via Chart-Option `attributionLogo`.
  NICHT die Plattform tradingview.com / Pine Script als Bot-Basis: Pine läuft auf deren
  Servern und kann den Python-Bot nicht steuern (nur Webhooks raus).
  Für statische Backtest-Auswertung: `mplfinance` oder Plotly.
- Nicht verifiziert: Alpaca Paper Trading (gratis, Aktien+Krypto) — Verfügbarkeit für
  Nutzer ausserhalb der USA wurde nicht geprüft. Nur relevant, falls Aktien dazukommen.

## Ordnerstruktur
```
src/data/        Marktdaten (ccxt, CSV-Dumps, Cache)
src/strategies/  Strategien, einheitliches Interface -> Signal(richtung, confidence, stop)
src/backtest/    Backtest-Engine + Metriken (Calmar, Sharpe, MaxDD, Winrate)
src/allocator/   Gewichtung der Strategien, Shadow-Mode
src/risk/        Confidence + ATR -> Positionsgrösse, harte Limits, Kill-Switch
src/journal/     Trade-Log mit Features, Confidence, Regime, Ergebnis
src/paper/       Paper-Trading-Runner gegen Live-Feed
src/live/        Echter Order-Router (erst wenn Paper stabil ist)
src/dashboard/   Web-Dashboard, liest nur Journal + Datalayer, keine Trading-Logik
config/          YAML/ENV. Keys NIE committen (.gitignore beachten)
data/raw|processed, logs/, notebooks/, tests/
```

## Stand (zuletzt: 2026-09-07)
Bestaetigt: BTCUSDT + ETHUSDT, 15m-Kerzen.

Fertig und getestet:
- Ordnerstruktur, README, .gitignore, requirements.txt, .env.example.
- `src/data/klines.py` - historische Klines von Binance Public REST, Parquet-Cache in
  `data/raw/`, Luecken-Pruefung. Verwirft bewusst die letzte, noch laufende Kerze
  (Lookahead-Schutz). Getestet: BTCUSDT 1h ab 2024-01-01 = 23'521 Kerzen, 0 Luecken.
  Braucht `pyarrow` (ist installiert).
  Im Cache: BTCUSDT und ETHUSDT 15m ab 2024-01-01, je 94'081 Kerzen, 0 Luecken.
- `src/core.py` - `Signal` und `Trade`. Signal erzwingt confidence 0..1 und einen Stop
  (ohne Stop kein Sizing). Trade rechnet `pnl` und `r_multiple`.
  R-Multiple ist die Hauptkennzahl pro Trade - vergleichbar ueber Groessen und Maerkte.

- `src/paper/broker.py` - PaperBroker. Ein virtuelles Wallet pro Bot. Slippage geht
  immer gegen uns (beim Oeffnen UND Schliessen), Taker-Fee auf beiden Seiten.
  `check_stops()` prueft Stops gegen High/Low der Kerze. Bekannte Schwaeche: bei
  Gap-Opens waere der echte Fill schlechter -> Verluste werden leicht unterschaetzt.
  Kennzahlen via `summary()`: return, max_drawdown, winrate, avg_r, fees.
- `src/journal/journal.py` - SQLite-Journal. `by_strategy()`, `by_regime()` und
  `calibration()`. Letzteres ist die wichtigste Auswertung im Projekt: steigt avg_r
  nicht mit der Confidence, ist das Sizing wertlos oder schaedlich.
  SQLite-Journal-Modus wird automatisch gewaehlt (WAL lokal, MEMORY auf Netz-/FUSE-
  Mounts, weil dort das File-Locking fehlt). Getestet mit 80 synthetischen Trades.
- `config/config.yaml` - Symbole, Timeframe, Kosten, Risiko-Limits, die drei Portfolios.
  Noch von keinem Modul eingelesen - Loader fehlt.

Naechste Schritte in dieser Reihenfolge:
1. Config-Loader (`src/utils/config.py`), damit die Werte aus config.yaml auch greifen.
2. `src/risk/` - Sizing aus Confidence + ATR, harte Limits, Kill-Switch.
3. `src/strategies/` - Bot A (Trendfolge) und Bot B (Mean-Reversion).
4. `src/backtest/` - Engine + Metriken (Calmar, Sharpe, MaxDD, Winrate).
5. `src/allocator/` - Gewichtung, Shadow-Mode.
6. `src/dashboard/` - Lightweight Charts.

Aufraeumen: `logs/_to_delete/` enthaelt Test-Datenbanken aus der SQLite-Fehlersuche.
Kann der User loeschen, wird nicht gebraucht.
