#!/usr/bin/env bash
# Park everything to save credit: ASG -> 0, Locust stopped, RDS stopped (via the Lambda).
# Data is kept. The ALB, S3, SQS and ECR stay (they cost little or nothing when idle,
# except the ALB at ~$0.02/h; use 99-teardown.sh after grading).
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
OUT="$(mktemp)"
aws lambda invoke --function-name "$LAMBDA_NAME" --cli-binary-format raw-in-base64-out \
  --payload '{"action":"stop"}' "$(command -v cygpath >/dev/null && cygpath -m "$OUT" || echo "$OUT")" >/dev/null
cat "$OUT"; echo; rm -f "$OUT"
log "stack parked. Resume with ./start.sh"
