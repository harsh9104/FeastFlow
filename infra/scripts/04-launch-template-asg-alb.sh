#!/usr/bin/env bash
# ALB + target group + launch template + Auto Scaling Group (min 2 / max 4, CPU target 50 %).
# Re-run after changing user-data: it adds a new launch-template version (ASG uses $Latest).
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${DB_HOST:?run 03-rds.sh first}"
: "${SG_APP:?run 01-network-sg.sh first}"

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

# ---- launch template ----------------------------------------------------
AMI_ID="$(aws ec2 describe-images --owners amazon \
  --filters 'Name=name,Values=al2023-ami-2023.*-x86_64' Name=state,Values=available \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)"
IMAGE="$ECR_IMAGE:latest"
DATABASE_URL="postgresql+psycopg://feastflow:${DB_PASSWORD}@${DB_HOST}:5432/feastflow"
ALB_DIMENSION="${LB_ARN#*:loadbalancer/}"
TG_DIMENSION="${TG_ARN##*:}"
CW_CONFIG="$(tr -d '\n' < "$INFRA_DIR/cloudwatch/agent-config.json")"

USER_DATA="$(
  {
    echo '#!/bin/bash'
    for v in REGION ECR_REGISTRY IMAGE DATABASE_URL JWT_SECRET ADMIN_EMAIL ADMIN_PASSWORD S3_BUCKET LOG_GROUP CW_CONFIG ASG_NAME ALB_DIMENSION TG_DIMENSION TG_ARN DB_ID; do
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
# HttpPutResponseHopLimit=2 lets the container reach IMDSv2 (instance id + role credentials).

if aws ec2 describe-launch-templates --launch-template-names "$LT_NAME" >/dev/null 2>&1; then
  aws ec2 create-launch-template-version --launch-template-name "$LT_NAME" \
    --source-version '$Latest' --launch-template-data "$LT_DATA" >/dev/null
  NEWV="$(aws ec2 describe-launch-templates --launch-template-names "$LT_NAME" --query 'LaunchTemplates[0].LatestVersionNumber' --output text)"
  aws ec2 modify-launch-template --launch-template-name "$LT_NAME" --default-version "$NEWV" >/dev/null
  log "launch template $LT_NAME -> version $NEWV"
else
  aws ec2 create-launch-template --launch-template-name "$LT_NAME" --launch-template-data "$LT_DATA" \
    --tag-specifications "$(tag_spec launch-template "$LT_NAME")" >/dev/null
fi

# ---- Auto Scaling Group -------------------------------------------------
LT_SPEC="LaunchTemplateName=$LT_NAME,Version=\$Latest"
if [ "$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" --query 'length(AutoScalingGroups)' --output text)" = "0" ]; then
  aws autoscaling create-auto-scaling-group --auto-scaling-group-name "$ASG_NAME" \
    --launch-template "$LT_SPEC" --min-size 2 --max-size 4 --desired-capacity 2 \
    --vpc-zone-identifier "$SUBNET_A,$SUBNET_B" --target-group-arns "$TG_ARN" \
    --health-check-type ELB --health-check-grace-period 180 --default-instance-warmup 120 \
    --tags "ResourceId=$ASG_NAME,ResourceType=auto-scaling-group,Key=Project,Value=$PROJECT,PropagateAtLaunch=true" \
           "ResourceId=$ASG_NAME,ResourceType=auto-scaling-group,Key=Name,Value=feastflow-app,PropagateAtLaunch=true"
else
  aws autoscaling update-auto-scaling-group --auto-scaling-group-name "$ASG_NAME" \
    --launch-template "$LT_SPEC" --min-size 2 --max-size 4
fi
aws autoscaling enable-metrics-collection --auto-scaling-group-name "$ASG_NAME" --granularity 1Minute
aws autoscaling put-scaling-policy --auto-scaling-group-name "$ASG_NAME" --policy-name feastflow-cpu-50 \
  --policy-type TargetTrackingScaling --estimated-instance-warmup 120 \
  --target-tracking-configuration \
  '{"TargetValue":50.0,"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"}}' >/dev/null

log "ALB: http://$ALB_DNS   (targets need a few minutes to boot and turn healthy)"
log "check: aws elbv2 describe-target-health --target-group-arn $TG_ARN"
log "admin login: $ADMIN_EMAIL / $ADMIN_PASSWORD   (stored in infra/.state.env)"
