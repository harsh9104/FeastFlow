#!/usr/bin/env bash
# Deletes everything FeastFlow created. Irreversible (the database too).
# Run: CONFIRM=yes ./99-teardown.sh
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
[ "${CONFIRM:-}" = "yes" ] || { echo "This deletes ALL FeastFlow AWS resources, including the database. Re-run with CONFIRM=yes"; exit 1; }
try() { "$@" >/dev/null 2>&1 || true; }

log "Schedule + Lambda"
try aws scheduler delete-schedule --name "$SCHEDULE_NAME"
try aws events remove-targets --rule "$SCHEDULE_NAME" --ids 1
try aws events delete-rule --name "$SCHEDULE_NAME"
try aws lambda delete-function --function-name "$LAMBDA_NAME"

log "Auto Scaling Group"
try aws autoscaling delete-auto-scaling-group --auto-scaling-group-name "$ASG_NAME" --force-delete
try aws ec2 delete-launch-template --launch-template-name "$LT_NAME"

log "Load balancer + target group"
LB="$(aws elbv2 describe-load-balancers --names "$ALB_NAME" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)"
if [ -n "$LB" ] && [ "$LB" != "None" ]; then
  try aws elbv2 delete-load-balancer --load-balancer-arn "$LB"
  try aws elbv2 wait load-balancers-deleted --load-balancer-arns "$LB"
fi
TG="$(aws elbv2 describe-target-groups --names "$TG_NAME" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)"
[ -z "$TG" ] || [ "$TG" = "None" ] || try aws elbv2 delete-target-group --target-group-arn "$TG"

log "Locust + any remaining tagged instances"
IDS="$(aws ec2 describe-instances --filters Name=tag:Project,Values="$PROJECT" Name=instance-state-name,Values=pending,running,stopped,stopping \
  --query 'Reservations[].Instances[].InstanceId' --output text)"
# shellcheck disable=SC2086
[ -z "$IDS" ] || { try aws ec2 terminate-instances --instance-ids $IDS; try aws ec2 wait instance-terminated --instance-ids $IDS; }

log "RDS (several minutes)"
try aws rds delete-db-instance --db-instance-identifier "$DB_ID" --skip-final-snapshot --delete-automated-backups
try aws rds wait db-instance-deleted --db-instance-identifier "$DB_ID"
try aws rds delete-db-subnet-group --db-subnet-group-name "$DB_SUBNET_GROUP"

log "Alarms, dashboard, SNS, SQS, logs"
ALARMS="$(aws cloudwatch describe-alarms --alarm-name-prefix feastflow- --query 'MetricAlarms[].AlarmName' --output text)"
# shellcheck disable=SC2086
[ -z "$ALARMS" ] || try aws cloudwatch delete-alarms --alarm-names $ALARMS
try aws cloudwatch delete-dashboards --dashboard-names "$DASHBOARD_NAME"
for t in "$SNS_TOPIC_NAME" "$ALERTS_TOPIC_NAME"; do
  try aws sns delete-topic --topic-arn "arn:aws:sns:${REGION}:${ACCOUNT_ID}:$t"
done
for q in "$SQS_PRIME_QUEUE" "$SQS_STANDARD_QUEUE" "$SQS_PRIME_QUEUE-dlq" "$SQS_STANDARD_QUEUE-dlq"; do
  url="$(aws sqs get-queue-url --queue-name "$q" --query QueueUrl --output text 2>/dev/null || true)"
  [ -z "$url" ] || try aws sqs delete-queue --queue-url "$url"
done
try aws logs delete-log-group --log-group-name "$LOG_GROUP"
try aws logs delete-log-group --log-group-name "/aws/lambda/$LAMBDA_NAME"

log "S3 + ECR"
try aws s3 rb "s3://$BUCKET" --force
try aws ecr delete-repository --repository-name "$ECR_REPO" --force

log "Security groups (retrying while network interfaces detach)"
for sg in SG_LOCUST SG_RDS SG_APP SG_ALB; do
  id="${!sg:-}"; [ -n "$id" ] || continue
  for _ in 1 2 3 4 5 6; do
    aws ec2 delete-security-group --group-id "$id" >/dev/null 2>&1 && break
    sleep 20
  done
done
rm -f "$STATE_FILE"
log "teardown complete"
