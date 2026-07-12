"""Use case ``complete_and_review`` (S5).

Two operations: marking the project as completed (R18, opening the
review window R30 via the CollaborationCompleted event), and submitting a
review (R30/R31/R32) with the in-transaction reputation update
(R33) before the ReviewSubmitted event is published.
"""

from __future__ import annotations

from ..domain.entities import Project, Review
from ..domain.errors import ValidationError
from ..events.bus import IEventBus
from ..repositories.interfaces import UnitOfWork


class CompleteProject:
    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(self, client_id: str, project_id: str) -> Project:
        project = self.uow.projects.get_with_proposals(project_id)
        if project is None:
            raise ValidationError("PROJECT_NOT_FOUND", "no such project")
        if project.client_id != client_id:
            raise ValidationError("NOT_OWNER", "only the project owner can complete")
        try:
            events = project.mark_completed()  # R18 in the domain
            self.uow.projects.save(project)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        for event in events:
            self.bus.publish(event)  # -> R30/R38 review-window notifications
        return project


class SubmitReview:
    def __init__(self, uow: UnitOfWork, bus: IEventBus):
        self.uow, self.bus = uow, bus

    def execute(
        self, author_id: str, project_id: str, rating: int, comment: str = ""
    ) -> Review:
        project = self.uow.projects.get_with_proposals(project_id)
        if project is None:
            raise ValidationError("PROJECT_NOT_FOUND", "no such project")
        existing = self.uow.reviews.list_by_project(project_id)
        review, event = Review.create(  # R30/R31/R32 enforced in the domain
            project, author_id, rating, comment, existing
        )
        self.uow.reviews.save(review)
        # R33 — reputation updated in the same transaction, so any
        # subsequent matching computation sees the new value immediately.
        target = self.uow.users.get(review.target_id)
        ratings = [r.rating for r in self.uow.reviews.list_by_target(review.target_id)]
        target.update_reputation(ratings)
        self.uow.users.save(target)
        self.uow.commit()
        self.bus.publish(event)
        return review
