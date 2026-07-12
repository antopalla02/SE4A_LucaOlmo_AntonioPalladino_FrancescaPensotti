"""Application factory (DD Sec. 3).

``create_app`` is the composition surface for the HTTP layer: it selects the
matching strategy from configuration (DD Sec. 2.4.2), creates the persistent
schema, wires the per-request dependencies, installs the single domain-error
translator (DD Sec. 3.3), and mounts the routers. The interactive OpenAPI
console served at ``/docs`` is the user interface of the prototype (DD Sec. 3:
the system is delivered as a documented API surface).
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from ..config import Config, build_strategy
from ..domain.errors import (
    DomainError,
    IllegalTransition,
    InvariantViolation,
    ValidationError,
)
from ..repositories.sql import create_schema, make_engine, session_factory
from .deps import AppState
from .routes import ALL_ROUTERS
from .security import TokenStore


def _status_for(exc: DomainError) -> int:
    if isinstance(exc, ValidationError):
        return 422
    if isinstance(exc, (InvariantViolation, IllegalTransition)):
        return 409
    return 400


def create_app(config: Optional[Config] = None, engine=None) -> FastAPI:
    config = config or Config.from_env()
    if engine is None:
        engine = make_engine(config.database_url)
    create_schema(engine)

    app = FastAPI(
        title="FreelanceMatch API",
        version="1.0",
        description=(
            "Reference implementation of the FreelanceMatch Design Document. "
            "Endpoints are grouped by requirement cluster; error bodies carry "
            "the machine-readable invariant/transition codes (DD Sec. 3.3)."
        ),
    )

    app.state.app_state = AppState(
        session_factory=session_factory(engine),
        strategy=build_strategy(config),
        ranking_size=config.ranking_size,
        tokens=TokenStore(),
    )

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=_status_for(exc),
            content={"error": exc.code, "detail": exc.detail},
        )

    for router in ALL_ROUTERS:
        app.include_router(router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "strategy": config.matching_strategy}

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
        }
        for path in schema.get("paths", {}).values():
            for op in path.values():
                op.setdefault("security", [{"BearerAuth": []}])
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi

    return app
