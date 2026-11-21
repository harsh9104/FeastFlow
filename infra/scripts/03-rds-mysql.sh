#!/usr/bin/env bash
# RDS MySQL 8.4, db.t3.micro, 20 GB gp3, single-AZ, private. First run takes ~5-10 min.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${SG_RDS:?run 01-network-sg.sh first}"

if ! aws rds describe-db-subnet-groups --db-subnet-group-name "$DB_SUBNET_GROUP" >/dev/null 2>&1; then
  # shellcheck disable=SC2086
  aws rds create-db-subnet-group --db-subnet-group-name "$DB_SUBNET_GROUP" \
    --db-subnet-group-description "FeastFlow DB subnets" --subnet-ids $ALL_SUBNETS \
    --tags Key=Project,Value="$PROJECT" >/dev/null
fi

if aws rds describe-db-instances --db-instance-identifier "$DB_ID" >/dev/null 2>&1; then
  log "RDS instance $DB_ID already exists"
  STATE="$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" --query 'DBInstances[0].DBInstanceStatus' --output text)"
  if [ "$STATE" = "stopped" ]; then
    aws rds start-db-instance --db-instance-identifier "$DB_ID" >/dev/null
    log "it was stopped: starting it"
  fi
else
  ENGINE_VERSION="$(aws rds describe-db-engine-versions --engine mysql --engine-version 8.4 --default-only \
    --query 'DBEngineVersions[0].EngineVersion' --output text)"
  aws rds create-db-instance --db-instance-identifier "$DB_ID" \
    --engine mysql --engine-version "$ENGINE_VERSION" --db-instance-class db.t3.micro \
    --allocated-storage 20 --storage-type gp3 \
    --master-username feastflow --master-user-password "$DB_PASSWORD" --db-name feastflow \
    --db-subnet-group-name "$DB_SUBNET_GROUP" --vpc-security-group-ids "$SG_RDS" \
    --no-publicly-accessible --no-multi-az --backup-retention-period 1 \
    --tags Key=Project,Value="$PROJECT" >/dev/null
  log "creating RDS MySQL $ENGINE_VERSION (waiting until available, ~5-10 min)..."
fi
aws rds wait db-instance-available --db-instance-identifier "$DB_ID"
save DB_HOST "$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)"
log "RDS ready at $DB_HOST"
