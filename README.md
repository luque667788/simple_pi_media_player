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