#!/usr/bin/env bash
# Create two PRIVATE, complete HAOS snapshots. This script does not modify
# /config/custom_components/samsung_health_bridge or
# /config/publish/samsung_health_bridge_publish.
#
# Run on HAOS with: bash /config/debug/export_haos_samsung_health_bridge.sh
# Optional for testing only: CONFIG_ROOT=/test/config OUTPUT_DIR=/test/out bash script.sh
set -Eeuo pipefail
umask 077

CONFIG_ROOT="${CONFIG_ROOT:-/config}"
OUTPUT_DIR="${OUTPUT_DIR:-/share/samsung_health_bridge_exports}"
CONFIG_ROOT="${CONFIG_ROOT%/}"
OUTPUT_DIR="${OUTPUT_DIR%/}"

LIVE_REL="custom_components/samsung_health_bridge"
STAGING_REL="publish/samsung_health_bridge_publish"
LIVE_DIR="$CONFIG_ROOT/$LIVE_REL"
STAGING_DIR="$CONFIG_ROOT/$STAGING_REL"

for dir in "$LIVE_DIR" "$STAGING_DIR"; do
  if [[ ! -d "$dir" ]]; then
    printf 'ERROR: Required directory not found: %s\n' "$dir" >&2
    exit 1
  fi
done

# Archives must stay OUTSIDE both source trees, so neither archive can end
# up inside the folder currently being archived.
case "$OUTPUT_DIR/" in
  "$LIVE_DIR/"*|"$STAGING_DIR/"*)
    echo 'ERROR: OUTPUT_DIR cannot be inside either source directory.' >&2
    exit 1 ;;
esac

mkdir -p "$OUTPUT_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LIVE_ARCHIVE="$OUTPUT_DIR/samsung_health_bridge_live_${STAMP}.tar.gz"
STAGING_ARCHIVE="$OUTPUT_DIR/samsung_health_bridge_publish_${STAMP}.tar.gz"
CHECKSUMS="$OUTPUT_DIR/samsung_health_bridge_${STAMP}.sha256"
LIVE_TMP="$LIVE_ARCHIVE.partial"
STAGING_TMP="$STAGING_ARCHIVE.partial"

for file in "$LIVE_ARCHIVE" "$STAGING_ARCHIVE" "$CHECKSUMS" "$LIVE_TMP" "$STAGING_TMP"; do
  if [[ -e "$file" ]]; then
    printf 'ERROR: Refusing to overwrite existing output: %s\n' "$file" >&2
    exit 1
  fi
done

trap 'rm -f -- "$LIVE_TMP" "$STAGING_TMP"' EXIT

printf 'Archiving LIVE integration: %s\n' "$LIVE_DIR"
tar -C "$CONFIG_ROOT" -czf "$LIVE_TMP" "$LIVE_REL"
tar -tzf "$LIVE_TMP" >/dev/null
mv -- "$LIVE_TMP" "$LIVE_ARCHIVE"

printf 'Archiving PUBLISH staging: %s\n' "$STAGING_DIR"
tar -C "$CONFIG_ROOT" -czf "$STAGING_TMP" "$STAGING_REL"
tar -tzf "$STAGING_TMP" >/dev/null
mv -- "$STAGING_TMP" "$STAGING_ARCHIVE"

sha256sum "$LIVE_ARCHIVE" "$STAGING_ARCHIVE" > "$CHECKSUMS"

printf '\nCreated two complete, private snapshots:\n'
ls -lh "$LIVE_ARCHIVE" "$STAGING_ARCHIVE" "$CHECKSUMS"
printf '\nContents: every regular file and dotfile below each source directory,\n'
printf 'including nested subdirectories; symlinks are archived as links.\n'
printf 'No source files were changed. Archives are saved OUTSIDE /config.\n'
printf '\nIMPORTANT: Treat these archives as PRIVATE. They may include credentials,\n'
printf 'health records, proprietary AARs, logs, or other material that must\n'
printf 'NOT be uploaded to public GitHub or attached to public issues.\n'
