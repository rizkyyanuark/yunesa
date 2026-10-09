#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Yunesa Version Bump Script
# =============================================================================
# Usage: ./scripts/bump-version.sh <new_version>
# Example: ./scripts/bump-version.sh 0.1.0
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 0.1.0"
    exit 1
fi

NEW_VERSION="$1"

# Validate version format
if [[ ! "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[a-zA-Z0-9]+)?$ ]]; then
    echo "Error: Invalid version format. Expected x.y.z (e.g. 0.1.0)"
    exit 1
fi

PYPROJECT_FILE="${PROJECT_ROOT}/backend/package/pyproject.toml"
PACKAGE_JSON="${PROJECT_ROOT}/web/package.json"

echo "Bumping project version to ${NEW_VERSION}..."

if [ -f "$PYPROJECT_FILE" ]; then
    sed -i -E "s/^version[[:space:]]*=[[:space:]]*\"[^\"]+\"/version = \"${NEW_VERSION}\"/" "$PYPROJECT_FILE"
    echo "✅ Updated ${PYPROJECT_FILE}"
fi

if [ -f "$PACKAGE_JSON" ]; then
    sed -i -E "s/\"version\":[[:space:]]*\"[^\"]+\"/\"version\": \"${NEW_VERSION}\"/" "$PACKAGE_JSON"
    echo "✅ Updated ${PACKAGE_JSON}"
fi

echo "🎉 Successfully bumped version to ${NEW_VERSION}!"
