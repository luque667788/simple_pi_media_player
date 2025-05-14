from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import logging
import time # Added to fix NameError
import json # Added for playlist persistence

# Custom logging setup
from logging_config import setup_logging

# MPV Controller (initially a placeholder, will be developed)
from mpv_controller import MPVController

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

# --- Configuration ---
# Determine project root dynamically (assuming main.py is in 'app' directory)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'app', 'uploads')
PLAYLIST_FILE = os.path.join(PROJECT_ROOT, 'playlist.json') # For persisting playlist
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # 300 MB upload limit

# --- Logging Setup ---
# Call setup_logging, passing the app instance and desired log file name (relative to project root)
setup_logging(app, log_filename="server.log")
logger = app.logger # Use Flask's configured logger

# --- Media Management (In-memory for simplicity first) ---
media_playlist = [] # List of filenames (relative to UPLOAD_FOLDER)
current_media_index = -1
is_playing = False
loop_playlist = False
# current_transition = "fade" # Default, if we implement selectable transitions

# --- Playlist Persistence Functions ---
def load_playlist_from_file():
    global media_playlist
    try:
        if os.path.exists(PLAYLIST_FILE):
            with open(PLAYLIST_FILE, 'r') as f:
                loaded_playlist = json.load(f)
                if isinstance(loaded_playlist, list):
                    media_playlist = loaded_playlist
                    logger.info(f"Playlist loaded from {PLAYLIST_FILE}: {media_playlist}")
                else:
                    logger.warning(f"Invalid playlist format in {PLAYLIST_FILE}. Starting with empty playlist.")
                    media_playlist = []
        else:
            logger.info(f"{PLAYLIST_FILE} not found. Starting with empty playlist.")
            media_playlist = []
    except Exception as e:
        logger.error(f"Error loading playlist from {PLAYLIST_FILE}: {e}. Starting with empty playlist.")
        media_playlist = []

def save_playlist_to_file():
    try:
        with open(PLAYLIST_FILE, 'w') as f:
            json.dump(media_playlist, f, indent=4)
        logger.info(f"Playlist saved to {PLAYLIST_FILE}")
    except Exception as e:
        logger.error(f"Error saving playlist to {PLAYLIST_FILE}: {e}")

# Load playlist at startup
load_playlist_from_file()

# --- MPV Controller Instance ---
mpv = MPVController() # Initialize the controller

# --- Utility Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    logger.info(f"Serving index.html. Current playlist: {media_playlist}")
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_files():
    global media_playlist
    if 'mediaFiles' not in request.files:
        logger.warning("Upload attempt with no 'mediaFiles' part.")
        return jsonify({"error": "No file part in the request"}), 400
    
    files = request.files.getlist('mediaFiles')
    uploaded_filenames = []
    errors = []

    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        try:
            os.makedirs(app.config['UPLOAD_FOLDER'])
            logger.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")
        except OSError as e:
            logger.error(f"Could not create upload folder: {e}")
            return jsonify({"error": "Could not create upload directory on server."}), 500

    for file in files:
        if file.filename == '':
            logger.warning("Upload attempt with an empty filename.")
            errors.append("One or more files had no selected filename.")
            continue
        if file and allowed_file(file.filename):
            filename = file.filename # Consider werkzeug.utils.secure_filename for production
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(save_path)
                if filename not in media_playlist: # Avoid duplicates
                    media_playlist.append(filename)
                uploaded_filenames.append(filename)
                logger.info(f"Successfully uploaded and saved: {filename}")
            except Exception as e:
                logger.error(f"Error saving file {filename}: {e}")
                errors.append(f"Could not save file {filename}.")
        elif file.filename:
            logger.warning(f"Upload attempt with disallowed file type: {file.filename}")
            errors.append(f"File type not allowed for {file.filename}.")

    if uploaded_filenames:
        save_playlist_to_file() # Save playlist after successful uploads
        return jsonify({
            "message": "Files processed.", 
            "uploaded": uploaded_filenames, 
            "playlist": media_playlist,
            "errors": errors
        }), 200 if not errors else 207 # 207 Multi-Status if some uploads failed
    else:
        return jsonify({"error": "No files were successfully uploaded.", "details": errors}), 400

@app.route('/api/playlist', methods=['GET'])
def get_playlist():
    global current_media_index, is_playing, loop_playlist
    mpv_status = mpv.get_playback_status()
    # Try to sync internal state with MPV's reported state if possible
    # This is a simplified sync; a more robust sync would involve deeper checks
    is_playing = mpv_status.get('is_playing_media', is_playing)
    current_file_from_mpv = mpv_status.get('current_file')
    
    # Update current_media_index based on what MPV says it's playing
    if current_file_from_mpv and current_file_from_mpv in media_playlist:
        try:
            current_media_index = media_playlist.index(current_file_from_mpv)
        except ValueError:
            # File MPV is playing is not in our known playlist, or playlist is out of sync
            logger.warning(f"MPV playing {current_file_from_mpv}, not in current Flask playlist or index out of sync.")
            # Reset index if file not found, or handle as appropriate
            # current_media_index = -1 
    elif not current_file_from_mpv and not is_playing:
        # If MPV reports no file and not playing, reflect that we are not at a specific index
        # current_media_index = -1 # Or keep last known if that's preferred UX
        pass # Keep current_media_index as is, might be pointing to the *next* to play

    logger.debug(f"Playlist requested. Current: {media_playlist}, Index: {current_media_index}, Playing: {is_playing}, Loop: {loop_playlist}")
    return jsonify({
        "playlist": media_playlist,
        "currentIndex": current_media_index,
        "currentFile": media_playlist[current_media_index] if 0 <= current_media_index < len(media_playlist) else None,
        "isPlaying": is_playing,
        "loop": loop_playlist,
        "mpv_is_running": mpv_status.get('is_mpv_running', False)
    })

@app.route('/api/control/play', methods=['POST'])
def control_play():
    global current_media_index, is_playing, media_playlist
    data = request.get_json(silent=True) or {}
    target_filename = data.get('filename')

    if not mpv.start_player(): # Ensure MPV is running, start if not.
        logger.error("MPV failed to start. Cannot play.")
        return jsonify({"error": "MPV player is not available."}), 503

    if target_filename:
        if target_filename in media_playlist:
            current_media_index = media_playlist.index(target_filename)
        else:
            logger.warning(f"Play requested for specific file '{target_filename}' not in playlist.")
            return jsonify({"error": f"File '{target_filename}' not found in playlist."}), 404
    elif not media_playlist:
        logger.info("Play command received but playlist is empty.")
        return jsonify({"status": "playlist_empty", "message": "Playlist is empty. Upload media first."}), 400
    elif current_media_index == -1 and media_playlist: # If no specific file and playlist not empty, start from beginning
        current_media_index = 0
    elif not (0 <= current_media_index < len(media_playlist)) and media_playlist: # If index is somehow invalid, reset
        logger.warning(f"Invalid current_media_index {current_media_index}, resetting to 0.")
        current_media_index = 0
    
    # If we are here, current_media_index should be valid for a non-empty playlist
    if not media_playlist: # Double check after logic
        return jsonify({"status": "playlist_empty", "message": "Playlist is empty."}), 400

    file_to_play = media_playlist[current_media_index]
    logger.info(f"Play command: Attempting to play '{file_to_play}' at index {current_media_index}")

    if mpv.load_file(file_to_play): # load_file now also implies play if MPV was idle
        if mpv.play(): # Ensure it's unpaused
            is_playing = True
            logger.info(f"Playback started for: {file_to_play}")
            return jsonify({"status": "playing", "currentFile": file_to_play, "currentIndex": current_media_index})
        else:
            is_playing = False # mpv.play() might have failed to unpause
            logger.error(f"MPV loaded file {file_to_play} but failed to ensure playback state.")
            return jsonify({"error": f"Loaded {file_to_play} but failed to start/resume playback in MPV."}), 500
    else:
        is_playing = False
        logger.error(f"MPV failed to load file: {file_to_play}")
        return jsonify({"error": f"MPV could not load file '{file_to_play}'."}), 500

@app.route('/api/control/pause', methods=['POST'])
def control_pause():
    global is_playing
    if mpv.pause():
        is_playing = False
        logger.info("Playback paused.")
        return jsonify({"status": "paused"})
    else:
        logger.warning("Failed to send pause command to MPV or MPV not running.")
        # Check if MPV is running at all
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to pause playback."}), 500

@app.route('/api/control/toggle_pause', methods=['POST'])
def control_toggle_pause():
    global is_playing
    # We need a more reliable way to get the new state from mpv_controller
    # For now, we'll assume the internal is_playing state of mpv_controller is updated
    if mpv.toggle_pause():
        # Update Flask's is_playing based on the controller's assumed state after toggle
        mpv_state = mpv.get_playback_status() # Get the latest assumed state
        is_playing = mpv_state.get('is_playing_media', is_playing)
        logger.info(f"Playback pause toggled. New assumed playing state: {is_playing}")
        return jsonify({"status": "toggled_pause", "isPlaying": is_playing})
    else:
        logger.warning("Failed to send toggle_pause command to MPV.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to toggle pause."}), 500

@app.route('/api/control/stop', methods=['POST'])
def control_stop():
    global is_playing, current_media_index
    if mpv.stop():
        is_playing = False
        current_media_index = -1 # Explicitly reset index when stopping
        logger.info("Playback stopped. MPV now idle (black screen). Index reset.")
        return jsonify({"status": "stopped"})
    else:
        logger.warning("Failed to send stop command to MPV.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to stop playback."}), 500

def _play_next_or_prev(direction):
    global current_media_index, is_playing, media_playlist, loop_playlist

    if not media_playlist:
        logger.info(f"Next/Prev called but playlist is empty.")
        mpv.stop() # Ensure MPV is stopped if it was somehow playing
        is_playing = False
        return jsonify({"status": "playlist_empty"}), 400

    if not mpv.get_playback_status().get('is_mpv_running'):
        logger.warning("Next/Prev called but MPV is not running. Attempting to start.")
        if not mpv.start_player():
             return jsonify({"error": "MPV is not running and could not be started."}), 503
        # If MPV just started, and we want to play next/prev from a known state, we might need to load current_media_index first
        # For now, assume if it wasn't running, we start from index 0 or the current_media_index if valid.
        if not (0 <= current_media_index < len(media_playlist)):
            current_media_index = 0 # Default to first item if index is invalid
    
    num_items = len(media_playlist)
    if direction == "next":
        current_media_index += 1
        if current_media_index >= num_items:
            if loop_playlist:
                current_media_index = 0
                logger.info("Reached end of playlist, looping to start.")
            else:
                logger.info("Reached end of playlist, no loop. Stopping.")
                mpv.stop()
                is_playing = False
                current_media_index = num_items -1 # Stay on last item visually
                return jsonify({"status": "playlist_ended"})
    elif direction == "previous":
        current_media_index -= 1
        if current_media_index < 0:
            if loop_playlist:
                current_media_index = num_items - 1
                logger.info("Reached start of playlist, looping to end.")
            else:
                logger.info("Reached start of playlist, no loop. Staying at first item.")
                current_media_index = 0
                # Optionally stop or let it continue playing the first item if it was already playing
                # For now, we assume if they hit prev on first item, they want it to replay or stay.
                # If it wasn't playing, it will load and play this item.

    file_to_play = media_playlist[current_media_index]
    logger.info(f"Changing track ({direction}) to: {file_to_play} at index {current_media_index}")
    if mpv.load_file(file_to_play):
        if mpv.play(): # Ensure it plays
            is_playing = True
            return jsonify({"status": f"playing_{direction}", "currentFile": file_to_play, "currentIndex": current_media_index})
        else:
            is_playing = False
            logger.error(f"MPV loaded {file_to_play} but failed to ensure playback state.")
            return jsonify({"error": f"Loaded {file_to_play} but failed to start/resume playback in MPV."}), 500
    else:
        is_playing = False
        logger.error(f"MPV failed to load file for {direction}: {file_to_play}")
        # Attempt to recover or stop
        mpv.stop()
        return jsonify({"error": f"MPV could not load file '{file_to_play}' for {direction}. Playback stopped."}), 500

@app.route('/api/control/next', methods=['POST'])
def control_next():
    return _play_next_or_prev("next")

@app.route('/api/control/previous', methods=['POST'])
def control_previous():
    return _play_next_or_prev("previous")

@app.route('/api/playlist/set_next', methods=['POST'])
def set_next_track():
    # This is a more complex feature: reordering the playlist or inserting.
    # For simplicity, this could mean "play this file *after* the current one finishes".
    # MPV's internal playlist (`playlist-play-index`, `loadfile <file> append-play`) could handle this.
    # Or, Flask reorders its `media_playlist`.
    # Let's implement a simple version: if a file is playing, queue this one up. If not, just play it.
    global media_playlist, current_media_index, is_playing
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename missing in request."}, 400)
    
    filename_to_set_next = data['filename']
    if filename_to_set_next not in media_playlist:
        return jsonify({"error": f"File '{filename_to_set_next}' not found in playlist."}), 404

    # Simplest interpretation: make this the item at current_media_index + 1
    # and adjust the rest of the playlist. This requires list manipulation.
    try:
        target_idx_in_playlist = media_playlist.index(filename_to_set_next)
    except ValueError:
        return jsonify({"error": "File somehow not in playlist after check (race condition?)"}), 500

    # If nothing is playing, or no valid current index, just make it the current and play
    if not is_playing or not (0 <= current_media_index < len(media_playlist)):
        current_media_index = target_idx_in_playlist
        # Effectively becomes a 'play this file' command
        save_playlist_to_file() # Playlist order might change if it plays now
        return control_play() # Reuse the play logic
    else:
        # Item is playing. Reorder playlist: remove target, insert after current_media_index
        logger.info(f"Setting '{filename_to_set_next}' to play after '{media_playlist[current_media_index]}'.")
        media_playlist.pop(target_idx_in_playlist)
        # Insert after current, or at end if current is last
        new_pos = current_media_index + 1
        media_playlist.insert(new_pos, filename_to_set_next)
        save_playlist_to_file() # Save reordered playlist
        logger.info(f"Playlist reordered. New playlist: {media_playlist}")
        return jsonify({"status": "next_item_set", "nextFile": filename_to_set_next, "playlist": media_playlist})


@app.route('/api/settings/loop', methods=['POST'])
def set_loop():
    global loop_playlist
    data = request.get_json()
    if data and 'loop' in data and isinstance(data['loop'], bool):
        loop_playlist = data['loop']
        logger.info(f"Playlist loop status set to: {loop_playlist}")
        return jsonify({"loop_status": loop_playlist})
    return jsonify({"error": "Invalid request. 'loop' boolean field required."}), 400

@app.route('/api/playlist/delete', methods=['POST'])
def delete_file_from_playlist():
    global media_playlist, current_media_index, is_playing
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename missing in request."}), 400

    filename = data['filename']
    if filename not in media_playlist:
        return jsonify({"error": f"File '{filename}' not found in playlist."}), 404

    idx = media_playlist.index(filename)
    media_playlist.pop(idx)

    # Remove file from uploads folder
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file from disk: {file_path}")
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")

    # Adjust current_media_index if needed
    if current_media_index == idx:
        mpv.stop()
        is_playing = False
        current_media_index = -1
    elif current_media_index > idx:
        current_media_index -= 1

    save_playlist_to_file()
    logger.info(f"Deleted '{filename}' from playlist.")
    return jsonify({"status": "deleted", "filename": filename, "playlist": media_playlist})

# Serve uploaded files (mainly for potential direct access or if frontend needs to load them for previews)
# In this app, MPV accesses them directly from filesystem, so this might not be strictly needed by frontend for playback.
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    logger.debug(f"Request for uploaded file: {filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/mpv/restart', methods=['POST'])
def restart_mpv_route():
    logger.info("API call to restart MPV.")
    mpv.terminate_player() # Terminate existing instance
    time.sleep(0.5) # Brief pause
    if mpv.start_player(): # Start a new instance
        logger.info("MPV restarted successfully via API.")
        return jsonify({"status": "mpv_restarted"}), 200
    else:
        logger.error("Failed to restart MPV via API.")
        return jsonify({"error": "Failed to restart MPV."}), 500


# --- Application Teardown ---
@app.teardown_appcontext
def teardown_mpv(exception=None):
    # This is called when the application context ends. Good for initial MPV start.
    # However, for ensuring MPV is *always* running when a request comes in, 
    # checks within routes or a @before_request might be more suitable for starting.
    # For cleanup on Flask app *exit*, this is not guaranteed for all exit types (e.g. crash, kill signal)
    # A more robust MPV cleanup might be needed via atexit or signal handling if Flask dev server is killed. 
    pass # MPV start is handled by first command or a dedicated startup check.

import atexit
def cleanup_on_exit():
    logger.info("Flask application is exiting. Terminating MPV player.")
    mpv.terminate_player()
atexit.register(cleanup_on_exit)


if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        logger.info(f"Created upload folder: {UPLOAD_FOLDER} on startup.")
    
    # Playlist is loaded by load_playlist_from_file() call earlier
    logger.info(f"Initial playlist: {media_playlist}")

    # Try to start MPV when Flask app starts, so it's ready.
    logger.info("Attempting to start MPV on Flask application startup...")
    if mpv.start_player():
        logger.info("MPV started successfully in idle mode.")
    else:
        logger.warning("MPV failed to start on application startup. It may need to be started manually or via an API call.")
        # The app can still run, but playback will fail until MPV is up.

    app.run(host='0.0.0.0', port=5000, debug=False) # debug=False for production, True for dev
