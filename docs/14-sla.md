# 14 – Service Level Agreement (SLA-01, SLA-02)

This is the formal SLA for the FeastFlow web app and API. It replaces the draft in [13 §13.6](13-traffic-simulation-and-sla.md#136-sla-definition-sla-01--draft). The availability figure in §4 is computed by the application itself, so every number in a report can be reproduced from the same data.

## 1. Service in scope

| Item | Definition |
|---|---|
| **Service** | The FeastFlow web UI and REST API, reached through the Application Load Balancer (`http://<alb-dns>/`) |
| **Components counted** | ALB, the Auto Scaling group of app instances, and the app containers on them |
| **Not counted** | The Locust load generator, CloudWatch itself, the GitHub Actions pipeline, and the RDS instance except where its failure makes the app return 5xx |
| **Environment** | AWS Learner Lab, `us-east-1`. The environment only runs while a lab session is active (see §5). |

## 2. Availability target

| | |
|---|---|
| **Target** | **99.5 %** availability per measurement period (NFR-02) |
| **Supporting objective** | p95 API response time **< 1 s** under the Festival scenario, request failure rate **< 1 %** (Festival) and **< 0.1 %** (Normal) |

## 3. Measurement period

- **One calendar month**, counting **only minutes in which the environment was running and reporting metrics** (the Learner Lab is switched off between sessions).
- Each load-test run is also reported on its own, because SLA-02 asks for measurements "during each scenario".

## 4. How availability is measured

The unit is **one minute**. Per minute, the application reads three values from the metrics source (CloudWatch on AWS, the local collector in development):

| Value | Source on AWS |
|---|---|
| Healthy targets | ALB `HealthyHostCount` (minimum in the minute) |
| Requests | ALB `RequestCount` (sum) |
| Server errors | ALB `HTTPCode_Target_5XX_Count` + `HTTPCode_ELB_5XX_Count` (sum) |

A measured minute is **unavailable** if either:

1. `HealthyHostCount = 0` (no instance could serve traffic), or
2. the 5xx ratio, errors ÷ requests, is **above 5 %** (and there was at least one request).

A minute with **no data at all** is **not measured**. It is neither up nor down, because it means the environment was not running (§5).

```
availability % = 100 × (1 − unavailable minutes ÷ measured minutes)
```

**Worked example.** In a month with 40 active lab hours there are 2,400 measured minutes. At 99.5 % the allowed downtime is 0.5 % × 2,400 = **12 minutes**. If a bad deployment returns 5xx for 15 of those minutes, availability is 100 × (1 − 15/2,400) = **99.375 %** and the target is **missed**.

For comparison, over a full always-on 30-day month (43,200 minutes) the 0.5 % budget would be about 216 minutes (3.6 hours).

### Running the calculation

```bash
# as the admin, for any period of up to 7 days (default: the last 24 hours)
curl -H "Authorization: Bearer $TOKEN" \
  "http://<host>/api/v1/admin/sla/availability?from=2026-11-01T00:00:00Z&to=2026-11-08T00:00:00Z"
```

The response contains `measured_minutes`, `no_data_minutes`, `unavailable_minutes`, `availability_pct`, `allowed_downtime_minutes`, `longest_outage_minutes`, `target_met`, any `breach_reasons`, and the list of `outages` with start, end and reason. For a month, sum the minutes from the weekly responses, or query a calendar month in pieces.

## 5. Exclusions

These minutes are **excluded from the measurement** and cannot cause a breach:

| # | Exclusion |
|---|---|
| E-1 | Time when the Learner Lab session is stopped or starting up (no metrics are reported, so those minutes are "no data") |
| E-2 | AWS regional or service incidents, confirmed on the AWS Health Dashboard |
| E-3 | Planned maintenance announced at least 24 hours in advance |
| E-4 | Load tests that deliberately exceed the configured maximum capacity (more than the ASG maximum of 4 instances can serve) |
| E-5 | Client-side errors (HTTP 4xx), which do not count toward the 5xx ratio |
| E-6 | Failures caused by the customer or administrator, such as deleting resources or exceeding Learner Lab budget caps |

Exclusions E-2 to E-6 are applied by choosing the reporting period (or splitting it around the excluded window) and are recorded in the report, because they cannot be detected automatically.

## 6. Breach conditions

The SLA is **breached** if either holds in a measurement period:

1. availability is **below 99.5 %**, or
2. **any single outage lasts more than 30 consecutive minutes**, even if the monthly percentage is still met.

An outage is a run of consecutive unavailable minutes. A gap of "no data" minutes ends an outage rather than extending it. The API reports both conditions in `breach_reasons`.

**Remedy.** This is a course project with no paying customers, so there are no financial credits. A breach is recorded in the final report together with its cause and the corrective action taken.

## 7. Supporting measurements per scenario (SLA-02)

Each load-test run stores these measurements automatically (Admin → Load Tests, and the comparison report):

| Measure | Where it comes from |
|---|---|
| API latency (average, p95) | Locust, stored on the run |
| Request failures (count, error rate) | Locust, stored on the run |
| Instance health and count (min → max in service) | CloudWatch / the local collector over the run window |
| CPU and memory (average, peak) | CloudWatch agent / the local collector |
| Scaling events | Auto Scaling activity history (AWS only) |
| Estimated cost of the run | Cost service |

The **Normal vs Festival comparison** (Admin → Costs → *Normal vs Festival comparison*) puts the two runs side by side. The expected results are in [13 §13.2](13-traffic-simulation-and-sla.md#132-scenarios-starting-values-a-12).

## 8. Design measures that support the target

| Measure | Effect |
|---|---|
| Minimum 2 instances in 2 Availability Zones | One instance or AZ can fail without an outage |
| ALB health check `GET /api/health` every 15 s (2 healthy / 3 unhealthy) | Failed targets stop receiving traffic within about 45 s |
| ASG health check type **ELB**, with automatic replacement | Unhealthy instances are replaced, not just removed |
| Liveness endpoint independent of the database | A database problem does not make the ALB remove every instance. `/api/health/ready` reports database state separately. |
| Rolling deploys through ASG instance refresh, not replace-all | New versions roll out while healthy instances keep serving (the CD pipeline is planned in P6) |
| Stateless app (JWT, no server sessions) | Any instance can serve any request |
| Gunicorn keep-alive of 75 s | Stays above the ALB idle timeout (60 s), avoiding spurious 502s |
| Target-tracking scale-out at 50 % CPU | Capacity grows under festival load before latency suffers |

## 9. Known limitations

| Limitation | Effect on the SLA |
|---|---|
| **Single-AZ RDS** | The database is a single point of failure. A database outage returns 5xx and counts as downtime. |
| **HTTP-only listener** (no domain or certificate in the lab) | No transport encryption. This is a security limitation, not an availability one, and is accepted for the lab (A-08). |
| Availability is judged from the ALB's own view | It cannot see problems that never reach the ALB, such as DNS or client network issues. |
| Local development measures the app from inside | The local metrics source reports one container, so "healthy hosts" is only 0 or 1+. |

## 10. Results

Fill this table after the AWS runs. Everything needed to produce it is in the application.

| Period | Measured min | Unavailable min | Availability | Longest outage | Target met | Notes |
|---|---|---|---|---|---|---|
| *(lab session 1)* | | | | | | |
| *(festival run)* | | | | | | |

Evidence to attach: the `/admin/sla/availability` response, the dashboard screenshot for the period, and the comparison report.
