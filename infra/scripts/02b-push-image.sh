#!/usr/bin/env bash
# Build the FeastFlow image (React build + API + worker) and push it to ECR.
# Usage: ./02b-push-image.sh   (tag = git short sha; VERSION=x overrides)
# To roll a new image out to running instances afterwards: ./redeploy.sh
source "$(dirname "${BASH_SOURCE[0]}")/00-env.sh"

docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop first."; exit 1; }
VERSION="${VERSION:-$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_REGISTRY"
BUILD_CTX="$REPO_DIR"
command -v cygpath >/dev/null && BUILD_CTX="$(cygpath -m "$REPO_DIR")"   # Git Bash: Windows path for docker.exe
# EC2 is x86_64; --platform keeps this right even when building on an ARM laptop.
docker build --platform linux/amd64 -t "$ECR_IMAGE:$VERSION" -t "$ECR_IMAGE:latest" "$BUILD_CTX"
docker push "$ECR_IMAGE:$VERSION"
docker push "$ECR_IMAGE:latest"
save APP_VERSION "$VERSION"
log "pushed $ECR_IMAGE:$VERSION (and :latest)"
