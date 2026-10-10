#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077

: "${CI_COMMIT_SHA:?}"
: "${CI_REGISTRY:?}"
: "${CI_REGISTRY_IMAGE:?}"
: "${CI_REGISTRY_USER:?}"
: "${CI_REGISTRY_PASSWORD:?}"
: "${CI_JOB_ID:?}"
[[ "$CI_COMMIT_SHA" =~ ^[a-f0-9]{40}$ ]] || { echo 'Full commit SHA required' >&2; exit 1; }
[[ "$CI_JOB_ID" =~ ^[0-9]+$ ]] || { echo 'Numeric job ID required' >&2; exit 1; }
architecture=$(docker info --format '{{.Architecture}}')
[[ "$architecture" == 'aarch64' || "$architecture" == 'arm64' ]] || { echo 'ARM64 Docker build host required' >&2; exit 1; }

builder="yunesa-ci-${CI_JOB_ID}"
test_container=''
docker_config=$(mktemp -d)
export DOCKER_CONFIG="$docker_config"
cleanup() {
  if [[ -n "$test_container" ]]; then docker rm --force "$test_container" >/dev/null; fi
  docker buildx rm "$builder" >/dev/null
  rm -r -- "$docker_config"
}
builder_created=false
trap 'if $builder_created; then cleanup; else rm -r -- "$docker_config"; fi' EXIT
printf '%s' "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" --username "$CI_REGISTRY_USER" --password-stdin
unset CI_REGISTRY_PASSWORD
docker buildx create --name "$builder" --driver docker-container \
  --driver-opt memory=1g,memory-swap=3g --use >/dev/null
builder_created=true
docker buildx inspect --bootstrap >/dev/null
mkdir -p artifacts

printf 'FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8\n' | \
  docker buildx build --platform linux/arm64 --file - \
  --tag "$CI_REGISTRY_IMAGE/ci-preflight:$CI_JOB_ID" --push .
echo 'BuildKit registry push preflight passed'

docker buildx build --platform linux/arm64 --file docker/api.Dockerfile \
  --tag "$CI_REGISTRY_IMAGE/api:$CI_COMMIT_SHA" --push --metadata-file artifacts/api-image.json .
api_digest=$(python3 -c 'import json; print(json.load(open("artifacts/api-image.json"))["containerimage.digest"])')
api_image="$CI_REGISTRY_IMAGE/api@$api_digest"
docker pull "$api_image"
test_container=$(docker create --memory 1g --memory-swap 3g \
  --env GEMINI_API_KEY=unit-test-provider-placeholder \
  --env SILICONFLOW_API_KEY=unit-test-provider-placeholder --env OPIK_ENABLED=false \
  --entrypoint sh "$api_image" -c \
  'uv run --frozen --group test --group dev pytest test/unit/test_package_import.py test/unit/test_auth_utils.py test/unit/storage/test_conversation_repository.py test/unit/knowledge/test_qdrant_storage.py --junitxml=/tmp/baseline-unit.xml && uv run --frozen --group dev ruff check /checks')
docker cp backend/test "$test_container:/app/test"
docker cp scripts "$test_container:/checks"
docker start --attach "$test_container"
test_status=$(docker inspect "$test_container" --format '{{.State.ExitCode}}')
[[ "$test_status" == '0' ]] || { echo "Baseline image checks failed (exit $test_status)" >&2; exit 1; }
docker cp "$test_container:/tmp/baseline-unit.xml" artifacts/baseline-unit.xml
python3 - <<'PY'
import xml.etree.ElementTree as ET
root = ET.parse('artifacts/baseline-unit.xml').getroot()
suites = [root] if root.tag == 'testsuite' else list(root.iter('testsuite'))
if sum(int(suite.get('skipped', 0)) for suite in suites):
    raise SystemExit('Required baseline tests were skipped')
PY
docker rm "$test_container" >/dev/null
test_container=''

docker buildx build --platform linux/arm64 --file docker/web.Dockerfile --target development \
  --tag "yunesa-web-check:$CI_JOB_ID" --load .
docker run --rm --memory 1g --memory-swap 3g "yunesa-web-check:$CI_JOB_ID" pnpm exec eslint src
docker buildx build --platform linux/arm64 --file docker/web.Dockerfile --target production \
  --tag "$CI_REGISTRY_IMAGE/web:$CI_COMMIT_SHA" --push --metadata-file artifacts/web-image.json .
web_digest=$(python3 -c 'import json; print(json.load(open("artifacts/web-image.json"))["containerimage.digest"])')
docker buildx build --platform linux/arm64 --file docker/minio.Dockerfile \
  --tag "$CI_REGISTRY_IMAGE/minio:$CI_COMMIT_SHA" --push --metadata-file artifacts/minio-image.json .
minio_digest=$(python3 -c 'import json; print(json.load(open("artifacts/minio-image.json"))["containerimage.digest"])')
printf 'YUNESA_API_IMAGE=%s\nYUNESA_WEB_IMAGE=%s\nYUNESA_MINIO_IMAGE=%s\n' \
  "$api_image" "$CI_REGISTRY_IMAGE/web@$web_digest" "$CI_REGISTRY_IMAGE/minio@$minio_digest" > artifacts/images.env
echo 'ARM64 API/web/MinIO images built; baseline unit tests, helper lint and frontend lint completed'
