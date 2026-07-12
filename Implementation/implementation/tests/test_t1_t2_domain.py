"""T1 — every invariant R14-R33: one test per invariant attempting the
violation and expecting DomainError (DD Sec. 5.3; RASD Sec. 2.2).
T2 — FSM transition coverage for Project and Proposal: all legal
transitions succeed, all illegal ones fail (RASD Sec. 3.2; R12-R18).
"""

from datetime import date, timedelta

import pytest

from app.domain.entities import (
    NEUTRAL_REPUTATION,
    Project,
    Proposal,
    Review,
    register_user,
)
from app.domain.enums import ProjectStatus, ProposalStatus, Role
from app.domain.errors import (
    DomainError,
    IllegalTransition,
    InvariantViolation,
    ValidationError,
)
from app.domain.events import CollaborationCompleted, ProposalAccepted

TOMORROW = date.today() + timedelta(days=30)


def make_project(client_id="c1", skills={"s1"}):
    return Project.create(
        client_id=client_id,
        title="T",
        description="D",
        required_skill_ids=set(skills),
        max_budget=1000,
        deadline=TOMORROW,
    )


def project_with_accepted():
    p = make_project()
    p.add_proposal("f1", "hi", 500)
    p.add_proposal("f2", "hi", 400)
    p.accept_proposal(p.proposals[0].id)
    return p


# --------------------------------------------------------------------- T1 -- #


class TestT1DomainRules:
    def test_r14_duplicate_proposal(self):
        p = make_project()
        p.add_proposal("f1", "a", 100)
        with pytest.raises(InvariantViolation) as e:
            p.add_proposal("f1", "b", 200)
        assert e.value.code == "R14_DUPLICATE_PROPOSAL"

    def test_r16_at_most_one_accepted(self):
        p = make_project()
        p.add_proposal("f1", "a", 100)
        p.add_proposal("f2", "b", 200)
        p.accept_proposal(p.proposals[0].id)
        accepted = [q for q in p.proposals if q.status == ProposalStatus.ACCEPTED]
        assert len(accepted) == 1
        # a second acceptance is impossible: project no longer open
        with pytest.raises(DomainError):
            p.accept_proposal(p.proposals[1].id)

    def test_r16_inprogress_iff_one_accepted(self):
        p = make_project()
        assert p.accepted_proposal() is None  # no proposal yet -> loop exhausts
        p.add_proposal("f0", "a", 100)
        p.add_proposal("f1", "b", 200)
        # accept the *second* proposal: accepted_proposal()'s search loop
        # must skip a non-matching (rejected) entry before finding it
        p.accept_proposal(p.proposals[1].id)
        assert p.status == ProjectStatus.IN_PROGRESS
        accepted = p.accepted_proposal()
        assert accepted is not None and accepted.freelancer_id == "f1"
        # and every other pending was rejected (cascade of R16)
        assert all(
            q.status != ProposalStatus.PENDING for q in p.proposals
        )

    def test_r18_completed_only_from_inprogress(self):
        p = make_project()
        with pytest.raises(IllegalTransition) as e:
            p.mark_completed()
        assert e.value.code == "R18_NOT_IN_PROGRESS"

    def test_r31_review_requires_completed_and_parties(self):
        p = project_with_accepted()
        # not completed yet
        with pytest.raises(InvariantViolation) as e:
            Review.create(p, "c1", 5, "", [])
        assert e.value.code == "R31_PROJECT_NOT_COMPLETED"
        p.mark_completed()
        # author not a party
        with pytest.raises(InvariantViolation) as e:
            Review.create(p, "stranger", 5, "", [])
        assert e.value.code == "R31_AUTHOR_NOT_PARTY"
        # rating out of {1..5} (or non-int) is rejected before anything else
        for bad_rating in (0, 6, "5"):
            with pytest.raises(ValidationError) as e:
                Review.create(p, "c1", bad_rating, "", [])
            assert e.value.code == "RATING_INVALID"
        # target is automatically the counterpart (author != target by shape)
        review, _ = Review.create(p, "c1", 5, "", [])
        assert review.target_id == "f1"

    def test_r31_one_review_per_project_author(self):
        p = project_with_accepted()
        p.mark_completed()
        r1, _ = Review.create(p, "c1", 5, "", [])
        with pytest.raises(InvariantViolation) as e:
            Review.create(p, "c1", 4, "", [r1])
        assert e.value.code == "R31_DUPLICATE_REVIEW"

    def test_r33_reputation_function_of_reviews(self):
        u = register_user("a@b.com", "h", Role.FREELANCER)
        assert u.reputation == NEUTRAL_REPUTATION  # no reviews -> 0.5
        u.update_reputation([5, 5])
        assert u.reputation == 1.0
        u.update_reputation([1])
        assert u.reputation == 0.0
        u.update_reputation([3, 5])  # (0.5 + 1.0)/2
        assert u.reputation == pytest.approx(0.75)
        u.update_reputation([])
        assert u.reputation == NEUTRAL_REPUTATION


# --------------------------------------------------------------------- T2 -- #


class TestT2ProjectFSM:
    def test_legal_open_to_inprogress(self):
        # R12 — a freshly created project enters the FSM in status = open
        assert make_project().status == ProjectStatus.OPEN
        # R11 — the creation guards reject every invalid field (the entry
        # transition of the Project FSM); each maps to its own error code
        base = dict(
            client_id="c1", title="T", description="D",
            required_skill_ids={"s1"}, max_budget=1000, deadline=TOMORROW,
        )
        bad = {
            "PROJECT_TITLE_EMPTY": {**base, "title": "   "},
            "PROJECT_DESCRIPTION_EMPTY": {**base, "description": ""},
            "PROJECT_SKILLS_EMPTY": {**base, "required_skill_ids": set()},
            "PROJECT_BUDGET_INVALID": {**base, "max_budget": -1},
            "PROJECT_DEADLINE_PAST": {**base, "deadline": date.today()},
        }
        for code, kwargs in bad.items():
            with pytest.raises(DomainError) as e:
                Project.create(**kwargs)
            assert e.value.code == code

        # ...then the legal open -> inProgress transition (R15/R16)
        p = make_project()
        p.add_proposal("f1", "a", 100)
        events = p.accept_proposal(p.proposals[0].id)
        assert p.status == ProjectStatus.IN_PROGRESS
        assert isinstance(events[0], ProposalAccepted)

    def test_legal_inprogress_to_completed(self):
        p = project_with_accepted()
        events = p.mark_completed()
        assert p.status == ProjectStatus.COMPLETED
        assert isinstance(events[0], CollaborationCompleted)

    def test_legal_open_self_transition_metadata(self):
        p = make_project()
        p.update_metadata(title="New title")
        assert p.title == "New title" and p.status == ProjectStatus.OPEN
        p.update_metadata(description="New description")
        assert p.description == "New description" and p.status == ProjectStatus.OPEN

    def test_illegal_accept_when_not_open(self):
        p = project_with_accepted()  # inProgress
        with pytest.raises(IllegalTransition):
            p.accept_proposal(p.proposals[0].id)
        p.mark_completed()
        with pytest.raises(IllegalTransition):
            p.accept_proposal(p.proposals[0].id)
        # a non-existent proposal id is rejected even on an open project
        q = make_project()
        with pytest.raises(ValidationError) as e:
            q.accept_proposal("no-such-id")
        assert e.value.code == "PROPOSAL_NOT_FOUND"

    def test_illegal_complete_from_open_or_completed(self):
        p = make_project()
        with pytest.raises(IllegalTransition):
            p.mark_completed()
        q = project_with_accepted()
        q.mark_completed()
        with pytest.raises(IllegalTransition):
            q.mark_completed()

    def test_illegal_metadata_update_when_not_open(self):
        p = project_with_accepted()
        with pytest.raises(IllegalTransition):
            p.update_metadata(title="X")

    def test_illegal_proposal_on_closed_project_r13(self):
        p = project_with_accepted()
        with pytest.raises(IllegalTransition) as e:
            p.add_proposal("f9", "late", 100)
        assert e.value.code == "PROJECT_NOT_OPEN"

    def test_illegal_proposal_after_deadline_r9(self):
        p = make_project()
        with pytest.raises(IllegalTransition):
            p.add_proposal("f1", "late", 100, today=TOMORROW + timedelta(days=1))


class TestT2ProposalFSM:
    def test_legal_pending_to_accepted_and_rejected(self):
        # entry-transition guards: an invalid offer never produces a Proposal
        for bad_offer in (-1, 10_000_001):
            with pytest.raises(ValidationError) as e:
                Proposal.create("p", "f1", "x", bad_offer)
            assert e.value.code == "OFFER_INVALID"

        a = Proposal.create("p", "f1", "x", 10)
        a.accept()
        assert a.status == ProposalStatus.ACCEPTED
        b = Proposal.create("p", "f2", "x", 10)
        b.reject()
        assert b.status == ProposalStatus.REJECTED

    def test_terminal_states_are_final(self):
        a = Proposal.create("p", "f1", "x", 10)
        a.accept()
        for op in (a.accept, a.reject):
            with pytest.raises(IllegalTransition):
                op()
        b = Proposal.create("p", "f2", "x", 10)
        b.reject()
        for op in (b.accept, b.reject):
            with pytest.raises(IllegalTransition):
                op()