"""Event handlers (DD Sec. 2.1.5 / 2.4.3).

Handlers registered at startup react to the lifecycle events:
notification creation (R35-R38), ranking recomputation on profile updates
(R21, R23), matching-quality metrics (R45). They use the same repository
interfaces as the use cases and run only AFTER the publishing use case has
committed (DD Sec. 2.3.2 ordering guarantee).
"""

from __future__ import annotations

from ..domain.entities import Freelancer, Notification
from ..domain.events import (
    CollaborationCompleted,
    ProfileUpdated,
    ProjectPublished,
    ProposalAccepted,
    ProposalReceived,
    ReviewSubmitted,
)
from ..matching.strategy import MatchingStrategy
from ..repositories.interfaces import UnitOfWork
from .bus import IEventBus


class EventHandlers:
    """Bundles the handlers with their collaborators. Wired in the
    composition root (DD Sec. 2.4.3 'How')."""

    def __init__(self, uow: UnitOfWork, strategy: MatchingStrategy, ranking_size: int):
        self.uow = uow
        self.strategy = strategy
        self.ranking_size = ranking_size  # the configurable N of R19 / C5

    # ------------------------------------------------------------------ #
    # registration
    # ------------------------------------------------------------------ #

    def register_all(self, bus: IEventBus) -> None:
        bus.subscribe(ProjectPublished, self.on_project_published)
        bus.subscribe(ProposalReceived, self.on_proposal_received)
        bus.subscribe(ProposalAccepted, self.on_proposal_accepted)
        bus.subscribe(CollaborationCompleted, self.on_collaboration_completed)
        bus.subscribe(ProfileUpdated, self.on_profile_updated)
        bus.subscribe(ReviewSubmitted, self.on_review_submitted)

    # ------------------------------------------------------------------ #
    # S2: publication side effects (R35, R21) + exposure metric (R45)
    # ------------------------------------------------------------------ #

    def on_project_published(self, event: ProjectPublished) -> None:
        project = self.uow.projects.get(event.project_id)
        if project is None:
            return
        candidates = [
            u for u in self.uow.users.list_freelancers() if isinstance(u, Freelancer)
        ]
        ranking = self.strategy.rank_freelancers(project, candidates)[
            : self.ranking_size
        ]
        # read-optimised projection (DD Sec. 2.4.5)
        self.uow.rankings.save_project_ranking(
            project.id, [(r.entity_id, r.score) for r in ranking]
        )
        # R35 — notify every freelancer in the ranking
        for r in ranking:
            self.uow.notifications.save(
                Notification.create(
                    user_id=r.entity_id,
                    kind="new_compatible_project",
                    message=f'New compatible project: "{project.title}"',
                    related_project_id=project.id,
                )
            )
            # R21 — refresh that freelancer's suggested view
            self._refresh_suggested(r.entity_id)
        # R45 — ranking exposures
        self.uow.metrics.record("rankings_computed")
        self.uow.metrics.record("freelancers_exposed", len(ranking))
        self.uow.commit()

    # ------------------------------------------------------------------ #
    # S3: proposal notification (R36) + outcome metric (R45)
    # ------------------------------------------------------------------ #

    def on_proposal_received(self, event: ProposalReceived) -> None:
        project = self.uow.projects.get(event.project_id)
        title = project.title if project else event.project_id
        self.uow.notifications.save(
            Notification.create(
                user_id=event.client_id,
                kind="new_proposal",
                message=f'New proposal received for "{title}"',
                related_project_id=event.project_id,
            )
        )
        # R45 — was the proposer among the suggested freelancers?
        exposed = {
            fid
            for fid, _ in self.uow.rankings.get_project_ranking(event.project_id)
        }
        self.uow.metrics.record("proposals_submitted")
        if event.freelancer_id in exposed:
            self.uow.metrics.record("proposals_from_suggested")
        self.uow.commit()

    # ------------------------------------------------------------------ #
    # S4: accepted/rejected fan-out (R37) — dispatched only after commit
    # ------------------------------------------------------------------ #

    def on_proposal_accepted(self, event: ProposalAccepted) -> None:
        project = self.uow.projects.get(event.project_id)
        title = project.title if project else event.project_id
        self.uow.notifications.save(
            Notification.create(
                user_id=event.accepted_freelancer_id,
                kind="accepted",
                message=f'Your proposal for "{title}" was accepted',
                related_project_id=event.project_id,
            )
        )
        for _pid, freelancer_id in event.rejected:
            self.uow.notifications.save(
                Notification.create(
                    user_id=freelancer_id,
                    kind="rejected",
                    message=f'Your proposal for "{title}" was rejected',
                    related_project_id=event.project_id,
                )
            )
        # R45 — acceptance outcome
        exposed = {
            fid
            for fid, _ in self.uow.rankings.get_project_ranking(event.project_id)
        }
        self.uow.metrics.record("proposals_accepted")
        if event.accepted_freelancer_id in exposed:
            self.uow.metrics.record("accepted_from_suggested")
        self.uow.commit()

    # ------------------------------------------------------------------ #
    # S5: review window notifications (R30, R38)
    # ------------------------------------------------------------------ #

    def on_collaboration_completed(self, event: CollaborationCompleted) -> None:
        project = self.uow.projects.get(event.project_id)
        title = project.title if project else event.project_id
        for user_id in (event.client_id, event.freelancer_id):
            self.uow.notifications.save(
                Notification.create(
                    user_id=user_id,
                    kind="review_window",
                    message=f'Review window opened for "{title}"',
                    related_project_id=event.project_id,
                )
            )
        self.uow.commit()

    # ------------------------------------------------------------------ #
    # R21 / R23: ranking recomputation on profile updates
    # ------------------------------------------------------------------ #

    def on_profile_updated(self, event: ProfileUpdated) -> None:
        if event.role != "freelancer":
            return
        # R21 — recompute the freelancer's suggested projects
        self._refresh_suggested(event.user_id)
        # R23 — recompute the rankings of the open projects possibly affected
        freelancer = self.uow.users.get(event.user_id)
        if not isinstance(freelancer, Freelancer):
            return
        candidates = [
            u for u in self.uow.users.list_freelancers() if isinstance(u, Freelancer)
        ]
        for project in self.uow.projects.list_open():
            if project.required_skill_ids & freelancer.skill_ids():
                ranking = self.strategy.rank_freelancers(project, candidates)[
                    : self.ranking_size
                ]
                self.uow.rankings.save_project_ranking(
                    project.id, [(r.entity_id, r.score) for r in ranking]
                )
        self.uow.commit()

    def _refresh_suggested(self, freelancer_id: str) -> None:
        freelancer = self.uow.users.get(freelancer_id)
        if not isinstance(freelancer, Freelancer):
            return
        ranking = self.strategy.rank_projects(
            freelancer, self.uow.projects.list_open()
        )[: self.ranking_size]
        self.uow.rankings.save_suggested_projects(
            freelancer_id, [(r.entity_id, r.score) for r in ranking]
        )

    # ------------------------------------------------------------------ #
    # R33 aftermath: reputation already updated in the use case transaction;
    # here only the R45 metric.
    # ------------------------------------------------------------------ #

    def on_review_submitted(self, event: ReviewSubmitted) -> None:
        self.uow.metrics.record("reviews_submitted")
        self.uow.commit()
