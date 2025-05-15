from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import logging
import time # Added to fix NameError
import json # Added for playlist persistence
import threading # For the image auto-advance timer

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
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

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
current_loop_mode = 'none'  # Persist the last set loop mode
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
    global current_loop_mode, current_media_index, is_playing, media_playlist, loop_playlist

    mpv_status = mpv.get_playback_status()
    
    # --- AUTO-ADVANCE FOR VIDEOS ---
    # This section can be largely removed or simplified if MPV handles playlist advancement internally
    # For 'playlist' mode, MPV's eof-reached + loop-playlist=inf will handle advancement.
    # For 'none' mode, MPV's eof-reached + loop-playlist=no + keep-open=no will stop it.
    # For 'file' mode, MPV's loop-file=inf handles it.

    # The main purpose of get_playlist is now to report the current state accurately.
    # We need to get the current file and index from MPV if possible.
    
    mpv_is_running = mpv_status.get('is_mpv_running', False)
    actual_current_file_from_mpv = None
    is_mpv_playing_media = False

    if mpv_is_running:
        # Try to get the 'path' or 'filename' property for the currently playing media
        path_resp = mpv._execute_command_and_get_response(["get_property", "path"])
        if path_resp and path_resp.get("data") is not None:
            actual_current_file_from_mpv = os.path.basename(path_resp["data"])
            # logger.debug(f"MPV current path: {path_resp['data']}, basename: {actual_current_file_from_mpv}")
        
        # Get playback state (pause status)
        pause_resp = mpv._execute_command_and_get_response(["get_property", "pause"])
        if pause_resp and "data" in pause_resp:
            is_mpv_playing_media = not pause_resp["data"] # True if not paused
            if is_playing != is_mpv_playing_media:
                logger.debug(f"Flask is_playing ({is_playing}) out of sync with MPV is_mpv_playing_media ({is_mpv_playing_media}). Syncing.")
                is_playing = is_mpv_playing_media
        
        # Sync current_media_index with MPV's playlist-pos if in 'playlist' mode
        if current_loop_mode == 'playlist':
            pos_resp = mpv._execute_command_and_get_response(["get_property", "playlist-pos"])
            if pos_resp and pos_resp.get("data") is not None:
                mpv_playlist_pos = int(pos_resp["data"])
                if 0 <= mpv_playlist_pos < len(media_playlist):
                    if current_media_index != mpv_playlist_pos:
                        logger.debug(f"Syncing current_media_index from {current_media_index} to {mpv_playlist_pos} based on MPV playlist-pos.")
                        current_media_index = mpv_playlist_pos
                    # Also sync the filename based on this index
                    actual_current_file_from_mpv = media_playlist[current_media_index]
                else:
                    logger.warning(f"MPV playlist-pos {mpv_playlist_pos} is out of sync with Flask media_playlist length {len(media_playlist)}.")
            # If MPV reports a file but it's not in our list, it's a desync (e.g. manual load via other means)
            elif actual_current_file_from_mpv and actual_current_file_from_mpv not in media_playlist:
                 logger.warning(f"MPV playing {actual_current_file_from_mpv}, which is NOT in Flask's media_playlist. State may be desynced.")
        
        # If MPV is idle (no file loaded), actual_current_file_from_mpv might be None
        if actual_current_file_from_mpv is None and is_mpv_playing_media:
            # This can happen if MPV is "playing" but it's an empty/idle state after 'stop'
            is_playing = False # Correct Flask's state
            logger.debug("MPV reports no file but was considered playing by Flask; correcting.")
        elif actual_current_file_from_mpv and actual_current_file_from_mpv in media_playlist:
            # If we have a file from MPV and it's in our playlist, ensure index is correct
            # This is a fallback if not in 'playlist' mode or if playlist-pos failed
            try:
                new_index = media_playlist.index(actual_current_file_from_mpv)
                if current_media_index != new_index and current_loop_mode != 'playlist': # Avoid conflict with playlist-pos sync
                    logger.debug(f"Syncing current_media_index (non-playlist mode) from {current_media_index} to {new_index} for {actual_current_file_from_mpv}.")
                    current_media_index = new_index
            except ValueError:
                 logger.warning(f"MPV playing {actual_current_file_from_mpv}, in Flask playlist but index() failed.")
        
    # Update Flask's global is_playing state based on MPV's actual state
    # This is crucial because MPV now controls its own state more directly
    if is_playing != is_mpv_playing_media and mpv_is_running:
        logger.info(f"Flask's is_playing ({is_playing}) differs from MPV's ({is_mpv_playing_media}). Updating Flask's state.")
        is_playing = is_mpv_playing_media

    # If MPV is not running, reflect that.
    if not mpv_is_running and is_playing:
        is_playing = False
        current_media_index = -1 # Reset index if MPV died
        logger.info("MPV is not running. Setting is_playing to False and resetting index.")


    # Fallback for currentFile if not accurately determined from MPV
    display_current_file = actual_current_file_from_mpv
    if display_current_file is None and 0 <= current_media_index < len(media_playlist):
        display_current_file = media_playlist[current_media_index]
    elif display_current_file is None and not media_playlist:
        display_current_file = None


    return jsonify({
        "playlist": media_playlist,
        "currentFile": display_current_file,
        "isPlaying": is_playing, # Use the synced is_playing state
        "loop_mode": current_loop_mode,
        "mpv_is_running": mpv_is_running,
        "currentIndex": current_media_index # For UI highlighting
    })

@app.route('/api/control/play', methods=['POST'])
def control_play():
    global current_media_index, is_playing, media_playlist
    
    data = request.get_json(silent=True) or {}
    target_filename = data.get('filename')

    if not mpv.start_player():
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
    elif current_media_index == -1 and media_playlist:
        current_media_index = 0
    elif not (0 <= current_media_index < len(media_playlist)) and media_playlist:
        logger.warning(f"Invalid current_media_index {current_media_index}, resetting to 0.")
        current_media_index = 0
    
    if not media_playlist:
        return jsonify({"status": "playlist_empty", "message": "Playlist is empty."}), 400

    # file_to_play = media_playlist[current_media_index] # Old logic
    # logger.info(f"Play command: Attempting to play '{file_to_play}' at index {current_media_index}")

    success = False
    if current_loop_mode == 'playlist':
        logger.info(f"Play command (playlist mode): Loading entire playlist to MPV, starting at index {current_media_index}")
        if mpv.load_playlist(media_playlist, current_media_index if current_media_index != -1 else 0):
            if mpv.play():
                is_playing = True
                success = True
                logger.info(f"MPV started playing its internal playlist. Current file: {media_playlist[current_media_index if current_media_index != -1 else 0]}")
            else:
                logger.error("MPV loaded playlist but failed to start playback.")
        else:
            logger.error("MPV failed to load the playlist.")
    else: # 'none' or 'file' mode
        file_to_play = media_playlist[current_media_index]
        logger.info(f"Play command (none/file mode): Attempting to play '{file_to_play}' at index {current_media_index}")
        if mpv.load_file(file_to_play):
            if mpv.play():
                is_playing = True
                success = True
                logger.info(f"Playback started for: {file_to_play}")
            else:
                logger.error(f"MPV loaded file {file_to_play} but failed to ensure playback state.")
        else:
            logger.error(f"MPV failed to load file: {file_to_play}")

    if success:
        return jsonify({"status": "playing", "currentFile": media_playlist[current_media_index if current_media_index != -1 else 0], "currentIndex": current_media_index if current_media_index != -1 else 0})
    else:
        is_playing = False
        # Determine more specific error based on logs above
        return jsonify({"error": "Failed to start playback. Check server logs."}), 500

@app.route('/api/control/pause', methods=['POST'])
def control_pause():
    global is_playing
    if mpv.pause():
        is_playing = False
        logger.info("Playback paused.")
        return jsonify({"status": "paused"})
    else:
        logger.warning("Failed to send pause command to MPV or MPV not running.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to pause playback."}), 500

@app.route('/api/control/toggle_pause', methods=['POST'])
def control_toggle_pause():
    global is_playing, current_media_index, media_playlist
    
    was_playing = is_playing 

    if mpv.toggle_pause():
        mpv_state = mpv.get_playback_status()
        is_playing = mpv_state.get('is_playing_media', False)
        current_file_from_mpv = mpv_state.get('current_file')

        logger.info(f"Toggle pause successful. MPV reports playing: {is_playing}, file: {current_file_from_mpv}")

        return jsonify({"status": "toggled", "isPlaying": is_playing, "currentFile": current_file_from_mpv})
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
        current_media_index = -1
        logger.info("Playback stopped. MPV now idle (black screen). Index reset.")
        return jsonify({"status": "stopped"})
    else:
        logger.warning("Failed to send stop command to MPV.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to stop playback."}), 500

def _play_next_or_prev(direction, from_auto_advance=False): # from_auto_advance is no longer needed here
    global current_media_index, is_playing, media_playlist, loop_playlist, current_loop_mode

    # This function's logic changes significantly when MPV manages the playlist.
    # For 'playlist' mode, we just tell MPV to go next/prev.
    # For 'none' or 'file' mode, Flask still manages the index and loads files one by one.

    is_background = from_auto_advance # Retain for now, though its role diminishes
    if not is_background:
        try:
            from flask import has_app_context
            is_background = not has_app_context()
        except (ImportError, RuntimeError):
            is_background = True

    logger.debug(f"_play_next_or_prev called for '{direction}'. Loop mode: {current_loop_mode}")

    if not media_playlist:
        logger.info(f"Next/Prev called but playlist is empty.")
        mpv.stop()
        is_playing = False
        return jsonify({"status": "playlist_empty"}), 400 # No background check, always return JSON

    if not mpv.get_playback_status().get('is_mpv_running'):
        logger.warning("Next/Prev called but MPV is not running. Attempting to start.")
        if not mpv.start_player():
            return jsonify({"error": "MPV is not running and could not be started."}), 503
        # If MPV just started, and we are in playlist mode, load the playlist
        if current_loop_mode == 'playlist':
            start_idx = 0 if current_media_index == -1 else current_media_index
            mpv.load_playlist(media_playlist, start_idx)
        elif not (0 <= current_media_index < len(media_playlist)): # For non-playlist modes
            current_media_index = 0
    
    if current_loop_mode == 'playlist':
        if direction == "next":
            mpv.playlist_next()
        elif direction == "previous":
            mpv.playlist_prev()
        
        # After telling MPV to change track, we need to get the updated status
        # The actual current_file and current_media_index will be updated by get_playlist polling
        # For an immediate response, we could try to query here, but it might be slow.
        # For now, let the polling handle the UI update.
        is_playing = True # Assume it will play
        # We don't know the file for sure without querying, so return a generic success
        # Or, call get_playlist's core logic here to get fresh data.
        # For simplicity, let's rely on the next get_playlist poll.
        logger.info(f"Sent {direction} command to MPV in playlist mode.")
        # Return a status that indicates the command was sent.
        # The UI will update with the actual file on the next status refresh.
        # We need to fetch the new current file and index from MPV
        time.sleep(0.2) # Give MPV a moment to process, then query
        new_status = get_playlist_data_for_response() # A helper to get fresh data
        return jsonify(new_status)

    else: # 'none' or 'file' mode - Flask manages playlist logic
        num_items = len(media_playlist)
        if current_media_index == -1 : # If stopped or uninitialized, start from 0 for next/prev
            current_media_index = 0
            if direction == "previous": # if prev is hit when uninitialized, go to last if looping, else 0
                 current_media_index = num_items -1 if loop_playlist else 0


        original_index = current_media_index
        if direction == "next":
            current_media_index += 1
            if current_media_index >= num_items:
                if loop_playlist: # This loop_playlist is Flask's, not MPV's loop-playlist property
                    current_media_index = 0
                    logger.info("Reached end of Flask playlist, looping to start.")
                else:
                    logger.info("Reached end of Flask playlist, no loop. Stopping.")
                    mpv.stop()
                    is_playing = False
                    current_media_index = num_items -1 # Stay on last item visually
                    return jsonify({"status": "playlist_ended", "currentFile": media_playlist[current_media_index], "currentIndex": current_media_index})
        elif direction == "previous":
            current_media_index -= 1
            if current_media_index < 0:
                if loop_playlist: # Flask's loop_playlist
                    current_media_index = num_items - 1
                    logger.info("Reached start of Flask playlist, looping to end.")
                else:
                    logger.info("Reached start of Flask playlist, no loop. Staying at first item.")
                    current_media_index = 0
        
        if not (0 <= current_media_index < len(media_playlist)): # Should not happen with logic above
            logger.error(f"Index {current_media_index} out of bounds after next/prev logic. Resetting to 0.")
            current_media_index = 0
            if not media_playlist: # Should have been caught earlier
                 return jsonify({"error": "Playlist is empty"}), 400


        file_to_play = media_playlist[current_media_index]
        logger.info(f"Changing track ({direction}) via Flask to: {file_to_play} at index {current_media_index}")
        if mpv.load_file(file_to_play):
            if mpv.play():
                is_playing = True
                logger.info(f"Successfully loaded and started {file_to_play} for {direction}.")
                return jsonify({"status": f"playing_{direction}", "currentFile": file_to_play, "currentIndex": current_media_index})
            else:
                is_playing = False
                logger.error(f"Loaded {file_to_play} for {direction}, but failed to start playback.")
                return jsonify({"error": f"Loaded {file_to_play} but failed to start/resume playback in MPV."}), 500
        else:
            is_playing = False
            logger.error(f"MPV failed to load file for {direction}: {file_to_play}")
            mpv.stop() # Stop MPV if load fails
            current_media_index = original_index # Revert index on failure
            return jsonify({"error": f"MPV could not load file '{file_to_play}' for {direction}. Playback stopped."}), 500

def get_playlist_data_for_response():
    """Helper function to get current playlist data, callable by other routes for immediate refresh."""
    global current_media_index, is_playing, media_playlist, current_loop_mode

    mpv_status_internal = mpv.get_playback_status() # Raw status from MPV
    mpv_is_running_internal = mpv_status_internal.get('is_mpv_running', False)
    actual_current_file_internal = None
    is_mpv_playing_media_internal = False

    if mpv_is_running_internal:
        path_resp_internal = mpv._execute_command_and_get_response(["get_property", "path"])
        if path_resp_internal and path_resp_internal.get("data") is not None:
            actual_current_file_internal = os.path.basename(path_resp_internal["data"])
        
        pause_resp_internal = mpv._execute_command_and_get_response(["get_property", "pause"])
        if pause_resp_internal and "data" in pause_resp_internal:
            is_mpv_playing_media_internal = not pause_resp_internal["data"]
        
        if current_loop_mode == 'playlist':
            pos_resp_internal = mpv._execute_command_and_get_response(["get_property", "playlist-pos"])
            if pos_resp_internal and pos_resp_internal.get("data") is not None:
                mpv_playlist_pos_internal = int(pos_resp_internal["data"])
                if 0 <= mpv_playlist_pos_internal < len(media_playlist):
                    current_media_index = mpv_playlist_pos_internal
                    actual_current_file_internal = media_playlist[current_media_index]
        elif actual_current_file_internal and actual_current_file_internal in media_playlist:
            try:
                current_media_index = media_playlist.index(actual_current_file_internal)
            except ValueError:
                pass # Keep previous index if file name lookup fails for some reason
        
        if is_playing != is_mpv_playing_media_internal:
             is_playing = is_mpv_playing_media_internal
    else:
        if is_playing:
            is_playing = False
        current_media_index = -1

    display_file = actual_current_file_internal
    if display_file is None and 0 <= current_media_index < len(media_playlist):
        display_file = media_playlist[current_media_index]
    
    return {
        "playlist": media_playlist,
        "currentFile": display_file,
        "isPlaying": is_playing,
        "loop_mode": current_loop_mode,
        "mpv_is_running": mpv_is_running_internal,
        "currentIndex": current_media_index
    }

@app.route('/api/control/next', methods=['POST'])
def control_next():
    return _play_next_or_prev("next")

@app.route('/api/control/previous', methods=['POST'])
def control_previous():
    return _play_next_or_prev("previous")

@app.route('/api/playlist/set_next', methods=['POST'])
def set_next_track():
    global media_playlist, current_media_index, is_playing, current_loop_mode
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename missing in request."}), 400
    
    filename_to_set_next = data['filename']
    if filename_to_set_next not in media_playlist:
        return jsonify({"error": f"File '{filename_to_set_next}' not found in playlist."}), 404

    try:
        target_idx_in_playlist = media_playlist.index(filename_to_set_next)
    except ValueError:
        return jsonify({"error": "File somehow not in playlist after check (race condition?)"}), 500

    # Move the file to the next slot after the current one, do not start playback or change current track
    if not (0 <= current_media_index < len(media_playlist)):
        # If nothing is playing, move the file to the start (after index -1, i.e., at 0)
        new_pos = 0
    else:
        new_pos = current_media_index + 1
    if target_idx_in_playlist == new_pos or target_idx_in_playlist == new_pos - 1:
        # Already in the correct position, nothing to do
        return jsonify({"status": "already_next", "playlist": media_playlist, "currentIndex": current_media_index })
    item_to_move = media_playlist.pop(target_idx_in_playlist)
    # Adjust new_pos if the item was before the insertion point
    if target_idx_in_playlist < new_pos:
        new_pos -= 1
    media_playlist.insert(new_pos, item_to_move)
    save_playlist_to_file()
    logger.info(f"Moved '{filename_to_set_next}' to position {new_pos} (next in playlist). New playlist: {media_playlist}")

    if current_loop_mode == 'playlist':
        # Reload MPV's playlist to update the order, but keep the current track
        mpv_path_resp = mpv._execute_command_and_get_response(["get_property", "path"])
        actual_mpv_playing_file = None
        if mpv_path_resp and mpv_path_resp.get("data") is not None:
            actual_mpv_playing_file = os.path.basename(mpv_path_resp["data"])
        try:
            if actual_mpv_playing_file:
                new_playing_index = media_playlist.index(actual_mpv_playing_file)
            else:
                new_playing_index = current_media_index if 0 <= current_media_index < len(media_playlist) else 0
            mpv.load_playlist(media_playlist, new_playing_index)
            current_media_index = new_playing_index
        except ValueError:
            logger.error("Error finding currently playing file in reordered playlist. Reloading playlist from start.")
            mpv.load_playlist(media_playlist, 0)
            current_media_index = 0

    return jsonify({"status": "next_item_set", "nextFile": filename_to_set_next, "playlist": media_playlist, "currentIndex": current_media_index })

@app.route('/api/settings/loop', methods=['POST'])
def set_loop():
    global loop_playlist
    data = request.get_json()
    if data and 'loop' in data and isinstance(data['loop'], bool):
        loop_playlist = data['loop']
        logger.info(f"Playlist loop status set to: {loop_playlist}")
        return jsonify({"loop_status": loop_playlist})
    return jsonify({"error": "Invalid request. 'loop' boolean field required."}), 400

@app.route('/api/settings/loop_mode', methods=['POST'])
def set_loop_mode():
    global current_loop_mode, loop_playlist, media_playlist, current_media_index, is_playing
    data = request.get_json()
    if not data or 'mode' not in data:
        return jsonify({"error": "Mode missing in request"}), 400
        
    mode = data['mode']
    if mode not in ['none', 'file', 'playlist']:
        return jsonify({"error": "Invalid mode. Use 'none', 'file', or 'playlist'"}), 400
        
    mpv_args = {}
    if mode == 'playlist':
        mpv_args['playlist_files'] = media_playlist
        valid_index = current_media_index if 0 <= current_media_index < len(media_playlist) else 0
        mpv_args['current_index_in_playlist'] = valid_index
    was_playing = is_playing
    if mpv.set_loop_mode(mode, **mpv_args):
        current_loop_mode = mode
        loop_playlist = (mode == 'playlist')
        if was_playing:
            logger.info("Resuming/confirming playback after mode switch.")
            mpv.play()
            is_playing = True
        else:
            is_playing = False
        logger.info(f"Loop mode set to {current_loop_mode} via API.")
        return jsonify(get_playlist_data_for_response())
    return jsonify({"error": "Failed to set loop mode"}), 500

@app.route('/api/control/loop_file', methods=['POST'])
def loop_current_file():
    if mpv.toggle_loop_file():
        return jsonify({"status": "success", "message": "Loop toggled for current file"})
    return jsonify({"status": "error", "message": "Failed to toggle loop"}), 500

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

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file from disk: {file_path}")
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")

    if current_media_index == idx:
        mpv.stop()
        is_playing = False
        current_media_index = -1
    elif current_media_index > idx:
        current_media_index -= 1

    save_playlist_to_file()
    logger.info(f"Deleted '{filename}' from playlist.")
    return jsonify({"status": "deleted", "filename": filename, "playlist": media_playlist})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    logger.debug(f"Request for uploaded file: {filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/mpv/restart', methods=['POST'])
def restart_mpv_route():
    logger.info("API call to restart MPV.")
    mpv.terminate_player()
    time.sleep(0.5)
    if mpv.start_player():
        logger.info("MPV restarted successfully via API.")
        return jsonify({"status": "mpv_restarted"}), 200
    else:
        logger.error("Failed to restart MPV via API.")
        return jsonify({"error": "Failed to restart MPV."}), 500

@app.teardown_appcontext
def teardown_mpv(exception=None):
    pass

import atexit
def cleanup_on_exit():
    logger.info("Flask application is exiting. Terminating MPV player.")
    mpv.terminate_player()
atexit.register(cleanup_on_exit)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        logger.info(f"Created upload folder: {UPLOAD_FOLDER} on startup.")
    
    logger.info(f"Initial playlist: {media_playlist}")

    logger.info("Attempting to start MPV on Flask application startup...")
    if mpv.start_player():
        logger.info("MPV started successfully in idle mode.")
    else:
        logger.warning("MPV failed to start on application startup. It may need to be started manually or via an API call.")

    app.run(host='0.0.0.0', port=5000, debug=False)
