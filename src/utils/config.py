"""Config-Loader. Alle Zahlen des Projekts kommen aus config/config.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


@dataclass(frozen=True)
class Costs:
    taker_fee: float
    slippage_bps: float


@dataclass(frozen=True)
class RiskLimits:
    base_risk_pct: float
    max_risk_pct: float
    max_leverage: float
    daily_loss_kill_pct: float


@dataclass(frozen=True)
class Config:
    symbols: list[str]
    timeframe: str
    history_start: str
    costs: Costs
    risk: RiskLimits
    portfolios: dict[str, dict]


@lru_cache(maxsize=1)
def load_config(path: Path | str = CONFIG_PATH) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Config(
        symbols=raw["market"]["symbols"],
        timeframe=raw["market"]["timeframe"],
        history_start=raw["market"]["history_start"],
        costs=Costs(**raw["costs"]),
        risk=RiskLimits(**raw["risk"]),
        portfolios=raw["portfolios"],
    )
