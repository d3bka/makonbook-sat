# MakonBook SAT System - Complete Deployment Guide

## 🚀 Production Deployment for makonbook.satmakon.com

This guide provides step-by-step instructions for deploying the MakonBook SAT system with nginx, gunicorn, PostgreSQL, SSL, and a Telegram bot for bulk user management.

## 📋 Prerequisites

### System Requirements
- **OS**: Ubuntu 20.04+ or compatible Linux distribution
- **RAM**: Minimum 2GB, Recommended 4GB+
- **Storage**: Minimum 20GB free space
- **Network**: Static IP address with DNS pointing to your domain

### Required Software
- Python 3.8+
- PostgreSQL 12+
- Nginx 1.18+
- Git
- Certbot (for SSL)

## 🔧 Step 1: System Preparation

### 1.1 Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 1.2 Install Required Packages
```bash
sudo apt install -y python3 python3-venv python3-pip postgresql postgresql-contrib nginx git curl ufw
```

### 1.3 Configure Firewall
```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### 1.4 Create Project User (if needed)
```bash
# Skip if using existing user
sudo adduser satmakon
sudo usermod -aG sudo satmakon
```

## 🗄️ Step 2: Database Setup

### 2.1 Configure PostgreSQL
```bash
sudo -u postgres psql
```

```sql
-- In PostgreSQL shell
CREATE DATABASE makonbook_sat;
CREATE USER makonbook_user WITH PASSWORD 'MakonBook2024Secure';
GRANT ALL PRIVILEGES ON DATABASE makonbook_sat TO makonbook_user;
GRANT ALL ON SCHEMA public TO makonbook_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO makonbook_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO makonbook_user;
\q
```

### 2.2 Test Database Connection
```bash
sudo -u postgres psql -d makonbook_sat -c "SELECT 1;"
```

## 📦 Step 3: Project Deployment

### 3.1 Clone Repository
```bash
cd /home/satmakon
git clone https://github.com/yourusername/makonbook.git
cd makonbook
```

### 3.2 Create Environment File
```bash
cp env.example .env
nano .env
```

Update `.env` with your values:
```env
# Database Configuration
DB_ENGINE=django.db.backends.postgresql
DB_NAME=makonbook_sat
DB_USER=makonbook_user
DB_PASSWORD=MakonBook2024Secure
DB_HOST=localhost
DB_PORT=5432

# Cloudflare R2 Storage Configuration
R2_ACCESS_KEY_ID=your_actual_access_key
R2_SECRET_ACCESS_KEY=your_actual_secret_key
R2_BUCKET_NAME=makonbook
R2_ENDPOINT_URL=your_actual_r2_endpoint

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Email Configuration
EMAIL=admin@satmakon.com
EMAIL_PASSWORD=your_email_password

# Production Settings
DEBUG=False
ALLOWED_HOSTS=makonbook.satmakon.com,127.0.0.1,localhost
```

### 3.3 Make Deployment Script Executable
```bash
chmod +x scripts/deploy.sh
```

## 🤖 Step 4: Telegram Bot Setup

### 4.1 Create Telegram Bot
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Use `/newbot` command
3. Follow instructions to create bot
4. Copy the bot token to your `.env` file

### 4.2 Add Telegram Admins
You'll add admin users after deployment via Django admin interface.

## 🚀 Step 5: Full System Deployment

### 5.1 Run Initial Setup
```bash
# This will setup everything: venv, nginx, systemd, SSL
./scripts/deploy.sh setup
```

This command will:
- ✅ Create Python virtual environment
- ✅ Install all dependencies
- ✅ Run database migrations (including Telegram bot models)
- ✅ Collect static files
- ✅ Configure Nginx with SSL-ready setup
- ✅ Install systemd services
- ✅ Obtain SSL certificate via certbot
- ✅ Start all services

### 5.2 Verify Deployment
```bash
./scripts/deploy.sh status
```

Expected output:
```
=== Service Status ===
✅ MakonBook application: RUNNING
✅ MakonBook bot: RUNNING  
✅ Nginx: RUNNING
✅ PostgreSQL: RUNNING

=== Website Status ===
✅ Website: ACCESSIBLE
```

## 👤 Step 6: Create Telegram Bot Admins

### 6.1 Access Django Admin
1. Navigate to `https://makonbook.satmakon.com/admin/`
2. Login with the existing admin user (`october1550`)

### 6.2 Add Telegram Admins
1. Go to "Telegram Admins" section
2. Click "Add Telegram Admin"
3. Fill in:
   - **Telegram ID**: User's numeric Telegram ID (get from @userinfobot)
   - **Username**: Their Telegram username (optional)
   - **First Name**: Their first name (optional)
   - **Is Admin**: Check for full admin privileges
   - **Is Support**: Check for support-only privileges
   - **Is Active**: Check to enable access

### 6.3 Get Telegram ID
Users can get their Telegram ID by:
1. Messaging [@userinfobot](https://t.me/userinfobot)
2. The bot will reply with their numeric ID

## 🔄 Step 7: Using the System

### 7.1 Website Access
- **URL**: https://makonbook.satmakon.com
- **Admin**: https://makonbook.satmakon.com/admin/
- **SAT Tests**: https://makonbook.satmakon.com/sat/practises/

### 7.2 Telegram Bot Usage
1. Users message your bot on Telegram
2. Use `/start` command to begin
3. Follow the interactive menu to create bulk users

#### Bot Features:
- 🔄 **Create Bulk Users**: Generate up to 50 users at once
- 📊 **Request History**: View previous bulk creation requests
- 👥 **Group Management**: Assign users to Django groups
- 🔐 **Secure Access**: Admin/Support role verification

#### Example Usage:
```
User: /start
Bot: Welcome! Select an option:
[🔄 Create Bulk Users] [📊 My Requests] [ℹ️ Help]

User: [Create Bulk Users]
Bot: Enter username prefix (2-10 chars, letters/numbers only):

User: student
Bot: ✅ Prefix Set: student
Enter number of users (1-50):

User: 25
Bot: ✅ Count Set: 25 users
Select groups for new users:
[⬜ Testers] [⬜ OFFLINE] [✅ Confirm Groups] [❌ Cancel]

User: [Confirm Groups]
Bot: 📋 Creation Summary:
• Prefix: student
• Count: 25 users  
• Groups: None
• Users: student001 through student025
Do you want to proceed?
[✅ Create Users] [❌ Cancel]

User: [Create Users]
Bot: ✅ Users Created Successfully!
📊 Summary: Created 25 users
👥 Created Users:
student001 - aB3kL8pQ
student002 - xY9mN2rT
...
```

## 📊 Step 8: Monitoring and Maintenance

### 8.1 Check Service Status
```bash
./scripts/deploy.sh status
```

### 8.2 View Logs
```bash
./scripts/deploy.sh logs
```

### 8.3 Deploy Updates
```bash
# After making code changes
./scripts/deploy.sh deploy "Description of changes"
```

### 8.4 Restart Services
```bash
./scripts/deploy.sh restart
```

## 🔐 Step 9: Security Configuration

### 9.1 SSL Certificate
- Automatically configured via certbot
- Auto-renewal enabled
- HTTPS redirect configured

### 9.2 Security Headers
All security headers are configured in nginx:
- X-Frame-Options
- X-Content-Type-Options  
- X-XSS-Protection
- Strict-Transport-Security
- Content-Security-Policy

### 9.3 Firewall
```bash
# Check firewall status
sudo ufw status

# Should show:
# To         Action      From
# 22/tcp     ALLOW       Anywhere
# Nginx Full ALLOW       Anywhere
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Website Not Loading
```bash
# Check nginx status
sudo systemctl status nginx

# Check nginx config
sudo nginx -t

# Check logs
sudo tail -f /var/log/nginx/makonbook_error.log
```

#### 2. 502 Bad Gateway
```bash
# Check gunicorn service
sudo systemctl status makonbook.service

# Check socket file
ls -la /home/satmakon/makonbook/makonbook.sock

# Restart application
sudo systemctl restart makonbook.service
```

#### 3. Database Connection Error
```bash
# Check PostgreSQL
sudo systemctl status postgresql

# Test connection
sudo -u postgres psql -d makonbook_sat -c "SELECT 1;"

# Check environment variables
cat .env | grep DB_
```

#### 4. Telegram Bot Not Responding
```bash
# Check bot service
sudo systemctl status makonbook-bot.service

# Check bot token
echo $TELEGRAM_BOT_TOKEN

# Test bot manually
source venv/bin/activate
python manage.py run_telegram_bot --debug
```

#### 5. SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Renew certificate
sudo certbot renew

# Test renewal
sudo certbot renew --dry-run
```

### Emergency Recovery
```bash
# Stop all services
sudo systemctl stop makonbook makonbook-bot nginx

# Check system resources
htop
df -h

# Restart services one by one
sudo systemctl start postgresql
sudo systemctl start nginx
sudo systemctl start makonbook
sudo systemctl start makonbook-bot
```

## 📈 Performance Optimization

### 9.1 Gunicorn Configuration
Already optimized in `scripts/configs/gunicorn.conf.py`:
- Worker processes: CPU cores × 2 + 1
- Unix socket for better performance
- Process restart after 1000 requests

### 9.2 Nginx Configuration
Already optimized in `scripts/nginx/makonbook.conf`:
- Gzip compression enabled
- Static file caching (1 year)
- Security headers
- HTTP/2 support

### 9.3 Database Performance
```bash
# Check database connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Optimize PostgreSQL (if needed)
sudo nano /etc/postgresql/*/main/postgresql.conf
```

## 📋 Production Checklist

- [ ] ✅ System packages updated
- [ ] ✅ PostgreSQL database created and configured
- [ ] ✅ Environment variables configured in `.env`
- [ ] ✅ Virtual environment created and dependencies installed
- [ ] ✅ Database migrations applied
- [ ] ✅ Static files collected
- [ ] ✅ Nginx configured with security headers
- [ ] ✅ SSL certificate obtained and auto-renewal enabled
- [ ] ✅ Systemd services installed and enabled
- [ ] ✅ Firewall configured
- [ ] ✅ All services running and accessible
- [ ] ✅ Telegram bot created and token configured
- [ ] ✅ Telegram admins added via Django admin
- [ ] ✅ Bot responding to commands
- [ ] ✅ Backup strategy implemented
- [ ] ✅ Monitoring and logging configured

## 🔄 Ongoing Maintenance

### Weekly Tasks
- Check service status: `./scripts/deploy.sh status`
- Review logs: `./scripts/deploy.sh logs`
- Monitor disk space: `df -h`

### Monthly Tasks
- Update system packages: `sudo apt update && sudo apt upgrade`
- Review SSL certificate: `sudo certbot certificates`
- Check database performance

### As Needed
- Deploy code updates: `./scripts/deploy.sh deploy "Description"`
- Add new Telegram admins via Django admin
- Review and manage user accounts

## 📞 Support

- **Documentation**: Check `docs/` directory
- **Scripts**: Use `./scripts/deploy.sh help`
- **Logs**: Use `./scripts/deploy.sh logs`
- **Status**: Use `./scripts/deploy.sh status`

**Your MakonBook SAT system is now fully deployed and ready for production use!** 🎉

Based on the comprehensive [DigitalOcean Django deployment guide](https://www.digitalocean.com/community/tutorials/how-to-set-up-django-with-postgres-nginx-and-gunicorn-on-ubuntu-22-04), this deployment follows industry best practices for production Django applications with additional features for your specific SAT testing system and Telegram bot integration.