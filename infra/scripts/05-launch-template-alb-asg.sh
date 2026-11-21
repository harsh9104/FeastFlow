#!/usr/bin/env bash
# ALB + target group + launch template + Auto Scaling Group (t3.micro, min 1 / max 4,
# target tracking at 60 % average CPU). Re-run it after changing settings: it adds a new
# launch-template version; then run ./redeploy.sh to replace the running instances.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${DB_HOST:?run 03-rds-mysql.sh first}"
: "${SG_APP:?run 01-network-sg.sh first}"
: "${S3_BUCKET:?run 02-s3-ecr.sh first}"
: "${SNS_TOPIC_ARN:?run 04-sqs-sns.sh first}"

ASG_MIN="${ASG_MIN:-1}"; ASG_MAX="${ASG_MAX:-4}"; CPU_TARGET="${CPU_TARGET:-60}"

# ---- log group ----------------------------------------------------------
aws logs create-log-group --log-group-name "$LOG_GROUP" 2>/dev/null || true
aws logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 7

# ---- ALB ----------------------------------------------------------------
LB_ARN="$(aws elbv2 describe-load-balancers --names "$ALB_NAME" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)"
if [ -z "$LB_ARN" ] || [ "$LB_ARN" = "None" ]; then
  LB_ARN="$(aws elbv2 create-load-balancer --name "$ALB_NAME" --type application --scheme internet-facing \
    --subnets "$SUBNET_A" "$SUBNET_B" --security-groups "$SG_ALB" \
    --tags Key=Project,Value="$PROJECT" --query 'LoadBalancers[0].LoadBalancerArn' --output text)"
fi
save LB_ARN "$LB_ARN"
save ALB_DNS "$(aws elbv2 describe-load-balancers --load-balancer-arns "$LB_ARN" --query 'LoadBalancers[0].DNSName' --output text)"

TG_ARN="$(aws elbv2 describe-target-groups --names "$TG_NAME" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)"
if [ -z "$TG_ARN" ] || [ "$TG_ARN" = "None" ]; then
  TG_ARN="$(aws elbv2 create-target-group --name "$TG_NAME" --protocol HTTP --port 8000 --vpc-id "$VPC_ID" \
    --target-type instance --health-check-path /api/health --health-check-interval-seconds 15 \
    --health-check-timeout-seconds 5 --healthy-threshold-count 2 --unhealthy-threshold-count 3 \
    --tags Key=Project,Value="$PROJECT" --query 'TargetGroups[0].TargetGroupArn' --output text)"
fi
save TG_ARN "$TG_ARN"
aws elbv2 modify-target-group-attributes --target-group-arn "$TG_ARN" \
  --attributes Key=deregistration_delay.timeout_seconds,Value=30 Key=stickiness.enabled,Value=false >/dev/null

if [ -z "$(aws elbv2 describe-listeners --load-balancer-arn "$LB_ARN" --query 'Listeners[?Port==`80`].ListenerArn' --output text)" ]; then
  aws elbv2 create-listener --load-balancer-arn "$LB_ARN" --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_ARN" >/dev/null
fi

# ---- container environment (same keys as .env.example) ------------------
if [ -n "${LOCUST_PRIVATE_IP:-}" ]; then
  LOCUST_URL="http://${LOCUST_PRIVATE_IP}:8089"
else
  LOCUST_URL=""
  log "WARNING: no Locust instance yet; the admin load-test panel will say 'not configured'."
  log "         Run 08-locust-ec2.sh, re-run this script, then ./redeploy.sh."
fi
APP_ENV_FILE="$(cat <<EOF
APP_ENV=production
DATABASE_URL=mysql+pymysql://feastflow:${DB_PASSWORD}@${DB_HOST}:3306/feastflow
JWT_SECRET=${JWT_SECRET}
JWT_EXPIRE_MINUTES=120
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
PRIME_PLAN_DAYS=30
AWS_REGION=${REGION}
AWS_DEFAULT_REGION=${REGION}
SQS_PRIME_QUEUE=${SQS_PRIME_QUEUE}
SQS_STANDARD_QUEUE=${SQS_STANDARD_QUEUE}
SNS_TOPIC_NAME=${SNS_TOPIC_NAME}
S3_BUCKET=${S3_BUCKET}
SEED_IMAGES=true
SNS_EMAIL_SUBSCRIPTIONS=true
CONFIRM_SECONDS=2
PREP_SECONDS=20
DELIVERY_SECONDS=40
AGING_SECONDS=120
LOADTEST_USERS=200
LOADTEST_PRIME_PERCENT=30
LOADTEST_PASSWORD=${LOADTEST_PASSWORD}
LOCUST_URL=${LOCUST_URL}
LOADTEST_TARGET=http://${ALB_DNS}
EOF
)"
# AWS_ENDPOINT_URL / S3_PUBLIC_ENDPOINT_URL are left out on purpose: boto3 then talks to
# real AWS with the LabRole credentials from the instance profile.

# ---- launch template ----------------------------------------------------
AMI_ID="$(latest_al2023_ami)"
IMAGE="$ECR_IMAGE:latest"
CW_CONFIG="$(tr -d '\n' < "$INFRA_DIR/cloudwatch/agent-config.json")"
APP_ENV_B64="$(printf '%s\n' "$APP_ENV_FILE" | base64 | tr -d '\n')"

USER_DATA="$(
  {
    echo '#!/bin/bash'
    for v in REGION ECR_REGISTRY IMAGE LOG_GROUP CW_CONFIG APP_ENV_B64; do
      printf 'export %s=%q\n' "$v" "${!v}"
    done
    tail -n +2 "$INFRA_DIR/user-data/app-instance.sh"   # drop its shebang
  } | base64 | tr -d '\n'
)"

LT_DATA="$(cat <<EOF
{
  "ImageId": "$AMI_ID",
  "InstanceType": "t3.micro",
  "IamInstanceProfile": {"Name": "$INSTANCE_PROFILE"},
  "SecurityGroupIds": ["$SG_APP"],
  "Monitoring": {"Enabled": true},
  "MetadataOptions": {"HttpTokens": "required", "HttpEndpoint": "enabled", "HttpPutResponseHopLimit": 2},
  "UserData": "$USER_DATA",
  "TagSpecifications": [
    {"ResourceType": "instance", "Tags": [{"Key": "Project", "Value": "$PROJECT"}, {"Key": "Name", "Value": "feastflow-app"}]},
    {"ResourceType": "volume",   "Tags": [{"Key": "Project", "Value": "$PROJECT"}]}
  ]
}
EOF
)"
# HttpPutResponseHopLimit=2 lets the containers reach IMDSv2 (instance id + LabRole credentials).

if aws ec2 describe-launch-templates --launch-template-names "$LT_NAME" >/dev/null 2>&1; then
  aws ec2 create-launch-template-version --launch-template-name "$LT_NAME" \
    --source-version '$Latest' --launch-template-data "$LT_DATA" >/dev/null
  NEWV="$(aws ec2 describe-launch-templates --launch-template-names "$LT_NAME" --query 'LaunchTemplates[0].LatestVersionNumber' --output text)"
  aws ec2 modify-launch-template --launch-template-name "$LT_NAME" --default-version "$NEWV" >/dev/null
  log "launch template $LT_NAME -> version $NEWV"
else
  aws ec2 create-launch-template --launch-template-name "$LT_NAME" --launch-template-data "$LT_DATA" \
    --tag-specifications "$(tag_spec launch-template "$LT_NAME")" >/dev/null
  log "launch template $LT_NAME created"
fi

# ---- Auto Scaling Group -------------------------------------------------
LT_SPEC="LaunchTemplateName=$LT_NAME,Version=\$Latest"
if [ "$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" --query 'length(AutoScalingGroups)' --output text)" = "0" ]; then
  aws autoscaling create-auto-scaling-group --auto-scaling-group-name "$ASG_NAME" \
    --launch-template "$LT_SPEC" --min-size "$ASG_MIN" --max-size "$ASG_MAX" --desired-capacity "$ASG_MIN" \
    --vpc-zone-identifier "$SUBNET_A,$SUBNET_B" --target-group-arns "$TG_ARN" \
    --health-check-type ELB --health-check-grace-period 240 --default-instance-warmup 120 \
    --tags "ResourceId=$ASG_NAME,ResourceType=auto-scaling-group,Key=Project,Value=$PROJECT,PropagateAtLaunch=true" \
           "ResourceId=$ASG_NAME,ResourceType=auto-scaling-group,Key=Name,Value=feastflow-app,PropagateAtLaunch=true"
  log "ASG $ASG_NAME created (min $ASG_MIN / max $ASG_MAX)"
else
  aws autoscaling update-auto-scaling-group --auto-scaling-group-name "$ASG_NAME" \
    --launch-template "$LT_SPEC" --min-size "$ASG_MIN" --max-size "$ASG_MAX"
  log "ASG $ASG_NAME updated (min $ASG_MIN / max $ASG_MAX)"
fi
aws autoscaling enable-metrics-collection --auto-scaling-group-name "$ASG_NAME" --granularity 1Minute
aws autoscaling put-scaling-policy --auto-scaling-group-name "$ASG_NAME" --policy-name "feastflow-cpu-$CPU_TARGET" \
  --policy-type TargetTrackingScaling --estimated-instance-warmup 120 \
  --target-tracking-configuration \
  "{\"TargetValue\":$CPU_TARGET.0,\"PredefinedMetricSpecification\":{\"PredefinedMetricType\":\"ASGAverageCPUUtilization\"}}" >/dev/null
save ASG_NAME "$ASG_NAME"

log "site: http://$ALB_DNS   (the first instance needs ~3-5 min to boot and turn healthy)"
log "check: aws elbv2 describe-target-health --target-group-arn $TG_ARN --query 'TargetHealthDescriptions[].TargetHealth.State'"
log "admin login: $ADMIN_EMAIL / (ADMIN_PASSWORD in infra/.state.env)"
