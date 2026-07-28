#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly OFFICIAL_DEB_URL="https://github.com/brwinfo/desktop-release/releases/download/v1.2.2/browsec-desktop_1.2.2_amd64.deb"
readonly DEB_SHA256="479dcbfd72adb3d222c74acb06ef176aafd4472a2df90e37bc820083a5549896"
readonly BROWBOX_SHA256="68aeab83cc4ab2659a5b92232261a20746ccdafc3b3d1e19b2d63247eec3bbf7"
readonly BROWRAY_SHA256="b2c525e082cf2fef460499c88838d355f0b9bfb5a00bdb3eaa99b6af63825006"

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/browsec-decky-runtime.XXXXXX")"
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT

deb_path="${1:-}"
if [[ -z "$deb_path" ]]; then
  deb_path="$temporary_dir/browsec-desktop.deb"
  printf 'Downloading the official Browsec Desktop 1.2.2 package...\n'
  curl --fail --location --proto '=https' --tlsv1.2 \
    --output "$deb_path" "$OFFICIAL_DEB_URL"
fi

if [[ ! -f "$deb_path" ]]; then
  printf 'Package not found: %s\n' "$deb_path" >&2
  exit 1
fi

actual_deb_hash="$(sha256sum "$deb_path" | awk '{print $1}')"
if [[ "$actual_deb_hash" != "$DEB_SHA256" ]]; then
  printf 'The official package failed SHA-256 verification.\n' >&2
  exit 1
fi

mkdir -p "$temporary_dir/extracted" "$PROJECT_DIR/bin"
ar p "$deb_path" data.tar.xz \
  | tar -xJf - -C "$temporary_dir/extracted" \
      ./opt/Browsec/resources/xray/browbox \
      ./opt/Browsec/resources/xray/browray

source_dir="$temporary_dir/extracted/opt/Browsec/resources/xray"
for name in browbox browray; do
  install -m 0755 "$source_dir/$name" "$PROJECT_DIR/bin/$name"
done

actual_browbox_hash="$(sha256sum "$PROJECT_DIR/bin/browbox" | awk '{print $1}')"
actual_browray_hash="$(sha256sum "$PROJECT_DIR/bin/browray" | awk '{print $1}')"
if [[ "$actual_browbox_hash" != "$BROWBOX_SHA256" ]] \
  || [[ "$actual_browray_hash" != "$BROWRAY_SHA256" ]]; then
  rm -f -- "$PROJECT_DIR/bin/browbox" "$PROJECT_DIR/bin/browray"
  printf 'The extracted Browsec runtime failed SHA-256 verification.\n' >&2
  exit 1
fi

printf 'Verified Browsec runtime imported into %s/bin\n' "$PROJECT_DIR"

