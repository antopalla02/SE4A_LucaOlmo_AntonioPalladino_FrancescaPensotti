"""Use case ``register_user`` (S1) and profile update (R6).

Orchestration only (DD Sec. 2.1.2): loads/saves through the repository
interfaces, mutates domain entities (which enforce their own invariants),
publishes lifecycle events after the commit.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..domain.entities import Freelancer, SkillRequest, User, register_user as _factory
from ..domain.enums import MasteryLevel, Role
from ..domain.errors import InvariantViolation, ValidationError
from ..domain.events import ProfileUpdated
from ..events.bus import IEventBus
from ..repositories.interfaces import UnitOfWork


class RegisterUser:
    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(self, email: str, password_hash: str, role: str) -> User:
        """S1 steps 1-2: R1 (registration), R2 (duplicate email)."""
        if self.uow.users.exists_by_email(email):
            raise InvariantViolation(
                "EMAIL_DUPLICATE", "email already associated to another account"
            )
        user = _factory(email, password_hash, Role(role))
        self.uow.users.save(user)
        self.uow.commit()
        return user


class UpdateProfile:
    """S1 steps 3-4 / R4, R5, R6, R7 — persisted (R7) before returning control;
    publishes ProfileUpdated after the commit (triggers R21/R23)."""

    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(
        self,
        user_id: str,
        *,
        business_name: Optional[str] = None,
        sector: Optional[str] = None,
        typical_needs: Optional[str] = None,
        hourly_rate: Optional[float] = None,
        portfolio_url: Optional[str] = None,
        competences: Optional[list[tuple[str, str]]] = None,  # (skill_id, level)
        availabilities: Optional[list[tuple[date, date]]] = None,
    ) -> User:
        user = self.uow.users.get(user_id)
        if user is None:
            raise ValidationError("USER_NOT_FOUND", "no such user")

        if user.role == Role.CLIENT:
            if business_name is not None:
                user.business_name = business_name
            if sector is not None:
                user.sector = sector
            if typical_needs is not None:
                user.typical_needs = typical_needs
        else:
            assert isinstance(user, Freelancer)
            if hourly_rate is not None:
                if hourly_rate < 0:
                    raise ValidationError("RATE_INVALID", "hourly rate must be >= 0")
                user.hourly_rate = float(hourly_rate)
            if portfolio_url is not None:
                user.portfolio_url = portfolio_url or None
            if competences is not None:
                for skill_id, level in competences:
                    # R8/R9 — reject a Competence whose Skill is not in the vocabulary
                    if self.uow.skills.get(skill_id) is None:
                        raise ValidationError(
                            "SKILL_NOT_IN_VOCABULARY",
                            f"skill '{skill_id}' is not in the controlled vocabulary",
                        )
                    user.declare_competence(skill_id, MasteryLevel(level))
            if availabilities is not None:
                for start, end in availabilities:
                    user.add_availability(start, end)

        self.uow.users.save(user)
        self.uow.commit()  # R7 — persisted before returning control
        self.bus.publish(ProfileUpdated(user_id=user.id, role=user.role.value))
        return user


class RequestSkill:
    """R8 — request mechanism for the addition of a new Skill."""

    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(self, requester_id: str, name: str) -> SkillRequest:
        request = SkillRequest.create(requester_id, name)
        self.uow.skills.save_request(request)
        self.uow.commit()
        return request
