#!/usr/bin/env bash
# Monthly cost budget for the lab account with email alerts (the $50 Learner Lab credit).
#   ALERT_EMAIL=you@example.com ./09-budget.sh
#   BUDGET_USD    default 50
#   Alerts: actual spend > 50 % and > 80 % of the budget, and forecast > 100 %.
# The whole lab account is FeastFlow, so the budget covers all costs (a Project-tag filter would
# need cost allocation tags activated, which Learner Lab doesn't allow). AWS Budgets refreshes
# spend data a few times a day, so alerts lag real usage by hours.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${ALERT_EMAIL:?set ALERT_EMAIL=you@example.com}"

BUDGET_USD="${BUDGET_USD:-50}"
BUDGET="{\"BudgetName\":\"$BUDGET_NAME\",\"BudgetType\":\"COST\",\"TimeUnit\":\"MONTHLY\",\"BudgetLimit\":{\"Amount\":\"$BUDGET_USD\",\"Unit\":\"USD\"}}"
SUBSCRIBER="SubscriptionType=EMAIL,Address=$ALERT_EMAIL"

if aws budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" >/dev/null 2>&1; then
  aws budgets update-budget --account-id "$ACCOUNT_ID" --new-budget "$BUDGET"
  log "budget $BUDGET_NAME updated (\$$BUDGET_USD / month)"
else
  aws budgets create-budget --account-id "$ACCOUNT_ID" --budget "$BUDGET"
  log "budget $BUDGET_NAME created (\$$BUDGET_USD / month)"
fi

notify() {  # notify ACTUAL|FORECASTED PERCENT
  local n="NotificationType=$1,ComparisonOperator=GREATER_THAN,Threshold=$2,ThresholdType=PERCENTAGE"
  local err
  if err="$(aws budgets create-notification --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" \
              --notification "$n" --subscribers "$SUBSCRIBER" 2>&1 >/dev/null)"; then
    log "alert: $1 spend > $2 % -> $ALERT_EMAIL"
  elif echo "$err" | grep -q DuplicateRecord; then   # alert exists: make sure this email is on it
    aws budgets create-subscriber --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" \
      --notification "$n" --subscriber "$SUBSCRIBER" 2>/dev/null || true
    log "alert: $1 spend > $2 % (already there)"
  else
    echo "$err"; return 1
  fi
}
notify ACTUAL 50
notify ACTUAL 80
notify FORECASTED 100
save BUDGET_NAME "$BUDGET_NAME"
log "spend so far: $(aws budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" \
  --query 'Budget.CalculatedSpend.ActualSpend.Amount' --output text 2>/dev/null || echo 'n/a yet') USD"
