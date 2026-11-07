#!/usr/bin/env bash
# Private S3 bucket (BPA on, SSE-S3, deny non-TLS) and ECR repo with a 10-image lifecycle.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"

if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  log "bucket $BUCKET exists"
else
  aws s3api create-bucket --bucket "$BUCKET" >/dev/null   # us-east-1: no LocationConstraint
  log "created bucket $BUCKET"
fi
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-policy --bucket "$BUCKET" \
  --policy "$(sed "s/__BUCKET__/$BUCKET/g" "$INFRA_DIR/policies/s3-bucket-policy.json")"
aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging "TagSet=[{Key=Project,Value=$PROJECT}]"
save S3_BUCKET "$BUCKET"

if ! aws ecr describe-repositories --repository-names "$ECR_REPO" >/dev/null 2>&1; then
  aws ecr create-repository --repository-name "$ECR_REPO" --tags Key=Project,Value="$PROJECT" >/dev/null
  log "created ECR repo $ECR_REPO"
fi
aws ecr put-lifecycle-policy --repository-name "$ECR_REPO" --lifecycle-policy-text \
  '{"rules":[{"rulePriority":1,"description":"keep last 10","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":10},"action":{"type":"expire"}}]}' >/dev/null
log "S3 + ECR ready ($BUCKET, $ECR_IMAGE)"
