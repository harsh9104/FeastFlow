# FeastFlow

A festival food-ordering platform with **Premium priority**, built to run on AWS Auto Scaling and to show how the system behaves on a normal day versus a festival day.

- **Customers** browse the menu, place orders and follow their status. **Premium** customers' orders are prepared first.
- **Admins** work a live priority queue, run load tests, watch a monitoring dashboard, and generate cost and comparison reports.
- **One container** serves the React app and the FastAPI API. It runs locally with Docker Compose and on AWS behind an ALB with an Auto Scaling group.

Priority is plain application logic: each order snapshots the customer's tier, and the queue is ordered by `priority DESC, created_at ASC`. Claims use `FOR UPDATE SKIP LOCKED`, so several admins on several instances never take the same order. IAM is not involved.

## Quick start (local)

Needs Docker with Compose. Nothing else.

```bash
cp .env.example .env        # defaults work as they are
docker compose up -d --build
```

Open **<http://localhost:8000>**. The first start runs the database migrations, seeds the menu, 100 load-test customers and the admin account.

| What | Where |
|---|---|
| App (UI and API) | <http://localhost:8000> |
| API docs | <http://localhost:8000/api/docs> |
| Locust UI (load generator) | <http://localhost:8089> |
| Admin login | `admin@feastflow.app` / `ChangeMe123!` (from `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env`) |
| Customers | Register at `/register` and pick Free or Premium |

Stop with `docker compose down` (add `-v` to wipe the database and reports).

### Try the Premium priority (AC-01)

1. Register a **Free** customer and a **Premium** customer in two browsers.
2. Place a Free order first, then a Premium order.
3. Sign in as admin and open **Queue**: the Premium order is on top even though it is newer.
4. Click **Claim next order**, then **Mark completed**. The customers' *My Orders* pages update on their own.

### Try the load test and the reports

1. Admin → **Load Tests** → start *Normal day* (leave *Quick run* ticked for a 60-second demo).
2. Watch live users, requests per second, failures and latency. Open **Dashboard** for CPU, traffic and response-time charts.
3. When it finishes, run *Festival day*, then go to **Costs** → *Normal vs Festival comparison* and download the report.

> Load-test customers place real orders, so they appear in the queue. `docker compose down -v` gives you a clean slate.

## Features by area

| Area | What you get |
|---|---|
| Accounts | Register and sign in with JWT, customer and admin roles, simulated Free/Premium switch |
| Ordering | Menu, cart, server-side pricing, atomic orders, idempotency key, status timeline |
| Admin queue | Premium-first queue, concurrency-safe claiming, status transitions with optimistic locking, wait-time stats |
| Load testing | Locust scenarios (Normal 25 users, Festival 250 users), live stats, run history, one run at a time |
| Monitoring | CPU, memory, traffic, latency, 5xx, fleet size, alarms, instances (local collector or CloudWatch) |
| Costs and reports | Rate table × measured usage, per-run cost, JSON/CSV/Markdown reports, Normal vs Festival comparison |
| SLA | 99.5 % availability target, calculated from the app: `GET /api/v1/admin/sla/availability` |

## Repository layout

```
backend/     FastAPI app (api -> services -> models), Alembic migrations, tests
frontend/    React 18 + TypeScript + Vite
loadtest/    Locust file and image
infra/       AWS CLI scripts, user-data, CloudWatch agent config, policies
docs/        Design package, SLA (read docs/README.md first)
Dockerfile   Multi-stage: builds the SPA, then the Python runtime
docker-compose.yml   App + Postgres 16 + Locust for local use
.github/workflows/ci.yml   Lint, migrations, tests, frontend build, image smoke test
```

## Development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
docker compose up -d db                                # Postgres on localhost:5432
docker compose exec db psql -U feastflow -c "CREATE DATABASE feastflow_test"
ruff check . && ruff format --check .
pytest -q                                              # uses the feastflow_test database
uvicorn app.main:app --reload                          # http://localhost:8000
```

The tests build their schema from the models. CI also runs the real migrations up, down and up again, so keep migrations reversible.

### Frontend

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
npm run build      # type-check + production build
```

### Adding a migration

Create `backend/alembic/versions/NNNN_name.py` (the next number, `down_revision` = the previous one). The container applies migrations on start, guarded by a database advisory lock so several instances can boot together.

## Configuration

All settings are environment variables (see `backend/app/core/config.py`).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local Postgres | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `JWT_SECRET` | `change-me` | Signing key. **Change it outside local use.** |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | empty | Seeds the admin on first migration |
| `ENV` | `development` | `production` hides the API docs |
| `METRICS_PROVIDER` | `local` | `local` or `cloudwatch` |
| `LOCUST_URL` | `http://localhost:8089` | Where the app controls Locust |
| `S3_BUCKET` | empty | When set, menu images and reports use S3. Empty = local `reports/` folder. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `WEB_CONCURRENCY` | 5, 5, 2 | Connection pool and worker count |
| `ASG_NAME`, `ALB_DIMENSION`, `TG_DIMENSION`, `TG_ARN`, `DB_INSTANCE_ID` | – | Only for `METRICS_PROVIDER=cloudwatch` |

## Deploying to AWS

The AWS side is scripted for the AWS Academy Learner Lab (`us-east-1`): security groups, S3, ECR, RDS, launch template, ALB, Auto Scaling group (min 2 / max 4, CPU target 50 %), CloudWatch alarms and a Locust instance. See **[infra/README.md](infra/README.md)** for prerequisites and the run order.

Teardown: `CONFIRM=yes infra/scripts/99-teardown.sh`. Idle: set the ASG to 0, stop Locust and RDS.

## Project status

| Area | Status |
|---|---|
| Core app, priority queue, frontend | Done and tested locally |
| Load tests, dashboard, costs and reports, SLA calculation | Done and tested locally |
| CI (`ci.yml`) | Written, not yet run on GitHub |
| AWS scripts (`infra/`) | Written, **not yet run** against a real account |
| CD (`cd.yml`: ECR push, instance refresh, smoke test) | Not written (needs the AWS stack) |
| Evidence: scaling run, screenshots, pipeline proof, real costs | Pending the AWS deployment |

## Documentation

Design and requirements are in **[docs/](docs/README.md)**. The SLA is **[docs/14-sla.md](docs/14-sla.md)**. The source requirements are in `FeastFlow_SRS_FRS.pdf`.

## Known limitations

- The ALB listener is HTTP only (no domain or certificate in the lab).
- RDS is single-AZ, so the database is a single point of failure.
- Subscription changes are simulated (no payments).
- The Festival scenario uses a constant spawn rate, not the multi-stage ramp in the design.
- Latency percentiles shown on the local dashboard are request-weighted averages across workers, not exact.
