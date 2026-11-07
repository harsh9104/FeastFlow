# 09 – API Endpoints (Task 3)

Base path: `/api/v1` (health endpoints are unversioned under `/api`). JSON only. Auth is `Authorization: Bearer <JWT>`.
Auth column: **Public**, **Customer** (role CUSTOMER), **Admin** (role ADMIN), **Any** (any signed-in user).

## 9.1 Health (NFR-06)

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/health` | Public | `200 {status:"ok", version, instance_id, az, uptime_s}`. Liveness, used by the ALB. |
| GET | `/api/health/ready` | Public | `200 {status:"ready", db:"ok"}` or `503`. DB ping. |

## 9.2 Auth & Users (FR-01, NFR-04)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/auth/register` | Public | `{full_name, email, password (min 8), subscription_tier: FREE or PREMIUM}` | `201 {user}`, `409 EMAIL_TAKEN` |
| POST | `/auth/login` | Public | `{email, password}` | `200 {access_token, token_type:"bearer", expires_in, user}`, `401` |
| GET | `/users/me` | Any | — | `200 {id, full_name, email, role, subscription_tier}` |
| PATCH | `/users/me/subscription` | Customer | `{subscription_tier}` | `200 {user}`. Simulated, no payment (A-01). |
| GET | `/admin/users` | Admin | `?tier=&page=&page_size=` | `200 {items, page, page_size, total}` |
| PATCH | `/admin/users/{id}/subscription` | Admin | `{subscription_tier}` | `200 {user}` |

## 9.3 Menu (FR-02)

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/menu` | Any | `200 [{id, name, description, category, price, image_url, is_available}]`. `image_url` is an S3 pre-signed URL (cached 10 min). |
| GET | `/menu/{id}` | Any | `200 {item}`, `404` |

Admin menu CRUD is **[OPTIONAL]** and not required by the FRS.

## 9.4 Customer Orders (FR-02, FR-06)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/orders` | Customer | `{items:[{menu_item_id, quantity}], notes?}` + optional header `Idempotency-Key` | `201 {id, status:"PENDING", priority, tier_at_order, items[], total_amount, created_at}`, `422 ITEM_UNAVAILABLE` |
| GET | `/orders` | Customer | `?status=&page=&page_size=` | `200 {items, page, page_size, total}`, own orders only |
| GET | `/orders/{id}` | Customer | — | `200 {order, items, history[], queue_position?}`, `404` if not owner |

`queue_position` (**[OPTIONAL]**) is the 1-based position among PENDING orders, so the customer can see Premium priority.

## 9.5 Admin Orders & Priority Queue (FR-03, FR-04, FR-05)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| GET | `/admin/orders` | Admin | `?status=&priority=&from=&to=&page=` | `200 {items:[{id, customer, status, priority, tier_at_order, total, created_at}], …}` |
| GET | `/admin/orders/queue` | Admin | `?limit=50` | `200 {items}`: PENDING, Premium first then FIFO |
| POST | `/admin/orders/queue/next` | Admin | — | `200 {order}` now PREPARING, or `204` if empty |
| PATCH | `/admin/orders/{id}/status` | Admin | `{status: PREPARING or COMPLETED, version}` | `200 {order}`, `409 INVALID_TRANSITION` or `STALE_VERSION` |
| GET | `/admin/orders/{id}/history` | Admin | — | `200 [{from_status, to_status, changed_by, changed_at}]` |
| GET | `/admin/orders/stats` | Admin | `?from=&to=` | `200 {counts_by_status, avg_wait_premium_s, avg_wait_free_s}`. Proves priority (AC-01). |

## 9.6 Load Tests (FR-07)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| GET | `/admin/load-tests/scenarios` | Admin | — | `200 [{name:"NORMAL", users:25, spawn_rate:5, duration_s:600}, {name:"FESTIVAL", users:250, spawn_rate:10, duration_s:900}]` |
| POST | `/admin/load-tests` | Admin | `{scenario: NORMAL or FESTIVAL}` | `202 {run_id, status:"RUNNING"}`, `409 LOAD_TEST_ALREADY_RUNNING`, `503 LOAD_GENERATOR_UNAVAILABLE` |
| GET | `/admin/load-tests` | Admin | `?page=` | `200 {items}`, run history |
| GET | `/admin/load-tests/{id}` | Admin | — | `200 {run, live_stats?}`. Finalizes lazily when the duration has elapsed. |
| POST | `/admin/load-tests/{id}/stop` | Admin | — | `200 {run status STOPPED}` |
| GET | `/admin/load-tests/compare` | Admin | `?normal_id=&festival_id=` | `200 {normal, festival, deltas}` (AC-04) |

## 9.7 Cloud Dashboard (FR-08..FR-11)

| Method | Path | Auth | Response (all cached 30 s) |
|---|---|---|---|
| GET | `/admin/cloud/metrics` | Admin | `?range=15m,1h,3h,24h`. Series: `cpu_avg`, `mem_used_pct`, `request_count`, `target_response_time_p50/p90`, `http_5xx`, `healthy_hosts`, `unhealthy_hosts`, `in_service_instances`, `rds_cpu`, `rds_connections` |
| GET | `/admin/cloud/instances` | Admin | `[{instance_id, az, lifecycle_state, health_status, target_health, launch_time, type}]` |
| GET | `/admin/cloud/scaling-activities` | Admin | `[{start_time, end_time, status, description, cause}]` (last 20) |
| GET | `/admin/cloud/alarms` | Admin | `[{name, state, reason, updated_at}]` |

## 9.8 Costs & Reports (FR-13, FR-15, NFR-07)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| GET | `/admin/costs/estimate` | Admin | `?from=&to=` or `?run_id=` | `200 {period, line_items:[{service, usage, unit, rate_usd, cost_usd}], total_usd, assumptions}` |
| GET | `/admin/costs/rates` | Admin | — | `200 {region, effective_date, rates}` (from `backend/app/config/aws_rates.json`) |
| POST | `/admin/reports` | Admin | `{report_type: LOAD_TEST, COST or COMPARISON, run_ids?, from?, to?, format}` | `201 {report_id, s3_key}` |
| GET | `/admin/reports` | Admin | — | `200 {items}` |
| GET | `/admin/reports/{id}/download` | Admin | — | `200 {url, expires_in: 300}` (pre-signed S3 GET) |

## 9.9 Example: place order

```http
POST /api/v1/orders
Authorization: Bearer eyJhbGciOi...
Idempotency-Key: 7d3e2c1a-...
Content-Type: application/json

{ "items": [ { "menu_item_id": 3, "quantity": 2 }, { "menu_item_id": 7, "quantity": 1 } ], "notes": "Less spicy" }
```

```http
HTTP/1.1 201 Created
X-Request-ID: 1b6f...
X-Served-By: i-0a1b2c3d4e (us-east-1b)

{ "id": 1042, "status": "PENDING", "priority": 1, "tier_at_order": "PREMIUM",
  "items": [ { "menu_item_id": 3, "name": "Paneer Tikka", "quantity": 2, "unit_price": "8.50", "line_total": "17.00" },
             { "menu_item_id": 7, "name": "Mango Lassi",  "quantity": 1, "unit_price": "3.00", "line_total": "3.00" } ],
  "total_amount": "20.00", "created_at": "2026-11-06T10:15:02Z" }
```

**Total: 34 endpoints** (2 health, 6 auth/users, 2 menu, 3 orders, 6 admin orders, 6 load tests, 4 cloud, 5 cost/reports). FastAPI auto-generates OpenAPI docs at `/api/docs`, restricted to non-production or admin.
