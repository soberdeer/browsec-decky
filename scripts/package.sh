#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly VERSION="$(
  node -p "require('${PROJECT_DIR}/package.json').version"
)"
readonly OUTPUT_DIR="$PROJECT_DIR/out"
readonly ARCHIVE="$OUTPUT_DIR/Browsec-Decky-${VERSION}.zip"
readonly CHECKSUM="$OUTPUT_DIR/Browsec-Decky-${VERSION}.sha256"

for required in \
  dist/index.js \
  package.json \
  plugin.json \
  main.py \
  bin/browbox \
  bin/browray \
  assets/logo.svg \
  LICENSE \
  THIRD_PARTY_NOTICES; do
  if [[ ! -e "$PROJECT_DIR/$required" ]]; then
    printf 'Required release file is missing: %s\n' "$required" >&2
    exit 1
  fi
done

"$PROJECT_DIR/scripts/verify-runtime.sh"

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/browsec-decky-package.XXXXXX")"
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT

stage="$temporary_dir/Browsec Decky"
mkdir -p "$stage"
cp -R \
  "$PROJECT_DIR/assets" \
  "$PROJECT_DIR/bin" \
  "$PROJECT_DIR/dist" \
  "$PROJECT_DIR/py_modules" \
  "$stage/"
cp \
  "$PROJECT_DIR/LICENSE" \
  "$PROJECT_DIR/THIRD_PARTY_NOTICES" \
  "$PROJECT_DIR/README.md" \
  "$PROJECT_DIR/main.py" \
  "$PROJECT_DIR/package.json" \
  "$PROJECT_DIR/plugin.json" \
  "$stage/"

rm -f -- "$stage/bin/.gitkeep"
find "$stage" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$stage" -type f -name '*.pyc' -delete
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f -exec chmod 0644 {} +
chmod 0755 "$stage/bin/browbox" "$stage/bin/browray"

mkdir -p "$OUTPUT_DIR"
rm -f -- "$ARCHIVE" "$CHECKSUM"
(
  cd "$temporary_dir"
  zip -X -q -r "$ARCHIVE" "Browsec Decky"
)
(
  cd "$OUTPUT_DIR"
  sha256sum "$(basename "$ARCHIVE")" >"$(basename "$CHECKSUM")"
  sha256sum --check "$(basename "$CHECKSUM")"
)
printf 'Created %s\n' "$ARCHIVE"
