#!/usr/bin/env bash
# Locust load generator on its own t3.small (outside the ASG so it doesn't skew the scaling
# metric). Runs the official locust image with loadtest/locustfile.py. The app starts and
# stops runs through Locust's web API and sends the ALB address with each start
# (LOADTEST_TARGET), so Locust doesn't need to know it.
# Run it BEFORE 05 so the app's launch template gets LOCUST_URL (Locust's private IP).
# If 05 already ran, re-run 05 and then ./redeploy.sh afterwards.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${SG_LOCUST:?run 01-network-sg.sh first}"

EXISTING="$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values=feastflow-locust Name=instance-state-name,Values=pending,running,stopped,stopping \
  --query 'Reservations[].Instances[].InstanceId' --output text)"
if [ -n "$EXISTING" ]; then
  log "Locust instance already exists: $EXISTING (start it with ./start.sh or aws ec2 start-instances)"
  save LOCUST_INSTANCE_ID "$EXISTING"
  save LOCUST_PRIVATE_IP "$(aws ec2 describe-instances --instance-ids "$EXISTING" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
  exit 0
fi

# Ship the real locustfile inside user-data (base64 avoids any quoting problems).
LOCUSTFILE_B64="$(base64 < "$REPO_DIR/loadtest/locustfile.py" | tr -d '\n')"
LOCUST_IMAGE="$(sed -n 's/^FROM \(locustio\/locust:[^ ]*\).*/\1/p' "$REPO_DIR/loadtest/Dockerfile")"

USER_DATA="$(cat <<EOF
#!/bin/bash
set -ex
exec > >(tee /var/log/feastflow-locust.log) 2>&1
dnf install -y docker
systemctl enable --now docker
mkdir -p /opt/locust
echo '$LOCUSTFILE_B64' | base64 -d > /opt/locust/locustfile.py
chmod 644 /opt/locust/locustfile.py
docker run -d --name locust --restart always -p 8089:8089 \\
  -e LOADTEST_PASSWORD='$LOADTEST_PASSWORD' -e LOADTEST_USERS=200 \\
  -v /opt/locust/locustfile.py:/home/locust/locustfile.py:ro \\
  $LOCUST_IMAGE -f /home/locust/locustfile.py
EOF
)"

IID="$(aws ec2 run-instances --image-id "$(latest_al2023_ami)" --instance-type t3.small \
  --subnet-id "$SUBNET_A" --security-group-ids "$SG_LOCUST" --associate-public-ip-address \
  --iam-instance-profile Name="$INSTANCE_PROFILE" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --user-data "$USER_DATA" \
  --tag-specifications "$(tag_spec instance feastflow-locust)" "$(tag_spec volume feastflow-locust)" \
  --query 'Instances[0].InstanceId' --output text)"
save LOCUST_INSTANCE_ID "$IID"
aws ec2 wait instance-running --instance-ids "$IID"
save LOCUST_PRIVATE_IP "$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
log "Locust instance $IID, private IP $LOCUST_PRIVATE_IP"
if [ -n "${LB_ARN:-}" ]; then   # the ASG already exists: hand the new LOCUST_URL to the app
  log "next: ./05-launch-template-alb-asg.sh && ./redeploy.sh   (so the app gets LOCUST_URL)"
fi
