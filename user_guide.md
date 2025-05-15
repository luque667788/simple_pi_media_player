# Media Player Simplified Guide

## Overview
This simplified media player now focuses on the core features you need:
- Playing/pausing videos and images
- Advancing to the next or previous media
- Looping through a playlist
- Auto-advancing through images with a configurable timer

## Main Features

### Playback Controls
- **Play**: Start playback of the current playlist from the currently selected media
- **Pause**: Pause playback
- **Toggle Pause**: Switch between play and pause states
- **Stop (Black Screen)**: Stop playback and show a black screen
- **Previous**: Go to the previous item in the playlist
- **Next**: Go to the next item in the playlist

### Playlist Management
- **Upload Files**: Add new media files to the playlist
- **Delete**: Remove media files from the playlist and disk
- **Play Next**: Set a specific file to play next after the current one

### Loop Settings
- **No Loop**: Stop at the end of the playlist
- **Loop Current File**: Repeat the current file indefinitely
- **Auto-advance Playlist**: Automatically play the next item and loop back to the beginning when the end is reached

### Image Settings
- **Auto-Advance Interval**: Set the time (in seconds) before automatically advancing to the next item when showing images
  - Set to 0 to disable auto-advancement for images

## Technical Notes
- MPV is used as the backend media player
- The system uses MPV's built-in playlist functionality for improved reliability
- If your media isn't advancing properly, try using the restart script (`restart.sh`)

## Troubleshooting
If you encounter issues with auto-advancement or looping:
1. Click "Restart MPV" to restart the media player process
2. If that doesn't work, run the restart.sh script:
   ```
   ./restart.sh
   ```
3. Set Loop Mode to "Auto-advance Playlist" to ensure proper playlist looping
