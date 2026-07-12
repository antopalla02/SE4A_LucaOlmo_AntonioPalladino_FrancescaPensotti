"""Use case ``publish_project`` (S2; DD Sec. 2.3.1).

Three design decisions are realised here:
(1) validation happens in the domain — Project.create() enforces R11/R12;
(2) the ranking computation goes through IMatchingStrategy (R26);
(3) side effects are observer-driven: a single ProjectPublished event is
    published after the commit, and the notification fan-out (R35) and the
    suggested-view refresh (R21) happen in subscribed handlers.

The transaction covers only the persistence of the new project; the
ranking runs after the commit (a matching failure must not roll back a
correctly published project — RASD S2 "empty ranking" alternative flow).
"""

from __future__ import annotations

from datetime import date

from ..domain.entities import Project
from ..domain.enums import Role
from ..domain.errors import ValidationError
from ..domain.events import ProjectPublished
from ..events.bus import IEventBus
from ..repositories.interfaces import UnitOfWork


class PublishProject:
    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(
        self,
        client_id: str,
        title: str,
        description: str,
        required_skill_ids: set[str],
        max_budget: float,
        deadline: date,
    ) -> Project:
        client = self.uow.users.get(client_id)
        if client is None or client.role != Role.CLIENT:
            raise ValidationError("CLIENT_NOT_FOUND", "publisher must be a client")
        for skill_id in required_skill_ids:
            if self.uow.skills.get(skill_id) is None:  # R8 controlled vocabulary
                raise ValidationError(
                    "SKILL_NOT_IN_VOCABULARY",
                    f"skill '{skill_id}' is not in the controlled vocabulary",
                )
        project = Project.create(  # R11 validation + R12 initial state, in the domain
            client_id=client_id,
            title=title,
            description=description,
            required_skill_ids=required_skill_ids,
            max_budget=max_budget,
            deadline=deadline,
        )
        self.uow.projects.save(project)
        self.uow.commit()  # transaction covers only the persistence
        # published AFTER the commit (DD Sec. 2.3.1) — triggers R19/R35/R21
        self.bus.publish(
            ProjectPublished(project_id=project.id, client_id=client_id)
        )
        return project
