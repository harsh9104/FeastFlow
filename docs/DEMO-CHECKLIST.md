# FeastFlow demo: test and screenshot checklist

Do these in order, in one sitting (about 1 hour 15 min, most of it waiting).
Use **Microsoft Edge**. Save each screenshot with the name in **bold** (e.g. `01-home.png`) into
`docs/screenshots/`; the report (`docs/REPORT.md`) points to these names.

Site: **http://feastflow-alb-2114225444.us-east-1.elb.amazonaws.com**
Admin login: `admin@feastflow.app`, password = `ADMIN_PASSWORD` in `infra/.state.env`.

---

## 0. Start everything (10-15 min, once)
1. Learner Lab → **Start Lab**, wait for the green dot.
2. **AWS Details → AWS CLI → Show**, copy the block into `C:\Users\Harsh Shah\.aws\credentials`.
3. Open **Git Bash**, then:
   ```bash
   cd /d/Harsh/Projects/FeastFlow/infra/scripts
   ./start.sh
   ```
4. Wait ~10 min (RDS starts first, then the app). The site opens when it's ready.

> Or ask Claude: "start the stack and tell me when the site is up".

---

## 1. The website (customer side) - 5 min
| Do | Screenshot |
|---|---|
| Open the site | **01-home.png** (restaurant list) |
| Click a restaurant | **02-menu.png** (dishes with photos, these come from S3) |
| **Register** a new customer with your real email, add 2 dishes, open the cart | **03-cart.png** |
| Place the order. Wait ~1 min on the order page until it says Delivered | **04-order-delivered.png** (timeline + rider name) |
| Open your email inbox: confirm the AWS subscription email, then you get order emails on the next orders | **05-sns-email.png** |

## 2. Prime - 3 min
| Do | Screenshot |
|---|---|
| Click **Prime** → join | **06-prime.png** (Prime badge) |
| Place another order. At checkout it says "Prime priority is on" | **07-prime-checkout.png** |

## 3. Admin dashboard - 3 min
Log out, log in as the admin (incognito window is easiest).
| Do | Screenshot |
|---|---|
| Open **Dispatch** board | **08-admin-board.png** |
| Open **Partners** | **09-partners.png** |

## 4. Festival order burst (Prime priority under rush) - 5 min
| Do | Screenshot |
|---|---|
| Admin → **Festival** → Order burst: **300** orders, **60** s, **30** % Prime → Start | |
| After ~1 min, open the Dispatch board: many orders, all riders busy, Prime on top | **10-burst-board.png** |
| On the Festival / Dispatch page, the **Prime vs Standard wait time** numbers | **11-prime-vs-standard.png** (Prime waits much less) |

## 5. Load test + auto scaling + load balancing - 25 min (the main demo)
| Do | Screenshot |
|---|---|
| Admin → **Festival** → Load generator → **festival** → Start | **12-locust-running.png** (users, requests/s) |
| Open the CloudWatch dashboard (link below). Wait ~8-10 min | **13-dashboard-cpu.png** (CPU above the 60 % line) |
| AWS Console → **EC2 → Auto Scaling Groups → feastflow-asg → Activity** | **14-asg-scale-out.png** ("Launching a new EC2 instance") |
| **EC2 → Target Groups → feastflow-tg → Targets**: 2-4 rows, all healthy | **15-targets-healthy.png** |
| **Load balancing proof**: open `/api/health` on the site and press F5 a few times, the `instance` value changes. Or in Git Bash run the line below | **16-load-balancing.png** |
| The rush ends ~14 min after Start. About 13 min later the instances go back to 1 | **17-asg-scale-in.png** (Activity: "Terminating") and **18-dashboard-full.png** |
| During the rush, Admin → **Cloud & cost**: 2-3 servers, CPU chart above the dashed 60 % line, "Launching a new EC2 instance" in Scaling activity, cost per hour | **29-cloud-panel.png** |
| **Then clean up** the thousands of load-test orders (Git Bash): `./clear-test-orders.sh` | (no screenshot) |

What to expect (measured on 21 Nov): scale-out to 2 about 5 min after Start, to 3 about 8 min after
Start, ~0.2 % failed requests, then 3 → 2 → 1 about 13-15 min after the rush ends.

Load-balancing line (Git Bash):
```bash
for i in $(seq 10); do curl -s http://feastflow-alb-2114225444.us-east-1.elb.amazonaws.com/api/health; echo; done
```
CloudWatch dashboard:
https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=FeastFlow

## 6. Other AWS proof (do these while waiting in step 5) - 10 min
| Where in the AWS Console | Screenshot |
|---|---|
| **SQS** → queues list (orders-prime, orders-standard + DLQs, message counts) | **19-sqs.png** |
| **SNS** → Topics → order-notifications / feastflow-alerts | **20-sns.png** |
| **RDS** → Databases → feastflow-db (Available) | **21-rds.png** |
| **S3** → feastflow-…-assets → `menu/` folder with photos | **22-s3.png** |
| **ECR** → feastflow repository (images) | **23-ecr.png** |
| **CloudWatch → Alarms** (9 feastflow alarms) | **24-alarms.png** |
| **CloudWatch → Log groups → /feastflow/app** (API and worker logs) | **25-logs.png** |
| **Lambda** → feastflow-auto-stop + **EventBridge Scheduler** → feastflow-nightly-stop | **26-lambda-scheduler.png** |
| **Billing → Budgets** → feastflow-monthly | **27-budget.png** |
| Learner Lab page: remaining credit | **28-credit-used.png** |

## 7. Finish
1. Run `./stop.sh` in Git Bash (or just leave it: the Lambda stops everything at 23:00 IST).
2. Tell Claude "screenshots done" to put the measured numbers into the report and push to GitHub.
3. **After grading only**: `CONFIRM=yes ./99-teardown.sh` deletes everything.
