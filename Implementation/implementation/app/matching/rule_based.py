"""RuleBasedStrategy — the comparison baseline (DD Sec. 2.2.2, R45).

Ranks by sequential criteria — full skill coverage first, then budget
feasibility, then decreasing reputation — without any weighted combination.
Used for the matching-quality comparison planned in the project proposal.
"""

from __future__ import annotations

from ..domain.entities import Freelancer, Project
from .strategy import HardFilterConfig, MatchingStrategy, ScoredResult


class RuleBasedStrategy(MatchingStrategy):
    name = "rule_based"

    def __init__(self, hard_filters: HardFilterConfig | None = None):
        self.hard_filters = hard_filters or HardFilterConfig()

    # Sequential criteria ------------------------------------------------- #

    def _full_coverage(self, project: Project, f: Freelancer) -> bool:
        return project.required_skill_ids <= f.skill_ids()

    def _budget_feasible(self, project: Project, f: Freelancer) -> bool:
        estimated = f.hourly_rate * self.hard_filters.nominal_hours
        return estimated <= project.max_budget

    def _any_overlap(self, project: Project, f: Freelancer) -> bool:
        return bool(project.required_skill_ids & f.skill_ids())

    def _key(self, project: Project, f: Freelancer) -> tuple:
        return (
            1 if self._full_coverage(project, f) else 0,
            1 if self._budget_feasible(project, f) else 0,
            f.reputation,
        )

    @staticmethod
    def _key_to_score(key: tuple) -> float:
        """Collapse the lexicographic key into a displayable score in [0,1]
        that preserves the ordering: coverage and feasibility dominate,
        reputation breaks ties."""
        cov, fea, rep = key
        return (cov * 2 + fea + rep) / 4.0

    def rank_freelancers(
        self, project: Project, candidates: list[Freelancer]
    ) -> list[ScoredResult]:
        eligible = [f for f in candidates if self._any_overlap(project, f)]
        ordered = sorted(eligible, key=lambda f: self._key(project, f), reverse=True)
        return [
            ScoredResult(f.id, self._key_to_score(self._key(project, f)))
            for f in ordered
        ]

    def rank_projects(
        self, freelancer: Freelancer, open_projects: list[Project]
    ) -> list[ScoredResult]:
        eligible = [p for p in open_projects if self._any_overlap(p, freelancer)]
        ordered = sorted(
            eligible, key=lambda p: self._key(p, freelancer), reverse=True
        )
        return [
            ScoredResult(p.id, self._key_to_score(self._key(p, freelancer)))
            for p in ordered
        ]
