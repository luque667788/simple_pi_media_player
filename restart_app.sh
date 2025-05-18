#!/bin/bash

APP_DIR=$(pwd)

echo "Restarting Simple Media Player..."

# Stop the application
"$APP_DIR/stop_app.sh"

# Wait a moment to ensure it has stopped
sleep 2

# For systemctl, we don't need to start the application in this script
# systemctl will handle starting the service after stopping it
# Instead, just make this script exit successfully

echo "Simple Media Player stopped, systemctl will now start it again."
exit 0
