#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

if (( $# > 0 )); then
  exec "$PROJECT_DIR/backend/src/import-runtime.sh" "$PROJECT_DIR/bin" "$1"
fi
exec "$PROJECT_DIR/backend/src/import-runtime.sh" "$PROJECT_DIR/bin"
