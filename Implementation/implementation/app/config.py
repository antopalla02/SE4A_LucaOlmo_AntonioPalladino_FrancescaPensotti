"""Configuration (RASD C5; DD Sec. 2.4.2 'How').

The active matching strategy is selected by a configuration key read at
startup; the score weights and the ranking truncation N are configuration
parameters, not user-facing settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.domain.errors import ValidationError
from app.matching.rule_based import RuleBasedStrategy
from app.matching.strategy import HardFilterConfig, MatchingStrategy, MatchingWeights
from app.matching.weighted import WeightedScoreStrategy


@dataclass
class Config:
    matching_strategy: str = "weighted"  # "weighted" | "rule_based"  (R26)
    ranking_size: int = 10  # the N of R19 (C5)
    weights: MatchingWeights = field(default_factory=MatchingWeights)
    hard_filters: HardFilterConfig = field(default_factory=HardFilterConfig)
    database_url: str = "sqlite:///freelancematch.db"

    @staticmethod
    def from_env() -> "Config":
        return Config(
            matching_strategy=os.environ.get("FM_MATCHING_STRATEGY", "weighted"),
            ranking_size=int(os.environ.get("FM_RANKING_SIZE", "10")),
            database_url=os.environ.get(
                "FM_DATABASE_URL", "sqlite:///freelancematch.db"
            ),
        )


def build_strategy(config: Config) -> MatchingStrategy:
    """Adding a third strategy = one new class implementing the interface
    plus one new value for this configuration key; no other file changes
    (DD Sec. 2.4.2, verified by T4)."""
    if config.matching_strategy == "weighted":
        return WeightedScoreStrategy(config.weights, config.hard_filters)
    if config.matching_strategy == "rule_based":
        return RuleBasedStrategy(config.hard_filters)
    raise ValidationError(
        "STRATEGY_UNKNOWN", f"unknown matching strategy '{config.matching_strategy}'"
    )
