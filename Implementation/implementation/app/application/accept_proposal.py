"""Use case ``accept_proposal`` (S4; DD Sec. 2.3.2).

This is the flow where the transactional design decision lives. The atomic
block of R16 starts when the use case loads the project together with its
proposals, and ends with the single ``projects.save`` + ``commit()``.
Inside the block, the entire decision logic is delegated to the domain:
Project.accept_proposal() performs the FSM checks and applies the three
transitions on the in-memory aggregate. Either all three become visible,
or none does (R16). Concurrent acceptances are serialised at the commit
point: the second transaction finds the project no longer open and the
domain check fails.

The ProposalAccepted event is published strictly AFTER the commit, never
inside the transaction (R37 must not fire for a rolled-back transition).
"""

from __future__ import annotations

from ..domain.entities import Project
from ..domain.errors import ValidationError
from ..events.bus import IEventBus
from ..repositories.interfaces import UnitOfWork


class AcceptProposal:
    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(self, client_id: str, project_id: str, proposal_id: str) -> Project:
        # ------------------- atomic block (R16) -------------------- #
        project = self.uow.projects.get_with_proposals(project_id)
        if project is None:
            raise ValidationError("PROJECT_NOT_FOUND", "no such project")
        if project.client_id != client_id:  # R15 — owner only (R42)
            raise ValidationError("NOT_OWNER", "only the project owner can accept")
        try:
            events = project.accept_proposal(proposal_id)  # FSM checks + 3 transitions
            self.uow.projects.save(project)  # single commit: all three or none
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        # ---------------- after the commit: event publication ------------- #
        for event in events:
            self.bus.publish(event)  # -> R37 notifications
        return project
