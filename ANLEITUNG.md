# Anleitung — was du machst, was ich mache

Stand: 07.09.2026

---

## Wo wir stehen

Das Fundament steht: Kursdaten, Paper-Broker, Trade-Journal. Alles getestet.
Ein Bot ist es noch nicht — es fehlt die Strategie, also erzeugt nichts ein Kaufsignal.

Wallets: drei virtuelle mit je 10'000 USD, existieren nur im Code.
Kein Konto, keine Börsenverbindung, kein echtes Geld. So bleibt es bis auf Weiteres.

---

## Teil 1 — jetzt, 15 Minuten

### 1. Git-Repo anlegen

Terminal im Projektordner öffnen:

```bash
git init
git add .
git commit -m "Fundament: Datenlayer, Paper-Broker, Journal"
```

Warum jetzt: sobald mehrere Strategien und Parameter im Spiel sind, willst du
zurückspringen können. Später nachzuholen kostet dich die Historie.
Die `.gitignore` ist da — Keys und Daten bleiben draussen.

### 2. Testdatenbanken wegwerfen

Ordner `logs/_to_delete/` löschen. Das sind meine Testreste, ich darf auf deinem
Rechner nicht löschen.

### 3. Zwei Dateien lesen

- `src/core.py` (~90 Zeilen) — `Signal` und `Trade`. Bestimmt die Struktur von allem.
- `config/config.yaml` (~25 Zeilen) — alle Zahlen des Projekts an einem Ort.

Das ist der günstigste Moment, um etwas an der Struktur zu ändern.
Wenn dir etwas komisch vorkommt: sag es, bevor zehn Module darauf aufbauen.

### 4. Eine Sache entscheiden

In `config.yaml` steht `base_risk_pct: 0.01` — 1% Risiko pro Trade.
Bei 10'000 USD sind das 100 USD, die du pro Trade maximal verlierst.
Passt das für dich, oder willst du beim Testen kleiner anfangen? Sag Bescheid.

---

## Teil 2 — die nächsten Sessions

Das baue ich, du schaust drauf und entscheidest:

| # | Was | Was du danach siehst |
|---|-----|---------------------|
| 1 | Config-Loader + Risk-Modul | Positionsgrösse aus Confidence und ATR |
| 2 | Strategie A: Trendfolge | Erste echte Kaufsignale |
| 3 | Backtest-Engine | **Erstes Ergebnis: Equity-Kurve über 2 Jahre BTC** |
| 4 | Strategie B: Mean-Reversion | Zwei Strategien im Vergleich |
| 5 | Allocator | Kapitalverteilung nach Performance |
| 6 | Dashboard | Chart mit Indikatoren und Trade-Markern |

Nach Schritt 3 hast du zum ersten Mal echte Zahlen. Bis dahin ist alles Vorarbeit.

---

## Teil 3 — wenn der Backtest läuft

Hier wird es entscheidend, und hier machen die meisten den Fehler ihres Lebens.

**Der erste Backtest wird wahrscheinlich schlecht aussehen. Das ist normal und gut.**

Was du dann NICHT machst: Parameter so lange verdrehen, bis die Kurve schön ist.
Das nennt sich Overfitting. Du bekommst eine Strategie, die die Vergangenheit
auswendig kann und in der Zukunft sofort verliert. Das ist der häufigste Grund,
warum private Trading-Bots scheitern.

Was du stattdessen machst:

1. Journal auswerten — in welchem Marktumfeld verliert die Strategie?
2. Confidence-Kalibrierung prüfen — steigt `avg_r` mit der Confidence?
3. Netto rechnen, nie brutto. Bei 15m-Kerzen fressen Gebühren viel.
   Ein Stop-Out kostet -1.17R, nicht -1.00R.
4. Änderungen immer gegen Daten prüfen, die bei der Optimierung nicht sichtbar waren.

---

## Teil 4 — echtes Geld

Frühestens nach **vier Wochen** dokumentiertem Paper-Trading ohne Eingriff.
Nicht "vier Wochen, in denen ich dreimal nachgeholfen habe".

Vorher zu klären:

- Mindestalter 18 für ein Handelskonto in der Schweiz.
- Nur Geld, dessen Totalverlust dir egal ist. Nicht "wäre schade" — egal.
- Kill-Switch getestet? Was passiert bei Internetausfall mitten in einer Position?
- Steuern: Krypto-Gewinne sind in der Schweiz für Privatpersonen normalerweise
  steuerfrei, aber gewerbsmässiger Handel wird anders behandelt. Bei einem Bot mit
  vielen Trades ist das keine theoretische Frage — vor dem Livegang abklären.

Ein Bot, der im Paper-Trading Gewinn macht, ist noch kein Bot, der live Gewinn macht.
Der Unterschied heisst Slippage, Latenz und die eigenen Nerven.

---

## Kurz

**Jetzt:** Git init, `_to_delete` löschen, `core.py` und `config.yaml` anschauen,
Risiko-Prozentsatz bestätigen.

**Dann:** sag mir, ob ich Risk + Strategie + Backtest durchziehen soll.
Danach hast du das erste echte Ergebnis.
