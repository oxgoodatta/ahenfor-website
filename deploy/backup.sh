#!/usr/bin/env bash
# Nightly backup of the database and (when stored locally) uploaded media.
# Cron example (02:30 daily):  30 2 * * * /srv/ahenfor/app/deploy/backup.sh >> /var/log/ahenfor-backup.log 2>&1
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/ahenfor/app}"
BACKUP_DIR="${BACKUP_DIR:-/srv/ahenfor/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

set -a; source "$APP_DIR/.env"; set +a
mkdir -p "$BACKUP_DIR"

# 1. Database
DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ] || [[ "$DB_URL" == sqlite* ]]; then
  # SQLite: consistent online copy via Python's backup API (safe while the site is running)
  DB_FILE="${DB_URL#sqlite:///}"
  DB_FILE="${DB_FILE:-$APP_DIR/instance/ahenfor.db}"
  "$APP_DIR/.venv/bin/python" -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" \
    "$DB_FILE" "$BACKUP_DIR/db-$STAMP.sqlite3"
else
  # PostgreSQL (custom format: restore with pg_restore)
  pg_dump --format=custom --no-owner --dbname="${DB_URL/postgresql+psycopg:/postgresql:}" \
    --file="$BACKUP_DIR/db-$STAMP.dump"
fi

# 2. Local media (skip when using S3/Cloudinary - enable versioning/backups there instead)
if [ "${MEDIA_STORAGE_PROVIDER:-local}" = "local" ]; then
  MEDIA_ROOT="${LOCAL_MEDIA_ROOT:-$APP_DIR/instance/uploads}"
  tar -czf "$BACKUP_DIR/media-$STAMP.tar.gz" -C "$(dirname "$MEDIA_ROOT")" "$(basename "$MEDIA_ROOT")"
fi

# 3. Prune old backups
find "$BACKUP_DIR" -type f -mtime +"$KEEP_DAYS" -delete
echo "Backup $STAMP complete"
# Copy $BACKUP_DIR off the server (rclone, rsync, provider snapshots): a backup on the same disk is not a backup.
