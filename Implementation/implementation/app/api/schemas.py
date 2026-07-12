"""Request/response DTOs (DD Sec. 3.1-3.2).

These Pydantic models are the *only* place where the wire format lives; they
are deliberately separate from the domain entities so that the boundary can
evolve without touching the domain (DD Sec. 2.1: the API layer depends on the
application layer, never the reverse). Every response model is built from a
domain entity by an explicit ``from_entity`` constructor.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from ..domain.entities import (
    Freelancer,
    Notification,
    Project,
    Proposal,
    Review,
    Skill,
    User,
)


# --------------------------------------------------------------- accounts -- #


class RegisterIn(BaseModel):
    email: str
    password: str
    role: str = Field(description="'client' or 'freelancer'")


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


class CompetenceIn(BaseModel):
    skill_id: str
    level: str = Field(description="'basic' | 'intermediate' | 'advanced'")


class AvailabilityIn(BaseModel):
    start: date
    end: date


class ProfileIn(BaseModel):
    # client fields
    business_name: Optional[str] = None
    sector: Optional[str] = None
    typical_needs: Optional[str] = None
    # freelancer fields
    hourly_rate: Optional[float] = None
    portfolio_url: Optional[str] = None
    competences: Optional[list[CompetenceIn]] = None
    availabilities: Optional[list[AvailabilityIn]] = None


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    reputation: float
    registered_at: datetime
    business_name: Optional[str] = None
    sector: Optional[str] = None
    hourly_rate: Optional[float] = None
    portfolio_url: Optional[str] = None
    competences: Optional[list[CompetenceIn]] = None
    availabilities: Optional[list[AvailabilityIn]] = None

    @staticmethod
    def from_entity(u: User) -> "UserOut":
        base = UserOut(
            id=u.id,
            email=u.email,
            role=u.role.value,
            reputation=u.reputation,
            registered_at=u.registered_at,
        )
        if isinstance(u, Freelancer):
            base.hourly_rate = u.hourly_rate
            base.portfolio_url = u.portfolio_url
            base.competences = [
                CompetenceIn(skill_id=c.skill_id, level=c.level.value)
                for c in u.competences
            ]
            base.availabilities = [
                AvailabilityIn(start=a.start, end=a.end) for a in u.availabilities
            ]
        else:
            base.business_name = getattr(u, "business_name", "")
            base.sector = getattr(u, "sector", "")
        return base


class SkillOut(BaseModel):
    id: str
    name: str

    @staticmethod
    def from_entity(s: Skill) -> "SkillOut":
        return SkillOut(id=s.id, name=s.name)


class SkillRequestIn(BaseModel):
    name: str


# --------------------------------------------------------------- projects -- #


class ProjectIn(BaseModel):
    title: str
    description: str
    required_skill_ids: list[str]
    max_budget: float
    deadline: date


class ProjectUpdateIn(BaseModel):
    """R45 — partial update of title/description; both optional so a
    client can change just one of the two (legality checked in the
    domain: only while the Project is 'open')."""

    title: Optional[str] = None
    description: Optional[str] = None


class ProposalOut(BaseModel):
    id: str
    project_id: str
    freelancer_id: str
    cover_letter: str
    offer: float
    status: str
    submitted_at: datetime

    @staticmethod
    def from_entity(p: Proposal) -> "ProposalOut":
        return ProposalOut(
            id=p.id,
            project_id=p.project_id,
            freelancer_id=p.freelancer_id,
            cover_letter=p.cover_letter,
            offer=p.offer,
            status=p.status.value,
            submitted_at=p.submitted_at,
        )


class ProjectOut(BaseModel):
    id: str
    client_id: str
    title: str
    description: str
    required_skill_ids: list[str]
    max_budget: float
    deadline: date
    status: str
    published_at: datetime
    proposals: list[ProposalOut] = []

    @staticmethod
    def from_entity(p: Project, with_proposals: bool = True) -> "ProjectOut":
        return ProjectOut(
            id=p.id,
            client_id=p.client_id,
            title=p.title,
            description=p.description,
            required_skill_ids=sorted(p.required_skill_ids),
            max_budget=p.max_budget,
            deadline=p.deadline,
            status=p.status.value,
            published_at=p.published_at,
            proposals=[ProposalOut.from_entity(pr) for pr in p.proposals]
            if with_proposals
            else [],
        )


# -------------------------------------------------------------- proposals -- #


class ProposalIn(BaseModel):
    cover_letter: str
    offer: float


# ---------------------------------------------------------------- reviews -- #


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class ReviewOut(BaseModel):
    id: str
    project_id: str
    author_id: str
    target_id: str
    rating: int
    comment: str
    submitted_at: datetime

    @staticmethod
    def from_entity(r: Review) -> "ReviewOut":
        return ReviewOut(
            id=r.id,
            project_id=r.project_id,
            author_id=r.author_id,
            target_id=r.target_id,
            rating=r.rating,
            comment=r.comment,
            submitted_at=r.submitted_at,
        )


# ---------------------------------------------------------------- ranking -- #


class RankingEntryOut(BaseModel):
    entity_id: str
    score: float


class NotificationOut(BaseModel):
    id: str
    kind: str
    message: str
    created_at: datetime
    related_project_id: Optional[str] = None

    @staticmethod
    def from_entity(n: Notification) -> "NotificationOut":
        return NotificationOut(
            id=n.id,
            kind=n.kind,
            message=n.message,
            created_at=n.created_at,
            related_project_id=n.related_project_id,
        )


class DashboardOut(BaseModel):
    """R39 — the per-user dashboard aggregates the read-side projections."""

    user_id: str
    role: str
    notifications: list[NotificationOut]
    suggested_projects: list[RankingEntryOut] = []
    my_projects: list[ProjectOut] = []
