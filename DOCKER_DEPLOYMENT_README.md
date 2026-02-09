# Docker Deployment Guide for Chip Broker Portal

This guide explains how to deploy the Chip Broker Portal using Docker with persistent data storage to ensure your database is never lost during updates.

## 🛡️ Data Safety Guarantee

**Your data will NEVER be lost** because:
- PostgreSQL data is stored in **persistent Docker volumes**
- Database backups are created automatically before each deployment
- Docker volumes survive container updates and server restarts
- All deployments use zero-downtime updates

## 📋 Prerequisites

- Ubuntu/Debian server (or any Linux distribution with Docker support)
- At least 2GB RAM, 2 CPU cores, 20GB disk space
- Root or sudo access
- Internet connection for downloading Docker images

## 🚀 Quick Start (5 minutes)

### 1. Install Docker and Docker Compose

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add your user to docker group (optional, for running without sudo)
sudo usermod -aG docker $USER
```

### 2. Clone and Setup Project

```bash
# Clone your project
git clone https://github.com/yourusername/chip-broker-portal.git
cd chip-broker-portal

# Copy environment template
cp .env.example .env

# Edit environment variables (IMPORTANT!)
nano .env
```

### 3. Configure Environment Variables

Edit `.env` file with your settings:

```bash
# Generate a secure secret key
SECRET_KEY="your-very-long-and-secure-secret-key-here"

# Database credentials (CHANGE THESE!)
DB_NAME="chip_broker_db"
DB_USER="chip_user"
DB_PASSWORD="your-very-secure-database-password-here"

# Domain and server settings
ALLOWED_HOSTS="your-server-ip,yourdomain.com,www.yourdomain.com"

# Email settings (optional)
EMAIL_HOST_USER="your-email@gmail.com"
EMAIL_HOST_PASSWORD="your-app-password"
```

### 4. Deploy

```bash
# Make deployment script executable
chmod +x deploy.sh

# Deploy the application
./deploy.sh deploy
```

That's it! Your application will be running at `http://your-server-ip`

## 🔧 Detailed Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | Generate with `openssl rand -hex 32` |
| `DEBUG` | Debug mode (False for production) | `False` |
| `ALLOWED_HOSTS` | Comma-separated domains/IPs | `example.com,www.example.com,192.168.1.100` |
| `DB_NAME` | PostgreSQL database name | `chip_broker_db` |
| `DB_USER` | Database username | `chip_user` |
| `DB_PASSWORD` | Database password | `secure-password-123` |
| `EMAIL_HOST_USER` | SMTP username | `noreply@example.com` |
| `EMAIL_HOST_PASSWORD` | SMTP password | `app-password` |

### SSL/HTTPS Setup (Recommended)

1. **Get SSL certificates** (using Let's Encrypt):

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com
```

2. **Update Nginx config**:

```bash
# Uncomment HTTPS server block in nginx/nginx.conf
# Update ssl_certificate paths to:
# ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
```

3. **Deploy and restart**:

```bash
./deploy.sh deploy
```

## 📊 Monitoring and Management

### Check Status

```bash
# View all services status
./deploy.sh status

# View logs
./deploy.sh logs

# View specific service logs
docker-compose logs web
docker-compose logs db
```

### Update Application

```bash
# Pull latest code and deploy
./deploy.sh deploy

# Or manually:
git pull origin main
./deploy.sh deploy
```

### Backup Data

```bash
# Create backup (automatic before deployments)
./deploy.sh backup

# Manual database backup
docker exec chip_broker_db pg_dump -U chip_user chip_broker_db > backup_$(date +%Y%m%d).sql
```

### Database Management

```bash
# Access database directly
docker exec -it chip_broker_db psql -U chip_user -d chip_broker_db

# Run Django management commands
docker-compose exec web python manage.py shell
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

## 🔧 Troubleshooting

### Application Not Starting

```bash
# Check logs
./deploy.sh logs

# Check if containers are running
docker ps

# Restart services
./deploy.sh restart
```

### Database Connection Issues

```bash
# Check database logs
docker-compose logs db

# Test database connection
docker exec chip_broker_db pg_isready -U chip_user -d chip_broker_db
```

### Permission Issues

```bash
# Fix Docker permissions
sudo chown -R $USER:$USER .
sudo chmod -R 755 .
```

### Port Already in Use

```bash
# Find what's using port 80
sudo lsof -i :80

# Change ports in docker-compose.yml if needed
```

## 🔄 Updating the Application

### Safe Updates (Recommended)

```bash
# This creates backup automatically and updates safely
./deploy.sh deploy
```

### Manual Updates

```bash
# Pull changes
git pull origin main

# Create backup
./deploy.sh backup

# Deploy
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py collectstatic --noinput
```

## 🔒 Security Best Practices

1. **Change default database credentials** in `.env`
2. **Use strong SECRET_KEY** (32+ characters)
3. **Enable HTTPS** with SSL certificates
4. **Configure firewall** (allow only ports 80, 443, 22)
5. **Keep Docker images updated**
6. **Regular backups** of database and code
7. **Monitor logs** for suspicious activity

## 📁 Project Structure

```
chip-broker-portal/
├── Dockerfile              # Application container
├── docker-compose.yml      # Service orchestration
├── nginx/nginx.conf        # Web server config
├── deploy.sh               # Deployment script
├── .env.example            # Environment template
├── .dockerignore           # Build optimization
└── ... (your Django app)
```

## 🚨 Emergency Recovery

If something goes wrong:

```bash
# Stop everything
./deploy.sh stop

# Restore from backup (check backups/ directory)
# Copy latest .env.backup to .env
# Restore database if needed:
# docker exec -i chip_broker_db psql -U chip_user -d chip_broker_db < backup_file.sql

# Start again
./deploy.sh deploy
```

## 📞 Support

If you encounter issues:

1. Check the logs: `./deploy.sh logs`
2. Verify environment variables in `.env`
3. Ensure all prerequisites are installed
4. Check Docker resources: `docker system df`

## 🎯 Performance Tuning

### For High Traffic

```yaml
# In docker-compose.yml, increase resources:
web:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '1.0'
        memory: 1G
```

### Database Optimization

```sql
-- Run these in PostgreSQL console
CREATE INDEX CONCURRENTLY idx_transaction_date ON core_transaction(created_at);
CREATE INDEX CONCURRENTLY idx_client_name ON core_client(name);
ANALYZE;
```

---

**Your data is safe!** Docker volumes ensure persistence across deployments. Always run `./deploy.sh deploy` for updates - it creates backups automatically.