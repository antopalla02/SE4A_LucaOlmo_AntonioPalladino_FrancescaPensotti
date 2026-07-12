"""Typed domain events.

Plain immutable dataclasses produced *by the domain entities* as return
values of their transition methods (DD Sec. 2.2.1) and published *by the
use cases* strictly after the transaction commit (DD Sec. 2.3.2). The
domain decides *which* events occurred; it has no dependency on the event
bus that will dispatch them.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime = field(default_factory=_now, init=False)


@dataclass(frozen=True)
class ProjectPublished(DomainEvent):
    """S2 step 5 — triggers R35 (notifications) and R21 (suggested view)."""

    project_id: str
    client_id: str


@dataclass(frozen=True)
class ProposalReceived(DomainEvent):
    """S3 step 4 — triggers R36 (notification to the project owner)."""

    proposal_id: str
    project_id: str
    freelancer_id: str
    client_id: str


@dataclass(frozen=True)
class ProposalAccepted(DomainEvent):
    """S4 step 4 — triggers R37 (accepted/rejected notifications).

    Carries the identifiers of the accepted and rejected proposals
    (DD Sec. 2.2.1).
    """

    project_id: str
    accepted_proposal_id: str
    accepted_freelancer_id: str
    rejected: tuple  # tuple[(proposal_id, freelancer_id), ...]


@dataclass(frozen=True)
class CollaborationCompleted(DomainEvent):
    """S5 step 2 — triggers R30/R38 (review window notifications)."""

    project_id: str
    client_id: str
    freelancer_id: str


@dataclass(frozen=True)
class ReviewSubmitted(DomainEvent):
    """S5 step 4 — reputation already updated in-transaction (R33);
    handlers use this for the matching-quality metrics (R45)."""

    review_id: str
    project_id: str
    author_id: str
    target_id: str
    rating: int


@dataclass(frozen=True)
class ProfileUpdated(DomainEvent):
    """S1 step 4 / R6 — triggers R21 and R23 (ranking recomputation)."""

    user_id: str
    role: str
