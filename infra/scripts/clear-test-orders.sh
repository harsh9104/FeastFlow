#!/usr/bin/env bash
# Cancel leftover load-test orders. Locust places real orders, and a 20-minute festival run
# leaves thousands waiting for the 20 riders, which would keep real customers' orders behind
# them for hours. Only synthetic orders (load-test accounts / festival burst) that haven't left
# the kitchen are cancelled; real orders and orders already out for delivery are untouched.
# Runs inside the app container through SSM (RDS is private). Usage: ./clear-test-orders.sh
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${ASG_NAME:?run 05 first}"

IID="$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" \
  --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`]|[0].InstanceId' --output text)"
[ "$IID" != "None" ] || { echo "no running app instance (stack parked? run ./start.sh)"; exit 1; }

PY="$(base64 -w0 <<'EOF'
from sqlalchemy import text
from app.db.session import engine
with engine.begin() as c:
    n = c.execute(text(
        "UPDATE orders SET status='CANCELLED', stage_due_at=NULL "
        "WHERE is_synthetic=1 AND status IN ('PLACED','CONFIRMED','PREPARING','AWAITING_PARTNER')"
    )).rowcount
    left = dict(c.execute(text(
        "SELECT status, COUNT(*) FROM orders WHERE status NOT IN ('DELIVERED','CANCELLED') GROUP BY status"
    )).all())
print(f"cancelled {n} test orders; still active: {left or 'none'}")
EOF
)"
CMD="echo $PY | base64 -d > /tmp/clear.py && docker cp /tmp/clear.py feastflow-api:/tmp/clear.py && docker exec -e PYTHONPATH=/app feastflow-api python /tmp/clear.py"
PARAMS="$("$PYTHON" -c 'import json,sys; print(json.dumps({"commands":[sys.argv[1]]}))' "$CMD")"
CID="$(aws ssm send-command --instance-ids "$IID" --document-name AWS-RunShellScript \
  --parameters "$PARAMS" --query Command.CommandId --output text)"
aws ssm wait command-executed --command-id "$CID" --instance-id "$IID" 2>/dev/null || true
OUT="$(aws ssm get-command-invocation --command-id "$CID" --instance-id "$IID" \
  --query '[StandardOutputContent,StandardErrorContent]' --output text)"
log "$OUT"
