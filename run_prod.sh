#!/bin/bash

# Navigate to the application directory (adjust if your script is not in the root)
APP_DIR=$(pwd)
LOG_FILE="gunicorn.log"
ERROR_LOG_FILE="gunicorn_error.log"

# Activate the virtual environment
source "$APP_DIR/videoplayer/bin/activate"

# Start Gunicorn server
# The --daemon flag runs Gunicorn in the background.
# You can adjust the number of workers (-w) based on your Raspberry Pi's CPU cores.
# For a Raspberry Pi, 2-4 workers are usually a good starting point.
# Bind to 0.0.0.0 to make it accessible from other devices on your network.
echo "Starting Gunicorn..."
# Removed --daemon flag so systemd can properly track the process
exec gunicorn --workers 1 \
        --bind 0.0.0.0:5000 \
        --log-level=info \
        --access-logfile "$APP_DIR/$LOG_FILE" \
        --error-logfile "$APP_DIR/$ERROR_LOG_FILE" \
        app.main:app

# The exec command above replaces the current process with gunicorn
# so these lines will never be reached, but if for some reason exec fails:
echo "Gunicorn failed to start. Check $APP_DIR/$ERROR_LOG_FILE for details."
