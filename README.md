# Simple Media Player

A simple web-based media player controller for video playback.

## Features

-   **Video Management**:
   -   Upload video files.
   -   Delete videos from the playlist and disk (only when nothing is playing).
-   **Playback Control**:
   -   Play, pause, and stop video playback.
   -   Loop settings for single files or entire playlists.
   -   Auto-advance through playlist items.
-   **Playlist Editing**:
   -   Toggle "Edit Playlist" mode to reorder items.
      -   In edit mode, playback stops, and controls are disabled.
   -   Drag-and-drop playlist items to reorder them.
   -   Click "Save Playlist" to save the new order and exit edit mode. Playback will restart if something was running.

## Usage

1.  Start the Flask application: `python -m app.main`
2.  Access the web interface at: http://localhost:5000
3.  Upload videos using the upload section.
4.  Use the playback controls to manage video playback.
5.  Click "Edit Playlist" to rearrange your playlist.

## Technical Details

-   Built with Flask backend
-   Uses MPlayer for video playback
-   Persistent playlist storage with JSON
-   Real-time UI updates
-   maps to frame buffer fb0.
-   Provides logs to file in case of debugging problems

## Performance Optimization (Raspberry Pi)

To improve performance on resource-constrained devices like the Raspberry Pi, two main strategies are employed:

1.  **Video Transcoding (Offline)**:
    *   A bash script `transcode_videos.sh` is provided to convert videos to a more Pi-friendly format.
    *   This script uses `ffmpeg` to reduce resolution, frame rate, and bitrate.
    *   **WARNING**: This script **OVERWRITES** the original video files in the input directory (specified by `FFMPEG_INPUT_DIR`, default `app/uploads/`) with their transcoded versions. Make sure you have backups if you need the original high-quality files.
    *   **Usage**: Run `./transcode_videos.sh` from the project root. The script will give you a 5-second countdown to cancel before starting.
    *   The script reads configuration from the `.env` file (see below).

2.  **MPlayer Configuration (Runtime)**:
    *   When running on a device identified as `raspberrypi` (via the `KTV_TARGET_DEVICE` environment variable), MPlayer is launched with specific command-line options to reduce CPU load.
    *   These options include enabling frame dropping and using low-resolution decoding with fast processing options.
    *   These settings are also configurable via the `.env` file.

## Environment Variables (.env)

The application and associated scripts can be configured using a `.env` file in the project root. Create this file if it doesn't exist.

```dotenv
# General
KTV_TARGET_DEVICE=raspberrypi # Set to 'laptop' or other for non-Pi X11 output

# MPlayer performance options for Raspberry Pi (used by mplayer_controller.py)
MPLAYER_RPI_ENABLE_FRAMEDROP=true
MPLAYER_RPI_LAVDOPTS="lowres=1:fast:skiploopfilter=all"

# FFmpeg transcoding options (used by transcode_videos.sh)
# This script now OVERWRITES files in FFMPEG_INPUT_DIR.
FFMPEG_INPUT_DIR="app/uploads"
# FFMPEG_OUTPUT_DIR and FFMPEG_OUTPUT_SUFFIX are no longer used in overwrite mode.
# FFMPEG_OUTPUT_DIR="app/uploads_transcoded"
# FFMPEG_OUTPUT_SUFFIX="_small"
FFMPEG_SCALE="240:320"
FFMPEG_FPS="15"
FFMPEG_VIDEO_BITRATE="300k"
FFMPEG_AUDIO_BITRATE="64k"
FFMPEG_VIDEO_CODEC="libx264"
FFMPEG_AUDIO_CODEC="aac"
```

## Installation

1.  Clone the repository.
2.  Run the installation script: `./install.sh`
    *   This will install `mplayer`, `ffmpeg`, and Python dependencies.
3.  Activate the virtual environment: `source videoplayer/bin/activate`