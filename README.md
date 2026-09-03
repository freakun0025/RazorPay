# RazorPay Recovery Engine

A highly resilient, AI-assisted recovery engine for handling failed payments, integrated with OpenRouter and Nemotron for intelligent recovery decisions.

## Architecture

This project implements a robust Phase 1-7 architecture:
- **Phase 1-3**: Distributed worker queues, terminal payment dominance, strict database locking (\SKIP LOCKED\), idempotency, and network failure semantics.
- **Phase 4**: AI Boundary using OpenRouter (Nemotron model). Provides advisory actions (CHARGE, ABORT, DELAY) using strict JSON structures and contextual bounding.
- **Phase 5**: Administrative Mutations with strict \X-Admin-API-Key\ authorization for stopping and forcing retries on recovery cases.
- **Phase 6**: Observability & Auditing. Correlation ID propagation (\X-Correlation-ID\) across HTTP and asynchronous worker boundaries. Nested secret scrubbing.
- **Phase 7**: Analytics & Measurement. \/admin/analytics/recovery\ read-only endpoint with database-native aggregations and strict currency isolation.

## Installation

\\ash
# Clone the repository
git clone <repository_url>
cd RazorPay
\
## Configuration

Required environment variables (do NOT use defaults in production):
- \DATABASE_URL\: PostgreSQL connection string.
- \ADMIN_API_KEY\: Strictly required. Missing or empty values will safely block the application from booting.
- \AI_PROVIDER\: \openrouter- \AI_BASE_URL\: \https://openrouter.ai/api/v1- \AI_MODEL\: vidia/nemotron-3.5-lightning:free- \AI_API_KEY\: Your OpenRouter API key.

To set up locally:
\\ash
cp .env.example .env
# Edit .env with your actual credentials
\
## Starting PostgreSQL & Migrations

The database is managed via \docker-compose\.

\\ash
# Start PostgreSQL
docker-compose up -d postgres

# Run Alembic migrations to upgrade the schema to head
docker-compose run --rm backend alembic upgrade head
\
## Running the Application & Workers

\\ash
# Start the FastAPI web server (port 8000)
docker-compose up backend

# Start the background asynchronous workers
docker-compose up worker
\
## Running Tests

To run the complete 71-test regression suite:
\\ash
docker-compose --env-file .env.example run --rm backend pytest tests/ -v
\
## Endpoints

### Operational
- \GET /health\ - System health check.
- \GET /ready\ - Database readiness check.

### Webhooks
- \POST /webhooks/payment\ - Handles \payment.failed\ and \payment.succeeded\ events with strict idempotency.

### Administrative (Requires \X-Admin-API-Key\ header)
- \GET /admin/cases/{case_id}\ - Retrieve a recovery case.
- \POST /admin/cases/{case_id}/stop\ - Halt a recovery case.
- \POST /admin/cases/{case_id}/retry\ - Force retry a recovery case.
- \GET /admin/analytics/recovery\ - Aggregated, currency-isolated analytics.

## Security Assumptions
- Webhook signature verification is documented as deferred for the MVP and must be implemented prior to exposing the webhook endpoint publicly.
- \ADMIN_API_KEY\ must be securely generated and injected via runtime environment secrets.
- \AI_API_KEY\ must be securely injected via runtime environment secrets. No real keys are stored in the repository.
