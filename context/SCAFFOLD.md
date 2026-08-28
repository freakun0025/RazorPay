## Purpose

This document defines the first implementation step for the Intelligent Revenue Recovery Engine.

The purpose of this step is to establish the complete project structure, architectural boundaries, initial data model, development infrastructure, and testing structure BEFORE implementing individual product features.

This is intentionally a separate phase from feature development.

The agent must first understand the complete scope of the system and create its skeleton.

---

# 1. Required Reading

Before scaffolding the project, read:

1. `PRD.md`
2. `architecture-essentials.md`
3. `architecture.md`
4. `AGENTS.md`

Do not begin scaffolding until these documents have been reviewed.

The scaffold must reflect the requirements and architecture contained in these documents.

---

# 2. Objective

Create the initial repository structure for the complete Intelligent Revenue Recovery Engine.

The scaffold should establish:

- application boundaries
- domain boundaries
- API boundaries
- persistence boundaries
- AI boundaries
- worker boundaries
- external integration boundaries
- configuration boundaries
- testing boundaries
- database migration structure
- container/development infrastructure
- documentation/ADR structure where appropriate

The objective is to make the project's intended architecture visible in the repository before feature implementation begins.

---

# 3. Important Rule: Scaffold First, Implement Later

During this step:

> **Create structure before implementing behavior.**

Do NOT implement the complete recovery workflow yet.

Do NOT build all API endpoints yet.

Do NOT build the AI decision engine yet.

Do NOT build the worker logic yet.

Do NOT implement the complete payment gateway simulation yet.

Do NOT prematurely optimize.

Do NOT invent additional product requirements.

The purpose of this step is to establish the skeleton.

Some files may contain:

- imports only
- class/interface declarations
- type definitions
- TODO comments
- placeholder functions
- empty configuration objects
- minimal schemas
- documentation comments

That is acceptable.

The project should be structurally complete even if behavior is not yet implemented.

---

# 4. Create the Directory Structure

Create the complete application structure according to the architecture.

A recommended starting structure is:

```text
.
├── AGENTS.md
├── CLAUDE.md
├── PRD.md
├── architecture.md
├── architecture-essentials.md
├── SCAFFOLD.md
│
├── README.md
├── .gitignore
├── .env.example
│
├── docker-compose.yml
├── Dockerfile
│
├── pyproject.toml
│
├── app/
│   ├── __init__.py
│   │
│   ├── main.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   ├── dependencies/
│   │   └── schemas/
│   │
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── recovery/
│   │   ├── payments/
│   │   ├── customers/
│   │   ├── subscriptions/
│   │   └── policies/
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── gateway/
│   │   ├── decision/
│   │   ├── prompts/
│   │   ├── tools/
│   │   └── schemas/
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── scheduler/
│   │   ├── executor/
│   │   └── jobs/
│   │
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── models/
│   │   ├── repositories/
│   │   └── transactions/
│   │
│   ├── integrations/
│   │   └── payment_gateway/
│   │
│   ├── audit/
│   │
│   ├── observability/
│   │
│   └── config/
│
├── migrations/
│   └── versions/
│
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   ├── policies/
│   │   ├── ai/
│   │   └── workers/
│   │
│   ├── integration/
│   │   ├── api/
│   │   ├── persistence/
│   │   ├── workers/
│   │   └── integrations/
│   │
│   └── e2e/
│
├── docs/
│   └── adr/
│
└── scripts/
````

The exact structure may be adjusted if the architecture documents require it.

Do not create unnecessary directories merely to make the repository look sophisticated.

---

# 5. Empty Directories

If a directory is part of the intended architecture but currently has no implementation:

CREATE IT ANYWAY.

Git does not track empty directories, so use an appropriate placeholder such as:

```text
.gitkeep
```

where necessary.

This is intentional.

The goal is for the repository structure to communicate the complete architectural scope from the beginning.

---

# 6. Initial Application Boundaries

The scaffold must establish the following conceptual boundaries.

## API

Responsible for:

* HTTP
* request validation
* response serialization
* webhook entry points
* dependency wiring

The API layer must not contain core recovery business logic.

---

## Domain

Responsible for:

* recovery cases
* payment state
* subscription state
* customer concepts
* state transitions
* business rules
* policy decisions

The domain should not depend directly on FastAPI.

---

## AI

Responsible for:

* model gateway
* prompt management
* structured AI decisions
* tool definitions
* AI schemas
* AI-specific evaluation support

The AI layer must not directly mutate financial state.

---

## Persistence

Responsible for:

* SQLAlchemy models
* database access
* repositories
* transaction boundaries
* database infrastructure

Persistence must not become the owner of business rules.

---

## Workers

Responsible for:

* durable job processing
* job claiming
* scheduled execution
* recovery action execution
* retry handling
* worker lifecycle

---

## Integrations

Responsible for external-system interfaces and adapters.

Initially this includes the mock payment gateway.

The domain should depend on an interface/port rather than directly on the mock implementation.

---

## Audit

Responsible for append-only audit event creation and related infrastructure.

---

## Observability

Responsible for:

* structured logging
* metrics
* correlation IDs
* instrumentation

Do not add an external observability platform unless explicitly required.

---

# 7. Initial Data Model

Create the initial database model structure based on `architecture.md`.

The initial entities are:

```text
Customer
    │
    └── Subscription
            │
            └── Payment
                    │
                    └── Recovery Case
                            │
                            ├── Recovery Attempt
                            ├── Recovery Decision
                            ├── Scheduled Job
                            └── Audit Events
```

The initial persistence model should account for:

* customers
* subscriptions
* payments
* recovery cases
* recovery attempts
* recovery decisions
* recovery jobs
* idempotency records
* audit events

Create the SQLAlchemy model structure and relationships.

Do not over-engineer the models.

Do not add entities that are not required by the product or architecture.

---

# 8. Database Rules

The initial database structure must respect:

* PostgreSQL
* SQLAlchemy 2.x
* Alembic
* UUID identifiers where specified
* explicit currency fields
* `NUMERIC` for monetary values
* timestamps
* foreign-key relationships
* appropriate uniqueness constraints
* appropriate indexes
* state/status fields

Money must never use floating-point database types.

The initial schema should be designed so that financial and recovery state can be represented correctly.

---

# 9. State Machine Scaffold

Create the initial state definitions and transition structure for:

* payment states
* recovery case states
* recovery attempt states
* job states

The scaffold should make invalid transitions difficult to implement accidentally.

At this stage, it is acceptable for transition implementations to contain placeholders.

However, the intended state machine must be visible in the code.

Do not allow arbitrary string mutations to become the eventual design.

---

# 10. API Scaffold

Create the initial API routing structure based on the architecture.

Expected categories include:

```text
/api/v1/...

payments
webhooks
recovery
metrics
```

Create route modules and schemas where appropriate.

The endpoints do not need full business behavior during scaffolding.

For example, a route may initially contain:

```python
@router.post(...)
async def endpoint(...):
    raise NotImplementedError
```

or an appropriate placeholder.

Do not build fake functionality merely to make endpoints appear operational.

---

# 11. AI Scaffold

Create the AI module boundaries:

```text
app/ai/
├── gateway/
├── decision/
├── prompts/
├── tools/
└── schemas/
```

Create initial interfaces/schemas for:

* AI gateway
* recovery decision
* tool definitions
* structured decision output
* prompt versioning

The AI must operate through a bounded interface.

Do not connect the entire application to an LLM during the scaffold phase unless required merely to validate configuration.

---

# 12. Worker Scaffold

Create the worker structure:

```text
app/workers/
├── scheduler/
├── executor/
└── jobs/
```

Establish the conceptual flow:

```text
Poll
  ↓
Claim
  ↓
Validate
  ↓
Execute
  ↓
Persist Result
  ↓
Audit
```

The worker implementation may initially be skeletal.

Do not build a complex distributed queue.

The initial architecture uses PostgreSQL-backed durable jobs.

---

# 13. Payment Gateway Scaffold

Create the integration boundary:

```text
PaymentGateway
       ↓
MockPaymentGateway
```

The interface should support the recovery workflow without coupling domain logic to the mock implementation.

The mock gateway should eventually be capable of simulating:

```text
SUCCESS
INSUFFICIENT_FUNDS
TEMPORARY_FAILURE
CARD_EXPIRED
DECLINED
NETWORK_ERROR
TIMEOUT
```

During scaffolding, it is enough to establish the interface and initial structure.

---

# 14. Configuration Scaffold

Create configuration management using environment variables.

Include placeholders for configuration such as:

```text
DATABASE_URL
AI_API_KEY
AI_MODEL
MAX_RECOVERY_ATTEMPTS
MAX_RECOVERY_WINDOW_HOURS
MAX_RETRY_DELAY_HOURS
WORKER_POLL_INTERVAL
JOB_LEASE_SECONDS
LOG_LEVEL
```

Create:

```text
.env.example
```

Never create a real `.env` containing secrets.

Never hard-code API keys.

---

# 15. Docker Scaffold

Create the initial local development infrastructure.

Expected conceptual services:

```text
backend
worker
postgres
```

The configuration should be intentionally simple.

Do not introduce Redis, Kafka, Kubernetes, or other infrastructure at this stage.

---

# 16. Testing Scaffold

Create the test structure before implementing features.

At minimum:

```text
tests/
├── unit/
├── integration/
└── e2e/
```

Create representative placeholder test modules for:

* state transitions
* policies
* AI validation
* persistence
* API behavior
* worker behavior
* payment gateway behavior
* complete recovery lifecycle

The goal is to establish where different classes of tests belong.

---

# 17. Documentation Scaffold

Create:

```text
docs/
└── adr/
```

Create a placeholder/readme explaining that significant architectural changes should be documented as ADRs.

Do not create dozens of speculative ADRs.

Only establish the mechanism.

---

# 18. Dependency Discipline

Use only dependencies justified by the current architecture.

The expected core stack is:

```text
Python
FastAPI
PostgreSQL
SQLAlchemy 2.x
Alembic
Pydantic
Gemini SDK
Pytest
Docker
```

Do not add:

```text
Kafka
Redis
Celery
LangGraph
Kubernetes
Vector databases
Microservices frameworks
```

unless an explicit architectural decision later requires them.

---

# 19. README Scaffold

Create an initial `README.md` that explains:

* what the project is
* the problem it solves
* the high-level architecture
* the current implementation stage
* how to start the local development environment
* where the major modules live

Clearly state that the project is currently in the **scaffolding phase** if feature implementation has not begun.

Do not claim features work when they have only been scaffolded.

---

# 20. Do Not Hide Missing Implementation

The scaffold should make incomplete areas obvious.

Prefer:

```text
TODO
NotImplementedError
placeholder interfaces
```

over fake implementations that appear functional.

A fake implementation can be dangerous because later agents may assume it is production behavior.

---

# 21. Scaffold Validation

After creating the structure, validate:

### Architecture

Does the repository structure correspond to `architecture-essentials.md` and `architecture.md`?

### Scope

Does the structure cover the complete intended product without inventing major features?

### Boundaries

Are API, domain, AI, persistence, workers, and integrations clearly separated?

### Data model

Are the major entities represented?

### Testing

Does every major subsystem have an obvious testing location?

### Infrastructure

Are local development requirements represented?

### Dependencies

Did the agent introduce unnecessary technologies?

### Implementation state

Did the agent accidentally implement business behavior during scaffolding?

---

# 22. Hard Questions

Before declaring scaffolding complete, the agent MUST answer:

## What do you think will break?

Identify structural weaknesses that could cause problems when features are implemented.

## What architectural boundary is missing?

Look for responsibilities that currently have nowhere appropriate to live.

## What edge cases are not represented?

Especially:

* duplicate events
* retries
* worker crashes
* gateway timeouts
* ambiguous external results
* invalid state transitions
* AI failure
* invalid AI output
* concurrent workers

## What is over-engineered?

Identify folders, abstractions, dependencies, or infrastructure that do not provide current value.

## What is under-engineered?

Identify missing boundaries that would force business logic into inappropriate modules later.

## What would an experienced backend engineer challenge?

Focus on architecture, correctness, maintainability, and operational behavior.

---

# 23. Final Scaffold Report

When scaffolding is complete, provide a concise report containing:

### Created

List the major directories and files created.

### Data Model

List the initial entities and important relationships.

### Architectural Boundaries

Explain where:

* API
* domain
* AI
* persistence
* worker
* integrations
* audit
* observability

live.

### Intentionally Unimplemented

List functionality that is deliberately not implemented yet.

### Dependencies Added

List dependencies and why each exists.

### Questions / Risks

List anything discovered that should be resolved before feature implementation.

### Hard-Question Review

Answer:

1. What will break?
2. What edge cases are missing?
3. What is over-engineered?
4. What is under-engineered?
5. What would an experienced backend engineer challenge?

---

# 24. Definition of Done

Scaffolding is complete when:

* [ ] Complete intended directory structure exists
* [ ] Required empty directories exist
* [ ] Application module boundaries exist
* [ ] Initial data model structure exists
* [ ] Database migration structure exists
* [ ] API structure exists
* [ ] AI structure exists
* [ ] Worker structure exists
* [ ] Integration structure exists
* [ ] Audit/observability structure exists
* [ ] Configuration structure exists
* [ ] Docker development structure exists
* [ ] Test structure exists
* [ ] ADR structure exists
* [ ] README exists
* [ ] No secrets are committed
* [ ] No unnecessary infrastructure was introduced
* [ ] No major business features were prematurely implemented
* [ ] Architecture was validated against project documents
* [ ] Hard-question review was completed

Only after these conditions are satisfied should feature implementation begin.

---

# Final Principle

> **The scaffold defines the territory before the agent starts building roads.**

The purpose of this phase is to give every subsequent coding task a clear architectural home.

Feature implementation should begin only after the repository structure, data model, boundaries, and development infrastructure have been established and reviewed.

````

