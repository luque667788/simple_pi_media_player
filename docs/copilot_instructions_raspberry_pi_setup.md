# Raspberry Pi Setup and Installation Script

## 1. Overview

This document outlines the setup steps for the Raspberry Pi 4 Model B and provides a basic installation script (`install.sh`) to prepare the environment for the application.

**Assumptions:**

*   Raspberry Pi OS (Debian-based, e.g., Bullseye) is already installed and functional.
*   The Raspberry Pi has internet connectivity.
*   The 2-inch screen (240x320) is connected and configured at the OS level (e.g., via `/boot/config.txt` for SPI/HDMI displays). This application will not handle low-level display driver setup.

## 2. Required Software on Raspberry Pi

*   **Python 3**: Usually pre-installed.
*   **pip** (Python package installer).
*   **Flask**: Python web framework.
*   **MPV Media Player**: The core playback engine.
*   **Git** (optional, for cloning the project).

## 3. Manual Setup Steps (if not covered by script)

1.  **Update System:**
    ```bash
    sudo apt update
    sudo apt upgrade -y
    ```

2.  **Install Python 3 and pip (if not present):**
    ```bash
    sudo apt install python3 python3-pip -y
    ```

3.  **Install MPV:**
    ```bash
    sudo apt install mpv -y
    ```

4.  **Install Git (optional):**
    ```bash
    sudo apt install git -y
    ```

5.  **Configure Display (Crucial for 2-inch screen):**
    *   This step is highly dependent on the specific 2-inch screen model and how it connects (SPI, HDMI).
    *   Typically involves editing `/boot/config.txt` to set display parameters, resolution, and enable necessary overlays (e.g., for SPI screens).
    *   **Example for a generic SPI display (consult screen's documentation!):**
        ```ini
        # In /boot/config.txt
        hdmi_force_hotplug=1 # If it's an HDMI display
        # For SPI displays, you might have lines like:
        # dtparam=spi=on
        # dtoverlay=tft35a:rotate=90 # Example, specific overlay for your screen
        # framebuffer_width=240
        # framebuffer_height=320
        ```
    *   Reboot after changes to `/boot/config.txt`.
    *   Ensure the console or X environment (if used) appears correctly on the 2-inch screen before running the app. MPV will use this existing setup.

## 4. `install.sh` Script

This script will automate the installation of dependencies and project setup.

```bash
#!/bin/bash

echo "Starting Application Setup for Raspberry Pi..."

# --- 1. System Update ---
echo "[INFO] Updating package lists and upgrading system..."
sudo apt update
sudo apt upgrade -y
echo "[SUCCESS] System updated."

# --- 2. Install Dependencies ---
echo "[INFO] Installing required packages (python3, pip, mpv, git)..."
sudo apt install python3 python3-pip mpv git -y
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install one or more system packages. Please check the output above."
    exit 1
fi
echo "[SUCCESS] System dependencies installed."

# --- 3. Project Directory (Assuming script is run from project root or project cloned here) ---
PROJECT_DIR=$(pwd) # Or set to a specific path if preferred
APP_DIR="$PROJECT_DIR/app"
UPLOAD_DIR="$APP_DIR/uploads"
STATIC_DIR="$APP_DIR/static"
TEMPLATES_DIR="$APP_DIR/templates"
LOG_DIR="$PROJECT_DIR" # For server.log, mpv.log

echo "[INFO] Project directory: $PROJECT_DIR"

# --- 4. Create Application Directories ---
echo "[INFO] Creating application directories (app, uploads, static, templates)..."
mkdir -p "$UPLOAD_DIR"
mkdir -p "$STATIC_DIR/css"
mkdir -p "$STATIC_DIR/js"
mkdir -p "$TEMPLATES_DIR"
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to create application directories."
    exit 1
fi
echo "[SUCCESS] Application directories created."

# --- 5. Install Python Dependencies (Flask) ---
# Assuming a requirements.txt file will be created for the project
# Create a simple requirements.txt for now
echo "[INFO] Creating requirements.txt..."
cat << EOF > "$PROJECT_DIR/requirements.txt"
Flask==2.0.1 # Or a more recent stable version
EOF

echo "[INFO] Installing Python dependencies from requirements.txt..."
pip3 install -r "$PROJECT_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install Python dependencies. Ensure pip3 is working."
    exit 1
fi
echo "[SUCCESS] Python dependencies installed."

# --- 6. Create Placeholder Log Files ---
echo "[INFO] Creating placeholder log files (server.log, mpv.log)..."
touch "$LOG_DIR/server.log"
touch "$LOG_DIR/mpv.log"
# Set permissions if necessary, e.g., if the app runs as a different user
# sudo chown pi:pi "$LOG_DIR/server.log" "$LOG_DIR/mpv.log" # Example for user 'pi'
echo "[SUCCESS] Log files created."


# --- 7. Final Instructions ---
echo ""
echo "---------------------------------------------------------------------"
echo "Installation Complete!"
echo "---------------------------------------------------------------------"
echo ""
echo "Next Steps:"
echo "1. Ensure your 2-inch display is correctly configured in /boot/config.txt and working."
echo "   This script does NOT configure the display hardware."
echo "2. Place your application files (main.py, mpv_controller.py, etc.) in the '$APP_DIR' directory."
echo "3. Place your HTML/CSS/JS files in '$STATIC_DIR' and '$TEMPLATES_DIR'."
echo "4. To run the application:"
echo "   cd $PROJECT_DIR"
echo "   python3 app/main.py"
echo ""
echo "The web interface should be accessible at http://<RaspberryPi_IP>:5000"
echo "MPV output will target the primary display (your 2-inch screen)."
echo "---------------------------------------------------------------------"

exit 0
```

## 5. Running the Application

1.  Make the script executable: `chmod +x install.sh`
2.  Run the script: `./install.sh`
3.  After installation, navigate to the project directory.
4.  Run the Flask application: `python3 app/main.py`
5.  Access the web interface from another device on the same network via `http://<RaspberryPi_IP_Address>:5000`.

## 6. Autostarting the Application (Optional)

For the application to start automatically on boot:

*   **Systemd Service:** This is the recommended method.
    1.  Create a service file, e.g., `/etc/systemd/system/my_media_app.service`:
        ```ini
        [Unit]
        Description=My Media Player Application
        After=network.target multi-user.target graphical.target # Ensure network and display are ready
        # If your display needs X server, you might need to ensure X is running first
        # Or if using DRM/KMS, ensure it's initialized.

        [Service]
        User=pi # Or the user your app should run as
        Group=pi
        WorkingDirectory=/home/pi/project_root # CHANGE TO YOUR PROJECT PATH
        ExecStart=/usr/bin/python3 /home/pi/project_root/app/main.py # CHANGE TO YOUR PROJECT PATH
        Restart=always # Restart if it crashes
        StandardOutput=file:/home/pi/project_root/server.log # Redirect stdout to log
        StandardError=file:/home/pi/project_root/server.log  # Redirect stderr to log

        [Install]
        WantedBy=multi-user.target # Or graphical.target if it needs GUI session
        ```
    2.  Replace `/home/pi/project_root` with the actual path to your project.
    3.  Replace `User=pi` and `Group=pi` if you use a different user.
    4.  Enable and start the service:
        ```bash
        sudo systemctl daemon-reload
        sudo systemctl enable my_media_app.service
        sudo systemctl start my_media_app.service
        ```
    5.  Check status: `sudo systemctl status my_media_app.service`

*   **rc.local (Simpler, less robust):**
    *   Edit `/etc/rc.local` and add the command to run your script before `exit 0`:
        ```bash
        python3 /home/pi/project_root/app/main.py &
        ```
    *   Ensure `/etc/rc.local` is executable.

**Note on Display for Autostart:** If MPV requires an X session, ensure the systemd service or autostart method correctly provides it. For a dedicated Pi display, running MPV directly with DRM/KMS (if supported by MPV build and display) or a minimal X session (e.g., using `openbox` or just `xinit`) might be necessary. The `--force-window=immediate` and other MPV flags help here. The systemd service might need `Environment="DISPLAY=:0"` if an X server is running on display :0.
