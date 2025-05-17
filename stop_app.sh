#!/bin/bash

# Find Gunicorn process and send SIGTERM to gracefully shut down
# This targets the Gunicorn master process for your specific application.
PID=$(pgrep -f "gunicorn.*app.main:app")

if [ -z "$PID" ]; then
  echo "Gunicorn process not found."
else
  echo "Stopping Gunicorn process (PID: $PID)..."
  kill -TERM "$PID"
  # Wait a bit for graceful shutdown
  sleep 2
  # Check if it's still running and force kill if necessary
  if ps -p "$PID" > /dev/null; then
    echo "Gunicorn did not stop gracefully, forcing kill..."
    kill -KILL "$PID"
  fi
  echo "Gunicorn stopped."
fi
