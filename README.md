# Intelligent Revenue Recovery Engine

> **AI-assisted, deterministic revenue recovery for failed payments.**

An event-driven backend that detects revenue at risk, diagnoses payment failures, recommends bounded recovery actions with AI, validates those recommendations deterministically, executes recovery work asynchronously, and measures the resulting recovery performance.

The core design principle is:

> **AI recommends. Deterministic systems validate and execute.**

---

## Why this project exists

Failed payments are not all the same.

A transient network failure may deserve another attempt. An insufficient-funds failure may be delayed. A stolen-card signal should not trigger another charge.

This engine turns that problem into a controlled workflow:

```text
Payment failure
      │
      ▼
Reliable webhook ingestion
      │
      ▼
Recovery case
      │
      ▼
AI recommendation
      │
      ▼
Deterministic validation
      │
      ▼
Durable recovery job
      │
      ▼
Worker execution
      │
      ▼
Payment gateway
      │
      ├───────────────┐
      ▼               ▼
  Recovered        Failed
                      │
                      ▼
                 Retry / Stop
                      │
                      ▼
             Audit + Observability
                      │
                      ▼
                 Analytics
```

This repository was built around the **AI Revenue Recovery** problem: recover measurable revenue while preserving financial safety, idempotency, concurrency correctness, auditability, and operational control.

---

## Key architectural invariant

The model is **not** the authority over financial state.

An AI response such as:

```json
{
  "action": "CHARGE",
  "reason": "The failure appears transient.",
  "confidence": 0.91
}
```

does not directly charge a customer.

Instead:

```text
AI recommendation
      ↓
Pydantic contract validation
      ↓
Current database state validation
      ↓
Recovery state-machine rules
      ↓
Attempt / retry limits
      ↓
Durable job
      ↓
Worker
      ↓
Gateway operation
```

The AI has no direct authority to:

- mutate payment state
- mutate recovery state
- execute gateway operations
- bypass idempotency
- bypass worker ownership
- bypass state-machine rules
- bypass transaction boundaries

---

# Features

- Reliable `payment.failed` / `payment.succeeded` webhook processing
- Event-level idempotency
- Immutable payment attribute protection
- Terminal payment dominance
- PostgreSQL-backed durable recovery jobs
- Safe concurrent job claiming with `FOR UPDATE SKIP LOCKED`
- Worker lease / stale-worker protection
- Explicit payment, recovery, attempt, and job state machines
- OpenRouter integration using NVIDIA Nemotron 3.5 Lightning
- OpenAI-compatible AI provider abstraction
- Strict Pydantic AI decision contract
- Defensive JSON extraction for non-strict model responses
- Deterministic operational/admin controls
- Transactionally coupled audit events
- Correlation IDs across HTTP and asynchronous worker boundaries
- Structured JSON logging
- Recursive secret scrubbing in observability payloads
- Health and database-readiness endpoints
- Currency-isolated recovery analytics
- SQL-side aggregation for analytics
- Database migrations with Alembic
- Docker Compose development environment
- Integration and unit test coverage for core invariants

---

# Architecture

## System overview

```text
                           ┌──────────────────────┐
                           │  Payment Provider    │
                           │  Webhook             │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │   FastAPI Webhook    │
                           │   /webhooks/payment  │
                           └──────────┬───────────┘
                                      │
                           validation + idempotency
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │    PostgreSQL        │
                           │                      │
                           │ Payment              │
                           │ RecoveryCase         │
                           │ RecoveryJob          │
                           │ IdempotencyRecord    │
                           └──────────┬───────────┘
                                      │
                              durable async work
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │       Worker         │
                           │   ExecutionService   │
                           └──────────┬───────────┘
                                      │
                         ┌────────────┴────────────┐
                         │                         │
                         ▼                         ▼
                 ┌───────────────┐       ┌────────────────┐
                 │ AI Decision   │       │ Payment        │
                 │ Provider      │       │ Gateway        │
                 │               │       │ Mock Client    │
                 │ OpenRouter →  │       └───────┬────────┘
                 │ Nemotron      │               │
                 └───────────────┘               │
                         │                       │
                         └───────────┬───────────┘
                                     ▼
                           ┌──────────────────────┐
                           │ Audit + Structured   │
                           │ Observability        │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │ Admin / Analytics    │
                           │ /admin/...           │
                           └──────────────────────┘
```

For the deeper architectural specification, see:

- [`context/Architecture.md`](context/Architecture.md)
- [`context/architecture-essentials.md`](context/architecture-essentials.md)
- [`context/PRD.md`](context/PRD.md)

---

# Architecture by phase

## Phase 1 — Foundation

Introduces:

- FastAPI application
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic
- Core database models
- Explicit state machines
- Relational constraints and indexes

Core entities:

```text
Customer
Subscription
Payment
RecoveryCase
RecoveryAttempt
RecoveryDecision
RecoveryJob
IdempotencyRecord
AuditEvent
```

---

## Phase 2 — Reliable Webhooks

Endpoint:

```http
POST /webhooks/payment
```

Supported events:

```text
payment.failed
payment.succeeded
```

The webhook layer protects the financial state through:

- idempotency
- immutable payment attributes
- financial validation
- terminal-state dominance
- transactional case creation
- safe handling of concurrent duplicate events

A duplicate webhook must not create duplicate financial state.

A late `payment.failed` event must not overwrite an already successful payment.

---

## Phase 3 — Durable Recovery Workers

Recovery work is represented as durable PostgreSQL jobs.

```text
RecoveryCase
     │
     ├── RecoveryAttempt
     │
     └── RecoveryJob
```

These are intentionally different concepts:

| Entity | Responsibility |
|---|---|
| `RecoveryCase` | Business recovery workflow |
| `RecoveryAttempt` | Actual financial recovery attempt |
| `RecoveryJob` | Asynchronous work item |

Jobs are claimed using PostgreSQL row locking:

```sql
FOR UPDATE SKIP LOCKED
```

This prevents two workers from claiming the same available job.

Worker leases and ownership checks also protect against stale/zombie workers.

---

## Phase 4 — AI Decision Engine

The AI layer uses:

```text
OpenRouter
    │
    ▼
NVIDIA Nemotron 3.5 Lightning
```

Configured through environment variables:

```text
AI_PROVIDER=openrouter
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=nvidia/nemotron-3.5-lightning:free
AI_API_KEY=<secret>
```

The provider is isolated behind an internal interface so business logic does not depend directly on HTTP or SDK details.

The model receives a deliberately small recovery context rather than an unrestricted database object.

Current decision contract:

```text
action:
  CHARGE | ABORT | DELAY

reason:
  string

confidence:
  0.0 - 1.0
```

The provider defensively handles model output that may contain markdown fences or surrounding text before applying Pydantic validation.

---

## Phase 5 — Administrative Operations

Admin endpoints provide controlled operational intervention.

Authentication:

```http
X-Admin-API-Key: <admin secret>
```

Operations include:

```text
GET  /admin/cases/{case_id}
POST /admin/cases/{case_id}/stop
POST /admin/cases/{case_id}/retry
```

Important safety properties:

- Admin mutations are transactionally controlled.
- Payment and recovery state are revalidated.
- A successful payment remains dominant.
- Admin retry does not directly call the gateway.
- Retry queues the normal recovery evaluation path.
- A running worker/job cannot be blindly duplicated.
- API responses use dedicated Pydantic DTOs rather than exposing ORM objects.

---

## Phase 6 — Observability and Auditability

Observability covers three different concerns:

```text
Logs
  → operational debugging

Audit events
  → durable business/security history

Health/readiness
  → infrastructure visibility
```

### Correlation IDs

Incoming requests can provide:

```http
X-Correlation-ID: <trace id>
```

Otherwise the application generates one.

Correlation IDs are:

- sanitized
- bounded
- safe for structured logging

When asynchronous work is created, the correlation ID is persisted in the recovery job payload so the worker can restore the trace later.

Conceptually:

```text
HTTP request
     │
     │ correlation_id = ABC
     ▼
RecoveryJob(payload={correlation_id: ABC})
     │
     ▼
Worker
     │
     │ restore ABC
     ▼
worker logs / audit events
```

### Audit transactions

Audit events are added to the same SQLAlchemy transaction as the business mutation.

The audit helper does not independently commit.

Therefore:

```text
business mutation + audit event
             │
             ▼
          COMMIT
```

or:

```text
business mutation + audit event
             │
             ▼
         ROLLBACK
```

This prevents an audit record from claiming that a mutation happened when the mutation itself was rolled back.

---

## Phase 7 — Recovery Analytics

Endpoint:

```http
GET /admin/analytics/recovery?start_at=<ISO8601>&end_at=<ISO8601>
```

Authentication:

```http
X-Admin-API-Key: <admin secret>
```

Analytics are aggregated by currency.

Example conceptual response:

```json
{
  "start_at": "2026-01-01T00:00:00",
  "end_at": "2026-02-01T00:00:00",
  "metrics_by_currency": {
    "USD": {
      "total_recovery_cases": 120,
      "successful_recovery_cases": 48,
      "failed_or_stopped_recovery_cases": 72,
      "total_recovery_attempts": 180,
      "successful_recovery_attempts": 48,
      "failed_recovery_attempts": 132,
      "amount_attempted": 15000.0,
      "amount_recovered": 6000.0,
      "amount_unrecovered": 9000.0,
      "recovery_rate": 0.4,
      "success_rate": 0.4
    }
  }
}
```

Currency isolation is intentional:

```text
USD 100 + USD 200 = USD 300

USD 100 + INR 200
```

must never be treated as one monetary total.

Analytics use database-side aggregation rather than loading every recovery case into Python.

Analytics access is itself audited with:

```text
ANALYTICS_ACCESSED
```

---

# State machines

The system uses explicit state transition maps instead of allowing arbitrary state changes.

## Recovery case

```text
OPEN
  │
  ▼
DECISION_PENDING
  │
  ├───────────────┐
  ▼               ▼
ACTION_SCHEDULED  ESCALATED
  │
  ▼
ACTION_EXECUTING
  │
  ├──► RECOVERED
  ├──► DECISION_PENDING
  ├──► ESCALATED
  └──► STOPPED
```

Terminal recovery states:

```text
RECOVERED
ESCALATED
STOPPED
```

## Payment

```text
PENDING
  ├──► SUCCEEDED
  └──► FAILED
           │
           ├──► RECOVERY_PENDING
           │        │
           │        ├──► RECOVERED
           │        └──► ABANDONED
           │
           └──► ABANDONED
```

`SUCCEEDED` is terminal and dominates later failure events.

## Recovery attempt

```text
SCHEDULED
    │
    ▼
 RUNNING
   ├──► SUCCEEDED
   ├──► FAILED
   └──► AMBIGUOUS
            │
            ├──► SUCCEEDED
            ├──► FAILED
            └──► RUNNING
```

## Recovery job

```text
PENDING
   │
   ▼
RUNNING
   ├──► SUCCEEDED
   ├──► FAILED
   └──► CANCELLED
```

---

# Database model

PostgreSQL is the system of record.

Core relationships:

```text
Customer
   │
   ├───────────────┐
   ▼               ▼
Payment        Subscription
   │
   ▼
RecoveryCase
   │
   ├───────────────┬───────────────┐
   ▼               ▼               ▼
RecoveryAttempt  RecoveryDecision  RecoveryJob
```

Additional infrastructure records:

```text
IdempotencyRecord
AuditEvent
```

Important database protections include:

- unique external payment identifiers
- unique idempotency keys
- unique recovery-attempt numbers per case
- active recovery-case uniqueness
- non-negative financial amount constraints
- indexes for recovery/job lookup and scaling
- relational foreign keys
- database-side aggregation for analytics

---

# API

## Operational

### `GET /health`

Liveness endpoint.

Response:

```json
{
  "status": "ok"
}
```

### `GET /ready`

Database readiness endpoint.

Successful response:

```json
{
  "status": "ready"
}
```

Database failure returns HTTP `503`.

---

## Webhooks

### `POST /webhooks/payment`

Processes:

```text
payment.failed
payment.succeeded
```

Unsupported event types are ignored.

The endpoint validates the event and delegates business behavior to the domain service.

> **Production note:** webhook signature verification is intentionally deferred for the MVP and must be implemented before exposing the endpoint to an untrusted public payment-provider network.

---

## Admin

All admin routes require:

```http
X-Admin-API-Key: <admin secret>
```

### `GET /admin/cases/{case_id}`

Returns operational recovery-case information using a dedicated response schema.

### `POST /admin/cases/{case_id}/stop`

Stops an eligible recovery case and cancels pending work where safe.

### `POST /admin/cases/{case_id}/retry`

Queues a fresh recovery evaluation through the normal asynchronous workflow.

### `GET /admin/analytics/recovery`

Returns recovery metrics grouped by currency for a requested time range.

---

# Project structure

```text
.
├── app/
│   ├── ai/
│   │   ├── contracts.py
│   │   ├── exceptions.py
│   │   └── gateway/
│   │       ├── client.py
│   │       └── provider.py
│   │
│   ├── api/
│   │   ├── dependencies/
│   │   │   └── auth.py
│   │   ├── middleware/
│   │   │   └── correlation.py
│   │   ├── routes/
│   │   │   ├── admin.py
│   │   │   ├── health.py
│   │   │   └── webhooks.py
│   │   └── schemas/
│   │       ├── admin.py
│   │       └── webhooks.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── domain/
│   │   ├── observability/
│   │   │   └── audit.py
│   │   ├── operations/
│   │   │   └── service.py
│   │   ├── payments/
│   │   │   └── service.py
│   │   ├── policies/
│   │   │   └── validator.py
│   │   └── recovery/
│   │       ├── states.py
│   │       └── state_machine.py
│   │
│   ├── integrations/
│   │   └── payment_gateway/
│   │       ├── interface.py
│   │       └── mock_client.py
│   │
│   ├── persistence/
│   │   ├── database.py
│   │   ├── models/
│   │   └── repositories/
│   │
│   ├── utils/
│   │   ├── context.py
│   │   └── logger.py
│   │
│   ├── workers/
│   │   └── executor/
│   │       ├── execution_service.py
│   │       └── main.py
│   │
│   └── main.py
│
├── migrations/
│   └── versions/
│
├── tests/
│   ├── integration/
│   │   ├── ai/
│   │   ├── api/
│   │   ├── persistence/
│   │   └── workers/
│   └── unit/
│       └── domain/
│
├── context/
│   ├── AGENTS.md
│   ├── Architecture.md
│   ├── architecture-essentials.md
│   ├── CLAUDE.md
│   ├── PRD.md
│   └── SCAFFOLD.md
│
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
└── README.md
```

---

# Technology stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI |
| Validation | Pydantic 2 |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2 |
| Migrations | Alembic |
| AI SDK | OpenAI-compatible Python SDK |
| AI Provider | OpenRouter |
| AI Model | NVIDIA Nemotron 3.5 Lightning |
| Background work | PostgreSQL-backed durable jobs |
| Containerization | Docker / Docker Compose |
| Testing | pytest / pytest-asyncio |

---

# Local setup

## Prerequisites

Install:

- Docker
- Docker Compose
- Git

For non-containerized development, use Python 3.11+.

---

## 1. Clone

```bash
git clone <repository-url>
cd intelligent-revenue-recovery-engine
```

---

## 2. Configure environment

```bash
cp .env.example .env
```

Set the required secrets in `.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/recovery_db

ADMIN_API_KEY=<strong-local-admin-secret>

AI_PROVIDER=openrouter
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=nvidia/nemotron-3.5-lightning:free
AI_API_KEY=<your-openrouter-api-key>
```

Optional operational configuration:

```env
AI_TIMEOUT=10.0
WORKER_LEASE_TIMEOUT=60
GATEWAY_HTTP_TIMEOUT=30
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Never commit real credentials.

---

# Start PostgreSQL

```bash
docker compose up -d postgres
```

Check that PostgreSQL is running:

```bash
docker compose ps
```

---

# Run migrations

```bash
docker compose run --rm backend alembic upgrade head
```

---

# Start the API

```bash
docker compose up backend
```

The API is available at:

```text
http://localhost:8000
```

FastAPI's interactive API documentation is available at:

```text
http://localhost:8000/docs
```

---

# Start the worker

```bash
docker compose up worker
```

The worker is responsible for processing durable recovery jobs.

---

# Running tests

The repository contains the full regression suite across:

- domain state transitions
- persistence constraints
- financial validation
- webhook idempotency
- concurrency
- worker behavior
- AI parsing/provider behavior
- admin authentication and mutations
- observability/remediation
- analytics

Run:

```bash
pytest tests/ -v
```

Or through Docker:

```bash
docker compose --env-file .env.example run --rm \
  -e PYTHONPATH=/app \
  backend \
  pytest tests/ -v
```

The final validated project state contains a **71-test regression suite**.

---

# Database access

The local PostgreSQL container exposes port `5432`.

Connect with:

```bash
psql postgresql://user:password@localhost:5432/recovery_db
```

Or enter the PostgreSQL container:

```bash
docker compose exec postgres psql \
  -U user \
  -d recovery_db
```

Useful inspection queries:

```sql
\dt
```

```sql
SELECT * FROM payments;
```

```sql
SELECT * FROM recovery_cases;
```

```sql
SELECT * FROM recovery_jobs;
```

```sql
SELECT * FROM recovery_attempts;
```

```sql
SELECT * FROM recovery_decisions;
```

```sql
SELECT * FROM audit_events;
```

```sql
SELECT * FROM idempotency_records;
```

---

# Example webhook

A failed payment can be simulated with:

```bash
curl -X POST http://localhost:8000/webhooks/payment \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-recovery-001" \
  -d '{
    "event_id": "evt_demo_001",
    "type": "payment.failed",
    "payment_id": "pay_demo_001",
    "customer_id": "00000000-0000-0000-0000-000000000001",
    "amount": 100.00,
    "currency": "USD",
    "failure_reason": "insufficient_funds"
  }'
```

A successful payment event can be simulated with the same payment identifier and:

```json
{
  "event_id": "evt_demo_002",
  "type": "payment.succeeded",
  "payment_id": "pay_demo_001",
  "customer_id": "00000000-0000-0000-0000-000000000001",
  "amount": 100.00,
  "currency": "USD"
}
```

The real integration should use the payment provider's verified webhook signature mechanism before public deployment.

---

# Example admin request

Set the local admin key:

```bash
export ADMIN_API_KEY="<your-local-admin-secret>"
```

Then:

```bash
curl http://localhost:8000/admin/cases/<case-id> \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

Stop a case:

```bash
curl -X POST http://localhost:8000/admin/cases/<case-id>/stop \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

Queue a retry:

```bash
curl -X POST http://localhost:8000/admin/cases/<case-id>/retry \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

Analytics:

```bash
curl "http://localhost:8000/admin/analytics/recovery?start_at=2026-01-01T00:00:00&end_at=2026-02-01T00:00:00" \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
```

---

# Security model

## Secrets

Secrets are supplied through environment variables.

Do not commit:

```text
AI_API_KEY
ADMIN_API_KEY
database passwords
gateway credentials
authorization headers
```

The repository's example environment should contain placeholders rather than real credentials.

---

## AI boundary

The AI provider receives only the recovery context needed for its decision.

The domain layer does not expose:

- database credentials
- provider secrets
- authorization headers
- arbitrary ORM objects
- unrestricted customer information

---

## Financial safety

Financial operations are protected by:

- idempotency
- immutable payment attributes
- terminal dominance
- explicit state transitions
- database constraints
- worker ownership
- bounded attempts
- just-in-time financial idempotency keys
- gateway/network calls outside database locks

---

## Admin safety

Admin endpoints:

- require an admin API key
- use dedicated response schemas
- revalidate state under database locking
- do not directly invoke the gateway
- preserve terminal payment dominance
- audit important administrative actions

---

## Observability safety

Logs and audit payloads are scrubbed for sensitive values.

Correlation IDs are sanitized and bounded to prevent log-injection and unbounded-payload problems.

Health/readiness failures do not expose database credentials or internal stack traces.

---

# Failure handling

The system is designed around explicit failure boundaries.

## Duplicate webhook

```text
duplicate event
     ↓
idempotency conflict
     ↓
financial mutation rejected
```

---

## Payment succeeds while recovery is running

```text
worker / admin operation
        ↓
re-lock payment
        ↓
Payment = SUCCEEDED
        ↓
do not retry / charge again
```

Terminal success dominates.

---

## Worker crashes

A job lease can expire.

A later worker can reclaim the eligible job while ownership checks prevent stale workers from committing state after losing their lease.

---

## Gateway timeout

A timeout can be ambiguous.

The system records an ambiguous attempt and uses reconciliation before blindly issuing another charge.

---

## AI failure

AI failures are handled separately from financial attempts.

An AI failure must not accidentally become a payment attempt.

The model can fail through:

- timeout
- provider error
- malformed response
- invalid structured output
- unexpected response shape

The deterministic application remains the authority.

---

# Testing philosophy

The test suite is intentionally hostile to race conditions and invalid state.

The project tests more than happy paths.

Examples include:

```text
duplicate webhooks
out-of-order events
immutable payment mutation
concurrent identical webhook requests
state-machine exhaustiveness
worker concurrency
admin vs worker races
admin vs succeeded-payment races
AI malformed JSON
AI structured-output validation
health/readiness failure
correlation propagation
nested secret scrubbing
analytics currency isolation
analytics zero-denominator behavior
analytics read-only behavior
```

The goal is to test **invariants**, not merely implementation details.

---

# Migrations

Alembic manages database evolution.

Run:

```bash
alembic upgrade head
```

Current migration history includes:

```text
a04bb93ae6eb  initial_schema
63505e2817ac  add_check_constraints
906b317e5e85  add_payload_to_recovery_jobs
f649369deabb  add_indexes_for_scaling
```

Do not modify production-like schemas manually; create an Alembic migration for schema changes.

---

# Design decisions

## Why PostgreSQL-backed jobs?

The MVP needs durable asynchronous work, but introducing Kafka or another distributed queue would add operational complexity without being necessary for the initial system.

PostgreSQL already provides:

- durability
- transactions
- row locking
- `SKIP LOCKED`
- recovery after process failure

A dedicated queue can be introduced later if throughput requirements justify it.

---

## Why AI instead of a completely deterministic rules engine?

The AI provides flexible diagnosis and recommendation from recovery context.

The deterministic layer remains responsible for:

- legal actions
- financial safety
- state transitions
- retries
- execution
- idempotency

This gives the system AI-assisted reasoning without making financial behavior probabilistic.

---

## Why not let the AI call the payment gateway?

Because that would combine:

```text
probabilistic reasoning
+
financial side effects
```

inside the same boundary.

Instead:

```text
AI
 ↓
recommendation

Backend
 ↓
validation

Worker
 ↓
financial operation
```

This keeps the dangerous side effect deterministic and auditable.

---

## Why use SQL aggregation for analytics?

The database is already the authoritative source of recovery state.

Aggregation belongs close to that data:

```text
PostgreSQL
  ↓
SUM / COUNT / GROUP BY
  ↓
small result
  ↓
API
```

rather than transferring every row into Python.

---

# Operational checklist

Before running the system in a real environment:

- [ ] Set a strong `ADMIN_API_KEY`
- [ ] Set a real `AI_API_KEY` through the runtime secret manager
- [ ] Verify `DATABASE_URL`
- [ ] Run `alembic upgrade head`
- [ ] Run the full test suite
- [ ] Verify `/health`
- [ ] Verify `/ready`
- [ ] Verify worker processing
- [ ] Verify webhook idempotency
- [ ] Verify payment terminal dominance
- [ ] Verify audit events
- [ ] Verify correlation IDs across worker boundaries
- [ ] Verify analytics aggregation
- [ ] Implement and verify production webhook signature validation
- [ ] Configure production logging/monitoring
- [ ] Review retention policies for audit/log data

---

# Documentation

Additional project documentation:

| Document | Purpose |
|---|---|
| `context/PRD.md` | Product requirements and scope |
| `context/Architecture.md` | Full system architecture |
| `context/architecture-essentials.md` | Condensed architecture reference |
| `context/AGENTS.md` | Engineering/agent instructions |
| `context/CLAUDE.md` | Compatibility/reference entry point |
| `context/SCAFFOLD.md` | Initial project scaffold |
| `docs/adr/README.md` | Architecture Decision Records |

---

# Project status

The implementation covers the complete Phase 1–7 design:

```text
Phase 1  Foundation
Phase 2  Reliable Webhooks
Phase 3  Durable Recovery Workers
Phase 4  AI Decision Engine
Phase 5  Administrative Operations
Phase 6  Observability & Auditability
Phase 7  Recovery Analytics
```

The final validation history includes the full regression suite and hostile audits focused on:

- financial correctness
- idempotency
- concurrency
- worker safety
- AI failure behavior
- admin race conditions
- secret leakage
- observability integrity
- analytics correctness
- database indexing/scaling

---

# License

Add the license appropriate for the intended submission or distribution before publishing this repository.
