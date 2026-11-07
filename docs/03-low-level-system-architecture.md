# 03 – Low-Level System Architecture

## 3.1 Runtime view of one application instance

```mermaid
flowchart TB
    ALB["Application Load Balancer"] -->|"HTTP 8000"| GUN

    subgraph EC2["EC2 instance - Amazon Linux 2023 - t3.micro"]
        UD["User data at boot<br/>install Docker and CW agent<br/>ECR login, docker run"]
        IMDS["IMDSv2<br/>instance-id, AZ, role credentials"]
        CWA["CloudWatch agent<br/>mem_used_percent, disk_used_percent"]

        subgraph DOCKER["Docker container feastflow-app"]
            ENT["entrypoint.sh<br/>alembic upgrade head under advisory lock"]
            GUN["Gunicorn master<br/>2 Uvicorn workers"]

            subgraph FASTAPI["FastAPI application"]
                MW["Middleware<br/>request-id, X-Served-By, timing, JSON access log, error handler"]
                STATIC["Static files<br/>React build with SPA fallback"]
                subgraph ROUTERS["Routers under /api/v1"]
                    R_AUTH["auth"]
                    R_MENU["menu"]
                    R_ORD["orders"]
                    R_ADM["admin orders and users"]
                    R_CLOUD["admin cloud, load-tests, costs, reports"]
                    R_HEALTH["health"]
                end
                DEPS["Dependencies<br/>get_db session, get_current_user, require_admin"]
                subgraph SERVICES["Services"]
                    S_AUTH["AuthService<br/>bcrypt, JWT HS256"]
                    S_ORDER["OrderService<br/>pricing, atomic create"]
                    S_QUEUE["QueueService<br/>priority ordering, SKIP LOCKED claim, transitions"]
                    S_LT["LoadTestService<br/>Locust HTTP client"]
                    S_MET["MetricsService<br/>boto3 with 30 s cache"]
                    S_COST["CostService<br/>rate table x usage"]
                    S_S3["StorageService<br/>S3 put, presigned URLs"]
                end
                REPO["SQLAlchemy 2.0 models and repositories<br/>pool size 5, max overflow 2 per worker"]
            end
        end
    end

    GUN --> MW
    MW --> STATIC
    MW --> ROUTERS
    ROUTERS --> DEPS
    DEPS --> SERVICES
    S_AUTH --> REPO
    S_ORDER --> REPO
    S_QUEUE --> REPO
    S_LT --> REPO
    S_COST --> REPO
    REPO -->|"psycopg 3, port 5432"| RDS[("RDS PostgreSQL")]
    S_MET -->|"GetMetricData, DescribeAutoScalingGroups,<br/>DescribeScalingActivities, DescribeTargetHealth,<br/>DescribeAlarms"| AWSAPI["CloudWatch, Auto Scaling, ELBv2 APIs"]
    S_S3 -->|"PutObject, GetObject"| S3[("Amazon S3")]
    S_LT -->|"POST /swarm, GET /stop,<br/>GET /stats/requests"| LOC["Locust EC2 port 8089"]
    CWA -->|"PutMetricData"| CW["CloudWatch"]
    DOCKER -->|"awslogs driver"| CWL["CloudWatch Logs<br/>/feastflow/app"]
    MW -.->|"read once at startup"| IMDS
    SERVICES -.->|"credentials"| IMDS
    UD --> ENT
    ENT --> GUN
```

## 3.2 Frontend (React SPA) structure

```mermaid
flowchart LR
    subgraph SPA["React SPA - Vite build"]
        ROUTER["React Router"]
        AUTHCTX["AuthContext<br/>JWT, user, role, tier"]
        APICLIENT["api client<br/>fetch wrapper, bearer token, error mapping"]
        subgraph CUSTOMER["Customer pages"]
            P_LOGIN["Login and Register"]
            P_MENU["Menu and Cart"]
            P_ORDERS["My Orders"]
            P_PROFILE["Profile and Plan"]
        end
        subgraph ADMIN["Admin pages - require ADMIN"]
            P_QUEUE["Order Queue"]
            P_ALL["All Orders and History"]
            P_LOAD["Load Tests"]
            P_DASH["Cloud Dashboard"]
            P_COST["Costs and Reports"]
            P_USERS["Users and Tiers"]
        end
    end
    ROUTER --> AUTHCTX
    ROUTER --> CUSTOMER
    ROUTER --> ADMIN
    CUSTOMER --> APICLIENT
    ADMIN --> APICLIENT
    APICLIENT -->|"same origin /api/v1"| ALB["ALB"]
```

## 3.3 Network and security boundaries

```mermaid
flowchart LR
    NET["Internet"] -->|"80"| SGALB["sg-alb<br/>ALB"]
    SGALB -->|"8000"| SGAPP["sg-app<br/>ASG instances"]
    SGAPP -->|"5432"| SGRDS["sg-rds<br/>RDS PostgreSQL"]
    SGAPP -->|"8089"| SGLOC["sg-locust<br/>Locust EC2"]
    SGLOC -->|"80 via public ALB DNS"| SGALB
    SGAPP -->|"HTTPS 443 AWS APIs"| AWSPUB["S3, ECR, CloudWatch,<br/>Auto Scaling, ELBv2, SSM"]
```

## 3.4 Key low-level decisions

| Topic | Decision | Reason |
|---|---|---|
| Process model | Gunicorn + 2 Uvicorn workers per t3.micro (2 vCPU, 1 GiB) | Uses both vCPUs within memory limits |
| DB connections | Per worker: pool 5 + overflow 2 = 7. Per instance: 14. At max 4 instances: **56**. db.t3.micro allows about 80–110. | Prevents connection exhaustion during festival scale-out (NFR-01) |
| Migrations | `alembic upgrade head` in entrypoint, wrapped in `pg_advisory_lock` | Several instances can boot at once, and the pipeline can't reach the private RDS |
| Health checks | `/api/health` = liveness (no DB), used by the ALB. `/api/health/ready` = DB ping, used by dashboard and smoke test. | A brief DB outage won't make the ASG terminate every instance |
| Instance identity | Read `instance-id` and `placement/availability-zone` via IMDSv2 once at startup, return in `X-Served-By` and `/api/health` | Demonstrates load distribution (AC-02) |
| Version | `GIT_SHA` build arg baked into image env, returned by `/api/health` | CD smoke test verifies the new version is live (AC-03) |
| AWS API usage | All boto3 reads cached in-process for 30 s | Limits throttling and GetMetricData cost when multiple admins poll |
| Logging | JSON lines to stdout (`ts, level, request_id, instance_id, method, path, status, latency_ms, user_id`). Docker `awslogs` sends them to `/feastflow/app`. | NFR-06, troubleshooting by request-id |
| Secrets | DB password and JWT secret come from SSM Parameter Store at boot **[OPTIONAL]**. Fallback is launch-template user-data env. | Learner Lab simplicity vs hygiene |
| Config | 12-factor env vars: `DATABASE_URL`, `JWT_SECRET`, `S3_BUCKET`, `ASG_NAME`, `TARGET_GROUP_ARN`, `ALB_ARN_SUFFIX`, `LOCUST_URL`, `AWS_REGION` | Same image for every environment |
