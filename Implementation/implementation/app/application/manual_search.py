"""Use case ``manual_search`` (S6; R27-R29).

Declared nice-to-have in the plan (DD Sec. 5.1, increment 3) but included.
The ordering parameter of R29 is resolved here: compatibility score (via
the injected strategy), deadline ascending, or budget descending.
No state change is induced by the search itself (S6 postconditions).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..domain.entities import Freelancer, Project, User
from ..domain.errors import ValidationError
from ..matching.strategy import MatchingStrategy
from ..repositories.interfaces import UnitOfWork

ORDERINGS = ("score", "deadline", "budget")


class ManualSearch:
    def __init__(self, uow: UnitOfWork, strategy: MatchingStrategy):
        self.uow, self.strategy = uow, strategy

    # R27 — client searches freelancers ---------------------------------- #

    def search_freelancers(
        self,
        skill_ids: Optional[set[str]] = None,
        rate_min: Optional[float] = None,
        rate_max: Optional[float] = None,
        available_from: Optional[date] = None,
        available_to: Optional[date] = None,
        order_by: str = "score",
        reference_project_id: Optional[str] = None,
    ) -> list[User]:
        if order_by not in ORDERINGS:
            raise ValidationError("ORDERING_INVALID", f"order_by must be in {ORDERINGS}")
        result = self.uow.users.search_freelancers(
            skill_ids, rate_min, rate_max, available_from, available_to
        )
        if order_by == "score" and reference_project_id:
            project = self.uow.projects.get(reference_project_id)
            if project is not None:
                ranking = self.strategy.rank_freelancers(
                    project, [f for f in result if isinstance(f, Freelancer)]
                )
                pos = {r.entity_id: i for i, r in enumerate(ranking)}
                result.sort(key=lambda f: pos.get(f.id, len(pos)))
                return result
        # fallback orderings for the freelancer catalogue
        if order_by == "budget":  # interpreted as hourly rate descending
            result.sort(key=lambda f: getattr(f, "hourly_rate", 0.0), reverse=True)
        else:  # reputation as the neutral default when no project reference
            result.sort(key=lambda f: f.reputation, reverse=True)
        return result

    # R28 — freelancer searches open projects ----------------------------- #

    def search_projects(
        self,
        freelancer_id: Optional[str] = None,
        skill_ids: Optional[set[str]] = None,
        budget_min: Optional[float] = None,
        budget_max: Optional[float] = None,
        deadline_from: Optional[date] = None,
        deadline_to: Optional[date] = None,
        order_by: str = "score",
    ) -> list[Project]:
        if order_by not in ORDERINGS:
            raise ValidationError("ORDERING_INVALID", f"order_by must be in {ORDERINGS}")
        result = self.uow.projects.search_open(
            skill_ids, budget_min, budget_max, deadline_from, deadline_to
        )
        if order_by == "deadline":  # R29 — deadline ascending
            result.sort(key=lambda p: p.deadline)
        elif order_by == "budget":  # R29 — budget descending
            result.sort(key=lambda p: p.max_budget, reverse=True)
        else:  # R29 — compatibility score via the injected strategy (R26)
            freelancer = self.uow.users.get(freelancer_id) if freelancer_id else None
            if isinstance(freelancer, Freelancer):
                ranking = self.strategy.rank_projects(freelancer, result)
                pos = {r.entity_id: i for i, r in enumerate(ranking)}
                result.sort(key=lambda p: pos.get(p.id, len(pos)))
        return result
