<div align="center">

# Design Document

### FreelanceMatch
*A web platform for automatic freelancer–client matching*

---

**Politecnico di Milano**
Software Engineering for Automation — A.Y. 2024-2025

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
