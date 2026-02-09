#!/bin/bash

# ===========================================
# CHIP BROKER PORTAL DEPLOYMENT SCRIPT
# ===========================================
# This script safely deploys updates to the server while preserving data
# Run this script on your server after pushing code changes

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="chip-broker-portal"
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root (not recommended for security)
if [[ $EUID -eq 0 ]]; then
    log_error "Do not run this script as root. Use a regular user with sudo privileges."
    exit 1
fi

# Check if docker and docker-compose are installed
check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    log_success "Dependencies check passed"
}

# Create backup of current state
create_backup() {
    log_info "Creating backup of current state..."

    mkdir -p "$BACKUP_DIR"

    # Backup environment file
    if [[ -f ".env" ]]; then
        cp .env "$BACKUP_DIR/.env.backup"
        log_info "Environment file backed up"
    else
        log_warning "No .env file found to backup"
    fi

    # Backup docker volumes (this creates a snapshot)
    log_info "Creating database backup..."
    docker exec chip_broker_db pg_dump -U chip_user -d chip_broker_db > "$BACKUP_DIR/database_backup.sql" 2>/dev/null || {
        log_warning "Could not create database backup. Database might not be running yet."
    }

    log_success "Backup created in: $BACKUP_DIR"
}

# Pull latest changes from git
pull_updates() {
    if [[ -d ".git" ]]; then
        log_info "Pulling latest changes from git..."
        git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || {
            log_warning "Could not pull from git. Make sure you're in a git repository."
        }
        log_success "Code updated"
    else
        log_info "Not a git repository, skipping git pull"
    fi
}

# Stop current containers gracefully
stop_containers() {
    log_info "Stopping current containers gracefully..."

    # Give containers time to finish current requests
    docker-compose down --timeout 30 2>/dev/null || true

    log_success "Containers stopped"
}

# Build and start new containers
start_containers() {
    log_info "Building and starting new containers..."

    # Build the images
    docker-compose build --no-cache

    # Start containers
    docker-compose up -d

    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    sleep 10

    # Run database migrations
    log_info "Running database migrations..."
    docker-compose exec -T web python manage.py migrate

    # Collect static files
    log_info "Collecting static files..."
    docker-compose exec -T web python manage.py collectstatic --noinput

    log_success "Containers started and configured"
}

# Health check
health_check() {
    log_info "Performing health checks..."

    # Wait a bit for services to fully start
    sleep 5

    # Check if services are running
    if docker-compose ps | grep -q "Up"; then
        log_success "Services are running"
    else
        log_error "Services failed to start properly"
        exit 1
    fi

    # Check web application health
    if curl -f http://localhost/health/ &>/dev/null; then
        log_success "Web application is healthy"
    else
        log_warning "Web application health check failed"
    fi
}

# Clean up old images and containers
cleanup() {
    log_info "Cleaning up old Docker resources..."

    # Remove unused images
    docker image prune -f

    # Remove stopped containers
    docker container prune -f

    log_success "Cleanup completed"
}

# Main deployment function
deploy() {
    log_info "Starting deployment of $PROJECT_NAME..."
    echo "==========================================="

    check_dependencies
    create_backup
    pull_updates
    stop_containers
    start_containers
    health_check
    cleanup

    echo "==========================================="
    log_success "Deployment completed successfully!"
    log_info "Your application is now running with the latest updates"
    log_info "Data has been preserved through Docker volumes"
    log_info "Backup location: $BACKUP_DIR"
}

# Rollback function
rollback() {
    log_warning "Starting rollback to previous state..."

    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "No backup found to rollback to"
        exit 1
    fi

    # Restore environment file
    if [[ -f "$BACKUP_DIR/.env.backup" ]]; then
        cp "$BACKUP_DIR/.env.backup" .env
        log_info "Environment file restored"
    fi

    # Note: Database rollback would need manual intervention
    # as we can't easily restore from SQL dump in a running container

    log_warning "Database rollback requires manual intervention."
    log_warning "Please check the backup file: $BACKUP_DIR/database_backup.sql"
    log_warning "You may need to restore it manually if necessary."

    # Restart containers with previous code
    git checkout HEAD~1 2>/dev/null || log_warning "Could not rollback git (might not be a git repo)"
    start_containers

    log_success "Rollback completed (code only, database may need manual restore)"
}

# Show usage
usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  deploy    - Deploy latest changes (default)"
    echo "  rollback  - Rollback to previous state"
    echo "  backup    - Create backup only"
    echo "  logs      - Show application logs"
    echo "  status    - Show container status"
    echo "  stop      - Stop all containers"
    echo "  restart   - Restart all containers"
    echo ""
    echo "Examples:"
    echo "  $0 deploy    # Deploy updates"
    echo "  $0 logs      # View logs"
    echo "  $0 status    # Check status"
}

# Main script logic
case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    rollback)
        rollback
        ;;
    backup)
        create_backup
        ;;
    logs)
        docker-compose logs -f
        ;;
    status)
        docker-compose ps
        ;;
    stop)
        docker-compose down
        ;;
    restart)
        docker-compose restart
        ;;
    *)
        usage
        exit 1
        ;;
esac