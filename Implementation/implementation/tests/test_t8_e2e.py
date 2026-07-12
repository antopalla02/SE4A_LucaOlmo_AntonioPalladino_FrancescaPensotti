"""T8 — end-to-end HTTP tests through the FastAPI surface (DD Sec. 5.1
increment 5; the acceptance test of the V-model, DD Sec. 4).

The walkthrough drives S1->S5 entirely over HTTP and asserts on the three
things the API boundary is responsible for (DD Sec. 3): the status codes,
the error bodies carrying the requirement/transition codes (Sec. 3.3), and the
per-user scoping/authorisation (R41/R42). The persistence layer is
a temp-file SQLite so that every request opens its own session against the
same database, exactly as in production.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import Config
from app.domain.entities import Skill
from app.repositories.sql import SqlUnitOfWork, make_engine, session_factory

TODAY = date.today()
DEADLINE = (TODAY + timedelta(days=40)).isoformat()


@pytest.fixture()
def client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path/'e2e.db'}")
    app = create_app(Config(ranking_size=10), engine=engine)
    # seed the controlled vocabulary directly (no admin endpoint in scope)
    uow = SqlUnitOfWork(session_factory(engine)())
    skill = Skill.create("python")
    uow.skills.save(skill)
    uow.commit()
    tc = TestClient(app)
    tc.skill_id = skill.id  # type: ignore[attr-defined]
    return tc


def _register_and_login(client, email, role):
    r = client.post("/users", json={"email": email, "password": "pw", "role": role})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    r = client.post("/login", json={"email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return uid, {"Authorization": f"Bearer {token}"}


class TestT8EndToEnd:
    def test_full_walkthrough_s1_to_s5(self, client):
        skill_id = client.skill_id

        # S1 — registration + login
        client_id, h_client = _register_and_login(client, "client@x.com", "client")
        f1_id, h_f1 = _register_and_login(client, "f1@x.com", "freelancer")
        f2_id, h_f2 = _register_and_login(client, "f2@x.com", "freelancer")

        # S1 — freelancer profiles (R6/R8 controlled vocabulary over HTTP)
        for h, lvl in ((h_f1, "advanced"), (h_f2, "basic")):
            r = client.put(
                "/users/me",
                headers=h,
                json={
                    "hourly_rate": 50,
                    "competences": [{"skill_id": skill_id, "level": lvl}],
                    "availabilities": [{"start": TODAY.isoformat(), "end": DEADLINE}],
                },
            )
            assert r.status_code == 200, r.text

        # S2 — publication (R11/R12) triggers the ranking (R19)
        r = client.post(
            "/projects",
            headers=h_client,
            json={
                "title": "Build API",
                "description": "REST API",
                "required_skill_ids": [skill_id],
                "max_budget": 4000,
                "deadline": DEADLINE,
            },
        )
        assert r.status_code == 201, r.text
        project_id = r.json()["id"]
        assert r.json()["status"] == "open"

        # R19 — the ranking projection is readable by the owner and ordered
        r = client.get(f"/projects/{project_id}/ranking", headers=h_client)
        assert r.status_code == 200, r.text
        ids = [e["entity_id"] for e in r.json()]
        assert ids and ids[0] == f1_id  # advanced beats basic

        # S3 — proposals (R13/R17)
        r = client.post(
            f"/projects/{project_id}/proposals",
            headers=h_f1,
            json={"cover_letter": "I can do it", "offer": 3000},
        )
        assert r.status_code == 201, r.text
        p1_id = r.json()["id"]
        r = client.post(
            f"/projects/{project_id}/proposals",
            headers=h_f2,
            json={"cover_letter": "Me too", "offer": 3200},
        )
        assert r.status_code == 201, r.text

        # S4 — acceptance (R15/R16) with cascade rejection
        r = client.post(
            f"/projects/{project_id}/proposals/{p1_id}/accept", headers=h_client
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "inProgress"
        statuses = {p["freelancer_id"]: p["status"] for p in body["proposals"]}
        assert statuses[f1_id] == "accepted"
        assert statuses[f2_id] == "rejected"

        # S5 — completion (R18) + mutual reviews (R31-R33)
        r = client.post(f"/projects/{project_id}/complete", headers=h_client)
        assert r.status_code == 200 and r.json()["status"] == "completed"
        assert (
            client.post(
                f"/projects/{project_id}/reviews",
                headers=h_client,
                json={"rating": 5, "comment": "great"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/projects/{project_id}/reviews",
                headers=h_f1,
                json={"rating": 4, "comment": "good client"},
            ).status_code
            == 201
        )

        # reputation propagated (R33) — f1 got a 5 => normalised 1.0
        r = client.get("/users/me", headers=h_f1)
        assert r.json()["reputation"] == 1.0

        # R45 — metrics accumulated through the run
        m = client.get("/metrics/matching").json()
        assert m["proposals_submitted"] == 2
        assert m["proposals_accepted"] == 1

    def test_error_bodies_carry_domain_codes(self, client):
        skill_id = client.skill_id
        _, h_client = _register_and_login(client, "c2@x.com", "client")
        f_id, h_f = _register_and_login(client, "f9@x.com", "freelancer")
        client.put(
            "/users/me",
            headers=h_f,
            json={
                "hourly_rate": 50,
                "competences": [{"skill_id": skill_id, "level": "advanced"}],
                "availabilities": [{"start": TODAY.isoformat(), "end": DEADLINE}],
            },
        )
        pid = client.post(
            "/projects",
            headers=h_client,
            json={
                "title": "T",
                "description": "D",
                "required_skill_ids": [skill_id],
                "max_budget": 4000,
                "deadline": DEADLINE,
            },
        ).json()["id"]

        # duplicate email -> 409 with the invariant code (R2)
        r = client.post(
            "/users", json={"email": "c2@x.com", "password": "x", "role": "client"}
        )
        assert r.status_code == 409
        assert r.json()["error"] == "EMAIL_DUPLICATE"

        # duplicate proposal -> 409 carrying the R14 code (R14)
        client.post(
            f"/projects/{pid}/proposals",
            headers=h_f,
            json={"cover_letter": "a", "offer": 1000},
        )
        r = client.post(
            f"/projects/{pid}/proposals",
            headers=h_f,
            json={"cover_letter": "b", "offer": 1000},
        )
        assert r.status_code == 409
        assert r.json()["error"].startswith("R14")

        # unknown skill in profile -> 422 validation code (R8)
        r = client.put(
            "/users/me",
            headers=h_f,
            json={"competences": [{"skill_id": "ghost", "level": "basic"}]},
        )
        assert r.status_code == 422
        assert r.json()["error"] == "SKILL_NOT_IN_VOCABULARY"

    def test_authorisation_and_scoping(self, client):
        skill_id = client.skill_id
        c_id, h_client = _register_and_login(client, "c3@x.com", "client")
        f_id, h_f = _register_and_login(client, "f3@x.com", "freelancer")
        pid = client.post(
            "/projects",
            headers=h_client,
            json={
                "title": "T",
                "description": "D",
                "required_skill_ids": [skill_id],
                "max_budget": 4000,
                "deadline": DEADLINE,
            },
        ).json()["id"]

        # no token -> 401 (R41)
        assert client.get("/users/me").status_code == 401

        # wrong role -> 403: a freelancer cannot publish, a client cannot propose
        assert (
            client.post(
                "/projects",
                headers=h_f,
                json={
                    "title": "x",
                    "description": "y",
                    "required_skill_ids": [skill_id],
                    "max_budget": 10,
                    "deadline": DEADLINE,
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/projects/{pid}/proposals",
                headers=h_client,
                json={"cover_letter": "a", "offer": 1},
            ).status_code
            == 403
        )

        # a non-owner client cannot see another client's ranking (R42)
        _, h_other = _register_and_login(client, "c4@x.com", "client")
        r = client.get(f"/projects/{pid}/ranking", headers=h_other)
        assert r.status_code == 422
        assert r.json()["error"] == "NOT_OWNER"

        # the dashboard is implicitly scoped to the principal (R42)
        r = client.get("/users/me/dashboard", headers=h_f)
        assert r.status_code == 200
        assert r.json()["user_id"] == f_id
        assert r.json()["role"] == "freelancer"

    def test_update_project_metadata_s7(self, client):
        skill_id = client.skill_id
        _, h_owner = _register_and_login(client, "owner@x.com", "client")
        _, h_intruder = _register_and_login(client, "intruder@x.com", "client")
        pid = client.post(
            "/projects",
            headers=h_owner,
            json={
                "title": "Old title",
                "description": "Old description",
                "required_skill_ids": [skill_id],
                "max_budget": 4000,
                "deadline": DEADLINE,
            },
        ).json()["id"]

        # legal: the owner edits title/description while open (R45/S7)
        r = client.put(
            f"/projects/{pid}", headers=h_owner, json={"title": "New title"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "New title"
        assert r.json()["description"] == "Old description"  # untouched
        assert r.json()["status"] == "open"

        # illegal: a non-owner cannot edit it -> 422 NOT_OWNER (R42)
        r = client.put(
            f"/projects/{pid}", headers=h_intruder, json={"title": "Hijacked"}
        )
        assert r.status_code == 422
        assert r.json()["error"] == "NOT_OWNER"

        # illegal: once the project is no longer open -> 409 (R45)
        f_id, h_f = _register_and_login(client, "f10@x.com", "freelancer")
        client.put(
            "/users/me",
            headers=h_f,
            json={
                "hourly_rate": 50,
                "competences": [{"skill_id": skill_id, "level": "advanced"}],
                "availabilities": [{"start": TODAY.isoformat(), "end": DEADLINE}],
            },
        )
        prop_id = client.post(
            f"/projects/{pid}/proposals",
            headers=h_f,
            json={"cover_letter": "x", "offer": 1000},
        ).json()["id"]
        client.post(f"/projects/{pid}/proposals/{prop_id}/accept", headers=h_owner)
        r = client.put(
            f"/projects/{pid}", headers=h_owner, json={"title": "Too late"}
        )
        assert r.status_code == 409
        assert r.json()["error"] == "PROJECT_NOT_OPEN"
