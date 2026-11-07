#!/bin/bash
# Body of the app instance user-data. 04-launch-template-asg-alb.sh prepends a header that exports:
#   REGION ECR_REGISTRY IMAGE DATABASE_URL JWT_SECRET ADMIN_EMAIL ADMIN_PASSWORD S3_BUCKET
#   LOG_GROUP CW_CONFIG ASG_NAME ALB_DIMENSION TG_DIMENSION TG_ARN DB_ID
set -ex
exec > >(tee /var/log/feastflow-userdata.log) 2>&1

dnf install -y docker amazon-cloudwatch-agent
systemctl enable --now docker

# Memory/disk metrics (A-07)
echo "$CW_CONFIG" > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker pull "$IMAGE"

docker run -d --name feastflow-app --restart always -p 8000:8000 \
  --log-driver awslogs \
  --log-opt awslogs-region="$REGION" \
  --log-opt awslogs-group="$LOG_GROUP" \
  --log-opt awslogs-create-group=true \
  -e ENV=production \
  -e AWS_REGION="$REGION" \
  -e DATABASE_URL="$DATABASE_URL" \
  -e DB_POOL_SIZE=3 -e DB_MAX_OVERFLOW=2 -e WEB_CONCURRENCY=2 \
  -e JWT_SECRET="$JWT_SECRET" \
  -e ADMIN_EMAIL="$ADMIN_EMAIL" -e ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  -e S3_BUCKET="$S3_BUCKET" \
  -e METRICS_PROVIDER=cloudwatch -e ASG_NAME="$ASG_NAME" -e ALB_DIMENSION="$ALB_DIMENSION" \
  -e TG_DIMENSION="$TG_DIMENSION" -e TG_ARN="$TG_ARN" -e DB_INSTANCE_ID="$DB_ID" \
  "$IMAGE"
