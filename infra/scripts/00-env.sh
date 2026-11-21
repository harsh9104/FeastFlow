#!/usr/bin/env bash
# Shared environment + helpers. Sourced by every script; safe to source repeatedly.
# Requires: AWS CLI v2 with Learner Lab credentials (AWS Details panel), Docker, openssl, python.
set -euo pipefail

export MSYS_NO_PATHCONV=1   # Git Bash on Windows: stop it rewriting "/feastflow/app" style args
export AWS_PAGER=""
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
REGION="$AWS_DEFAULT_REGION"
PROJECT="FeastFlow"

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$INFRA_DIR/.." && pwd)"
STATE_FILE="$INFRA_DIR/.state.env"   # git-ignored: resource ids + generated secrets
touch "$STATE_FILE"
# Secrets come only from the state file. A shell that loaded backend/.env would otherwise leak
# its local placeholders (ChangeMe123!, change-me) into the deployment.
unset DB_PASSWORD JWT_SECRET ADMIN_EMAIL ADMIN_PASSWORD LOADTEST_PASSWORD
# shellcheck disable=SC1090
source "$STATE_FILE"

save() {  # save KEY VALUE -> persists in the state file and exports it
  { grep -v "^$1=" "$STATE_FILE" || true; } > "$STATE_FILE.tmp"
  printf '%s="%s"\n' "$1" "$2" >> "$STATE_FILE.tmp"
  mv "$STATE_FILE.tmp" "$STATE_FILE"
  export "$1=$2"
}
log() { printf '\033[1;34m[%s]\033[0m %s\n' "$(basename "${0:-env}")" "$*"; }
tag_spec() { printf 'ResourceType=%s,Tags=[{Key=Project,Value=%s},{Key=Name,Value=%s}]' "$1" "$PROJECT" "$2"; }

command -v aws >/dev/null || { echo "aws CLI not found. Install AWS CLI v2 first."; exit 1; }
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)" || {
  echo "AWS credentials missing/expired. Start the lab, then paste fresh ones from"
  echo "Learner Lab > AWS Details > AWS CLI into ~/.aws/credentials."; exit 1; }
PYTHON="$(command -v python3 || command -v python || true)"

# ---- names (the app's queue/topic names match .env.example) ------------
BUCKET="feastflow-${ACCOUNT_ID}-assets"
ECR_REPO="feastflow"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_IMAGE="${ECR_REGISTRY}/${ECR_REPO}"
DB_ID="feastflow-db"
DB_SUBNET_GROUP="feastflow-db-subnets"
ASG_NAME="feastflow-asg"
LT_NAME="feastflow-lt"
ALB_NAME="feastflow-alb"
TG_NAME="feastflow-tg"
LOG_GROUP="/feastflow/app"
SQS_PRIME_QUEUE="orders-prime"
SQS_STANDARD_QUEUE="orders-standard"
SNS_TOPIC_NAME="order-notifications"
ALERTS_TOPIC_NAME="feastflow-alerts"
LAMBDA_NAME="feastflow-auto-stop"
SCHEDULE_NAME="feastflow-nightly-stop"
DASHBOARD_NAME="FeastFlow"
INSTANCE_PROFILE="LabInstanceProfile"           # Learner Lab can't create roles: reuse LabRole
LAB_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/LabRole"

# ---- default VPC + two public subnets in distinct AZs ------------------
if [ -z "${VPC_ID:-}" ]; then
  VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
  [ "$VPC_ID" != "None" ] || { echo "No default VPC found."; exit 1; }
  save VPC_ID "$VPC_ID"
fi
if [ -z "${SUBNET_A:-}" ]; then
  save SUBNET_A "$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" Name=availability-zone,Values="${REGION}a" \
    --query 'Subnets[0].SubnetId' --output text)"
  save SUBNET_B "$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" Name=availability-zone,Values="${REGION}b" \
    --query 'Subnets[0].SubnetId' --output text)"
fi
ALL_SUBNETS="$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" --query 'Subnets[].SubnetId' --output text)"

# ---- secrets (generated once, kept in .state.env) ----------------------
[ -n "${DB_PASSWORD:-}" ]       || save DB_PASSWORD "$(openssl rand -hex 16)"
[ -n "${JWT_SECRET:-}" ]        || save JWT_SECRET "$(openssl rand -hex 32)"
[ -n "${ADMIN_EMAIL:-}" ]       || save ADMIN_EMAIL "admin@feastflow.app"
[ -n "${ADMIN_PASSWORD:-}" ]    || save ADMIN_PASSWORD "$(openssl rand -hex 8)Aa1!"
[ -n "${LOADTEST_PASSWORD:-}" ] || save LOADTEST_PASSWORD "$(openssl rand -hex 16)"   # app (05) + Locust (08)

latest_al2023_ami() {
  aws ec2 describe-images --owners amazon \
    --filters 'Name=name,Values=al2023-ami-2023.*-x86_64' Name=state,Values=available \
    --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text
}

# Idempotent ingress helper: ignores "already exists".
allow() {  # allow SG_ID PORT (--cidr X | --source-group Y)
  local sg="$1" port="$2"; shift 2
  local err; err="$(aws ec2 authorize-security-group-ingress --group-id "$sg" --protocol tcp --port "$port" "$@" 2>&1 >/dev/null)" \
    || { echo "$err" | grep -q 'InvalidPermission.Duplicate' || { echo "$err"; return 1; }; }
}
