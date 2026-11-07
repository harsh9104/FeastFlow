# 07 – Finalized Technology Stack (Task 3)

Every row matches SRS §4. Only libraries and versions were added.

| Layer | SRS says | Final choice | Notes |
|---|---|---|---|
| Frontend | React | **React 18 + TypeScript + Vite 5**, React Router 6, Recharts (dashboard charts), plain CSS modules | No UI framework, to keep the bundle small. Build output is served by the backend container. |
| Backend | Python FastAPI | **Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), Alembic, psycopg 3, PyJWT, bcrypt, boto3, httpx** | Sync SQLAlchemy is simpler and is enough at this scale. Gunicorn + Uvicorn workers. |
| Database | PostgreSQL (RDS if permitted) | **Amazon RDS for PostgreSQL 16**, db.t3.micro, single-AZ, 20 GB gp3 | Fallback if RDS is blocked: `postgres:16` container on a dedicated t3.micro EC2 outside the ASG |
| Compute | EC2 + Docker | **Amazon Linux 2023 on t3.micro**, Docker Engine, one container per instance | Multi-stage Dockerfile: `node:20-alpine` builds the SPA, then `python:3.12-slim` serves it |
| Traffic | ALB + EC2 Auto Scaling | **ALB (HTTP :80)** + **ASG min 2 / max 4, target tracking CPU 50 %** | Max 4 respects Learner Lab instance caps and budget (NFR-03) |
| Monitoring | CloudWatch + optional SNS | **CloudWatch** metrics, Logs, Alarms, Dashboard, **CloudWatch agent** for memory; **SNS email [OPTIONAL]** | |
| Access / storage | IAM + S3 | **LabRole / LabInstanceProfile** (Learner Lab-provided), security groups, **S3** private bucket with bucket policy | Custom IAM roles cannot be created in Learner Lab (see doc 12) |
| Image registry | (not specified) | **Amazon ECR** | Fallback: GitHub Container Registry (public image) |
| CI/CD | GitHub + CodePipeline/CodeBuild (if permitted) | **GitHub Actions** (CI + CD). CodePipeline + CodeBuild is the documented alternative **[OPTIONAL]**. | See rationale below |
| Load testing | Locust | **Locust 2.x** on a dedicated t3.small EC2, controlled via its HTTP API | |
| Local dev | — | Docker Compose (app + postgres), `.env` files | |
| Quality | — | ruff (lint + format), pytest + httpx TestClient, ESLint, Vitest **[OPTIONAL]** | |

## CI/CD choice: GitHub Actions (primary) vs CodePipeline/CodeBuild (alternative)

| Criterion | GitHub Actions | CodePipeline + CodeBuild |
|---|---|---|
| Works in Learner Lab | Yes. Runs outside AWS and uses session credentials stored as repo secrets. | Usually available with `LabRole` as service role. The GitHub source connection (CodeStar Connections) is **often blocked**, so it must be verified. |
| Credential handling | Learner Lab keys + session token expire each session (~4 h), so the three secrets must be **refreshed before each demo**. OIDC isn't possible because IAM providers can't be created. | Uses LabRole, so there are no external secrets |
| Cost | Free for public/private repos within minutes quota | Charged against lab credits |
| Evidence for AC-03 | Workflow run log + ASG instance-refresh history + `/api/health` version | Pipeline execution history |

**Decision:** use GitHub Actions. If your lab confirms CodePipeline + CodeStar connection work, the same steps map 1:1 to a `buildspec.yml`. I'll include it as an optional file.

## Deliberately NOT used (keeps it lightweight)

| Service | Why not |
|---|---|
| SQS / Redis for the queue | Priority ordering + `SKIP LOCKED` in PostgreSQL already satisfies FR-05/NFR-05, and the spec requires priority in app logic |
| ECS / EKS / Lambda | The SRS mandates EC2 + Docker and ASG scaling events |
| NAT Gateway / private app subnets | About $0.045/h plus data charges, which doesn't fit the lab budget. App SG only accepts traffic from the ALB SG. |
| CloudFront / Route 53 / ACM | No domain in Learner Lab. Not required by the FRS. |
| Cognito | Restricted in Learner Lab, and the FRS asks for app-managed users |
| Payment, maps, multi-restaurant | Excluded by CON-03 |
