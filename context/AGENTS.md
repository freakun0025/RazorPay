# AGENTS.md — Coding Agent Operating Contract

## 1. Purpose

This repository is a learning-first implementation of an **Intelligent Revenue Recovery Engine** for the Razorpay AI Revenue Recovery track.

The primary goal is not to maximize hackathon selection probability. The goal is to build a project that demonstrates and teaches:

- production-grade backend engineering
- financial-system correctness
- asynchronous workflows
- state machines
- database transactions and concurrency
- idempotency and failure recovery
- modern AI integration
- safe agent/tool workflows
- observability and auditability
- engineering judgment and trade-off analysis

The code should therefore be understandable enough for the owner to explain deeply in interviews.



---

## 2. Source-of-Truth Hierarchy

Before making implementation decisions, read the relevant project documents.

Priority:

1. `PRD.md` — product requirements and scope
2. `architecture-essentials.md` — critical architectural invariants and decisions
3. `architecture.md` — complete technical architecture
4. `AGENTS.md` — coding/agent operating rules
5. ADRs — decisions that intentionally modify or extend the architecture

If two documents conflict:

- do NOT silently choose one
- identify the conflict
- explain the consequence
- propose the smallest safe resolution
- ask for confirmation when the decision is material

Never let a coding task silently redefine the product or architecture.

---

## 3. Core Engineering Principle

> **Probabilistic AI operates inside deterministic financial infrastructure.**

The fundamental boundary is:

```text
AI recommends
      ↓
Schema validation
      ↓
Deterministic policy validation
      ↓
Domain state validation
      ↓
Authorized execution
      ↓
Transactional persistence
      ↓
Audit
```

The AI must never become the source of truth for:

- payment state
- recovery state
- money
- retry limits
- authorization
- stopping rules
- database mutations
- final financial execution

AI may analyze context and select bounded actions. Deterministic code decides whether those actions are legal and executes them.

---

## 4. Before Coding

For any non-trivial task:

1. Read the relevant requirements.
2. Identify the affected domain/module.
3. Inspect existing code before proposing new abstractions.
4. Identify invariants that must remain true.
5. State the implementation plan briefly.
6. Prefer the smallest implementation that satisfies the requirement.
7. Only then modify code.

Do not create speculative infrastructure.

Do not introduce a dependency merely because it is popular.

---

## 5. Architecture Defaults

The default architecture is:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic
- Gemini through an internal AI gateway
- PostgreSQL-backed durable jobs
- Python background worker
- Docker
- Pytest

The initial system is a **modular monolith**, not microservices.

Do not introduce Kafka, Redis, Celery, Kubernetes, LangGraph, vector databases, microservices, or similar infrastructure unless there is a concrete requirement that justifies it and the learning value outweighs the added complexity.

If proposing such a change, explain:

- problem being solved
- why the current architecture cannot solve it adequately
- alternatives considered
- operational cost
- learning value
- what complexity it introduces

---

## 6. Financial Correctness Is Non-Negotiable

Never use binary floating-point arithmetic for money.

Use:

- PostgreSQL `NUMERIC`
- Python `Decimal`
- explicit currency

Never silently round financial values.

Never invent financial state.

Never mark a payment as recovered merely because an internal function completed. The authoritative external operation must produce a valid result.

---

## 7. State Machines Must Be Explicit

Payment and recovery states are domain concepts, not arbitrary database strings.

Never scatter statements like:

```python
payment.status = "RECOVERED"
```

through unrelated code.

State transitions must go through explicit domain logic that validates:

- current state
- requested transition
- business conditions
- terminal states

Invalid transitions must fail loudly.

Tests must cover valid and invalid transitions.

---

## 8. Idempotency Is Mandatory

Assume every external event and worker operation can happen more than once.

The system must safely handle:

- duplicate webhooks
- duplicate API requests
- worker retries
- worker crashes
- network timeouts
- ambiguous external outcomes

A retry must never blindly create a second financial operation.

When implementing an operation that crosses a process or external-system boundary, explicitly answer:

> "What happens if this operation executes twice?"

If the answer is unclear, the implementation is not complete.

---

## 9. Transactions and Consistency

Critical state changes must be transactional where required.

For example:

```text
state transition
+ recovery attempt
+ job creation
+ audit event
```

should not leave the system in a half-committed state.

Do not hide transaction boundaries behind abstractions that make them impossible to reason about.

Prefer explicit transaction handling around financial/workflow invariants.

---

## 10. Worker Safety

Workers must be safe to restart and safe to run concurrently.

A worker must:

1. claim a job safely
2. verify the job is still executable
3. verify the recovery case state
4. execute through an appropriate domain/integration boundary
5. persist the result transactionally
6. write an audit event

Use database locking/claiming patterns appropriate to PostgreSQL, including `FOR UPDATE SKIP LOCKED` where applicable.

Long-running jobs need a recoverable lease/ownership strategy.

Never assume a worker will finish after claiming a job.

---

## 11. AI Engineering Rules

AI calls must use:

- structured outputs
- explicit schemas
- bounded actions
- explicit tool definitions
- deterministic validation
- fallback behavior

The AI receives an application-built context object.

The AI must not receive unrestricted database access.

The AI must never receive tools equivalent to:

```text
execute_sql
update_database
modify_payment
charge_customer
```

Prefer bounded commands such as:

```text
schedule_retry
send_communication
escalate_case
stop_recovery
```

Every AI decision must be validated before execution.

Record enough metadata to evaluate AI behavior later:

- model
- prompt version
- decision schema version
- structured output
- policy result
- execution result

If the AI is unavailable, the backend must remain safe and usable through deterministic fallback behavior.

---

## 12. Prompts Are Code

Prompts must not be scattered through business logic.

Store prompts in a dedicated AI/prompt area.

Version important prompts.

If a prompt change can alter financial/recovery behavior:

- record the change
- update the prompt version
- run the relevant AI evaluation tests
- document the expected behavioral difference

Do not optimize prompts solely for eloquent reasoning. Optimize for valid, bounded, useful decisions.

---

## 13. External Integrations

The recovery domain must depend on interfaces/ports rather than concrete mock implementations.

For example:

```text
Recovery Domain
      ↓
PaymentGateway interface
      ↓
MockPaymentGateway
```

The mock gateway should intentionally simulate failures such as:

- success
- insufficient funds
- temporary failure
- expired card
- decline
- timeout
- network error

A reliable system must be designed around failure, not only success.

---

## 14. Webhooks

Webhook handlers should:

1. validate the request
2. establish idempotency
3. persist durable information
4. trigger/queue appropriate domain work
5. acknowledge quickly

Do not put a long-running recovery workflow directly inside the webhook request.

Assume webhook delivery can be duplicated, delayed, reordered, or retried.

---

## 15. Auditability

Financial/recovery actions must be explainable after the fact.

Important decisions and mutations should have an audit trail containing enough information to answer:

- what happened?
- when?
- to what entity?
- why?
- who/what initiated it?
- what decision was made?
- what policy result occurred?
- what was the external outcome?

Audit events are append-only from the application perspective.

Do not silently overwrite historical audit information.

---

## 16. Observability

Use structured logs with useful correlation identifiers.

Important identifiers include:

- correlation ID
- recovery case ID
- payment ID
- attempt ID
- job ID

At minimum, the system should eventually expose metrics around:

- revenue at risk
- revenue recovered
- recovery rate
- recovery attempts
- recovery success rate
- recovery time
- AI decisions
- AI failures
- worker failures

Do not add an observability platform merely for appearance. Start with useful structured logs and metrics.

---

## 17. Testing Requirements

Do not consider a feature complete merely because the happy path works.

### Unit tests

Cover:

- state transitions
- policy validation
- retry calculations
- AI schema validation
- domain rules

### Integration tests

Cover:

- PostgreSQL transactions
- idempotency
- API/database interaction
- worker/database interaction
- gateway behavior

### End-to-end tests

At least one test should exercise the important lifecycle:

```text
payment failure
→ recovery case
→ AI/rule decision
→ policy validation
→ job
→ worker
→ gateway
→ state update
→ audit
```

Whenever a bug is found, first ask whether a regression test should be added.

---

## 18. Hard-Question Review

After every substantial implementation, the agent must challenge its own work.

Answer these questions:

### What do you think will break?

Identify likely failure points, especially around:

- concurrency
- retries
- duplicate events
- external timeouts
- partial database failure
- AI failure
- invalid AI output
- stale jobs
- state transitions

### What edge cases are we missing?

Consider:

- duplicate webhooks
- out-of-order events
- repeated failures
- maximum retries
- terminal states
- zero/negative/huge amounts
- unsupported currencies
- expired recovery windows
- worker crashes
- gateway timeout after an ambiguous charge
- duplicate tool calls
- AI hallucinated parameters
- AI provider outage

### What is over-engineered?

Identify:

- abstractions with no current use
- infrastructure added for hypothetical scale
- unnecessary dependencies
- premature microservices
- unnecessary caching
- excessive generic frameworks
- code that makes the system harder to understand

### What is under-engineered?

Identify:

- missing transaction boundaries
- weak idempotency
- unsafe retries
- missing state validation
- missing audit events
- unbounded AI actions
- missing failure handling

### What would an experienced backend engineer challenge?

The answer should focus on correctness and trade-offs, not style preferences.

---

## 19. Implementation Quality Gate

Before declaring a task complete, verify:

- [ ] Requirements satisfied
- [ ] Existing architecture respected
- [ ] No unnecessary dependency introduced
- [ ] Financial values use safe representations
- [ ] State transitions are explicit
- [ ] Idempotency considered
- [ ] Transaction boundaries considered
- [ ] Failure paths considered
- [ ] AI output validated where applicable
- [ ] External calls have safe retry/timeout behavior
- [ ] Auditability preserved
- [ ] Tests added/updated
- [ ] Existing tests still pass
- [ ] Logs/errors are useful
- [ ] Hard-question review completed
- [ ] Documentation updated if behavior/architecture changed

Do not claim a feature is complete if a known correctness issue remains.

---

## 20. Validation Loop

The coding agent should work in a loop:

```text
Understand
   ↓
Plan
   ↓
Implement
   ↓
Run tests / static checks
   ↓
Inspect failures
   ↓
Fix
   ↓
Hard-question review
   ↓
Re-test
   ↓
Summarize
```

If validation fails, do not merely suppress the failure.

Find the root cause and correct it.

If the failure reveals an architectural problem, stop and explain it rather than accumulating patches.

---

## 21. Do Not Silently Change Scope

Do not add:

- dashboards
- authentication systems
- multi-tenancy
- complex notification providers
- production cloud infrastructure
- advanced ML pipelines
- distributed tracing platforms
- message brokers

unless the requirement or an explicitly approved architectural decision calls for them.

The project is intentionally deep in backend correctness rather than broad in features.

---

## 22. Learning-First Development

When there are multiple valid implementations, prefer the one that:

1. teaches a durable engineering concept
2. remains production-reasonable
3. is explainable in an interview
4. avoids unnecessary abstraction

The agent should not hide important backend behavior behind generated boilerplate.

When implementing a non-obvious mechanism, briefly explain:

- what problem it solves
- why this implementation was chosen
- what trade-off it creates

---

## 23. Changes to Architecture Documents

If implementation reveals that an architectural decision is wrong:

Do not silently rewrite the architecture.

Instead:

1. identify the issue
2. explain why the current decision fails
3. propose alternatives
4. recommend one
5. update the relevant ADR/architecture document only after the decision is intentional

`architecture-essentials.md` should remain short and focused on invariants and critical decisions.

`architecture.md` can contain deeper implementation detail.

---

## 24. Git Discipline

Keep changes reviewable.

Prefer small, coherent commits.

Do not mix unrelated refactors with feature work.

Do not rewrite working code merely to make it stylistically different.

Never commit secrets, API keys, credentials, local databases, or generated sensitive data.

---

## 25. Agent Behavior

The coding agent is an implementation partner, not the project owner.

It should:

- question unclear requirements
- challenge unsafe designs
- identify edge cases
- point out over-engineering
- explain important trade-offs
- verify its work
- preserve project invariants

It should NOT:

- blindly obey an unsafe implementation request
- invent requirements
- silently change architecture
- add technologies for prestige
- treat an LLM response as authoritative
- declare success without validation

When uncertain, surface the uncertainty.

When a decision is consequential, ask before making it.

---

## 26. Definition of Done

A change is done when:

> **The required behavior works, failure modes have been considered, invariants remain intact, tests validate the important paths, and the implementation is understandable enough to defend in an engineering interview.**
