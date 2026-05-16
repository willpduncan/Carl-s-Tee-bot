#!/bin/bash
# Immediately disable TeeBot. Booker will skip its next fire.
# Run on the VPS as a user with read access to /etc/teebot/secrets.env

set -e

if [ -f /etc/teebot/secrets.env ]; then
    . /etc/teebot/secrets.env
fi

DB="${DB_PATH:-/var/lib/teebot/teebot.db}"

sqlite3 "$DB" "UPDATE config SET bot_enabled=0"
echo "TeeBot disabled (DB: $DB)"
echo "Audit log tail:"
sqlite3 "$DB" "SELECT timestamp, event_type, success FROM audit_log ORDER BY id DESC LIMIT 10"
