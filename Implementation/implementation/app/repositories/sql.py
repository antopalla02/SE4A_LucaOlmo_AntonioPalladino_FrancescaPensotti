"""SQLite/SQLAlchemy implementation of the repository interfaces
(DD Sec. 2.1.6 / 2.4.4, increment 4).

The ORM mapping is kept in this package so that the ``domain`` package
remains free of ORM imports (DD Sec. 2.4.4 'How'): the rows below are
infrastructure records, converted to/from domain entities by the
repositories. ``SqlUnitOfWork`` carries the transactional guarantees that
the atomic block of R16 requires (R16): every mutation between the start
of the use case and ``commit()`` becomes visible in one transaction.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from ..domain.entities import (
    Availability,
    Client,
    Competence,
    Freelancer,
    Notification,
    Project,
    Proposal,
    Review,
    Skill,
    SkillRequest,
    User,
)
from ..domain.enums import MasteryLevel, ProjectStatus, ProposalStatus, Role
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


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# ORM rows (infrastructure records, NOT domain entities)
# --------------------------------------------------------------------------- #


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    registered_at: Mapped[datetime] = mapped_column(DateTime)
    reputation: Mapped[float] = mapped_column(Float, default=0.5)
    # client fields
    business_name: Mapped[str] = mapped_column(String, default="")
    sector: Mapped[str] = mapped_column(String, default="")
    typical_needs: Mapped[str] = mapped_column(String, default="")
    # freelancer fields
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    competences: Mapped[list["CompetenceRow"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    availabilities: Mapped[list["AvailabilityRow"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class CompetenceRow(Base):
    __tablename__ = "competences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"))
    level: Mapped[str] = mapped_column(String)


class AvailabilityRow(Base):
    __tablename__ = "availabilities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)


class SkillRow(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)


class SkillRequestRow(Base):
    __tablename__ = "skill_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    requester_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    required_skill_ids: Mapped[str] = mapped_column(Text)  # JSON list
    max_budget: Mapped[float] = mapped_column(Float)
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    # Optimistic-lock guard (DD Sec. 2.3.2 / R16): two transactions that read
    # the same open project cannot both persist a transition. SQLAlchemy adds
    # "AND version = :old" to every UPDATE; the loser of the race matches zero
    # rows and raises StaleDataError, which is exactly the serialisation point
    # the acceptance flow relies on (R16).
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    __mapper_args__ = {"version_id_col": version}
    proposals: Mapped[list["ProposalRow"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class ProposalRow(Base):
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    freelancer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    cover_letter: Mapped[str] = mapped_column(Text)
    offer: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)


class ReviewRow(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    author_id: Mapped[str] = mapped_column(String, index=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)


class NotificationRow(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    related_project_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class RankingRow(Base):
    """Read-optimised projection (DD Sec. 2.4.5)."""

    __tablename__ = "rankings"
    key: Mapped[str] = mapped_column(String, primary_key=True)  # kind:owner_id
    payload: Mapped[str] = mapped_column(Text)  # JSON [(id, score), ...]


class MetricRow(Base):
    __tablename__ = "metrics"
    name: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- #
# row <-> entity converters
# --------------------------------------------------------------------------- #


def _user_to_entity(row: UserRow) -> User:
    common = dict(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        role=Role(row.role),
        registered_at=row.registered_at,
        reputation=row.reputation,
    )
    if row.role == Role.CLIENT.value:
        return Client(
            **common,
            business_name=row.business_name,
            sector=row.sector,
            typical_needs=row.typical_needs,
        )
    return Freelancer(
        **common,
        hourly_rate=row.hourly_rate,
        portfolio_url=row.portfolio_url,
        competences=[
            Competence(skill_id=c.skill_id, level=MasteryLevel(c.level))
            for c in row.competences
        ],
        availabilities=[
            Availability(start=a.start, end=a.end) for a in row.availabilities
        ],
    )


def _proposal_to_entity(row: ProposalRow) -> Proposal:
    return Proposal(
        id=row.id,
        project_id=row.project_id,
        freelancer_id=row.freelancer_id,
        cover_letter=row.cover_letter,
        offer=row.offer,
        status=ProposalStatus(row.status),
        submitted_at=row.submitted_at,
    )


def _project_to_entity(row: ProjectRow, with_proposals: bool = True) -> Project:
    return Project(
        id=row.id,
        client_id=row.client_id,
        title=row.title,
        description=row.description,
        required_skill_ids=set(json.loads(row.required_skill_ids)),
        max_budget=row.max_budget,
        deadline=row.deadline,
        status=ProjectStatus(row.status),
        published_at=row.published_at,
        proposals=[_proposal_to_entity(p) for p in row.proposals]
        if with_proposals
        else [],
    )


# --------------------------------------------------------------------------- #
# repositories
# --------------------------------------------------------------------------- #


class SqlUserRepository(IUserRepository):
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: str) -> Optional[User]:
        row = self.session.get(UserRow, user_id)
        return _user_to_entity(row) if row else None

    def get_by_email(self, email: str) -> Optional[User]:
        row = self.session.scalar(
            select(UserRow).where(UserRow.email == email.strip().lower())
        )
        return _user_to_entity(row) if row else None

    def exists_by_email(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    def save(self, user: User) -> None:
        row = self.session.get(UserRow, user.id) or UserRow(id=user.id)
        row.email = user.email
        row.password_hash = user.password_hash
        row.role = user.role.value
        row.registered_at = user.registered_at
        row.reputation = user.reputation
        if isinstance(user, Client):
            row.business_name = user.business_name
            row.sector = user.sector
            row.typical_needs = user.typical_needs
        if isinstance(user, Freelancer):
            row.hourly_rate = user.hourly_rate
            row.portfolio_url = user.portfolio_url
            row.competences = [
                CompetenceRow(user_id=user.id, skill_id=c.skill_id, level=c.level.value)
                for c in user.competences
            ]
            row.availabilities = [
                AvailabilityRow(user_id=user.id, start=a.start, end=a.end)
                for a in user.availabilities
            ]
        self.session.add(row)
        self.session.flush()

    def list_freelancers(self) -> list[User]:
        rows = self.session.scalars(
            select(UserRow).where(UserRow.role == Role.FREELANCER.value)
        )
        return [_user_to_entity(r) for r in rows]

    def search_freelancers(
        self,
        skill_ids=None,
        rate_min=None,
        rate_max=None,
        available_from=None,
        available_to=None,
    ) -> list[User]:
        result = []
        for f in self.list_freelancers():
            if skill_ids and not (set(skill_ids) <= f.skill_ids()):
                continue
            if rate_min is not None and f.hourly_rate < rate_min:
                continue
            if rate_max is not None and f.hourly_rate > rate_max:
                continue
            if available_from is not None and available_to is not None:
                if not any(
                    a.overlap_days(available_from, available_to) > 0
                    for a in f.availabilities
                ):
                    continue
            result.append(f)
        return result


class SqlProjectRepository(IProjectRepository):
    def __init__(self, session: Session):
        self.session = session

    def get(self, project_id: str) -> Optional[Project]:
        row = self.session.get(ProjectRow, project_id)
        return _project_to_entity(row) if row else None

    def get_with_proposals(self, project_id: str) -> Optional[Project]:
        return self.get(project_id)  # proposals loaded eagerly (selectin)

    def save(self, project: Project) -> None:
        row = self.session.get(ProjectRow, project.id) or ProjectRow(id=project.id)
        row.client_id = project.client_id
        row.title = project.title
        row.description = project.description
        row.required_skill_ids = json.dumps(sorted(project.required_skill_ids))
        row.max_budget = project.max_budget
        row.deadline = project.deadline
        row.status = project.status.value
        row.published_at = project.published_at
        existing = {p.id: p for p in row.proposals}
        rows = []
        for p in project.proposals:
            prow = existing.get(p.id) or ProposalRow(id=p.id)
            prow.project_id = project.id
            prow.freelancer_id = p.freelancer_id
            prow.cover_letter = p.cover_letter
            prow.offer = p.offer
            prow.status = p.status.value
            prow.submitted_at = p.submitted_at
            rows.append(prow)
        row.proposals = rows
        self.session.add(row)
        self.session.flush()

    def list_open(self) -> list[Project]:
        rows = self.session.scalars(
            select(ProjectRow).where(ProjectRow.status == ProjectStatus.OPEN.value)
        )
        return [_project_to_entity(r) for r in rows]

    def list_by_client(self, client_id: str) -> list[Project]:
        rows = self.session.scalars(
            select(ProjectRow).where(ProjectRow.client_id == client_id)
        )
        return [_project_to_entity(r) for r in rows]

    def list_with_proposals_by_freelancer(self, freelancer_id: str) -> list[Project]:
        pids = self.session.scalars(
            select(ProposalRow.project_id).where(
                ProposalRow.freelancer_id == freelancer_id
            )
        ).all()
        rows = self.session.scalars(
            select(ProjectRow).where(ProjectRow.id.in_(set(pids)))
        )
        return [_project_to_entity(r) for r in rows]

    def search_open(
        self,
        skill_ids=None,
        budget_min=None,
        budget_max=None,
        deadline_from=None,
        deadline_to=None,
    ) -> list[Project]:
        result = []
        for p in self.list_open():
            if skill_ids and not (set(skill_ids) & p.required_skill_ids):
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


class SqlReviewRepository(IReviewRepository):
    def __init__(self, session: Session):
        self.session = session

    def save(self, review: Review) -> None:
        self.session.add(
            ReviewRow(
                id=review.id,
                project_id=review.project_id,
                author_id=review.author_id,
                target_id=review.target_id,
                rating=review.rating,
                comment=review.comment,
                submitted_at=review.submitted_at,
            )
        )
        self.session.flush()

    def _to_entity(self, r: ReviewRow) -> Review:
        return Review(
            id=r.id,
            project_id=r.project_id,
            author_id=r.author_id,
            target_id=r.target_id,
            rating=r.rating,
            comment=r.comment,
            submitted_at=r.submitted_at,
        )

    def list_by_project(self, project_id: str) -> list[Review]:
        rows = self.session.scalars(
            select(ReviewRow).where(ReviewRow.project_id == project_id)
        )
        return [self._to_entity(r) for r in rows]

    def list_by_target(self, target_id: str) -> list[Review]:
        rows = self.session.scalars(
            select(ReviewRow).where(ReviewRow.target_id == target_id)
        )
        return [self._to_entity(r) for r in rows]


class SqlNotificationRepository(INotificationRepository):
    def __init__(self, session: Session):
        self.session = session

    def save(self, n: Notification) -> None:
        self.session.add(
            NotificationRow(
                id=n.id,
                user_id=n.user_id,
                kind=n.kind,
                message=n.message,
                created_at=n.created_at,
                related_project_id=n.related_project_id,
            )
        )
        self.session.flush()

    def list_by_user(self, user_id: str) -> list[Notification]:
        rows = self.session.scalars(
            select(NotificationRow)
            .where(NotificationRow.user_id == user_id)
            .order_by(NotificationRow.created_at)
        )
        return [
            Notification(
                id=r.id,
                user_id=r.user_id,
                kind=r.kind,
                message=r.message,
                created_at=r.created_at,
                related_project_id=r.related_project_id,
            )
            for r in rows
        ]


class SqlSkillRepository(ISkillRepository):
    def __init__(self, session: Session):
        self.session = session

    def get(self, skill_id: str) -> Optional[Skill]:
        row = self.session.get(SkillRow, skill_id)
        return Skill(id=row.id, name=row.name) if row else None

    def get_by_name(self, name: str) -> Optional[Skill]:
        row = self.session.scalar(select(SkillRow).where(SkillRow.name == name.strip()))
        return Skill(id=row.id, name=row.name) if row else None

    def save(self, skill: Skill) -> None:
        row = self.session.get(SkillRow, skill.id) or SkillRow(id=skill.id)
        row.name = skill.name
        self.session.add(row)
        self.session.flush()

    def list_all(self) -> list[Skill]:
        rows = self.session.scalars(select(SkillRow).order_by(SkillRow.name))
        return [Skill(id=r.id, name=r.name) for r in rows]

    def save_request(self, request: SkillRequest) -> None:
        self.session.add(
            SkillRequestRow(
                id=request.id,
                requester_id=request.requester_id,
                name=request.name,
                approved=request.approved,
            )
        )
        self.session.flush()

    def list_requests(self) -> list[SkillRequest]:
        rows = self.session.scalars(select(SkillRequestRow))
        return [
            SkillRequest(
                id=r.id, requester_id=r.requester_id, name=r.name, approved=r.approved
            )
            for r in rows
        ]


class SqlRankingRepository(IRankingRepository):
    def __init__(self, session: Session):
        self.session = session

    def _save(self, key: str, ranking) -> None:
        row = self.session.get(RankingRow, key) or RankingRow(key=key)
        row.payload = json.dumps([list(t) for t in ranking])
        self.session.add(row)
        self.session.flush()

    def _get(self, key: str):
        row = self.session.get(RankingRow, key)
        return [tuple(t) for t in json.loads(row.payload)] if row else []

    def save_project_ranking(self, project_id, ranking):
        self._save(f"project:{project_id}", ranking)

    def get_project_ranking(self, project_id):
        return self._get(f"project:{project_id}")

    def save_suggested_projects(self, freelancer_id, ranking):
        self._save(f"suggested:{freelancer_id}", ranking)

    def get_suggested_projects(self, freelancer_id):
        return self._get(f"suggested:{freelancer_id}")


class SqlMetricsRepository(IMetricsRepository):
    def __init__(self, session: Session):
        self.session = session

    def record(self, metric: str, amount: int = 1) -> None:
        row = self.session.get(MetricRow, metric) or MetricRow(name=metric, value=0)
        row.value += amount
        self.session.add(row)
        self.session.flush()

    def snapshot(self) -> dict[str, int]:
        rows = self.session.scalars(select(MetricRow))
        return {r.name: r.value for r in rows}


# --------------------------------------------------------------------------- #
# Unit of Work
# --------------------------------------------------------------------------- #


def make_engine(database_url: str):
    return create_engine(database_url, connect_args={"check_same_thread": False})


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)


class SqlUnitOfWork(UnitOfWork):
    """One SQLAlchemy session = one transactional context. ``commit()`` is
    the single point at which the aggregate mutations of a use case become
    visible (R16); concurrent acceptances are serialised here
    (DD Sec. 2.3.2 / 5.2 integration point 1)."""

    def __init__(self, session: Session):
        self.session = session
        self.users = SqlUserRepository(session)
        self.projects = SqlProjectRepository(session)
        self.reviews = SqlReviewRepository(session)
        self.notifications = SqlNotificationRepository(session)
        self.skills = SqlSkillRepository(session)
        self.rankings = SqlRankingRepository(session)
        self.metrics = SqlMetricsRepository(session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


def session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
