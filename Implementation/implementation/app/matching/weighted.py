"""WeightedScoreStrategy — the default implementation of S(P,F) (R24, R25).

The four sub-scores (s_skills, s_budget, s_reputation, s_availability) are
private methods, each normalised in [0,1]; ``_compute_score`` combines them
with the weights held by the MatchingWeights value object. Hard filters
(R25) are applied before any score is computed, so excluded candidates
never enter the scoring loop (DD Sec. 2.2.2).
"""

from __future__ import annotations

from datetime import date

from ..domain.entities import Freelancer, Project
from ..domain.enums import MasteryLevel
from .strategy import (
    HardFilterConfig,
    MatchingStrategy,
    MatchingWeights,
    ScoredResult,
)

_MASTERY_WEIGHT = {
    MasteryLevel.BASIC: 0.5,
    MasteryLevel.INTERMEDIATE: 0.75,
    MasteryLevel.ADVANCED: 1.0,
}


class WeightedScoreStrategy(MatchingStrategy):
    name = "weighted"

    def __init__(
        self,
        weights: MatchingWeights | None = None,
        hard_filters: HardFilterConfig | None = None,
    ):
        self.weights = (weights or MatchingWeights()).validate()
        self.hard_filters = hard_filters or HardFilterConfig()

    # ------------------------------------------------------------------ #
    # Hard filters (R25): applied BEFORE scoring
    # ------------------------------------------------------------------ #

    def _passes_hard_filters(self, project: Project, f: Freelancer) -> bool:
        # Budget overrun beyond the configured tolerance (R25 example).
        estimated_cost = f.hourly_rate * self.hard_filters.nominal_hours
        if estimated_cost > project.max_budget * (1 + self.hard_filters.budget_tolerance):
            return False
        # No overlap at all with the required skills: nothing to match on.
        if not (project.required_skill_ids & f.skill_ids()):
            return False
        return True

    # ------------------------------------------------------------------ #
    # Sub-scores, each normalised in [0,1] (R24)
    # ------------------------------------------------------------------ #

    def _s_skills(self, project: Project, f: Freelancer) -> float:
        """Coverage of the required skills, weighted by mastery level."""
        required = project.required_skill_ids
        if not required:
            return 0.0
        by_skill = {c.skill_id: c.level for c in f.competences}
        total = sum(
            _MASTERY_WEIGHT[by_skill[s]] for s in required if s in by_skill
        )
        return total / len(required)

    def _s_budget(self, project: Project, f: Freelancer) -> float:
        """1 when the estimated cost fits the budget, decaying linearly
        with the overrun up to the hard-filter bound."""
        estimated = f.hourly_rate * self.hard_filters.nominal_hours
        if estimated <= 0:
            return 1.0
        if project.max_budget <= 0:
            return 0.0
        ratio = estimated / project.max_budget
        if ratio <= 1.0:
            return 1.0
        tol = self.hard_filters.budget_tolerance
        # ratio in (1, 1+tol]: linear decay 1 -> 0
        return max(0.0, 1.0 - (ratio - 1.0) / tol) if tol > 0 else 0.0

    def _s_reputation(self, project: Project, f: Freelancer) -> float:
        """Reputation is already normalised in [0,1] (R33)."""
        return min(1.0, max(0.0, f.reputation))

    def _s_availability(
        self, project: Project, f: Freelancer, today: date | None = None
    ) -> float:
        """Fraction of the project window [today, deadline] covered by the
        freelancer's availability windows."""
        today = today or date.today()
        if project.deadline <= today:
            return 0.0
        window_days = (project.deadline - today).days
        covered = sum(a.overlap_days(today, project.deadline) for a in f.availabilities)
        return min(1.0, covered / window_days) if window_days > 0 else 0.0

    # ------------------------------------------------------------------ #
    # S(P,F) (R24)
    # ------------------------------------------------------------------ #

    def _compute_score(self, project: Project, f: Freelancer) -> float:
        w = self.weights
        return (
            w.w_skills * self._s_skills(project, f)
            + w.w_budget * self._s_budget(project, f)
            + w.w_reputation * self._s_reputation(project, f)
            + w.w_availability * self._s_availability(project, f)
        )

    # ------------------------------------------------------------------ #
    # The two ranking directions (G1 / G2) — DD Sec. 2.2.2
    # ------------------------------------------------------------------ #

    def rank_freelancers(
        self, project: Project, candidates: list[Freelancer]
    ) -> list[ScoredResult]:
        eligible = [f for f in candidates if self._passes_hard_filters(project, f)]
        scored = [ScoredResult(f.id, self._compute_score(project, f)) for f in eligible]
        return sorted(scored, key=lambda r: r.score, reverse=True)

    def rank_projects(
        self, freelancer: Freelancer, open_projects: list[Project]
    ) -> list[ScoredResult]:
        eligible = [
            p for p in open_projects if self._passes_hard_filters(p, freelancer)
        ]
        scored = [
            ScoredResult(p.id, self._compute_score(p, freelancer)) for p in eligible
        ]
        return sorted(scored, key=lambda r: r.score, reverse=True)
