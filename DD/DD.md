<div align="center">

# Design Document

### FreelanceMatch
*A web platform for automatic freelancer–client matching*

---

**Politecnico di Milano**
Software Engineering for Automation — A.Y. 2025-2026

</div>

| | |
|---|---|
| **Authors** | Olmo Luca (10838404), Palladino Antonio (10778757), Pensotti Francesca (10777621) |
| **Repository** | `https://github.com/<owner>/SE4A_LucaOlmo_AntonioPalladino_FrancescaPensotti` |

---

## Table of contents

- [1. Introduction](#1-introduction)
  - [1.1 Purpose](#11-purpose)
  - [1.2 Definitions, Acronyms, Abbreviations](#12-definitions-acronyms-abbreviations)
  - [1.3 Revision history](#13-revision-history)
  - [1.4 Document structure](#14-document-structure)
- [2. Architectural Design](#2-architectural-design)
  - [2.1 Component view](#21-component-view)
  - 2.2 Class view
  - 2.3 Runtime view
  - 2.4 Selected architectural styles and patterns
- 3. User Interface Design *(TBD)*
- 4. Requirements Traceability *(TBD)*
- 5. Implementation, Integration and Test Plan *(TBD)*
- 6. References *(TBD)*

---

## 1. Introduction

### 1.1 Purpose

This document describes the design of FreelanceMatch, whose requirements are specified in the Requirements Analysis and Specification Document (RASD). While the RASD answers the question of *what* the system must do (its goals (G1–G6), its functional requirements (R1–R32) and the qualities it must exhibit (NFR1–NFR17)),  this document answers the question of *how* the system is organised to do it.

The main goals of the project, stated in full in RASD Sec. 1.1, are recalled here in compact form to keep this document self-contained:

- **G1/G2** — bidirectional automatic matching: ranked freelancers for every published project, ranked projects for every registered freelancer;
- **G3** — management of the full project lifecycle with the constraints of each phase;
- **G4** — reputation derived from mutual reviews, fed back into the matching;
- **G5** — replaceability of the matching algorithm without changes to the rest of the system;
- **G6** — manual search complementary to the automatic matching.

The design presented here is organised around three architectural decisions, each anticipated in the RASD and motivated in Sec. 2.4 of this document: a *Strategy* interface that isolates the matching algorithm (G5, R20, NFR15); an *Observer*-based event mechanism that decouples lifecycle transitions from their side effects (notifications, ranking recomputation); and a *Repository* layer that abstracts data access so that the domain logic can be tested against in-memory implementations.

The target implementation, described in Sec. 5, is a Python web service exposing a REST API (FastAPI) backed by a relational store (SQLite via SQLAlchemy); the system is delivered API-first, with the auto-generated OpenAPI interface serving as the demonstration UI (see Sec. 3).

### 1.2 Definitions, Acronyms, Abbreviations

The definitions of the domain terms (Client, Freelancer, Project, Proposal, Review, Reputation, Matching, Compatibility score *S(P,F)*, etc.) are given in RASD Sec. 1.3.1 and are not repeated here. The following additional terms are specific to this document.

| Term | Definition |
|---|---|
| **Component** | A unit of the system with a well-defined responsibility and an explicit interface towards the other components. In this design, components correspond to Python packages. |
| **Use case (application service)** | The orchestration of a single user-triggered flow (one of the scenarios S1–S6 of RASD Sec. 2.1), implemented as one application-layer module that coordinates domain entities, repositories and events. |
| **Event bus** | The in-process publish/subscribe mechanism through which lifecycle events are propagated to their observers. |
| **Domain layer** | The set of entities, value objects and invariants of RASD Sec. 2.2, implemented without dependencies on frameworks, persistence or transport. |
| **DTO** | Data Transfer Object: the request/response schema exposed by the REST API, distinct from the domain entities. |

| Acronym | Meaning |
|---|---|
| DD | Design Document |
| RASD | Requirements Analysis and Specification Document |
| API | Application Programming Interface |
| REST | Representational State Transfer |
| ORM | Object-Relational Mapping |
| FSM | Finite State Machine |

### 1.3 Revision history

| Version | Date | Notes |
|---------|------|-------|
| 0.1 | 2026-06-12 | Section 1-2 |

### 1.4 Document structure

**Section 2 (Architectural Design)** presents the architecture from four complementary points of view: the component view (Sec. 2.1) identifies the components, their responsibilities and the interfaces they export; the class view (Sec. 2.2) refines the most relevant components into class diagrams; the runtime view (Sec. 2.3) shows how the components interact to accomplish the main scenarios of the RASD; Sec. 2.4 names and motivates the architectural styles and design patterns adopted.

**Section 3 (User Interface Design)** describes the interface through which the system is operated, which in this API-first delivery is the auto-generated OpenAPI (Swagger) console.

**Section 4 (Requirements Traceability)** maps the requirements R1–R32 of the RASD onto the design elements introduced in Section 2, extending the traceability matrix of RASD Sec. 2.4.7.

**Section 5 (Implementation, Integration and Test Plan)** defines the order in which the components will be implemented, the order in which they will be integrated, and the strategy for testing the integration.

**Section 6 (References)** lists the sources cited in this document.

---

## 2. Architectural Design

### 2.1 Component view

Figure 1 shows the components of the system and the dependencies between them. The architecture is layered: each component belongs to one of four layers — presentation, application, domain, infrastructure — and dependencies point inward, towards the domain. The domain layer has no outgoing dependency: it does not know how it is stored, how it is exposed over the network, or which concrete matching algorithm is active. This direction of dependencies is the single most important property of the architecture, because it is what makes the three replaceability requirements of the RASD (R20/NFR15 for the matching strategy, DEP1/Sec. 2.6.2 for the data store) achievable without touching the domain logic.

![Component view — Figure 1](images/component_view.png)

The components, their responsibilities and the interfaces they export are described below. Component names correspond one-to-one to the Python packages of the implementation (Sec. 5), so that the mapping between this document and the source tree is direct.

#### 2.1.1 API Gateway (`api`)

The single entry point of the system. It exposes the REST interface described by the auto-generated OpenAPI specification (Sec. 3), translates HTTP requests into invocations of the application-layer use cases, and translates the results (or the domain errors) back into HTTP responses with the appropriate status codes. The component contains no business logic: every rule lives in the layers below. 

#### 2.1.2 Use Cases (`application`)

One module per scenario of RASD Sec. 2.1: `register_user` (S1), `publish_project` (S2), `submit_proposal` (S3), `accept_proposal` (S4), `complete_and_review` (S5), `manual_search` (S6). Each use case orchestrates the same four collaborators: it loads and saves entities through **IRepository**, invokes the active matching algorithm through **IMatchingStrategy** when needed, mutates the domain entities (which enforce their own invariants), and publishes lifecycle events through **IEventBus**. The use case layer is also where transactional boundaries are drawn: the atomic block of R12 (acceptance + cascading rejections + project transition) is delimited here, around the corresponding repository operations (NFR6).

#### 2.1.3 Domain Model (`domain`)

The implementation of the entities and invariants of RASD Sec. 2.2: `User` (with `Client` and `Freelancer`), `Skill`, `Competence`, `Availability`, `Project`, `Proposal`, `Review`. State transitions follow exactly the finite state machines of RASD Sec. 3.2; invalid transitions and violations of the invariants DOM1–DOM7 raise domain errors that the upper layers translate into user-facing failures. The component depends on nothing: it is plain Python, importable and testable in isolation.

#### 2.1.4 Matching (`matching`)

The implementation of the matching procedure behind the **IMatchingStrategy** interface (R20). The interface exposes a single operation, `rank(project, candidates) → ordered list of (freelancer, score)`, plus its symmetric counterpart for the freelancer-side ranking. Two concrete strategies are provided: `WeightedScoreStrategy`, implementing the score S(P,F) of R18 with its four weighted sub-scores and the hard filters of R19; and `RuleBasedStrategy`, the sequential-criteria baseline used for the quality comparison described in the project proposal (NFR16). The active strategy is selected by configuration at startup; adding a third strategy requires implementing the interface and registering it, with no change to any other component (NFR15).

#### 2.1.5 Event Bus (`events`)

The in-process publish/subscribe mechanism behind the **IEventBus** interface. Use cases publish typed lifecycle events — `ProjectPublished`, `ProposalReceived`, `ProposalAccepted`, `CollaborationCompleted`, `ProfileUpdated` — and handlers registered at startup react to them: notification creation (R28–R31), ranking recomputation on profile updates (R16, R17), reputation refresh on review submission (R27). The publisher does not know its subscribers; adding a new side effect to an existing event means adding a new handler, not modifying the use case that publishes it.

#### 2.1.6 Repositories (`repositories`)

The data-access layer behind the **IRepository** interface family (one repository per aggregate: users, projects, proposals, reviews, notifications, skills). Two implementations are provided: the SQLite/SQLAlchemy implementation used at runtime, and an in-memory implementation used by the test suite, which makes the domain and application layers testable without a database (the rationale anticipated in RASD Sec. 2.6.2/DEP1). The repository layer is the only component allowed to touch the database.

#### 2.1.7 Dependency rules

The dependency rules, visible as arrow directions in Figure 1, are summarised below; they will be enforced during implementation by the package import structure.

| Component | May depend on | Must not depend on |
|---|---|---|
| `api` | `application` | `domain`, `matching`, `events`, `repositories` directly |
| `application` | `domain`, and the three interfaces (`IMatchingStrategy`, `IEventBus`, `IRepository`) | concrete implementations in `matching`, `events`, `repositories` |
| `domain` | nothing | everything else |
| `matching` | `domain` | `application`, `api`, `repositories` |
| `events` | `domain` (event payloads) | `api` |
| `repositories` | `domain` | `application`, `api`, `matching` |

### 2.2 Class view

This section refines two of the components introduced in Sec. 2.1 down to the class level: the Domain Model and the Matching component. These two are the ones whose internal structure carries actual design decisions; the remaining components (API Gateway, Use Cases, Event Bus, Repositories) are intentionally thin — their structure is one module per responsibility, fully described by Sec. 2.1 and by the runtime view of Sec. 2.3, and a class diagram would add no information.

#### 2.2.1 Domain Model

Figure 2 shows the classes of the `domain` package. The diagram is the implementation-level refinement of the conceptual domain model of RASD Sec. 2.2: the entities, associations and multiplicities are unchanged, and the refinement consists of (i) concrete attribute types, (ii) the behavioural methods that each entity exposes, and (iii) the explicit enumerations backing the `status` attributes.

![Class view: domain — Figure 2](images/class_domain.png)

The key design decision in this diagram is that **state transitions are methods of the entities themselves**, not procedures of the application layer. `Project.accept_proposal()` and `Project.mark_completed()` implement the FSM of RASD Sec. 3.2.1; `Proposal.accept()` and `Proposal.reject()` implement the FSM of RASD Sec. 3.2.2. Each method checks the current state and raises a `DomainError` when the requested transition is not legal. For instance, `accept_proposal()` on a project whose status is not `OPEN` fails before any side effect occurs. This placement guarantees that the invariants DOM1–DOM7 cannot be bypassed: there is no code path that mutates a `status` attribute directly, so any caller, present or future, goes through the validating methods.

Transition methods return the list of `DomainEvent`s that the transition implies (e.g. `accept_proposal()` returns a `ProposalAccepted` event carrying the identifiers of the accepted and rejected proposals). The entity *decides* which events occurred; the application layer *publishes* them on the event bus after the transaction commits. This split keeps the domain free of any dependency on the event infrastructure while still making the entity the single source of truth for what happened.

`User.reputation` is stored as a plain attribute and recomputed by `update_reputation(reviews)` upon submission of a new review (R27, DOM7), rather than being recalculated on every read: the trade-off favours read performance (reputation is read by every matching computation) at the negligible cost of one extra write per review.

#### 2.2.2 Matching

Figure 3 shows the classes of the `matching` package, the concrete realisation of the *Strategy* pattern required by R20/NFR15.

![Class view: matching — Figure 3](images/class_matching.png)

`MatchingStrategy` is the interface the application layer depends on. It exposes the two ranking directions of G1/G2 as separate operations — `rank_freelancers(project, candidates)` and `rank_projects(freelancer, open_projects)` — both returning ordered lists of scored results, truncated to the configured length *N* by the caller.

`WeightedScoreStrategy` is the default implementation and realises the score S(P,F) of R18. The four sub-scores (`s_skills`, `s_budget`, `s_reputation`, `s_availability`) are private methods, each normalised in [0,1]; `compute_score` combines them with the weights held by the `MatchingWeights` value object, whose `validate()` enforces that the weights sum to one. Hard filters (R19) are applied before any score is computed, so excluded candidates never enter the scoring loop. Keeping the weights in a separate value object (rather than as constructor arguments) gives the administrator-facing configuration of RASD C5 a single, validated home.

`RuleBasedStrategy` is the second implementation, used as the comparison baseline for the matching-quality assessment (NFR16): it ranks by sequential criteria the full skill coverage first, then budget feasibility, then decreasing reputation without any weighted combination.

The active strategy is chosen by configuration at application startup and injected into the use cases that need it (S2 publication, S6 search ordering, profile-update recomputations). No component other than the startup wiring knows which concrete class is active; replacing or adding a strategy therefore satisfies NFR15 by construction.

### 2.3 Runtime view

This section shows how the components of Sec. 2.1 collaborate at runtime to accomplish the main scenarios of the system. The same selection criterion of RASD Sec. 3.1 applies, now at the design level: a runtime diagram is included only for the flows in which the *internal* collaboration between components carries design decisions that the component view alone cannot show. These are, again, S2 (project publication, where the matching strategy and the event propagation enter the picture) and S4 (proposal acceptance, where the transactional boundary is the decision). The remaining scenarios follow the same uniform pattern — `api` → use case → repository (→ event bus) — with no variation worth a dedicated diagram.

Both diagrams use the components of Sec. 2.1 as lifelines, with the application layer depending only on the three interfaces (`IRepository`, `IMatchingStrategy`, `IEventBus`); the concrete implementations behind them are interchangeable, as discussed in Sec. 2.4.

#### 2.3.1 S2 — Project publication

Figure 4 shows the runtime interaction for the publication of a project (RASD scenario S2, requirements R7, R8, R15, R16, R18, R19, R28).

![Runtime view S2 — Figure 4](images/runtime_s2_publication.png)

Three design decisions are visible in the diagram. First, **validation happens in the domain**: `Project.create(...)` enforces R7 (mandatory fields, deadline in the future, budget ≥ 0) and sets the initial state per R8; the use case never constructs a `Project` in an invalid state. Second, **the ranking computation goes through `IMatchingStrategy`**: the use case does not know whether the active strategy is the weighted-score or the rule-based one, which is the operational meaning of R20. Third, **side effects are observer-driven**: the use case publishes a single `ProjectPublished` event and terminates; the notification fan-out (R28) and the refresh of the freelancer-side suggested view (R16) happen in handlers subscribed to that event. Adding a further side effect to project publication — e.g. an audit log — would mean registering one more handler, with no change to `publish_project`.

The transaction in this flow covers only the persistence of the new project. The ranking computation runs after the commit: a failure in the matching must not roll back a correctly published project; in the worst case the ranking is recomputed on the next profile-update event, and the project remains visible in the catalogue for manual applications (consistently with the "empty ranking" alternative flow of RASD S2).

#### 2.3.2 S4 — Proposal acceptance

Figure 5 shows the runtime interaction for the acceptance of a proposal (RASD scenario S4, requirements R11, R12, R13, R30, NFR6).

![Runtime view S4 — Figure 5](images/runtime_s4_acceptance.png)

This is the flow where the transactional design decision lives, and the diagram makes its boundaries explicit. The atomic block of R12 starts when the use case loads the project together with its proposals, and ends with the single `projects.save(project)` commit. Inside the block, the entire decision logic is delegated to the domain: `Project.accept_proposal(proposal_id)` performs the FSM checks of RASD Sec. 3.2.1–3.2.2 and applies the three transitions (chosen proposal → `ACCEPTED`, every other pending proposal → `REJECTED`, project → `IN_PROGRESS`) on the in-memory aggregate. The repository then persists the aggregate in one commit: either all three transitions become visible, or none does (NFR6). Concurrent acceptance attempts are serialised at this commit point — the second transaction finds the project no longer `OPEN` and the domain check fails, which is the design-level realisation of the "concurrent acceptance" exception flow of RASD S4.

The `ProposalAccepted` event is published **after** the commit, never inside the transaction. This ordering rules out the failure mode in which freelancers receive acceptance or rejection notifications (R30) for a transition that was subsequently rolled back. The trade-off is the opposite, narrower failure mode — a crash between commit and publish would lose the notifications — which is acceptable for in-app notifications that the user can in any case derive from the dashboard state (R32).

