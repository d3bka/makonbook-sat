#!/bin/bash

# MakonBook SAT System - Unified Management Script
# Replaces: start_makonbook.sh, stop_makonbook.sh, start_telegram_bot.sh, stop_telegram_bot.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/home/satmakon/makonbook"
VENV_DIR="$PROJECT_DIR/venv"
WEB_PID_FILE="$PROJECT_DIR/makonbook.pid"
BOT_PID_FILE="$PROJECT_DIR/telegram_bot.pid"
LOG_DIR="$PROJECT_DIR/logs"

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

# Change to project directory
cd "$PROJECT_DIR"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to check if process is running
is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Running
        else
            rm -f "$pid_file"  # Remove stale PID file
            return 1  # Not running
        fi
    fi
    return 1  # Not running
}

# Function to start web application
start_web() {
    print_status "Starting MakonBook web application..."
    
    if is_running "$WEB_PID_FILE"; then
        local pid=$(cat "$WEB_PID_FILE")
        print_warning "Web application is already running with PID $pid"
        return 0
    fi
    
    # Remove old socket file if it exists
    if [ -S "$PROJECT_DIR/makonbook.sock" ]; then
        rm -f "$PROJECT_DIR/makonbook.sock"
        print_status "Removed old socket file"
    fi
    
    # Start gunicorn
    gunicorn \
        --bind unix:"$PROJECT_DIR/makonbook.sock" \
        --daemon \
        --pid "$WEB_PID_FILE" \
        --access-logfile "$LOG_DIR/access.log" \
        --error-logfile "$LOG_DIR/error.log" \
        --log-level info \
        --workers 3 \
        --timeout 30 \
        --umask 0o002 \
        satmakon.wsgi:application
    
    # Wait a moment for socket to be created
    sleep 2
    
    # Fix socket permissions for nginx
    if [ -S "$PROJECT_DIR/makonbook.sock" ]; then
        chmod 660 "$PROJECT_DIR/makonbook.sock"
        print_status "Socket permissions set for nginx access"
    fi
    
    if is_running "$WEB_PID_FILE"; then
        local pid=$(cat "$WEB_PID_FILE")
        print_success "Web application started successfully! PID: $pid"
    else
        print_error "Failed to start web application"
        return 1
    fi
}

# Function to stop web application
stop_web() {
    print_status "Stopping MakonBook web application..."
    
    if [ -f "$WEB_PID_FILE" ]; then
        local pid=$(cat "$WEB_PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            print_status "Stopping process $pid..."
            kill "$pid"
            
            # Wait for process to stop
            for i in {1..10}; do
                if ! ps -p "$pid" > /dev/null 2>&1; then
                    print_success "Web application stopped successfully!"
                    rm -f "$WEB_PID_FILE"
                    break
                fi
                sleep 1
            done
            
            # Force kill if still running
            if ps -p "$pid" > /dev/null 2>&1; then
                print_warning "Force killing process..."
                kill -9 "$pid" 2>/dev/null || true
                rm -f "$WEB_PID_FILE"
                print_success "Web application force stopped!"
            fi
        else
            print_status "Process not running, removing stale PID file"
            rm -f "$WEB_PID_FILE"
        fi
    else
        print_status "Web application is not running"
    fi
    
    # Remove socket file if it exists
    if [ -S "$PROJECT_DIR/makonbook.sock" ]; then
        rm -f "$PROJECT_DIR/makonbook.sock"
        print_status "Removed socket file"
    fi
}

# Function to start telegram bot
start_bot() {
    print_status "Starting MakonBook Telegram bot..."
    
    if is_running "$BOT_PID_FILE"; then
        local pid=$(cat "$BOT_PID_FILE")
        print_warning "Telegram bot is already running with PID $pid"
        return 0
    fi
    
    # Load environment variables from .env file
    if [ -f ".env" ]; then
        export $(cat .env | grep -v "^#" | grep -v "^$" | xargs)
        print_status "Environment variables loaded from .env"
    fi
    
    # Start the bot in background
    nohup python manage.py run_telegram_bot > "$LOG_DIR/telegram_bot.log" 2>&1 &
    local bot_pid=$!
    
    # Save PID
    echo $bot_pid > "$BOT_PID_FILE"
    
    sleep 2
    
    if is_running "$BOT_PID_FILE"; then
        print_success "Telegram bot started successfully! PID: $bot_pid"
    else
        print_error "Failed to start Telegram bot"
        return 1
    fi
}

# Function to stop telegram bot
stop_bot() {
    print_status "Stopping MakonBook Telegram bot..."
    
    if [ -f "$BOT_PID_FILE" ]; then
        local pid=$(cat "$BOT_PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            print_status "Stopping process $pid..."
            kill "$pid"
            
            # Wait for process to stop
            for i in {1..10}; do
                if ! ps -p "$pid" > /dev/null 2>&1; then
                    print_success "Telegram bot stopped successfully!"
                    rm -f "$BOT_PID_FILE"
                    break
                fi
                sleep 1
            done
            
            # Force kill if still running
            if ps -p "$pid" > /dev/null 2>&1; then
                print_warning "Force killing process..."
                kill -9 "$pid" 2>/dev/null || true
                rm -f "$BOT_PID_FILE"
                print_success "Telegram bot force stopped!"
            fi
        else
            print_status "Process not running, removing stale PID file"
            rm -f "$BOT_PID_FILE"
        fi
    else
        print_status "Telegram bot is not running"
    fi
}

# Function to check status
check_status() {
    print_status "Checking MakonBook system status..."
    echo ""
    
    # Check web application
    if is_running "$WEB_PID_FILE"; then
        local pid=$(cat "$WEB_PID_FILE")
        print_success "Web Application: RUNNING (PID: $pid)"
    else
        print_error "Web Application: STOPPED"
    fi
    
    # Check telegram bot
    if is_running "$BOT_PID_FILE"; then
        local pid=$(cat "$BOT_PID_FILE")
        print_success "Telegram Bot: RUNNING (PID: $pid)"
    else
        print_error "Telegram Bot: STOPPED"
    fi
    
    # Check nginx
    if systemctl is-active --quiet nginx; then
        print_success "Nginx: RUNNING"
    else
        print_error "Nginx: STOPPED"
    fi
    
    # Check PostgreSQL
    if systemctl is-active --quiet postgresql; then
        print_success "PostgreSQL: RUNNING"
    else
        print_error "PostgreSQL: STOPPED"
    fi
    
    echo ""
    print_status "Socket: $PROJECT_DIR/makonbook.sock"
    print_status "Logs: $LOG_DIR/"
}

# Function to show logs
show_logs() {
    echo -e "${BLUE}=== Web Application Logs (last 20 lines) ===${NC}"
    tail -20 "$LOG_DIR/error.log" 2>/dev/null || echo "No web logs found"
    
    echo -e "\n${BLUE}=== Telegram Bot Logs (last 20 lines) ===${NC}"
    tail -20 "$LOG_DIR/telegram_bot.log" 2>/dev/null || echo "No bot logs found"
    
    echo -e "\n${BLUE}=== Nginx Error Logs (last 10 lines) ===${NC}"
    sudo tail -10 /var/log/nginx/error.log 2>/dev/null || echo "No nginx logs found"
}

# Function to show help
show_help() {
    echo -e "${BLUE}MakonBook SAT System - Management Script${NC}"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start-web       - Start web application (Gunicorn)"
    echo "  stop-web        - Stop web application"
    echo "  restart-web     - Restart web application"
    echo ""
    echo "  start-bot       - Start Telegram bot"
    echo "  stop-bot        - Stop Telegram bot"
    echo "  restart-bot     - Restart Telegram bot"
    echo ""
    echo "  start-all       - Start both web and bot"
    echo "  stop-all        - Stop both web and bot"
    echo "  restart-all     - Restart both web and bot"
    echo ""
    echo "  status          - Check system status"
    echo "  logs            - Show recent logs"
    echo "  help            - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 start-all"
    echo "  $0 status"
    echo "  $0 restart-web"
    echo "  $0 logs"
}

# Main command handling
case "${1:-help}" in
    "start-web")
        start_web
        ;;
    "stop-web")
        stop_web
        ;;
    "restart-web")
        stop_web
        start_web
        ;;
    "start-bot")
        start_bot
        ;;
    "stop-bot")
        stop_bot
        ;;
    "restart-bot")
        stop_bot
        start_bot
        ;;
    "start-all")
        start_web
        start_bot
        check_status
        ;;
    "stop-all")
        stop_web
        stop_bot
        ;;
    "restart-all")
        stop_web
        stop_bot
        start_web
        start_bot
        check_status
        ;;
    "status")
        check_status
        ;;
    "logs")
        show_logs
        ;;
    "help"|*)
        show_help
        ;;
esac

exit 0