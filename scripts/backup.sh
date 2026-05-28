#!/usr/bin/env bash
# Backup the Tree of Wishes database.
# SQLite: copies the file. PostgreSQL: uses pg_dump.
# Keeps the 30 most recent backups; older ones are deleted.
# Usage: ./scripts/backup.sh [BACKUP_DIR]
# Default BACKUP_DIR: <repo-root>/backups

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${1:-$REPO_ROOT/backups}"
KEEP=30

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

# Load .env if present (picks up DATABASE_URL)
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.env"
  set +a
fi

DATABASE_URL="${DATABASE_URL:-sqlite:///$REPO_ROOT/wishes.db}"

if [[ "$DATABASE_URL" == sqlite://* ]]; then
  # Strip the sqlite:/// prefix to get the file path
  DB_PATH="${DATABASE_URL#sqlite:///}"
  # Resolve relative paths against repo root
  [[ "$DB_PATH" != /* ]] && DB_PATH="$REPO_ROOT/$DB_PATH"

  DEST="$BACKUP_DIR/wishes_${TIMESTAMP}.db"
  cp "$DB_PATH" "$DEST"
  echo "SQLite backup → $DEST"
else
  DEST="$BACKUP_DIR/wishes_${TIMESTAMP}.sql.gz"
  pg_dump "$DATABASE_URL" | gzip > "$DEST"
  echo "PostgreSQL backup → $DEST"
fi

# Prune: keep only the $KEEP most recent backups
ls -1t "$BACKUP_DIR"/wishes_*.{db,sql.gz} 2>/dev/null \
  | tail -n +$((KEEP + 1)) \
  | xargs -r rm --
echo "Kept newest $KEEP backups in $BACKUP_DIR"
