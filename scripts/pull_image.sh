#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${1:-}"

if [ -z "$IMAGE_TAG" ]; then
    echo "Usage: $0 <image:tag>"
    exit 1
fi

echo -e "\033[0;36m🔄 Pulling Docker image: ${IMAGE_TAG}...\033[0m"
docker pull "$IMAGE_TAG"
echo -e "\033[0;32m✅ Successfully pulled ${IMAGE_TAG}\033[0m"
