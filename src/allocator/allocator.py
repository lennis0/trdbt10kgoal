"""Allocator - entscheidet laufend, wie viel Kapital jede Strategie bekommt.

Kein Ein/Aus-Schalter, sondern Gewichte. Der Unterschied ist wichtig:
- Ein harter Schalter waere eine Entscheidung auf Basis weniger Trades. Bei den
  Verteilungen hier (Bot A: 10% Winrate, Gewinn aus Fat Tails) ist so eine
  Entscheidung fast immer verfrueht.
- Gewichte erlauben "hauptsaechlich A, ein bisschen B" und passen sich weiter an.
  Laeuft eine Strategie deutlich besser, geht ihr Gewicht Richtung Maximum und
  die andere wird klein - ohne je ganz zu verschwinden.

MIN_WEIGHT ist der Kern des Ganzen: keine Strategie faellt auf null. Eine
abgeschaltete Strategie erzeugt keine Trades mehr, ohne Trades gibt es keine
Messung, und ohne Messung kann sie nie zurueckkommen - selbst wenn ihr Marktumfeld
laengst wieder da ist. Ein kleines Restgewicht haelt die Messung am Leben.

Bewertungsmasstab ist die Summe der R-Multiples im Fenster, nicht der Gewinn in
Franken. Sonst gewinnt automatisch die Strategie, die zuletzt das groesste
Gewicht hatte - eine Rueckkopplung, die sich selbst verstaerkt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.core import Trade


@dataclass
class AllocatorConfig:
    """ACHTUNG - Standard ist bewusst "aus" (rebalance_days sehr gross).

    Gemessen (analysis/allocator_check.py) schlaegt die feste 50/50-Aufteilung die
    performance-basierte Gewichtung auf beiden Assets deutlich. Begruendung siehe
    CLAUDE.md: Bot A ist eine Fat-Tail-Strategie und liegt in den meisten
    rollierenden Fenstern im Minus. Wer nach juengster Performance gewichtet,
    macht ihn genau dann klein, bevor die grossen Gewinner kommen.

    Die Klasse bleibt, weil sie fuer regimebasierte Gewichtung wiederverwendet
    werden kann - dann aber nach Marktumfeld, nicht nach Rendite.
    """
    lookback_days: int = 365      # kurze Fenster sind bei Fat Tails reines Rauschen
    rebalance_days: int = 10**6   # Standard: aus (feste Gewichte) - siehe oben
    min_weight: float = 0.05      # nie ganz abschalten
    max_weight: float = 0.80      # nie alles auf eine Karte
    min_trades: int = 5           # darunter keine Aussage -> Gleichgewicht
    aggressiveness: float = 1.0   # >1 = staerkere Spreizung der Gewichte


@dataclass
class Allocator:
    strategies: list[str]
    config: AllocatorConfig = field(default_factory=AllocatorConfig)

    def __post_init__(self) -> None:
        equal = 1.0 / len(self.strategies)
        self.weights: dict[str, float] = {s: equal for s in self.strategies}
        self.history: list[tuple[datetime, dict[str, float]]] = []
        self._last_rebalance: datetime | None = None

    def maybe_rebalance(self, now: datetime, trades: list[Trade]) -> bool:
        if self._last_rebalance is not None and \
                now - self._last_rebalance < timedelta(days=self.config.rebalance_days):
            return False
        self._last_rebalance = now
        self.weights = self._compute(now, trades)
        self.history.append((now, dict(self.weights)))
        return True

    def _compute(self, now: datetime, trades: list[Trade]) -> dict[str, float]:
        cfg = self.config
        since = now - timedelta(days=cfg.lookback_days)

        scores: dict[str, float] = {}
        for name in self.strategies:
            window = [t for t in trades
                      if t.strategy == name and t.exit_time and t.exit_time >= since]
            if len(window) < cfg.min_trades:
                scores[name] = None   # zu wenig Daten fuer eine Aussage
            else:
                scores[name] = sum(t.r_multiple for t in window) / len(window)

        known = {k: v for k, v in scores.items() if v is not None}
        if not known:
            equal = 1.0 / len(self.strategies)
            return {s: equal for s in self.strategies}

        # Nur positive Erwartungswerte bekommen Gewicht. Eine Strategie, die im
        # Fenster Geld verliert, faellt auf das Mindestgewicht - sie handelt weiter,
        # aber klein genug, dass sie kaum schadet.
        positive = {k: v ** cfg.aggressiveness for k, v in known.items() if v > 0}

        if not positive:
            # Alle im Minus: alle auf Minimum. Das Gesamtrisiko sinkt automatisch,
            # weil die Gewichte nicht mehr auf 1 normiert werden.
            return {s: cfg.min_weight for s in self.strategies}

        total = sum(positive.values())
        raw = {s: positive.get(s, 0.0) / total for s in self.strategies}

        return self._apply_limits(raw)

    def _apply_limits(self, raw: dict[str, float]) -> dict[str, float]:
        """Gewichte auf [min_weight, max_weight] bringen, Summe bleibt 1.

        Naiv waere: begrenzen, dann normieren. Das verletzt die Grenzen aber wieder -
        beim Normieren waechst der gekappte Wert erneut ueber das Maximum. Darum
        iterativ: begrenzen, den Rest auf die noch freien Strategien verteilen.
        """
        cfg = self.config
        weights = dict(raw)
        for _ in range(10):
            fixed = {s: min(max(w, cfg.min_weight), cfg.max_weight)
                     for s, w in weights.items()}
            total = sum(fixed.values())
            if abs(total - 1.0) < 1e-9:
                return fixed
            free = [s for s, w in fixed.items()
                    if cfg.min_weight < w < cfg.max_weight]
            if not free:
                return fixed
            rest = 1.0 - sum(w for s, w in fixed.items() if s not in free)
            free_total = sum(fixed[s] for s in free) or 1.0
            weights = dict(fixed)
            for s in free:
                weights[s] = rest * fixed[s] / free_total
        return fixed

    def weight(self, strategy: str) -> float:
        return self.weights.get(strategy, self.config.min_weight)
