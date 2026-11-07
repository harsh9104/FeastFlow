#!/usr/bin/env bash
# Locust load generator on its own t3.small (outside the ASG so it doesn't skew the scaling metric).
# Installs the real loadtest/locustfile.py. Run this BEFORE 04: the app instances need Locust's
# private IP (LOCUST_URL), and the app tells Locust the ALB address with each swarm request,
# so Locust itself does not need to know the ALB.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"
: "${SG_LOCUST:?run 01-network-sg.sh first}"

EXISTING="$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values=feastflow-locust Name=instance-state-name,Values=pending,running,stopped,stopping \
  --query 'Reservations[].Instances[].InstanceId' --output text)"
if [ -n "$EXISTING" ]; then
  log "Locust instance already exists: $EXISTING (start it with: aws ec2 start-instances --instance-ids $EXISTING)"
  save LOCUST_INSTANCE_ID "$EXISTING"
  save LOCUST_PRIVATE_IP "$(aws ec2 describe-instances --instance-ids "$EXISTING" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
  exit 0
fi

# Ship the real locustfile inside user-data (base64 avoids any quoting problems).
LOCUSTFILE_B64="$(base64 < "$REPO_DIR/loadtest/locustfile.py" | tr -d '\n')"

AMI_ID="$(aws ec2 describe-images --owners amazon \
  --filters 'Name=name,Values=al2023-ami-2023.*-x86_64' Name=state,Values=available \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)"

USER_DATA="$(cat <<EOF
#!/bin/bash
set -ex
dnf install -y python3-pip
pip3 install locust==2.32.4
mkdir -p /opt/locust
echo '$LOCUSTFILE_B64' | base64 -d > /opt/locust/locustfile.py
cat > /etc/systemd/system/locust.service <<'UNIT'
[Unit]
Description=Locust
After=network-online.target
[Service]
Environment=LOADTEST_PASSWORD=$LOADTEST_PASSWORD
ExecStart=/usr/local/bin/locust -f /opt/locust/locustfile.py --web-host 0.0.0.0 --web-port 8089
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now locust
EOF
)"

IID="$(aws ec2 run-instances --image-id "$AMI_ID" --instance-type t3.small \
  --subnet-id "$SUBNET_A" --security-group-ids "$SG_LOCUST" --associate-public-ip-address \
  --iam-instance-profile Name="$INSTANCE_PROFILE" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --user-data "$USER_DATA" \
  --tag-specifications "$(tag_spec instance feastflow-locust)" \
  --query 'Instances[0].InstanceId' --output text)"
save LOCUST_INSTANCE_ID "$IID"
aws ec2 wait instance-running --instance-ids "$IID"
save LOCUST_PRIVATE_IP "$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
log "Locust instance $IID, private IP $LOCUST_PRIVATE_IP (API: http://$LOCUST_PRIVATE_IP:8089)"
