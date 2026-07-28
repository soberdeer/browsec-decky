#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly BROWBOX_SHA256="68aeab83cc4ab2659a5b92232261a20746ccdafc3b3d1e19b2d63247eec3bbf7"
readonly BROWRAY_SHA256="b2c525e082cf2fef460499c88838d355f0b9bfb5a00bdb3eaa99b6af63825006"

verify_file() {
  local name="$1"
  local expected="$2"
  local path="$PROJECT_DIR/bin/$name"
  [[ -f "$path" && ! -L "$path" && -x "$path" ]] || {
    printf 'Missing or unsafe runtime file: %s\n' "$path" >&2
    exit 1
  }
  local actual
  actual="$(sha256sum "$path" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || {
    printf 'Runtime hash mismatch: %s\n' "$name" >&2
    exit 1
  }
}

verify_file browbox "$BROWBOX_SHA256"
verify_file browray "$BROWRAY_SHA256"
printf 'Browsec runtime integrity verified.\n'

