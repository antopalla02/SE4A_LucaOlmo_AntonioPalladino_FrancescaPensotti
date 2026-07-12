"""Seed script (DD Sec. 3.4 — demo data for the interactive console).

Populates the controlled skill vocabulary, a set of freelancers with varied
competences/availabilities, a client, and one open project. Running it makes
the /docs console immediately explorable: the project already has a computed
ranking (R19) and the freelancers already have suggested-project views (R21).

Usage:
    python seed.py            # seeds the database named by FM_DATABASE_URL
All demo accounts use the password 'password'.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.api.security import hash_password
from app.application.publish_project import PublishProject
from app.application.register_user import RegisterUser, UpdateProfile
from app.config import Config, build_strategy
from app.domain.entities import Skill
from app.events.bus import InProcessEventBus
from app.events.handlers import EventHandlers
from app.repositories.sql import (
    SqlUnitOfWork,
    create_schema,
    make_engine,
    session_factory,
)

TODAY = date.today()
SOON = TODAY + timedelta(days=45)

SKILLS = ["python", "javascript", "react", "figma", "postgresql", "devops"]

FREELANCERS = [
    # email, rate, [(skill, level)], available window
    ("ada@demo.io", 55, [("python", "advanced"), ("postgresql", "intermediate")]),
    ("grace@demo.io", 70, [("python", "advanced"), ("devops", "advanced")]),
    ("linus@demo.io", 40, [("javascript", "advanced"), ("react", "advanced")]),
    ("don@demo.io", 35, [("figma", "advanced"), ("react", "basic")]),
    ("edsger@demo.io", 90, [("python", "intermediate")]),
]


def run(config: Config | None = None) -> None:
    config = config or Config.from_env()
    engine = make_engine(config.database_url)
    create_schema(engine)
    uow = SqlUnitOfWork(session_factory(engine)())
    bus = InProcessEventBus()
    EventHandlers(uow, build_strategy(config), config.ranking_size).register_all(bus)

    # controlled vocabulary
    skills = {}
    for name in SKILLS:
        if uow.skills.get_by_name(name) is None:
            s = Skill.create(name)
            uow.skills.save(s)
            skills[name] = s
        else:
            skills[name] = uow.skills.get_by_name(name)
    uow.commit()

    # freelancers
    reg = RegisterUser(uow, bus)
    upd = UpdateProfile(uow, bus)
    for email, rate, comps in FREELANCERS:
        if uow.users.exists_by_email(email):
            continue
        f = reg.execute(email, hash_password("password"), "freelancer")
        upd.execute(
            f.id,
            hourly_rate=rate,
            competences=[(skills[name].id, lvl) for name, lvl in comps],
            availabilities=[(TODAY, SOON)],
        )

    # a client + one open project (publication computes the ranking, R19)
    if not uow.users.exists_by_email("acme@demo.io"):
        client = reg.execute("acme@demo.io", hash_password("password"), "client")
        PublishProject(uow, bus).execute(
            client.id,
            "Internal analytics API",
            "Build a Python + PostgreSQL service exposing analytics endpoints.",
            {skills["python"].id, skills["postgresql"].id},
            6000,
            SOON,
        )

    print(f"Seeded '{config.database_url}'.")
    print("Demo accounts (password = 'password'):")
    print("  client:      acme@demo.io")
    for email, *_ in FREELANCERS:
        print(f"  freelancer:  {email}")


if __name__ == "__main__":
    run()
