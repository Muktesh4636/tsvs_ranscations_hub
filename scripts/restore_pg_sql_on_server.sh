#!/bin/bash
# Run ON THE PRODUCTION SERVER as root (host for https://svs.transactions.pravoo.in/).
# Replaces the app database with a pg_dump .sql file from your laptop.
#
# Usage:
#   cd /root/chip_3 && chmod +x scripts/restore_pg_sql_on_server.sh
#   ./scripts/restore_pg_sql_on_server.sh /root/chip_3/restore_dump.sql
#
# WARNING: Deletes all current data in the target database.

set -euo pipefail

SQL_FILE="${1:?Usage: $0 /path/to/dump.sql}"

if [ ! -f "$SQL_FILE" ]; then
    echo "File not found: $SQL_FILE"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
    echo "Missing .env in $PROJECT_ROOT"
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

DB_NAME="${DB_NAME:-broker_portal}"

echo "Stopping chip-broker.service..."
systemctl stop chip-broker.service || true

echo "Replacing schema public on database $DB_NAME (all existing app data removed)..."
sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<EOSQL
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
EOSQL

echo "Restoring from $SQL_FILE ..."
sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$SQL_FILE"

# App user (from .env) must access tables owned by postgres after restore
if [ -n "${DB_USER:-}" ] && [ "$DB_USER" != "postgres" ]; then
    echo "Granting privileges to app user: $DB_USER"
    sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "
GRANT USAGE ON SCHEMA public TO \"$DB_USER\";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"$DB_USER\";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"$DB_USER\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO \"$DB_USER\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO \"$DB_USER\";
"
fi

echo "Starting chip-broker.service..."
systemctl start chip-broker.service

echo "Done. Test login at https://svs.transactions.pravoo.in/"
echo "If something failed, restore from /root/chip_3_backups/ or your server backup."
