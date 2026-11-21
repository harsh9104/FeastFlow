#!/usr/bin/env bash
# Order queues (Prime + standard, each with a dead-letter queue) and the customer
# notification topic. Same layout as infra/localstack/init-aws.sh uses locally.
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"

queue_arn() {  # queue_arn URL
  aws sqs get-queue-attributes --queue-url "$1" --attribute-names QueueArn --query Attributes.QueueArn --output text
}

for q in "$SQS_PRIME_QUEUE" "$SQS_STANDARD_QUEUE"; do
  dlq_url="$(aws sqs create-queue --queue-name "$q-dlq" --tags Project="$PROJECT" \
    --attributes MessageRetentionPeriod=1209600 --query QueueUrl --output text)"
  dlq_arn="$(queue_arn "$dlq_url")"
  redrive="{\"deadLetterTargetArn\":\"$dlq_arn\",\"maxReceiveCount\":\"5\"}"
  attrs="$("$PYTHON" -c 'import json,sys; print(json.dumps({"VisibilityTimeout":"60","ReceiveMessageWaitTimeSeconds":"0","RedrivePolicy":sys.argv[1]}))' "$redrive")"
  url="$(aws sqs create-queue --queue-name "$q" --tags Project="$PROJECT" --query QueueUrl --output text)"
  aws sqs set-queue-attributes --queue-url "$url" --attributes "$attrs"   # also updates an existing queue
  log "queue $q (+ $q-dlq) ready"
done

save SNS_TOPIC_ARN "$(aws sns create-topic --name "$SNS_TOPIC_NAME" --tags Key=Project,Value="$PROJECT" \
  --query TopicArn --output text)"
log "SNS topic $SNS_TOPIC_ARN ready (customers are subscribed by the app when they register)"
