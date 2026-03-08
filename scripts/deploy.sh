#!/bin/bash

# MakonBook SAT System - Professional Deployment Script
# Domain: makonbook.satmakon.com
# Author: AI Assistant
# Date: $(date)

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/home/satmakon/makonbook"
VENV_DIR="$PROJECT_DIR/venv"
NGINX_CONFIG="/etc/nginx/sites-available/makonbook.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/makonbook.conf"
SYSTEMD_DIR="/etc/systemd/system"
LOG_DIR="/var/log/makonbook"
DOMAIN="makonbook.satmakon.com"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if service exists
service_exists() {
    systemctl list-unit-files | grep -q "^$1.service"
}

# Function to deploy code changes
deploy_code() {
    print_status "Starting code deployment..."
    
    cd "$PROJECT_DIR"
    
    # Check if git repository exists
    if [ ! -d ".git" ]; then
        print_error "Git repository not found. Please initialize git first."
        exit 1
    fi
    
    # Add all changes
    print_status "Adding changes to git..."
    git add .
    
    # Generate commit message with timestamp
    COMMIT_MSG="Auto deployment - $(date '+%Y-%m-%d %H:%M:%S')"
    if [ $# -gt 0 ]; then
        COMMIT_MSG="$*"
    fi
    
    # Commit changes
    if git diff --staged --quiet; then
        print_warning "No changes to commit."
    else
        print_status "Committing changes..."
        git commit -m "$COMMIT_MSG"
        
        # Push to remote
        print_status "Pushing to GitHub..."
        git push origin master || {
            print_warning "Failed to push to remote. Continuing with local deployment..."
        }
    fi
    
    print_success "Code deployment completed"
}

# Function to setup virtual environment
setup_venv() {
    print_status "Setting up Python virtual environment..."
    
    if [ ! -d "$VENV_DIR" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    print_status "Upgrading pip..."
    pip install --upgrade pip
    
    # Install requirements
    print_status "Installing Python packages..."
    pip install -r r.txt
    
    print_success "Virtual environment setup completed"
}

# Function to run Django management commands
django_management() {
    print_status "Running Django management commands..."
    
    source "$VENV_DIR/bin/activate"
    cd "$PROJECT_DIR"
    
    # Make migrations for telegram bot if needed
    print_status "Creating migrations for telegram bot..."
    python manage.py makemigrations telegram_bot
    
    # Run migrations
    print_status "Running database migrations..."
    python manage.py migrate
    
    # Collect static files
    print_status "Collecting static files..."
    python manage.py collectstatic --noinput
    
    # Create superuser if needed (interactive)
    # python manage.py createsuperuser
    
    print_success "Django management commands completed"
}

# Function to setup log directories
setup_logging() {
    print_status "Setting up logging directories..."
    
    sudo mkdir -p "$LOG_DIR"
    sudo chown satmakon:satmakon "$LOG_DIR"
    sudo chmod 755 "$LOG_DIR"
    
    # Create log files if they don't exist
    sudo touch "$LOG_DIR/access.log" "$LOG_DIR/error.log"
    sudo chown satmakon:satmakon "$LOG_DIR"/*.log
    
    print_success "Logging setup completed"
}

# Function to setup nginx
setup_nginx() {
    print_status "Setting up Nginx configuration..."
    
    # Copy nginx configuration
    sudo cp scripts/nginx/makonbook.conf "$NGINX_CONFIG"
    
    # Create symbolic link if it doesn't exist
    if [ ! -L "$NGINX_ENABLED" ]; then
        sudo ln -s "$NGINX_CONFIG" "$NGINX_ENABLED"
    fi
    
    # Test nginx configuration
    print_status "Testing Nginx configuration..."
    sudo nginx -t
    
    # Remove default nginx site if it exists
    if [ -L "/etc/nginx/sites-enabled/default" ]; then
        sudo rm /etc/nginx/sites-enabled/default
    fi
    
    print_success "Nginx configuration completed"
}

# Function to setup systemd services
setup_systemd() {
    print_status "Setting up systemd services..."
    
    # Copy service files
    sudo cp scripts/systemd/makonbook.service "$SYSTEMD_DIR/"
    sudo cp scripts/systemd/makonbook-bot.service "$SYSTEMD_DIR/"
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable services
    sudo systemctl enable makonbook.service
    sudo systemctl enable makonbook-bot.service
    
    print_success "Systemd services setup completed"
}

# Function to setup SSL with certbot
setup_ssl() {
    print_status "Setting up SSL with certbot..."
    
    # Check if certbot is installed
    if ! command_exists certbot; then
        print_status "Installing certbot..."
        sudo apt update
        sudo apt install -y certbot python3-certbot-nginx
    fi
    
    # Check if certificate already exists
    if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        print_warning "SSL certificate already exists for $DOMAIN"
        return 0
    fi
    
    # Get SSL certificate
    print_status "Obtaining SSL certificate for $DOMAIN..."
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@satmakon.com
    
    # Setup auto-renewal
    print_status "Setting up SSL certificate auto-renewal..."
    sudo systemctl enable certbot.timer
    
    print_success "SSL setup completed"
}

# Function to restart services
restart_services() {
    print_status "Restarting services..."
    
    # Use the new unified management script instead of systemd
    if [ -f "$PROJECT_DIR/manage.sh" ]; then
        chmod +x "$PROJECT_DIR/manage.sh"
        "$PROJECT_DIR/manage.sh" restart-all
    else
        print_warning "manage.sh not found, using legacy method"
        
        # Legacy restart method
        pkill -f "gunicorn.*satmakon.wsgi" || true
        pkill -f "run_telegram_bot" || true
        sleep 2
        
        # Start services using individual scripts if they exist
        [ -f "$PROJECT_DIR/start_makonbook.sh" ] && "$PROJECT_DIR/start_makonbook.sh" || true
        [ -f "$PROJECT_DIR/start_telegram_bot.sh" ] && "$PROJECT_DIR/start_telegram_bot.sh" || true
    fi
    
    # Restart nginx
    sudo systemctl restart nginx
    print_status "Restarted Nginx"
    
    print_success "All services restarted"
}

# Function to check service status
check_status() {
    print_status "Checking service status..."
    
    echo -e "\n${BLUE}=== Service Status ===${NC}"
    
    # Use the new unified management script if available
    if [ -f "$PROJECT_DIR/manage.sh" ]; then
        chmod +x "$PROJECT_DIR/manage.sh"
        "$PROJECT_DIR/manage.sh" status
    else
        print_warning "manage.sh not found, using legacy status check"
        
        # Legacy status check
        if pgrep -f "gunicorn.*satmakon.wsgi" > /dev/null; then
            print_success "MakonBook application: RUNNING"
        else
            print_error "MakonBook application: STOPPED"
        fi
        
        if pgrep -f "run_telegram_bot" > /dev/null; then
            print_success "MakonBook bot: RUNNING"
        else
            print_error "MakonBook bot: STOPPED"
        fi
        
        # Check Nginx
        if systemctl is-active --quiet nginx; then
            print_success "Nginx: RUNNING"
        else
            print_error "Nginx: FAILED"
        fi
        
        # Check PostgreSQL
        if systemctl is-active --quiet postgresql; then
            print_success "PostgreSQL: RUNNING"
        else
            print_error "PostgreSQL: FAILED"
        fi
    fi
    
    echo -e "\n${BLUE}=== Website Status ===${NC}"
    if curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/health/" | grep -q "200"; then
        print_success "Website: ACCESSIBLE"
    else
        print_error "Website: NOT ACCESSIBLE"
    fi
}

# Function to show help
show_help() {
    echo -e "${BLUE}MakonBook Deployment Script${NC}"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  deploy [message]     - Deploy code changes with optional commit message"
    echo "  setup               - Full initial setup (nginx, systemd, ssl)"
    echo "  update              - Update application (venv, django, restart)"
    echo "  restart             - Restart all services"
    echo "  status              - Check service status"
    echo "  ssl                 - Setup SSL certificate"
    echo "  logs                - Show application logs"
    echo "  help                - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 deploy 'Fix user authentication bug'"
    echo "  $0 setup"
    echo "  $0 update"
    echo "  $0 status"
}

# Function to show logs
show_logs() {
    print_status "Showing application logs..."
    
    echo -e "\n${BLUE}=== MakonBook Application Logs ===${NC}"
    sudo journalctl -u makonbook.service -n 50 --no-pager
    
    echo -e "\n${BLUE}=== MakonBook Bot Logs ===${NC}"
    sudo journalctl -u makonbook-bot.service -n 50 --no-pager
    
    echo -e "\n${BLUE}=== Nginx Error Logs ===${NC}"
    sudo tail -n 50 /var/log/nginx/makonbook_error.log
}

# Main script logic
case "${1:-help}" in
    "deploy")
        shift  # Remove 'deploy' from arguments
        deploy_code "$@"
        setup_venv
        django_management
        restart_services
        check_status
        ;;
    "setup")
        print_status "Starting full MakonBook setup..."
        setup_venv
        django_management
        setup_logging
        setup_nginx
        setup_systemd
        setup_ssl
        restart_services
        check_status
        print_success "Full setup completed!"
        ;;
    "update")
        print_status "Updating MakonBook application..."
        setup_venv
        django_management
        restart_services
        check_status
        ;;
    "restart")
        restart_services
        check_status
        ;;
    "status")
        check_status
        ;;
    "ssl")
        setup_ssl
        restart_services
        ;;
    "logs")
        show_logs
        ;;
    "help"|*)
        show_help
        ;;
esac

print_success "Script execution completed!"