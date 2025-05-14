# Backend Specifications (Flask)

## 1. Overview

The backend will be a Flask application responsible for handling media uploads, managing the playback queue, and controlling MPV.

## 2. API Endpoints

All endpoints will be prefixed with `/api`.

*   **`POST /api/upload`**
    *   **Description**: Uploads one or more media files (images, videos).
    *   **Request**: `multipart/form-data` containing the files.
    *   **Response**:
        *   Success (200 OK): `{ "message": "Files uploaded successfully", "filenames": ["file1.jpg", "file2.mp4"] }`
        *   Error (e.g., 400 Bad Request, 500 Internal Server Error): `{ "error": "Error message" }`
    *   **Action**: Saves files to the `/app/uploads/` directory. Updates the internal media queue (e.g., a Python list or a simple SQLite table).

*   **`GET /api/playlist`**
    *   **Description**: Retrieves the current media playlist.
    *   **Response**:
        *   Success (200 OK): `{ "playlist": ["file1.jpg", "file2.mp4", ...], "currentIndex": 0, "isPlaying": false, "loop": true }`
        *   Error (500 Internal Server Error): `{ "error": "Error message" }`

*   **`POST /api/control/play`**
    *   **Description**: Starts or resumes playback. If a specific item is provided, it plays that item. If not, it plays from the current position or the beginning.
    *   **Request (optional JSON body)**: `{ "filename": "optional_specific_file.mp4" }`
    *   **Response**: `{ "status": "playing", "currentFile": "file_being_played.mp4" }` or `{ "error": "message" }`
    *   **Action**: Instructs `mpv_controller.py` to play the media.

*   **`POST /api/control/pause`**
    *   **Description**: Pauses playback.
    *   **Response**: `{ "status": "paused" }` or `{ "error": "message" }`
    *   **Action**: Instructs `mpv_controller.py` to pause.

*   **`POST /api/control/stop`**
    *   **Description**: Stops playback and tells MPV to show a black screen.
    *   **Response**: `{ "status": "stopped" }` or `{ "error": "message" }`
    *   **Action**: Instructs `mpv_controller.py` to stop and clear the screen.

*   **`POST /api/control/next`**
    *   **Description**: Skips to the next media item.
    *   **Response**: `{ "status": "playing_next", "currentFile": "next_file.mp4" }` or `{ "status": "playlist_ended" }` or `{ "error": "message" }`
    *   **Action**: Instructs `mpv_controller.py` to play the next item. Handles looping if enabled.

*   **`POST /api/control/previous`**
    *   **Description**: Skips to the previous media item.
    *   **Response**: `{ "status": "playing_previous", "currentFile": "previous_file.mp4" }` or `{ "error": "message" }`
    *   **Action**: Instructs `mpv_controller.py` to play the previous item.

*   **`POST /api/control/set_next`**
    *   **Description**: Sets a specific file to be played next after the current one finishes.
    *   **Request (JSON body)**: `{ "filename": "file_to_play_next.mp4" }`
    *   **Response**: `{ "status": "next_item_set", "nextFile": "file_to_play_next.mp4" }` or `{ "error": "File not found" }`
    *   **Action**: Modifies the playback queue.

*   **`POST /api/playlist/clear`**
    *   **Description**: Clears the entire playlist.
    *   **Response**: `{ "status": "playlist_cleared" }`
    *   **Action**: Clears the media queue and stops playback if active.

*   **`POST /api/settings/loop`**
    *   **Description**: Toggles playlist looping.
    *   **Request (JSON body)**: `{ "loop": true/false }`
    *   **Response**: `{ "loop_status": true/false }`

*   **`POST /api/settings/transition` (Optional - could be fixed)**
    *   **Description**: Sets the preferred transition.
    *   **Request (JSON body)**: `{ "transition": "fade" | "dissolve" | "slide" }`
    *   **Response**: `{ "transition_set": "fade" }`

## 3. Media Management

*   Uploaded files will be stored in `/app/uploads/`.
*   The playlist can be a simple Python list of filenames stored in memory or persisted in a very simple SQLite database if needed for robustness across server restarts.
    *   **SQLite Option (`database.py`)**:
        *   Table: `media_queue (id INTEGER PRIMARY KEY, filename TEXT, sort_order INTEGER)`
        *   Functions: `add_to_queue(filename)`, `get_queue()`, `clear_queue()`, `reorder_queue()`.

## 4. Error Handling

*   Consistent JSON error responses: `{ "error": "Descriptive error message" }`.
*   Proper HTTP status codes (400, 404, 500).

## 5. Logging

*   Flask's built-in logger will be configured to write to `server.log`.
*   Log requests, errors, and significant actions (e.g., playback start/stop).
*   See `copilot_instructions_logging.md` for more details.

## 6. `main.py` (Flask App Structure - Simplified)

```python
from flask import Flask, request, jsonify, render_template
# import mpv_controller
# import logging_config

app = Flask(__name__)
# logging_config.setup_logging(app)

# In-memory playlist for simplicity, or use database.py
playlist = []
current_index = -1
is_playing = False
loop_playlist = False
current_transition = "fade" # Default

UPLOAD_FOLDER = 'app/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

# --- API Endpoints ---
# /api/upload
# /api/playlist
# /api/control/play
# /api/control/pause
# /api/control/stop
# /api/control/next
# /api/control/previous
# /api/control/set_next
# /api/playlist/clear
# /api/settings/loop
# /api/settings/transition

if __name__ == '__main__':
    # Ensure upload folder exists
    # os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(host='0.0.0.0', port=5000) # Accessible on the network
```

## 7. Security Considerations (Basic)

*   Since this is a local network application for a single user, security is not the primary focus, but:
    *   Validate file uploads (e.g., allowed extensions, sanitize filenames to prevent path traversal).
    *   No direct execution of user input.
