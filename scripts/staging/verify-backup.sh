#!/bin/bash
# Verifies a backup produced by backup.sh is intact: checksum matches and
# the gzip stream isn't corrupt. Does NOT touch any running database —
# restore.sh is what actually proves a backup is restorable, and should be
# run against a disposable copy periodically (see docs/runbooks/BACKUP_RESTORE.md).
#
# Usage: scripts/staging/verify-backup.sh <path-to-backup-file.sql.gz|.tar.gz>
set -euo pipefail

FILE="${1:?Usage: verify-backup.sh <path-to-rastichat-db-or-media-backup-file>}"
CHECKSUM_FILE="${FILE}.sha256"

if [ ! -f "$FILE" ]; then
  echo "Backup file not found: $FILE" >&2
  exit 1
fi
if [ ! -f "$CHECKSUM_FILE" ]; then
  echo "No checksum file found alongside it: $CHECKSUM_FILE" >&2
  exit 1
fi

echo "=== Verifying checksum ==="
if (cd "$(dirname "$FILE")" && sha256sum -c "$(basename "$CHECKSUM_FILE")"); then
  echo "Checksum OK."
else
  echo "CHECKSUM MISMATCH — this backup file is corrupt or was tampered with. Do not restore it." >&2
  exit 1
fi

echo "=== Verifying archive integrity ==="
case "$FILE" in
  *.sql.gz) gzip -t "$FILE" && echo "gzip stream OK." ;;
  *.tar.gz) tar -tzf "$FILE" >/dev/null && echo "tar archive OK." ;;
  *) echo "Unrecognized backup file extension — skipping format-specific check." ;;
esac

echo
echo "Backup file verified: $FILE"
