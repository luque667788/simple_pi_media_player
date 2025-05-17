# Kanga Media Player

A simple web-based media player controller for video playback.

## Features

- Upload and manage video files
- Play, pause, and stop video playback
- Loop settings for single files or entire playlists
- Auto-advance through playlist items
- Reorder playlist items using drag-and-drop
- Delete videos from playlist and disk

## New Drag-and-Drop Functionality

The media player now includes a playlist editing mode that allows for:

1. **Edit Mode Toggling**:
   - Click the "Edit Playlist" button to enter edit mode
   - In edit mode, playback stops and controls are disabled
   - Click "Save Playlist" to save the new order and exit edit mode

2. **Drag-and-Drop Reordering**:
   - In edit mode, drag playlist items to reorder them
   - Grab items by the handle on the left side
   - The new order is saved when you click "Save Playlist"

3. **Deletion Rules**:
   - Videos can be deleted at any time in edit mode
   - In normal mode, videos can only be deleted when nothing is playing

## Usage

1. Start the Flask application: `python -m app.main`
2. Access the web interface at: http://localhost:5000
3. Upload videos using the upload section
4. Use the playback controls to manage video playback
5. Click "Edit Playlist" to rearrange your playlist

## Technical Details

- Built with Flask backend
- Uses MPlayer for video playback
- Persistent playlist storage with JSON
- Real-time UI updates
