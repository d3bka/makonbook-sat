# Gunicorn Configuration for MakonBook SAT System
# Production-ready WSGI server configuration

import multiprocessing
import os

# Get project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Server socket
bind = f"unix:{PROJECT_DIR}/makonbook.sock"
backlog = 2048

# Socket permissions for nginx access
umask = 0o002  # This will create socket with 775 permissions

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging - use local logs directory
loglevel = "info"
accesslog = f"{PROJECT_DIR}/logs/access.log"
errorlog = f"{PROJECT_DIR}/logs/error.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "makonbook_gunicorn"

# Preload application for better performance
preload_app = True

# Graceful shutdown
graceful_timeout = 30

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
