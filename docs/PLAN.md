# FeastFlow: Project Workflow Plan (fresh rebuild)

## Context
The goal is a food-ordering system with two dashboards:
1. **Customer dashboard**: register or log in, browse food (images from S3), place orders, buy a **Prime** subscription so their orders are handled before ordinary ones.
2. **Restaurant/Dispatch dashboard (admin)**: orders arrive automatically, a **free delivery partner is auto-assigned**, and a **Festival Mode** floods the system with orders.

It must run on **AWS Learner Lab with only $50 of credit**. The working folder is empty. Decision: **start fresh**. The old commit `cb0ef7b` stays in git history, and its patterns can be reused for reference: `queue_service.py`, the Locust file, `infra/scripts/*`.

Decisions made: one React app with role-based dashboards · simulated delivery partners · festival = in-app button **and** Locust.

---

## 1. Corrections to the AWS service list (important for viva/report)
| What you wrote | Problem | What we'll do instead |
|---|---|---|
| **IAM** verifies if the user is Prime | IAM controls *AWS principals* (EC2, Lambda), not app customers. Learner Lab also **cannot create IAM users or roles**. | Prime status = `users.is_prime` + `prime_expires_at` in RDS, carried in the JWT and re-checked on the server at order time. IAM = `LabRole`/`LabInstanceProfile` lets EC2 and Lambda reach SQS, SNS, S3 and CloudWatch without keys. |
| **AWS Budgets** triggers scaling at CPU > 60% | Budgets only tracks **money**. It cannot read CPU or scale anything. Budgets is also often blocked in Learner Lab. | **CloudWatch alarm + ASG target-tracking policy (CPU 60%)** does the scaling. Budgets (if the lab allows it) sends alerts at $10/$25/$40, and the lab's credit meter is the fallback. |
| SQS for priority | SQS has **no message priority**. | **Two queues**: `orders-prime` and `orders-standard`, each with a DLQ. Workers always drain prime first. |
| SNS to customers | Email subscriptions need each customer to click a confirmation link. SMS is sandboxed. | One topic `order-notifications`. Each customer subscribes by email at sign-up, with a **filter policy on `user_id`**. Festival test users get no subscription. |

## 2. Architecture
```
Browser ──► ALB ──► Target Group ──► ASG (Launch Template, t3.micro, min 1 / max 4, CPU 60%)
                                       └─ each EC2: Docker [ api (FastAPI + React build) | worker ]
api  ── place order ──► RDS MySQL (status PLACED) ──► SQS orders-prime / orders-standard
worker ◄── poll prime first, then standard ── assign free partner (MySQL SKIP LOCKED) ──► SNS
S3: food images (private, presigned URLs) · CloudWatch: metrics, logs, alarms, dashboard
EventBridge Scheduler ──► Lambda: nightly ASG→0, stop RDS, stop Locust EC2 (optional morning start)
Locust EC2 (t3.small, only during tests) ──► ALB   (festival HTTP load)
```
- Workers run on every EC2, so **ASG scale-out also adds order-processing capacity**.
- The admin dashboard refreshes by **polling every 3 s**. This works behind the ALB without sticky sessions or websockets.

## 3. Tech stack
FastAPI (Python 3.12) + SQLAlchemy + Alembic · MySQL 8 (RDS) · boto3 · React + Vite + TypeScript · Docker · LocalStack for SQS/SNS/S3 during local development · Locust · AWS CLI bash scripts for infra · GitHub Actions for CI.

## 4. Data model (MySQL)
- `users` (id, name, email, password_hash, role CUSTOMER/ADMIN, is_prime, prime_expires_at)
- `restaurants` (id, name, area) · `menu_items` (restaurant_id, name, price, category, image_key, is_available)
- `orders` (user_id, restaurant_id, status, priority 0/1, total, idempotency_key, created/confirmed/assigned/delivered_at, partner_id)
- `order_items` · `order_events` (order_id, status, at): the timeline shown in both dashboards
- `delivery_partners` (name, phone, status AVAILABLE/BUSY/OFFLINE, current_order_id, deliveries_count)

**Order lifecycle:** `PLACED → CONFIRMED → PREPARING → OUT_FOR_DELIVERY → DELIVERED`. When no partner is free, the order waits in `AWAITING_PARTNER` and is retried. Prime orders are assigned first.

## 5. Core flows
1. **Order placement** (`POST /api/orders`): validate items and compute the price on the server → insert the order with `priority = 1 if prime` → send the message to the matching SQS queue → return 202. The idempotency key prevents duplicate orders when a request is retried.
2. **Worker loop**: receive from `orders-prime` (batch of 10). If it's empty, receive from `orders-standard` → process each message **idempotently**, because SQS can deliver the same message more than once → set CONFIRMED → simulated prep timer → pick a partner with `SELECT … WHERE status='AVAILABLE' ORDER BY deliveries_count LIMIT 1 FOR UPDATE SKIP LOCKED` → OUT_FOR_DELIVERY → simulated delivery timer → DELIVERED, partner back to AVAILABLE → publish to SNS at each step → delete the message.
3. **Re-assignment sweeper**: every few seconds, assign waiting orders `ORDER BY priority DESC, created_at` whenever partners free up.
4. **Prime subscription**: `POST /api/prime/subscribe` (mock payment, 30 days). A badge shows in the UI, and the order card shows "Priority".

## 6. Dashboards (one React app)
- **Customer**: Login/Register · Menu by restaurant with S3 images · Cart · Checkout · My Orders with live status timeline and assigned partner · Prime page.
- **Admin / Dispatch**: Live order board (Prime highlighted and ordered first) · Delivery partners (free/busy, add/remove) · Queue depth (SQS prime vs standard) · **Festival Mode** panel · Cloud panel (instances in the ASG, CPU, scaling activity, alarms read from CloudWatch) · Cost estimate.

## 7. Festival-day scenario
- **In-app button**: "Fire N orders over M seconds, X% prime". The API generates synthetic orders from seeded test customers straight into SQS. This shows the queue spike, prime-first processing and partners running out.
- **Locust** (separate t3.small, started and stopped from the admin panel): real HTTP traffic of login → menu → order against the ALB. This raises CPU above 60%, so the **ASG scales 1→3/4 and back down**. Profiles: `normal` (20 users) and `festival` (300+ users with a spike).
- Optional: an **ASG scheduled action** that raises min capacity on a "festival date" (proactive scaling story).

## 8. Budget plan ($50)
| Resource | ~$/hour |
|---|---|
| 2× t3.micro EC2 | 0.021 |
| ALB (+ LCU) | ~0.03 |
| RDS db.t3.micro MySQL, 20 GB | 0.017 (+~$2.3/mo storage) |
| Public IPv4 (≈4) | 0.02 |
| SQS / SNS / Lambda / S3 / CloudWatch | ≈ $0 (free tier level) |
| **Baseline** | **≈ $0.09/h** |

Locust EC2 runs only during tests (+$0.02/h). Working 8 h a day comes to about $0.75 a day, so $50 covers 2+ months **if the Lambda auto-stop runs every night**. Rules: build the infra late (after local is done), tag everything `Project=FeastFlow`, and run the teardown script after grading.

## 9. Phased workflow
| Phase | Work | Exit check |
|---|---|---|
| **P0 Setup** | Repo skeleton (`backend/`, `frontend/`, `worker` entry, `infra/`, `loadtest/`, `docs/`). Docker Compose: api, worker, mysql, localstack. Config via env vars. Health endpoint. CI (lint + tests). | `docker compose up` gives healthy endpoints |
| **P1 Auth & Prime** | Register/login (bcrypt + JWT), roles, seeded admin, Prime subscribe/expiry | Tests for 401/403 and prime flag |
| **P2 Menu & Orders** | Restaurants/menu seed, S3 image upload + presigned URLs, cart, `POST /orders` → SQS | Order lands in the right queue locally |
| **P3 Worker & Partners** | Priority consumption, partner auto-assign, lifecycle timers, sweeper, SNS publish, DLQ | Test: a prime order placed after a standard one is assigned first. Concurrent workers never double-assign a partner. |
| **P4 Frontend** | Customer + Admin dashboards (sections 6) | Full flow in the browser locally |
| **P5 Festival** | Festival button + Locust scenarios | 500 orders processed locally, prime first |
| **P6 AWS build** | Scripts in order: `01-network-sg` → `02-s3-ecr` (push image, upload food images) → `03-rds-mysql` → `04-sqs-sns` → `05-launch-template-alb-asg` → `06-cloudwatch-alarms` → `07-lambda-eventbridge` → `08-locust-ec2` → `99-teardown` | App reachable via the ALB DNS name, orders flow through real SQS and SNS |
| **P7 Monitoring** | CloudWatch agent (memory + app logs), dashboard, alarms (CPU, SQS backlog, 5xx, unhealthy hosts → SNS admin email), Budgets alerts if allowed | Dashboard shows CPU, queue depth and instances |
| **P8 Festival demo & report** | Run normal vs festival, capture ASG scale-out/in, queue drain, prime vs standard wait times, cost used; write docs and diagrams | Evidence screenshots + report |

## 10. Verification
- **Local**: `docker compose up`, then pytest (auth, priority ordering, partner assignment under concurrency, idempotent re-delivery), then manual browser run of both dashboards, then the festival button with 500 orders.
- **AWS**: `curl http://<alb-dns>/api/health` several times, checking that the `X-Served-By` instance ID alternates. Place an order and see it in the SQS console metrics and in the SNS email. Run Locust festival, then watch the CloudWatch CPU alarm → ASG activity history (scale-out, then scale-in after the test). Invoke the Lambda manually once and confirm the ASG goes to 0 and RDS is stopping.

## 11. Things to verify in your Learner Lab before P6
RDS MySQL allowed? · ECR allowed? · EventBridge Scheduler vs EventBridge rules (use rules if Scheduler is blocked) · Budgets available? · max EC2 count (we use ≤ 5).
