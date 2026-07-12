"""HTTP routes, grouped into routers by requirement cluster (DD Sec. 3.2).

Each router corresponds to one cluster of the design: accounts (R1-R8),
projects (R11/R12/R18/R45), proposals (R13-R17), matching (R19-R26), search
(R27-R29), reviews (R30-R33), notifications/dashboard (R35-R39) and the
matching-quality metrics (R44). The handlers are thin: they translate the
DTO into a use-case call and the result back into a DTO. Domain errors are
not caught here — they propagate to the single translator installed in
``app.py`` (DD Sec. 3.3).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from ..application.accept_proposal import AcceptProposal
from ..application.complete_and_review import CompleteProject, SubmitReview
from ..application.manual_search import ManualSearch
from ..application.publish_project import PublishProject
from ..application.register_user import RegisterUser, RequestSkill, UpdateProfile
from ..application.submit_proposal import SubmitProposal
from ..application.update_project import UpdateProject
from ..domain.entities import Client, Freelancer, User
from ..domain.errors import ValidationError
from .deps import (
    AppState,
    RequestContext,
    get_app_state,
    get_context,
    get_current_user,
    require_client,
    require_freelancer,
)
from .schemas import (
    DashboardOut,
    LoginIn,
    NotificationOut,
    ProfileIn,
    ProjectIn,
    ProjectOut,
    ProjectUpdateIn,
    ProposalIn,
    ProposalOut,
    RankingEntryOut,
    RegisterIn,
    ReviewIn,
    ReviewOut,
    SkillOut,
    SkillRequestIn,
    TokenOut,
    UserOut,
)
from .security import hash_password, verify_password

accounts = APIRouter(tags=["accounts (R1-R8)"])
projects = APIRouter(tags=["projects (R11,R12,R18,R45)"])
proposals = APIRouter(tags=["proposals (R13-R17)"])
matching = APIRouter(tags=["matching (R19-R26)"])
search = APIRouter(tags=["search (R27-R29)"])
reviews = APIRouter(tags=["reviews (R30-R33)"])
dashboard = APIRouter(tags=["notifications & dashboard (R35-R39)"])
metrics = APIRouter(tags=["metrics (R44)"])


# --------------------------------------------------------------- accounts -- #


@accounts.post("/users", response_model=UserOut, status_code=201)
def register(body: RegisterIn, ctx: RequestContext = Depends(get_context)) -> UserOut:
    """S1 / R1, R2 — password stored hashed (R42)."""
    user = RegisterUser(ctx.uow, ctx.bus).execute(
        body.email, hash_password(body.password), body.role
    )
    return UserOut.from_entity(user)


@accounts.post("/login", response_model=TokenOut)
def login(
    body: LoginIn,
    ctx: RequestContext = Depends(get_context),
    state: AppState = Depends(get_app_state),
) -> TokenOut:
    user = ctx.uow.users.get_by_email(body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise ValidationError("CREDENTIALS_INVALID", "wrong email or password")
    token = state.tokens.issue(user.id)
    return TokenOut(access_token=token, user_id=user.id, role=user.role.value)


@accounts.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_entity(user)


@accounts.put("/users/me", response_model=UserOut)
def update_me(
    body: ProfileIn,
    user: User = Depends(get_current_user),
    ctx: RequestContext = Depends(get_context),
) -> UserOut:
    """R4-R6 — profile update on the authenticated principal only (R42)."""
    updated = UpdateProfile(ctx.uow, ctx.bus).execute(
        user.id,
        business_name=body.business_name,
        sector=body.sector,
        typical_needs=body.typical_needs,
        hourly_rate=body.hourly_rate,
        portfolio_url=body.portfolio_url,
        competences=[(c.skill_id, c.level) for c in body.competences]
        if body.competences is not None
        else None,
        availabilities=[(a.start, a.end) for a in body.availabilities]
        if body.availabilities is not None
        else None,
    )
    return UserOut.from_entity(updated)


@accounts.get("/skills", response_model=list[SkillOut])
def list_skills(ctx: RequestContext = Depends(get_context)) -> list[SkillOut]:
    return [SkillOut.from_entity(s) for s in ctx.uow.skills.list_all()]


@accounts.post("/skills/requests", status_code=201)
def request_skill(
    body: SkillRequestIn,
    user: User = Depends(get_current_user),
    ctx: RequestContext = Depends(get_context),
) -> dict:
    """R8 — request the addition of a new skill to the controlled vocabulary."""
    req = RequestSkill(ctx.uow, ctx.bus).execute(user.id, body.name)
    return {"id": req.id, "name": req.name, "approved": req.approved}


# --------------------------------------------------------------- projects -- #


@projects.post("/projects", response_model=ProjectOut, status_code=201)
def publish_project(
    body: ProjectIn,
    client: Client = Depends(require_client),
    ctx: RequestContext = Depends(get_context),
) -> ProjectOut:
    """S2 / R11, R12 — validated and put in 'open' by the domain; publication
    triggers the ranking and the notification fan-out via the event bus."""
    project = PublishProject(ctx.uow, ctx.bus).execute(
        client.id,
        body.title,
        body.description,
        set(body.required_skill_ids),
        body.max_budget,
        body.deadline,
    )
    return ProjectOut.from_entity(project)


@projects.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str, ctx: RequestContext = Depends(get_context)
) -> ProjectOut:
    project = ctx.uow.projects.get_with_proposals(project_id)
    if project is None:
        raise ValidationError("PROJECT_NOT_FOUND", "no such project")
    return ProjectOut.from_entity(project)


@projects.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    body: ProjectUpdateIn,
    client: Client = Depends(require_client),
    ctx: RequestContext = Depends(get_context),
) -> ProjectOut:
    """R45 — the Client owner may update title and/or description while
    the Project is 'open' (checked in the domain); owner-only (R42)."""
    project = UpdateProject(ctx.uow).execute(
        client.id, project_id, title=body.title, description=body.description
    )
    return ProjectOut.from_entity(project)


@projects.post("/projects/{project_id}/complete", response_model=ProjectOut)
def complete_project(
    project_id: str,
    client: Client = Depends(require_client),
    ctx: RequestContext = Depends(get_context),
) -> ProjectOut:
    """S5 / R18 — only the owner can complete (checked in the use case)."""
    project = CompleteProject(ctx.uow, ctx.bus).execute(client.id, project_id)
    return ProjectOut.from_entity(project)


# -------------------------------------------------------------- proposals -- #


@proposals.post(
    "/projects/{project_id}/proposals", response_model=ProposalOut, status_code=201
)
def submit_proposal(
    project_id: str,
    body: ProposalIn,
    freelancer: Freelancer = Depends(require_freelancer),
    ctx: RequestContext = Depends(get_context),
) -> ProposalOut:
    """S3 / R13-R14, R17 — open + before deadline + no duplicate (domain)."""
    proposal = SubmitProposal(ctx.uow, ctx.bus).execute(
        freelancer.id, project_id, body.cover_letter, body.offer
    )
    return ProposalOut.from_entity(proposal)


@proposals.post(
    "/projects/{project_id}/proposals/{proposal_id}/accept",
    response_model=ProjectOut,
)
def accept_proposal(
    project_id: str,
    proposal_id: str,
    client: Client = Depends(require_client),
    ctx: RequestContext = Depends(get_context),
) -> ProjectOut:
    """S4 / R15-R16 — atomic acceptance with cascade rejection (R16)."""
    project = AcceptProposal(ctx.uow, ctx.bus).execute(
        client.id, project_id, proposal_id
    )
    return ProjectOut.from_entity(project)


# --------------------------------------------------------------- matching -- #


@matching.get(
    "/projects/{project_id}/ranking", response_model=list[RankingEntryOut]
)
def project_ranking(
    project_id: str,
    client: Client = Depends(require_client),
    ctx: RequestContext = Depends(get_context),
) -> list[RankingEntryOut]:
    """R20 — expose to the owning client the top-N ranking (computed at
    publication, R19), read from the projection. Owner-only (R42)."""
    project = ctx.uow.projects.get(project_id)
    if project is None:
        raise ValidationError("PROJECT_NOT_FOUND", "no such project")
    if project.client_id != client.id:
        raise ValidationError("NOT_OWNER", "only the owner can see the ranking")
    ranking = ctx.uow.rankings.get_project_ranking(project_id)
    return [RankingEntryOut(entity_id=fid, score=sc) for fid, sc in ranking]


@matching.get(
    "/users/me/suggested-projects", response_model=list[RankingEntryOut]
)
def suggested_projects(
    freelancer: Freelancer = Depends(require_freelancer),
    ctx: RequestContext = Depends(get_context),
) -> list[RankingEntryOut]:
    """R21 — the freelancer's suggested-project view (kept fresh by the
    profile-update and publication handlers)."""
    ranking = ctx.uow.rankings.get_suggested_projects(freelancer.id)
    return [RankingEntryOut(entity_id=pid, score=sc) for pid, sc in ranking]


# ----------------------------------------------------------------- search -- #


@search.get("/search/freelancers", response_model=list[UserOut])
def search_freelancers(
    skill_ids: list[str] = Query(default=[]),
    rate_min: Optional[float] = None,
    rate_max: Optional[float] = None,
    available_from: Optional[date] = None,
    available_to: Optional[date] = None,
    order_by: str = "score",
    reference_project_id: Optional[str] = None,
    client: Client = Depends(require_client),
    ctx: RequestContext = Depends(get_context),
) -> list[UserOut]:
    """R27, R29 — client-side manual search of freelancers."""
    found = ManualSearch(ctx.uow, ctx.strategy).search_freelancers(
        skill_ids=set(skill_ids) or None,
        rate_min=rate_min,
        rate_max=rate_max,
        available_from=available_from,
        available_to=available_to,
        order_by=order_by,
        reference_project_id=reference_project_id,
    )
    return [UserOut.from_entity(f) for f in found]


@search.get("/search/projects", response_model=list[ProjectOut])
def search_projects(
    skill_ids: list[str] = Query(default=[]),
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
    deadline_from: Optional[date] = None,
    deadline_to: Optional[date] = None,
    order_by: str = "score",
    freelancer: Freelancer = Depends(require_freelancer),
    ctx: RequestContext = Depends(get_context),
) -> list[ProjectOut]:
    """R28, R29 — freelancer-side manual search of open projects."""
    found = ManualSearch(ctx.uow, ctx.strategy).search_projects(
        freelancer_id=freelancer.id,
        skill_ids=set(skill_ids) or None,
        budget_min=budget_min,
        budget_max=budget_max,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        order_by=order_by,
    )
    return [ProjectOut.from_entity(p, with_proposals=False) for p in found]


# ---------------------------------------------------------------- reviews -- #


@reviews.post(
    "/projects/{project_id}/reviews", response_model=ReviewOut, status_code=201
)
def submit_review(
    project_id: str,
    body: ReviewIn,
    user: User = Depends(get_current_user),
    ctx: RequestContext = Depends(get_context),
) -> ReviewOut:
    """S5 / R31-R33 — one review per (project, author), reputation updated
    in the same transaction (R31/R33)."""
    review = SubmitReview(ctx.uow, ctx.bus).execute(
        user.id, project_id, body.rating, body.comment
    )
    return ReviewOut.from_entity(review)


# ------------------------------------------------- notifications & dashboard - #


@dashboard.get("/users/me/notifications", response_model=list[NotificationOut])
def my_notifications(
    user: User = Depends(get_current_user),
    ctx: RequestContext = Depends(get_context),
) -> list[NotificationOut]:
    """R35-R38 — the authenticated user's notification feed (R42)."""
    return [
        NotificationOut.from_entity(n)
        for n in ctx.uow.notifications.list_by_user(user.id)
    ]


@dashboard.get("/users/me/dashboard", response_model=DashboardOut)
def my_dashboard(
    user: User = Depends(get_current_user),
    ctx: RequestContext = Depends(get_context),
) -> DashboardOut:
    """R39/R40 — aggregates the read-side projections (incl. reputation, R40) for the principal."""
    notifications = [
        NotificationOut.from_entity(n)
        for n in ctx.uow.notifications.list_by_user(user.id)
    ]
    suggested: list[RankingEntryOut] = []
    my_projects: list[ProjectOut] = []
    if isinstance(user, Freelancer):
        suggested = [
            RankingEntryOut(entity_id=pid, score=sc)
            for pid, sc in ctx.uow.rankings.get_suggested_projects(user.id)
        ]
        my_projects = [
            ProjectOut.from_entity(p, with_proposals=False)
            for p in ctx.uow.projects.list_with_proposals_by_freelancer(user.id)
        ]
    else:
        my_projects = [
            ProjectOut.from_entity(p, with_proposals=False)
            for p in ctx.uow.projects.list_by_client(user.id)
        ]
    return DashboardOut(
        user_id=user.id,
        role=user.role.value,
        notifications=notifications,
        suggested_projects=suggested,
        my_projects=my_projects,
    )


# ---------------------------------------------------------------- metrics -- #


@metrics.get("/metrics/matching")
def matching_metrics(ctx: RequestContext = Depends(get_context)) -> dict:
    """R44 — the matching-quality counters accumulated by the handlers."""
    return ctx.uow.metrics.snapshot()


ALL_ROUTERS = (
    accounts,
    projects,
    proposals,
    matching,
    search,
    reviews,
    dashboard,
    metrics,
)
