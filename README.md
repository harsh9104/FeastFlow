# FeastFlow

Food ordering with Prime priority, auto-assigned delivery partners and a festival-day load scenario,
deployed on AWS Learner Lab (EC2 + ALB + ASG, RDS MySQL, SQS, SNS, S3, CloudWatch, Lambda + EventBridge).

The full project plan is in [docs/PLAN.md](docs/PLAN.md).

## Run without Docker (quick demo)
```bash
cd frontend && npm install && npm run build && cd ../backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # once
.venv/Scripts/python scripts/demo_no_docker.py    # http://127.0.0.1:8000
```
Real API, worker and UI; SQLite instead of MySQL and a local moto server on :4566 for
SQS/SNS/S3 (photos load, no emails). Fresh data on every start, timers shortened. If Locust
is installed in `loadtest/.venv`, it starts too, so the Festival page's load generator works.

## Run locally
```bash
docker compose up --build
curl http://localhost:8000/api/health        # liveness
curl http://localhost:8000/api/health/ready  # checks MySQL
```

## API so far
| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/register` | anyone |
| POST | `/api/auth/login` | anyone |
| GET | `/api/users/me` | logged in |
| POST | `/api/prime/subscribe` · `/api/prime/cancel` | customer (mock payment, 30 days) |
| GET | `/api/admin/users?prime_only=true` | admin |
| GET | `/api/restaurants` · `/api/restaurants/{id}/menu` | anyone (images are presigned S3 URLs) |
| POST | `/api/orders` (optional `Idempotency-Key` header) | customer → 202, sent to `orders-prime` or `orders-standard` |
| GET | `/api/orders` · `/api/orders/{id}` | owner (or admin) |
| PATCH | `/api/admin/menu-items/{id}` (price, availability) | admin |
| POST | `/api/admin/menu-items/{id}/image` (JPEG/PNG/WebP ≤ 2 MB → S3) | admin |
| GET | `/api/admin/orders?status=ACTIVE` (Prime first) · `ALL` · any single status | admin |
| GET · POST | `/api/admin/partners` | admin |
| PATCH | `/api/admin/partners/{id}` (`AVAILABLE` / `OFFLINE`, not mid-delivery) | admin |
| GET | `/api/admin/dispatch/stats` (queue depths, partners, Prime vs standard wait times) | admin |
| GET · POST | `/api/admin/festival/runs` · `POST …/{id}/cancel` | admin |
| GET | `/api/admin/loadtest` · `POST /api/admin/loadtest/start` (`normal`/`festival`) · `/stop` | admin |

## Order worker
`python -m worker.main` runs beside the API on every instance. It confirms orders from SQS
(`orders-prime` before `orders-standard`, with a 4:1 poll ratio so standard orders aren't starved),
then moves each order along simulated timers:

`PLACED → CONFIRMED → PREPARING → AWAITING_PARTNER → OUT_FOR_DELIVERY → DELIVERED`

A free delivery partner is auto-assigned when food is ready: Prime first, then the longest-waiting order;
standard orders waiting over `AGING_SECONDS` count as urgent. Rows are locked with
`FOR UPDATE SKIP LOCKED`, so several workers never take the same order or partner. SNS emails go out at
CONFIRMED, OUT_FOR_DELIVERY and DELIVERED. Timers: `CONFIRM_SECONDS`, `PREP_SECONDS`, `DELIVERY_SECONDS`.

Interactive docs: http://localhost:8000/docs. Default admin: `admin@feastflow.app` / `Admin@12345` (set `ADMIN_EMAIL`/`ADMIN_PASSWORD`).

## Dashboards
One React app (`frontend/`) served by FastAPI from the same container:
- **Customer** (`/`): restaurants and menu with S3 photos, cart, checkout, live order tracking, Prime.
- **Dispatch** (`/admin`, admin login): live order board (Prime first), queue depths, Prime vs standard
  wait times, delivery partners on/off shift, menu photos and availability, customers.

Pages poll every 3–5 s (pausing in hidden tabs), which works behind the ALB without sticky sessions.

Frontend development with hot reload (API on :8000 via `docker compose up`):
```bash
cd frontend && npm install && npm run dev   # http://localhost:5173, /api proxied to :8000
```

## Festival day
Admin → **Festival** has two tools:
- **Order burst**: N orders over M seconds from the 200 seeded test customers (30% Prime), through the
  normal checkout → SQS → worker path. Shows Prime priority and rider shortage on the dispatch board.
  Runs are stored in `festival_runs`, so any instance can show progress or cancel; a run whose instance
  dies is marked failed after 30 s without a heartbeat.
- **Load generator**: starts/stops Locust (`loadtest/locustfile.py`) through its web API. `normal` =
  20 users for 10 min; `festival` = 20 min peaking at 450 users, long enough for the ASG to scale out
  and back in. Locally: `docker compose --profile loadtest up` (Locust UI on :8089).

Test customers are `customer0001@loadtest.feastflow.app` … They can log in only when
`LOADTEST_PASSWORD` is set (Locust needs it); unset, the accounts stay locked. Their orders are flagged
synthetic (no emails) and they're hidden from the customer list.

Measured with the no-Docker demo (300 orders in 30 s, 30% Prime, 20 riders, 10 s deliveries):

| | Avg wait for rider | Avg order to door |
|---|---|---|
| Prime | 12.8 s | 32.8 s |
| Standard | 70.5 s | 86.4 s |

## Backend tests
```bash
cd backend
pip install -r requirements-dev.txt
ruff check . && pytest -q
# include the MySQL-only concurrency test (needs `docker compose up mysql`):
TEST_DATABASE_URL=mysql+pymysql://feastflow:feastflow@localhost:3306/feastflow_test pytest -q
```
