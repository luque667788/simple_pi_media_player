#!/bin/bash

APP_DIR=$(pwd)

echo "Restarting Kanga Media Player..."

# Stop the application
"$APP_DIR/stop_app.sh"

# Wait a moment to ensure it has stopped
sleep 2

# Start the application
"$APP_DIR/run_prod.sh"

echo "Kanga Media Player restart sequence complete."
