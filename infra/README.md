# FeastFlow on AWS (P6)

Idempotent AWS CLI scripts for the AWS Academy **Learner Lab** (us-east-1). Run them from **Git Bash**.
Everything is tagged `Project=FeastFlow`. `infra/localstack/` and `infra/mysql/` are for local development only.

## Before every session
1. Learner Lab → **Start Lab**, wait for the green dot.
2. **AWS Details → AWS CLI → Show**, copy the whole `[default]` block into `C:\Users\<you>\.aws\credentials`
   (never into this repo). The keys change every session.
3. `aws sts get-caller-identity` should print the account number.
4. Docker Desktop must be running for `02b-push-image.sh`.

## First deployment (~30-45 min, mostly waiting for RDS)
```bash
cd infra/scripts
./01-network-sg.sh              # security groups (MY_IP=x.x.x.x also opens the Locust UI to you)
./02-s3-ecr.sh                  # private S3 bucket (food photos) + ECR repo
./02b-push-image.sh             # build the app image and push it
./03-rds-mysql.sh               # RDS MySQL 8.4 (5-10 min)
./04-sqs-sns.sh                 # orders-prime / orders-standard (+ DLQs), order-notifications topic
./08-locust-ec2.sh              # load generator, BEFORE 05 so the app gets its address
./05-launch-template-alb-asg.sh # ALB, launch template, ASG min 1 / max 4, scale at 60 % CPU
ALERT_EMAIL=you@example.com ./06-cloudwatch-alarms.sh   # alarms + "FeastFlow" dashboard
./07-lambda-eventbridge.sh      # nightly auto-stop at 23:00 IST (STOP_CRON / STOP_TZ to change)
```
Then open `http://<ALB_DNS>` (printed by 05, also in `infra/.state.env`) and log in as the admin.
`ADMIN_PASSWORD` is in `infra/.state.env`, along with the other generated secrets and resource ids.
That file is git-ignored; keep it, the scripts need it.

## Day to day
| Task | Command |
|---|---|
| Park everything (ASG → 0, Locust + RDS stopped) | `./stop.sh` |
| Resume | `./start.sh` (site back ~5 min after RDS is up) |
| Ship new code | `./02b-push-image.sh && ./redeploy.sh` |
| Change app settings (env vars) | edit `05`, re-run it, then `./redeploy.sh` |
| Delete everything after grading | `CONFIRM=yes ./99-teardown.sh` |

The Lambda also parks the stack every night. Learner Lab additionally stops EC2 instances when a
session ends; the ASG replaces them when the lab starts again.

## Verify
```bash
source ../.state.env
curl -s http://$ALB_DNS/api/health
for i in 1 2 3 4 5 6; do curl -sI http://$ALB_DNS/api/health | grep -i x-served-by; done  # alternates once 2+ instances
aws elbv2 describe-target-health --target-group-arn $TG_ARN --query 'TargetHealthDescriptions[].TargetHealth.State'
aws sqs get-queue-attributes --queue-url $(aws sqs get-queue-url --queue-name orders-standard --query QueueUrl --output text) \
  --attribute-names ApproximateNumberOfMessages
```
- Place an order in the browser: it should reach DELIVERED with a partner assigned, and the customer
  gets SNS emails once they confirmed the subscription email.
- Admin → load test → **festival**: CPU passes 60 %, the ASG goes 1 → 3/4 (EC2 → Auto Scaling Groups →
  Activity), then scales back in after the run. Watch it on the CloudWatch **FeastFlow** dashboard.
- `./stop.sh`: ASG desired 0 and RDS `stopping`.

## Troubleshooting
- `ExpiredToken` / `InvalidClientTokenId`: credentials are from an old session, paste new ones.
- Target stays unhealthy: on the instance (EC2 → Connect → Session Manager) check
  `/var/log/feastflow-userdata.log` and `docker logs feastflow-api`. App logs are also in the CloudWatch
  log group `/feastflow/app`. The usual cause is RDS still starting.
- Load-test panel says "not configured": run `08`, re-run `05`, then `./redeploy.sh`.
- The app's containers authenticate with LabRole (instance profile), so no keys are stored on AWS.
