# FeastFlow infrastructure (P5)

Idempotent AWS CLI scripts for the AWS Academy **Learner Lab** (us-east-1). Run from **Git Bash / WSL / CloudShell**.
Everything is tagged `Project=FeastFlow`. Design: `docs/02-high-level-aws-architecture.md`, constraints: `docs/12-…`.

## Prerequisites
- AWS CLI v2, Docker, `openssl`, a running Learner Lab session.
- Credentials from Learner Lab → **AWS Details → AWS CLI**. Paste into `~/.aws/credentials` (or export `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`). They expire with the session (~4 h).

## Run order
```bash
cd infra/scripts
./01-network-sg.sh          # security groups (optional: MY_IP=x.x.x.x to open Locust UI to you)
./02-s3-ecr.sh              # S3 bucket + ECR repo
./02b-push-image.sh         # docker build + push :latest and :<version>
./03-rds.sh                 # RDS PostgreSQL (5-10 min)
./06-locust.sh              # Locust EC2 with loadtest/locustfile.py (before 04: the app needs its IP)
./04-launch-template-asg-alb.sh   # ALB, target group, launch template, ASG (min 2 / max 4, CPU 50 %)
ALERT_EMAIL=you@example.com ./05-alarms-sns.sh   # alarms (ALERT_EMAIL optional)
```
`06` runs before `04` on purpose: the launch template passes Locust's private IP to the app as `LOCUST_URL`,
and the app sends the ALB address to Locust with every start request. If you created the ASG first,
run `06` and then re-run `04` (it adds a launch-template version) and start an instance refresh.
Generated secrets (DB password, JWT secret, admin password, load-test password) and resource ids live in
`infra/.state.env` (git-ignored). The 100 load-test accounts are seeded only because `LOADTEST_PASSWORD` is set;
the app and Locust both receive the same random value (the public dev password `loadtest-pass` is never used on AWS).

## Verify (P5 exit criteria)
```bash
source .state.env
for i in 1 2 3 4 5 6; do curl -sI http://$ALB_DNS/api/health | grep -i x-served-by; done   # alternates between 2 instances
curl -s http://$ALB_DNS/api/health
aws elbv2 describe-target-health --target-group-arn $TG_ARN --query 'TargetHealthDescriptions[].TargetHealth.State'
aws cloudwatch list-metrics --namespace CWAgent --metric-name mem_used_percent   # memory metric (after ~3 min)
```
Instance boot log: `/var/log/feastflow-userdata.log`. App logs: CloudWatch log group `/feastflow/app`.

## Notes
- The app container needs IMDSv2 hop limit 2 (set in the launch template) to read its instance id and role credentials.
- DB pool is 3+2 connections per worker, 2 workers per instance, so max 4 instances use at most 40 of db.t3.micro's ~80 connections.
- Menu images: upload files to `s3://<bucket>/menu/<slug>.jpg` (keys are seeded as `menu/paneer-tikka.jpg`, …). Missing images are hidden in the UI.
- To redeploy a new image manually: `./02b-push-image.sh` then
  `aws autoscaling start-instance-refresh --auto-scaling-group-name feastflow-asg --preferences MinHealthyPercentage=100,InstanceWarmup=120`
  (P6 automates this).
- Idle: set ASG min/desired to 0, stop the Locust instance, stop RDS. Teardown: `CONFIRM=yes ./99-teardown.sh`.
- If RDS or ECR is blocked in your lab, see docs 12 (L-09, L-11) for the fallbacks.
