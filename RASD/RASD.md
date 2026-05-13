<div align="center">

# Requirements Analysis and Specification Document

### FreelanceMatch
*A web platform for automatic freelancer–client matching*

---

**Politecnico di Milano**
Software Engineering for Automation — A.Y. 2025-2026

</div>

| | |
|---|---|
| **Authors** | Olmo Luca (10838404), Palladino Antonio (10778757), Pensotti Francesca (10777621) |
| **Repository** | `https://github.com/<owner>/SE4A_Olmo_Palladino_Pensotti` |

---

## Table of contents

- [1. Introduction](#1-introduction)
  - [1.1 Purpose](#11-purpose)
  - [1.2 Scope](#12-scope)
    - [1.2.1 World and machine](#121-world-and-machine)
    - [1.2.2 Shared phenomena](#122-shared-phenomena)
  - [1.3 Definitions, Acronyms, Abbreviations](#13-definitions-acronyms-abbreviations)
    - [1.3.1 Definitions](#131-definitions)
    - [1.3.2 Acronyms and abbreviations](#132-acronyms-and-abbreviations)
  - [1.4 Document structure](#14-document-structure)
- 2\. Overall description *(TBD)*
  - [2.1 Scenarios](#21-scenarios)
  - [2.2 Domain model](#22-domain-model)
  - 2.3 User characteristics
  - 2.4 Product functions
  - 2.5 Non-functional aspects
  - 2.6 Assumptions, dependencies and constraints
- 3\. Additional models *(TBD)*
  - 3.1 Requirements-level sequence diagrams
  - 3.2 Finite state machines
- 4\. References *(TBD)*


## 1. Introduction

### 1.1 Purpose

FreelanceMatch is a web-based platform that mediates the encounter between freelance professionals and clients seeking to commission specific work. The problem the system addresses is the inefficiency of the manual search-and-filter workflow imposed by existing platforms (e.g., Upwork, Fiverr), where both sides must invest non-trivial time in sifting through profiles or postings before any contact can occur.

The system replaces (and, optionally, complements) this manual workflow with an automatic matching procedure: when a client publishes a project, the system computes a compatibility score for every available freelancer and presents a ranked shortlist; symmetrically, every freelancer receives a ranked list of projects whose requirements are compatible with their declared profile. Beyond the matching core, the platform manages the entire project lifecycle — from publication, through application and acceptance, to completion and mutual review — and maintains a reputation signal that feeds back into subsequent matches.

The high-level goals of the project are listed below; each goal is later refined into one or more functional requirements (Sec. 2.4) and traced from the corresponding scenarios (Sec. 2.1).

- **G1** — The system shall produce, for each published project, a ranked list of candidate freelancers ordered by a compatibility score that combines skills, budget, reputation and availability.
- **G2** — The system shall produce, for each registered freelancer, a ranked list of open projects compatible with the freelancer's declared profile.
- **G3** — The system shall manage the full lifecycle of a project, from publication to completion and review, enforcing the constraints of each phase (e.g., a client can accept at most one proposal per project; a project under way no longer accepts proposals).
- **G4** — The system shall maintain, for each user, a reputation derived from the reviews received at the end of past collaborations, and shall make this reputation available as an input to the matching procedure.
- **G5** — The matching procedure shall be replaceable with alternative algorithms (e.g., a rule-based ranker) without altering the rest of the system.
- **G6** — The system shall provide both clients and freelancers with a manual search facility, complementary to the automatic matching, so that a user can override the suggested ranking when desired.


### 1.2 Scope

This section describes who interacts with the system and what is exchanged at its boundary. We separate the *world*, i.e. the actors and processes outside the platform, from the *machine*, i.e. the platform itself.

#### 1.2.1 World and machine

The world includes:

- **Clients**, who publish projects and choose the freelancer they want to work with.
- **Freelancers**, who maintain a profile, look at the projects available, and apply to those they are interested in.


The machine — FreelanceMatch — is the web platform that stores profiles and projects, computes the matching, shows ranked lists to the users, and keeps track of proposals, accepted collaborations, reviews and reputations.

#### 1.2.2 Shared phenomena

The points of contact between the world and the machine are listed below. We distinguish actions performed by users (`WP`, world phenomena observed by the machine) from actions performed by the system (`MP`, machine phenomena observed by the world).

**Controlled by the world**

- **WP1** — A user signs up and chooses a role (client or freelancer).
- **WP2** — A client publishes a project, providing title, description, required skills, maximum budget and application deadline.
- **WP3** — A freelancer creates or updates the profile (skills with mastery level, hourly rate, availability, portfolio link).
- **WP4** — A freelancer sends a proposal for an open project, with a cover letter and an economic offer.
- **WP5** — A client accepts one of the proposals received.
- **WP6** — A client marks a project as completed.
- **WP7** — A user submits a review at the end of a collaboration.
- **WP8** — A user runs a manual search with filters.

**Controlled by the machine**

- **MP1** — The system shows to a client the ranked list of freelancers suggested for a project.
- **MP2** — The system shows to a freelancer the ranked list of projects compatible with the freelancer profile.
- **MP3** — The system sends notifications when relevant events happen (new compatible project, new proposal, proposal accepted or rejected, project completed, review window opened).
- **MP4** — The system displays a personal dashboard to each user.
- **MP5** — The system updates the reputation of a user when a new review on that user is submitted.


### 1.3 Definitions, Acronyms, Abbreviations

#### 1.3.1 Definitions


| Term | Definition |
|---|---|
| **Client** | A registered user whose role is "client". Clients publish projects and choose which proposal to accept. |
| **Freelancer** | A registered user whose role is "freelancer". Freelancers maintain a profile and apply to the projects they are interested in. |
| **Profile** | The set of attributes describing a registered user. Clients and freelancers have different profile fields. |
| **Skill** | A competence declared by a freelancer in their profile, associated with a mastery level among "basic", "intermediate" and "advanced". |
| **Project** | A work assignment published by a client, characterised by a title, a description, a list of required skills, a maximum budget (in euros) and an application deadline. |
| **Proposal** | A candidacy submitted by a freelancer for a specific project, containing a cover letter and an economic offer (in euros). A freelancer cannot submit more than one proposal per project. |
| **Collaboration** | The relationship between a client and a freelancer that starts when the client accepts a proposal and ends when the project is marked as completed. |
| **Review** | A 1–5 star rating with an optional textual comment, submitted by one of the two parties at the end of a collaboration. A review cannot be edited after submission. |
| **Reputation** | An aggregate value, normalised in `[0,1]`, computed from the reviews received by a user. Users with no reviews are assigned a neutral reputation. |
| **Compatibility score *S(P,F)*** | A number in `[0,1]` expressing how compatible freelancer *F* is with project *P*. It combines four sub-scores: skills coverage, budget, reputation and availability. |
| **Ranking** | The list of freelancers (resp. projects) ordered by *S(P,F)* in decreasing order. |
| **Matching** | The procedure that, given a project (or a freelancer), produces the corresponding ranking. |
| **Notification** | An in-app message delivered to a user when a relevant lifecycle event takes place (see MP3). |

#### 1.3.2 Acronyms and abbreviations

| Acronym | Meaning |
|---|---|
| RASD | Requirements Analysis and Specification Document |
| UML  | Unified Modeling Language |
| FSM  | Finite State Machine |
| WP   | World Phenomenon (controlled by the world) |
| MP   | Machine Phenomenon (controlled by the machine) |
| G    | Goal |
| R    | Functional Requirement |
| NFR  | Non-Functional Requirement |
| DOM  | Domain Assumption |


### 1.4 Document structure

The remainder of this document is organised as follows.

**Section 2 (Overall description)** presents the requirements at a moderate level of detail. It opens with informal scenarios that illustrate, from the user's perspective, the typical interactions with the platform (Sec. 2.1). It then formalises the entities and relationships of the application domain through a class diagram (Sec. 2.2), characterises the user classes (Sec. 2.3), enumerates the product's functional requirements (Sec. 2.4) and non-functional requirements (Sec. 2.5), and concludes with the assumptions, dependencies and constraints under which the requirements are valid (Sec. 2.6).

**Section 3 (Additional models)** refines the requirements where useful with UML sequence diagrams at the requirements level (Sec. 3.1) and finite state machines for the entities whose lifecycle is non-trivial, in particular `Project` and `Proposal` (Sec. 3.2).

**Section 4 (References)** lists the external sources cited throughout the document.

---

## 2. Overall description

### 2.1 Scenarios

This section describes the main interaction flows between FreelanceMatch and its actors. Each scenario is presented as a structured flow rather than as a narrative: it lists the actor that triggers it, the preconditions under which the flow can be executed, the main sequence of steps performed by the actor and by the system, the postconditions after a successful execution, and the relevant alternative or exception flows. Each step is annotated with the shared phenomena (`WP`/`MP`, see Sec. 1.2.2) that it exercises, so that the trace from the boundary description to the requirements (Sec. 2.4) is explicit.

The scenarios cover the lifecycle of the system from registration to review and span both directions of the matching (client-driven and freelancer-driven). The scenarios are intentionally separated by responsibility: where two actors interact across time, the flow is split at the system boundary so that each scenario remains driven by a single actor.

#### S1 — Account creation and profile setup

**Primary actor.** Any unregistered visitor.

**Preconditions.** The visitor has access to the public landing page; no authenticated session exists.

**Main flow.**
1. The actor selects a role among `client` and `freelancer` and submits the registration data *(WP1)*.
2. The system validates the data (well-formed email, password complexity, role consistency) and creates a `User` record with an initial neutral reputation `0.5`.
3. The actor completes the role-specific profile fields *(WP3)*: a `Client` provides business name, sector and typical needs; a `Freelancer` provides one or more `Competence`s (each pointing to a `Skill` with a mastery level), the hourly rate, one or more `Availability` windows and an optional portfolio link.
4. The system persists the profile and indexes it for use by the matching procedure (Sec. 2.2).

**Postconditions.** The actor holds an authenticated session bound to the chosen role. For freelancers, the profile is now eligible to appear in the ranking of any open project whose required skills overlap with the declared competences.

**Alternatives and exceptions.**
- *Duplicate email.* The system rejects the registration without creating any record.
- *Incomplete mandatory fields.* The system refuses to persist the profile and reports the missing fields; the user remains in an unauthenticated or partially configured state.
- *Skill not present in the catalogue.* The freelancer can request the addition of a new `Skill`; until the request is approved, the corresponding `Competence` is not used by the matching.

---

#### S2 — Project publication and computation of the candidate ranking

**Primary actor.** An authenticated `Client`.

**Preconditions.** The client has at least one valid payment-and-contact configuration on the profile (the system does not collect payments, but the contact information must be present).

**Main flow.**
1. The client submits a new project specifying: title, description, set of required `Skill`s, maximum budget, application deadline *(WP2)*.
2. The system validates the project (mandatory fields present, deadline in the future, budget ≥ 0, at least one required skill) and creates a `Project` with `status = open`.
3. The system triggers the matching procedure with the active strategy (Sec. 2.2 and `G5`). For every freelancer *F* whose hard filters are satisfied, the system computes the compatibility score *S(P,F)*.
4. The system ranks freelancers by *S(P,F)* in decreasing order, truncates to the top *N* (where *N* is a configuration parameter), and exposes the ranking to the client *(MP1)*.
5. The system delivers a notification of "new compatible project" to the freelancers in the ranking *(MP3)* and updates their personal "suggested projects" view *(MP2)*.

**Postconditions.** The project is visible in the catalogue with `status = open`; the ranking is available to the client for inspection until the application deadline expires or until a proposal is accepted (whichever comes first).

**Alternatives and exceptions.**
- *No freelancer satisfies the hard filters.* The system creates the project with an empty ranking and informs the client. The project remains open for manual applications.
- *Profile updates after publication.* If a freelancer updates the profile in a way that would have made them eligible for a project still in `open` state, the matching is recomputed for that project (the trigger is on profile-update events as well, per the *Observer* contract in Deliverable 2).

---

#### S3 — Submission of a proposal by a freelancer

**Primary actor.** An authenticated `Freelancer`.

**Preconditions.** The target project has `status = open`, the application deadline has not expired, and the freelancer has not already submitted a proposal for the same project (DOM1, Sec. 2.2).

**Main flow.**
1. The freelancer accesses the project — either from the suggested ranking *(MP2)*, from a notification *(MP3)*, or via manual search (S6).
2. The freelancer submits a proposal containing a cover letter and an economic offer in euros *(WP4)*.
3. The system validates the offer (numeric, ≥ 0, within plausible bounds) and creates a `Proposal` with `status = pending`, linked to the freelancer and to the project.
4. The system delivers a notification of "new proposal" to the project owner *(MP3)*.

**Postconditions.** The proposal is in the project's list of received proposals, ordered by *S(P,F)* of the corresponding freelancer.

**Alternatives and exceptions.**
- *Application deadline expired between display and submission.* The system rejects the submission, informs the freelancer and refreshes the project view.
- *Project moved to* `inProgress` *between display and submission* (i.e. another proposal was accepted in the meantime). Same handling as the previous case.
- *Duplicate proposal* (DOM1). The system rejects the second submission and points the freelancer to the existing one.

---

#### S4 — Acceptance of a proposal and transition to `inProgress`

**Primary actor.** The `Client` owner of the project.

**Preconditions.** The project has `status = open` and at least one `Proposal` with `status = pending`.

**Main flow.**
1. The client inspects the list of received proposals, ordered by *S(P,F)* *(MP1)*.
2. The client accepts one specific proposal *(WP5)*.
3. The system performs, atomically with respect to other lifecycle transitions of the same project: (i) sets the chosen proposal's `status` to `accepted`; (ii) sets every other pending proposal of the same project to `status = rejected`; (iii) sets the project's `status` to `inProgress`. This sequence preserves the invariant DOM2 (at most one accepted proposal per project) and DOM3 (project status reflects acceptance).
4. The system delivers an "accepted" notification to the chosen freelancer and a "rejected" notification to every other involved freelancer *(MP3)*.
5. From this point on, the project is removed from the open catalogue and refuses any further submission attempt (see S3 exceptions).

**Postconditions.** Exactly one accepted proposal exists for the project; the project is in `inProgress`; the application channel is closed.

**Alternatives and exceptions.**
- *Concurrent acceptance attempts.* The transitions in step 3 are serialised; the second attempt observes `status ≠ open` and is rejected.
- *Cancellation by the client before acceptance.* (Out of scope of this iteration; an open project can only transition to `inProgress` or remain `open` until the deadline.)

---

#### S5 — Completion of the collaboration and mutual review

**Primary actor.** The `Client` owner of the project (for completion); both parties (for the review).

**Preconditions.** The project has `status = inProgress` and exactly one `Proposal` with `status = accepted` (DOM3).

**Main flow.**
1. The client marks the project as completed *(WP6)*. The system transitions the project to `status = completed` (DOM4) and opens the review window for both parties.
2. The system delivers a "review window opened" notification to the client and to the freelancer of the accepted proposal *(MP3)*.
3. Each party (independently) submits at most one review whose `target` is the counterpart, providing a 1–5 rating and an optional comment *(WP7)*. DOM5 and DOM6 govern the existence and uniqueness of each review.
4. On submission of every review, the system updates the `reputation` of the target user as a function of the reviews where the user is the target (DOM7), and immediately reflects the new value in any subsequent matching computation *(MP5)*.

**Postconditions.** The project is in `completed`; up to two reviews exist for the project (one per party); the reputations of both users reflect the new reviews.

**Alternatives and exceptions.**
- *One party never submits the review.* The system does not block the lifecycle: the missing review simply does not exist; the existing one is still recorded and counted.
- *Attempt to edit a submitted review.* The system rejects the modification (review is single-shot by definition).

---

#### S6 — Manual search and filtered browsing

**Primary actor.** Any authenticated user.

**Preconditions.** The actor is authenticated; no specific notification or ranking is required.

**Main flow.**
1. The actor opens the manual search view, distinct from the suggested ranking, and submits a query with filters *(WP8)*. The available filters depend on the role: a client filters freelancers by required skills, hourly-rate range and availability window; a freelancer filters projects by category, budget range and deadline window.
2. The system returns the records satisfying the filters and offers an explicit secondary ordering choice (by *S(P,F)*, by deadline, or by budget).
3. From the result list, the actor can navigate to a specific project (and trigger S3) or to a specific freelancer profile.

**Postconditions.** No state change is induced by the search itself. Any subsequent action (e.g. proposal submission) follows its own scenario.

**Alternatives and exceptions.**
- *Empty result set.* The system returns the empty list with an explicit indication; no error.
- *Filter values inconsistent with the catalogue* (e.g. budget range that no project satisfies). Same handling as empty result set.

---

The flows above span every shared phenomenon listed in Sec. 1.2.2 at least once: WP1, WP3 in S1; WP2 in S2; WP4 in S3 (and reused in S6 as the entry point); WP5 in S4; WP6, WP7 in S5; WP8 in S6; MP1 and MP3 are exercised in multiple scenarios (S2, S3, S4, S5); MP2 in S2; MP4 is implicitly exercised whenever any scenario produces a state change; MP5 in S5.


### 2.2 Domain model

This section formalises the entities of the application domain and the relationships between them. The model is intentionally kept at the conceptual level: it captures *what* the system has to talk about, not *how* it stores it. Figure 1 shows the resulting UML class diagram. 

![Domain model — Figure 1](images/UML_domainmodel.png)

**Actors and roles.** Every person registered on the platform is a `User`. The two roles a user can have, *Client* and *Freelancer*, are modelled as subclasses: a `User` is exactly one of the two and the role is fixed at registration time. The attributes that are common to both (e.g. email, registration date, reputation) live in `User`; the role-specific attributes — business-related fields for `Client`, hourly rate and portfolio for `Freelancer` — live in the respective subclasses.

**Skills and competences.** Skills are first-class citizens of the domain: the same `Skill` (e.g. "Figma") can be required by many projects and declared by many freelancers, and the matching procedure needs to compare them by identity rather than by string. The mastery level is not a property of the skill itself — it is a property of the *relation* between a `Freelancer` and a `Skill`, and it is reified through the class `Competence`. This gives a clean place to attach the mastery level (`basic` / `intermediate` / `advanced`) without polluting either side of the association.

**Availability.** Each `Freelancer` declares zero or more `Availability` windows (intervals of dates), used by the matching to assess whether the freelancer is free during the lifetime of a project.

**Projects and proposals.** A `Project` is published by a `Client`. It lists one or more required `Skill`s and it carries its own status — `open`, `inProgress` or `completed`. A `Proposal` is the candidacy of a freelancer for a project, with cover letter, economic offer and its own status (`pending`, `accepted` or `rejected`). We deliberately do *not* introduce a separate "Collaboration" class: a collaboration is uniquely identified by a `Project` whose status is `inProgress` or `completed` together with the unique `Proposal` whose status is `accepted` for that project, and modelling it as a separate entity would be redundant.

**Reviews.** A `Review` carries a rating (1–5), an optional comment and a timestamp. Each review has three associations: an *author* (the user who wrote it), a *target* (the user it is about) and a reference to the `Project` to which the collaboration refers. This shape lets the system enforce the constraint that for each completed project there are at most two reviews — one in each direction — and lets the reputation of a user be derived as an aggregate over the reviews where the user appears as target.

**Domain invariants.** The following invariants are not visible in the diagram and have to be enforced by the system. 

- **DOM1** — A `Freelancer` cannot have two `Proposal`s for the same `Project`.
- **DOM2** — For each `Project`, at most one `Proposal` has `status = accepted`.
- **DOM3** — A `Project` has `status = inProgress` if and only if exactly one of its `Proposal`s has `status = accepted` and the project has not yet been marked as completed.
- **DOM4** — A `Project` can transition to `status = completed` only from `status = inProgress`.
- **DOM5** — A `Review` whose target is user *u* and whose project is *p* exists only if (i) `p.status = completed`, (ii) the author and the target are the two parties of *p* (i.e. the client owner of *p* and the freelancer of the accepted proposal of *p*), and (iii) author ≠ target.
- **DOM6** — At most one `Review` per `(project, author)` pair: each party may review the counterpart at most once per collaboration.
- **DOM7** — `User.reputation` is a function of the `Review`s whose target is the user; for users with no reviews, the value is fixed to the neutral `0.5`.

---

