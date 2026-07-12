"""Matching component (DD Sec. 2.1.4 / 2.2.2) — the *Strategy* interface.

``MatchingStrategy`` is the interface the application layer depends on
(R26). It exposes the two ranking directions of G1/G2 as separate
operations, both returning ordered lists of ``ScoredResult``; truncation
to the configured length N is performed by the caller (DD Sec. 2.2.2).

Depends only on ``domain`` (dependency rules, DD Sec. 2.1.7).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..domain.entities import Freelancer, Project
from ..domain.errors import ValidationError


@dataclass(frozen=True)
class ScoredResult:
    """One entry of a ranking: the matched entity id and its score."""

    entity_id: str
    score: float


@dataclass(frozen=True)
class MatchingWeights:
    """Value object holding the four weights of S(P,F) (R24).

    Kept separate from the strategy constructor so that the
    administrator-facing configuration of RASD C5 has a single,
    validated home (DD Sec. 2.2.2).
    """

    w_skills: float = 0.4
    w_budget: float = 0.2
    w_reputation: float = 0.25
    w_availability: float = 0.15

    def validate(self) -> "MatchingWeights":
        """R24 — weights normalised, summing to one."""
        total = self.w_skills + self.w_budget + self.w_reputation + self.w_availability
        if any(
            w < 0
            for w in (self.w_skills, self.w_budget, self.w_reputation, self.w_availability)
        ):
            raise ValidationError("WEIGHTS_NEGATIVE", "weights must be >= 0")
        if abs(total - 1.0) > 1e-9:
            raise ValidationError("WEIGHTS_SUM", f"weights must sum to 1 (got {total})")
        return self


@dataclass(frozen=True)
class HardFilterConfig:
    """R25 — hard filters applied before any score is computed.

    ``budget_tolerance``: a freelancer whose estimated cost exceeds
    ``max_budget * (1 + budget_tolerance)`` is excluded from the ranking.
    ``nominal_hours``: nominal effort used to turn an hourly rate into an
    estimated cost (the project model carries a total budget, not hours).
    """

    budget_tolerance: float = 0.2
    nominal_hours: float = 40.0


class MatchingStrategy(ABC):
    """The Strategy interface (GoF) — DD Sec. 2.4.2, G5/R26."""

    name: str = "abstract"

    @abstractmethod
    def rank_freelancers(
        self, project: Project, candidates: list[Freelancer]
    ) -> list[ScoredResult]:
        """G1 — ranked freelancers for a published project (R19)."""

    @abstractmethod
    def rank_projects(
        self, freelancer: Freelancer, open_projects: list[Project]
    ) -> list[ScoredResult]:
        """G2 — ranked open projects for a registered freelancer (R21)."""
