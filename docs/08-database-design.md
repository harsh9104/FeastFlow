# 08 – Database Design: Tables, Relationships, Constraints (Task 3)

PostgreSQL 16. All timestamps are `timestamptz` (UTC). Enums are implemented as `varchar` + `CHECK` constraints, which are easier to migrate than PG enums. Diagram: [05-database-er-diagram.md](05-database-er-diagram.md).

## 8.1 `users` (FR-01, CON-02)

| Column | Type | Constraints |
|---|---|---|
| id | bigint | PK, `GENERATED ALWAYS AS IDENTITY` |
| email | varchar(255) | NOT NULL, UNIQUE (stored lowercased) |
| password_hash | varchar(255) | NOT NULL (bcrypt, cost 12) |
| full_name | varchar(120) | NOT NULL |
| role | varchar(16) | NOT NULL, DEFAULT `'CUSTOMER'`, CHECK in (`CUSTOMER`,`ADMIN`) |
| subscription_tier | varchar(16) | NOT NULL, DEFAULT `'FREE'`, CHECK in (`FREE`,`PREMIUM`) |
| created_at / updated_at | timestamptz | NOT NULL DEFAULT now() |

## 8.2 `menu_items` (FR-02, FR-13)

| Column | Type | Constraints |
|---|---|---|
| id | bigint | PK identity |
| name | varchar(120) | NOT NULL, UNIQUE |
| description | text | |
| category | varchar(50) | NOT NULL |
| price | numeric(10,2) | NOT NULL, CHECK `price > 0` |
| image_key | varchar(255) | S3 key, e.g. `menu/paneer-tikka.jpg` |
| is_available | boolean | NOT NULL DEFAULT true |
| created_at / updated_at | timestamptz | |

Seeded with about 12 items through an Alembic data migration (A-02).

## 8.3 `orders` (FR-02..06)

| Column | Type | Constraints |
|---|---|---|
| id | bigint | PK identity (doubles as order number) |
| user_id | bigint | NOT NULL, FK → users(id) ON DELETE RESTRICT |
| status | varchar(16) | NOT NULL DEFAULT `'PENDING'`, CHECK in (`PENDING`,`PREPARING`,`COMPLETED`) |
| priority | smallint | NOT NULL, CHECK in (0,1): 1 = Premium, 0 = Free (**snapshot at creation**) |
| tier_at_order | varchar(16) | NOT NULL, CHECK in (`FREE`,`PREMIUM`) |
| total_amount | numeric(10,2) | NOT NULL, CHECK ≥ 0. Informational, no payment (CON-03). |
| notes | text | max 500 chars (validated in API) |
| version | integer | NOT NULL DEFAULT 1 (optimistic concurrency) |
| idempotency_key | varchar(64) | NULL. **[OPTIONAL]** UNIQUE (user_id, idempotency_key) |
| created_at / updated_at | timestamptz | NOT NULL |
| preparing_at / completed_at | timestamptz | NULL. Used for wait-time metrics (Premium vs Free). |

**Indexes**
- `ix_orders_queue` on `(status, priority DESC, created_at ASC)`: serves the processing queue (FR-05).
- `ix_orders_user_created` on `(user_id, created_at DESC)`: serves "My Orders".

## 8.4 `order_items`

| Column | Type | Constraints |
|---|---|---|
| id | bigint | PK identity |
| order_id | bigint | NOT NULL, FK → orders(id) ON DELETE CASCADE, indexed |
| menu_item_id | bigint | NOT NULL, FK → menu_items(id) ON DELETE RESTRICT |
| quantity | integer | NOT NULL, CHECK 1–20 |
| unit_price | numeric(10,2) | NOT NULL (price snapshot) |
| line_total | numeric(10,2) | NOT NULL |

UNIQUE `(order_id, menu_item_id)`: the API merges duplicate lines.

## 8.5 `order_status_history` (FR-06)

| Column | Type | Constraints |
|---|---|---|
| id | bigint | PK identity |
| order_id | bigint | NOT NULL, FK → orders(id) ON DELETE CASCADE |
| from_status | varchar(16) | NULL (creation) |
| to_status | varchar(16) | NOT NULL |
| changed_by | bigint | NOT NULL, FK → users(id) |
| changed_at | timestamptz | NOT NULL DEFAULT now() |

Index `(order_id, changed_at)`.

## 8.6 `load_test_runs` (FR-07, NFR-07, AC-04)

| Column | Type | Constraints |
|---|---|---|
| id | bigint | PK identity |
| scenario | varchar(16) | CHECK in (`NORMAL`,`FESTIVAL`) |
| status | varchar(16) | CHECK in (`RUNNING`,`COMPLETED`,`STOPPED`,`FAILED`) |
| started_by | bigint | FK → users(id) |
| target_users, spawn_rate, duration_seconds | integer | NOT NULL |
| started_at, ended_at | timestamptz | |
| total_requests, failed_requests | bigint | |
| avg_response_ms, p95_response_ms, peak_rps | numeric(10,2) | |
| avg_cpu_percent, peak_cpu_percent | numeric(5,2) | from CloudWatch over the run window |
| min_instances, max_instances | integer | from `GroupInServiceInstances` |
| estimated_cost_usd | numeric(10,4) | |
| raw_stats | jsonb | full Locust + CloudWatch summary |

**Partial unique index** `ux_one_running_test ON load_test_runs ((true)) WHERE status = 'RUNNING'` ensures only one active scenario across all instances.

## 8.7 `reports` (FR-13, FR-15)

| Column | Type | Constraints |
|---|---|---|
| id | bigint | PK identity |
| report_type | varchar(16) | CHECK in (`LOAD_TEST`,`COST`,`COMPARISON`) |
| load_test_run_id | bigint | NULL, FK → load_test_runs(id) ON DELETE SET NULL |
| created_by | bigint | FK → users(id) |
| s3_key | varchar(255) | NOT NULL, e.g. `reports/2026/11/festival-run-7.json` |
| format | varchar(8) | CHECK in (`JSON`,`CSV`,`MD`) |
| created_at | timestamptz | |

## 8.8 Core queries (application-level priority, FR-05 / NFR-05)

**Queue view (FR-03):**
```sql
SELECT o.*, u.full_name
FROM orders o JOIN users u ON u.id = o.user_id
WHERE o.status = 'PENDING'
ORDER BY o.priority DESC, o.created_at ASC
LIMIT :limit OFFSET :offset;
```

**Claim next (concurrency-safe across all ASG instances):**
```sql
WITH next AS (
  SELECT id FROM orders
  WHERE status = 'PENDING'
  ORDER BY priority DESC, created_at ASC
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE orders o
SET status = 'PREPARING', version = o.version + 1,
    preparing_at = now(), updated_at = now()
FROM next WHERE o.id = next.id
RETURNING o.*;
-- same transaction: INSERT INTO order_status_history (...)
```

**Status transition (optimistic lock):**
```sql
UPDATE orders
SET status = :to, version = version + 1, updated_at = now(),
    preparing_at = CASE WHEN :to = 'PREPARING' THEN now() ELSE preparing_at END,
    completed_at = CASE WHEN :to = 'COMPLETED' THEN now() ELSE completed_at END
WHERE id = :id AND status = :expected_from AND version = :version;
-- 0 rows -> 409
```

Allowed transitions, enforced in `QueueService`: `PENDING→PREPARING`, `PREPARING→COMPLETED`.

**[OPTIONAL] Anti-starvation aging:** off by default. If enabled, sort by `priority + LEAST(extract(epoch from now()-created_at)/600, 1)`, so a Free order waiting more than 10 min ties with new Premium orders. Disable it for the AC-01 demo so strict priority is visible.

## 8.9 Consistency & integrity summary (NFR-05)

- Order + items + first history row are written in **one transaction**. Prices are always read from the DB, never trusted from the client.
- Status changes are **conditional UPDATEs** (expected status + version), so lost updates are impossible.
- Queue claims use **`FOR UPDATE SKIP LOCKED`**, so no two admins/instances claim the same order.
- One running load test is enforced by a **partial unique index**, not by in-memory flags, because instances are stateless.
- Default isolation `READ COMMITTED` is enough with the patterns above.

## 8.10 Migrations & seed

- Alembic revisions live in `backend/alembic/versions/`.
- `0001_initial_schema`, `0002_seed_menu`, `0003_seed_admin` (admin email/password from env), `0004_seed_loadtest_users` (e.g. 100 users `lt-free-NN` / `lt-prem-NN` for Locust).
