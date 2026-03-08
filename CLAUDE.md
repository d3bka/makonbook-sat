# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MakonBook is a Django-based SAT (Scholastic Assessment Test) practice system that provides comprehensive test preparation with scoring, certificates, and analytics. The system includes a Telegram bot for bulk user management.

- **Framework**: Django 5.1.5 with PostgreSQL
- **Domain**: https://makonbook.satmakon.com
- **Storage**: Cloudflare R2 for media files and certificates

## Essential Commands

### Development & Testing
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r r.txt

# Run database migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver

# Run Telegram bot (development)
python manage.py run_telegram_bot --debug
```

### Production Deployment
```bash
# Start all services (web app + telegram bot)
./manage.sh start-all

# Stop all services
./manage.sh stop-all

# Check system status
./manage.sh status

# View logs
./manage.sh logs

# Deploy using scripts
./scripts/deploy.sh deploy "commit message"

# Check deployment status
./scripts/deploy.sh status
```

### Database Operations
```bash
# Run migrations
python manage.py migrate

# Create migration files
python manage.py makemigrations

# Reset database (development only)
python manage.py flush

# Load fixtures
python manage.py loaddata fixture_name
```

### Management Commands
```bash
# Run Telegram bot
python manage.py run_telegram_bot

# Backup database
python manage.py backup

# Import users from file
python manage.py import_users

# Sync media files to R2
python manage.py sync_media

# Update math questions
python manage.py update_math_questions

# Copy English questions
python manage.py copy_english_questions
```

## Architecture Overview

### Django Apps Structure
- **apps.base**: User management, authentication, profiles, email verification
- **apps.sat**: SAT test system, questions, scoring, reviews, certificates
- **apps.telegram_bot**: Telegram bot for bulk user creation and management

### Database Models
- **User Management**: User, UserProfile, EmailVerification
- **SAT Testing**: Test, English_Question, Math_Question, TestModule, TestReview
- **Telegram**: TelegramAdmin, BulkUserRequest, GeneratedUser
- **Media**: BaseVideo (HLS streaming support)

### Storage Architecture
- **PublicStorage**: Public media files (images, static content) - querystring_auth=False
- **PrivateStorage**: Private files (certificates, sensitive content) - querystring_auth=True
- **Location**: media/ for public, private/ for sensitive files
- **Backend**: Cloudflare R2 via S3Boto3Storage with SigV4 signatures

### URL Structure
- `/` - Base app (home, auth, profile)
- `/sat/` - SAT testing system (tests, questions, results, rankings)
- `/admin/` - Django admin interface
- Telegram bot runs separately via management command

## Key Configuration

### Environment Variables (.env)
Essential environment variables:
- `DB_ENGINE=django.db.backends.postgresql`
- `DB_NAME=makonbook_sat`
- `DB_USER=makonbook_user`
- `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL`
- `TELEGRAM_BOT_TOKEN`
- `DEBUG=False` (production)
- `ALLOWED_HOSTS=makonbook.satmakon.com,localhost`

### Settings Configuration
- Secret key stored in `satmakon/config.ini`
- Cloudflare R2 configured with SigV4 and virtual addressing
- Comprehensive logging to `logs/` directory
- HTTPS security settings enabled

## Important File Locations

### Configuration
- `satmakon/settings.py` - Main Django settings
- `satmakon/config.ini` - Secret key storage
- `.env` - Environment variables
- `r.txt` - Python dependencies

### Storage Classes
- `apps/sat/storages.py` - PublicStorage and PrivateStorage classes
- `apps/sat/store.py` - Storage utilities

### Management Scripts
- `manage.sh` - Production service management
- `scripts/deploy.sh` - Deployment automation
- `scripts/configs/gunicorn.conf.py` - Gunicorn configuration
- `scripts/nginx/makonbook.conf` - Nginx configuration

### Telegram Bot
- `apps/telegram_bot/bot.py` - Main bot logic
- `apps/telegram_bot/handlers.py` - Bot message handlers
- `apps/telegram_bot/management/commands/run_telegram_bot.py` - Bot management command

## Testing System Architecture

### Test Structure
- Tests contain English and Math sections
- Each section has Module 1 and Module 2
- Questions support images and explanations
- Timed testing with configurable limits
- OFFLINE users get unlimited time

### Scoring & Certificates
- Automatic scoring with 400-1600 scale
- Domain-based performance analysis
- PDF certificates generated and stored in R2
- Rankings and analytics for performance tracking

## Production Deployment

### Service Architecture
- **Gunicorn**: WSGI server with Unix socket
- **Nginx**: Reverse proxy with SSL termination
- **PostgreSQL**: Primary database
- **Systemd**: Service management (makonbook.service, makonbook-bot.service)

### File Permissions
- Socket file: 660 permissions for nginx access
- Log directory: /home/satmakon/makonbook/logs/
- Static files: Collected to staticfiles/

## Development Guidelines

### Storage Usage
- Use `PublicStorage()` for publicly accessible files (question images, static content)
- Use `PrivateStorage()` for sensitive files (certificates, user-specific content)
- R2 integration requires proper SigV4 signatures and virtual addressing

### Database Migrations
- System uses condensed migration architecture (2 files total)
- Always test migrations on development before production
- Use `python manage.py migrate --check` to verify

### Telegram Bot Development
- Bot handles bulk user creation with group assignment
- Admin verification required via TelegramAdmin model
- Test bot locally with `--debug` flag

### User Groups
- **OFFLINE**: Users with unlimited test time
- **Testers**: Access to additional test features
- Default users: Standard timed testing

## Security Considerations

- Never commit `.env` or `config.ini` files
- Use environment variables for all sensitive configuration
- R2 storage uses signed URLs for private content
- HTTPS enforced with secure cookies and CSRF protection
- Telegram bot requires admin verification for bulk operations