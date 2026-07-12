"""Use case ``update_project`` (R45).

The Client owner of a Project may update its title and/or description
while the Project is still ``open``; the invariant is enforced in the
domain by ``Project.update_metadata()`` (RASD Sec. 3.2.1 — self-transition
legal only in ``open``). This is a simple metadata edit: it does not
change the Project's status and it does not emit a domain event, so no
event bus is involved (unlike ``publish_project`` or ``complete_and_review``).
"""

from __future__ import annotations

from typing import Optional

from ..domain.entities import Project
from ..domain.errors import ValidationError
from ..repositories.interfaces import UnitOfWork


class UpdateProject:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    def execute(
        self,
        client_id: str,
        project_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Project:
        project = self.uow.projects.get_with_proposals(project_id)
        if project is None:
            raise ValidationError("PROJECT_NOT_FOUND", "no such project")
        if project.client_id != client_id:
            raise ValidationError(
                "NOT_OWNER", "only the project owner can update it"
            )
        project.update_metadata(title=title, description=description)  # R45
        self.uow.projects.save(project)
        self.uow.commit()
        return project
