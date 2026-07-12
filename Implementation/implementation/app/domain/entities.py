"""Domain entities (DD Sec. 2.1.3 / 2.2.1).

Implementation-level refinement of the conceptual domain model of RASD
Sec. 2.2: User (Client / Freelancer), Skill, Competence, Availability,
Project, Proposal, Review, Notification.

The key design decision (DD Sec. 2.2.1): **state transitions are methods
of the entities themselves**. Each transition method checks the current
state, raises a DomainError when the transition is not legal, applies the
change and returns the list of DomainEvents that the transition implies.
There is no code path that mutates a ``status`` attribute directly, so the
domain rules cannot be bypassed.

Plain Python: no framework, persistence or transport imports
(dependency rules, DD Sec. 2.1.7).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from .enums import MasteryLevel, ProjectStatus, ProposalStatus, Role
from .errors import IllegalTransition, InvariantViolation, ValidationError
from .events import (
    CollaborationCompleted,
    DomainEvent,
    ProposalAccepted,
    ReviewSubmitted,
)

NEUTRAL_REPUTATION = 0.5  # R33: users with no reviews


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Skills and competences (RASD Sec. 2.2, R8)
# --------------------------------------------------------------------------- #


@dataclass
class Skill:
    """Controlled-vocabulary entry (R8). Compared by identity, not string."""

    id: str
    name: str

    @staticmethod
    def create(name: str) -> "Skill":
        name = (name or "").strip()
        if not name:
            raise ValidationError("SKILL_NAME_EMPTY", "skill name must be non-empty")
        return Skill(id=new_id(), name=name)


@dataclass
class SkillRequest:
    """Request for the addition of a new Skill, subject to approval (R8)."""

    id: str
    requester_id: str
    name: str
    approved: bool = False

    @staticmethod
    def create(requester_id: str, name: str) -> "SkillRequest":
        name = (name or "").strip()
        if not name:
            raise ValidationError("SKILL_NAME_EMPTY", "skill name must be non-empty")
        return SkillRequest(id=new_id(), requester_id=requester_id, name=name)


@dataclass
class Competence:
    """Reified Freelancer-Skill relation carrying the mastery level (RASD 2.2)."""

    skill_id: str
    level: MasteryLevel


@dataclass
class Availability:
    """Interval of dates during which the freelancer is free (RASD 2.2)."""

    start: date
    end: date

    def __post_init__(self):
        if self.end < self.start:
            raise ValidationError(
                "AVAILABILITY_INVALID", "availability end precedes start"
            )

    def overlap_days(self, start: date, end: date) -> int:
        lo, hi = max(self.start, start), min(self.end, end)
        return max(0, (hi - lo).days + 1)


# --------------------------------------------------------------------------- #
# Users (RASD Sec. 2.2: User with Client and Freelancer subclasses)
# --------------------------------------------------------------------------- #


@dataclass
class User:
    """Common attributes of both roles. ``reputation`` is stored and
    recomputed on review submission (DD Sec. 2.2.1: read-optimised
    trade-off; R33)."""

    id: str
    email: str
    password_hash: str
    role: Role
    registered_at: datetime
    reputation: float = NEUTRAL_REPUTATION

    def update_reputation(self, ratings: list[int]) -> None:
        """R33: reputation = f(reviews where the user is target),
        normalised in [0,1]; neutral 0.5 with no reviews."""
        if not ratings:
            self.reputation = NEUTRAL_REPUTATION
        else:
            self.reputation = sum((r - 1) / 4 for r in ratings) / len(ratings)


@dataclass
class Client(User):
    """R4 — business name, sector, typical needs."""

    business_name: str = ""
    sector: str = ""
    typical_needs: str = ""


@dataclass
class Freelancer(User):
    """R5 — competences, hourly rate, availability windows, portfolio."""

    competences: list[Competence] = field(default_factory=list)
    hourly_rate: float = 0.0
    availabilities: list[Availability] = field(default_factory=list)
    portfolio_url: Optional[str] = None

    def declare_competence(self, skill_id: str, level: MasteryLevel) -> None:
        """R5 — add or update a competence (one per skill)."""
        for c in self.competences:
            if c.skill_id == skill_id:
                c.level = level
                return
        self.competences.append(Competence(skill_id=skill_id, level=level))

    def add_availability(self, start: date, end: date) -> None:
        """R5 — declare an availability window."""
        self.availabilities.append(Availability(start=start, end=end))

    def skill_ids(self) -> set[str]:
        return {c.skill_id for c in self.competences}


def register_user(email: str, password_hash: str, role: Role) -> User:
    """R1 — factory for the role subclasses; validation of S1 step 2."""
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValidationError("EMAIL_INVALID", "email is not well-formed")
    if not password_hash:
        raise ValidationError("PASSWORD_EMPTY", "password must be non-empty")
    cls = Client if role == Role.CLIENT else Freelancer
    return cls(
        id=new_id(),
        email=email,
        password_hash=password_hash,
        role=role,
        registered_at=utcnow(),
        reputation=NEUTRAL_REPUTATION,
    )


# --------------------------------------------------------------------------- #
# Proposal (RASD Sec. 3.2.2)
# --------------------------------------------------------------------------- #


@dataclass
class Proposal:
    id: str
    project_id: str
    freelancer_id: str
    cover_letter: str
    offer: float
    status: ProposalStatus = ProposalStatus.PENDING
    submitted_at: datetime = field(default_factory=utcnow)

    @staticmethod
    def create(
        project_id: str, freelancer_id: str, cover_letter: str, offer: float
    ) -> "Proposal":
        """S3 step 3 — offer numeric, >= 0, within plausible bounds."""
        if offer is None or offer < 0:
            raise ValidationError("OFFER_INVALID", "economic offer must be >= 0")
        if offer > 10_000_000:
            raise ValidationError("OFFER_INVALID", "economic offer out of bounds")
        return Proposal(
            id=new_id(),
            project_id=project_id,
            freelancer_id=freelancer_id,
            cover_letter=cover_letter or "",
            offer=float(offer),
        )

    # FSM transitions (RASD Sec. 3.2.2). Both terminal states are final.

    def accept(self) -> None:
        if self.status != ProposalStatus.PENDING:
            raise IllegalTransition(
                "PROPOSAL_NOT_PENDING",
                f"cannot accept a proposal in status {self.status.value}",
            )
        self.status = ProposalStatus.ACCEPTED

    def reject(self) -> None:
        if self.status != ProposalStatus.PENDING:
            raise IllegalTransition(
                "PROPOSAL_NOT_PENDING",
                f"cannot reject a proposal in status {self.status.value}",
            )
        self.status = ProposalStatus.REJECTED


# --------------------------------------------------------------------------- #
# Project aggregate (RASD Sec. 3.2.1; DD Sec. 2.2.1, 2.4.4)
# --------------------------------------------------------------------------- #


@dataclass
class Project:
    """Aggregate root: loaded together with its proposals when a transition
    needs them (``projects.get_with_proposals``, DD Sec. 2.4.4)."""

    id: str
    client_id: str
    title: str
    description: str
    required_skill_ids: set[str]
    max_budget: float
    deadline: date
    status: ProjectStatus = ProjectStatus.OPEN
    published_at: datetime = field(default_factory=utcnow)
    proposals: list[Proposal] = field(default_factory=list)

    # -- creation (R11, R12) -------------------------------------------------- #

    @staticmethod
    def create(
        client_id: str,
        title: str,
        description: str,
        required_skill_ids: set[str],
        max_budget: float,
        deadline: date,
        today: Optional[date] = None,
    ) -> "Project":
        """R11 — mandatory fields, non-empty skills, budget >= 0, deadline
        strictly in the future. R12 — initial status = open. The use case
        never constructs a Project in an invalid state (DD Sec. 2.3.1)."""
        today = today or date.today()
        if not (title or "").strip():
            raise ValidationError("PROJECT_TITLE_EMPTY", "title is mandatory")
        if not (description or "").strip():
            raise ValidationError("PROJECT_DESCRIPTION_EMPTY", "description is mandatory")
        if not required_skill_ids:
            raise ValidationError("PROJECT_SKILLS_EMPTY", "at least one required skill")
        if max_budget is None or max_budget < 0:
            raise ValidationError("PROJECT_BUDGET_INVALID", "budget must be >= 0")
        if deadline <= today:
            raise ValidationError(
                "PROJECT_DEADLINE_PAST", "deadline must be strictly in the future"
            )
        return Project(
            id=new_id(),
            client_id=client_id,
            title=title.strip(),
            description=description.strip(),
            required_skill_ids=set(required_skill_ids),
            max_budget=float(max_budget),
            deadline=deadline,
        )

    # -- queries ------------------------------------------------------------ #

    def can_receive_proposals(self, today: Optional[date] = None) -> bool:
        """R13/R17 — only open projects before the deadline accept proposals."""
        today = today or date.today()
        return self.status == ProjectStatus.OPEN and self.deadline > today

    def accepted_proposal(self) -> Optional[Proposal]:
        for p in self.proposals:
            if p.status == ProposalStatus.ACCEPTED:
                return p
        return None

    # -- proposal submission (R13, R14, R17; R14) ---------------------------- #

    def add_proposal(
        self,
        freelancer_id: str,
        cover_letter: str,
        offer: float,
        today: Optional[date] = None,
    ) -> Proposal:
        if not self.can_receive_proposals(today):
            raise IllegalTransition(
                "PROJECT_NOT_OPEN",
                "project does not accept proposals (status is not open or "
                "deadline expired)",  # R17 / S3 exceptions
            )
        if any(p.freelancer_id == freelancer_id for p in self.proposals):
            raise InvariantViolation(
                "R14_DUPLICATE_PROPOSAL",
                "a freelancer cannot have two proposals for the same project",
            )
        proposal = Proposal.create(self.id, freelancer_id, cover_letter, offer)
        self.proposals.append(proposal)
        return proposal

    # -- FSM transitions (RASD Sec. 3.2.1) ----------------------------------- #

    def accept_proposal(self, proposal_id: str) -> list[DomainEvent]:
        """R15/R16 — the entire decision logic of S4, on the in-memory
        aggregate. Performs the FSM checks and applies the three transitions:
        chosen proposal -> accepted, every other pending -> rejected,
        project -> inProgress (R16). Returns the ProposalAccepted
        event; the caller persists the aggregate in ONE commit (R16) and
        publishes the event only after the commit (DD Sec. 2.3.2)."""
        if self.status != ProjectStatus.OPEN:
            raise IllegalTransition(
                "PROJECT_NOT_OPEN",
                f"cannot accept a proposal on a project in status "
                f"{self.status.value}",  # serialises concurrent acceptances
            )
        chosen = next((p for p in self.proposals if p.id == proposal_id), None)
        if chosen is None:
            raise ValidationError("PROPOSAL_NOT_FOUND", "no such proposal")
        chosen.accept()  # (i)
        rejected: list[tuple[str, str]] = []
        for p in self.proposals:
            if p.id != chosen.id and p.status == ProposalStatus.PENDING:
                p.reject()  # (ii)
                rejected.append((p.id, p.freelancer_id))
        self.status = ProjectStatus.IN_PROGRESS  # (iii) — R16 holds
        return [
            ProposalAccepted(
                project_id=self.id,
                accepted_proposal_id=chosen.id,
                accepted_freelancer_id=chosen.freelancer_id,
                rejected=tuple(rejected),
            )
        ]

    def mark_completed(self) -> list[DomainEvent]:
        """R18 — completed only from inProgress. Returns the
        CollaborationCompleted event (opens the review window, R30)."""
        if self.status != ProjectStatus.IN_PROGRESS:
            raise IllegalTransition(
                "R18_NOT_IN_PROGRESS",
                "a project can transition to completed only from inProgress",
            )
        accepted = self.accepted_proposal()
        if accepted is None:  # defensive: R16 should make this impossible
            raise InvariantViolation(
                "R16_NO_ACCEPTED_PROPOSAL",
                "in-progress project without an accepted proposal",
            )
        self.status = ProjectStatus.COMPLETED
        return [
            CollaborationCompleted(
                project_id=self.id,
                client_id=self.client_id,
                freelancer_id=accepted.freelancer_id,
            )
        ]

    def update_metadata(
        self, title: Optional[str] = None, description: Optional[str] = None
    ) -> None:
        """RASD Sec. 3.2.1 — self-transition allowed only in ``open``."""
        if self.status != ProjectStatus.OPEN:
            raise IllegalTransition(
                "PROJECT_NOT_OPEN", "metadata can be updated only while open"
            )
        if title is not None and title.strip():
            self.title = title.strip()
        if description is not None and description.strip():
            self.description = description.strip()


# --------------------------------------------------------------------------- #
# Review (R30-R33; R31/R32; single state transition — RASD Sec. 3.2)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Review:
    """Immutable by construction: no update method exists (R32)."""

    id: str
    project_id: str
    author_id: str
    target_id: str
    rating: int
    comment: str
    submitted_at: datetime

    @staticmethod
    def create(
        project: Project,
        author_id: str,
        rating: int,
        comment: str,
        existing_for_project: list["Review"],
    ) -> tuple["Review", ReviewSubmitted]:
        """R31 — enforces R31 (completed project, parties only,
        author != target) and R31 (one review per (project, author))."""
        if project.status != ProjectStatus.COMPLETED:
            raise InvariantViolation(
                "R31_PROJECT_NOT_COMPLETED",
                "reviews exist only for completed projects",
            )
        accepted = project.accepted_proposal()
        parties = {project.client_id, accepted.freelancer_id}
        if author_id not in parties:
            raise InvariantViolation(
                "R31_AUTHOR_NOT_PARTY",
                "the author must be one of the two parties of the project",
            )
        target_id = (parties - {author_id}).pop()  # author != target by shape
        if not isinstance(rating, int) or rating not in (1, 2, 3, 4, 5):
            raise ValidationError("RATING_INVALID", "rating must be in {1..5}")
        if any(r.author_id == author_id for r in existing_for_project):
            raise InvariantViolation(
                "R31_DUPLICATE_REVIEW",
                "each party may review the counterpart at most once",
            )
        review = Review(
            id=new_id(),
            project_id=project.id,
            author_id=author_id,
            target_id=target_id,
            rating=rating,
            comment=comment or "",
            submitted_at=utcnow(),
        )
        event = ReviewSubmitted(
            review_id=review.id,
            project_id=project.id,
            author_id=author_id,
            target_id=target_id,
            rating=rating,
        )
        return review, event


# --------------------------------------------------------------------------- #
# Notification (MP3; R35-R38)
# --------------------------------------------------------------------------- #


@dataclass
class Notification:
    id: str
    user_id: str
    kind: str  # new_compatible_project | new_proposal | accepted | rejected | review_window
    message: str
    created_at: datetime
    related_project_id: Optional[str] = None

    @staticmethod
    def create(
        user_id: str, kind: str, message: str, related_project_id: Optional[str] = None
    ) -> "Notification":
        return Notification(
            id=new_id(),
            user_id=user_id,
            kind=kind,
            message=message,
            created_at=utcnow(),
            related_project_id=related_project_id,
        )
