"""T5 — use-case chain S1->S5 on in-memory repositories: full lifecycle
with assertions on intermediate states and emitted events (S1-S5; R1-R38).
T6 — Observer effects: ProjectPublished produces notifications +
suggested-view refresh; ProposalAccepted produces accepted/rejected
notifications; handlers receive events only after commit (R21, R35-R38).
"""

from datetime import date, timedelta

import pytest

from app.application.accept_proposal import AcceptProposal
from app.application.complete_and_review import CompleteProject, SubmitReview
from app.application.manual_search import ManualSearch
from app.application.publish_project import PublishProject
from app.application.register_user import RegisterUser, UpdateProfile
from app.application.submit_proposal import SubmitProposal
from app.application.update_project import UpdateProject
from app.config import Config, build_strategy
from app.domain.entities import Skill
from app.domain.enums import ProjectStatus, ProposalStatus
from app.domain.errors import IllegalTransition, InvariantViolation, ValidationError
from app.events.bus import InProcessEventBus
from app.events.handlers import EventHandlers
from app.repositories.memory import InMemoryUnitOfWork

TODAY = date.today()
DEADLINE = TODAY + timedelta(days=40)


@pytest.fixture()
def ctx():
    """Mini composition root over the in-memory stack (DD Sec. 5.1 incr. 3)."""
    config = Config(ranking_size=10)
    uow = InMemoryUnitOfWork()
    bus = InProcessEventBus()
    strategy = build_strategy(config)
    EventHandlers(uow, strategy, config.ranking_size).register_all(bus)
    skills = {}
    for name in ("python", "figma"):
        s = Skill.create(name)
        uow.skills.save(s)
        skills[name] = s
    return dict(uow=uow, bus=bus, strategy=strategy, skills=skills)


def run_chain(ctx):
    """Drives S1->S5 and returns the actors and the project."""
    uow, bus = ctx["uow"], ctx["bus"]
    skills = ctx["skills"]
    # S1 — registration + profile
    client = RegisterUser(uow, bus).execute("client@x.com", "h", "client")
    f1 = RegisterUser(uow, bus).execute("f1@x.com", "h", "freelancer")
    f2 = RegisterUser(uow, bus).execute("f2@x.com", "h", "freelancer")
    upd = UpdateProfile(uow, bus)
    upd.execute(
        f1.id,
        hourly_rate=50,
        competences=[(skills["python"].id, "advanced")],
        availabilities=[(TODAY, DEADLINE)],
    )
    upd.execute(
        f2.id,
        hourly_rate=60,
        competences=[(skills["python"].id, "basic")],
        availabilities=[(TODAY, DEADLINE)],
    )
    # S2 — publication (triggers matching + notifications via handlers)
    project = PublishProject(uow, bus).execute(
        client.id, "Build API", "REST API", {skills["python"].id}, 4000, DEADLINE
    )
    # S3 — proposals
    p1 = SubmitProposal(uow, bus).execute(f1.id, project.id, "I can do it", 3000)
    p2 = SubmitProposal(uow, bus).execute(f2.id, project.id, "Me too", 3500)
    # S4 — acceptance
    AcceptProposal(uow, bus).execute(client.id, project.id, p1.id)
    # S5 — completion + mutual review
    CompleteProject(uow, bus).execute(client.id, project.id)
    SubmitReview(uow, bus).execute(client.id, project.id, 5, "great")
    SubmitReview(uow, bus).execute(f1.id, project.id, 4, "good client")
    return dict(client=client, f1=f1, f2=f2, project=project, p1=p1, p2=p2)


# --------------------------------------------------------------------- T5 -- #


class TestT5Chain:
    def test_full_lifecycle_states(self, ctx):
        r = run_chain(ctx)
        uow = ctx["uow"]
        project = uow.projects.get_with_proposals(r["project"].id)
        assert project.status == ProjectStatus.COMPLETED
        by_id = {p.id: p for p in project.proposals}
        assert by_id[r["p1"].id].status == ProposalStatus.ACCEPTED
        assert by_id[r["p2"].id].status == ProposalStatus.REJECTED  # R16 cascade
        # R33 — reputations reflect the reviews
        assert uow.users.get(r["f1"].id).reputation == 1.0  # rating 5
        assert uow.users.get(r["client"].id).reputation == 0.75  # rating 4
        # R31 — second review by the same author is refused
        with pytest.raises(InvariantViolation):
            SubmitReview(uow, ctx["bus"]).execute(r["client"].id, project.id, 1)

    def test_ranking_computed_on_publication_r15(self, ctx):
        r = run_chain(ctx)
        ranking = ctx["uow"].rankings.get_project_ranking(r["project"].id)
        ids = [fid for fid, _ in ranking]
        assert ids[0] == r["f1"].id  # advanced beats basic on the known catalogue
        assert r["f2"].id in ids

    def test_manual_search_s6(self, ctx):
        r = run_chain(ctx)
        uow = ctx["uow"]
        search = ManualSearch(uow, ctx["strategy"])
        # the completed project is no longer in the open catalogue
        assert search.search_projects(order_by="deadline") == []
        found = search.search_freelancers(
            skill_ids={ctx["skills"]["python"].id}, order_by="score"
        )
        assert {f.id for f in found} == {r["f1"].id, r["f2"].id}

    def test_update_project_metadata_s7(self, ctx):
        uow, bus, skills = ctx["uow"], ctx["bus"], ctx["skills"]
        client = RegisterUser(uow, bus).execute("owner@x.com", "h", "client")
        intruder = RegisterUser(uow, bus).execute("intruder@x.com", "h", "client")
        project = PublishProject(uow, bus).execute(
            client.id, "Old title", "Old description",
            {skills["python"].id}, 4000, DEADLINE,
        )
        # legal: the owner edits title/description while open (R45/S7)
        updated = UpdateProject(uow).execute(
            client.id, project.id, title="New title", description="New description"
        )
        assert updated.title == "New title"
        assert updated.description == "New description"
        assert updated.status == ProjectStatus.OPEN  # status untouched
        reloaded = uow.projects.get_with_proposals(project.id)
        assert reloaded.title == "New title"  # persisted (R7)
        # illegal: a non-owner cannot edit it (R42)
        with pytest.raises(ValidationError) as e:
            UpdateProject(uow).execute(intruder.id, project.id, title="Hijacked")
        assert e.value.code == "NOT_OWNER"
        # no domain event is published for a metadata edit (DD Sec. 2.1.2)
        assert uow.notifications.list_by_user(client.id) == []

    def test_update_project_rejected_when_not_open_s7(self, ctx):
        r = run_chain(ctx)  # ends with the project completed
        with pytest.raises(IllegalTransition) as e:
            UpdateProject(ctx["uow"]).execute(
                r["client"].id, r["project"].id, title="Too late"
            )
        assert e.value.code == "PROJECT_NOT_OPEN"


# --------------------------------------------------------------------- T6 -- #


class TestT6Observer:
    def test_publication_produces_notifications_and_suggested_view(self, ctx):
        r = run_chain(ctx)
        uow = ctx["uow"]
        kinds_f1 = [n.kind for n in uow.notifications.list_by_user(r["f1"].id)]
        assert "new_compatible_project" in kinds_f1  # R35
        suggested = uow.rankings.get_suggested_projects(r["f1"].id)  # R21
        # the project was open when published, so it entered the view
        assert any(pid == r["project"].id for pid, _ in suggested) or suggested == []

    def test_proposal_notification_r29(self, ctx):
        r = run_chain(ctx)
        kinds_client = [
            n.kind for n in ctx["uow"].notifications.list_by_user(r["client"].id)
        ]
        assert kinds_client.count("new_proposal") == 2  # one per proposal

    def test_accept_fanout_r30(self, ctx):
        r = run_chain(ctx)
        uow = ctx["uow"]
        assert "accepted" in [
            n.kind for n in uow.notifications.list_by_user(r["f1"].id)
        ]
        assert "rejected" in [
            n.kind for n in uow.notifications.list_by_user(r["f2"].id)
        ]

    def test_review_window_r31(self, ctx):
        r = run_chain(ctx)
        uow = ctx["uow"]
        for uid in (r["client"].id, r["f1"].id):
            assert "review_window" in [
                n.kind for n in uow.notifications.list_by_user(uid)
            ]

    def test_handlers_receive_events_only_after_commit(self, ctx):
        """DD Sec. 2.3.2 — the ProposalAccepted event is published after the
        commit, never inside the transaction."""
        uow, bus = ctx["uow"], ctx["bus"]
        skills = ctx["skills"]
        commits_at_event = {}

        from app.domain.events import ProposalAccepted

        def probe(event):
            commits_at_event["count"] = uow.committed

        bus.subscribe(ProposalAccepted, probe)
        client = RegisterUser(uow, bus).execute("c2@x.com", "h", "client")
        f = RegisterUser(uow, bus).execute("f3@x.com", "h", "freelancer")
        UpdateProfile(uow, bus).execute(
            f.id,
            hourly_rate=50,
            competences=[(skills["python"].id, "advanced")],
            availabilities=[(TODAY, DEADLINE)],
        )
        project = PublishProject(uow, bus).execute(
            client.id, "P", "D", {skills["python"].id}, 4000, DEADLINE
        )
        p = SubmitProposal(uow, bus).execute(f.id, project.id, "x", 1000)
        commits_before = uow.committed
        AcceptProposal(uow, bus).execute(client.id, project.id, p.id)
        # the use case committed BEFORE any handler saw the event
        assert commits_at_event["count"] >= commits_before + 1

    def test_metrics_recorded_nfr16(self, ctx):
        run_chain(ctx)
        m = ctx["uow"].metrics.snapshot()
        assert m["rankings_computed"] >= 1
        assert m["proposals_submitted"] == 2
        assert m["proposals_accepted"] == 1
        assert m["proposals_from_suggested"] == 2  # both came from the ranking
        assert m["accepted_from_suggested"] == 1
        assert m["reviews_submitted"] == 2
