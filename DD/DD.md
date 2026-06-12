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
| **Version** | 0.1 |
| **Release date** | 2026-06-10 |
| **Repository** | `https://github.com/<owner>/SE4A_LucaOlmo_AntonioPalladino_FrancescaPensotti` |

---

## Table of contents

- [1. Introduction](#1-introduction)
  - [1.1 Purpose](#11-purpose)
  - [1.2 Definitions, Acronyms, Abbreviations](#12-definitions-acronyms-abbreviations)
  - [1.3 Revision history](#13-revision-history)
  - [1.4 Document structure](#14-document-structure)
- 2\. Architectural Design *(TBD)*
  - 2.1 Component view
  - 2.2 Class view
  - 2.3 Runtime view
  - 2.4 Selected architectural styles and patterns
- 3\. User Interface Design *(TBD)*
- 4\. Requirements Traceability *(TBD)*
- 5\. Implementation, Integration and Test Plan *(TBD)*
- 6\. References *(TBD)*

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
| 0.1 | 2026-06-10 | Initial draft. Section 1 (Introduction). |

### 1.4 Document structure

**Section 2 (Architectural Design)** presents the architecture from four complementary points of view: the component view (Sec. 2.1) identifies the components, their responsibilities and the interfaces they export; the class view (Sec. 2.2) refines the most relevant components into class diagrams; the runtime view (Sec. 2.3) shows how the components interact to accomplish the main scenarios of the RASD; Sec. 2.4 names and motivates the architectural styles and design patterns adopted.

**Section 3 (User Interface Design)** describes the interface through which the system is operated, which in this API-first delivery is the auto-generated OpenAPI (Swagger) console.

**Section 4 (Requirements Traceability)** maps the requirements R1–R32 of the RASD onto the design elements introduced in Section 2, extending the traceability matrix of RASD Sec. 2.4.7.

**Section 5 (Implementation, Integration and Test Plan)** defines the order in which the components will be implemented, the order in which they will be integrated, and the strategy for testing the integration.

**Section 6 (References)** lists the sources cited in this document.

