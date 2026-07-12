"""Enumerations backing the ``status``/``role``/``level`` attributes.

State names match exactly the values introduced in RASD Sec. 2.2 and the
FSMs of RASD Sec. 3.2 (DD Sec. 2.2.1: "the explicit enumerations backing
the status attributes").
"""

from enum import Enum


class Role(str, Enum):
    CLIENT = "client"
    FREELANCER = "freelancer"


class ProjectStatus(str, Enum):
    """RASD Sec. 3.2.1 — three states, two non-trivial transitions."""

    OPEN = "open"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"


class ProposalStatus(str, Enum):
    """RASD Sec. 3.2.2 — pending is the only non-terminal state."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MasteryLevel(str, Enum):
    """RASD Sec. 1.3.1 (Skill): mastery level of a Competence."""

    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
