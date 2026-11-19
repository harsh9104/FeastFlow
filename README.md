# FeastFlow

Food ordering with Prime priority, auto-assigned delivery partners and a festival-day load scenario,
deployed on AWS Learner Lab (EC2 + ALB + ASG, RDS MySQL, SQS, SNS, S3, CloudWatch, Lambda + EventBridge).

The full project plan is in [docs/PLAN.md](docs/PLAN.md).

## Run locally
```bash
docker compose up --build
curl http://localhost:8000/api/health        # liveness
curl http://localhost:8000/api/health/ready  # checks MySQL
```

## API so far
| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/register` | anyone |
| POST | `/api/auth/login` | anyone |
| GET | `/api/users/me` | logged in |
| POST | `/api/prime/subscribe` · `/api/prime/cancel` | customer (mock payment, 30 days) |
| GET | `/api/admin/users?prime_only=true` | admin |

Interactive docs: http://localhost:8000/docs. Default admin: `admin@feastflow.local` / `Admin@12345` (set `ADMIN_EMAIL`/`ADMIN_PASSWORD`).

## Backend tests
```bash
cd backend
pip install -r requirements-dev.txt
ruff check . && pytest -q
```
