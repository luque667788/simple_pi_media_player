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
gunicorn --workers 1 \
         --bind 0.0.0.0:5000 \
         --log-level=info \
         --access-logfile "$APP_DIR/$LOG_FILE" \
         --error-logfile "$APP_DIR/$ERROR_LOG_FILE" \
         --daemon \
         app.main:app

# Check if Gunicorn started successfully
if pgrep -f "gunicorn.*app.main:app" > /dev/null; then
  echo "Gunicorn started successfully."
  echo "Access the application at http://<your_pi_ip>:5000"
  echo "Logs: $APP_DIR/$LOG_FILE and $APP_DIR/$ERROR_LOG_FILE"
else
  echo "Gunicorn failed to start. Check $APP_DIR/$ERROR_LOG_FILE for details."
fi
