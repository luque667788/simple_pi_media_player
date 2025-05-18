#!/bin/bash

# Find Gunicorn process and send SIGTERM to gracefully shut down
# This targets the Gunicorn master process for your specific application.
PIDS=( $(pgrep -f "gunicorn.*app.main:app") )

if [ ${#PIDS[@]} -eq 0 ]; then
  echo "Gunicorn process not found."
else
  echo "Stopping Gunicorn process (PIDs: ${PIDS[@]})..."
  kill -TERM "${PIDS[@]}"
  # Wait a bit for graceful shutdown
  sleep 2
  # Check if any are still running and force kill if necessary
  for PID in "${PIDS[@]}"; do
    if ps -p "$PID" > /dev/null; then
      echo "Gunicorn PID $PID did not stop gracefully, forcing kill..."
      kill -KILL "$PID"
    fi
  done
  echo "Gunicorn stopped."
fi
