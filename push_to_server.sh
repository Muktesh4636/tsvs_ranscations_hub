#!/bin/bash
# One-command script to push code from local to server

# Server details
SERVER="root@72.61.148.117"
SERVER_PATH="/root/chip_3"
PASSWORD="To1#NXG(ihxodLqmDUU6"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Pushing code to server...${NC}"

# Check if sshpass is installed
if ! command -v sshpass &> /dev/null; then
    echo -e "${RED}Error: sshpass is not installed.${NC}"
    echo "Install it with: brew install hudochenkov/sshpass/sshpass (macOS) or apt-get install sshpass (Linux)"
    exit 1
fi

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Create backup on server before pushing
echo -e "${YELLOW}📦 Creating backup on server before pushing code...${NC}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_RESPONSE=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER" "
    cd $SERVER_PATH && 
    mkdir -p /root/chip_3_backups/pre_deploy &&
    /root/backup_chip3.sh 2>&1 | tail -5
" 2>&1)

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Backup created successfully${NC}"
    echo "$BACKUP_RESPONSE"
else
    echo -e "${YELLOW}⚠️  Backup warning (continuing anyway):${NC}"
    echo "$BACKUP_RESPONSE"
fi

echo -e "${YELLOW}Syncing files to server...${NC}"

# Use rsync to sync files (excluding unnecessary files)
rsync -avz --progress \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='staticfiles/' \
    --exclude='media/' \
    --exclude='*.log' \
    --exclude='.env' \
    --exclude='db.sqlite3' \
    --exclude='.DS_Store' \
    --exclude='*.swp' \
    --exclude='*.swo' \
    -e "sshpass -p '$PASSWORD' ssh -o StrictHostKeyChecking=no" \
    ./ "$SERVER:$SERVER_PATH/"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Code pushed successfully!${NC}"
    
    # Optionally restart services on server
    read -p "Restart Gunicorn service on server? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Restarting services...${NC}"
        sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER" "systemctl restart chip-broker.service && echo 'Service restarted'"
    fi
else
    echo -e "${RED}❌ Error pushing code${NC}"
    exit 1
fi

echo -e "${GREEN}Done!${NC}"
