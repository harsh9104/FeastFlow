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

## Backend tests
```bash
cd backend
pip install -r requirements-dev.txt
ruff check . && pytest -q
```
