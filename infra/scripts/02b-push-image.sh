#!/usr/bin/env bash
# Build the single FeastFlow image and push it to ECR as :latest and :<version>.
# Usage: VERSION=1.0.0 ./02b-push-image.sh   (default: git short sha, else timestamp)
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"

VERSION="${VERSION:-$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker build --build-arg APP_VERSION="$VERSION" -t "$ECR_IMAGE:$VERSION" -t "$ECR_IMAGE:latest" "$REPO_DIR"
docker push "$ECR_IMAGE:$VERSION"
docker push "$ECR_IMAGE:latest"
save APP_VERSION "$VERSION"
log "pushed $ECR_IMAGE:$VERSION"
