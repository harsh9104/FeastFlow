# FeastFlow 🍽️

**A food-ordering platform built to survive a festival-night rush on AWS: it scales out automatically,
serves Prime customers first, and never loses an order.**

[![CI/CD](https://github.com/harsh9104/FeastFlow/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/harsh9104/FeastFlow/actions/workflows/ci-cd.yml)
![AWS](https://img.shields.io/badge/AWS-us--east--1-FF9900?logo=amazonwebservices&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![MySQL](https://img.shields.io/badge/RDS_MySQL-8.4-4479A1?logo=mysql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-container-2496ED?logo=docker&logoColor=white)

FeastFlow is a cloud computing project: a complete ordering system (customer site + admin dispatch
dashboard) deployed on **11 AWS services** and tested with real traffic. Customers browse restaurants,
order, follow their order live and can buy **Prime** so their orders are handled first. A built-in
**Festival mode** floods the system with orders or HTTP traffic to prove it scales.

<p align="center">
  <img src="docs/screenshots/01-home.png" width="49%" alt="Customer home page">
  <img src="docs/screenshots/10-burst-board.png" width="49%" alt="Dispatch board during a festival burst">
</p>

---

## Results at a glance

| What was tested | Result on the live AWS deployment |
|---|---|
| **Auto scaling** under a 20-minute festival load test (up to 450 users) | 1 → 2 → 3 instances in 5-8 min, back to 1 about 15 min after the rush |
| **Response time** while scaling | p95 fell from 1.4 s on 1 instance to **98 ms** on 3 |
| **Reliability** over 94,000 requests | **0.21 %** failed (fast `503 Server busy` while new instances booted), no crashes |
| **Prime priority** in a 300-order burst with only 20 riders | Prime waited **48 s** for a rider vs **150 s** for standard (3× less) |
| **Order safety** | 300 / 300 burst orders created, 0 lost, 0 in dead-letter queues |
| **Load balancing** | Requests alternate across instances in 2 Availability Zones |
| **Cost** | Whole project (development + 3 load tests) used **$3.90** of the $50 lab credit |

Full write-up with all evidence: **[docs/REPORT.md](docs/REPORT.md)** · [PDF](docs/REPORT.pdf)

---

## Architecture

```mermaid
flowchart LR
  U[Customer / Admin browser] -->|HTTP| ALB[Application Load Balancer]
  L[Locust EC2<br/>load generator] -->|festival traffic| ALB
  subgraph ASG[Auto Scaling Group · 1-4 × t3.micro · 2 AZs · scale at 60 % CPU]
    E[EC2 instances<br/>API + worker containers]
  end
  ALB --> E
  E -->|users, orders, riders| RDS[(RDS MySQL 8.4)]
  E -->|new order| Q[[SQS orders-prime<br/>SQS orders-standard]]
  Q -->|Prime read first| E
  Q -.->|5 failures| DLQ[[Dead-letter queues]]
  E -->|status emails| SNS[SNS]
  E -->|dish photos| S3[(S3 private bucket)]
  ECR[(ECR)] -->|image at boot| E
  E -->|metrics + logs| CW[CloudWatch<br/>dashboard · 9 alarms]
  EB[EventBridge Scheduler<br/>23:00 IST] --> LAM[Lambda auto-stop]
  LAM -->|park ASG + RDS| ASG
  GH[GitHub Actions] -->|test · build · push · roll out| ECR
```

| AWS service | What it does in FeastFlow |
|---|---|
| **EC2 + Auto Scaling** | Runs the API and the order worker; target tracking keeps CPU near 60 %, unhealthy instances are replaced |
| **Application Load Balancer** | One public entry point, health checks every 15 s, spreads traffic over both AZs |
| **RDS MySQL** | Users, menus, orders, riders (private, not reachable from the internet) |
| **SQS** | Two queues so Prime is read first (SQS has no priority), each with a dead-letter queue |
| **SNS** | Order emails to customers, alarm emails to the admin |
| **S3** | Private dish photos served through short-lived presigned URLs |
| **ECR** | The Docker image, tagged with each git commit |
| **CloudWatch** | Dashboard, logs, 9 alarms (CPU, backlogs, DLQs, unhealthy hosts, 5xx, memory, RDS) |
| **Lambda + EventBridge Scheduler** | Parks the whole stack at 23:00 IST every night to save credit |
| **AWS Budgets** | $50 budget with email alerts |
| **IAM / SSM** | Instance role instead of stored keys; remote commands without SSH |

---

## How it works

**Ordering.** `POST /api/orders` validates the cart, prices it on the server, saves the order in MySQL
and *then* puts a message on `orders-prime` or `orders-standard`. It answers `202 Accepted` immediately,
so customers never wait for the kitchen.

**Prime priority without starvation.** Each worker reads the Prime queue 4 times for every 1 read of the
standard queue. When food is ready, a free rider is chosen **Prime first, then oldest first**, and standard
orders that have waited too long are promoted.

**Safe with many workers.** Riders and orders are locked with `SELECT … FOR UPDATE SKIP LOCKED`, so two
workers on different instances can never take the same rider or order. A message that fails 5 times
goes to a dead-letter queue and raises an alarm.

**Graceful under overload.** Admission control lets each instance run at most 10 API requests at once
(below its 12 database connections) and queues the rest. This fixed a real thread-pool / connection-pool
deadlock found in the first load test, which had been crashing instances in a loop.

**Order lifecycle:** `PLACED → CONFIRMED → PREPARING → AWAITING_PARTNER → OUT_FOR_DELIVERY → DELIVERED`,
with SNS emails at CONFIRMED, OUT_FOR_DELIVERY and DELIVERED.

---

## Screenshots

| | |
|---|---|
| ![Menu](docs/screenshots/02-menu.png) **Menu** with photos from S3 | ![Order delivered](docs/screenshots/04-order-delivered.png) **Live order tracking**, rider auto-assigned |
| ![Prime vs standard](docs/screenshots/11-prime-vs-standard.png) **Prime vs standard** wait times during a burst | ![Cloud panel](docs/screenshots/29-cloud-panel.png) **Cloud & cost** admin page: servers, CPU, cost per hour |
| ![CloudWatch dashboard](docs/screenshots/18-dashboard-full.png) **CloudWatch**: CPU, instances 1 → 3 → 1, requests | ![CI/CD run](docs/screenshots/30-cicd-run.png) **GitHub Actions**: test, build, deploy |

All 37 figures (app and AWS Console) are in the [report appendices](docs/REPORT.md#appendix-a-application-screenshots-live-aws-deployment-21-nov-2026).

---

## CI/CD

Every push runs [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml):

```
push / PR ─┬─ backend: ruff lint + pytest (SQLite + moto fakes for AWS)
           └─ frontend: TypeScript type-check + Vite build
                    │ both pass
   branch / PR ─────┴─► docker: image build check
   push to main ───────► deploy: build → push to ECR (tag = commit) → rolling redeploy of the ASG → smoke test through the ALB
```

New instances must pass the load balancer health check before old ones are removed, so a bad image
never takes the site down. Learner Lab has no IAM users or OIDC roles, so the deploy job uses the lab
session keys stored as encrypted repository secrets.

---

## Documents

| Document | What's in it |
|---|---|
| [Project report](docs/REPORT.md) ([PDF](docs/REPORT.pdf)) | Architecture, security, deployment, monitoring, test results, cost, 37 figures |
| [Service Level Agreement](docs/FeastFlow-SLA.docx) | Commitments (99.0 % availability, p95 < 500 ms, errors < 1 %), composite availability from AWS SLAs, RTO / RPO, incidents, credits |
| [Monthly AWS bill report](docs/FeastFlow-AWS-Bill-Report.docx) | A month with 7 festival days costs **$63.09**; every line item explained |
| [Project plan](docs/PLAN.md) | Phases, design decisions, budget |
| [Demo checklist](docs/DEMO-CHECKLIST.md) | Step-by-step demo and screenshot guide |
| [AWS deployment guide](infra/README.md) | Scripts to build, run, park and delete the AWS stack |

---

## Tech stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, boto3 · **Frontend:** React 18, TypeScript,
Vite · **Data:** MySQL 8.4 (RDS), SQLite for tests · **Infra:** Docker, AWS CLI scripts (idempotent),
CloudWatch agent · **Testing:** pytest, moto, Locust · **CI/CD:** GitHub Actions

```
backend/      FastAPI app (app/), order worker (worker/), Alembic migrations, tests
frontend/     React app: customer site + admin dispatch dashboard
infra/        AWS scripts (01-09, start/stop/redeploy/teardown), Lambda, CloudWatch agent config
loadtest/     Locust scenarios (normal, festival)
docs/         Report, SLA, bill report, plan, screenshots
.github/      CI/CD workflow
```

---

## Run it yourself

### Quick demo, no Docker
```bash
cd frontend && npm install && npm run build && cd ../backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # once
.venv/Scripts/python scripts/demo_no_docker.py    # http://127.0.0.1:8000
```
Real API, worker and UI; SQLite instead of MySQL and a local moto server for SQS/SNS/S3 (photos load,
no emails). Fresh data on every start, timers shortened. If Locust is installed in `loadtest/.venv`, the
Festival page's load generator works too.

### With Docker
```bash
docker compose up --build
curl http://localhost:8000/api/health        # liveness
curl http://localhost:8000/api/health/ready  # checks MySQL
```
Interactive API docs: http://localhost:8000/docs. Local admin: `admin@feastflow.app` / `Admin@12345`
(change with `ADMIN_EMAIL` / `ADMIN_PASSWORD`; the AWS deployment generates its own password).

Frontend with hot reload: `cd frontend && npm run dev` (http://localhost:5173, `/api` proxied to :8000).

### On AWS
See **[infra/README.md](infra/README.md)**: nine scripts build the stack in 30-45 minutes on an AWS
Academy Learner Lab account; `stop.sh` / `start.sh` park and resume it, `99-teardown.sh` deletes everything.

### Tests
```bash
cd backend
pip install -r requirements-dev.txt
ruff check . && pytest -q
# include the MySQL-only concurrency test (needs `docker compose up mysql`):
TEST_DATABASE_URL=mysql+pymysql://feastflow:feastflow@localhost:3306/feastflow_test pytest -q
```

---

<details>
<summary><b>API reference</b></summary>

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | anyone |
| GET | `/api/users/me` | logged in |
| POST | `/api/prime/subscribe` · `/api/prime/cancel` | customer (mock payment, 30 days) |
| GET | `/api/restaurants` · `/api/restaurants/{id}/menu` | anyone (images are presigned S3 URLs) |
| POST | `/api/orders` (optional `Idempotency-Key` header) | customer → 202, sent to `orders-prime` or `orders-standard` |
| GET | `/api/orders` · `/api/orders/{id}` | owner (or admin) |
| GET | `/api/admin/users?prime_only=true` | admin |
| PATCH | `/api/admin/menu-items/{id}` (price, availability) | admin |
| POST | `/api/admin/menu-items/{id}/image` (JPEG/PNG/WebP ≤ 2 MB → S3) | admin |
| GET | `/api/admin/orders?status=ACTIVE` (Prime first) · `ALL` · any single status | admin |
| GET · POST | `/api/admin/partners` | admin |
| PATCH | `/api/admin/partners/{id}` (`AVAILABLE` / `OFFLINE`, not mid-delivery) | admin |
| GET | `/api/admin/dispatch/stats` (queue depths, partners, Prime vs standard wait times) | admin |
| GET · POST | `/api/admin/festival/runs` · `POST …/{id}/cancel` | admin |
| GET | `/api/admin/loadtest` · `POST /api/admin/loadtest/start` (`normal` / `festival`) · `/stop` | admin |
| GET | `/api/admin/cloud` (ASG, CPU, alarms, scaling activity, cost estimate) | admin |
| GET | `/api/health` · `/api/health/ready` | load balancer |

</details>

<details>
<summary><b>Festival mode details</b></summary>

Admin → **Festival** has two tools:
- **Order burst:** N orders over M seconds from 200 seeded test customers (30 % Prime), through the
  normal checkout → SQS → worker path. Shows Prime priority and rider shortage on the dispatch board.
  Runs are stored in the database, so any instance can show progress or cancel; a run whose instance
  dies is marked failed after 30 s without a heartbeat.
- **Load generator:** starts and stops Locust (`loadtest/locustfile.py`) on its own EC2 instance.
  `normal` = 20 users for 10 min; `festival` = 20 min peaking at 450 users, long enough for the ASG to
  scale out and back in. Locally: `docker compose --profile loadtest up` (Locust UI on :8089).

Test customers (`customer0001@loadtest.feastflow.app` …) can log in only when `LOADTEST_PASSWORD` is
set. Their orders are flagged synthetic (no emails) and hidden from the customer list;
`infra/scripts/clear-test-orders.sh` cancels leftovers after a load test.

Worker timers are set with `CONFIRM_SECONDS`, `PREP_SECONDS`, `DELIVERY_SECONDS`; standard orders
waiting longer than `AGING_SECONDS` count as urgent.

</details>

---

**Author:** Harsh Shah ([@harsh9104](https://github.com/harsh9104)) · Cloud computing project, November 2026
