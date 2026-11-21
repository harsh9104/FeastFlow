#!/usr/bin/env bash
# Cost guard: a Lambda that parks the stack (ASG -> 0, Locust EC2 stopped, RDS stopped),
# run every night by EventBridge Scheduler (falls back to an EventBridge rule if the lab
# blocks Scheduler). Both run as LabRole.
#   STOP_CRON   default "cron(0 23 * * ? *)" = 23:00 in STOP_TZ
#   STOP_TZ     default Asia/Kolkata (Scheduler only; rules always use UTC)
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${ASG_NAME:?run 05 first}"
[ -n "$PYTHON" ] || { echo "python is needed to zip the Lambda code"; exit 1; }

STOP_CRON="${STOP_CRON:-cron(0 23 * * ? *)}"
STOP_TZ="${STOP_TZ:-Asia/Kolkata}"

# ---- package + deploy ---------------------------------------------------
BUILD_DIR="$(mktemp -d)"
ZIP="$BUILD_DIR/auto_stop.zip"
SRC="$INFRA_DIR/lambda/auto_stop.py"
if command -v cygpath >/dev/null; then   # Git Bash: Windows paths for python.exe / aws.exe
  ZIP="$(cygpath -m "$ZIP")"; SRC="$(cygpath -m "$SRC")"
fi
"$PYTHON" - "$SRC" "$ZIP" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[2], "w", zipfile.ZIP_DEFLATED) as z:
    z.write(sys.argv[1], "auto_stop.py")
PY
ZIP_ARG="fileb://$ZIP"
ENV_VARS="Variables={ASG_NAME=$ASG_NAME,DB_ID=$DB_ID,PROJECT=$PROJECT,ASG_MIN=${ASG_MIN:-1}}"

if aws lambda get-function --function-name "$LAMBDA_NAME" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$LAMBDA_NAME" --zip-file "$ZIP_ARG" >/dev/null
  aws lambda wait function-updated --function-name "$LAMBDA_NAME"
  aws lambda update-function-configuration --function-name "$LAMBDA_NAME" --environment "$ENV_VARS" >/dev/null
  log "updated Lambda $LAMBDA_NAME"
else
  aws lambda create-function --function-name "$LAMBDA_NAME" --runtime python3.12 \
    --handler auto_stop.handler --role "$LAB_ROLE_ARN" --zip-file "$ZIP_ARG" \
    --timeout 30 --memory-size 128 --environment "$ENV_VARS" \
    --tags Project="$PROJECT" >/dev/null
  log "created Lambda $LAMBDA_NAME"
fi
aws lambda wait function-active --function-name "$LAMBDA_NAME"
rm -rf "$BUILD_DIR"
LAMBDA_ARN="$(aws lambda get-function --function-name "$LAMBDA_NAME" --query Configuration.FunctionArn --output text)"
save LAMBDA_ARN "$LAMBDA_ARN"

# ---- nightly schedule ---------------------------------------------------
TARGET="{\"Arn\":\"$LAMBDA_ARN\",\"RoleArn\":\"$LAB_ROLE_ARN\",\"Input\":\"{\\\"action\\\":\\\"stop\\\"}\"}"
sched_args=(--name "$SCHEDULE_NAME" --schedule-expression "$STOP_CRON" --schedule-expression-timezone "$STOP_TZ"
            --flexible-time-window Mode=OFF --target "$TARGET")
if aws scheduler get-schedule --name "$SCHEDULE_NAME" >/dev/null 2>&1 \
   && aws scheduler update-schedule "${sched_args[@]}" >/dev/null 2>&1; then
  save SCHEDULE_KIND scheduler; log "updated EventBridge schedule: $STOP_CRON $STOP_TZ"
elif aws scheduler create-schedule "${sched_args[@]}" >/dev/null 2>&1; then
  save SCHEDULE_KIND scheduler; log "created EventBridge schedule: $STOP_CRON $STOP_TZ"
else
  log "EventBridge Scheduler unavailable, using an EventBridge rule (UTC)"
  RULE_CRON="${RULE_CRON:-cron(30 17 * * ? *)}"   # 17:30 UTC = 23:00 IST
  RULE_ARN="$(aws events put-rule --name "$SCHEDULE_NAME" --schedule-expression "$RULE_CRON" \
    --tags Key=Project,Value="$PROJECT" --query RuleArn --output text)"
  aws lambda add-permission --function-name "$LAMBDA_NAME" --statement-id feastflow-nightly \
    --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$RULE_ARN" >/dev/null 2>&1 || true
  aws events put-targets --rule "$SCHEDULE_NAME" \
    --targets "[{\"Id\":\"1\",\"Arn\":\"$LAMBDA_ARN\",\"Input\":\"{\\\"action\\\":\\\"stop\\\"}\"}]" >/dev/null
  save SCHEDULE_KIND rule; log "rule $SCHEDULE_NAME: $RULE_CRON"
fi
log "test it now with ./stop.sh (park) and ./start.sh (resume)"
