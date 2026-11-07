# 04 – Complete Project Flowchart

This doc has five parts: (1) the end-to-end overview, (2) the customer workflow, (3) the admin workflow, (4) the cloud workflows (scaling, monitoring, CI/CD), and (5) the order status state machine.

## 4.1 End-to-end overview

```mermaid
flowchart LR
    S0(["User opens FeastFlow URL"]) --> ALB["ALB routes to healthy EC2"]
    ALB --> AUTH{"Signed in?"}
    AUTH -->|"No"| LOGIN["Register or sign in"]
    LOGIN --> AUTH
    AUTH -->|"Yes"| ROLE{"Role?"}
    ROLE -->|"CUSTOMER"| CFLOW["Customer workflow<br/>browse, order, track"]
    ROLE -->|"ADMIN"| AFLOW["Admin workflow<br/>queue, status, load tests,<br/>dashboard, costs"]
    CFLOW --> DB[("RDS PostgreSQL")]
    AFLOW --> DB
    AFLOW -->|"launch scenario"| LOCUST["Locust traffic"]
    LOCUST --> ALB
    ALB --> CWM["CloudWatch metrics"]
    CWM --> SCALE{"CPU above or below 50 % target?"}
    SCALE -->|"above"| SOUT["ASG scales out"]
    SCALE -->|"below for 15 min"| SIN["ASG scales in"]
    SOUT --> ALB
    SIN --> ALB
    CWM --> AFLOW
```

## 4.2 Customer workflow

```mermaid
flowchart TD
    C0(["Customer visits site"]) --> C1{"Has account?"}
    C1 -->|"No"| C2["Register: name, email, password,<br/>plan FREE or PREMIUM"]
    C2 --> C3{"Valid and email unique?"}
    C3 -->|"No"| C2
    C3 -->|"Yes"| C4["Account created, role CUSTOMER"]
    C1 -->|"Yes"| C5["Sign in"]
    C4 --> C5
    C5 --> C6{"Credentials valid?"}
    C6 -->|"No"| C5
    C6 -->|"Yes"| C7["JWT issued, stored in client"]
    C7 --> C8["Browse menu"]
    C8 --> C9["Add items to cart"]
    C9 --> C10["Submit order"]
    C10 --> C11{"Items available and qty 1 to 20?"}
    C11 -->|"No"| C9
    C11 -->|"Yes"| C12["Server prices items and snapshots<br/>priority from subscription tier"]
    C12 --> C13["Single DB transaction:<br/>order, order items, history PENDING"]
    C13 --> C14["Order confirmation with<br/>order id and priority"]
    C14 --> C15["My Orders: view status<br/>PENDING, PREPARING, COMPLETED"]
    C15 --> C16{"Upgrade plan?"}
    C16 -->|"Yes"| C17["Toggle to PREMIUM - simulated, no payment<br/>applies to future orders"]
    C17 --> C8
    C16 -->|"No"| C18(["Done"])
```

## 4.3 Admin workflow

```mermaid
flowchart TD
    A0(["Admin signs in"]) --> A1{"role is ADMIN?"}
    A1 -->|"No"| A2["403 Forbidden"]
    A1 -->|"Yes"| A3["Admin home"]
    A3 --> Q["Order Queue"]
    A3 --> LT["Load Tests"]
    A3 --> DSH["Cloud Dashboard"]
    A3 --> CST["Costs and Reports"]

    Q --> Q1["View PENDING orders<br/>Premium first, then oldest first"]
    Q1 --> Q2{"Action"}
    Q2 -->|"Start next"| Q3["Claim head of queue<br/>FOR UPDATE SKIP LOCKED"]
    Q2 -->|"Update specific order"| Q4["PATCH status"]
    Q3 --> Q5{"Transition valid and<br/>version unchanged?"}
    Q4 --> Q5
    Q5 -->|"No"| Q6["409 Conflict, refresh queue"]
    Q5 -->|"Yes"| Q7["Status updated and history row written"]
    Q7 --> Q1

    LT --> L1{"Choose scenario"}
    L1 -->|"Normal day"| L2["25 users, spawn 5 per s, 10 min"]
    L1 -->|"Festival day"| L3["Ramp to 250 users, spawn 10 per s, 15 min"]
    L2 --> L4{"Another run active?"}
    L3 --> L4
    L4 -->|"Yes"| L5["409 already running"]
    L4 -->|"No"| L6["Insert run RUNNING, call Locust swarm"]
    L6 --> L7["Watch live stats, instances, scaling events"]
    L7 --> L8["Run ends: collect Locust and CloudWatch stats,<br/>estimate cost, save report to S3"]

    DSH --> D1["CPU, memory, requests, latency, 5xx,<br/>healthy hosts, scaling activity, alarms"]
    CST --> K1["Estimated cost by period and by run"]
    K1 --> K2["Generate cost report, store in S3,<br/>download via presigned URL"]
    L8 --> K1
```

## 4.4 Cloud workflows

### 4.4.1 Auto scaling and monitoring

```mermaid
flowchart TD
    T0(["Traffic arrives at ALB"]) --> T1["ALB distributes to InService healthy targets"]
    T1 --> T2["Instances publish CPU via detailed monitoring,<br/>memory via CloudWatch agent"]
    T2 --> T3["CloudWatch evaluates target tracking<br/>ASG avg CPU target 50 %"]
    T3 --> T4{"CPU vs target"}
    T4 -->|"Above for 3 min"| T5{"Desired below max 4?"}
    T5 -->|"Yes"| T6["Launch instance from launch template"]
    T6 --> T7["User data: pull image from ECR, run container"]
    T7 --> T8{"ALB health check /api/health passes?"}
    T8 -->|"Yes"| T9["Register as healthy, receives traffic"]
    T8 -->|"No, after grace period"| T10["ASG replaces instance"]
    T10 --> T6
    T5 -->|"No"| T11["Stay at max, latency alarm may fire"]
    T4 -->|"Below for 15 min"| T12{"Desired above min 2?"}
    T12 -->|"Yes"| T13["Deregister with 30 s drain, terminate"]
    T12 -->|"No"| T14["Hold at min"]
    T4 -->|"Near target"| T14
    T2 --> T15{"Alarm threshold breached?<br/>5xx, latency, unhealthy, memory, RDS CPU"}
    T15 -->|"Yes"| T16["Alarm state ALARM, shown on dashboard,<br/>SNS email optional"]
    T15 -->|"No"| T17["OK"]
```

### 4.4.2 CI/CD pipeline

```mermaid
flowchart TD
    G0(["Developer pushes or opens PR"]) --> G1["GitHub Actions: CI job"]
    G1 --> G2["Backend: ruff lint, pytest with Postgres service"]
    G1 --> G3["Frontend: npm ci, lint, build"]
    G2 --> G4{"All checks pass?"}
    G3 --> G4
    G4 -->|"No"| G5(["Fail, block merge"])
    G4 -->|"Yes"| G6{"Branch is main?"}
    G6 -->|"No, PR only"| G7(["Report status on PR"])
    G6 -->|"Yes"| G8["Configure AWS creds from<br/>Learner Lab session secrets"]
    G8 --> G9["Docker multi-stage build<br/>tag with git SHA and latest"]
    G9 --> G10["Push to Amazon ECR"]
    G10 --> G11["ASG start-instance-refresh<br/>MinHealthyPercentage 50"]
    G11 --> G12["New instances pull new image,<br/>old ones drained and terminated"]
    G12 --> G13{"Refresh Successful?"}
    G13 -->|"No"| G14(["Fail job, rollback by retagging<br/>previous SHA as latest and refreshing"])
    G13 -->|"Yes"| G15["Smoke test: GET /api/health<br/>version equals git SHA"]
    G15 --> G16(["Deployment evidence for AC-03"])
```

## 4.5 Order status state machine (FR-04)

```mermaid
stateDiagram-v2
    [*] --> PENDING : customer submits order
    PENDING --> PREPARING : admin starts order or claims next
    PREPARING --> COMPLETED : admin marks completed
    COMPLETED --> [*]
```

Only forward transitions are allowed. Any other transition, such as `COMPLETED → PENDING` or skipping straight to `PENDING → COMPLETED`, returns **409 Conflict**.
