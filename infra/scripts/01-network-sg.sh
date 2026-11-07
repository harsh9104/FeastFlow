#!/usr/bin/env bash
# Security groups (network-level least privilege, doc 02). No SSH is opened.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"

mk_sg() {  # mk_sg NAME DESCRIPTION -> prints id
  local id
  id="$(aws ec2 describe-security-groups --filters Name=group-name,Values="$1" Name=vpc-id,Values="$VPC_ID" \
        --query 'SecurityGroups[0].GroupId' --output text)"
  if [ "$id" = "None" ]; then
    id="$(aws ec2 create-security-group --group-name "$1" --description "$2" --vpc-id "$VPC_ID" \
          --tag-specifications "$(tag_spec security-group "$1")" --query GroupId --output text)"
  fi
  echo "$id"
}

save SG_ALB    "$(mk_sg feastflow-sg-alb    'FeastFlow ALB: HTTP from internet')"
save SG_APP    "$(mk_sg feastflow-sg-app    'FeastFlow app: 8000 from ALB only')"
save SG_RDS    "$(mk_sg feastflow-sg-rds    'FeastFlow RDS: 5432 from app only')"
save SG_LOCUST "$(mk_sg feastflow-sg-locust 'FeastFlow Locust: 8089 from app')"

allow "$SG_ALB" 80   --cidr 0.0.0.0/0
allow "$SG_APP" 8000 --source-group "$SG_ALB"
allow "$SG_RDS" 5432 --source-group "$SG_APP"
allow "$SG_LOCUST" 8089 --source-group "$SG_APP"
if [ -n "${MY_IP:-}" ]; then   # optional: reach the Locust UI from your machine, e.g. MY_IP=1.2.3.4
  allow "$SG_LOCUST" 8089 --cidr "${MY_IP}/32"
fi
log "security groups ready: alb=$SG_ALB app=$SG_APP rds=$SG_RDS locust=$SG_LOCUST"
