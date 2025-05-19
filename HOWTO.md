# DOCUMENTATION: Raspberry Pi Video Playback System

## Table of Contents
1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
   - [Initial Setup: Flashing the Image](#initial-setup-flashing-the-image)
   - [Important Credentials](#important-credentials)
3. [Basic Usage](#basic-usage)
   - [Network Configuration via RaspAp](#network-configuration-via-raspap)
   - [Accessing the Video Control Interface](#accessing-the-video-control-interface)
   - [Video Playback Features](#video-playback-features)
   - [Uploading MP4 Files](#uploading-mp4-files)
4. [System Management](#system-management)
   - [Application Management and Autostart](#application-management-and-autostart)
   - [Troubleshooting and Basic Information](#troubleshooting-and-basic-information)
5. [Advanced Technical Information](#advanced-technical-information)
   - [System Configuration Details](#system-configuration-details)
   - [Manual Installation Instructions](#manual-installation-instructions)
6. [Important Notes and Disclaimers](#important-notes-and-disclaimers)

## Introduction

This document provides instructions on setting up and using the custom Raspberry Pi image for video playback on a small display. The system is designed to be easy to use while providing reliable playback of video content.

Many of the information that is mentioned here is repeated in the delivery description you can find right here: https://gitshare.me/repo/41d890c1-ade8-4809-8dc9-f30df3288586?password=luiz

However here I try to go a little more in detail on the topics.

## Getting Started

### Initial Setup: Flashing the Image

1. Download the provided .img file for the Raspberry Pi.
2. Use the Raspberry Pi Imager tool (or a similar SD card flashing utility).
3. In Raspberry Pi Imager, choose "Use custom" (or "Choose OS" then "Use custom") and select the downloaded .img file.
4. Select your SD card as the target and proceed to write the image.

### Important Credentials

Keep these credentials handy for accessing the various components of the system:

- **Raspberry Pi OS Login**:
  - Username: pi
  - Password: q1w2e3r4
- **RaspAp Wi-Fi Hotspot (Default)**:
  - Network Name (SSID): RaspAp
  - Password: ChangeMe
- **RaspAp Web Interface** (http://raspberrypi.local):
  - Username: admin
  - Password: secret
- **Video Control Web Interface** (http://raspberrypi.local:5000):
  - No login required; access is direct.

## Basic Usage

### Network Configuration via RaspAp

Once the Raspberry Pi boots up with the flashed SD card, it creates a Wi-Fi hotspot.

1. **Connect to the Hotspot**:
   - Search for a Wi-Fi network named "RaspAp".
   - Connect to this network using the password: ChangeMe.

2. **Accessing the RaspAp Web Interface**:
   - After connecting to the Raspberry Pi's Wi-Fi network, open a web browser.
   - Navigate to: http://raspberrypi.local
   - Log in using the credentials provided in the previous section.

3. **Using RaspAp**:
   - RaspAp (Raspberry Pi Access Point) simplifies network management, allowing you to:
     - Monitor basic system statistics.
     - Configure the Raspberry Pi to connect to an existing Wi-Fi network.
     - Perform basic system commands like rebooting or shutting down the Pi.
   - Note: If your computer is connected only to the Raspberry Pi's hotspot, your computer will not have internet access. To allow both internet access, use RaspAp to connect the Pi to your local Wi-Fi network, and then connect your computer to the same network.
   - For more details, visit: https://raspap.com/#promo

### Accessing the Video Control Interface

The main application for controlling video playback has its own web interface.

1. **Access Address**:
   - Ensure your device is connected to the same network as the Raspberry Pi.
   - Open a web browser and go to: http://raspberrypi.local:5000

2. **Interface Overview**:
   - The user interface is designed to be simple and self-explanatory.
   For more details on the playback modes and controls, refer to the [Video Playback Features](#video-playback-features) section.

### Video Playback Features

The video control interface offers several playback modes and controls:

1. **Playback Modes**:
   - **Play/Stop**: Basic playback of the selected file or playlist.
   - **Loop File**: Continuously plays a single selected video file.
   - **Playlist Mode**: Plays through a list of uploaded videos.
     - Editing the playlist order will restart playback from the beginning of the new playlist.
     - 'Next' and 'Previous' controls are available.
     - The system automatically advances to the next video when the current one finishes.
     - The playlist will loop back to the beginning after the last video has played.

2. **Controls**:
   - **Play**: Starts playback from the beginning of the playlist or unpauses a paused video.
   - **Pause**: Pauses the current video.
   - **Stop**: Clears the screen (makes it black) and terminates the player process.
   - **Next/Previous**: (Playlist Mode only) Skips to the next or previous video in the playlist.
   - **Restart MPlayer Process**: Similar to clicking 'Stop' and then 'Play'.
   - **Refresh Status**: Generally not needed as the application automatically updates.

3. **Note on Playback Behavior**:
   - When a video finishes playing (without looping), the display will hold the last frame. Clicking 'Stop' will clear the screen.
   - Due to limitations with MPlayer, real-time changes to the queue order while playing are not possible

### Uploading MP4 Files

1. **Supported Format**: MP4 files can be uploaded via the web interface.

2. **File Size Recommendation**: Keep individual uploads under 100MB due to Raspberry Pi processing limitations.

3. **Transcoding Process**:
   - When uploaded, videos are automatically transcoded to match the display's resolution, reducing framerate and color depth.
   - This optimization is necessary because the Raspberry Pi decodes video on the CPU, and the SPI interface has bandwidth limitations.
   - While this reduces quality, it's generally not noticeable on the small display.
   
4. **Processing Time**:
   - Small videos (~10MB): About 10 seconds
   - Larger videos (~100MB): Several minutes (potentially around 5 minutes or more)
   - During transcoding of large videos, the CPU will work intensively and may become hot.
   
5. **Upload Condition**: You can only upload videos when nothing is currently playing and the mplayer process is not running (click the stop button on the UI).

## System Management

### Application Management and Autostart

- The video playback application starts automatically when the Raspberry Pi boots up.
- It runs as a systemctl service named simple_media_player.service.
- Management commands (if needed):
  ```
  sudo systemctl stop simple_media_player.service
  sudo systemctl start simple_media_player.service
  sudo systemctl restart simple_media_player.service
  sudo systemctl status simple_media_player.service
  ```

- The application also includes these utility scripts that are used internally in the setup:
  - `run_prod.sh` - Starts the application using Gunicorn
  - `stop_app.sh` - Gracefully stops the running application
  - `restart_app.sh` - Restarts the application by calling stop and run
  - `clean_env.sh` - Cleans log files, playlist files, and uploaded videos
  - `transcode_videos.sh` - Batch transcodes videos to optimize for display

### Troubleshooting and Basic Information

- **Log Files**:
  - Log files are generated in the development/simple_pi_media_player/ directory.
  - These can be helpful for debugging if you encounter issues.

- **Development Folder**:
  - Custom code for the web server, frontend, and video player control resides in development/simple_pi_media_player/.
  - A small README is present there that attempts to give an introduction to the codebase, but modification is not recommended without familiarity with codebase.

- **.env Configuration File**:
  - A .env file is included with variables that can be changed for custom setups.
  - This is not typically required for standard operation (you can ignore it unless you want to tweak with it a little but then do it on your own responsibility).

- **Performance Considerations**:
  - The Raspberry Pi CPU can get quite hot during prolonged video processing or playback.
  - Using a heatsink is recommended for long-term deployment.
  - The maximum achievable framerate is approximately 15-20 FPS.
  - If the target framerate cannot be met, frames will be dropped to prevent slow-motion playback.

## Advanced Technical Information

### System Configuration Details

This section provides insight into how the Raspberry Pi system is configured and how could another developer configure it in the same way (without using the prebuilt image that was provided).

1. **OS Setup Script**:
   - The image includes an `OS_setup.sh` script documenting the system configuration process.
   - This can serve as a reference if setting up from scratch, though using the pre-built image is recommended.
   - Manual intervention would be required even when using the script.

2. **System Configuration Components**:
   - **System essentials**: Updates packages and installs required tools (git, curl, raspi-config)
   - **Interface enablement**: Activates SSH, SPI, and I2C interfaces
   - **Display configuration**: Sets up the ST7789V SPI display through framebuffer overlay
   - **Boot parameters**: Configures proper framebuffer console mapping
   - **Application setup**: Creates directories, clones repositories, and configures systemd services

3. **Display Configuration Details**:
   - Video output goes to the small SPI-connected display via framebuffer.
   - HDMI video output is intentionally disabled (using hdmi_blanking=2 in config.txt).
   - The framebuffer overlay uses specific settings for the ST7789V display (reset_pin=27, dc_pin=25, led_pin=18).

4. **Audio Configuration**:
   - While HDMI video is disabled, audio through HDMI port 0 is still available.
   - You can connect to the HDMI port for audio despite no video being displayed.

5. **Framebuffer Setup**:
   - The system uses framebuffer device (/dev/fb0) to send video data to the display.
   - This is configured through dtoverlay settings in /boot/firmware/config.txt and cmdline.txt modifications.

6. **Network Configuration**:
   - RaspAP installation (for Wi-Fi hotspot) must be done manually if setting up from scratch.
   - Command: `curl -sL https://install.raspap.com | bash`
   ### Systemctl Setup

   The video playback application is managed as a systemd service, ensuring it starts automatically on boot and can be easily controlled. Below is the configuration file used for the service:

   ```ini
   [Unit]
   Description=Simple Media Player Service
   After=network.target

   [Service]
   Type=simple
   ExecStart=/bin/bash /pi/development/simple_pi_media_player/run_prod.sh
   ExecStop=/bin/bash /pi/development/simple_pi_media_player/stop_app.sh
   ExecReload=/bin/bash /pi/development/simple_pi_media_player/restart_app.sh
   WorkingDirectory=/home/pi/development/simple_pi_media_player
   Restart=on-failure
   RestartSec=5
   User=pi
   Group=pi

   [Install]
   WantedBy=multi-user.target
   ```

   This file is located at `/systemd/system/simple_media_player.service` and can be edited using the following command:

   ```bash
   sudo nano /systemd/system/simple_media_player.service
   ```

   ### Key Features of the Service

   - **Automatic Startup**: The service starts automatically when the Raspberry Pi boots up.
   - **Restart on Failure**: If the application crashes, the service will attempt to restart it after 5 seconds.
   - **Custom Scripts**: The service uses the provided `run_prod.sh`, `stop_app.sh`, and `restart_app.sh` scripts for managing the application lifecycle.
   - **User and Group**: The service runs under the `pi` user and group for proper permissions.

   ### Managing the Service

   Use the following commands to control the service:

   - Start the service:
      ```bash
      sudo systemctl start simple_media_player.service
      ```
   - Stop the service:
      ```bash
      sudo systemctl stop simple_media_player.service
      ```
   - Restart the service:
      ```bash
      sudo systemctl restart simple_media_player.service
      ```
   - Check the service status:
      ```bash
      sudo systemctl status simple_media_player.service
      ```

   ### Enabling the Service

   To ensure the service starts on boot, enable it with:

   ```bash
   sudo systemctl enable simple_media_player.service
   ```

   If changes are made to the service file, reload the systemd daemon and restart the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart simple_media_player.service
   ```

7. **Required Manual Steps** (if not using pre-built image):
   - Installing RaspAP when prompted by the setup script
   - Rebooting after script completion
   - Additional reboots may be necessary if framebuffer device is not detected
   - Adjusting permissions based on specific Raspberry Pi model

### Manual Installation Instructions

The installation script provided serves as a template for users with Linux experience who wish to implement a custom solution. It has not been extensively tested and may require manual adjustments to ensure proper functionality. Users are advised to proceed with caution and make modifications as needed based on their specific requirements.

- **Strong Recommendation**: Use the pre-built image provided by flashing the .img file.
- **Warning**: The manual installation script has not been extensively tested.
- **Complexity**: Manual setup is more complex and requires additional troubleshooting.
- **Reliability**: Flashing the image is a much simpler and more reliable method.

## Important Notes and Disclaimers

- **Software Maturity**: This software was developed to meet specific requirements and has undergone testing. However, it was created in a short timeframe and is not considered production-ready for critical applications without further testing.

- **Scope**: Creating a full-featured media player is a significant project. This solution provides a simplified player specific to the project's specific needs and display capabilities and doesnt have and never will have all the features of a fully fledged play software that was designed by big open source communities.

- **Display Limitations**: The Waveshare display is small with limitations in resolution and color depth. The video playback has been optimized for this specific hardware. As already discussed in the chat the frame rate is not ideal.