# 11 – Module-wise Development Roadmap (Task 3)

Phases follow the dependency order in [01 §5](01-requirement-analysis.md#5-module-dependencies). Each phase ends with a demonstrable exit criterion. Durations assume one developer working part-time and can be adjusted.

| Phase | Modules | Scope | Exit criteria | Req / AC | Est. |
|---|---|---|---|---|---|
| **P0 Foundation** | — | Repo skeleton, Dockerfile, docker-compose (app + Postgres), FastAPI app factory, config, JSON logging, error envelope, `/api/health`, `/api/health/ready`, Alembic baseline, ruff + pytest wiring | `docker compose up` gives healthy endpoints locally | NFR-06 | 1–2 days |
| **P1 Auth & Users** | M1 | `users` table, register/login/me, bcrypt, JWT, `require_admin`, seeded admin, tier toggle (self + admin) | Tests: register, login, 401/403 paths, tier change | FR-01, NFR-04, CON-02 | 2 days |
| **P2 Menu & Ordering** | M2, M3 | `menu_items` + seed, `GET /menu`, `orders`/`order_items`/history, atomic `POST /orders`, My Orders | Tests: server-side pricing, unavailable item → 422, rollback on failure | FR-02, FR-06, NFR-05 | 2–3 days |
| **P3 Priority Queue & Admin Orders** | M4 | Queue endpoint, claim-next with `SKIP LOCKED`, status PATCH with version check, history, wait-time stats | Tests: Premium before older Free order, two concurrent claims get different orders, invalid transition → 409. **AC-01 demonstrable locally.** | FR-03/04/05, NFR-05, AC-01 | 2–3 days |
| **P4 Frontend** | M1–M4 UI | Vite React TS app: auth pages, menu/cart, My Orders, admin queue/orders/users. Multi-stage Docker build serves SPA. | Full customer + admin order flow in the browser from a single container | FR-01..04 | 4–5 days |
| **P5 AWS Infrastructure** | M9 | SGs, S3 (+ bucket policy, menu images), ECR, RDS, launch template + user-data + CW agent, ALB + target group, ASG (min 2/max 4, CPU 50 %), alarms, optional SNS, Locust EC2 | App reachable via ALB DNS. `X-Served-By` alternates between 2 instances. Memory metric visible. | FR-08, FR-09, FR-11, FR-12, FR-13, NFR-02, NFR-03 | 3–4 days |
| **P6 CI/CD** | M10 | `ci.yml` (lint, tests with Postgres service, frontend build), `cd.yml` (ECR push, instance refresh, wait, smoke test checks version), rollback runbook | Push to `main`, new version live with no downtime. **AC-03 evidence captured.** | FR-14, AC-03 | 2 days |
| **P7 Monitoring Dashboard** | M6 | MetricsService (GetMetricData, ASG, ELBv2, alarms) + 30 s cache, admin dashboard charts, CloudWatch console dashboard JSON | Dashboard shows CPU, memory, traffic, health, scaling activity, alarms | FR-10, FR-11, SLA-02 | 2–3 days |
| **P8 Load-Test Module** | M5 | `locustfile.py` (seeded FREE/PREMIUM users), scenario config, start/stop/status API, lazy finalization, admin UI | Festival run shows scale-out 2 → 3–4 and scale-in afterward. **AC-02 evidence.** | FR-07, OBJ-02, NFR-01, AC-02 | 3 days |
| **P9 Cost & Reports** | M7 | Rate table, CostService (instance-hours from `GroupInServiceInstances`, ALB/RDS hours, IPv4, storage), per-run cost, report generation → S3, pre-signed download, compare endpoint | Normal vs Festival comparison report downloadable. **AC-04 evidence.** | FR-13, FR-15, NFR-07, AC-04 | 2 days |
| **P10 SLA, Evidence & Final Docs** | all | SLA document (SLA-01), availability calculation, final architecture diagram, screenshots (CloudWatch, scaling, pipeline), load-test results, cost report, README runbook, teardown | All DEL-01 / DEL-02 items checked off | SLA-01/02, OBJ-04, DEL-01/02 | 2 days |

**Total estimate:** about 25–30 working days.

## Milestones

| Milestone | After phase | Demo |
|---|---|---|
| **MS1 – Core app** | P4 | Local container: register Free + Premium, place orders, admin sees Premium first, updates status |
| **MS2 – In the cloud** | P6 | ALB URL live on 2 instances, code push auto-deploys |
| **MS3 – Elastic & observable** | P8 | Festival scenario triggers scaling, visible on dashboard |
| **MS4 – Submission** | P10 | Full deliverables package |

## Learner Lab working practices (apply from P5 onward)

1. Start every work session by refreshing the GitHub secrets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` from the lab's "AWS Details" panel.
2. Keep `infra/scripts` re-runnable so a lost environment can be rebuilt in minutes.
3. When idle for long periods, set ASG min/desired to 0, stop Locust EC2, and stop RDS.
4. Tag everything `Project=FeastFlow`. Run `99-teardown.sh` after final grading.
