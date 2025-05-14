# Developer Decisions and Implementation Log

This document tracks the thought process, decisions made, and steps taken during the development of the MPV-based media player application.

## Phase 1: Project Setup and Initial Backend Structure

**Date:** 2025-05-14

**Goal:** Establish the basic directory structure and create the initial Flask application file (`main.py`) with logging and a placeholder for the MPV controller.

**Thought Process & Decisions:**

1.  **Directory Structure**: Based on `docs/copilot_instructions_overview.md`, the core application will reside in an `app` directory, with subdirectories for `static` (CSS, JS), `templates` (HTML), and `uploads` (media files).
2.  **Main Application File**: `app/main.py` will be the entry point for the Flask backend.
3.  **Logging**: Implement basic logging to `server.log` from the start, as specified in `docs/copilot_instructions_logging.md`. This will help in debugging from the outset.
4.  **MPV Controller Placeholder**: Create an empty `app/mpv_controller.py` which will be developed later. This allows `main.py` to import it without errors during initial development.
5.  **Basic Flask App**: Initialize Flask, define a simple root route (`/`) that will eventually serve the main `index.html`.
6.  **Configuration**: Store upload folder path and other potential configurations.

**Implementation Steps:**

*   Create the `dev_decisions.md` file.
*   Create the directory structure: `app`, `app/static/css`, `app/static/js`, `app/templates`, `app/uploads`.
*   Create `app/logging_config.py` to handle logging setup for the Flask application. This module configures a `RotatingFileHandler` to output logs to `server.log` in the project root, with a defined format and log rotation.
*   Create `app/mpv_controller.py`. This is a significant module responsible for all interactions with MPV.
    *   **Decision**: Use MPV's IPC (Inter-Process Communication) via a Unix socket (`mpvsocket` in the project root) for controlling MPV. This is more robust and flexible than repeatedly launching CLI commands for each action (play, pause, load file).
    *   **Features**:
        *   Starts MPV with specific parameters for the 2-inch screen (`--autofit=240x320`, `--geometry=240x320+0+0`, `--no-osc`, `--no-border`, `--input-ipc-server`, `--idle=yes`, `--log-file`).
        *   Handles starting, stopping (terminating), loading files, playing, pausing, and toggling pause.
        *   Includes basic error handling and logging for MPV actions.
        *   Attempts to clean up the socket file on start and termination.
        *   Includes a `if __name__ == '__main__':` block for standalone testing of MPV control logic.
        *   Logs MPV's own output to `mpv.log` in the project root.
*   Create `app/main.py`:
    *   Initializes the Flask application.
    *   Integrates `logging_config.py` for application-wide logging.
    *   Initializes the `MPVController`.
    *   Defines basic application configuration (upload folder, allowed extensions, max content length).
    *   Implements in-memory playlist management (`media_playlist`, `current_media_index`, `is_playing`, `loop_playlist`).
    *   **Implemented API Endpoints (Initial Set)**:
        *   `/`: Serves `index.html`.
        *   `/api/upload`: Handles file uploads, saves to `app/uploads`, updates the playlist.
        *   `/api/playlist`: Returns the current playlist state.
        *   `/api/control/play`: Plays a specified file or the current/first file.
        *   `/api/control/pause`: Pauses playback.
        *   `/api/control/toggle_pause`: Toggles pause state.
        *   `/api/control/stop`: Stops playback (MPV goes idle, showing black).
        *   `/api/control/next`: Plays the next track, handles looping.
        *   `/api/control/previous`: Plays the previous track, handles looping.
        *   `/api/playlist/set_next`: Reorders the playlist to play a specified file next.
        *   `/api/playlist/clear`: Clears the playlist and stops MPV.
        *   `/api/settings/loop`: Toggles loop mode.
        *   `/uploads/<filename>`: Serves uploaded files (though MPV accesses them directly).
        *   `/api/mpv/restart`: An endpoint to terminate and restart the MPV process.
    *   Includes an `atexit` handler to attempt to terminate MPV when the Flask app exits.
    *   Attempts to start MPV when the Flask application itself starts.
*   Create placeholder `server.log` and `mpv.log` in the project root (done via `touch` command).

## Phase 2: Basic Frontend and Utility Scripts

**Date:** 2025-05-14

**Goal:** Create the initial HTML, CSS, and JavaScript for the frontend, plus the `requirements.txt` and `install.sh` script.

**Thought Process & Decisions:**

1.  **HTML (`index.html`)**: Keep it simple as per `copilot_instructions_frontend.md`. Include sections for upload, controls, and playlist. Use basic HTML elements.
2.  **CSS (`style.css`)**: Minimal styling for readability and usability. Focus on clear button definitions.
3.  **JavaScript (`main.js`)**:
    *   Selects all necessary DOM elements from `index.html`.
    *   Implements an `fetchAPI` helper function for making requests to the backend, including basic error handling and JSON parsing.
    *   `updatePlaylistUI`: Clears and repopulates the playlist `<ul>` based on data from the backend. Adds click listeners to playlist items to play them.
    *   `updateStatusUI`: Updates various spans and elements on the page (current file, player state, MPV process status, loop checkbox) based on backend data.
    *   `fetchAndRefreshStatus`: Calls the `/api/playlist` endpoint and then updates the UI.
    *   **Event Listeners Added For**:
        *   `uploadButton`: Collects files from `mediaUploadInput`, sends them as `FormData` to `/api/upload`, and updates status/playlist.
        *   `playButton`, `pauseButton`, `togglePauseButton`, `stopButton`, `nextButton`, `prevButton`: Call their respective `/api/control/*` endpoints and refresh status.
        *   `loopCheckbox`: Sends its state to `/api/settings/loop`.
        *   `clearPlaylistButton`: Calls `/api/playlist/clear` after confirmation.
        *   `refreshStatusButton`: Manually triggers `fetchAndRefreshStatus`.
        *   `restartMpvButton`: Calls `/api/mpv/restart` after confirmation.
        *   Playlist items (`<li>` created in `updatePlaylistUI`): Click calls `playSpecificFile(filename)` which in turn calls `/api/control/play` with the specific filename.
    *   **Initial Load & Auto-Refresh**: Calls `fetchAndRefreshStatus` on page load and sets an interval to call it every 10 seconds to keep the UI somewhat in sync with the backend state.
4.  **`requirements.txt`**: List Python dependencies. For now, only `Flask`. (Pillow was added to `mpv_controller.py` for the dummy image in its test block, so it should be included if that test is to be easily runnable).
5.  **`install.sh`**: Based on `copilot_instructions_raspberry_pi_setup.md`. This script will update the system, install `python3`, `pip`, `mpv`, `git`, create directories, and install Python requirements.

**Implementation Steps:**

*   Create `app/templates/index.html`.
*   Create `app/static/css/style.css`.
*   Create `app/static/js/main.js`.
*   Create `requirements.txt`.
*   Create `install.sh` in the project root.

## Phase 3: Completing Minimal Functionality

**Date:** 2025-05-14

**Goal:** Ensure all minimal planned features are working, specifically adding the "Set as Next" functionality to the frontend and implementing a basic fade transition effect.

**Thought Process & Decisions:**

1. **"Play Next" Feature**:
   * The backend (`main.py`) already had a `/api/playlist/set_next` API endpoint, but it wasn't fully utilized in the frontend.
   * Add a "Play Next" button to each playlist item to allow users to set which file should play after the current one.
   * This creates a more interactive user experience where users can easily queue up what plays next.

2. **Simple Fade Transition**:
   * Implement a simplified version of the fade transition for media changes in `mpv_controller.py`.
   * For images: gradually decrease alpha (opacity) before loading the new file, then increase it back.
   * For videos: use MPV's internal display-resample video-sync property to enable smoother transitions.
   * This is a basic implementation that provides visual feedback during transitions without complex filter chains.

3. **Frontend Styling**:
   * Update playlist item styling to accommodate the new "Play Next" buttons.
   * Improve the overall layout of playlist items for better usability.

**Implementation Steps:**

* **Frontend Changes**:
  * Modified `updatePlaylistUI()` in `main.js` to include "Play Next" buttons for each item.
  * Added `setNextTrack()` function to handle the API call to `/api/playlist/set_next`.
  * Updated CSS to style the new buttons and improve playlist item layout.

* **Backend Changes**:
  * Enhanced `load_file()` method in `mpv_controller.py` to implement a basic fade transition effect.
  * This uses MPV's alpha property manipulation for images and video-sync property for videos.

### Step 3.1: Fix `NameError` in MPV Restart Route

*   **Issue:** A `NameError: name 'time' is not defined` occurs in the `/api/mpv/restart` route in `app/main.py` because the `time` module was used without being imported.
*   **Action:** Added `import time` at the top of `app/main.py`.

### Step 3.2: Implement Playlist Persistence

*   **Issue:** The media playlist is stored in memory and is lost when the Flask server restarts or the page is refreshed (as the frontend fetches the fresh, empty list from the restarted server).
*   **Goal:** Make the playlist persistent across server restarts.
*   **Decision:** Implement playlist persistence by saving the `media_playlist` to a JSON file (`playlist.json`) in the project root. The playlist will be loaded from this file when the server starts and saved to this file whenever it's modified (e.g., after uploads, clearing, or reordering).
*   **Implementation in `app/main.py`**:
    *   Imported the `json` module.
    *   Defined a `PLAYLIST_FILE` constant for `playlist.json`.
    *   Created `load_playlist_from_file()`: Reads `playlist.json` if it exists and populates `media_playlist`. Handles potential errors during loading (e.g., file not found, invalid JSON) by defaulting to an empty playlist.
    *   Created `save_playlist_to_file()`: Writes the current `media_playlist` to `playlist.json` in a pretty-printed JSON format.
    *   Called `load_playlist_from_file()` once when the Flask application starts to initialize the playlist.
    *   Called `save_playlist_to_file()` in the following routes after the `media_playlist` is modified:
        *   `upload_files()`: After successfully adding new files.
        *   `set_next_track()`: After reordering the playlist.
        *   `clear_playlist()`: After clearing the playlist.
    *   Modified the `if __name__ == '__main__':` block to log the initial playlist after attempting to load it.

**Notes for Future Improvement:**
* The fade transition is basic and could be enhanced with more sophisticated MPV filter chains for true crossfades.

