"""Repository interfaces (DD Sec. 2.1.6 / 2.4.4 — *Repository* pattern).

One interface per aggregate, declared next to the domain and implemented
by the infrastructure: SQLAlchemy/SQLite at runtime, in-memory dictionaries
for the test suite (rationale anticipated in RASD Sec. 2.6.2 / DEP1).

Operations are aggregate-oriented (``get_with_proposals``, ``save``,
``list_open``) rather than generic CRUD on rows: the unit of loading and
saving is the aggregate that the domain methods operate on.

``UnitOfWork`` bundles the repositories and the transactional boundary:
the atomic block of R16 is delimited in the use case around ``commit()``
(DD Sec. 2.1.2 / 2.3.2, R16).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from ..domain.entities import (
    Notification,
    Project,
    Review,
    Skill,
    SkillRequest,
    User,
)


class IUserRepository(ABC):
    @abstractmethod
    def get(self, user_id: str) -> Optional[User]: ...

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    def exists_by_email(self, email: str) -> bool:
        """R2 — duplicate-email check."""

    @abstractmethod
    def save(self, user: User) -> None: ...

    @abstractmethod
    def list_freelancers(self) -> list[User]: ...

    @abstractmethod
    def search_freelancers(
        self,
        skill_ids: Optional[set[str]] = None,
        rate_min: Optional[float] = None,
        rate_max: Optional[float] = None,
        available_from: Optional[date] = None,
        available_to: Optional[date] = None,
    ) -> list[User]:
        """R27 — manual search over the freelancer catalogue."""


class IProjectRepository(ABC):
    @abstractmethod
    def get(self, project_id: str) -> Optional[Project]: ...

    @abstractmethod
    def get_with_proposals(self, project_id: str) -> Optional[Project]:
        """DD Sec. 2.4.4 — returns the Project together with its Proposals,
        because accept_proposal() needs to transition them together inside
        one atomic block."""

    @abstractmethod
    def save(self, project: Project) -> None:
        """Persists the aggregate (project AND its proposals) in one commit
        boundary (R16)."""

    @abstractmethod
    def list_open(self) -> list[Project]: ...

    @abstractmethod
    def list_by_client(self, client_id: str) -> list[Project]: ...

    @abstractmethod
    def list_with_proposals_by_freelancer(self, freelancer_id: str) -> list[Project]:
        """Dashboard support (R39): the projects a freelancer applied to."""

    @abstractmethod
    def search_open(
        self,
        skill_ids: Optional[set[str]] = None,
        budget_min: Optional[float] = None,
        budget_max: Optional[float] = None,
        deadline_from: Optional[date] = None,
        deadline_to: Optional[date] = None,
    ) -> list[Project]:
        """R28 — manual search over the open-project catalogue."""


class IReviewRepository(ABC):
    @abstractmethod
    def save(self, review: Review) -> None: ...

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[Review]: ...

    @abstractmethod
    def list_by_target(self, target_id: str) -> list[Review]:
        """R33 — the reviews feeding a user's reputation."""


class INotificationRepository(ABC):
    @abstractmethod
    def save(self, notification: Notification) -> None: ...

    @abstractmethod
    def list_by_user(self, user_id: str) -> list[Notification]: ...


class ISkillRepository(ABC):
    @abstractmethod
    def get(self, skill_id: str) -> Optional[Skill]: ...

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Skill]: ...

    @abstractmethod
    def save(self, skill: Skill) -> None: ...

    @abstractmethod
    def list_all(self) -> list[Skill]: ...

    @abstractmethod
    def save_request(self, request: SkillRequest) -> None:
        """R8 — request mechanism for new skills."""

    @abstractmethod
    def list_requests(self) -> list[SkillRequest]: ...


class IRankingRepository(ABC):
    """Read-optimised projection of the rankings, refreshed by event
    handlers (DD Sec. 2.4.5 — the only CQRS-flavoured concession)."""

    @abstractmethod
    def save_project_ranking(self, project_id: str, ranking: list[tuple[str, float]]) -> None: ...

    @abstractmethod
    def get_project_ranking(self, project_id: str) -> list[tuple[str, float]]: ...

    @abstractmethod
    def save_suggested_projects(self, freelancer_id: str, ranking: list[tuple[str, float]]) -> None: ...

    @abstractmethod
    def get_suggested_projects(self, freelancer_id: str) -> list[tuple[str, float]]:
        """R21 — the freelancer's 'suggested projects' view."""


class IMetricsRepository(ABC):
    """R45 — exposures and outcomes recorded by event handlers, so the
    active strategy can be assessed without changes to application code."""

    @abstractmethod
    def record(self, metric: str, amount: int = 1) -> None: ...

    @abstractmethod
    def snapshot(self) -> dict[str, int]: ...


class UnitOfWork(ABC):
    """Bundle of repositories sharing one transactional context.

    The use case draws the atomic block of R16 around ``commit()``
    (DD Sec. 2.1.2): every mutation between the start of the use case and
    commit() becomes visible atomically, or not at all (R16).
    """

    users: IUserRepository
    projects: IProjectRepository
    reviews: IReviewRepository
    notifications: INotificationRepository
    skills: ISkillRepository
    rankings: IRankingRepository
    metrics: IMetricsRepository

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
