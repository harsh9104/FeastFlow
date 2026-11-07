#!/usr/bin/env bash
# CloudWatch alarms from doc 02. Optional SNS email: ALERT_EMAIL=you@example.com ./05-alarms-sns.sh
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${LB_ARN:?run 04 first}"; : "${TG_ARN:?run 04 first}"

LB_DIM="${LB_ARN#*:loadbalancer/}"   # app/feastflow-alb/abc123
TG_DIM="${TG_ARN##*:}"               # targetgroup/feastflow-tg/abc123

ACTIONS=()
if [ -n "${ALERT_EMAIL:-}" ]; then
  TOPIC="$(aws sns create-topic --name feastflow-alerts --tags Key=Project,Value="$PROJECT" --query TopicArn --output text)"
  aws sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
  ACTIONS=(--alarm-actions "$TOPIC" --ok-actions "$TOPIC")
  log "SNS topic $TOPIC (confirm the subscription email)"
fi

alarm() {  # alarm NAME DESCRIPTION args...
  local name="$1" desc="$2"; shift 2
  aws cloudwatch put-metric-alarm --alarm-name "$name" --alarm-description "$desc" \
    --treat-missing-data notBreaching "${ACTIONS[@]}" "$@"
  log "alarm $name"
}

ALB_DIMS="Name=LoadBalancer,Value=$LB_DIM"
TG_DIMS="Name=TargetGroup,Value=$TG_DIM Name=LoadBalancer,Value=$LB_DIM"

alarm feastflow-high-cpu "ASG average CPU > 75%" \
  --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=AutoScalingGroupName,Value="$ASG_NAME" \
  --statistic Average --period 60 --evaluation-periods 3 --datapoints-to-alarm 3 \
  --threshold 75 --comparison-operator GreaterThanThreshold

# shellcheck disable=SC2086
alarm feastflow-unhealthy-hosts "At least one unhealthy target" \
  --namespace AWS/ApplicationELB --metric-name UnHealthyHostCount --dimensions $TG_DIMS \
  --statistic Maximum --period 60 --evaluation-periods 2 --datapoints-to-alarm 2 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold

# shellcheck disable=SC2086
alarm feastflow-high-latency "Target response time p90 > 1s" \
  --namespace AWS/ApplicationELB --metric-name TargetResponseTime --dimensions $ALB_DIMS \
  --extended-statistic p90 --period 60 --evaluation-periods 3 --datapoints-to-alarm 3 \
  --threshold 1.0 --comparison-operator GreaterThanThreshold

alarm feastflow-high-memory "Average memory > 85%" \
  --namespace CWAgent --metric-name mem_used_percent --dimensions Name=AutoScalingGroupName,Value="$ASG_NAME" \
  --statistic Average --period 60 --evaluation-periods 3 --datapoints-to-alarm 3 \
  --threshold 85 --comparison-operator GreaterThanThreshold

alarm feastflow-rds-cpu "RDS CPU > 80%" \
  --namespace AWS/RDS --metric-name CPUUtilization --dimensions Name=DBInstanceIdentifier,Value="$DB_ID" \
  --statistic Average --period 60 --evaluation-periods 5 --datapoints-to-alarm 5 \
  --threshold 80 --comparison-operator GreaterThanThreshold

# 5xx rate (%) via metric math
METRICS="$(cat <<EOF
[
 {"Id":"rate","Expression":"100*errs/reqs","Label":"5xx percent","ReturnData":true},
 {"Id":"errs","ReturnData":false,"MetricStat":{"Period":60,"Stat":"Sum","Metric":{"Namespace":"AWS/ApplicationELB",
   "MetricName":"HTTPCode_Target_5XX_Count","Dimensions":[{"Name":"LoadBalancer","Value":"$LB_DIM"}]}}},
 {"Id":"reqs","ReturnData":false,"MetricStat":{"Period":60,"Stat":"Sum","Metric":{"Namespace":"AWS/ApplicationELB",
   "MetricName":"RequestCount","Dimensions":[{"Name":"LoadBalancer","Value":"$LB_DIM"}]}}}
]
EOF
)"
alarm feastflow-5xx-rate "5xx responses > 5% of requests" \
  --metrics "$METRICS" --evaluation-periods 3 --datapoints-to-alarm 3 \
  --threshold 5 --comparison-operator GreaterThanThreshold
