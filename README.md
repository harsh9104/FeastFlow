# FeastFlow

Food ordering with Prime priority, auto-assigned delivery partners and a festival-day load scenario,
deployed on AWS Learner Lab (EC2 + ALB + ASG, RDS MySQL, SQS, SNS, S3, CloudWatch, Lambda + EventBridge).

The full project plan is in [docs/PLAN.md](docs/PLAN.md).

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

## Backend tests
```bash
cd backend
pip install -r requirements-dev.txt
ruff check . && pytest -q
# include the MySQL-only concurrency test (needs `docker compose up mysql`):
TEST_DATABASE_URL=mysql+pymysql://feastflow:feastflow@localhost:3306/feastflow_test pytest -q
```
