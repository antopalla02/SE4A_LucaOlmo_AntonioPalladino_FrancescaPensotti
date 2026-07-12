"""T7 — the SQLite-backed integration tests (DD Sec. 5.1 increment 4, 5.2
integration point 1).

Three things are verified here, all on the real persistent stack:

1. The whole S1->S5 script of T5 runs *unchanged* on ``SqlUnitOfWork``:
   the use cases and handlers are storage-agnostic, so swapping the
   in-memory repositories for the SQLAlchemy ones must not change any
   observable behaviour (DD Sec. 2.1.6 — the repository seam).

2. The atomic block of acceptance (R16) is genuinely atomic on
   SQLite: an acceptance that fails mid-way leaves the project untouched.

3. Two concurrent acceptances of the *same* open project are serialised:
   exactly one transition is persisted, the loser raises (DD Sec. 2.3.2).
   The serialisation point is the optimistic-lock guard on ProjectRow.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.orm.exc import StaleDataError

from app.application.accept_proposal import AcceptProposal
from app.application.publish_project import PublishProject
from app.application.register_user import RegisterUser, UpdateProfile
from app.application.submit_proposal import SubmitProposal
from app.application.update_project import UpdateProject
from app.config import Config, build_strategy
from app.domain.entities import Skill
from app.domain.enums import ProjectStatus, ProposalStatus
from app.domain.errors import DomainError
from app.events.bus import InProcessEventBus
from app.events.handlers import EventHandlers
from app.repositories.sql import (
    ProjectRow,
    SqlUnitOfWork,
    create_schema,
    make_engine,
    session_factory,
)

# the S1->S5 driver is storage-agnostic, so we reuse it verbatim
from tests.test_t5_t6_integration import DEADLINE, TODAY, run_chain


@pytest.fixture()
def engine(tmp_path):
    """A real on-disk SQLite database (a temp file so several sessions can
    open the same database, which is what the race test needs)."""
    url = f"sqlite:///{tmp_path/'fm.db'}"
    eng = make_engine(url)
    create_schema(eng)
    return eng


def make_ctx(engine):
    """Mini composition root over the SQL stack, shaped exactly like the
    in-memory ``ctx`` of T5 so that ``run_chain`` accepts it unchanged."""
    config = Config(ranking_size=10)
    Session = session_factory(engine)
    uow = SqlUnitOfWork(Session())
    bus = InProcessEventBus()
    strategy = build_strategy(config)
    EventHandlers(uow, strategy, config.ranking_size).register_all(bus)
    skills = {}
    for name in ("python", "figma"):
        s = Skill.create(name)
        uow.skills.save(s)
        skills[name] = s
    uow.commit()
    return dict(uow=uow, bus=bus, strategy=strategy, skills=skills), Session


# ------------------------------------------------------------ portability -- #


class TestT7Portability:
    def test_full_chain_runs_unchanged_on_sqlite(self, engine):
        ctx, _ = make_ctx(engine)
        r = run_chain(ctx)
        uow = ctx["uow"]
        project = uow.projects.get_with_proposals(r["project"].id)
        assert project.status == ProjectStatus.COMPLETED
        by_id = {p.id: p for p in project.proposals}
        assert by_id[r["p1"].id].status == ProposalStatus.ACCEPTED
        assert by_id[r["p2"].id].status == ProposalStatus.REJECTED  # R16 cascade
        assert uow.users.get(r["f1"].id).reputation == 1.0
        assert uow.users.get(r["client"].id).reputation == 0.75

    def test_state_survives_a_fresh_session(self, engine):
        """What was committed is really on disk: a brand-new session sees it
        (this is the property the in-memory stack cannot demonstrate)."""
        ctx, Session = make_ctx(engine)
        r = run_chain(ctx)
        fresh = SqlUnitOfWork(Session())
        project = fresh.projects.get_with_proposals(r["project"].id)
        assert project is not None
        assert project.status == ProjectStatus.COMPLETED
        ranking = fresh.rankings.get_project_ranking(r["project"].id)
        assert [fid for fid, _ in ranking][0] == r["f1"].id  # R19 projection persisted


# ---------------------------------------------------------- project update - #


class TestT7ProjectUpdate:
    def test_update_project_persists_across_sessions(self, engine):
        """S7/R45 on the real store: the edit survives a fresh session, and
        the field that was not part of the request is left untouched."""
        ctx, Session = make_ctx(engine)
        uow, bus, skills = ctx["uow"], ctx["bus"], ctx["skills"]
        client = RegisterUser(uow, bus).execute("owner@x.com", "h", "client")
        project = PublishProject(uow, bus).execute(
            client.id, "Old title", "Old description",
            {skills["python"].id}, 4000, DEADLINE,
        )
        UpdateProject(uow).execute(client.id, project.id, title="New title")

        fresh = SqlUnitOfWork(Session())
        reloaded = fresh.projects.get_with_proposals(project.id)
        assert reloaded.title == "New title"
        assert reloaded.description == "Old description"  # untouched field


# ------------------------------------------------------- atomic + race ----- #


def _open_project_with_two_proposals(engine):
    """Drive S1->S3 only, leaving an open project with two pending proposals,
    and return (engine, ids) for the acceptance tests."""
    ctx, Session = make_ctx(engine)
    uow, bus, skills = ctx["uow"], ctx["bus"], ctx["skills"]
    client = RegisterUser(uow, bus).execute("c@x.com", "h", "client")
    f1 = RegisterUser(uow, bus).execute("f1@x.com", "h", "freelancer")
    f2 = RegisterUser(uow, bus).execute("f2@x.com", "h", "freelancer")
    upd = UpdateProfile(uow, bus)
    upd.execute(
        f1.id, hourly_rate=50,
        competences=[(skills["python"].id, "advanced")],
        availabilities=[(TODAY, DEADLINE)],
    )
    upd.execute(
        f2.id, hourly_rate=55,
        competences=[(skills["python"].id, "intermediate")],
        availabilities=[(TODAY, DEADLINE)],
    )
    project = PublishProject(uow, bus).execute(
        client.id, "API", "REST API", {skills["python"].id}, 4000, DEADLINE
    )
    p1 = SubmitProposal(uow, bus).execute(f1.id, project.id, "me", 3000)
    p2 = SubmitProposal(uow, bus).execute(f2.id, project.id, "me too", 3200)
    return Session, dict(client=client.id, project=project.id, p1=p1.id, p2=p2.id)


class TestT7Atomicity:
    def test_acceptance_is_atomic_on_sqlite(self, engine):
        Session, ids = _open_project_with_two_proposals(engine)
        uow = SqlUnitOfWork(Session())
        bus = InProcessEventBus()
        AcceptProposal(uow, bus).execute(ids["client"], ids["project"], ids["p1"])
        # one transaction made all three transitions visible at once (R16)
        check = SqlUnitOfWork(Session())
        project = check.projects.get_with_proposals(ids["project"])
        assert project.status == ProjectStatus.IN_PROGRESS
        by_id = {p.id: p for p in project.proposals}
        assert by_id[ids["p1"]].status == ProposalStatus.ACCEPTED
        assert by_id[ids["p2"]].status == ProposalStatus.REJECTED

    def test_rejected_acceptance_leaves_no_trace(self, engine):
        """A non-owner acceptance is refused before any write; the open
        project is left exactly as it was (R15/R42, atomic rollback)."""
        Session, ids = _open_project_with_two_proposals(engine)
        uow = SqlUnitOfWork(Session())
        with pytest.raises(DomainError):
            AcceptProposal(uow, InProcessEventBus()).execute(
                "intruder-id", ids["project"], ids["p1"]
            )
        check = SqlUnitOfWork(Session())
        project = check.projects.get_with_proposals(ids["project"])
        assert project.status == ProjectStatus.OPEN
        assert all(
            p.status == ProposalStatus.PENDING for p in project.proposals
        )


class TestT7ConcurrentRace:
    def test_two_acceptances_of_same_open_project_serialise(self, engine):
        """The race: two transactions both read the project while it is still
        open, then each tries to accept a different proposal. The optimistic
        lock lets exactly one commit; the other matches zero rows on its
        guarded UPDATE and raises (DD Sec. 2.3.2 — serialisation point)."""
        Session, ids = _open_project_with_two_proposals(engine)

        # two independent sessions => two independent transactions
        uow_a = SqlUnitOfWork(Session())
        uow_b = SqlUnitOfWork(Session())

        # Each live transaction reads (and keeps) the aggregate it is working
        # on, exactly as a request handler holds its loaded objects for the
        # duration of the request. Pinning the ORM rows keeps the pre-race
        # version in each session's identity map.
        row_a = uow_a.session.get(ProjectRow, ids["project"])
        row_b = uow_b.session.get(ProjectRow, ids["project"])
        assert row_a.version == row_b.version  # both saw the same open project

        # both read the SAME open project before either writes
        proj_a = uow_a.projects.get_with_proposals(ids["project"])
        proj_b = uow_b.projects.get_with_proposals(ids["project"])
        assert proj_a.status == ProjectStatus.OPEN
        assert proj_b.status == ProjectStatus.OPEN

        # A wins: accept p1, persist, commit
        proj_a.accept_proposal(ids["p1"])
        uow_a.projects.save(proj_a)
        uow_a.commit()

        # B loses: its guarded UPDATE (version still the pre-A value) hits 0 rows
        proj_b.accept_proposal(ids["p2"])
        with pytest.raises(StaleDataError):
            uow_b.projects.save(proj_b)
            uow_b.commit()
        uow_b.rollback()

        # final state: exactly one acceptance survived
        check = SqlUnitOfWork(Session())
        final = check.projects.get_with_proposals(ids["project"])
        assert final.status == ProjectStatus.IN_PROGRESS
        accepted = [p for p in final.proposals if p.status == ProposalStatus.ACCEPTED]
        assert len(accepted) == 1
        assert accepted[0].id == ids["p1"]

    def test_second_acceptance_after_commit_fails_domain_check(self, engine):
        """The higher-level guard: once the first acceptance is committed, a
        later transaction re-reads the project, finds it no longer open, and
        the domain FSM refuses the transition (R16)."""
        Session, ids = _open_project_with_two_proposals(engine)
        AcceptProposal(SqlUnitOfWork(Session()), InProcessEventBus()).execute(
            ids["client"], ids["project"], ids["p1"]
        )
        with pytest.raises(DomainError):
            AcceptProposal(SqlUnitOfWork(Session()), InProcessEventBus()).execute(
                ids["client"], ids["project"], ids["p2"]
            )
