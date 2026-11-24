# FeastFlow: Scalable Food Ordering on AWS

**Cloud computing project report** · Deployed on AWS Academy Learner Lab (us-east-1) · November 2026

---

## 1. Introduction

FeastFlow is a food-ordering web application built to show how a cloud system handles a sudden
rush of orders, like a festival evening, without slowing down for its best customers or falling over.

It has two sides:
- **Customers** register, browse restaurants and dishes (photos stored in S3), place orders, follow
  each order live from "Placed" to "Delivered", and can buy a **Prime** subscription so their orders
  are handled first.
- **Admin / dispatch** sees every order arrive, delivery partners (riders) are **assigned automatically**,
  and a **Festival mode** floods the system with orders or with real HTTP traffic to test it.

The goals were:
1. A working end-to-end ordering system on real AWS services.
2. **Prime orders served before standard orders**, even when riders run out.
3. **Automatic scaling** when traffic rises, and scaling back down afterwards to save money.
4. **Load balancing** across all running servers.
5. **Monitoring and alerts** for problems and for cost.
6. Stay inside the **$50 Learner Lab credit**.

## 2. Architecture

```mermaid
flowchart LR
  U[Customer / Admin browser] -->|HTTP :80| ALB[Application Load Balancer]
  L[Locust EC2<br/>load generator] -->|festival traffic| ALB
  ALB --> TG[Target group<br/>health check /api/health]
  subgraph ASG[Auto Scaling Group: 1 to 4 x t3.micro, scale at 60% CPU]
    E1[EC2: api + worker containers]
    E2[EC2: api + worker containers]
  end
  TG --> E1 & E2
  E1 & E2 -->|orders, users, riders| RDS[(RDS MySQL 8.4)]
  E1 & E2 -->|new order| SQSP[[SQS orders-prime]]
  E1 & E2 -->|new order| SQSS[[SQS orders-standard]]
  SQSP & SQSS -->|worker reads prime first| E1 & E2
  SQSP -.->|5 failures| DLQ[[Dead-letter queues]]
  E1 & E2 -->|status emails| SNS[SNS order-notifications]
  E1 & E2 -->|dish photos, presigned URLs| S3[(S3 private bucket)]
  ECR[(ECR image)] -->|docker pull at boot| E1 & E2
  E1 & E2 -->|metrics + logs| CW[CloudWatch<br/>dashboard, 9 alarms]
  CW -->|alarm emails| SNSA[SNS feastflow-alerts]
  EB[EventBridge Scheduler<br/>23:00 IST] --> LAM[Lambda auto-stop]
  LAM -->|ASG to 0, stop RDS + Locust| ASG
  B[AWS Budgets $50] -->|50/80/100% emails| Admin((Admin email))
```

**How a request flows:** the browser talks only to the load balancer. The ALB sends each request to
a healthy EC2 instance in the Auto Scaling Group. Every instance runs two Docker containers from the
same image: the **API** (FastAPI, also serves the React site) and the **order worker**. So adding an
instance adds both web capacity and order-processing capacity.

**How an order flows:**
1. `POST /api/orders` checks the items, computes the price on the server, saves the order in MySQL
   (status `PLACED`) and puts a message on **`orders-prime`** (Prime customer) or **`orders-standard`**.
   It answers `202 Accepted` at once, so the customer never waits for the kitchen.
2. A worker reads **Prime first** (4 Prime polls for every standard poll, so standard orders still move),
   marks the order `CONFIRMED`, then `PREPARING` on a timer.
3. When the food is ready, a free rider is picked with `SELECT … FOR UPDATE SKIP LOCKED`, so two
   workers on different instances can never take the same rider or order. If no rider is free the order
   waits in `AWAITING_PARTNER`; waiting orders are assigned **Prime first, then oldest first**, and
   standard orders that waited too long are promoted so they are never starved.
4. `OUT_FOR_DELIVERY` → `DELIVERED`; the rider becomes free again. SNS emails the customer at the
   main steps.
5. A message that fails 5 times goes to a **dead-letter queue** (and raises an alarm) instead of
   blocking the queue.

## 3. AWS services used

| Service | What it does in FeastFlow |
|---|---|
| **EC2** (t3.micro) | Runs the API and worker containers. Amazon Linux 2023, set up by a user-data script at boot. |
| **Auto Scaling Group + Launch Template** | 1 to 4 instances. Target-tracking policy keeps average CPU near **60 %**. Unhealthy instances are replaced automatically. |
| **Application Load Balancer** | Single public address; spreads requests over all healthy instances; health check on `/api/health`. |
| **RDS MySQL 8.4** (db.t3.micro) | Users, menu, orders, order timeline, riders. Private (not reachable from the internet). |
| **SQS** | Two order queues (Prime and standard), each with a dead-letter queue. SQS has no message priority, so priority comes from using two queues. |
| **SNS** | `order-notifications`: emails customers about their orders. `feastflow-alerts`: emails the admin when an alarm fires. |
| **S3** | Private bucket for dish photos; public access blocked, encrypted, served through short-lived presigned URLs. |
| **ECR** | Stores the application Docker image; instances pull it at boot. |
| **CloudWatch** | Metrics (CPU, memory via the CloudWatch agent, queue depth, requests, errors), app logs, the **FeastFlow** dashboard and 9 alarms. |
| **Lambda + EventBridge Scheduler** | Cost guard: every night at 23:00 IST the Lambda scales the ASG to 0 and stops RDS and the Locust instance. |
| **AWS Budgets** | $50 monthly budget, emails at 50 % and 80 % spent and when the forecast passes 100 %. |
| **IAM (LabRole / LabInstanceProfile)** | Lets EC2 and Lambda use SQS, SNS, S3, ECR and CloudWatch **without any keys stored on the servers**. |
| **Systems Manager (SSM)** | Remote commands on instances without opening SSH. |

### Design corrections (important for the viva)
| Common idea | Why it doesn't work | What FeastFlow does |
|---|---|---|
| "IAM checks if a customer is Prime" | IAM controls AWS resources, not app users. Learner Lab also can't create IAM users or roles. | Prime is a field in MySQL (`is_prime`, `prime_expires_at`), carried in the login token and re-checked at order time. |
| "Budgets scales the servers at 60 % CPU" | Budgets only tracks money; it can't read CPU or scale. | A **CloudWatch alarm + ASG target-tracking policy** scales. Budgets only sends cost alerts. |
| "SQS has priority" | SQS has no message priority. | **Two queues**, read Prime first. |

## 4. Security
- Security groups form a chain: internet → ALB (port 80) → app instances (port 8000, **only from the
  ALB**) → RDS (port 3306, **only from the app**). No SSH port is open anywhere.
- RDS and the S3 bucket are private. Photos are shown through presigned URLs that expire.
- Passwords are hashed with bcrypt; logins use signed JWT tokens; a wrong email and a wrong
  password take the same time and give the same message, so attackers can't find valid emails.
- No AWS keys on the servers: they use the instance role. Secrets (database password, JWT secret,
  admin password) are generated randomly at deploy time and kept out of git.
- IMDSv2 is required on all instances.
- Retried checkouts can't create duplicate orders (idempotency key).

## 5. Deployment
Everything is created by plain AWS CLI scripts in `infra/scripts/`, run in order. Each script is safe to
run again (it skips what already exists).

| Script | Creates |
|---|---|
| `01-network-sg.sh` | Security groups |
| `02-s3-ecr.sh`, `02b-push-image.sh` | S3 bucket, ECR repository, builds and pushes the image |
| `03-rds-mysql.sh` | RDS MySQL |
| `04-sqs-sns.sh` | Queues, dead-letter queues, notification topic |
| `08-locust-ec2.sh` | Locust load-generator instance |
| `05-launch-template-alb-asg.sh` | Load balancer, target group, launch template, Auto Scaling Group, scaling policy |
| `06-cloudwatch-alarms.sh` | 9 alarms, alert topic, dashboard |
| `07-lambda-eventbridge.sh` | Auto-stop Lambda and nightly schedule |
| `09-budget.sh` | Monthly budget and alerts |
| `stop.sh` / `start.sh` / `redeploy.sh` / `99-teardown.sh` | Daily park/resume, roll out new code, delete everything |

### 5.1 CI/CD pipeline
New code reaches AWS through a GitHub Actions pipeline (`.github/workflows/ci-cd.yml`):

```
push / pull request ─┬─ backend: ruff lint + 9 pytest suites (SQLite + moto fakes for AWS)
                     └─ frontend: TypeScript typecheck + Vite build
                              │ (both must pass)
        branch / PR ──────────┴──► docker: image build check
        push to main ─────────────► deploy (GitHub environment "production"):
                                     1. build image, push to ECR as feastflow:<git sha> and :latest
                                     2. redeploy.sh: rolling replacement of the ASG instances
                                     3. smoke test /api/health/ready through the load balancer
```

- **Continuous integration:** every push and pull request runs the lint, tests and both builds, so a
  broken change is caught before it can be deployed.
- **Continuous deployment:** a green push to `main` is deployed with no manual steps and no downtime.
  New instances must pass the target group health check before the old ones are removed, so a bad
  image never takes the site down (the roll stops and the old instances stay). Each image is tagged with
  its commit, so a rollback is a re-run of an older workflow run.
- Deploys never overlap (a `concurrency` group), and each run writes the image tag, site URL and
  health result to its summary page. If the stack is parked, the image is still pushed and goes live
  on the next `start.sh`.
- **Learner Lab limits:** the lab can't create IAM users or an OIDC role for GitHub, so the deploy job
  uses the lab's session keys stored as encrypted repository secrets. They expire with each lab session,
  so `infra/scripts/gh-set-aws-secrets.sh` refreshes them after Start Lab; until then the deploy job fails
  early with a clear message while CI still runs. Instance refresh is blocked too, which is why the
  pipeline reuses `redeploy.sh`.

**Figure 5.1a: A pipeline run on `main` (commit `90caa95`): backend and frontend pass, deploy passes; the docker check is skipped because on `main` the deploy job builds the image**
![CI/CD run: all jobs green](screenshots/30-cicd-run.png)

**Figure 5.1b: The deploy job's summary: image `feastflow:90caa95` (also `:latest`) pushed to ECR. The stack was parked at the time (0 in-service instances), so the image went live on the next `start.sh`**
![Deploy summary](screenshots/31-cicd-summary.png)

**Figure 5.1c: The lab session keys stored as encrypted repository secrets (values are never shown)**
![Repository secrets](screenshots/32-cicd-secrets.png)

Problems found and fixed during the first real deployment:
- Learner Lab blocks **ASG instance refresh**, so `redeploy.sh` replaces instances itself (start new ones,
  wait until healthy, remove old ones) while pausing auto scaling so it can't interfere.
- The site is plain HTTP (no domain or certificate in the lab), and browsers hide some features on
  HTTP pages; the checkout used one (`crypto.randomUUID`) and was fixed with a fallback.
- A CloudWatch metric-math expression and Windows path handling in the scripts were corrected.
- Under load the API froze in a thread-pool / connection-pool deadlock; fixed with admission control
  (details in section 7.3).

## 6. Monitoring and alerts
The **FeastFlow** CloudWatch dashboard shows: ASG CPU (with the 60 % scaling line), instances in
service, orders waiting in each SQS queue, ALB requests and 5xx errors, response time (p90), RDS CPU
and connections, and memory.

| Alarm | Fires when |
|---|---|
| feastflow-high-cpu | Average CPU > 80 % for 5 min (still overloaded after scaling) |
| feastflow-orders-backlog | > 200 standard orders waiting for 5 min |
| feastflow-prime-backlog | > 50 Prime orders waiting for 3 min |
| feastflow-dlq-orders-prime / -standard | Any order lands in a dead-letter queue |
| feastflow-unhealthy-hosts | An instance fails health checks for 3 min |
| feastflow-high-memory | Memory > 85 % |
| feastflow-rds-cpu | Database CPU > 80 % for 5 min |
| feastflow-5xx-rate | Server errors > 5 % of requests |

Alarms email the admin through SNS. The ASG's own scaling alarms (created by the target-tracking policy)
are separate and act automatically.

**Cloud & cost panel in the admin dashboard.** The admin site has its own *Cloud & cost* page
(`GET /api/admin/cloud`), so the scaling story can be shown without opening the AWS Console. It reads,
through the instance role:
- the Auto Scaling Group: servers with zone, state and health, min / desired / max, the 60 % CPU target;
- CloudWatch: average CPU and servers in service for the last hour (two charts on the same time axis),
  and every FeastFlow alarm plus the ASG's own scaling alarms, firing ones first;
- the ASG's scaling activity history (launches and terminations with their cause);
- an hourly **cost estimate** built from what is running right now (app servers, ALB, RDS running or
  stopped, Locust, public IPv4 addresses) at us-east-1 list prices, projected to a work day, a day and a
  month, next to the actual spend from AWS Budgets.

Each AWS read is separate, so if the lab refuses one call only that part of the page is missing.
On the Learner Lab this happens with AWS Budgets: LabRole may not call `budgets:ViewBudget`, so the
panel shows the estimate but not the actual spend (the budget and its email alerts still work, as they
were set up with the lab user's own credentials).
Results are cached for 15 s per instance so several open admin tabs don't flood the AWS APIs.

## 7. Test results

### 7.1 Order flow on AWS
An order placed on the live site went `PLACED → CONFIRMED → PREPARING → OUT_FOR_DELIVERY → DELIVERED`
in about 70 seconds, through the real SQS queue and worker, with a rider assigned automatically. *(Figures 3-4.)*

### 7.2 Festival order burst: Prime priority under a rush
**Setup:** 300 orders in 60 seconds, 30 % Prime, only 20 riders, so riders run out on purpose.

| | Orders | Avg time to confirm | Avg wait for a rider | Avg order to door |
|---|---|---|---|---|
| **Prime** | 90 | 1 s | **48 s** | **112 s** |
| **Standard** | 210 | 1 s | 150 s | 189 s |

All 300 orders were created with **0 failures**. Prime orders waited about **3 times less** for a rider
than standard orders and were delivered about 77 seconds sooner, while standard orders were still
delivered (no starvation). *(Figures 14-16; a second burst run showed the same pattern: Prime 46.7 s
vs standard 100 s waiting for a rider.)*

### 7.3 Load test, auto scaling and load balancing
**Setup:** Locust on its own EC2, `festival` profile, 20 minutes: ramp to 300 users, peak of 450 users at
minute 9-11, then down to 30 users so scale-in can be seen. Each simulated user logs in, browses
menus and places orders through the load balancer.

**Timeline (21 Nov 2026, times IST):**

| Time | Users | Instances | Avg CPU | Requests/s | p95 response | What happened |
|---|---|---|---|---|---|---|
| 18:13 | 50 | 1 | 28 % | 28 | 70 ms | Test starts |
| 18:16 | 237 | 1 | **77 %** | 87 | 1.2 s | CPU above the 60 % target |
| 18:18 | 237 | 1 → **2** | 67 % | 81 | 1.4 s | **Scale-out alarm fires, 2nd instance launched** |
| 18:21 | 237 | 2 → **3** | 66 % | 129 | **130 ms** | 2nd instance healthy, traffic split across both; 3rd launched |
| 18:24 | 300 | **3** | 64 % | 165 | **98 ms** | All 3 healthy, requests spread evenly over 3 instances |
| 18:27 | 30 | 3 | 24 % → 1 % | 17 | 55 ms | Festival rush over |
| 18:40 | 0 | 3 → **2** | 1 % | 0 | | **Scale-in alarm (15 min below target), instance removed** |
| 18:42 | 0 | 2 → **1** | 1 % | 0 | | Back to 1 instance: paying for capacity only while it's needed |

**Totals:** 93,931 requests, 196 failed (**0.21 %**), peak 402 simultaneous users and 177 requests/s.
Every failure was a fast `503 Server busy` from the app's admission limit during the minutes when one
instance carried the whole rush, before the new instances were ready. No instance crashed.

**Load balancing:** each response carries an `X-Served-By` header with the instance id. Sampling it
during the test showed requests alternating over 2, then 3 instances (for example 3 / 2 / 3 out of 8),
and response time fell from 1.4 s on one instance to about 100 ms on three.

**Second run (22 Nov 2026, times IST), same profile, to repeat the result:**

| Time | Users | Instances | Avg CPU | Requests/s | p95 response | What happened |
|---|---|---|---|---|---|---|
| 00:57 | 50 | 1 | ~25 % | 27 | 70 ms | Test starts |
| 01:00 | 209 | 1 | 81 % | 90 | 790 ms | CPU above the 60 % target |
| 01:03 | 209 | 1 → **2** | 71 % | 89 | 660 ms | **Scale-out alarm fires, 2nd instance launched** |
| 01:06 | 375 | 2 → **3** | 70 % → 45 % | 42 | 11 s | Users jump while the 3rd instance boots: the worst minute of the test |
| 01:09 | 300 | **3** | 62 % | | | All 3 targets healthy; 9 sample requests split 3 / 2 / 4 over the three instances |
| 01:11 | 300 | 3 | 49 % | 166 | **85 ms** | Fully recovered on 3 instances; rush ends, users drop to 30 |
| 01:25 | 30 | 3 → **2** | low | 17 | 57 ms | **Scale-in alarm (about 15 min below target), instance removed** |
| 01:27 | 30 | 2 → **1** | low | 17 | | Back to 1 instance at 01:28 |

**Totals:** 94,174 requests, 325 failed (**0.35 %**), all fast `503 Server busy` rejections from the
admission limit while one or two instances carried a sudden jump in users. No failures after the 3rd
instance turned healthy at 01:09, and no instance crashed. Both runs show the same pattern: scale-out
about 5-6 minutes after load rises, scale-in about 15 minutes after it drops, and response time back
near 100 ms once the new instances are in service.

**Third run (25 Nov 2026, times IST), recorded in the AWS Console (Appendix B):** the stack was
started at 01:27, the `festival` Locust profile and a 5,000-order burst (35 % Prime) at about 01:40.
CPU passed the 60 % target and peaked at about 75 %. The group scaled 1 → 2 at about 01:43 and
2 → 3 at about 01:48. At 01:49 two targets were healthy and requests alternated between them; at 01:54
all 3 servers were in service. After the rush, the group scaled 3 → 2 → 1 at about 02:13-02:15. It
showed the same pattern as the first two runs. *(Figures 18-25.)*

**Problem found and fixed during testing.** The first run crashed instances in a loop under load
although CPU stayed low. The logs showed `QueuePool limit … reached, connection timed out`: FastAPI's
worker threads and the database connections were waiting on each other (a thread-pool / connection-pool
deadlock), so even the health check stopped answering and the ALB replaced the instance. The fix is
**admission control**: at most 10 API requests run at once per instance (below the 12 database
connections), extra requests queue without holding a thread or connection, and the health check skips
the queue. After the fix the system degraded gracefully and scaled exactly as designed.

**Cleaning up after a load test:** Locust places real orders (15,873 in the first run, 14,607 in the second), far more than 20
riders can deliver. `infra/scripts/clear-test-orders.sh` cancels leftover load-test orders so real
customers aren't queued behind them.

*(Console evidence: Appendix B, Figures 18-25.)*

## 8. Cost
| Resource | Approx. cost per hour |
|---|---|
| 1 × t3.micro app instance (up to 4 during tests) | $0.0104 each |
| Application Load Balancer | ~$0.025 |
| RDS db.t3.micro + 20 GB | ~$0.02 |
| Locust t3.small (only during tests) | $0.021 |
| Public IPv4 addresses | ~$0.005 each |
| SQS, SNS, Lambda, S3, CloudWatch | ≈ $0 at this volume |
| **Running total** | **≈ $0.09 per hour** |

The nightly Lambda auto-stop means the stack only costs money while it's being used. A full working
day costs well under $1, so the $50 credit covers the whole project with a large margin.
**Credit actually used:** by 25 Nov 2026, after all development, three load tests and the CI/CD
deployments, the Learner Lab page shows **$3.90 of the $50** used, under 8 % *(Figure 37)*. The
`feastflow-monthly` budget ($50) is healthy with its alert threshold OK *(Figure 36)*.

## 9. Conclusion
FeastFlow runs end to end on AWS: customers order through a load balancer, orders go through SQS to
workers on every instance, riders are assigned safely even with several workers, and customers get
SNS emails. Under a festival rush, **Prime customers were served about 3 times faster** than standard
customers without starving anyone, and the system **scaled out automatically** when CPU passed 60 %
and **scaled back in** when traffic dropped. Monitoring, alerts, a budget and a nightly auto-stop keep it
observable and cheap.

**Possible improvements:** HTTPS with a domain and certificate (ACM), Multi-AZ RDS for high
availability, scaling on queue depth as well as CPU, and SMS notifications.

## Appendix A: Application screenshots (live AWS deployment, 21 Nov 2026)

All captured from the site served by the ALB (`http://feastflow-alb-….elb.amazonaws.com`).

### Customer side
**Figure 1: Home page, restaurant list**
![Home](screenshots/01-home.png)

**Figure 2: Restaurant menu; dish photos are served from the private S3 bucket through presigned URLs**
![Menu](screenshots/02-menu.png)

**Figure 3: Cart and checkout**
![Cart](screenshots/03-cart.png)

**Figure 4: Order delivered: live timeline Placed → Confirmed → Preparing → Finding rider → On the way →
Delivered, with the rider assigned automatically (the order went through SQS and the worker)**
![Order delivered](screenshots/04-order-delivered.png)

**Figure 5: Prime offer page**
![Prime offer](screenshots/06a-prime-offer.png)

**Figure 6: Prime active**
![Prime active](screenshots/06-prime.png)

**Figure 7: Checkout as a Prime member: "Prime priority is on"**
![Prime checkout](screenshots/07-prime-checkout.png)

**Figure 8: My orders**
![My orders](screenshots/07b-my-orders.png)

### Admin / dispatch side
**Figure 9: Dispatch board**
![Admin board](screenshots/08-admin-board.png)

**Figure 10: Delivery partners**
![Partners](screenshots/09-partners.png)

**Figure 11: Menu management (prices, availability, photo upload to S3)**
![Admin menu](screenshots/09b-admin-menu.png)

**Figure 12: Customers**
![Customers](screenshots/09c-customers.png)

**Figure 13: Festival page: order burst and Locust load generator controls**
![Festival page](screenshots/09d-festival-page.png)

### Festival order burst (300 orders, 60 s, 30 % Prime, 20 riders)
**Figure 14: Dispatch board during the burst: all 20 riders busy, Prime orders first in "Waiting for rider"**
![Burst board](screenshots/10-burst-board.png)

**Figure 15: Burst progress**
![Burst progress](screenshots/10b-burst-progress.png)

**Figure 16: Prime vs standard during the burst: Prime waited 46.7 s for a rider, standard 1 min 40 s**
![Prime vs standard](screenshots/11-prime-vs-standard.png)

**Figure 17: Festival runs history: run #3 (25 Nov, 5,000 orders, 35 % Prime) in progress, with the two completed 300-order runs from 21 Nov below it. Each run records the instance that ran it**
![Festival runs](screenshots/11b-festival-runs.png)

## Appendix B: AWS Console screenshots
Taken on 25 Nov 2026 during the third load test (section 7.3). The console header shows the Learner
Lab identity. The CloudWatch dashboard is in UTC (IST = UTC + 5:30); all other times are IST.

### Load test, auto scaling and load balancing
**Figure 18: Locust load generator just after Start: 50 users, 27 requests/s, p95 91 ms, 0 failures**
![Locust running](screenshots/12-locust-running.png)

**Figure 19: CloudWatch dashboard early in the run (about 01:45 IST): CPU rising on the single instance and requests climbing on the ALB**
![Dashboard early](screenshots/13-dashboard-cpu.png)

**Figure 20: ASG activity history. Top row: `start.sh` raises the desired capacity 0 → 1 at 01:27 on 25 Nov. Below it, the scale-in from the 22 Nov run: the target-tracking low-CPU alarm reduced desired capacity 3 → 2 at 01:25 and 2 → 1 at 01:27, then `stop.sh` set it to 0 at 01:29**
![ASG activity](screenshots/14-asg-scale-out.png)

**Figure 21: Target group `feastflow-tg` after scale-out: 2 healthy targets in two Availability Zones (us-east-1a and us-east-1b)**
![Healthy targets](screenshots/15-targets-healthy.png)

**Figure 22: Load balancing: 10 requests to `/api/health` through the ALB are answered by two different instances**
![Load balancing](screenshots/16-load-balancing.png)

**Figure 23: Admin Cloud & cost panel during the rush (01:54): 3 of max 4 servers in service, CPU around the 60 % target line, servers stepping up 1 → 2 → 3, current cost $0.125 per hour**
![Cloud panel](screenshots/29-cloud-panel.png)

**Figure 24: CloudWatch dashboard for the whole run: CPU peaks at about 75 % (20:10-20:25 UTC), instances in service go 1 → 2 → 3 and back to 1, ALB requests rise and fall with the rush, and SQS queues drain**
![Dashboard full](screenshots/18-dashboard-full.png)

**Figure 25: ASG self-healing after the test: when the ALB health check failed on an instance, the group terminated it and launched a replacement automatically (03:06 and 03:12)**
![ASG health replacement](screenshots/17-asg-scale-in.png)

### Messaging and notifications
**Figure 26: SNS email subscription confirmation for the `order-notifications` topic**
![SNS email](screenshots/05-sns-email.png)

**Figure 27: SQS queues: `orders-prime` and `orders-standard`, each with a dead-letter queue, encrypted with SSE-SQS**
![SQS](screenshots/19-sqs.png)

**Figure 28: SNS topics: `order-notifications` (customer emails) and `feastflow-alerts` (alarm emails). `RedshiftSNS` belongs to the Learner Lab, not FeastFlow**
![SNS](screenshots/20-sns.png)

### Data and storage
**Figure 29: RDS `feastflow-db`: MySQL on db.t3.micro, Available, 5 connections**
![RDS](screenshots/21-rds.png)

**Figure 30: S3 assets bucket, `menu/` folder with the dish images (20 objects)**
![S3](screenshots/22-s3.png)

**Figure 31: ECR repository `feastflow`: images tagged with their git commit by the CI/CD pipeline (`50234d0`, `latest`, `90caa95`)**
![ECR](screenshots/23-ecr.png)

### Monitoring
**Figure 32: CloudWatch alarms: all 9 FeastFlow alarms OK (0 in alarm) across ELB, RDS, SQS, EC2 and the CloudWatch agent**
![Alarms](screenshots/24-alarms.png)

**Figure 33: CloudWatch log group `/feastflow/app`: separate API and worker log streams for every instance**
![Logs](screenshots/25-logs.png)

### Cost control
**Figure 34: Lambda `feastflow-auto-stop`, triggered by EventBridge Scheduler**
![Lambda](screenshots/26a-lambda-scheduler.png)

**Figure 35: EventBridge schedule `feastflow-nightly-stop`: enabled, runs at 23:00 in the Asia/Kolkata time zone**
![Scheduler](screenshots/26b-lambda-scheduler.png)

**Figure 36: AWS Budget `feastflow-monthly`: $50 per month, healthy, alert threshold OK**
![Budget](screenshots/27-budget.png)

**Figure 37: Learner Lab credit: $3.90 of $50 used**
![Credit used](screenshots/28-credit-used.png)
