"""T3 — WeightedScoreStrategy: sub-scores normalised in [0,1], weights
validated, hard filters exclude before scoring, known catalogue -> known
ranking (R24, R25).
T4 — Strategy swap: identical input through both strategies yields valid
but distinct rankings; active strategy switchable by configuration alone
(R26, G5).
"""

from datetime import date, timedelta

import pytest

from app.config import Config, build_strategy
from app.domain.entities import Availability, Competence, Freelancer, Project
from app.domain.enums import MasteryLevel, Role
from app.domain.errors import ValidationError
from app.matching.rule_based import RuleBasedStrategy
from app.matching.strategy import HardFilterConfig, MatchingWeights
from app.matching.weighted import WeightedScoreStrategy

TODAY = date.today()
DEADLINE = TODAY + timedelta(days=40)


def freelancer(fid, skills, rate, reputation=0.5, available=True):
    f = Freelancer(
        id=fid,
        email=f"{fid}@x.com",
        password_hash="h",
        role=Role.FREELANCER,
        registered_at=None,
        reputation=reputation,
        hourly_rate=rate,
    )
    f.competences = [Competence(skill_id=s, level=l) for s, l in skills]
    if available:
        f.availabilities = [Availability(start=TODAY, end=DEADLINE)]
    return f


def project(skills={"s1", "s2"}, budget=4000):
    return Project.create(
        client_id="c1",
        title="P",
        description="D",
        required_skill_ids=set(skills),
        max_budget=budget,
        deadline=DEADLINE,
    )


# --------------------------------------------------------------------- T3 -- #


class TestT3Weighted:
    def test_weights_validated(self):
        with pytest.raises(ValidationError):
            MatchingWeights(0.5, 0.5, 0.5, 0.5).validate()
        with pytest.raises(ValidationError):
            MatchingWeights(-0.2, 0.5, 0.5, 0.2).validate()
        MatchingWeights().validate()  # default sums to 1

    def test_subscores_normalised(self):
        s = WeightedScoreStrategy()
        p = project()
        f = freelancer(
            "f1",
            [("s1", MasteryLevel.ADVANCED), ("s2", MasteryLevel.BASIC)],
            rate=50,
            reputation=0.9,
        )
        for sub in (s._s_skills, s._s_budget, s._s_reputation, s._s_availability):
            v = sub(p, f)
            assert 0.0 <= v <= 1.0, sub.__name__
        assert 0.0 <= s._compute_score(p, f) <= 1.0

    def test_hard_filter_excludes_before_scoring(self):
        # budget overrun beyond tolerance (R25): rate*40h = 8000 > 4000*1.2
        s = WeightedScoreStrategy(hard_filters=HardFilterConfig(0.2, 40))
        p = project(budget=4000)
        too_expensive = freelancer("f1", [("s1", MasteryLevel.ADVANCED)], rate=200)
        no_overlap = freelancer("f2", [("zz", MasteryLevel.ADVANCED)], rate=10)
        ok = freelancer("f3", [("s1", MasteryLevel.ADVANCED)], rate=50)
        ranking = s.rank_freelancers(p, [too_expensive, no_overlap, ok])
        assert [r.entity_id for r in ranking] == ["f3"]

    def test_known_catalogue_known_ranking(self):
        s = WeightedScoreStrategy()
        p = project()
        full_advanced = freelancer(
            "best",
            [("s1", MasteryLevel.ADVANCED), ("s2", MasteryLevel.ADVANCED)],
            rate=50,
            reputation=0.9,
        )
        partial = freelancer("mid", [("s1", MasteryLevel.BASIC)], rate=50, reputation=0.9)
        low_rep = freelancer(
            "low",
            [("s1", MasteryLevel.ADVANCED), ("s2", MasteryLevel.ADVANCED)],
            rate=50,
            reputation=0.1,
        )
        ranking = s.rank_freelancers(p, [partial, low_rep, full_advanced])
        assert [r.entity_id for r in ranking] == ["best", "low", "mid"]
        assert ranking[0].score > ranking[1].score > ranking[2].score

    def test_rank_projects_symmetric_direction(self):
        s = WeightedScoreStrategy()
        f = freelancer("f1", [("s1", MasteryLevel.ADVANCED)], rate=50, reputation=0.8)
        p_match = project(skills={"s1"})
        p_nomatch = project(skills={"zz"})
        ranking = s.rank_projects(f, [p_nomatch, p_match])
        assert [r.entity_id for r in ranking] == [p_match.id]


# --------------------------------------------------------------------- T4 -- #


class TestT4StrategySwap:
    def catalogue(self):
        p = project(budget=4000)
        # weighted prefers high reputation; rule-based prefers full coverage
        full_cov_low_rep = freelancer(
            "full",
            [("s1", MasteryLevel.BASIC), ("s2", MasteryLevel.BASIC)],
            rate=50,
            reputation=0.2,
        )
        partial_high_rep = freelancer(
            "partial",
            [("s1", MasteryLevel.ADVANCED)],
            rate=50,
            reputation=1.0,
        )
        return p, [full_cov_low_rep, partial_high_rep]

    def test_strategy_can_be_swapped(self):
        """The mechanical verification promised in DD Sec. 2.4.2: the active
        strategy is switchable by configuration alone."""
        s_weighted = build_strategy(Config(matching_strategy="weighted"))
        s_rule = build_strategy(Config(matching_strategy="rule_based"))
        assert isinstance(s_weighted, WeightedScoreStrategy)
        assert isinstance(s_rule, RuleBasedStrategy)
        with pytest.raises(ValidationError):
            build_strategy(Config(matching_strategy="nope"))

    def test_identical_input_distinct_valid_rankings(self):
        p, candidates = self.catalogue()
        r_weighted = build_strategy(Config(matching_strategy="weighted")).rank_freelancers(
            p, candidates
        )
        r_rule = build_strategy(Config(matching_strategy="rule_based")).rank_freelancers(
            p, candidates
        )
        ids_w = [r.entity_id for r in r_weighted]
        ids_r = [r.entity_id for r in r_rule]
        # both valid (same candidate set, scores in [0,1], strictly ordered)
        for ranking in (r_weighted, r_rule):
            assert all(0.0 <= r.score <= 1.0 for r in ranking)
            assert sorted((r.score for r in ranking), reverse=True) == [
                r.score for r in ranking
            ]
        assert set(ids_w) == set(ids_r) == {"full", "partial"}
        # but distinct: weighted favours reputation, rule-based full coverage
        assert ids_w[0] == "partial"
        assert ids_r[0] == "full"
