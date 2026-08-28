# Architecture Essentials — Intelligent Revenue Recovery Engine

> This is the compact architectural reference for the project.
> For complete technical details, consult `architecture.md`.
>
> This file is intentionally concise enough to be loaded frequently by the
> coding agent.
>
> **Do not blindly implement the architecture. Challenge it when appropriate.**
> If an implementation decision conflicts with these invariants, stop and
> explicitly identify the conflict before proceeding.

---

# 1. System Identity

The Intelligent Revenue Recovery Engine is a:

**Python + FastAPI modular monolith backed by PostgreSQL, with durable
PostgreSQL-backed workers and a bounded Gemini AI decision layer.**

The system detects revenue at risk, diagnoses the situation, chooses a
bounded recovery intervention, executes it asynchronously, and records the
complete outcome.

The project is intentionally designed to demonstrate:

* Production-grade backend engineering
* Reliability and failure handling
* Database and transaction design
* Asynchronous processing
* Modern AI integration
* AI safety and deterministic guardrails
* Observability and auditability

Primary architectural principle:

> **AI recommends. Deterministic systems validate and execute.**

---

# 2. Architecture Style

Use:

> **Modular Monolith + Asynchronous Worker Architecture**

Do NOT begin with microservices.

Conceptually:

```text
External / Simulated Systems
            │
            ▼
       FastAPI API
            │
            ▼
     Recovery Domain
      + State Machine
            │
      ┌─────┴─────┐
      ▼           ▼
   Policy       AI Engine
      │           │
      └─────┬─────┘
            ▼
    Deterministic Validation
            │
            ▼
      Recovery Command
            │
            ▼
       PostgreSQL
            │
            ▼
      Background Worker
            │
            ▼
      Mock Gateway
            │
            ▼
    State + Audit + Metrics
```

The architecture should remain simple enough for one engineer to understand
completely.

---

# 3. Technology Stack

| Concern    | Technology                        |
| ---------- | --------------------------------- |
| Language   | Python                            |
| API        | FastAPI                           |
| Database   | PostgreSQL                        |
| ORM        | SQLAlchemy 2.x                    |
| Migrations | Alembic                           |
| Validation | Pydantic                          |
| AI         | Gemini via Google's supported SDK |
| Worker     | Python worker                     |
| Job Store  | PostgreSQL                        |
| Containers | Docker / Docker Compose           |
| Testing    | Pytest                            |

The exact AI model must be configurable.

```text
AI_MODEL=...
```

Do not scatter model-specific configuration throughout business logic.

---

# 4. Source of Truth

**PostgreSQL is the authoritative source of truth.**

It owns:

* Payment state
* Subscription state
* Recovery state
* Recovery attempts
* Recovery decisions
* Durable jobs
* Idempotency records
* Audit events

Do not use:

* LLM output
* In-memory state
* Frontend state
* Redis/cache

as the authoritative source of financial state.

---

# 5. AI Boundary

The AI is a **bounded decision component**, not an autonomous financial
authority.

```text
Recovery Context
      │
      ▼
     AI
      │
      ▼
Structured Decision
      │
      ▼
Schema Validation
      │
      ▼
Deterministic Policy
      │
      ▼
Domain Command
      │
      ▼
Execution
```

The AI MAY:

* Diagnose likely failure causes
* Select predefined recovery strategies
* Recommend retry timing
* Recommend communication channels
* Produce structured reasoning
* Request predefined tools

The AI MUST NOT:

* Directly modify the database
* Directly modify payment state
* Execute arbitrary SQL
* Directly charge customers
* Override retry limits
* Override stopping rules
* Invent arbitrary recovery actions
* Decide financial truth

Critical rule:

> **The LLM never bypasses the domain or policy layer.**

---

# 6. AI Structured Output

AI responses must use structured schemas.

Example:

```json
{
  "action": "SCHEDULE_RETRY",
  "delay_hours": 48,
  "communication_channel": null,
  "reason": "Temporary failure appears recoverable."
}
```

Allowed actions should come from predefined schemas/enums.

Examples:

```text
SCHEDULE_RETRY
SEND_COMMUNICATION
ESCALATE
STOP
```

Exact actions may evolve.

Arbitrary AI-generated actions are prohibited.

Validate AI output using Pydantic before it reaches business logic.

---

# 7. Policy Layer

The policy engine is deterministic.

It validates:

* Action eligibility
* Maximum retry attempts
* Maximum recovery window
* Maximum retry delay
* Communication limits
* Current recovery state
* Required parameters
* Stopping conditions

Example:

```text
AI recommends:
delay_hours = 720

Policy:
MAX_RETRY_DELAY = 168

Result:
REJECT
→ deterministic fallback / escalation
```

> **AI recommendations are never policy authorization.**

---

# 8. Recovery State Machine

Recovery is explicitly modeled as a state machine.

Typical lifecycle:

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
  RECOVERED         FAILED        AMBIGUOUS
                      │
                      ▼
              DECISION_PENDING
                      │
                ┌─────┴─────┐
                ▼           ▼
              RETRY       STOPPED

Possible terminal state:
ESCALATED
```

State transitions must be explicit and validated.

Never allow arbitrary code to directly mutate important state:

```python
recovery_case.status = "RECOVERED"
```

Instead, state changes must go through domain-controlled transition logic.

Invalid transitions must be rejected.

---

# 9. Core Domain Model

Conceptual relationship:

```text
Customer
   │
   └── Subscription
          │
          └── Payment
                 │
                 └── Recovery Case
                        │
                        ├── Recovery Attempts
                        ├── Recovery Decisions
                        ├── Recovery Jobs
                        └── Audit Events
```

Primary entities:

```text
customers
subscriptions
payments
recovery_cases
recovery_attempts
recovery_decisions
recovery_jobs
idempotency_records
audit_events
```

Refer to `architecture.md` for complete schemas and fields.

---

# 10. Money

Financial values must NEVER use binary floating-point arithmetic.

Use:

```text
PostgreSQL NUMERIC
+
Python Decimal
```

Always store currency explicitly.

Example:

```text
2500.00 INR
```

not:

```text
2500.0 float
```

---

# 11. Idempotency

Idempotency is mandatory at critical boundaries.

### Event Level

Duplicate webhooks/events must result in one logical event.
Use database-enforced uniqueness (e.g., a UNIQUE constraint on idempotency_key) and handle IntegrityError to safely reject concurrent duplicate webhooks.

### Action Level

A worker retry must not execute the same financial operation twice.
Gateway mutations MUST require deterministic idempotency keys. Internal worker execution is at-least-once; external idempotency ensures exactly-once financial effects.

### Active Case Uniqueness
Prevent multiple simultaneously active recovery cases for the same payment using a database-level partial unique constraint.

### API Level

Financial/recovery mutation endpoints should support idempotency where
appropriate.

Core invariant:

> **Duplicate events or requests must never cause duplicate financial
> operations.**

---

# 12. Transactions

Critical multi-record operations must be transactional.

Example:

```text
BEGIN TRANSACTION

Update recovery state
Create recovery attempt
Create recovery job
Create audit event

COMMIT
```

Either the complete operation succeeds or the related state changes are
rolled back.

Recovery outcomes should similarly keep relevant:

```text
Gateway Result
+ Payment State
+ Recovery State
+ Attempt Result
+ Audit Event
```

consistent.

---

# 13. Background Worker

Recovery actions execute asynchronously.

Worker lifecycle:

```text
Poll
  ↓
Claim Job
  ↓
Verify Job
  ↓
Verify Recovery State
  ↓
Execute Action
  ↓
Record Outcome
  ↓
Update State
  ↓
Write Audit Event
```

Jobs are stored durably in PostgreSQL.

The initial system does NOT require:

```text
Kafka
RabbitMQ
Celery
Redis
Kubernetes
```

unless a concrete architectural requirement justifies them.

---

# 14. Safe Job Claiming

Multiple workers must not execute the same job concurrently.

Use PostgreSQL row-locking patterns such as:

```sql
SELECT ...
FROM recovery_jobs
WHERE status = 'PENDING'
  AND available_at <= NOW()
ORDER BY available_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Workers must support:

* Job claiming
* Retry attempts
* Scheduled execution
* Failure handling
* Lease/timeout recovery
* Idempotent execution

Worker crashes must not permanently lose work.

---

# 15. External Gateway Boundary

The recovery domain depends on an interface, not directly on the mock
gateway implementation.

```text
Recovery Domain
      │
      ▼
PaymentGateway Interface
      │
      ▼
MockPaymentGateway
```

The mock gateway should simulate realistic outcomes:

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

---

# 16. Webhook Processing

Webhook lifecycle:

```text
External Gateway
      │
      ▼
POST /webhooks/payment
      │
      ▼
Validate
      │
      ▼
Check Idempotency
      │
      ▼
Persist Event
      │
      ▼
Trigger Domain Processing
```

Webhook processing must be idempotent.

The endpoint should acknowledge after durable persistence rather than
performing the entire recovery workflow synchronously.

The system must explicitly handle out-of-order terminal webhooks (e.g., a SUCCESS webhook arriving while a recovery job is merely SCHEDULED) by safely short-circuiting pending workflows, rather than rejecting them as invalid state transitions.

---

# 17. AI Failure Handling

AI failure must never make the recovery system unusable.

Possible failures:

```text
Timeout
Rate Limit
Provider Failure
Invalid Structured Output
Malformed Tool Call
Model Unavailable
```

Expected behavior:

```text
AI Failure
    ↓
Deterministic Fallback Policy
    ↓
Safe Action / Escalation / Stop
```

Fallback behavior must itself be bounded and deterministic.

---

# 18. Tool Calling

If AI tool calling is used, tools must be narrowly scoped.

Examples:

```text
schedule_retry
send_communication
escalate_case
stop_recovery
```

The AI must NOT receive tools such as:

```text
execute_sql
update_database
modify_payment
charge_customer
```

Tool execution:

```text
AI Tool Request
      ↓
Schema Validation
      ↓
Policy Validation
      ↓
State Validation
      ↓
Domain Execution
      ↓
Database Transaction
      ↓
Audit Event
```

> **Tool calling is a request mechanism, not an authorization mechanism.**

---

# 19. Auditability

Every important decision and state-changing operation must be auditable.

Audit events are append-only.

Important audit information includes:

```text
entity
event_type
actor
correlation_id
payload
timestamp
```

AI decisions should record:

```text
model_name
prompt_version
decision_schema_version
structured_output
policy_result
```

The system should be able to answer:

> Why did this recovery action happen?

> What requested it?

> What policy allowed it?

> What happened during execution?

> How much revenue was recovered?

---

# 20. Observability

Use structured logging.

Important identifiers:

```text
correlation_id
recovery_case_id
payment_id
attempt_id
job_id
```

Core metrics:

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

The complete recovery lifecycle should be traceable through a correlation ID.

---

# 21. Security

Follow least privilege.

Never commit:

```text
API keys
Passwords
Database credentials
Tokens
```

Use environment variables or appropriate secret management.

The AI receives only the minimum structured context required.

Never provide unrestricted database access to the model.

---

# 22. Failure-First Design

Every important feature must consider failure modes.

At minimum:

### Duplicate Webhook

```text
Duplicate Event
      ↓
One Logical Event
```

### Worker Crash

```text
Worker Claims Job
      ↓
Worker Crashes
      ↓
Lease Expires
      ↓
Job Can Be Reclaimed
```

### Gateway Timeout

A timeout does NOT necessarily mean the external operation failed.

The system must account for ambiguous external outcomes before retrying
financial operations.

### AI Failure

```text
AI Failure
      ↓
Deterministic Fallback
```

### Invalid AI Decision

```text
Invalid Decision
      ↓
Reject
      ↓
Fallback / Escalate
```

### Duplicate Action

A retry of a worker job must not duplicate financial operations.

---

# 23. Module Boundaries

Recommended structure:

```text
app/
├── api/
├── domain/
│   ├── recovery/
│   ├── payments/
│   ├── customers/
│   ├── subscriptions/
│   └── policies/
├── ai/
│   ├── gateway/
│   ├── decision/
│   ├── prompts/
│   ├── tools/
│   └── schemas/
├── workers/
├── persistence/
├── integrations/
├── audit/
├── observability/
└── config/
```

Exact folders may evolve.

Responsibilities must remain separated.

---

# 24. Data Access Direction

Dependency direction:

```text
API
 ↓
Domain
 ↓
Persistence
 ↓
PostgreSQL
```

AI must not bypass the domain.

Correct:

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

Forbidden:

```text
AI → PostgreSQL
AI → SQL
AI → Direct Financial Mutation
```

---

# 25. API Boundary

Initial API categories:

```text
Payment / Simulation
POST /payments
POST /payments/{id}/fail
POST /payments/{id}/simulate-success

Webhooks
POST /webhooks/payment

Recovery
GET  /recovery/cases
GET  /recovery/cases/{id}
POST /recovery/cases/{id}/retry
POST /recovery/cases/{id}/stop

Metrics
GET /metrics/recovery
GET /metrics/recovery/batch
```

Exact endpoints may evolve.

Manual recovery operations must use the same domain policies as automated
recovery.

---

# 26. Configuration

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

Configuration should be environment-driven and have safe defaults.

---

# 27. Testing Priorities

Testing must prioritize correctness under failure.

### Unit Tests

* State transitions
* Policy rules
* Retry calculations
* AI output validation
* Domain logic

### Integration Tests

* PostgreSQL transactions
* API + database
* Idempotency
* Worker + database
* Mock gateway

### End-to-End

```text
Payment Failure
      ↓
Recovery Case
      ↓
AI Decision
      ↓
Policy Validation
      ↓
Job
      ↓
Worker
      ↓
Gateway
      ↓
Recovery Outcome
      ↓
Audit
```

AI evaluation should measure:

* Valid decision rate
* Policy rejection rate
* Fallback frequency
* Recovery success by action
* Failure behavior

Not merely whether the AI produces convincing explanations.

---

# 28. Dependency Discipline

Do NOT introduce technology simply because it is popular.

Potentially unnecessary for the initial system:

```text
Kafka
Kubernetes
Redis
Celery
LangGraph
Vector Databases
Microservices
```

Before introducing a new technology, answer:

1. What concrete problem does it solve?
2. Why can't the current architecture solve it?
3. What learning value does it provide?
4. What complexity does it introduce?
5. Can I explain and maintain the technology myself?
6. Is it solving a real current problem or a hypothetical future problem?

> **Prefer boring infrastructure when it teaches the underlying concept more
> clearly.**

---

# 29. Architecture Review Protocol

**This section is mandatory guidance for the coding agent.**

Before implementing a significant architectural change, feature, dependency,
or abstraction, challenge the design.

Do not assume that an existing design is automatically correct simply because
it appears in `architecture.md`.

Ask:

### What could break?

Identify:

* Failure modes
* Race conditions
* Data corruption scenarios
* Duplicate execution
* Partial transactions
* External-system ambiguity
* AI failures
* Worker crashes
* Invalid state transitions
* Security issues
* Observability gaps

### What edge cases are missing?

Consider:

* Duplicate events
* Retries
* Timeouts
* Concurrent workers
* Replayed webhooks
* Stale jobs
* Maximum retry limits
* Boundary timestamps
* Zero/negative/very large amounts
* Currency mismatches
* Missing customer data
* Previously recovered payments
* Already-cancelled subscriptions
* AI returning malformed or contradictory output
* External gateway succeeding after a timeout

Do not assume the happy path is sufficient.

### What is over-engineered?

Explicitly question:

* New infrastructure
* New abstractions
* New services
* New databases
* New queues
* Excessive design patterns
* Premature scalability
* AI frameworks that do not solve a concrete problem
* Abstractions that exist only to make the architecture look impressive

Ask:

> Can this be implemented correctly with the existing stack?

If yes, prefer the simpler implementation unless the additional complexity
has clear learning value.

### What is under-engineered?

Also ask:

* Are transactions missing?
* Is idempotency missing?
* Is state being mutated directly?
* Is error handling superficial?
* Is the worker unsafe?
* Can an external timeout cause duplicate payment execution?
* Can AI bypass policy?
* Is the audit trail incomplete?
* Are important failures invisible?

Do not simplify away correctness.

### What assumptions are we making?

Identify assumptions about:

* Payment gateway behavior
* Webhook delivery
* AI reliability
* Database behavior
* Worker execution
* Timing
* Customer behavior
* Retry semantics

If an assumption is important, make it explicit.

---

# 30. Hard Questions the Agent Should Ask Itself

Before declaring an implementation complete, the agent should challenge it with
questions such as:

```text
What do you think will break first?

What happens if this request arrives twice?

What happens if two workers process this simultaneously?

What happens if the worker crashes at this exact point?

What happens if the gateway times out after actually charging the customer?

What happens if the AI is unavailable?

What happens if the AI returns a syntactically valid but unsafe decision?

What happens if the AI recommends something outside policy?

What happens if the database transaction partially fails?

What happens if a webhook is delayed or replayed?

What happens if the recovery case has already reached a terminal state?

What prevents duplicate financial execution?

What prevents an invalid state transition?

What prevents an AI decision from bypassing business rules?

What data is authoritative?

What information is being persisted unnecessarily?

What is the simplest implementation that preserves correctness?

What have we over-engineered?

What have we under-engineered?

Which component would become the bottleneck first?

Which failure would be hardest to detect?

Which assumption would be most dangerous if it were wrong?

What would I change if this handled 100x more traffic?

Do we actually need that change today?
```

The purpose is not to make every implementation maximally complex.

The purpose is to make the implementation **deliberate**.

---

# 31. Learning-First Principle

This is a solo learning project.

The goal is not:

> Build the largest possible architecture.

The goal is:

> **Understand why each architectural decision exists and be able to defend it
> in an interview.**

Prefer technologies and patterns that expose fundamental engineering concepts:

```text
Transactions
Concurrency
Idempotency
State Machines
Async Processing
Failure Recovery
Database Integrity
API Design
AI Guardrails
Observability
Testing
```

Avoid technologies that hide these concepts behind unnecessary abstraction.

A simpler system that the developer understands deeply is better than a
complex system assembled from frameworks the developer cannot explain.

---

# 32. Interview-Quality Standard

A feature is not complete merely because:

```text
API works
+
Database works
+
LLM responds
```

The implementation should be able to explain:

```text
Why this architecture?

Why PostgreSQL?

Why a modular monolith?

Why a database-backed job queue?

Why not Kafka?

Why does AI not directly execute actions?

How is idempotency implemented?

How are concurrent workers handled?

What happens during a gateway timeout?

What happens when AI fails?

How are state transitions enforced?

How is money represented safely?

How is every recovery action audited?

How do you test failure scenarios?
```

The architecture should produce **understanding**, not just functionality.

---

# 33. Architectural Invariants

These rules are non-negotiable unless the architecture is explicitly revised
and documented.

### INVARIANT 1

**AI cannot directly mutate financial state.**

### INVARIANT 2

**Every recovery action must be bounded.**

### INVARIANT 3

**Duplicate events/actions cannot cause duplicate financial operations.**

### INVARIANT 4

**Money cannot use floating-point arithmetic.**

### INVARIANT 5

**Invalid state transitions must be rejected.**

### INVARIANT 6

**Important recovery decisions and state changes must be auditable.**

### INVARIANT 7

**PostgreSQL is the source of truth.**

### INVARIANT 8

**External failures cannot corrupt internal financial state.**

### INVARIANT 9

**AI failure cannot make the recovery system unusable.**

### INVARIANT 10

**Workers must be safe to restart and recover from crashes.**

### INVARIANT 11

**Business policy is deterministic and cannot be overridden by AI.**

### INVARIANT 12

**External integrations are accessed through interfaces/adapters.**

### INVARIANT 13

**Architectural complexity must be justified by a concrete problem or
meaningful learning value.**

### INVARIANT 14

**The agent must challenge questionable architecture instead of blindly
implementing it.**

---

# 34. Complete Mental Model

When implementing any feature, reason about the system in this order:

```text
EVENT
  ↓
API / WEBHOOK
  ↓
VALIDATION + IDEMPOTENCY
  ↓
DOMAIN STATE
  ↓
CONTEXT BUILDING
  ↓
AI DECISION
  ↓
STRUCTURED VALIDATION
  ↓
DETERMINISTIC POLICY
  ↓
DOMAIN COMMAND
  ↓
TRANSACTION
  ↓
DURABLE JOB
  ↓
WORKER
  ↓
EXTERNAL ACTION
  ↓
RESULT
  ↓
STATE TRANSITION
  ↓
AUDIT
  ↓
METRICS
```

For any new feature, ask:

1. What domain state does this affect?
2. What are the valid state transitions?
3. What happens if the request is duplicated?
4. What happens if the process crashes?
5. What happens if the external system times out?
6. What happens if the AI fails?
7. What deterministic policy prevents unsafe behavior?
8. What must be persisted transactionally?
9. How is the operation audited?
10. How will this be tested under failure?
11. Is this abstraction actually necessary?
12. What could break?
13. What edge cases are missing?
14. What is over-engineered?
15. What is under-engineered?

---

# 35. Architectural North Star

The system is built around one principle:

> **Probabilistic AI operates inside deterministic financial infrastructure.**

The AI provides intelligence.

The backend provides:

```text
Correctness
+
Reliability
+
Bounded Execution
+
State Management
+
Transactional Integrity
+
Idempotency
+
Auditability
+
Observability
```

The project should optimize for:

> **Correctness under failure, not merely a working happy path.**

And simultaneously:

> **The simplest architecture that provides the required correctness and
> meaningful engineering learning.**


For complete implementation details, schemas, API specifications, scalability
strategy, and architecture evolution, consult:

```text
architecture.md
```
