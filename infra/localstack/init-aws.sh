#!/bin/sh
# Runs inside LocalStack on startup: mirrors the AWS resources we create in P6.
set -e
for q in orders-prime orders-standard; do
  awslocal sqs create-queue --queue-name "$q-dlq" >/dev/null
  dlq_arn=$(awslocal sqs get-queue-attributes --queue-url "http://localhost:4566/000000000000/$q-dlq" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)
  awslocal sqs create-queue --queue-name "$q" --attributes \
    "{\"VisibilityTimeout\":\"60\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$dlq_arn\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}" >/dev/null
done
awslocal sns create-topic --name order-notifications >/dev/null
awslocal s3 mb s3://feastflow-assets >/dev/null
echo "LocalStack resources ready"
