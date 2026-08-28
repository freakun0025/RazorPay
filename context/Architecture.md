# System Architecture — Intelligent Revenue Recovery Engine

## 1. Purpose of This Document

This document defines the technical architecture of the Intelligent Revenue Recovery Engine.

The PRD defines:

- What the product does
- Who it is for
- Product requirements
- Product scope
- Success criteria

This document defines:

- How the product is implemented
- System components
- Technology choices
- Data models
- State machines
- API boundaries
- AI architecture
- Asynchronous processing
- Reliability mechanisms
- Security boundaries
- Testing boundaries
- Scalability strategy

This document is the primary technical source of truth for implementation.

Any implementation decision that conflicts with this document should be explicitly identified before changing the architecture.

---

# 2. Architectural Goals

The architecture must optimize for:

1. Financial correctness
2. Reliability
3. Idempotency
4. Explicit state management
5. Safe asynchronous execution
6. Strong database integrity
7. Bounded AI execution
8. Auditability
9. Testability
10. Observability
11. Maintainability
12. Learning value

The architecture should resemble a production backend without introducing infrastructure complexity that does not provide meaningful engineering value.

---

# 3. Core Architectural Principle

The most important architectural rule is:

> AI recommends. Deterministic systems validate and execute.

The LLM is NOT the source of truth for:

- Payment state
- Recovery state
- Financial amounts
- Retry limits
- Authorization
- Stopping rules
- Database mutations
- Final execution

The LLM can:

- Analyze structured context
- Diagnose likely causes
- Select from predefined recovery strategies
- Provide structured reasoning/explanation
- Request predefined tools

The deterministic backend must:

- Validate the request
- Validate the AI output
- Enforce business rules
- Enforce state transitions
- Enforce retry limits
- Enforce stopping rules
- Execute the approved operation
- Persist the result
- Write the audit trail

---

# 4. Architecture Style

The initial system will use a:

> **Modular Monolith + Event-Driven Asynchronous Worker Architecture**

It is intentionally NOT a microservices architecture.

The system will consist of one primary backend application with clearly separated modules and one or more background worker processes.

Conceptually:

```text
                         ┌──────────────────────┐
                         │   External Systems   │
                         │                      │
                         │ Mock Gateway         │
                         │ Mock Merchant        │
                         └──────────┬───────────┘
                                    │
                              Webhooks / API
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                    FastAPI Application                         │
│                                                               │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │ API Layer   │──▶│ Recovery     │──▶│ AI Decision      │  │
│  │             │   │ Domain       │   │ Engine           │  │
│  └─────────────┘   └──────┬───────┘   └────────┬─────────┘  │
│                            │                     │            │
│                            ▼                     ▼            │
│                    ┌──────────────┐      ┌──────────────┐    │
│                    │ Policy /     │      │ AI Gateway   │    │
│                    │ Guardrails   │      │              │    │
│                    └──────┬───────┘      └──────────────┘    │
│                           │                                  │
│                           ▼                                  │
│                    ┌──────────────┐                          │
│                    │ Persistence  │                          │
│                    │ Layer        │                          │
│                    └──────┬───────┘                          │
└───────────────────────────┼───────────────────────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ PostgreSQL   │
                    └──────────────┘

                            ▲
                            │
                    ┌───────┴────────┐
                    │ Background     │
                    │ Worker         │
                    │                │
                    │ Scheduled Jobs │
                    │ Recovery Jobs  │
                    └────────────────┘
````

---

# 5. Technology Stack

## 5.1 Backend

### Python

Python will be the primary backend language.

Reason:

* Existing project familiarity
* Fast development
* Strong AI ecosystem
* Excellent API ecosystem
* Strong async support
* Strong testing ecosystem

The objective is to spend engineering time learning backend architecture rather than learning a new language during the initial build.

---

## 5.2 API Framework

### FastAPI

FastAPI will be used for:

* REST APIs
* Webhook endpoints
* Request validation
* Response serialization
* Dependency injection
* API documentation
* Async request handling

FastAPI is the primary application entry point.

---

## 5.3 Database

### PostgreSQL

PostgreSQL is the primary system of record.

PostgreSQL will store:

* Customers
* Subscriptions
* Payments
* Recovery cases
* Recovery attempts
* Recovery decisions
* Scheduled jobs
* Audit events
* Idempotency records
* Recovery metrics or metric source data

Financial and workflow state requires relational integrity.

MongoDB should NOT be introduced simply because the project contains AI-generated JSON.

---

## 5.4 ORM / Database Access

### SQLAlchemy 2.x

SQLAlchemy will be used for:

* Database models
* Queries
* Transactions
* Relationships
* Connection management

The implementation should prefer explicit SQLAlchemy patterns over hiding important transactional behavior behind excessive abstractions.

---

## 5.5 Database Migrations

### Alembic

Alembic will manage schema migrations.

Database schema changes must be represented as migrations rather than manually modifying production-like databases.

---

## 5.6 Validation / Schemas

### Pydantic

Pydantic will define:

* API request schemas
* API response schemas
* Domain command schemas
* AI structured output schemas
* Tool argument schemas
* Configuration schemas

The same validation philosophy should apply to both external API data and LLM-generated data.

---

## 5.7 AI Model

The AI layer should initially use a Gemini model through Google's supported Python SDK.

The exact model should be configurable through environment variables.

The application must NOT hard-code a specific model throughout the business logic.

Example:

```text
AI_MODEL=...
```

The application should interact with the model through an internal AI gateway abstraction.

---

## 5.8 AI Integration

The AI layer will use:

* Structured outputs
* Function/tool calling
* Explicit tool schemas
* Deterministic validation
* Bounded tool access

The application should avoid depending on unconstrained natural-language responses.

---

## 5.9 Background Processing

### Initial approach: PostgreSQL-backed durable job queue

The initial implementation will use PostgreSQL as the durable source of scheduled recovery jobs.

A worker process will poll for executable jobs using safe row-locking patterns.

Conceptually:

```text
PostgreSQL
    │
    │ SELECT pending jobs
    │ FOR UPDATE SKIP LOCKED
    ▼
Worker
    │
    ▼
Execute Recovery Action
```

This avoids introducing Kafka or another distributed messaging system before it is actually required.

The worker must support:

* Job claiming
* Retry attempts
* Job status
* Scheduled execution
* Failure handling
* Lease/timeout recovery
* Idempotent execution

---

## 5.10 Optional Infrastructure

Redis is NOT required for the initial MVP.

Redis may be introduced later for:

* Distributed rate limiting
* Caching
* Short-lived coordination
* High-throughput queues

It must not be introduced merely because "production systems use Redis."

---

## 5.11 Containerization

### Docker

Docker will be used for local infrastructure and reproducible development.

Initial services:

```text
backend
worker
postgres
```

The exact Docker Compose configuration should keep local development simple.

---

# 6. High-Level System Architecture

The complete architecture is:

```text
                         ┌──────────────────────┐
                         │  Simulated Merchant  │
                         │  / Payment Gateway   │
                         └──────────┬───────────┘
                                    │
                             Payment Event
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    FastAPI API       │
                         │                      │
                         │ Authentication       │
                         │ Validation           │
                         │ Idempotency          │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Recovery Domain      │
                         │                      │
                         │ Case Creation        │
                         │ State Machine        │
                         │ Context Assembly     │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Root Cause / Policy  │
                         │ Layer                │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ AI Decision Engine   │
                         │                      │
                         │ Structured Output    │
                         │ Tool Calling         │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Deterministic        │
                         │ Policy Validator     │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Recovery Command     │
                         │ / Job Creation       │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ PostgreSQL           │
                         │ Durable Job Store    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Background Worker    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Recovery Action      │
                         │ Executor             │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Mock Payment Gateway │
                         └──────────┬───────────┘
                                    │
                              Result / Event
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ State + Audit        │
                         │ Update               │
                         └──────────────────────┘
```

---

# 7. Application Module Boundaries

The backend should be organized around domain responsibilities rather than technology layers alone.

Recommended structure:

```text
app/
├── api/
│   ├── routes/
│   ├── dependencies/
│   └── schemas/
│
├── domain/
│   ├── recovery/
│   ├── payments/
│   ├── customers/
│   ├── subscriptions/
│   └── policies/
│
├── ai/
│   ├── gateway/
│   ├── decision/
│   ├── prompts/
│   ├── tools/
│   └── schemas/
│
├── workers/
│   ├── scheduler/
│   ├── executor/
│   └── jobs/
│
├── persistence/
│   ├── models/
│   ├── repositories/
│   └── transactions/
│
├── integrations/
│   └── payment_gateway/
│
├── audit/
│
├── observability/
│
└── config/
```

The exact folder structure may evolve, but the responsibilities must remain separated.

---

# 8. Core Domain Entities

The primary entities are:

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

---

# 9. Data Model

## 9.1 customers

Represents a merchant's customer.

Suggested fields:

```text
customers
-----------------------------
id                  UUID PK
external_id         VARCHAR UNIQUE
email               VARCHAR
name                VARCHAR
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

The model should contain only information necessary for the recovery workflow.

Note: The domain layer MUST explicitly validate that monetary values are positive and use supported currencies BEFORE beginning any recovery processing.

---

# 10. subscriptions

Represents a customer's subscription.

```text
subscriptions
-----------------------------
id                  UUID PK
customer_id         UUID FK
external_id         VARCHAR UNIQUE
status              ENUM
amount              NUMERIC
currency            VARCHAR
billing_interval    VARCHAR
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

Possible statuses:

```text
ACTIVE
PAST_DUE
CANCELLED
RECOVERED
```

The exact status model may evolve.

---

# 11. payments

Represents an individual payment attempt.

```text
payments
-----------------------------
id                  UUID PK
external_id         VARCHAR UNIQUE
customer_id         UUID FK
subscription_id     UUID FK NULL
amount              NUMERIC
currency            VARCHAR
status              ENUM
failure_code        VARCHAR NULL
failure_message     VARCHAR NULL
attempt_count       INTEGER
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

Possible statuses:

```text
PENDING
SUCCEEDED
FAILED
RECOVERY_PENDING
RECOVERED
ABANDONED
```

Payment status must never be changed arbitrarily.

---

# 12. recovery_cases

Represents the revenue-recovery process for a revenue-at-risk event.

```text
recovery_cases
-----------------------------
id                  UUID PK
payment_id          UUID FK
customer_id         UUID FK
amount_at_risk      NUMERIC
currency            VARCHAR
status              ENUM
failure_reason      VARCHAR
attempt_count       INTEGER
max_attempts        INTEGER
started_at          TIMESTAMP
last_action_at      TIMESTAMP NULL
completed_at        TIMESTAMP NULL
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

Possible statuses:

```text
OPEN
DECISION_PENDING
ACTION_SCHEDULED
ACTION_EXECUTING
RECOVERED
ESCALATED
STOPPED
```

---

# 13. recovery_attempts

Represents each concrete recovery attempt.

```text
recovery_attempts
-----------------------------
id                  UUID PK
recovery_case_id    UUID FK
attempt_number      INTEGER
action_type         VARCHAR
status              ENUM
scheduled_for       TIMESTAMP NULL
started_at          TIMESTAMP NULL
completed_at        TIMESTAMP NULL
failure_reason      VARCHAR NULL
result_code         VARCHAR NULL
created_at          TIMESTAMP
```

Possible statuses:

```text
SCHEDULED
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

A unique constraint should prevent duplicate attempt numbers for the same recovery case.

---

# 14. recovery_decisions

Represents the AI/policy decision associated with a recovery attempt.

```text
recovery_decisions
-----------------------------
id                  UUID PK
recovery_case_id    UUID FK
attempt_id          UUID FK NULL
decision_source     VARCHAR
action_type         VARCHAR
parameters_json     JSONB
reason              TEXT
policy_result       VARCHAR
model_name          VARCHAR NULL
prompt_version      VARCHAR NULL
created_at          TIMESTAMP
```

`decision_source` may contain:

```text
AI
RULE
FALLBACK
```

This allows the system to distinguish AI decisions from deterministic fallbacks.

---

# 15. recovery_jobs

Represents durable asynchronous work.

```text
recovery_jobs
-----------------------------
id                  UUID PK
recovery_case_id    UUID FK
attempt_id          UUID FK NULL
job_type            VARCHAR
status              ENUM
scheduled_for       TIMESTAMP
available_at        TIMESTAMP
attempt_count       INTEGER
max_attempts        INTEGER
locked_at           TIMESTAMP NULL
locked_by           VARCHAR NULL
last_error          TEXT NULL
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

Possible statuses:

```text
PENDING
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

The worker must safely claim jobs.

---

# 16. idempotency_records

Stores processed idempotency keys/events.

```text
idempotency_records
-----------------------------
id                  UUID PK
idempotency_key     VARCHAR UNIQUE
request_hash        VARCHAR
response_status     INTEGER
response_body       JSONB
created_at          TIMESTAMP
expires_at          TIMESTAMP NULL
```

This prevents duplicate processing of webhook or API events. The idempotency_key MUST have a UNIQUE constraint in the database. Handlers must rely on catching IntegrityError (or equivalent unique violation) to safely reject concurrent identical requests rather than relying on application-level read-then-write checks.

---

# 17. audit_events

Represents the append-only audit trail.

```text
audit_events
-----------------------------
id                  UUID PK
entity_type         VARCHAR
entity_id           UUID
event_type          VARCHAR
actor_type          VARCHAR
actor_id            VARCHAR NULL
payload             JSONB
correlation_id      VARCHAR
created_at          TIMESTAMP
```

Possible actor types:

```text
SYSTEM
AI
WORKER
MERCHANT
MOCK_GATEWAY
```

Audit records should be append-only from the application perspective.

Existing audit events must never be silently overwritten.

---

# 18. Money Representation

Monetary values must NOT be represented using floating-point numbers.

Use:

```text
NUMERIC
```

in PostgreSQL and an appropriate decimal representation in Python.

For example:

```text
2500.00
```

rather than:

```text
2500.0 float
```

Currency must always be stored explicitly.

Never perform financial calculations using binary floating-point arithmetic.

---

# 19. State Machine

The recovery workflow is a state machine.

Initial state:

```text
PAYMENT_FAILED
```

Then:

```text
PAYMENT_FAILED
      │
      ▼
RECOVERY_PENDING
      │
      ▼
DECISION_PENDING
      │
      ▼
ACTION_SCHEDULED
      │
      ▼
ACTION_EXECUTING
      │
      ├───────────────┐
      │               │
      ▼               ▼
   RECOVERED        FAILED
                      │
                      ▼
                DECISION_PENDING
                      │
               ┌──────┴──────┐
               ▼             ▼
            RETRY         STOPPED
```

Alternative terminal state:

```text
ESCALATED
```

---

# 20. State Transition Rules

State transitions must be explicit.

Example:

```text
RECOVERY_PENDING
        ↓
DECISION_PENDING
```

is valid.

But:

```text
RECOVERED
        ↓
ACTION_EXECUTING
```

is invalid.

The state machine should expose explicit transition operations rather than allowing arbitrary updates such as:

```python
payment.status = "RECOVERED"
```

throughout the codebase.

Domain logic should control state transitions.

---

# 21. AI Architecture

The AI system is a bounded decision component.

```text
Recovery Case
     │
     ▼
Context Builder
     │
     ▼
Structured Context
     │
     ▼
AI Decision Engine
     │
     ├── Structured Output
     │
     └── Tool Call
     │
     ▼
AI Decision Validator
     │
     ├── Valid
     │
     └── Invalid
     │
     ▼
Policy Engine
     │
     ▼
Recovery Command
```

---

# 22. AI Context

The LLM should receive a structured context object rather than raw database access.

Example:

```json
{
  "payment": {
    "amount": 2500,
    "currency": "INR",
    "failure_code": "INSUFFICIENT_FUNDS",
    "attempt_count": 1
  },
  "customer": {
    "tenure_days": 730,
    "successful_payments": 22,
    "failed_payments": 2
  },
  "recovery": {
    "previous_actions": [],
    "max_attempts": 3
  }
}
```

The AI must not query PostgreSQL directly.

The application constructs the context.

---

# 23. AI Decision Schema

The AI should produce a structured decision.

Example:

```json
{
  "action": "SCHEDULE_RETRY",
  "delay_hours": 48,
  "communication_channel": null,
  "reason": "The payment failure appears potentially temporary and no previous recovery action has been attempted."
}
```

The schema must reject:

* Unknown actions
* Invalid parameter types
* Negative delays
* Unsupported communication channels
* Parameters outside allowed ranges
* Missing required fields

---

# 24. AI Tool Boundary

The AI may be provided with a small number of explicit tools.

Example:

```text
schedule_retry
send_communication
escalate_case
stop_recovery
```

The LLM does NOT receive:

```text
execute_sql
update_payment
modify_database
charge_customer
```

The AI cannot directly mutate financial state.

---

# 25. Tool Execution

Tool calling follows:

```text
LLM
 │
 ▼
Tool Request
 │
 ▼
Schema Validation
 │
 ▼
Policy Validation
 │
 ▼
State Validation
 │
 ▼
Execution
 │
 ▼
Database Transaction
 │
 ▼
Audit Event
```

Every tool invocation must pass deterministic validation.

---

# 26. AI Failure Handling

AI calls can fail.

Examples:

* Timeout
* Rate limit
* Invalid structured output
* Provider unavailable
* Malformed tool call
* Model unavailable

The recovery system must not fail permanently because the AI is unavailable.

A deterministic fallback policy should exist.

Example:

```text
AI unavailable
     ↓
Deterministic Recovery Policy
     ↓
Safe action / escalation / stop
```

The fallback must be bounded.

---

# 27. AI Prompt Versioning

AI decisions should record:

```text
model_name
prompt_version
decision_schema_version
```

This allows future comparison of:

* Model behavior
* Prompt changes
* Decision outcomes

Prompts should not be scattered throughout business logic.

---

# 28. Recovery Policy Engine

The Policy Engine is deterministic.

It validates:

```text
Allowed action
Maximum retries
Maximum delay
Recovery window
Customer contact limits
State transition
Action eligibility
```

Example:

```text
AI:
SCHEDULE_RETRY
delay_hours = 720

Policy:
Maximum delay = 168 hours

Result:
REJECT
```

The AI does not get to override policy.

---

# 29. Idempotency Architecture

Idempotency must exist at multiple levels.

## Event Level

Prevent duplicate webhook processing.

```text
event_id
```

must be unique.

---

## Action Level

Prevent the same recovery action from being executed twice.

A worker retry must not create a second payment attempt if the first execution already succeeded.

---

## API Level

Endpoints that create financial/recovery operations should support idempotency keys where appropriate.

---

# 30. Database Transactions

Critical operations must use database transactions.

For example:

```text
BEGIN TRANSACTION

Update recovery state
Create recovery attempt
Create recovery job
Create audit event

COMMIT
```

Either all related records are committed or none are.

---

# 31. Worker Architecture

Workers execute durable recovery jobs.

Worker lifecycle:

```text
Poll
  ↓
Claim Job
  ↓
Verify Job Still Valid
  ↓
Verify Recovery Case State
  ↓
Re-validate State and Policy
  ?
Execute Action
  ↓
Record Outcome
  ↓
Update State
  ↓
Write Audit Event
```

---

# 32. Safe Job Claiming

Workers must avoid two workers executing the same job concurrently.

The database should be used to atomically claim jobs.

Conceptually:

```sql
SELECT *
FROM recovery_jobs
WHERE status = 'PENDING'
  AND available_at <= NOW()
ORDER BY available_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

The exact query may differ during implementation.

The important invariant is:

> At most one active worker should own a recovery job at a time.

---

# 33. Worker Crash Recovery

Workers can crash.

A job stuck in:

```text
RUNNING
```

must eventually become eligible for recovery.

Use a lease mechanism:

```text
locked_at
locked_by
```

If a worker has held a job longer than the configured lease duration, another worker may reclaim it subject to idempotency checks.

---

# 34. Retry Strategy

Retries should be bounded.

Example:

```text
Attempt 1
   ↓
5 min
   ↓
Attempt 2
   ↓
30 min
   ↓
Attempt 3
   ↓
STOP
```

The exact schedule is policy-driven.

The AI may recommend timing within allowed limits, but cannot exceed deterministic limits.

---

# 35. External Gateway Architecture

The mock payment gateway must be accessed through an interface.

Example:

```python
class PaymentGateway:
    async def retry_payment(...):
        ...
```

The domain should not directly depend on the mock implementation.

Architecture:

```text
Recovery Domain
      │
      ▼
PaymentGateway Interface
      │
      ▼
MockPaymentGateway
```

This allows a future real provider adapter without rewriting the recovery domain.

---

# 36. Mock Gateway Behavior

The mock gateway should simulate realistic external-system behavior.

Possible results:

```text
SUCCESS
INSUFFICIENT_FUNDS
TEMPORARY_FAILURE
CARD_EXPIRED
NETWORK_ERROR
DECLINED
TIMEOUT
```

The gateway should intentionally be capable of failing.

A system that only handles successful external calls does not demonstrate reliable backend engineering.

---

# 37. Webhook Architecture

The simulated gateway may send webhook events.

Example:

```text
Mock Gateway
     │
     │ POST /webhooks/payment
     ▼
FastAPI
     │
     ├── Validate
     ├── Idempotency
     ├── Persist Event
     └── Trigger Domain Processing
```

Webhook processing must be idempotent.

The webhook endpoint should acknowledge quickly after durable persistence rather than performing an entire recovery workflow synchronously.

---

# 38. Correlation IDs

Every major workflow should have a correlation ID.

Example:

```text
correlation_id = rec_01H...
```

The same identifier should appear in:

* API logs
* Recovery case
* AI decision
* Worker logs
* Audit events
* Gateway interactions

This allows an entire recovery lifecycle to be traced.

---

# 39. Observability

The system should expose:

### Structured Logs

Important fields:

```text
timestamp
level
service
event
correlation_id
recovery_case_id
payment_id
attempt_id
```

---

### Metrics

At minimum:

```text
revenue_at_risk
revenue_recovered
recovery_rate
recovery_attempts
recovery_success_rate
average_recovery_time
ai_decision_count
ai_failure_count
worker_job_failures
```

---

# 40. Security Architecture

The system must follow least privilege.

### API

Validate incoming requests.

### Database

The application should use a dedicated database user rather than PostgreSQL superuser access.

### AI

The model receives only the minimum context required.

### Tools

The model can access only explicitly exposed tools.

### Secrets

API keys and credentials must be stored in environment variables or a secret-management system.

Never commit:

```text
API keys
Passwords
Database credentials
Tokens
```

to source control.

---

# 41. Data Access Rules

The architecture follows:

```text
API
 ↓
Domain
 ↓
Repository / Persistence
 ↓
Database
```

The AI layer must never bypass the domain layer to directly mutate persistence.

Similarly:

```text
AI → PostgreSQL
```

is prohibited.

Instead:

```text
AI
 ↓
Structured Decision
 ↓
Policy
 ↓
Domain Command
 ↓
Persistence
```

---

# 42. Consistency Boundaries

The following operations should be treated as atomic where appropriate:

### Recovery Decision + Job Creation

If a decision results in a scheduled action:

```text
Decision persisted
+
Recovery attempt persisted
+
Job persisted
+
Audit event persisted
```

should be committed together.

---

### Recovery Result + State Transition

When an action succeeds:

```text
Gateway result
+
Payment state
+
Recovery state
+
Attempt result
+
Audit event
```

should be persisted consistently.

---

# 43. Failure Scenarios the Architecture Must Handle

The system must explicitly consider:

### Duplicate webhook

```text
Webhook A
Webhook A
```

Result:

```text
One logical event
```

---

### Worker crash

```text
Worker claims job
      ↓
Worker crashes
```

Result:

```text
Job eventually becomes reclaimable
```

---

### Gateway timeout

```text
Worker → Gateway
          ↓
       timeout
```

The system must not blindly assume failure and retry without considering whether the external operation may have succeeded.

---

### AI unavailable

```text
AI unavailable
      ↓
Fallback policy
```

---

### AI produces invalid action

```text
Invalid AI decision
      ↓
Reject
      ↓
Fallback / escalation
```

---

### Duplicate action

A retry of a worker job must not produce duplicate payment execution.

---

# 44. Scalability Strategy

The initial system is intentionally a modular monolith.

If traffic grows:

```text
                    Load Balancer
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
          API 1        API 2       API 3
             │           │           │
             └───────────┼───────────┘
                         │
                    PostgreSQL
                         │
                  ┌──────┴──────┐
                  ▼             ▼
               Worker 1      Worker 2
```

The worker layer can scale independently.

---

# 45. Future Event-Driven Architecture

If the system eventually needs much higher throughput, a dedicated message broker can be introduced.

Potential future architecture:

```text
API
 ↓
PostgreSQL
 ↓
Outbox
 ↓
Message Broker
 ↓
Workers
```

Potential technologies:

```text
Kafka
RabbitMQ
Cloud Pub/Sub
AWS SQS
```

These are future scalability options.

They are NOT required for the MVP.

---

# 46. Transactional Outbox — Future Evolution

If external event publishing becomes necessary, use a transactional outbox pattern.

Conceptually:

```text
BEGIN
   Update Database
   Insert Outbox Event
COMMIT

Outbox Worker
      ↓
Message Broker
```

This prevents the classic failure:

```text
Database committed
      ↓
Application crashes
      ↓
Event never published
```

The outbox pattern should only be introduced when the architecture actually requires an external event broker.

---

# 47. Caching Strategy

PostgreSQL is the source of truth.

Caching must never become the source of financial truth.

If caching is introduced later:

```text
PostgreSQL
    ↑
Source of Truth

Redis
    ↑
Performance Optimization
```

Financial state must always be validated against authoritative data when necessary.

---

# 48. API Architecture

Initial API categories:

## Revenue / Payment Simulation

```text
POST /payments
POST /payments/{id}/fail
POST /payments/{id}/simulate-success
```

---

## Webhooks

```text
POST /webhooks/payment
```

---

## Recovery

```text
GET  /recovery/cases
GET  /recovery/cases/{id}
POST /recovery/cases/{id}/retry
POST /recovery/cases/{id}/stop
```

Manual endpoints must still respect the same domain policies as automated actions.

---

## Metrics

```text
GET /metrics/recovery
GET /metrics/recovery/batch
```

The exact API surface may evolve.

---

# 49. API Versioning

Public-facing APIs should be versioned when appropriate.

Example:

```text
/api/v1/...
```

Internal functions do not require HTTP versioning.

---

# 50. Configuration

Configuration must be environment-driven.

Examples:

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

Business limits should be configurable but must have safe defaults.

---

# 51. Testing Architecture

Testing should occur at multiple levels.

## Unit Tests

Test:

* State transitions
* Policy validation
* Retry calculations
* AI output validation
* Domain logic

---

## Integration Tests

Test:

* PostgreSQL transactions
* API + database
* Idempotency
* Worker + database
* Mock gateway integration

---

## End-to-End Tests

Test the complete workflow:

```text
Payment Failure
      ↓
Recovery
      ↓
AI Decision
      ↓
Policy
      ↓
Job
      ↓
Worker
      ↓
Gateway
      ↓
Recovery
```

---

# 52. AI Evaluation

AI functionality must be tested separately from backend correctness.

The evaluation system should eventually contain representative scenarios such as:

```text
Insufficient funds
Temporary network error
Expired card
Repeated failure
High-value customer
Maximum retries reached
```

The system should measure:

* Valid action rate
* Invalid action rate
* Policy rejection rate
* Recovery success by action
* Fallback frequency

The LLM should not be evaluated only on whether its natural-language reasoning sounds good.

The important question is:

> Did the AI select an appropriate bounded action that resulted in successful recovery?

---

# 53. AI Determinism and Reproducibility

AI decisions are inherently probabilistic.

For important experiments, record:

```text
model
model version if available
prompt version
decision schema version
input context
structured output
policy validation result
execution result
```

This allows decisions to be analyzed after the fact.

---

# 54. Dependency Rules

Dependencies must be justified by a concrete requirement.

Do NOT introduce:

```text
Kafka
Kubernetes
Redis
Celery
LangGraph
Vector databases
Microservices
```

simply because they are popular technologies.

Introduce a technology only when:

1. It solves a real architectural problem.
2. The problem cannot reasonably be solved with the current stack.
3. The learning value justifies the added complexity.
4. The technology can be properly understood and maintained.

---

# 55. Deliberate Technology Choices

The initial stack is intentionally:

```text
Language       Python
API            FastAPI
Database       PostgreSQL
ORM            SQLAlchemy 2.x
Migrations     Alembic
Validation     Pydantic
AI             Gemini via Google SDK
Worker         Python worker + PostgreSQL-backed jobs
Containers     Docker
Testing        Pytest
```

This stack should be considered the default unless a documented architectural reason exists to change it.

---

# 56. Why Not Spring Boot Initially?

Spring Boot is an excellent production backend technology.

However, it is not the initial technology for this project because the goal is to learn:

* Backend architecture
* Reliability
* State machines
* Database transactions
* Async processing
* AI integration

rather than spending the initial implementation learning framework-specific boilerplate.

The backend principles learned here should later transfer to Spring Boot.

---

# 57. Why Not Microservices?

The initial system is a solo project.

Microservices would introduce:

* Network boundaries
* Service discovery
* Deployment complexity
* Distributed tracing
* Inter-service failure modes
* More infrastructure

without providing enough additional learning value at MVP scale.

The code should instead use strong module boundaries inside a modular monolith.

---

# 58. Architecture Decision Records

Significant architectural changes should be documented.

Example:

```text
ADR-001: Use PostgreSQL as system of record
ADR-002: Use modular monolith
ADR-003: Use database-backed job queue
ADR-004: Use AI tool calling with deterministic validation
```

Each ADR should contain:

```text
Context
Decision
Alternatives
Reasoning
Consequences
```

---

# 59. Architectural Invariants

The following invariants must NEVER be casually violated:

### Invariant 1

AI cannot directly mutate financial state.

### Invariant 2

Every recovery action must be bounded.

### Invariant 3

Duplicate events must not cause duplicate financial operations.

### Invariant 4

Money must not be represented using floating-point arithmetic.

### Invariant 5

Invalid state transitions must be rejected.

### Invariant 6

Recovery decisions and critical state changes must be auditable.

### Invariant 7

PostgreSQL is the source of truth for financial/recovery state.

### Invariant 8

External gateway failures must not corrupt internal state.

### Invariant 9

AI failure must not make the entire recovery system unusable.

### Invariant 10

Workers must be safe to restart.

---

# 60. Complete Request Lifecycle

A representative failed-payment lifecycle is:

```text
1. Mock Gateway detects payment failure

2. Gateway sends webhook

3. FastAPI receives webhook

4. Request is validated

5. Idempotency is checked

6. Payment/recovery case is persisted

7. State transitions to RECOVERY_PENDING

8. Recovery context is constructed

9. Root cause is determined

10. AI Decision Engine receives structured context

11. AI returns structured decision/tool call

12. AI decision is schema validated

13. Policy Engine validates the decision

14. State transition is validated

15. Recovery action is persisted

16. Recovery job is created

17. Worker claims the job

18. Worker verifies the job is still executable

19. Worker executes the recovery action

20. Mock Gateway returns an outcome

21. Payment/recovery state is updated transactionally

22. Recovery attempt is recorded

23. Audit event is appended

24. Metrics are updated/derived

25. Case becomes:

    RECOVERED
    OR
    DECISION_PENDING
    OR
    ESCALATED
    OR
    STOPPED
```

---

# 61. Architecture Evolution Path

The system should evolve incrementally.

## Stage 1 — Correct Modular Monolith

```text
FastAPI
+
PostgreSQL
+
Worker
+
Mock Gateway
+
AI
```

---

## Stage 2 — Stronger Observability

Add:

```text
Structured logging
Metrics
Tracing
```

---

## Stage 3 — Higher Throughput

Potentially add:

```text
Redis
Message Broker
Multiple Workers
```

---

## Stage 4 — Event-Driven Architecture

Potentially introduce:

```text
Transactional Outbox
Message Broker
Independent Consumers
```

---

## Stage 5 — Service Extraction

Only if justified:

```text
Recovery Service
AI Decision Service
Notification Service
Payment Adapter Service
```

Microservices are an optimization for scale and organizational boundaries, not the starting point.

---

# 62. Architecture Quality Standard

An implementation is not considered architecturally complete merely because:

```text
API works
+
Database works
+
LLM responds
```

It must also demonstrate:

```text
Correct state transitions
+
Idempotency
+
Transactional integrity
+
Bounded recovery
+
Safe asynchronous execution
+
AI guardrails
+
Failure handling
+
Auditability
+
Observability
```

The architecture should optimize for **correctness under failure**, not merely the happy path.

---

# 63. Final Architecture Statement

The Intelligent Revenue Recovery Engine is a:

> **Python/FastAPI modular monolith backed by PostgreSQL, with durable asynchronous recovery workers and a bounded AI decision layer using structured outputs and tool calling.**

The system uses:

```text
PostgreSQL
    ↓
Source of Truth

FastAPI
    ↓
API / Event Boundary

Domain Layer
    ↓
Business Rules / State Machine

AI Decision Engine
    ↓
Probabilistic Intelligence

Policy Engine
    ↓
Deterministic Safety

Worker
    ↓
Asynchronous Execution

Mock Gateway
    ↓
External-System Simulation

Audit + Metrics
    ↓
Accountability
```

The defining technical principle remains:

> **Probabilistic AI operates inside deterministic financial infrastructure.**

The architecture should remain simple enough to understand completely, but deep enough to demonstrate real backend engineering principles.

````




