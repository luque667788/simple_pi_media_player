# Simple Media Player

A simple web-based media player controller optimized for video playback on embedded devices, particularly Raspberry Pi with small displays.

For detailed information about the user interface and how to use the video player features, please refer to the [`HOWTO.md`](HOWTO.md) document.

## Features

-   **Video Management**:
   -   Upload video files with automatic transcoding for optimization.
   -   Delete videos from the playlist and disk (only when nothing is playing).
-   **Playback Control**:
   -   Play, pause, and stop video playback.
   -   Loop settings for single files or entire playlists.
   -   Auto-advance through playlist items.
-   **Playlist Editing**:
   -   Toggle "Edit Playlist" mode to reorder items.
      -   In edit mode, playback stops, and controls are disabled.
   -   Drag-and-drop playlist items to reorder them.
   -   Click "Save Playlist" to save the new order and exit edit mode.

## Project Structure

- **Application Code**: 
  - `app/` - Main Python Flask application directory
  - `app/main.py` - Entry point for the web application
  - `app/mplayer_controller.py` - Handles interaction with MPlayer
  - `app/static/` - CSS and JavaScript assets
  - `app/templates/` - HTML templates
  - `app/uploads/` - Directory for video files

- **Utility Scripts**:
  - `run_prod.sh` - Starts the application using Gunicorn
  - `stop_app.sh` - Gracefully stops the running application
  - `restart_app.sh` - Restarts the application by calling stop and run
  - `clean_env.sh` - Cleans log files and other temporary files
  - `transcode_videos.sh` - Batch transcodes videos to optimize for display
  - `install.sh` - Installs dependencies and sets up the application


## Development Usage
=======
-   Built with Flask backend for responsive web control
-   Uses MPlayer for optimized video playback on resource-constrained devices
-   Persistent playlist storage with JSON for reliable operation
-   Real-time UI updates for synchronized control experience
-   Maps directly to frame buffer fb1 for direct display output
-   Provides detailed logs to file for troubleshooting and debugging
-   Configured as a systemd service for automatic startup on boot


1.  Clone the repository.
2.  Run the installation script: `./install.sh`
    *   This will install `mplayer`, `ffmpeg`, and Python dependencies.
3.  Activate the virtual environment: `source videoplayer/bin/activate`
4.  Start the Flask development server: `python -m app.main`
5.  Access the web interface at: `http://localhost:5000`

## Production Usage

For production deployment, use the provided utility scripts:

- **Start the application**: `./run_prod.sh`  
  Launches the application using Gunicorn for better performance and reliability.
  
- **Stop the application**: `./stop_app.sh`  
  Gracefully terminates the running application.
  
- **Restart the application**: `./restart_app.sh`  
  Performs a clean restart by stopping and starting the application.
  
- **Access the web interface**: Navigate to `http://[device-ip]:5000` or `http://raspberrypi.local:5000` when running on Raspberry Pi



## Performance Optimization

Two main strategies are employed for optimized performance:

1.  **Video Transcoding**:
    *   When videos are uploaded via the web interface, they undergo automatic transcoding to optimize for the Pi's display and processing capabilities.
    *   This process resizes videos to match the display resolution (typically 240x320), reduces framerate to 15-20 FPS, and lowers color depth and bitrates.
    *   These optimizations are necessary because the Raspberry Pi decodes video on the CPU and the SPI display interface has bandwidth limitations.
    *   For offline batch processing, a bash script `transcode_videos.sh` is provided.
    *   Transcoding Time: Small videos (~10MB) take about 10 seconds, while larger files (~100MB) may take several minutes.
    *   **WARNING**: The `transcode_videos.sh` script **OVERWRITES** the original video files in the input directory (specified by `FFMPEG_INPUT_DIR`, default `app/uploads/`) with their transcoded versions. Make sure you have backups if you need the original high-quality files.
    *   **Usage**: Run `./transcode_videos.sh` from the project root. The script will give you a 5-second countdown to cancel before starting.
    *   The script reads configuration from the `.env` file (see below).

2.  **MPlayer Configuration (Runtime)**:
    *   When running on a device identified as `raspberrypi` (via the `KTV_TARGET_DEVICE` environment variable), MPlayer is launched with specific command-line options to reduce CPU load.
    *   These options include enabling frame dropping and using low-resolution decoding with fast processing options.
    *   These settings are also configurable via the `.env` file.

## Environment Variables (.env)

The application and associated scripts can be configured using a `.env` file in the project root:

```dotenv
# General
KTV_TARGET_DEVICE=raspberrypi # Set to 'laptop' or other for non-Pi X11 output

# MPlayer performance options
MPLAYER_RPI_ENABLE_FRAMEDROP=true
MPLAYER_RPI_LAVDOPTS="lowres=1:fast:skiploopfilter=all"

# FFmpeg transcoding options
FFMPEG_INPUT_DIR="app/uploads"
FFMPEG_SCALE="240:320"
FFMPEG_FPS="15"
FFMPEG_VIDEO_BITRATE="300k"
FFMPEG_AUDIO_BITRATE="64k"
FFMPEG_VIDEO_CODEC="libx264"
FFMPEG_AUDIO_CODEC="aac"
```

## Technical Details

-   Built with **Flask** backend for responsive web control
-   Uses **MPlayer** for optimized video playback on resource-constrained devices
-   **Persistent playlist** storage with JSON for reliable operation
-   **Real-time UI updates** for synchronized control experience
-   **Direct framebuffer output** for display on embedded devices
-   **Detailed logging** to help troubleshoot issues
-   Configured as a **systemd service** for automatic startup on boot

## Installation

1.  Clone the repository.
2.  Run the installation script: `./install.sh`
    *   This will install `mplayer`, `ffmpeg`, and Python dependencies.
3.  Activate the virtual environment: `source videoplayer/bin/activate`

## System Deployment

For information about:
- Setting up the Raspberry Pi hardware
- Flashing the pre-built image
- Network configuration
- Accessing the interface
- Hardware pinout details
- System configuration details (display, audio, network)
- Manual installation steps
- Troubleshooting


Please refer to the comprehensive [`HOWTO.md`](HOWTO.md) document.
=======
### What the Setup Script Does

1. **System Configuration**:
   - Updates and upgrades the system packages
   - Installs required tools (git, curl, raspi-config)
   - Enables SSH for remote access
   - Enables SPI and I2C interfaces required for the display

2. **Display Configuration**:
   - Configures the ST7789V SPI display by adding framebuffer overlay to `/boot/firmware/config.txt`
   - Sets up resolution, pin connections, and rotation parameters
   - Updates framebuffer console mapping in boot command line
   - **Important**: Disables HDMI video output (`hdmi_blanking=2`) to save resources and prevent conflicts
   
3. **Audio Configuration**:
   - Note that while HDMI video is disabled, audio through HDMI port 0 is still available
   - If you need audio output, connect to the HDMI port and configure audio settings as needed

4. **Network Setup**:
   - Includes manual step for installing RaspAP for Wi-Fi hotspot functionality
   - This must be done manually by running: `curl -sL https://install.raspap.com | bash`

5. **Application Installation**:
   - Creates development folder and clones the media player repository
   - Runs the installation script to set up dependencies
   - Configures a systemd service for automatic startup

### Manual Steps Required

Even if using the setup script, some manual intervention is required:

1. You must manually install RaspAP when prompted
2. A system reboot is recommended after running the script
3. If framebuffer device `/dev/fb1` is not detected immediately, a reboot will be necessary
4. You may need to adjust permissions or system settings based on your specific Raspberry Pi model

### Note on HDMI Configuration

TThe script always enables the HDMI output by setting up the /boot/firmware/config.txt file the following lines:

`hdmi_force_hotplug=1`
`hdmi_drive=2`

So that it is always mapped to frame buffer 0 and the terminal should be presented there in the HDMI instead of in the spi display.
