# Media Player User Guide (Raspberry Pi + Docker Edition)

## Overview
This media player is designed for Raspberry Pi 4 (64-bit OS) and runs in a Docker container. It uses MPV for playback and supports video and image playlists, with output mapped to the Pi's framebuffer (`/dev/fb0`).

## Features
- Play, pause, toggle pause, and stop (black screen)
- Next/previous navigation
- Playlist management: upload, delete, reorder, and 'play next'
- Loop modes: none, loop current file, loop playlist (auto-advance)
- Auto-advance for images with configurable timer
- MPV process management (restart from UI)
- Web UI for all controls (accessible on port 5000)

## Usage

### 1. Running on Raspberry Pi
- The app is packaged as a Docker container. See below for build and run instructions.
- MPV outputs to `/dev/fb0` (framebuffer) and `/dev/snd` (audio).
- The web interface is available at `http://<raspberry-pi-ip>:5000`.

### 2. Playback Controls
- **Play**: Start playback from the current playlist position
- **Pause**: Pause playback
- **Toggle Pause**: Switch between play and pause
- **Stop (Black Screen)**: Stop playback and blank the screen
- **Previous/Next**: Move to previous or next item in the playlist

### 3. Playlist Management
- **Upload Files**: Add new media (video/image) files to the playlist
- **Delete**: Remove files from playlist and disk
- **Play Next**: Move a file to play immediately after the current one (does not interrupt current playback)

### 4. Loop and Auto-Advance
- **No Loop**: Playback stops at the end of the playlist
- **Loop Current File**: Repeat the current file indefinitely
- **Loop Playlist**: Auto-advance through the playlist and loop back to the start
- **Auto-Advance Interval**: Set time (in seconds) to auto-advance images; set to 0 to disable

### 5. MPV Process Management
- **Restart MPV**: Use the UI button to restart the MPV process if playback is stuck or desynced
- **Loop mode changes**: The app automatically restarts MPV when changing loop modes for reliability

### 6. Docker Build & Run (for Raspberry Pi 4)
1. **Build the image on your x86_64 machine for ARM64:**
   ```bash
   docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
   docker buildx create --use
   docker buildx build --platform linux/arm64 -t kanga2:latest .
   # Optionally export for transfer:
   docker buildx build --platform linux/arm64 -t kanga2:latest --output type=docker,dest=kanga2-arm64.tar .
   ```
2. **Transfer the image to your Pi and load it:**
   ```bash
   scp kanga2-arm64.tar pi@raspberrypi.local:/home/pi/
   # On the Pi:
   docker load -i kanga2-arm64.tar
   ```
3. **Run the container on the Pi:**
   ```bash
   docker run --rm -it \
     --device /dev/fb0:/dev/fb0 \
     --device /dev/snd:/dev/snd \
     -v $(pwd)/app/uploads:/app/uploads \
     -v $(pwd)/playlist.json:/app/playlist.json \
     -p 5000:5000 \
     --privileged \
     kanga2:latest
   ```
   Or use `docker-compose up` if you have a `docker-compose.yml`.

### 7. Technical Notes
- MPV is started with framebuffer output (see `mpv_controller.py` for options)
- All playlist and state is managed in the container, with uploads and playlist.json mapped to the host
- The UI is fully web-based and works from any device on the same network

### 8. Troubleshooting
- If playback is stuck or the playlist is out of sync, use the 'Restart MPV' button
- If you see nothing on the screen, check that `/dev/fb0` is not in use by another process and that your display is connected
- For audio issues, ensure `/dev/snd` is mapped and your Pi's audio is configured
- For advanced debugging, check `server.log` and `mpv.log` in the project directory

---
For more details, see the README or ask for help!
