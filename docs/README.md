# FeastFlow – Architecture & Design Package

**Status:** Design approved and implemented through P9 locally. AWS deployment pending. See the project [README](../README.md) for current status.
**Source of truth:** `../FeastFlow_SRS_FRS.pdf`
**Date:** 2026-11-06

## Contents

| # | Document | Task |
|---|---|---|
| 01 | [Requirement Analysis](01-requirement-analysis.md): roles, modules, components, dependencies, traceability | Task 1 |
| 02 | [High-Level AWS Architecture](02-high-level-aws-architecture.md) *(diagram)* | Task 2.1 |
| 03 | [Low-Level System Architecture](03-low-level-system-architecture.md) *(diagrams)* | Task 2.2 |
| 04 | [Project Flowchart: Customer, Admin, Cloud](04-project-flowchart.md) *(diagrams)* | Task 2.3 |
| 05 | [Database ER Diagram](05-database-er-diagram.md) *(diagram)* | Task 2.4 |
| 06 | [API Request & Response Workflow](06-api-request-response-workflow.md) *(diagrams)* | Task 2.5 |
| 07 | [Technology Stack](07-technology-stack.md) | Task 3 |
| 08 | [Database Tables & Relationships](08-database-design.md) | Task 3 |
| 09 | [API Endpoints](09-api-endpoints.md) | Task 3 |
| 10 | [Folder Structure](10-folder-structure.md) | Task 3 |
| 11 | [Development Roadmap](11-development-roadmap.md) | Task 3 |
| 12 | [Learner Lab Constraints, Optional Services, Assumptions, Cost](12-learner-lab-constraints-and-assumptions.md) | Constraints |
| 13 | [Normal vs Festival Traffic Simulation & SLA](13-traffic-simulation-and-sla.md) | Constraints |
| 14 | [Service Level Agreement](14-sla.md): availability target, measurement, exclusions, breach conditions | SLA-01/02 |

## Design at a glance

- **React (Vite, TS) + FastAPI** packaged in **one Docker image** on **EC2 t3.micro** instances in an **ASG (min 2 / max 4, CPU target 50 %)** behind an **ALB**.
- **RDS PostgreSQL** (db.t3.micro, single-AZ) stores users, menu, orders, status history, load-test runs and reports.
- **Premium priority is pure application logic:** `orders.priority` is snapshotted from `users.subscription_tier`, the queue is ordered `priority DESC, created_at ASC`, and claims are concurrency-safe via `FOR UPDATE SKIP LOCKED`. IAM is not involved (CON-02).
- **Locust** on a separate EC2 runs **Normal-day (25 users)** and **Festival-day (250 users)** scenarios, launched from the admin UI.
- **CloudWatch** (+ agent for memory) feeds alarms, auto scaling and the in-app dashboard. **S3** holds menu images and reports.
- **GitHub Actions** handles CI/CD: test → build → push to ECR → ASG instance refresh → smoke test.
- **Learner Lab-aware:** LabRole/LabInstanceProfile, no NAT, HTTP-only ALB, about $0.13/h baseline.

## Mermaid validation

Node.js/Mermaid CLI is not installed on this machine, so diagrams were checked with a static lint script. It checks fences, diagram headers, balanced brackets and quotes, subgraph/`end` and `alt`/`loop`/`opt` block balance, reserved IDs, and semicolons in sequence messages. All diagrams use a conservative syntax subset: quoted labels, no parentheses in ER types. To render-check, paste any block into <https://mermaid.live> or use the VS Code "Markdown Preview Mermaid Support" extension.

## Approval checklist (please confirm or amend)

1. ☐ Premium is selectable at registration and toggleable without payment (A-01).
2. ☐ GitHub Actions as CI/CD, with CodePipeline/CodeBuild only as an optional alternative.
3. ☐ RDS PostgreSQL single-AZ (fallback: Postgres on EC2 if RDS is blocked in your lab).
4. ☐ ASG min 2 / max 4 on t3.micro, CPU target 50 %.
5. ☐ Scenario sizes 25 / 250 users (to be calibrated).
6. ☐ HTTP-only ALB accepted as a lab limitation.
7. ☐ React + TypeScript, served from the same container as the API.
