#!/bin/bash
# Body of the app instance user-data. 05-launch-template-alb-asg.sh prepends a header that
# exports REGION ECR_REGISTRY IMAGE LOG_GROUP CW_CONFIG and APP_ENV_B64 (the container env file).
# Each instance runs two containers from the same image: the API and the order worker,
# so scaling out the ASG also adds order-processing capacity.
set -ex
exec > >(tee /var/log/feastflow-userdata.log) 2>&1

dnf install -y docker amazon-cloudwatch-agent
systemctl enable --now docker

# Memory/disk metrics per ASG
echo "$CW_CONFIG" > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s

mkdir -p /opt/feastflow
echo "$APP_ENV_B64" | base64 -d > /opt/feastflow/app.env
chmod 600 /opt/feastflow/app.env

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker pull "$IMAGE"

run() {  # run NAME [command...]
  local name="$1"; shift
  docker rm -f "$name" 2>/dev/null || true
  docker run -d --name "$name" --restart always --env-file /opt/feastflow/app.env \
    --log-driver awslogs --log-opt awslogs-region="$REGION" --log-opt awslogs-group="$LOG_GROUP" \
    --log-opt awslogs-stream="$name-$(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null || hostname)" \
    "$@"
}
# API first: its entrypoint runs the migrations. The worker restarts until the tables exist.
run feastflow-api -p 8000:8000 "$IMAGE"
run feastflow-worker "$IMAGE" python -m worker.main
