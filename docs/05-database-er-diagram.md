# 05 – Database ER Diagram

Engine: **PostgreSQL 16** on Amazon RDS. Column-level detail, constraints, and indexes are in [08-database-design.md](08-database-design.md).

```mermaid
erDiagram
    USERS ||--o{ ORDERS : "places"
    ORDERS ||--|{ ORDER_ITEMS : "contains"
    MENU_ITEMS ||--o{ ORDER_ITEMS : "is ordered as"
    ORDERS ||--|{ ORDER_STATUS_HISTORY : "has status changes"
    USERS ||--o{ ORDER_STATUS_HISTORY : "changes status"
    USERS ||--o{ LOAD_TEST_RUNS : "launches"
    LOAD_TEST_RUNS ||--o{ REPORTS : "produces"
    USERS ||--o{ REPORTS : "generates"

    USERS {
        bigint id PK
        varchar email UK "lowercased"
        varchar password_hash "bcrypt"
        varchar full_name
        varchar role "CUSTOMER or ADMIN"
        varchar subscription_tier "FREE or PREMIUM"
        timestamptz created_at
        timestamptz updated_at
    }

    MENU_ITEMS {
        bigint id PK
        varchar name UK
        text description
        varchar category
        numeric price "10,2 and above 0"
        varchar image_key "S3 object key"
        boolean is_available
        timestamptz created_at
        timestamptz updated_at
    }

    ORDERS {
        bigint id PK
        bigint user_id FK
        varchar status "PENDING, PREPARING, COMPLETED"
        smallint priority "1 PREMIUM, 0 FREE, snapshot"
        varchar tier_at_order "FREE or PREMIUM"
        numeric total_amount "informational, no payment"
        text notes
        int version "optimistic lock"
        varchar idempotency_key "optional, unique per user"
        timestamptz created_at
        timestamptz updated_at
        timestamptz preparing_at
        timestamptz completed_at
    }

    ORDER_ITEMS {
        bigint id PK
        bigint order_id FK
        bigint menu_item_id FK
        int quantity "1 to 20"
        numeric unit_price "price snapshot"
        numeric line_total
    }

    ORDER_STATUS_HISTORY {
        bigint id PK
        bigint order_id FK
        varchar from_status "null for creation"
        varchar to_status
        bigint changed_by FK
        timestamptz changed_at
    }

    LOAD_TEST_RUNS {
        bigint id PK
        varchar scenario "NORMAL or FESTIVAL"
        varchar status "RUNNING, COMPLETED, STOPPED, FAILED"
        bigint started_by FK
        int target_users
        int spawn_rate
        int duration_seconds
        timestamptz started_at
        timestamptz ended_at
        bigint total_requests
        bigint failed_requests
        numeric avg_response_ms
        numeric p95_response_ms
        numeric peak_rps
        numeric avg_cpu_percent
        numeric peak_cpu_percent
        int min_instances
        int max_instances
        numeric estimated_cost_usd
        jsonb raw_stats "Locust and CloudWatch summary"
    }

    REPORTS {
        bigint id PK
        varchar report_type "LOAD_TEST, COST, COMPARISON"
        bigint load_test_run_id FK "nullable"
        bigint created_by FK
        varchar s3_key
        varchar format "JSON, CSV, MD"
        timestamptz created_at
    }
```

## Relationships

| Relationship | Cardinality | Rule |
|---|---|---|
| USERS → ORDERS | 1 : 0..N | Only `CUSTOMER` users place orders. `ON DELETE RESTRICT`. |
| ORDERS → ORDER_ITEMS | 1 : 1..N | Every order has at least one item. `ON DELETE CASCADE`. |
| MENU_ITEMS → ORDER_ITEMS | 1 : 0..N | Price is copied into `unit_price`, so later menu price changes don't alter history. `ON DELETE RESTRICT`. |
| ORDERS → ORDER_STATUS_HISTORY | 1 : 1..N | Creation writes a `NULL → PENDING` row, and every transition appends one (FR-06). |
| USERS → ORDER_STATUS_HISTORY | 1 : 0..N | `changed_by` is the customer for creation and the admin for transitions. |
| USERS → LOAD_TEST_RUNS | 1 : 0..N | Admin who launched the scenario. |
| LOAD_TEST_RUNS → REPORTS | 1 : 0..N | Report rows for a run. Cost/comparison reports may have `NULL` run. |
| USERS → REPORTS | 1 : 0..N | Admin who generated the report. |
