"""Use case ``submit_proposal`` (S3).

The domain decides: Project.add_proposal() enforces R13/R17 (open + before
deadline) and R14 (no duplicate proposal). The ProposalReceived event
(R36) is published after the commit.
"""

from __future__ import annotations

from ..domain.entities import Freelancer, Proposal
from ..domain.errors import ValidationError
from ..domain.events import ProposalReceived
from ..events.bus import IEventBus
from ..repositories.interfaces import UnitOfWork


class SubmitProposal:
    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(
        self, freelancer_id: str, project_id: str, cover_letter: str, offer: float
    ) -> Proposal:
        freelancer = self.uow.users.get(freelancer_id)
        if not isinstance(freelancer, Freelancer):
            raise ValidationError("FREELANCER_NOT_FOUND", "submitter must be a freelancer")
        project = self.uow.projects.get_with_proposals(project_id)
        if project is None:
            raise ValidationError("PROJECT_NOT_FOUND", "no such project")
        proposal = project.add_proposal(freelancer_id, cover_letter, offer)
        self.uow.projects.save(project)
        self.uow.commit()
        self.bus.publish(
            ProposalReceived(
                proposal_id=proposal.id,
                project_id=project.id,
                freelancer_id=freelancer_id,
                client_id=project.client_id,
            )
        )
        return proposal
