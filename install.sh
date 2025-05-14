#!/bin/bash

echo "Starting Application Setup for Raspberry Pi..."

# --- 0. Configuration ---
# Determine the directory where the script is located
SCRIPT_DIR="$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" &> /dev/null && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
APP_DIR="$PROJECT_DIR/app"
UPLOAD_DIR="$APP_DIR/uploads"
STATIC_DIR="$APP_DIR/static"
TEMPLATES_DIR="$APP_DIR/templates"
LOG_DIR="$PROJECT_DIR" # For server.log, mpv.log

PYTHON_EXECUTABLE="python3"
PIP_EXECUTABLE="pip3"

# --- 1. System Update ---
echo "[INFO] Updating package lists and upgrading system..."
sudo apt update && sudo apt upgrade -y
if [ $? -ne 0 ]; then
    echo "[WARNING] System update/upgrade failed. Continuing, but some packages might not install correctly."
fi
echo "[SUCCESS] System update/upgrade step completed."

# --- 2. Install Dependencies ---
echo "[INFO] Installing required packages (python3, pip, mpv, git)..."
sudo apt install $PYTHON_EXECUTABLE ${PIP_EXECUTABLE} mpv git -y
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install one or more system packages (python3, pip3, mpv, git). Please check the output above and install them manually."
    exit 1
fi
echo "[SUCCESS] System dependencies installed."

# --- 3. Create Application Directories (if they don't exist) ---
echo "[INFO] Ensuring application directories exist..."
mkdir -p "$UPLOAD_DIR"
mkdir -p "$STATIC_DIR/css"
mkdir -p "$STATIC_DIR/js"
mkdir -p "$TEMPLATES_DIR"
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to create application directories."
    exit 1
fi
echo "[SUCCESS] Application directories verified/created."

# --- 4. Install Python Dependencies ---
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "[INFO] Installing Python dependencies from requirements.txt..."
    $PIP_EXECUTABLE install -r "$PROJECT_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install Python dependencies from requirements.txt. Ensure $PIP_EXECUTABLE is working and requirements.txt is valid."
        exit 1
    fi
    echo "[SUCCESS] Python dependencies installed."
else
    echo "[WARNING] requirements.txt not found in $PROJECT_DIR. Skipping Python dependency installation. Please create it and install manually if needed (e.g., pip3 install Flask Pillow)."
fi

# --- 5. Create Placeholder Log Files (if they don't exist) ---
echo "[INFO] Ensuring placeholder log files exist (server.log, mpv.log)..."
touch "$LOG_DIR/server.log"
touch "$LOG_DIR/mpv.log"
# Set permissions if necessary, e.g., if the app runs as a different user
# Example for user 'pi':
# sudo chown pi:pi "$LOG_DIR/server.log" "$LOG_DIR/mpv.log"
# sudo chmod 664 "$LOG_DIR/server.log" "$LOG_DIR/mpv.log"
echo "[SUCCESS] Log files verified/created."

# --- 6. MPV Check ---
echo "[INFO] Verifying MPV installation..."
if ! command -v mpv &> /dev/null
then
    echo "[ERROR] MPV could not be found. The installation might have failed. Please install MPV manually." 
    exit 1
fi
echo "[SUCCESS] MPV appears to be installed."

# --- 7. Final Instructions ---
echo ""
echo "---------------------------------------------------------------------"
echo "Installation Script Finished!"
echo "---------------------------------------------------------------------"
echo ""
echo "Project Directory: $PROJECT_DIR"
echo ""
echo "Next Steps:"
echo "1. IMPORTANT: Ensure your 2-inch display is correctly configured in Raspberry Pi OS (e.g., /boot/config.txt or /boot/firmware/config.txt)."
echo "   This script does NOT configure the display hardware itself."
echo "2. Review server.log and mpv.log in $LOG_DIR for any runtime errors."
echo "3. To run the application:"
echo "   cd $PROJECT_DIR"
echo "   $PYTHON_EXECUTABLE app/main.py"
echo ""
echo "The web interface should be accessible at http://<RaspberryPi_IP>:5000"
echo "MPV output will target the primary display (your 2-inch screen)."
echo ""
echo "To set up autostart (optional, using systemd):"
echo "   a. Create a service file, e.g., /etc/systemd/system/my_media_app.service"
cat << EOF_SERVICE_EXAMPLE

[Unit]
Description=My Simple Media Player Application
After=network.target graphical.target # Or multi-user.target if no X needed by MPV

[Service]
User=pi # CHANGE THIS if you run as a different user
Group=pi # CHANGE THIS if you run as a different user
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_EXECUTABLE $APP_DIR/main.py
Restart=always
StandardOutput=append:$LOG_DIR/server.log
StandardError=append:$LOG_DIR/server.log
# Environment="DISPLAY=:0" # Uncomment if MPV needs an X session on a specific display

[Install]
WantedBy=multi-user.target # Or graphical.target

EOF_SERVICE_EXAMPLE
echo "   b. Replace 'User=pi', 'Group=pi', and paths if necessary."
        echo "   c. sudo systemctl daemon-reload"
        echo "   d. sudo systemctl enable my_media_app.service"
        echo "   e. sudo systemctl start my_media_app.service"
echo "   f. Check status: sudo systemctl status my_media_app.service"
echo "---------------------------------------------------------------------"

exit 0
