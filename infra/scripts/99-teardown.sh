#!/usr/bin/env bash
# Deletes everything tagged/named for FeastFlow. Irreversible. Run: CONFIRM=yes ./99-teardown.sh
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
[ "${CONFIRM:-}" = "yes" ] || { echo "This deletes ALL FeastFlow AWS resources. Re-run with CONFIRM=yes"; exit 1; }
try() { "$@" >/dev/null 2>&1 || true; }

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
[ -z "$IDS" ] || { try aws ec2 terminate-instances --instance-ids $IDS; try aws ec2 wait instance-terminated --instance-ids $IDS; }

log "RDS"
try aws rds delete-db-instance --db-instance-identifier "$DB_ID" --skip-final-snapshot --delete-automated-backups
try aws rds wait db-instance-deleted --db-instance-identifier "$DB_ID"
try aws rds delete-db-subnet-group --db-subnet-group-name feastflow-db-subnets

log "Alarms, SNS, logs"
try aws cloudwatch delete-alarms --alarm-names feastflow-high-cpu feastflow-unhealthy-hosts feastflow-high-latency \
  feastflow-high-memory feastflow-rds-cpu feastflow-5xx-rate
TOPIC="$(aws sns list-topics --query "Topics[?contains(TopicArn,'feastflow-alerts')].TopicArn" --output text)"
[ -z "$TOPIC" ] || try aws sns delete-topic --topic-arn "$TOPIC"
try aws logs delete-log-group --log-group-name "$LOG_GROUP"

log "S3 + ECR"
try aws s3 rb "s3://$BUCKET" --force
try aws ecr delete-repository --repository-name "$ECR_REPO" --force

log "Security groups (retrying while ENIs detach)"
for sg in SG_LOCUST SG_RDS SG_APP SG_ALB; do
  id="${!sg:-}"; [ -n "$id" ] || continue
  for _ in 1 2 3 4 5 6; do
    aws ec2 delete-security-group --group-id "$id" >/dev/null 2>&1 && break
    sleep 20
  done
done
rm -f "$STATE_FILE"
log "teardown complete"
