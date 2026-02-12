#!/bin/bash
# Docker Volume Backup Script for Smart Document Intelligence Platform
# Usage: ./backup.sh [daily|weekly|monthly]

set -e

BACKUP_TYPE=${1:-daily}
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/opt/backups/docintel/${BACKUP_TYPE}"
RETENTION_DAYS=30

# Create backup directory
mkdir -p "${BACKUP_DIR}"

echo "Starting ${BACKUP_TYPE} backup at ${TIMESTAMP}..."

# Function to backup a volume
backup_volume() {
    local volume_name=$1
    local backup_file="${BACKUP_DIR}/${volume_name}_${TIMESTAMP}.tar.gz"
    
    echo "Backing up volume: ${volume_name}"
    
    # Create temporary container to access volume
    docker run --rm \
        -v "${volume_name}":/source:ro \
        -v "${BACKUP_DIR}":/backup \
        alpine:latest \
        tar -czf "/backup/$(basename ${backup_file})" -C /source .
    
    echo "✓ Volume ${volume_name} backed up to ${backup_file}"
}

# Backup all volumes
echo "Backing up Docker volumes..."
backup_volume "docintel_ollama_data"
backup_volume "docintel_backend_data"

# Also backup uploaded files if using bind mounts
if [ -d "./uploads" ]; then
    echo "Backing up uploads directory..."
    tar -czf "${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz" ./uploads/
    echo "✓ Uploads backed up"
fi

# Database backup (if needed separately)
echo "Creating database dump..."
if docker ps | grep -q "docintel-backend"; then
    docker exec docintel-backend \
        sqlite3 /app/backend/data/document_intel.db ".backup /tmp/db_backup.db" 2>/dev/null || true
    docker cp docintel-backend:/tmp/db_backup.db "${BACKUP_DIR}/db_${TIMESTAMP}.sqlite" 2>/dev/null || true
    echo "✓ Database backed up"
fi

# Create backup manifest
cat > "${BACKUP_DIR}/manifest_${TIMESTAMP}.txt" << EOF
Backup Type: ${BACKUP_TYPE}
Timestamp: ${TIMESTAMP}
Date: $(date)
Hostname: $(hostname)
Docker Volumes:
- docintel_ollama_data
- docintel_backend_data

Files:
$(ls -la "${BACKUP_DIR}"/*${TIMESTAMP}*)
EOF

# Cleanup old backups
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}" -name "manifest_*.txt" -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}" -name "db_*.sqlite" -mtime +${RETENTION_DAYS} -delete

# Sync to remote (optional) - configure S3 or rsync here
# Example: aws s3 sync ${BACKUP_DIR} s3://your-bucket/backups/

echo "✓ Backup completed: ${BACKUP_DIR}"
echo "Backup size: $(du -sh ${BACKUP_DIR} | cut -f1)"

# Send notification (optional)
# curl -X POST "https://api.pushover.net/..." || true
