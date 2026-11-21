#!/usr/bin/env bash
# Replace the app instances so they pick up the newest image (after ./02b-push-image.sh) and
# launch-template settings (after re-running 05). Learner Lab denies StartInstanceRefresh, so
# this rolls by hand: add as many new instances as are running now, wait until they are healthy
# in the target group, then terminate the old ones. No downtime.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${ASG_NAME:?run 05 first}"; : "${TG_ARN:?run 05 first}"

asg() { aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" --query "AutoScalingGroups[0].$1" --output text; }
OLD="$(asg 'Instances[?LifecycleState==`InService`].InstanceId')"
N="$(wc -w <<<"$OLD")"
MAX="$(asg MaxSize)"
[ "$N" -gt 0 ] || { log "no running instances (stack parked?); nothing to replace"; exit 0; }

TARGET=$(( N * 2 )); [ "$TARGET" -le "$MAX" ] || TARGET="$MAX"
[ "$TARGET" -gt "$N" ] || { echo "ASG is at max ($MAX): lower the load or raise ASG_MAX first"; exit 1; }
aws autoscaling update-auto-scaling-group --auto-scaling-group-name "$ASG_NAME" --max-size "$MAX" --desired-capacity "$TARGET"
log "old instance(s): $OLD; launching $(( TARGET - N )) new one(s), waiting until healthy (~4-6 min)..."

for _ in $(seq 1 60); do
  NEW_HEALTHY=0
  for id in $(aws elbv2 describe-target-health --target-group-arn "$TG_ARN" \
      --query 'TargetHealthDescriptions[?TargetHealth.State==`healthy`].Target.Id' --output text); do
    grep -qw "$id" <<<"$OLD" || NEW_HEALTHY=$(( NEW_HEALTHY + 1 ))
  done
  [ "$NEW_HEALTHY" -ge $(( TARGET - N )) ] && break
  sleep 10
done
[ "$NEW_HEALTHY" -ge $(( TARGET - N )) ] || { echo "new instances did not turn healthy in 10 min; old ones kept. See README troubleshooting."; exit 1; }

for id in $OLD; do
  aws autoscaling terminate-instance-in-auto-scaling-group --instance-id "$id" --should-decrement-desired-capacity >/dev/null
done
log "new instance(s) healthy; terminated old: $OLD (the ALB drains them for 30 s)"
