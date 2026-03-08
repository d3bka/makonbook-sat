# MakonBook Deployment Scripts

This directory contains all configuration files and scripts needed for deploying the MakonBook SAT system in production.

## 📁 Directory Structure

```
scripts/
├── configs/
│   └── gunicorn.conf.py       # Gunicorn WSGI server configuration
├── nginx/
│   └── makonbook.conf         # Nginx reverse proxy configuration
├── systemd/
│   ├── makonbook.service      # Systemd service for Django app
│   └── makonbook-bot.service  # Systemd service for Telegram bot
├── deploy.sh                  # Main deployment script
└── README.md                  # This file
```

## 🚀 Quick Start

### 1. Initial Setup
```bash
# Make script executable
chmod +x scripts/deploy.sh

# Run full setup (first time only)
sudo ./scripts/deploy.sh setup
```

### 2. Deploy Changes
```bash
# Deploy with auto-generated commit message
./scripts/deploy.sh deploy

# Deploy with custom commit message
./scripts/deploy.sh deploy "Fix user authentication bug"
```

### 3. Check Status
```bash
./scripts/deploy.sh status
```

## 📋 Available Commands

### `deploy [message]`
- Commits and pushes code changes to GitHub
- Updates Python dependencies
- Runs Django migrations
- Collects static files
- Restarts all services
- Checks service status

### `setup`
- **First-time deployment only**
- Sets up virtual environment
- Configures Nginx
- Installs systemd services
- Obtains SSL certificate with certbot
- Starts all services

### `update`
- Updates application without code deployment
- Reinstalls Python dependencies
- Runs Django migrations
- Restarts services

### `restart`
- Restarts all services (Django app, Telegram bot, Nginx)
- Checks service status

### `status`
- Shows status of all services
- Tests website accessibility
- Displays any error messages

### `ssl`
- Obtains or renews SSL certificate
- Configures HTTPS in Nginx

### `logs`
- Shows recent logs from all services
- Useful for debugging issues

## ⚙️ Configuration Files

### Gunicorn (`configs/gunicorn.conf.py`)
- **Workers**: CPU cores × 2 + 1 (auto-scaling)
- **Socket**: Unix socket for better performance
- **Logging**: Comprehensive access and error logs
- **Security**: Process isolation and resource limits

### Nginx (`nginx/makonbook.conf`)
- **Domain**: makonbook.satmakon.com
- **SSL**: HTTPS redirect and security headers
- **Static Files**: Direct serving for performance
- **Gzip**: Compression for faster loading
- **Security**: Multiple security headers

### Systemd Services
- **makonbook.service**: Main Django application
- **makonbook-bot.service**: Telegram bot for user management
- **Auto-start**: Both services start automatically on boot
- **Restart**: Automatic restart on failure

## 🔧 Environment Setup

### Required Environment Variables
Create `.env` file with:
```env
# Database (PostgreSQL)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=makonbook_sat
DB_USER=makonbook_user
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432

# Cloudflare R2 Storage
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=makonbook
R2_ENDPOINT_URL=your_r2_endpoint

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token

# Application
DEBUG=False
ALLOWED_HOSTS=makonbook.satmakon.com,localhost
EMAIL=admin@satmakon.com
```

### System Requirements
- **OS**: Ubuntu 20.04+ (or compatible)
- **Python**: 3.8+
- **PostgreSQL**: 12+
- **Nginx**: 1.18+
- **Node.js**: Not required (pure Django/Python)

## 🔐 Security Features

### SSL/TLS
- **Let's Encrypt**: Free SSL certificates
- **Auto-renewal**: Certbot timer service
- **HSTS**: HTTP Strict Transport Security
- **Perfect Forward Secrecy**: Modern cipher suites

### Application Security
- **CSRF Protection**: Django built-in protection
- **SQL Injection**: Django ORM protection
- **XSS Protection**: Template auto-escaping
- **Secure Headers**: Multiple security headers in Nginx

### Access Control
- **Telegram Bot**: Admin/Support role verification
- **File Permissions**: Restricted file system access
- **Process Isolation**: Systemd security settings

## 📊 Monitoring

### Service Status
```bash
# Check all services
sudo systemctl status makonbook makonbook-bot nginx postgresql

# Check specific service
sudo systemctl status makonbook.service
```

### Logs
```bash
# Application logs
sudo journalctl -u makonbook.service -f

# Bot logs
sudo journalctl -u makonbook-bot.service -f

# Nginx logs
sudo tail -f /var/log/nginx/makonbook_access.log
sudo tail -f /var/log/nginx/makonbook_error.log
```

### Performance
```bash
# Check resource usage
htop

# Check disk space
df -h

# Check database connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
```

## 🔄 Maintenance

### Regular Tasks
1. **Weekly**: Check service status and logs
2. **Monthly**: Update system packages
3. **Quarterly**: Review and rotate logs
4. **Annually**: Review SSL certificate

### Backup Strategy
- **Database**: Automated PostgreSQL dumps
- **Code**: Git repository on GitHub
- **Configs**: All configs in this scripts directory
- **SSL**: Let's Encrypt handles certificate backup

### Updates
```bash
# Update application
./scripts/deploy.sh update

# Update system packages
sudo apt update && sudo apt upgrade

# Update Python packages
source venv/bin/activate
pip list --outdated
pip install --upgrade package_name
```

## 🚨 Troubleshooting

### Common Issues

#### Service Won't Start
```bash
# Check service status
sudo systemctl status makonbook.service

# Check logs
sudo journalctl -u makonbook.service -n 50

# Check socket file
ls -la /home/satmakon/makonbook/makonbook.sock
```

#### Website Not Accessible
```bash
# Check Nginx status
sudo systemctl status nginx

# Test Nginx config
sudo nginx -t

# Check SSL certificate
sudo certbot certificates
```

#### Database Connection Issues
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test database connection
sudo -u postgres psql -d makonbook_sat -c "SELECT 1;"
```

#### Telegram Bot Not Working
```bash
# Check bot service
sudo systemctl status makonbook-bot.service

# Check bot token
echo $TELEGRAM_BOT_TOKEN

# Test bot manually
python manage.py run_telegram_bot --debug
```

### Emergency Recovery
```bash
# Stop all services
sudo systemctl stop makonbook makonbook-bot nginx

# Backup current state
sudo cp -r /home/satmakon/makonbook /backup/makonbook-$(date +%Y%m%d)

# Restore from backup
# ... restore commands ...

# Start services
sudo systemctl start postgresql nginx makonbook makonbook-bot
```

## 📞 Support

- **Documentation**: See `docs/` directory
- **Logs**: Use `./scripts/deploy.sh logs`
- **Status**: Use `./scripts/deploy.sh status`
- **GitHub**: Check repository for updates

## 🎯 Production Checklist

- [ ] Environment variables configured
- [ ] PostgreSQL database created
- [ ] SSL certificate installed
- [ ] Telegram bot token set
- [ ] All services running
- [ ] Website accessible via HTTPS
- [ ] Bot responding to commands
- [ ] Static files loading
- [ ] Database migrations applied
- [ ] Backup strategy in place