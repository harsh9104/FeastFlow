# 06 – API Request & Response Workflow

## 6.1 Generic request lifecycle (every `/api/v1` call)

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser or Locust
    participant ALB as Application Load Balancer
    participant MW as FastAPI middleware
    participant DEP as Auth dependency
    participant H as Route handler
    participant SVC as Service layer
    participant DB as RDS PostgreSQL

    B->>ALB: HTTP request with Authorization Bearer JWT
    ALB->>MW: Forward to healthy target on port 8000
    MW->>MW: Assign X-Request-ID, start timer
    MW->>DEP: Resolve dependencies
    alt Missing or invalid JWT
        DEP-->>B: 401 Unauthorized error body
    else Role not allowed for route
        DEP-->>B: 403 Forbidden error body
    else Authorized
        DEP->>H: current_user with role and tier
        H->>H: Validate body with Pydantic
        alt Validation fails
            H-->>B: 422 Unprocessable Entity with field errors
        else Valid
            H->>SVC: Call business logic
            SVC->>DB: Query or transaction via pooled connection
            DB-->>SVC: Rows
            SVC-->>H: Domain result
            H-->>MW: Response model
            MW->>MW: Add X-Served-By instance-id and X-Request-ID, write JSON access log
            MW-->>ALB: 2xx JSON
            ALB-->>B: 2xx JSON
        end
    end
```

## 6.2 Sign in (FR-01, NFR-04)

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant API as FastAPI auth router
    participant AS as AuthService
    participant DB as RDS PostgreSQL

    B->>API: POST /api/v1/auth/login with email and password
    API->>AS: authenticate
    AS->>DB: SELECT user by lowercased email
    DB-->>AS: user row or none
    alt User not found or bcrypt check fails
        AS-->>API: invalid credentials
        API-->>B: 401 INVALID_CREDENTIALS
    else Valid
        AS->>AS: Sign JWT HS256 with sub, role, tier, exp 60 min
        AS-->>API: token and user
        API-->>B: 200 access_token, token_type bearer, user profile
    end
```

## 6.3 Place order (FR-02, FR-05, FR-06, NFR-05)

```mermaid
sequenceDiagram
    autonumber
    participant B as Customer browser
    participant API as Orders router
    participant OS as OrderService
    participant DB as RDS PostgreSQL

    B->>API: POST /api/v1/orders with items and optional Idempotency-Key
    API->>OS: create_order for current_user
    OS->>DB: BEGIN
    opt Idempotency-Key supplied
        OS->>DB: SELECT order by user_id and key
        DB-->>OS: existing order returns 200 with same body
    end
    OS->>DB: SELECT id, price, is_available FROM menu_items WHERE id IN requested ids
    DB-->>OS: menu rows
    alt Any item missing or unavailable
        OS->>DB: ROLLBACK
        API-->>B: 422 ITEM_UNAVAILABLE
    else All valid
        OS->>OS: priority = 1 if tier is PREMIUM else 0, compute totals server-side
        OS->>DB: INSERT orders status PENDING with priority and tier_at_order
        OS->>DB: INSERT order_items with price snapshots
        OS->>DB: INSERT order_status_history from NULL to PENDING
        OS->>DB: COMMIT
        OS-->>API: order
        API-->>B: 201 Created with order id, status, priority, items, total
    end
```

## 6.4 Admin claims next order & updates status (FR-03, FR-04, FR-05, NFR-05)

```mermaid
sequenceDiagram
    autonumber
    participant A1 as Admin 1
    participant A2 as Admin 2 on another instance
    participant API as Admin orders router
    participant QS as QueueService
    participant DB as RDS PostgreSQL

    A1->>API: POST /api/v1/admin/orders/queue/next
    A2->>API: POST /api/v1/admin/orders/queue/next
    API->>QS: claim_next for admin 1
    API->>QS: claim_next for admin 2
    QS->>DB: BEGIN then SELECT PENDING ORDER BY priority DESC, created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED
    Note over QS,DB: Admin 2 skips the row locked by Admin 1 and gets the next one
    QS->>DB: UPDATE status PREPARING, version plus 1, preparing_at now
    QS->>DB: INSERT history PENDING to PREPARING, COMMIT
    alt Queue empty
        API-->>A1: 204 No Content
    else Claimed
        API-->>A1: 200 order now PREPARING
        API-->>A2: 200 different order now PREPARING
    end

    A1->>API: PATCH /api/v1/admin/orders/42/status with status COMPLETED and version 2
    API->>QS: transition
    QS->>DB: UPDATE orders SET status COMPLETED, version 3 WHERE id 42 AND status PREPARING AND version 2
    alt 0 rows updated
        QS-->>API: conflict
        API-->>A1: 409 INVALID_TRANSITION or STALE_VERSION
    else 1 row updated
        QS->>DB: INSERT history PREPARING to COMPLETED, COMMIT
        API-->>A1: 200 updated order
    end
```

## 6.5 Launch load-test scenario (FR-07)

```mermaid
sequenceDiagram
    autonumber
    participant A as Admin browser
    participant API as Load-test router
    participant LS as LoadTestService
    participant DB as RDS PostgreSQL
    participant L as Locust EC2 port 8089
    participant ALB as ALB and ASG fleet
    participant CW as CloudWatch

    A->>API: POST /api/v1/admin/load-tests with scenario FESTIVAL
    API->>LS: start
    LS->>DB: INSERT run RUNNING with users, spawn rate, duration
    Note over DB: Partial unique index allows only one RUNNING row
    alt Unique violation, a run is already active
        API-->>A: 409 LOAD_TEST_ALREADY_RUNNING
    else Inserted
        LS->>L: POST /swarm with user_count, spawn_rate, host ALB DNS, run_time
        alt Locust unreachable
            LS->>DB: UPDATE run FAILED
            API-->>A: 503 LOAD_GENERATOR_UNAVAILABLE
        else Started
            API-->>A: 202 Accepted with run id
            L->>ALB: Simulated customer traffic
        end
    end

    loop Every 5 s while page open
        A->>API: GET /api/v1/admin/load-tests/run-id
        API->>LS: get status
        LS->>L: GET /stats/requests
        L-->>LS: live rps, failures, latency percentiles
        API-->>A: 200 live stats
    end

    Note over LS: Lazy finalization when now is past started_at plus duration, done by whichever instance serves the next poll, guarded by row lock
    LS->>L: GET /stats/requests final
    LS->>CW: GetMetricData for CPU, instance count, latency in run window
    LS->>LS: Estimate run cost
    LS->>DB: UPDATE run COMPLETED with summary
    LS->>LS: Write JSON and CSV report to S3 and INSERT reports row
```

## 6.6 Cloud dashboard metrics (FR-10, FR-11)

```mermaid
sequenceDiagram
    autonumber
    participant A as Admin browser
    participant API as Cloud router
    participant MS as MetricsService
    participant C as In-process cache 30 s
    participant AWS as CloudWatch, Auto Scaling, ELBv2

    A->>API: GET /api/v1/admin/cloud/metrics?range=1h
    API->>MS: get_metrics
    MS->>C: lookup key metrics 1h
    alt Cache hit
        C-->>MS: cached series
    else Cache miss
        MS->>AWS: GetMetricData CPU, mem_used_percent, RequestCount, TargetResponseTime, 5XX, HealthyHostCount, GroupInServiceInstances
        AWS-->>MS: time series
        MS->>C: store for 30 s
    end
    MS-->>API: series
    API-->>A: 200 metrics JSON
```

## 6.7 Response conventions

**Success**: resource or list.

```json
{ "items": [ { "id": 101, "status": "PENDING", "priority": 1 } ], "page": 1, "page_size": 20, "total": 134 }
```

**Error**: same shape for every non-2xx.

```json
{
  "error": { "code": "INVALID_TRANSITION", "message": "Order 42 cannot move from COMPLETED to PREPARING", "details": null },
  "request_id": "6f1c2e7a-..."
}
```

**Headers on every response:** `X-Request-ID`, `X-Served-By: i-0abc123 (us-east-1a)`.

| HTTP | When |
|---|---|
| 200 / 201 / 202 / 204 | OK / created / async started (load test) / empty queue |
| 401 | Missing, expired or invalid JWT, or bad credentials |
| 403 | Authenticated but wrong role (customer calling `/admin/*`) |
| 404 | Resource not found, or a customer requesting another user's order (no existence leak) |
| 409 | Duplicate email, invalid status transition, stale version, load test already running |
| 422 | Request validation failure, unavailable menu item |
| 503 | DB unreachable (`/health/ready`), Locust unreachable |
| 500 | Unhandled. Logged with request-id, generic message returned. |
