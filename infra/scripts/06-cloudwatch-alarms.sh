#!/usr/bin/env bash
# CloudWatch alarms + a "FeastFlow" dashboard. Alarms notify an admin SNS topic.
# Optional: ALERT_EMAIL=you@example.com ./06-cloudwatch-alarms.sh  (confirm the email AWS sends)
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${LB_ARN:?run 05 first}"; : "${TG_ARN:?run 05 first}"

LB_DIM="${LB_ARN#*:loadbalancer/}"   # app/feastflow-alb/abc123
TG_DIM="${TG_ARN##*:}"               # targetgroup/feastflow-tg/abc123

ALERTS_TOPIC="$(aws sns create-topic --name "$ALERTS_TOPIC_NAME" --tags Key=Project,Value="$PROJECT" --query TopicArn --output text)"
save ALERTS_TOPIC_ARN "$ALERTS_TOPIC"
if [ -n "${ALERT_EMAIL:-}" ]; then
  aws sns subscribe --topic-arn "$ALERTS_TOPIC" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
  log "subscribed $ALERT_EMAIL to $ALERTS_TOPIC_NAME (click the confirmation link in the email)"
fi
ACTIONS=(--alarm-actions "$ALERTS_TOPIC" --ok-actions "$ALERTS_TOPIC")

alarm() {  # alarm NAME DESCRIPTION args...
  local name="$1" desc="$2"; shift 2
  aws cloudwatch put-metric-alarm --alarm-name "$name" --alarm-description "$desc" \
    --treat-missing-data notBreaching "${ACTIONS[@]}" "$@"
  log "alarm $name"
}

ALB_DIMS="Name=LoadBalancer,Value=$LB_DIM"
TG_DIMS="Name=TargetGroup,Value=$TG_DIM Name=LoadBalancer,Value=$LB_DIM"

# The ASG scales on its own target-tracking alarms at 60 %; this one tells a human
# that CPU stayed high even after scaling (e.g. already at max 4 instances).
alarm feastflow-high-cpu "ASG average CPU > 80% for 5 min" \
  --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=AutoScalingGroupName,Value="$ASG_NAME" \
  --statistic Average --period 60 --evaluation-periods 5 --datapoints-to-alarm 5 \
  --threshold 80 --comparison-operator GreaterThanThreshold

alarm feastflow-orders-backlog "More than 200 standard orders waiting for 5 min" \
  --namespace AWS/SQS --metric-name ApproximateNumberOfMessagesVisible --dimensions Name=QueueName,Value="$SQS_STANDARD_QUEUE" \
  --statistic Maximum --period 60 --evaluation-periods 5 --datapoints-to-alarm 5 \
  --threshold 200 --comparison-operator GreaterThanThreshold

alarm feastflow-prime-backlog "More than 50 Prime orders waiting for 3 min" \
  --namespace AWS/SQS --metric-name ApproximateNumberOfMessagesVisible --dimensions Name=QueueName,Value="$SQS_PRIME_QUEUE" \
  --statistic Maximum --period 60 --evaluation-periods 3 --datapoints-to-alarm 3 \
  --threshold 50 --comparison-operator GreaterThanThreshold

for q in "$SQS_PRIME_QUEUE" "$SQS_STANDARD_QUEUE"; do
  alarm "feastflow-dlq-$q" "Orders failed 5 times and landed in $q-dlq" \
    --namespace AWS/SQS --metric-name ApproximateNumberOfMessagesVisible --dimensions Name=QueueName,Value="$q-dlq" \
    --statistic Maximum --period 60 --evaluation-periods 1 \
    --threshold 0 --comparison-operator GreaterThanThreshold
done

# shellcheck disable=SC2086
alarm feastflow-unhealthy-hosts "At least one unhealthy target" \
  --namespace AWS/ApplicationELB --metric-name UnHealthyHostCount --dimensions $TG_DIMS \
  --statistic Maximum --period 60 --evaluation-periods 3 --datapoints-to-alarm 3 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold

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
 {"Id":"rate","Expression":"IF(reqs > 0, 100*FILL(errs,0)/reqs, 0)","Label":"5xx percent","ReturnData":true},
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

# ---- dashboard -----------------------------------------------------------
widget() {  # widget X Y TITLE METRICS_JSON [STAT]
  printf '{"type":"metric","x":%s,"y":%s,"width":12,"height":6,"properties":{"title":"%s","region":"%s","view":"timeSeries","stat":"%s","period":60,"metrics":%s}}' \
    "$1" "$2" "$3" "$REGION" "${5:-Average}" "$4"
}
BODY="{\"widgets\":[
$(widget 0 0 'ASG CPU % (scales at 60)' "[[\"AWS/EC2\",\"CPUUtilization\",\"AutoScalingGroupName\",\"$ASG_NAME\"]]"),
$(widget 12 0 'Instances in service' "[[\"AWS/AutoScaling\",\"GroupInServiceInstances\",\"AutoScalingGroupName\",\"$ASG_NAME\"],[\".\",\"GroupDesiredCapacity\",\".\",\".\"]]" Maximum),
$(widget 0 6 'Orders waiting in SQS' "[[\"AWS/SQS\",\"ApproximateNumberOfMessagesVisible\",\"QueueName\",\"$SQS_PRIME_QUEUE\"],[\".\",\".\",\".\",\"$SQS_STANDARD_QUEUE\"]]" Maximum),
$(widget 12 6 'ALB requests and 5xx' "[[\"AWS/ApplicationELB\",\"RequestCount\",\"LoadBalancer\",\"$LB_DIM\"],[\".\",\"HTTPCode_Target_5XX_Count\",\".\",\".\"]]" Sum),
$(widget 0 12 'ALB response time p90 (s)' "[[\"AWS/ApplicationELB\",\"TargetResponseTime\",\"LoadBalancer\",\"$LB_DIM\"]]" p90),
$(widget 12 12 'RDS CPU % and connections' "[[\"AWS/RDS\",\"CPUUtilization\",\"DBInstanceIdentifier\",\"$DB_ID\"],[\".\",\"DatabaseConnections\",\".\",\".\"]]"),
$(widget 0 18 'Memory % (CloudWatch agent)' "[[\"CWAgent\",\"mem_used_percent\",\"AutoScalingGroupName\",\"$ASG_NAME\"]]")
]}"
aws cloudwatch put-dashboard --dashboard-name "$DASHBOARD_NAME" --dashboard-body "$BODY" >/dev/null
log "dashboard: https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=${DASHBOARD_NAME}"
