# 10 – Recommended Project Folder Structure (Task 3)

Monorepo layout: one repo, one Docker image, one pipeline.

```text
FeastFlow/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # PR + push: lint, test, build (no deploy)
│       └── cd.yml                  # main only: build, push ECR, instance refresh, smoke test
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, middleware, static SPA mount
│   │   ├── core/
│   │   │   ├── config.py           # pydantic-settings, env vars
│   │   │   ├── security.py         # bcrypt, JWT encode/decode
│   │   │   ├── logging.py          # JSON logging
│   │   │   ├── errors.py           # error envelope + exception handlers
│   │   │   └── instance.py         # IMDSv2 instance-id / AZ lookup
│   │   ├── db/
│   │   │   ├── session.py          # engine, pool sizing, get_db
│   │   │   └── base.py
│   │   ├── models/                 # SQLAlchemy ORM: user, menu_item, order, order_item,
│   │   │                           # order_status_history, load_test_run, report
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── api/
│   │   │   ├── deps.py             # get_current_user, require_admin, require_customer
│   │   │   └── v1/
│   │   │       ├── health.py
│   │   │       ├── auth.py
│   │   │       ├── users.py
│   │   │       ├── menu.py
│   │   │       ├── orders.py
│   │   │       ├── admin_orders.py
│   │   │       ├── admin_users.py
│   │   │       ├── load_tests.py
│   │   │       ├── cloud.py
│   │   │       └── costs_reports.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── order_service.py
│   │   │   ├── queue_service.py    # priority ordering, SKIP LOCKED, transitions
│   │   │   ├── load_test_service.py# Locust HTTP client, lazy finalization
│   │   │   ├── metrics_service.py  # boto3 CloudWatch/ASG/ELBv2 + TTL cache
│   │   │   ├── cost_service.py
│   │   │   └── storage_service.py  # S3 put / presign
│   │   └── config/
│   │       ├── aws_rates.json      # us-east-1 on-demand rates (dated)
│   │       └── scenarios.json      # NORMAL / FESTIVAL parameters
│   ├── alembic/
│   │   ├── env.py                  # advisory lock around upgrade
│   │   └── versions/
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_orders.py
│   │   ├── test_queue_priority.py  # Premium-first + concurrent claim
│   │   └── test_status_transitions.py
│   ├── requirements.txt
│   ├── pyproject.toml              # ruff, pytest config
│   └── entrypoint.sh               # migrate, then exec gunicorn
├── frontend/
│   ├── src/
│   │   ├── api/                    # client.ts + per-resource modules
│   │   ├── context/AuthContext.tsx
│   │   ├── routes/                 # ProtectedRoute, AdminRoute
│   │   ├── components/             # Navbar, MenuCard, CartDrawer, StatusBadge, PriorityBadge, MetricChart
│   │   ├── pages/
│   │   │   ├── customer/           # Login, Register, Menu, MyOrders, Profile
│   │   │   └── admin/              # Queue, Orders, LoadTests, Dashboard, Costs, Users
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts              # dev proxy /api -> localhost:8000
├── loadtest/
│   ├── locustfile.py               # CustomerUser: login once, browse, order, view orders
│   ├── users.csv                   # seeded load-test credentials (FREE / PREMIUM mix)
│   └── README.md
├── infra/
│   ├── user-data/
│   │   ├── app-instance.sh         # Docker, CW agent, ECR login, docker run
│   │   └── locust-instance.sh
│   ├── cloudwatch/
│   │   ├── agent-config.json       # mem_used_percent, disk_used_percent
│   │   └── dashboard.json
│   ├── policies/
│   │   ├── s3-bucket-policy.json   # enforceable (resource policy)
│   │   └── app-least-privilege.json# design reference (cannot attach in Learner Lab)
│   ├── scripts/                    # idempotent AWS CLI provisioning, run in order
│   │   ├── 00-env.sh
│   │   ├── 01-network-sg.sh
│   │   ├── 02-s3-ecr.sh
│   │   ├── 03-rds.sh
│   │   ├── 04-launch-template-asg-alb.sh
│   │   ├── 05-alarms-sns.sh
│   │   ├── 06-locust.sh
│   │   └── 99-teardown.sh
│   ├── cloudformation/             # [OPTIONAL] IaC alternative to scripts
│   └── codebuild/buildspec.yml     # [OPTIONAL] CodeBuild alternative
├── docs/                           # these design docs + later: SLA, cost report, results
├── Dockerfile                      # multi-stage: node build -> python runtime
├── docker-compose.yml              # local: app + postgres:16
├── .env.example
├── .dockerignore
├── .gitignore
└── README.md
```

## Conventions

- **Layering:** `api` (HTTP only) → `services` (business rules, transactions) → `models` (persistence). Routers contain no SQL.
- **Config:** all through env vars defined in `core/config.py`. Nothing AWS-specific is hard-coded.
- **One image:** `Dockerfile` stage 1 builds `frontend/dist`. Stage 2 copies it to `backend/app/static`. FastAPI serves `/api/*` and falls back to `index.html` for everything else.
- **Infra scripts** are re-runnable and tag every resource `Project=FeastFlow`, which makes teardown and cost attribution easy.
