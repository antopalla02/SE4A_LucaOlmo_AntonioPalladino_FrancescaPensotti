"""In-memory implementation of the repository interfaces (DD Sec. 2.1.6).

Implemented *before* the SQL ones because they unblock the testing of
everything above the domain at negligible cost (DD Sec. 5.1, increment 2).
Domain and application tests run in milliseconds with no database.

Commit/rollback are no-ops: the in-memory store mutates aggregates in
place; the transactional semantics of R16 becomes real with the SQLite
implementation (DD Sec. 5.2, integration point 1).
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Optional

from ..domain.entities import (
    Freelancer,
    Notification,
    Project,
    Review,
    Skill,
    SkillRequest,
    User,
)
from ..domain.enums import ProjectStatus, Role
from .interfaces import (
    IMetricsRepository,
    INotificationRepository,
    IProjectRepository,
    IRankingRepository,
    IReviewRepository,
    ISkillRepository,
    IUserRepository,
    UnitOfWork,
)


class InMemoryUserRepository(IUserRepository):
    def __init__(self, store: dict):
        self._users: dict[str, User] = store.setdefault("users", {})

    def get(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        email = email.strip().lower()
        return next((u for u in self._users.values() if u.email == email), None)

    def exists_by_email(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    def save(self, user: User) -> None:
        self._users[user.id] = user

    def list_freelancers(self) -> list[User]:
        return [u for u in self._users.values() if u.role == Role.FREELANCER]

    def search_freelancers(
        self,
        skill_ids: Optional[set[str]] = None,
        rate_min: Optional[float] = None,
        rate_max: Optional[float] = None,
        available_from: Optional[date] = None,
        available_to: Optional[date] = None,
    ) -> list[User]:
        result = []
        for u in self.list_freelancers():
            assert isinstance(u, Freelancer)
            if skill_ids and not (skill_ids <= u.skill_ids()):
                continue
            if rate_min is not None and u.hourly_rate < rate_min:
                continue
            if rate_max is not None and u.hourly_rate > rate_max:
                continue
            if available_from is not None and available_to is not None:
                if not any(
                    a.overlap_days(available_from, available_to) > 0
                    for a in u.availabilities
                ):
                    continue
            result.append(u)
        return result


class InMemoryProjectRepository(IProjectRepository):
    def __init__(self, store: dict):
        self._projects: dict[str, Project] = store.setdefault("projects", {})

    def get(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def get_with_proposals(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)  # aggregate is stored whole

    def save(self, project: Project) -> None:
        self._projects[project.id] = project

    def list_open(self) -> list[Project]:
        return [p for p in self._projects.values() if p.status == ProjectStatus.OPEN]

    def list_by_client(self, client_id: str) -> list[Project]:
        return [p for p in self._projects.values() if p.client_id == client_id]

    def list_with_proposals_by_freelancer(self, freelancer_id: str) -> list[Project]:
        return [
            p
            for p in self._projects.values()
            if any(pr.freelancer_id == freelancer_id for pr in p.proposals)
        ]

    def search_open(
        self,
        skill_ids: Optional[set[str]] = None,
        budget_min: Optional[float] = None,
        budget_max: Optional[float] = None,
        deadline_from: Optional[date] = None,
        deadline_to: Optional[date] = None,
    ) -> list[Project]:
        result = []
        for p in self.list_open():
            if skill_ids and not (skill_ids & p.required_skill_ids):
                continue
            if budget_min is not None and p.max_budget < budget_min:
                continue
            if budget_max is not None and p.max_budget > budget_max:
                continue
            if deadline_from is not None and p.deadline < deadline_from:
                continue
            if deadline_to is not None and p.deadline > deadline_to:
                continue
            result.append(p)
        return result


class InMemoryReviewRepository(IReviewRepository):
    def __init__(self, store: dict):
        self._reviews: dict[str, Review] = store.setdefault("reviews", {})

    def save(self, review: Review) -> None:
        self._reviews[review.id] = review

    def list_by_project(self, project_id: str) -> list[Review]:
        return [r for r in self._reviews.values() if r.project_id == project_id]

    def list_by_target(self, target_id: str) -> list[Review]:
        return [r for r in self._reviews.values() if r.target_id == target_id]


class InMemoryNotificationRepository(INotificationRepository):
    def __init__(self, store: dict):
        self._notifications: dict[str, Notification] = store.setdefault(
            "notifications", {}
        )

    def save(self, notification: Notification) -> None:
        self._notifications[notification.id] = notification

    def list_by_user(self, user_id: str) -> list[Notification]:
        return sorted(
            (n for n in self._notifications.values() if n.user_id == user_id),
            key=lambda n: n.created_at,
        )


class InMemorySkillRepository(ISkillRepository):
    def __init__(self, store: dict):
        self._skills: dict[str, Skill] = store.setdefault("skills", {})
        self._requests: dict[str, SkillRequest] = store.setdefault("skill_requests", {})

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def get_by_name(self, name: str) -> Optional[Skill]:
        name = name.strip().lower()
        return next(
            (s for s in self._skills.values() if s.name.lower() == name), None
        )

    def save(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    def list_all(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def save_request(self, request: SkillRequest) -> None:
        self._requests[request.id] = request

    def list_requests(self) -> list[SkillRequest]:
        return list(self._requests.values())


class InMemoryRankingRepository(IRankingRepository):
    def __init__(self, store: dict):
        self._project_rankings: dict[str, list] = store.setdefault(
            "project_rankings", {}
        )
        self._suggested: dict[str, list] = store.setdefault("suggested_projects", {})

    def save_project_ranking(self, project_id, ranking):
        self._project_rankings[project_id] = list(ranking)

    def get_project_ranking(self, project_id):
        return list(self._project_rankings.get(project_id, []))

    def save_suggested_projects(self, freelancer_id, ranking):
        self._suggested[freelancer_id] = list(ranking)

    def get_suggested_projects(self, freelancer_id):
        return list(self._suggested.get(freelancer_id, []))


class InMemoryMetricsRepository(IMetricsRepository):
    def __init__(self, store: dict):
        self._metrics: dict[str, int] = store.setdefault("metrics", {})

    def record(self, metric: str, amount: int = 1) -> None:
        self._metrics[metric] = self._metrics.get(metric, 0) + amount

    def snapshot(self) -> dict[str, int]:
        return dict(self._metrics)


class InMemoryUnitOfWork(UnitOfWork):
    """All repositories share one dict-of-dicts ``store``; commit/rollback
    are no-ops (see module docstring)."""

    def __init__(self, store: Optional[dict] = None):
        self.store = store if store is not None else {}
        self.users = InMemoryUserRepository(self.store)
        self.projects = InMemoryProjectRepository(self.store)
        self.reviews = InMemoryReviewRepository(self.store)
        self.notifications = InMemoryNotificationRepository(self.store)
        self.skills = InMemorySkillRepository(self.store)
        self.rankings = InMemoryRankingRepository(self.store)
        self.metrics = InMemoryMetricsRepository(self.store)
        self.committed = 0  # observable in tests (T5/T6 ordering assertions)

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        pass
