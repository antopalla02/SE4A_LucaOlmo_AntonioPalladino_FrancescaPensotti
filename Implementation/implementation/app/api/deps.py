"""FastAPI dependencies: per-request wiring and authentication.

Each HTTP request gets its own UnitOfWork (one SQLAlchemy session) and its
own event bus with the handlers freshly registered on it, so that the
observer side effects of a request commit into the *same* trans* context as
the request (DD Sec. 2.3 — the handlers share the use case's UnitOfWork).
The strategy is stateless and shared from application state (DD Sec. 2.4.2:
chosen once at startup).

``get_current_user`` turns a bearer token into the authenticated principal;
routes pass ``current_user.id`` as the actor, which is the single mechanism
behind the per-user scoping of R42.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

from fastapi import Depends, Header, HTTPException, Request

from ..domain.entities import Client, Freelancer, User
from ..events.bus import InProcessEventBus
from ..events.handlers import EventHandlers
from ..matching.strategy import MatchingStrategy
from ..repositories.sql import SqlUnitOfWork
from .security import TokenStore


@dataclass
class AppState:
    session_factory: object
    strategy: MatchingStrategy
    ranking_size: int
    tokens: TokenStore


@dataclass
class RequestContext:
    uow: SqlUnitOfWork
    bus: InProcessEventBus
    strategy: MatchingStrategy
    ranking_size: int


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def get_context(request: Request) -> Iterator[RequestContext]:
    state: AppState = request.app.state.app_state
    session = state.session_factory()
    uow = SqlUnitOfWork(session)
    bus = InProcessEventBus()
    EventHandlers(uow, state.strategy, state.ranking_size).register_all(bus)
    try:
        yield RequestContext(uow, bus, state.strategy, state.ranking_size)
    finally:
        session.close()


def get_current_user(
    ctx: RequestContext = Depends(get_context),
    authorization: Optional[str] = Header(default=None),
    request: Request = None,  # type: ignore[assignment]
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    state: AppState = request.app.state.app_state
    user_id = state.tokens.resolve(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid token")
    user = ctx.uow.users.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown principal")
    return user


def require_client(user: User = Depends(get_current_user)) -> Client:
    if not isinstance(user, Client):
        raise HTTPException(status_code=403, detail="client role required")
    return user


def require_freelancer(user: User = Depends(get_current_user)) -> Freelancer:
    if not isinstance(user, Freelancer):
        raise HTTPException(status_code=403, detail="freelancer role required")
    return user
