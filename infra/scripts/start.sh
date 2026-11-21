#!/usr/bin/env bash
# Resume after ./stop.sh or the nightly auto-stop: start RDS, wait for it, then bring the
# Locust EC2 and the ASG (min 1) back. The site is up again ~5 min after RDS is available.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
STATUS="$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" --query 'DBInstances[0].DBInstanceStatus' --output text)"
if [ "$STATUS" = "stopped" ]; then
  aws rds start-db-instance --db-instance-identifier "$DB_ID" >/dev/null
  log "starting RDS..."
elif [ "$STATUS" = "stopping" ]; then
  log "RDS is still stopping; waiting for it, then starting it"
  aws rds wait db-instance-stopped --db-instance-identifier "$DB_ID" 2>/dev/null || true
  aws rds start-db-instance --db-instance-identifier "$DB_ID" >/dev/null
fi
aws rds wait db-instance-available --db-instance-identifier "$DB_ID"
log "RDS available"
OUT="$(mktemp)"
aws lambda invoke --function-name "$LAMBDA_NAME" --cli-binary-format raw-in-base64-out \
  --payload '{"action":"start"}' "$(command -v cygpath >/dev/null && cygpath -m "$OUT" || echo "$OUT")" >/dev/null
cat "$OUT"; echo; rm -f "$OUT"
log "site: http://${ALB_DNS:-<run 05>}  (give the instance ~5 min to turn healthy)"
