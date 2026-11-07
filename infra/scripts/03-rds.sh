#!/usr/bin/env bash
# RDS PostgreSQL 16, db.t3.micro, single-AZ, private. Takes ~5-10 min on first run.
# If RDS is blocked in your lab, see docs/12 (L-09): run postgres:16 on a dedicated EC2 and
# set DB_HOST manually in .state.env instead.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"

SUBNET_GROUP="feastflow-db-subnets"
if ! aws rds describe-db-subnet-groups --db-subnet-group-name "$SUBNET_GROUP" >/dev/null 2>&1; then
  # shellcheck disable=SC2086
  aws rds create-db-subnet-group --db-subnet-group-name "$SUBNET_GROUP" \
    --db-subnet-group-description "FeastFlow DB subnets" --subnet-ids $ALL_SUBNETS \
    --tags Key=Project,Value="$PROJECT" >/dev/null
fi

if aws rds describe-db-instances --db-instance-identifier "$DB_ID" >/dev/null 2>&1; then
  log "RDS instance $DB_ID already exists"
else
  aws rds create-db-instance --db-instance-identifier "$DB_ID" \
    --engine postgres --engine-version 16 --db-instance-class db.t3.micro \
    --allocated-storage 20 --storage-type gp3 \
    --master-username feastflow --master-user-password "$DB_PASSWORD" --db-name feastflow \
    --db-subnet-group-name "$SUBNET_GROUP" --vpc-security-group-ids "$SG_RDS" \
    --no-publicly-accessible --no-multi-az --backup-retention-period 1 \
    --tags Key=Project,Value="$PROJECT" >/dev/null
  log "creating RDS instance (waiting until available)..."
fi
aws rds wait db-instance-available --db-instance-identifier "$DB_ID"
save DB_HOST "$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)"
log "RDS ready at $DB_HOST"
