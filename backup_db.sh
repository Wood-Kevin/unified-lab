#!/bin/bash

# Define backup paths and timestamps
BACKUP_DIR="$HOME/lab-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/telemetry_db_$TIMESTAMP.sql"

echo "Starting automated database backup..."

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Run pg_dump inside the container using Docker Compose
# -T avoids pseudo-terminal allocation errors when run via cron
cd $HOME/unified-lab
docker compose exec -T metrics-db pg_dump -U postgres -d telemetry > "$BACKUP_FILE"

# Verify the file was created and isn't empty
if [ -s "$BACKUP_FILE" ]; then
    echo "Backup successful! Saved to: $BACKUP_FILE"
    
    # Housekeeping: Delete backups older than 7 days to keep our 100GB disk clean
    find "$BACKUP_DIR" -type f -name "telemetry_db_*.sql" -mtime +7 -delete
    echo "Old backup cleanup complete."
else
    echo "ERROR: Database backup failed or file is empty."
    rm -f "$BACKUP_FILE"
    exit 1
fi